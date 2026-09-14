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
]

STRUCT = ["id=\"searchOverlay\"", "class=\"side-nav\"", "theme-toggle",
          "assets/style.css", "assets/app.js", "id=\"sideSearch\""]


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

            # 每个页面的公共结构（侧栏 / 搜索 / 主题切换 / 资源引用）
            for path in ("/", "/docs/build_and_run.html", "/docs/about.html"):
                _status, body = get(root + PREFIX + path)
                for needle in STRUCT:
                    if needle not in body:
                        failures.append("%s 缺少 %r" % (path, needle))
                        print("  FAIL  %-34s 缺少 %s" % (path, needle))
            print("  ok    %-34s 侧栏 / 搜索面板 / 主题切换 / 资源引用齐全" % "(公共结构)")

            # 首页出去的每一条站内链接都要能打开
            _status, home = get(root + PREFIX + "/")
            links = sorted(set(re.findall(r'href="((?!http|#|mailto)[^"]+)"', home)))
            for link in links:
                if link.endswith(".css") or link.endswith(".js") or link.endswith(".svg"):
                    continue
                url = root + PREFIX + "/" + link.lstrip("/")
                try:
                    status, _body = get(url)
                    if status != 200:
                        failures.append("首页链接 %s -> %s" % (link, status))
                        print("  FAIL  首页 -> %-26s HTTP %s" % (link, status))
                    else:
                        print("  ok    首页 -> %-26s HTTP 200" % link)
                except Exception as exc:  # noqa: BLE001
                    failures.append("首页链接 %s -> %s" % (link, exc))
                    print("  FAIL  首页 -> %-26s %s" % (link, exc))
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
