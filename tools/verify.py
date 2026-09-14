#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""站点自检 / site verifier.

检查 dist/：
  1. 每个 HTML 页面都能在本地 HTTP server 上打开（HTTP 200）；
  2. 站内链接与静态资源都存在（相对路径，任意 base path 可用）；
  3. 没有任何外部依赖（<link>/<script>/<img>/@import/字体）；
  4. Markdown 渲染是否干净：表格、代码块、标题、标题 id、以及是否残留原始标记；
  5. 截图（assets/img/*.png）：合法 PNG、尺寸已经裁到示例窗口的尺度、有 alt 文本、
     相对引用能解析、指南里顺序正确；
  6. Lua 语法高亮：```lua 围栏必须是构建期就写好的 <span class="tok-*">，
     非 Lua 的围栏必须完全不高亮（负向对照）；
  7. 本地 HTTP：页面 + 截图全部 HTTP 200。

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

    # dist/ 里所有 PNG（含魔数校验 + 从 IHDR 读尺寸，不依赖任何第三方库）
    pngs = []
    for base, _dirs, files in os.walk(img_root):
        for name in files:
            if not name.lower().endswith(".png"):
                continue
            p = os.path.join(base, name)
            rel = os.path.relpath(p, DIST).replace("\\", "/")
            pngs.append(rel)
            with open(p, "rb") as fh:
                blob = fh.read(33)
            if blob[:8] != b"\x89PNG\r\n\x1a\n":
                fail("%s 不是合法 PNG（魔数 %r）" % (rel, blob[:8]))
                continue
            if blob[12:16] != b"IHDR":
                fail("%s 的 PNG 没有 IHDR（前 33 字节异常）" % rel)
                continue
            w = int.from_bytes(blob[16:20], "big")
            h = int.from_bytes(blob[20:24], "big")
            size = os.path.getsize(p)
            print("  ok    %s  %dx%d  %.1f KB" % (rel, w, h, size / 1024.0))
            # 示例截图必须是「裁到窗口」的尺度：整屏 1920x1280 那种 2.7 MB 的原图
            # 会喧宾夺主，这里直接把上限写死，避免以后再退回去。
            if rel.startswith("assets/img/derma/"):
                if w > 800 or h > 500:
                    fail("%s 尺寸 %dx%d 太大 —— 应该裁到示例窗口（上限 800x500）"
                         % (rel, w, h))
                if size > 200 * 1024:
                    fail("%s 有 %.1f KB —— 裁切后应该远小于 200 KB"
                         % (rel, size / 1024.0))
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


# ---------------------------------------------------------------- Lua 高亮
CODEBLOCK_RE = re.compile(r"(?s)<pre><code([^>]*)>(.*?)</code></pre>")
TOKEN_RE = re.compile(r'<span class="(tok-[a-z]+)"')
LUA_LANGS = ("language-lua", "language-glua", "language-luau")


def check_highlighting() -> None:
    """```lua 围栏必须在构建期就被切成 <span class="tok-*">（运行时零依赖），
    同时用负向对照确认别的语言的围栏没有被误判成 Lua。"""
    print("\n[5] Lua 语法高亮（构建期 / 负向对照）")

    lua_blocks = 0
    other_blocks = 0
    used_classes: set[str] = set()
    per_page: dict[str, int] = {}

    for page in html_files():
        with open(os.path.join(DIST, *page.split("/")), "r", encoding="utf-8") as fh:
            text = fh.read()
        for attrs, body in CODEBLOCK_RE.findall(text):
            classes = set(TOKEN_RE.findall(body))
            is_lua = any(lang in attrs for lang in LUA_LANGS)
            if is_lua:
                lua_blocks += 1
                per_page[page] = per_page.get(page, 0) + 1
                used_classes |= classes
                if not classes:
                    fail("%s: 有一个 Lua 代码块完全没有高亮标记（%r…）"
                         % (page, body[:60]))
                elif "tok-keyword" not in classes:
                    warn("%s: Lua 代码块里没有 tok-keyword（可能整段都是注释）" % page)
            else:
                other_blocks += 1
                # 负向对照：非 Lua 围栏（powershell / 无语言的控制台片段 / 目录树）
                # 一个 tok-* 都不该有。
                if classes:
                    fail("%s: 非 Lua 的代码块被误高亮成 %s（%r…）"
                         % (page, sorted(classes), body[:60]))

    if lua_blocks == 0:
        fail("整整 7 个页面里没有一个被高亮的 Lua 代码块")
    else:
        ok("%d 个 Lua 代码块全部带 <span class=\"tok-*\">（%s）"
           % (lua_blocks, "、".join("%s×%d" % kv for kv in sorted(per_page.items()))))

    # 调色板确实用上了：关键字 / 字符串 / 注释 / 数字 / 运算符 / 方法名 / 类名
    expect = {"tok-keyword", "tok-string", "tok-comment", "tok-number",
              "tok-op", "tok-method", "tok-class"}
    missing = sorted(expect - used_classes)
    if missing:
        warn("高亮调色板里这些类别没出现：%s" % ", ".join(missing))
    else:
        ok("关键字 / 字符串 / 注释 / 数字 / 运算符 / 方法 / 类名 7 类标记都出现了")

    # 指南是唯一有 lua 围栏的页面：6 段（含 §2 列表项里缩进的那一段）
    guide_lua = per_page.get("docs/derma_basic_guide.html", 0)
    if guide_lua < 6:
        fail("docs/derma_basic_guide.html 只有 %d 个高亮的 Lua 代码块，应该有 6 个"
             % guide_lua)
    else:
        ok("指南里的 6 段 ```lua（含 §2 列表项里那段）全部高亮")

    if other_blocks == 0:
        warn("没有任何非 Lua 代码块，负向对照没有实际生效")

    # 样式与脚本：颜色对齐 GMod wiki，放大层是本站自己实现的
    css_path = os.path.join(DIST, "assets", "style.css")
    js_path = os.path.join(DIST, "assets", "app.js")
    with open(css_path, "r", encoding="utf-8") as fh:
        css = fh.read()
    with open(js_path, "r", encoding="utf-8") as fh:
        js = fh.read()
    for needle in ("tok-keyword", "#03a9f4", "#ecce39", "#4caf50", "#81d0da",
                   "#7cd7e0", "#7bd6ff", "#9c9c9c", ".lightbox"):
        if needle not in css:
            fail("assets/style.css 缺少 %r" % needle)
    for needle in ("lightbox", "openLightbox", "closeLightbox", 'querySelector("pre code")',
                   "innerText"):
        if needle not in js:
            fail("assets/app.js 缺少 %r" % needle)
    # 复制按钮必须从 DOM 取纯文本（innerText），否则会把 tok-* 的 <span> 一起复制走
    if "innerText" in js and ".innerHTML" not in js.split("代码块复制")[-1][:600]:
        ok("「复制」按钮取的是纯文本（innerText），高亮标记不会被复制")
    if "lightbox" in js and ".lightbox" in css:
        ok("点击放大由 assets/app.js + style.css 自带（无第三方库）")

    # 关键页面必须有的结构（和 [2] 里的 expect 互补：这里只管高亮）
    with open(os.path.join(DIST, "docs", "derma_basic_guide.html"),
              "r", encoding="utf-8") as fh:
        guide = fh.read()
    if 'class="language-lua"' not in guide:
        fail("docs/derma_basic_guide.html 里没有 language-lua 代码块")
    if "<copy" in guide or "prism" in guide.lower() or "highlight.js" in guide.lower():
        fail("页面里出现了外部高亮方案（应该完全用构建期生成）")
    ok("没有引入任何运行时高亮库 / 外部脚本")


# ---------------------------------------------------------------- HTTP 检查
class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_a):  # noqa: D102
        pass


def check_http() -> None:
    print("\n[6] 本地 HTTP 服务（相对路径 / 任意 base path）")
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
    check_highlighting()
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
