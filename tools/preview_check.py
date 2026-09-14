#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""真实预览检查：模拟 GitHub Pages 把站点挂在子路径下的行为。

GitHub Pages 的用户站会挂在 /<repo>/ 这样的子路径下，所以这里起一个
「把 dist/ 当作 /hl2sb.github.io/ 子目录」的本地服务器，按真实 URL 抓页面，
检查 HTTP 200、内容、侧栏/搜索面板结构、首页出去的相对链接，以及文档里的
截图（`../assets/img/*.png` 必须在子路径下 200、真的是 PNG、而且尺寸已经裁到
示例窗口的尺度），还有构建期写入的 Lua 高亮标记（`<span class="tok-*">`）。

用法:
    python tools/preview_check.py
"""

from __future__ import annotations

import functools
import http.server
import json
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
PREFIX = "/hl2sb.github.io"   # 模拟 https://<user>.github.io/<repo>/


class Handler(http.server.SimpleHTTPRequestHandler):
    """把 /<PREFIX>/... 映射到 dist/... 的静态服务器。"""

    def __init__(self, *args, **kwargs):
        kwargs["directory"] = DIST
        super().__init__(*args, **kwargs)

    def translate_path(self, path: str) -> str:
        parsed = urllib.parse.urlparse(path).path
        if parsed.startswith(PREFIX):
            parsed = parsed[len(PREFIX):] or "/"
        else:
            parsed = "/"
        return super().translate_path(parsed)

    def log_message(self, *_a):
        pass


# (路径, 说明, 必须出现的内容)
CHECKS = [
    ("/", "首页", ["class=\"hero\"", "docs/derma_basic_guide.html", "assets/style.css"]),
    ("/index.html", "首页", ["HL2SB 文档站", "class=\"hero\"", "id=\"searchOverlay\""]),
    ("/docs/index.html", "Wiki 目录", ["derma_basic_guide.html", "gmod_lua_port_plan.html"]),
    ("/docs/derma_basic_guide.html", "Derma 基础指南",
     ["<table", "<pre><code", "DFrame:GetClientArea",
      "id=\"0-运行环境和-gmod-不一样的第一件事\"", "class=\"codeblock\"",
      "src=\"../assets/img/derma/test-panel-empty.png\"",
      "src=\"../assets/img/derma/test-panel-example.png\"",
      # 构建期写入的 Lua 高亮：关键字 / 字符串 / 注释 / 方法名
      "class=\"language-lua\"", "class=\"tok-keyword\"", "class=\"tok-string\"",
      "class=\"tok-comment\"", "class=\"tok-method\"", "class=\"tok-number\"",
      "class=\"tok-op\""]),
    ("/docs/gmod_lua_port_plan.html", "移植计划与状态", ["<table", "class=\"codeblock\""]),
    ("/docs/gmod_compat_layer.html", "兼容层", ["<table", "lua/includes/extensions"]),
    ("/docs/file_find.html", "file.Find 参考",
     ["<table", "class=\"language-lua\"", "class=\"tok-keyword\"",
      "class=\"tok-method\"", "file_Find", "wiki.facepunch.com/gmod/file.Find",
      "gmod_compat_layer.html", "derma_basic_guide.html"]),
    ("/docs/build_and_run.html", "构建与运行",
     ["waf.bat", "build\\game\\client\\client.dll", "class=\"toc\"", "lua/autorun"]),
    ("/docs/about.html", "关于 / 版权", ["Facepunch", "stephen-cusi/source-engine-mod"]),
    ("/assets/style.css", "样式表",
     ["--accent", "#0082ff", "#383c3e", "#90beef",
      # Lua token 颜色（逐条对齐上游 GMod wiki 的 styles/gmod.css）
      ".tok-keyword", "#03a9f4", ".tok-string", "#ecce39", ".tok-comment",
      "#4caf50", ".tok-method", "#7cd7e0", ".tok-class", "#81d0da",
      # 截图呈现 + 无依赖放大层
      "max-width: min(100%, 640px)", ".lightbox", "zoom-in"]),
    ("/assets/app.js", "脚本",
     ["search-index.json", "hl2sb-theme", "openLightbox", "closeLightbox",
      "innerText", "querySelectorAll(\".doc img, .prose img\")"]),
    ("/assets/search-index.json", "搜索索引", ["derma_basic_guide.html", "headings"]),
    ("/assets/favicon.svg", "图标", ["<svg"]),
    ("/404.html", "404 页面", ["404"]),

    # ---- 英文镜像 /en/（结构、锚点、资源路径都要与中文对齐）----
    ("/en/index.html", "英文首页",
     ["class=\"hero\"", "en/docs/derma_basic_guide.html", "class=\"lang-switch\"",
      "documentation", "id=\"searchOverlay\""]),
    ("/en/docs/index.html", "Wiki index (EN)",
     ["derma_basic_guide.html", "gmod_lua_port_plan.html", "class=\"toc\""]),
    ("/en/docs/derma_basic_guide.html", "Derma basics (EN)",
     ["<table", "<pre><code", "class=\"codeblock\"",
      # 英文页深一层：图片必须是 ../../assets/...
      "src=\"../../assets/img/derma/test-panel-empty.png\"",
      "src=\"../../assets/img/derma/test-panel-example.png\"",
      # 锚点与中文页逐字相同（深链跨语言通用）
      "id=\"0-运行环境和-gmod-不一样的第一件事\"", "id=\"5-皮肤skin系统\"",
      "class=\"language-lua\"", "class=\"tok-keyword\""]),
    ("/en/docs/file_find.html", "file.Find (EN)",
     ["<table", "class=\"language-lua\"", "class=\"tok-keyword\"", "file_Find",
      "wiki.facepunch.com/gmod/file.Find", "id=\"4-pathid-支持情况\""]),
    ("/en/docs/gmod_lua_port_plan.html", "port plan (EN)",
     ["<table", "class=\"codeblock\"", "id=\"9-移植状态与经验v3-增补2026-09-12-09-13\""]),
    ("/en/docs/gmod_compat_layer.html", "compat layer (EN)",
     ["<table", "lua/includes/extensions"]),
    ("/en/docs/build_and_run.html", "build & run (EN)",
     ["waf.bat", "class=\"toc\"", "lua/autorun"]),
    ("/en/docs/about.html", "about (EN)", ["Facepunch", "stephen-cusi/source-engine-mod"]),
    ("/en/404.html", "404 (EN)", ["404"]),
    ("/assets/search-index.en.json", "英文搜索索引",
     ["gmod_lua_port_plan.html", "headings"]),
    ("/assets/app.js", "脚本（双语）",
     ["data-index", "data-copied", "data-none", "data-lb-close"]),
]

# 公共结构在这些页面上都要有（中英各挑几页）
STRUCT_PAGES = ["/", "/docs/file_find.html", "/en/index.html", "/en/docs/file_find.html",
                "/docs/build_and_run.html", "/docs/about.html"]

STRUCT = ["id=\"searchOverlay\"", "class=\"side-nav\"", "theme-toggle",
          "class=\"lang-switch\"", "assets/style.css", "assets/app.js", "id=\"sideSearch\""]


failures: list[str] = []


def get(url: str) -> tuple[int, str]:
    with urllib.request.urlopen(url, timeout=15) as resp:
        return resp.status, resp.read().decode("utf-8", "replace")


def get_bytes(url: str) -> tuple[int, bytes]:
    with urllib.request.urlopen(url, timeout=15) as resp:
        return resp.status, resp.read()


PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def png_size(blob: bytes) -> tuple[int, int]:
    """从 IHDR 读尺寸（不依赖任何第三方库）。"""
    if len(blob) < 24 or blob[12:16] != b"IHDR":
        return (0, 0)
    return (int.from_bytes(blob[16:20], "big"), int.from_bytes(blob[20:24], "big"))


# ---------------------------------------------------------------- 站内搜索
# app.js 从自己 <script src="$$ROOT$$assets/app.js"> 反推站点根（SITE_ROOT），
# 索引与搜索结果链接都拼它。这里用同一套算法把「浏览器实际会请求的 URL」算出来，
# 在子路径部署下逐条抓一遍 —— 这正是以前坏掉的地方（docs/ 页面去请求
# docs/assets/search-index.json，404 之后 index 变空，搜索什么都搜不到）。
APP_JS_RE = r'<script src="([^"]*assets/app\.js)"'


def page_root(html: str) -> str:
    """页面自己的站点根前缀（"" 或 "../"），与 app.js 的 SITE_ROOT 一致。"""
    m = re.search(APP_JS_RE, html)
    if not m:
        return ""
    return m.group(1)[: m.group(1).index("assets/app.js")]


def js_score(entry: dict, terms: list[str], q: str) -> int:
    """app.js 里 score() 的等价实现（用来验证「确实搜得到东西」）。"""
    s = 0
    title = (entry.get("title") or "").lower()
    heads = " ".join(entry.get("headings") or []).lower()
    text = (entry.get("text") or "").lower()
    if q in title:
        s += 100
    for t in terms:
        if t in title:
            s += 40
        if t in heads:
            s += 12
        s += min(text.count(t), 12) * 2
    return s


def js_search(index: list[dict], query: str) -> list[str]:
    q = query.strip().lower()
    terms = [t for t in q.split() if t]
    found = []
    for entry in index:
        sc = js_score(entry, terms, q)
        if sc > 0:
            found.append((sc, entry))
    found.sort(key=lambda kv: -kv[0])
    return [e.get("url", "") for _s, e in found]


def main() -> int:
    if not os.path.isdir(DIST):
        print("dist/ 不存在，先运行 python tools/build.py")
        return 2

    handler = functools.partial(Handler)
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as httpd:
        port = httpd.server_address[1]
        root = "http://127.0.0.1:%d" % port
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        print("本地预览（模拟 Pages 子路径）: %s%s/\n" % (root, PREFIX))
        try:
            for path, label, needles in CHECKS:
                url = root + PREFIX + path
                try:
                    status, body = get(url)
                except urllib.error.HTTPError as exc:
                    failures.append("%s -> HTTP %s" % (path, exc.code))
                    print("  FAIL  %-34s HTTP %s" % (path, exc.code))
                    continue
                except Exception as exc:  # noqa: BLE001
                    failures.append("%s -> %s" % (path, exc))
                    print("  FAIL  %-34s %s" % (path, exc))
                    continue
                missing = [n for n in needles if n not in body]
                if missing:
                    failures.append("%s 缺少 %r" % (path, missing))
                    print("  FAIL  %-34s HTTP %s 缺少 %s" % (path, status, missing))
                else:
                    print("  ok    %-34s HTTP %s  %7d B  %s"
                          % (path, status, len(body.encode("utf-8")), label))

            # 截图：指南页 HTML 里的 <img src> 必须是相对本页的路径
            # （../assets/img/...），并且在 /<repo>/ 子路径部署下真能 200 拿到 PNG。
            _status, guide = get(root + PREFIX + "/docs/derma_basic_guide.html")
            imgs = re.findall(r'<img\s+src="([^"]+)"\s+alt="([^"]*)"', guide)
            if not imgs:
                failures.append("指南页没有任何 <img>")
                print("  FAIL  %-34s 没有任何 <img>" % "/docs/derma_basic_guide.html")
            for src, alt in imgs:
                if src.startswith(("http://", "https://", "/")):
                    failures.append("指南页图片不是相对路径: %s" % src)
                    print("  FAIL  %-34s 图片路径必须相对: %s" % ("(图片)", src))
                    continue
                # 页面的目录是 /<repo>/docs/，相对引用就从这里解析
                resolved = os.path.normpath(os.path.join(
                    PREFIX + "/docs", urllib.parse.unquote(src))).replace("\\", "/")
                url = root + resolved
                try:
                    status, blob = get_bytes(url)
                except Exception as exc:  # noqa: BLE001
                    failures.append("图片 %s -> %s" % (src, exc))
                    print("  FAIL  图片 %-32s %s" % (src, exc))
                    continue
                if status != 200 or not blob.startswith(PNG_MAGIC):
                    failures.append("图片 %s -> HTTP %s / PNG=%s" % (src, status, blob[:8]))
                    print("  FAIL  图片 %-32s HTTP %s 不是 PNG" % (src, status))
                else:
                    w, h = png_size(blob)
                    print("  ok    %-34s HTTP %s  %7d B  %dx%d  %s"
                          % (resolved, status, len(blob), w, h, alt[:24]))
                    # 示例截图必须是「裁到窗口」的尺度，不是整屏实拍
                    if w > 800 or h > 500:
                        failures.append("图片 %s 尺寸 %dx%d 太大（应该裁到示例窗口）"
                                        % (src, w, h))
                        print("  FAIL  图片 %-32s %dx%d 太大" % (src, w, h))

            # 每个页面的公共结构（侧栏 / 搜索 / 主题 / 语言切换 / 资源引用），中英都查
            for path in STRUCT_PAGES:
                _status, body = get(root + PREFIX + path)
                for needle in STRUCT:
                    if needle not in body:
                        failures.append("%s 缺少 %r" % (path, needle))
                        print("  FAIL  %-34s 缺少 %s" % (path, needle))
            print("  ok    %-34s 侧栏 / 搜索面板 / 主题 / 语言切换 / 资源引用齐全（中英）"
                  % "(公共结构)")

            # 语言切换器：中文页 -> 英文页 -> 必须能切回来（旗帜按钮就是这两条链接）
            for from_path, to_hreflang in (("/docs/file_find.html", "en"),
                                           ("/en/docs/file_find.html", "zh-CN")):
                _st, body = get(root + PREFIX + from_path)
                m = re.search(r'<a class="lang-switch" href="([^"]+)" hreflang="([^"]+)"', body)
                if not m:
                    failures.append("%s 没有语言切换器" % from_path)
                    print("  FAIL  %-34s 没有语言切换器" % from_path)
                    continue
                href, hreflang = m.group(1), m.group(2)
                page_dir = os.path.dirname(PREFIX + from_path)
                target = os.path.normpath(
                    os.path.join(page_dir, urllib.parse.unquote(href))).replace("\\", "/")
                try:
                    status, back = get(root + target)
                except Exception as exc:  # noqa: BLE001
                    failures.append("%s 的语言切换器 -> %s（%s）" % (from_path, href, exc))
                    print("  FAIL  %-34s 语言切换器 -> %s" % (from_path, exc))
                    continue
                want_back = os.path.relpath(PREFIX + from_path, os.path.dirname(target)).replace("\\", "/")
                if status != 200 or hreflang != to_hreflang or 'href="%s"' % want_back not in back:
                    failures.append("%s -> %s 切换失败（HTTP %s / hreflang %s / 回链 %s）"
                                    % (from_path, href, status, hreflang, want_back))
                    print("  FAIL  %-34s 语言切换器 -> %s HTTP %s" % (from_path, href, status))
                else:
                    print("  ok    %-34s 语言切换器 -> %s HTTP 200（hreflang=%s，可切回）"
                          % (from_path, href, hreflang))

            # 跨页锚点：目录页里指向别页的 #锚点 必须在目标页真的存在
            # （2026-09 中文页里真的断了两处，英文版照抄也一起断 —— 现在静态 + 动态都查）
            for index_path in ("/docs/index.html", "/en/docs/index.html"):
                _st, body = get(root + PREFIX + index_path)
                page_dir = os.path.dirname(PREFIX + index_path)
                checked = 0
                for ref, anchor in re.findall(r'href="([^"#]+\.html)#([^"]+)"', body):
                    target = os.path.normpath(
                        os.path.join(page_dir, urllib.parse.unquote(ref))).replace("\\", "/")
                    try:
                        st, target_html = get(root + target)
                    except Exception:  # noqa: BLE001
                        st = 0
                    if st != 200 or 'id="%s"' % urllib.parse.unquote(anchor) not in target_html:
                        failures.append("%s -> %s#%s 锚点不存在（HTTP %s）"
                                        % (index_path, ref, anchor, st))
                        print("  FAIL  %-34s 锚点 %s#%s 不存在" % (index_path, ref, anchor))
                    else:
                        checked += 1
                print("  ok    %-34s %d 个跨页锚点全部命中" % (index_path, checked))

            # 站内搜索：按每个页面自己声明的 data-index 抓索引（中英各一份），
            # 逐条抓结果链接，再跑 score() 的等价实现确认「确实搜得到东西」。
            # 以前索引是页面相对的，docs/ 页面拿到 404，于是搜索永远回「没有匹配的页面」。
            indexes = {}
            for label, page_path, page_dir in (("/index.html", "/index.html", "/"),
                                               ("/docs/file_find.html", "/docs/file_find.html", "/docs/"),
                                               ("/en/index.html", "/en/index.html", "/en/"),
                                               ("/en/docs/file_find.html", "/en/docs/file_find.html", "/en/docs/")):
                _st, page_html = get(root + PREFIX + page_path)
                mi = re.search(r'id="searchOverlay"[^>]*data-index="([^"]+)"', page_html, re.S)
                if not mi:
                    failures.append("%s 的搜索面板没有 data-index" % label)
                    print("  FAIL  %-34s 搜索面板没有 data-index" % label)
                    continue
                idx_url = os.path.normpath(
                    os.path.join(PREFIX + page_dir, urllib.parse.unquote(mi.group(1)))).replace("\\", "/")
                try:
                    status, body = get(root + idx_url)
                    parsed = json.loads(body)
                except Exception as exc:  # noqa: BLE001
                    failures.append("%s 加载索引失败（%s -> %s）" % (label, idx_url, exc))
                    print("  FAIL  %-34s 索引 %s -> %s" % (label, idx_url, exc))
                    continue
                if status != 200 or not parsed:
                    failures.append("%s 的索引 %s -> HTTP %s / %d 条"
                                    % (label, idx_url, status, len(parsed or [])))
                    print("  FAIL  %-34s 索引 %s HTTP %s" % (label, idx_url, status))
                    continue
                indexes[label] = parsed
                print("  ok    %-34s 索引 HTTP 200  %d 条  %s"
                      % (label, len(parsed), idx_url))

                r = page_root(page_html)
                broken = []
                for entry in parsed:
                    target = os.path.normpath(
                        os.path.join(PREFIX + page_dir, r + entry.get("url", ""))).replace("\\", "/")
                    try:
                        st, _b = get(root + target)
                    except Exception:  # noqa: BLE001
                        st = 0
                    if st != 200:
                        broken.append("%s -> %s" % (entry.get("url"), st))
                if broken:
                    failures.append("%s 上 %d 条搜索结果打不开（例：%s）"
                                    % (label, len(broken), broken[0]))
                    print("  FAIL  %-34s %d 条结果链接打不开（例：%s）"
                          % (label, len(broken), broken[0]))
                else:
                    print("  ok    %-34s %d 条搜索结果链接全部 HTTP 200"
                          % (label, len(parsed)))

            # 召回：中英各测一组。file.Find 是本页；hook.call 只出现在移植计划页的深处
            # （中文 12808 字符处、英文更靠后）—— 正文上限还是 6000 的时候这些必挂，
            # 等于给「长页面搜不到」上的回归锁。
            for label, want_hits in (
                    ("/index.html", [("file.Find", "docs/file_find.html"),
                                     ("hook.call", "docs/gmod_lua_port_plan.html")]),
                    ("/en/index.html", [("file.Find", "en/docs/file_find.html"),
                                        ("hook.call", "en/docs/gmod_lua_port_plan.html")])):
                index = indexes.get(label)
                if not index:
                    continue
                for query, want in want_hits:
                    hits = js_search(index, query)
                    if want in hits:
                        print("  ok    %-34s 搜索 %-14s 命中 %d 条，含 %s"
                              % ("(搜索召回 " + label + ")", repr(query), len(hits), want))
                    else:
                        failures.append("搜索 %r 找不到 %s（命中 %s）" % (query, want, hits[:3]))
                        print("  FAIL  %-34s 搜索 %r 找不到 %s（命中 %s）"
                              % ("(搜索召回)", query, want, hits[:3]))
                if js_search(index, "zzz-no-such-term-zzz"):
                    failures.append("搜索负向对照失败：乱词也命中了页面（%s）" % label)
                    print("  FAIL  %-34s 乱词居然也命中" % "(搜索召回)")
                else:
                    print("  ok    %-34s 负向对照：乱词 0 命中" % "(搜索召回)")

            # 两个首页出去的每一条站内链接都要能打开（中英各爬一遍）
            for home_path in ("/", "/en/index.html"):
                _status, home = get(root + PREFIX + home_path)
                home_dir = os.path.dirname(PREFIX + home_path)
                links = sorted(set(re.findall(r'href="((?!http|#|mailto)[^"]+)"', home)))
                bad = 0
                for link in links:
                    if link.endswith(".css") or link.endswith(".js") or link.endswith(".svg"):
                        continue
                    target = os.path.normpath(
                        os.path.join(home_dir, urllib.parse.unquote(link))).replace("\\", "/")
                    try:
                        status, _body = get(root + target)
                        if status != 200:
                            bad += 1
                            failures.append("%s 链接 %s -> %s" % (home_path, link, status))
                            print("  FAIL  %-14s -> %-26s HTTP %s" % (home_path, link, status))
                    except Exception as exc:  # noqa: BLE001
                        bad += 1
                        failures.append("%s 链接 %s -> %s" % (home_path, link, exc))
                        print("  FAIL  %-14s -> %-26s %s" % (home_path, link, exc))
                if not bad:
                    print("  ok    %-14s 的 %d 条站内链接全部 HTTP 200" % (home_path, len(links)))
        finally:
            httpd.shutdown()

    print("\n结果: %s" % ("全部通过" if not failures else "%d 个失败" % len(failures)))
    for f in failures:
        print("  FAIL: %s" % f)
    return 1 if failures else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    raise SystemExit(main())
