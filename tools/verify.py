#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""站点自检 / site verifier.

检查 dist/：
  1. 每个 HTML 页面都能在本地 HTTP server 上打开（HTTP 200）；
  2. 站内链接与静态资源都存在（相对路径，任意 base path 可用）；
  3. 没有任何外部依赖（<link>/<script>/<img>/@import/字体）；
  4. Markdown 渲染是否干净：表格、代码块、标题、标题 id、以及是否残留原始标记；
  5. 截图（assets/img/*.png）：合法 PNG、有 alt 文本、相对引用能解析、指南里顺序正确；
  6. 本地 HTTP：页面 + 截图全部 HTTP 200。

用法:
    python tools/verify.py            # 自动起 http.server，自检后关闭
    python tools/verify.py --no-http  # 只做静态检查
"""

from __future__ import annotations

import argparse
import functools
import html as _html
import http.server
import os
import re
import socketserver
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(REPO_ROOT, "dist")

FAIL: list[str] = []
WARN: list[str] = []
OK = 0


def fail(msg: str) -> None:
    FAIL.append(msg)
    print("  FAIL  %s" % msg)


def warn(msg: str) -> None:
    WARN.append(msg)
    print("  warn  %s" % msg)


def ok(msg: str) -> None:
    global OK
    OK += 1
    print("  ok    %s" % msg)


def html_files() -> list[str]:
    out = []
    for base, _dirs, files in os.walk(DIST):
        for name in files:
            if name.endswith(".html"):
                rel = os.path.relpath(os.path.join(base, name), DIST).replace("\\", "/")
                out.append(rel)
    return sorted(out)


# ---------------------------------------------------------------- 静态检查
def check_files_exist() -> None:
    print("\n[1] 站内链接 / 资源 / 外部依赖")
    pages = html_files()
    if not pages:
        fail("dist/ 里没有 HTML —— 先跑 python tools/build.py")
        return

    assets = 0
    external = 0
    for page in pages:
        path = os.path.join(DIST, *page.split("/"))
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()

        # 外部依赖：<link href="http..."> / <script src="http..."> / <img src="http...
        for m in re.finditer(r'<(?:link|script|img)\b[^>]*?(?:href|src)="([^"]+)"', text):
            url = m.group(1)
            if url.startswith(("http://", "https://", "//")):
                external += 1
                fail("%s 引用了外部资源: %s" % (page, url))
        if "@import" in text:
            fail("%s 里出现 @import" % page)

        base_dir = os.path.dirname(path)

        # 相对引用：href/src="..."
        for m in re.finditer(r'(?:href|src)="([^"#][^"]*)"', text):
            ref = m.group(1)
            if ref.startswith(("http://", "https://", "//", "mailto:", "data:", "javascript:")):
                continue
            target = ref.split("#", 1)[0].split("?", 1)[0]
            if not target:
                continue
            resolved = os.path.normpath(os.path.join(base_dir, urllib.parse.unquote(target)))
            if os.path.isdir(resolved) or (not os.path.exists(resolved) and
                                           not os.path.exists(resolved + ".html") and
                                           not os.path.exists(os.path.join(resolved, "index.html"))):
                fail("%s -> 断链 %s" % (page, ref))
            else:
                assets += 1

        # 锚点：href="#id" 必须能在本页找到 id
        ids = set(re.findall(r'id="([^"]+)"', text))
        for m in re.finditer(r'href="#([^"]+)"', text):
            anchor = urllib.parse.unquote(m.group(1))
            if anchor not in ids:
                fail("%s -> 断锚点 #%s" % (page, anchor))

    ok("%d 个页面、%d 个相对引用全部可解析；%d 个外部依赖" % (len(pages), assets, external))


def check_rendering() -> None:
    print("\n[2] Markdown 渲染质量")

    def strip_code(text: str) -> str:
        """去掉代码块与行内代码的内容，避免把代码里的 ** 误判成未渲染的标记。
        用 <br> 占位，保留行结构（行首标记类检查依赖换行）。"""
        text = re.sub(r"(?s)<pre><code.*?</code></pre>", " <br> ", text)
        text = re.sub(r"(?s)<code>.*?</code>", " ", text)
        text = re.sub(r"(?s)<li>", "\n<li>", text)
        text = text.replace("<br>", "\n").replace("</li>", "\n</li>")
        return text

    raw_markers = [
        (re.compile(r"^\s*#{1,6}\s+\S", re.M), "行首还有 # 标题标记"),
        (re.compile(r"^\s*```", re.M), "还有未处理的 ``` 围栏"),
        (re.compile(r"^\s*\|.*\|\s*$", re.M), "还有未渲染的表格行"),
        (re.compile(r"\[[^\]\n]+\]\([^)\n]+\)"), "还有未渲染的链接"),
        (re.compile(r"^\s*&gt;\s", re.M), "还有未渲染的引用块"),
        (re.compile(r"\*\*[^*\n]+\*\*"), "还有未渲染的粗体"),
    ]
    for page in html_files():
        with open(os.path.join(DIST, *page.split("/")), "r", encoding="utf-8") as fh:
            text = strip_code(fh.read())
        for rx, label in raw_markers:
            hits = rx.findall(text)
            if hits:
                fail("%s: %s（%d 处，例：%r）" % (page, label, len(hits), hits[0][:70]))

    # 关键页面必须有的结构
    expect = {
        "docs/derma_basic_guide.html": ['<table', '<pre><code', 'class="codeblock"',
                                        'id="5-皮肤skin系统"',
                                        '<img src="../assets/img/derma/test-panel-empty.png"',
                                        '<img src="../assets/img/derma/test-panel-example.png"'],
        "docs/gmod_lua_port_plan.html": ['<table', 'class="codeblock"',
                                         'id="9-移植状态与经验v3-增补2026-09-12-09-13"',
                                         'id="9-移植状态与经验v3-增补2026-09-12--09-13"'],
        "docs/build_and_run.html": ['<table', '<pre><code', 'waf.bat'],
        "docs/gmod_compat_layer.html": ['<table', 'lua/autorun/client'],
        "index.html": ['class="hero"', 'docs/derma_basic_guide.html', '<table'],
        "docs/index.html": ['class="toc"', 'gmod_lua_port_plan.html'],
    }
    for page, needles in expect.items():
        rel = page[5:] if page.startswith("dist/") else page
        path = os.path.join(DIST, *rel.split("/"))
        if not os.path.exists(path):
            fail("缺少页面 %s" % rel)
            continue
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        for needle in needles:
            if needle not in text:
                fail("%s 缺少 %r" % (rel, needle))
    ok("渲染检查完成（表格 / 代码块 / 标题锚点 / 首页结构）")


def check_self_contained() -> None:
    print("\n[3] 自包含性")
    total = 0
    for base, _dirs, files in os.walk(DIST):
        for name in files:
            total += os.path.getsize(os.path.join(base, name))
    ok("dist/ 总大小 %.1f KB" % (total / 1024.0))
    for page in html_files():
        with open(os.path.join(DIST, *page.split("/")), "r", encoding="utf-8") as fh:
            text = fh.read()
        if "fonts.googleapis" in text or "cdn." in text:
            fail("%s 使用了 CDN" % page)
    ok("无 CDN / 无外部字体引用")


def check_images() -> None:
    print("\n[4] 图片 / screenshots")
    img_root = os.path.join(DIST, "assets", "img")
    if not os.path.isdir(img_root):
        warn("dist/assets/img 不存在（Markdown 里还没有截图引用）")
        return

    # dist/ 里所有 PNG（含魔数校验）
    pngs = []
    for base, _dirs, files in os.walk(img_root):
        for name in files:
            if not name.lower().endswith(".png"):
                continue
            p = os.path.join(base, name)
            rel = os.path.relpath(p, DIST).replace("\\", "/")
            pngs.append(rel)
            with open(p, "rb") as fh:
                magic = fh.read(8)
            if magic != b"\x89PNG\r\n\x1a\n":
                fail("%s 不是合法 PNG（魔数 %r）" % (rel, magic))
    pngs.sort()
    if not pngs:
        warn("dist/assets/img 下没有 PNG")
        return

    # 每个 <img>：相对路径、能解析到文件、有 alt 文本
    seen: dict[str, list[str]] = {}
    for page in html_files():
        with open(os.path.join(DIST, *page.split("/")), "r", encoding="utf-8") as fh:
            text = fh.read()
        base_dir = os.path.dirname(os.path.join(DIST, *page.split("/")))
        refs = re.findall(r'<img\b([^>]*)>', text)
        seen[page] = []
        for attrs in refs:
            sm = re.search(r'src="([^"]+)"', attrs)
            am = re.search(r'alt="([^"]*)"', attrs)
            if not sm:
                fail("%s 有 <img> 没有 src" % page)
                continue
            src = _html.unescape(sm.group(1))
            seen[page].append(src)
            if src.startswith(("http://", "https://", "//")):
                fail("%s 的图片是外链: %s" % (page, src))
                continue
            resolved = os.path.normpath(os.path.join(base_dir, urllib.parse.unquote(src)))
            if not os.path.isfile(resolved):
                fail("%s -> 图片缺失 %s" % (page, src))
            if not am or not _html.unescape(am.group(1)).strip():
                fail("%s 的图片缺少 alt 文本: %s" % (page, src))

    # 指南里的两张截图：顺序必须是「先空窗、后完整」
    guide = seen.get("docs/derma_basic_guide.html", [])
    want = ["../assets/img/derma/test-panel-empty.png",
            "../assets/img/derma/test-panel-example.png"]
    if guide != want:
        fail("docs/derma_basic_guide.html 的图片应为 %s，实际 %s" % (want, guide))
    else:
        ok("指南里的两张截图顺序正确（空窗 -> 完整），相对路径 ../assets/img/... 解析成功")
    ok("%d 张 PNG（%d KB）全部是合法 PNG，%d 个页面的 <img> 引用可解析"
       % (len(pngs), sum(os.path.getsize(os.path.join(DIST, *p.split("/")))
                         for p in pngs) // 1024, len(seen)))


# ---------------------------------------------------------------- HTTP 检查
class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_a):  # noqa: D102
        pass


def check_http() -> None:
    print("\n[5] 本地 HTTP 服务（相对路径 / 任意 base path）")
    handler = functools.partial(_Quiet, directory=DIST)
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as httpd:
        port = httpd.server_address[1]
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        try:
            pages = html_files() + ["assets/style.css", "assets/app.js",
                                    "assets/search-index.json", ".nojekyll"]
            # 截图（PNG）也要能 200 拿到 —— 直接按页面里的相对引用反推 URL
            for base, _dirs, files in os.walk(os.path.join(DIST, "assets", "img")):
                for name in files:
                    rel = os.path.relpath(os.path.join(base, name), DIST)
                    pages.append(rel.replace("\\", "/"))
            for page in pages:
                url = "http://127.0.0.1:%d/%s" % (port, urllib.parse.quote(page))
                try:
                    with urllib.request.urlopen(url, timeout=10) as resp:
                        if resp.status != 200:
                            fail("%s -> HTTP %s" % (page, resp.status))
                        else:
                            resp.read()
                except urllib.error.HTTPError as exc:
                    fail("%s -> HTTP %s" % (page, exc.code))
                except Exception as exc:  # noqa: BLE001
                    fail("%s -> %s" % (page, exc))
            ok("%d 个 URL 全部 HTTP 200" % len(pages))
        finally:
            httpd.shutdown()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-http", action="store_true")
    args = ap.parse_args()

    if not os.path.isdir(DIST):
        print("dist/ 不存在，先运行: python tools/build.py")
        return 2

    print("HL2SB 站点自检 / verify  (dist=%s)" % DIST)
    check_files_exist()
    check_rendering()
    check_self_contained()
    check_images()
    if not args.no_http:
        check_http()

    print("\n结果: %d 项通过, %d 个警告, %d 个失败" % (OK, len(WARN), len(FAIL)))
    for w in WARN:
        print("  warn: %s" % w)
    for f in FAIL:
        print("  FAIL: %s" % f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    raise SystemExit(main())
