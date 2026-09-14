#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HL2SB 文档站静态生成器 / static site builder for the HL2SB docs site.

把 docs/ 下的 Markdown 预渲染成静态 HTML，输出到 dist/。
设计要点 / design notes:

* **零外部依赖** —— 不联网、不用 CDN，Markdown 渲染器就在本文件里。
* **任意 base path 可用** —— 所有链接/资源都是相对路径（Python 的 os.path.relpath
  按页面深度算出 ../ 前缀），因此
      https://<user>.github.io/hl2sb.github.io/
      https://hl2sb.github.io/
  两种部署方式都能用。
* **截图约定** —— `docs/*.md` 里写 `![说明](../assets/img/...)`：这条相对路径
  相对生成的 `docs/*.html`（也相对 `docs/` 在 GitHub 上的位置，所以网页和
  GitHub 上都能直接显示），`assets/` 整棵树会被原样复制到 `dist/assets/`。
* **语法高亮也是构建期的** —— ```lua 围栏在这里用一个小 Lua 词法分析器切成
  `<span class="tok-*">`，颜色对齐上游 GMod wiki 的 `styles/gmod.css`。页面加载时
  不跑任何高亮 JS、不拉任何外部脚本，`tools/verify.py` 的「0 external deps」保持成立。

用法 / usage:
    python tools/build.py            # -> dist/
    python tools/build.py --out dist
"""

from __future__ import annotations

import argparse
import html as _html
import json
import os
import re
import shutil
import sys
from datetime import date

# --------------------------------------------------------------------------
# 站点配置 / site configuration
# --------------------------------------------------------------------------

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIR = os.path.join(REPO_ROOT, "docs")
ASSETS_DIR = os.path.join(REPO_ROOT, "assets")

SITE = {
    "name": {
        "zh": "HL2SB 文档",
        "en": "HL2SB Docs",
    },
    "tagline": {
        "zh": "Half-Life 2: Sandbox —— 跑 Garry's Mod Lua 的 Source 引擎分支",
        "en": "Half-Life 2: Sandbox — the Source engine fork that runs Garry's Mod's Lua",
    },
    "repo_engine": "https://github.com/stephen-cusi/source-engine-mod",
    "repo_game": "https://github.com/stephen-cusi/hl2sb-gamefile",
    "repo_site": "https://github.com/stephen-cusi/hl2sb.github.io",
    "pages_url_personal": "https://stephen-cusi.github.io/hl2sb.github.io/",
    "pages_url_org": "https://hl2sb.github.io/",
    "year": date.today().year,
}

# --------------------------------------------------------------------------
# 语言 / languages
# --------------------------------------------------------------------------
# 中文是主语言，页面直接放在站点根目录；英文是**镜像**，放在 /en/ 下，目录结构与中文
# 完全一致（docs/x.html <-> en/docs/x.html）。因此两种语言的相对链接规则一模一样：
#   * 侧栏/目录：root = "../" * 深度
#   * 搜索结果：索引里的 url 一律是「相对 dist 根」的路径，app.js 拼上 SITE_ROOT
#   * 语言切换：两个输出文件之间用 os.path.relpath 算相对路径
# 右上角的旗帜按钮显示的是**目标语言**（在中文页上显示 EN + 英国旗），点一下就切过去。
LANGUAGES = [
    {
        "code": "zh",
        "html_lang": "zh-CN",
        "home": "index.html",                     # 相对 dist 根的首页
        "self_name": "中文",
        "short": "中文",
        "search_index": "assets/search-index.json",
    },
    {
        "code": "en",
        "html_lang": "en",
        "home": "en/index.html",
        "self_name": "English",
        "short": "EN",
        "search_index": "assets/search-index.en.json",
    },
]
LANG_CODES = [l["code"] for l in LANGUAGES]
LANG_BY_CODE = {l["code"]: l for l in LANGUAGES}
HOME_OF = {l["code"]: l["home"] for l in LANGUAGES}
INDEX_OF = {l["code"]: l["search_index"] for l in LANGUAGES}
OTHER_LANG = {"zh": "en", "en": "zh"}

# 界面文案 / UI strings。模板里所有会显示给读者的字都在这里，加语言时只改这里 + PAGES。
UI = {
    "zh": {
        "brand_sub": "文档站",
        "skip": "跳到正文",
        "nav_toggle": "切换导航",
        "search": "搜索",
        "theme": "切换主题",
        "lang_switch_title": "Switch to English",
        "search_dialog": "站内搜索",
        "search_ph": "搜索文档…（标题与正文）",
        "search_idle": "输入关键词开始搜索。",
        "search_loading": "正在加载索引…",
        "search_none": "没有匹配的页面。",
        "search_hint": "↑↓ 选择 · Enter 打开 · Esc 关闭",
        "side_search_ph": "搜索文档…",
        "side_hint": "按 <kbd>/</kbd> 或 <kbd>Ctrl</kbd>+<kbd>K</kbd> 搜索",
        "side_project": "项目",
        "side_home": "首页",
        "side_repo": "GitHub 仓库 ↗",
        "toc": "本页目录",
        "copy": "复制",
        "copied": "已复制",
        "lightbox_close": "放大的截图（点击或按 Esc 关闭）",
        "lightbox_open": "放大截图：",
        "crumb_home": "首页",
        "src_note": "源文件：",
        "src_note_tail": "本页由该 Markdown 预渲染生成，原文是唯一事实来源",
        "generated": "生成于",
        "edit": "在 GitHub 上查看 / 编辑这一页 ↗",
        "footer_p1": "<strong>HL2SB</strong> —— Half-Life 2: Sandbox，基于 Source SDK 2013 / "
                     "nillerusr source-engine 的引擎分支，运行 Garry's Mod 的 Lua。",
        "footer_p2": "引擎源码与 SDK 代码仅供非商业用途；Half-Life、Source、Garry's Mod 及相关"
                     "商标归 Valve / Facepunch 所有。本站文档除特别说明外与上游保持一致。",
        "footer_engine": "引擎仓库",
        "footer_game": "游戏内容仓库",
        "footer_site": "本站源码",
        "footer_about": "关于 / 版权",
        "footer_note": "© $$YEAR$$ HL2SB 贡献者 · 由 <code>tools/build.py</code> 预渲染为静态 "
                       "HTML（无 CDN、无外部依赖）",
        "notfound_title": "页面不存在",
        "notfound_desc": "找不到这个页面",
        "notfound_body": '<div class="prose"><h1>404</h1><p>这个页面不存在。回到 '
                         '<a href="$$HOME$$">首页</a> 或 <a href="$$INDEX$$">文档目录</a>。</p></div>',
    },
    "en": {
        "brand_sub": "Docs",
        "skip": "Skip to content",
        "nav_toggle": "Toggle navigation",
        "search": "Search",
        "theme": "Toggle theme",
        "lang_switch_title": "切换到中文",
        "search_dialog": "Search this site",
        "search_ph": "Search the docs… (titles and body text)",
        "search_idle": "Type a keyword to search.",
        "search_loading": "Loading the index…",
        "search_none": "No matching pages.",
        "search_hint": "↑↓ select · Enter open · Esc close",
        "side_search_ph": "Search the docs…",
        "side_hint": "Press <kbd>/</kbd> or <kbd>Ctrl</kbd>+<kbd>K</kbd> to search",
        "side_project": "Project",
        "side_home": "Home",
        "side_repo": "GitHub repo ↗",
        "toc": "On this page",
        "copy": "Copy",
        "copied": "Copied",
        "lightbox_close": "Enlarged screenshot (click or press Esc to close)",
        "lightbox_open": "Enlarge screenshot: ",
        "crumb_home": "Home",
        "src_note": "Source: ",
        "src_note_tail": "this page is pre-rendered from that Markdown, which stays the single "
                         "source of truth",
        "generated": "generated",
        "edit": "View / edit this page on GitHub ↗",
        "footer_p1": "<strong>HL2SB</strong> — Half-Life 2: Sandbox, an engine fork based on "
                     "Source SDK 2013 / nillerusr source-engine, running Garry's Mod's Lua.",
        "footer_p2": "Engine and SDK source code is for non-commercial use only; Half-Life, Source, "
                     "Garry's Mod and related trademarks belong to Valve / Facepunch. Unless noted "
                     "otherwise these docs match upstream.",
        "footer_engine": "Engine repo",
        "footer_game": "Game content repo",
        "footer_site": "Site source",
        "footer_about": "About / license",
        "footer_note": "© $$YEAR$$ HL2SB contributors · pre-rendered to static HTML by "
                       "<code>tools/build.py</code> (no CDN, no external dependencies)",
        "notfound_title": "Page not found",
        "notfound_desc": "No such page",
        "notfound_body": '<div class="prose"><h1>404</h1><p>No such page. Back to the '
                         '<a href="$$HOME$$">home page</a> or the '
                         '<a href="$$INDEX$$">document index</a>.</p></div>',
    },
}

# 右上角语言切换器里的旗帜：内联 SVG，零外部依赖。
# ⚠️ 不用国旗 emoji（🇨🇳/🇬🇧）—— Windows 浏览器不渲染它们，会退化成 "CN"/"GB" 字母。
_FLAG_STAR = ("M0,-1 L0.224,-0.309 L0.951,-0.309 L0.363,0.118 L0.588,0.809 "
              "L0,0.382 L-0.588,0.809 L-0.363,0.118 L-0.951,-0.309 L-0.224,-0.309 Z")

FLAG_CN = (
    '<svg class="flag" viewBox="0 0 30 20" width="21" height="14" aria-hidden="true" '
    'focusable="false">'
    '<rect width="30" height="20" fill="#de2910"/>'
    '<g fill="#ffde00">'
    '<path transform="translate(6 5) scale(3)" d="%s"/>'
    '<path transform="translate(12 2) scale(1)" d="%s"/>'
    '<path transform="translate(14.6 4.4) scale(1)" d="%s"/>'
    '<path transform="translate(14.6 7.6) scale(1)" d="%s"/>'
    '<path transform="translate(12 10) scale(1)" d="%s"/>'
    "</g></svg>"
) % ((_FLAG_STAR,) * 5)

FLAG_EN = (
    '<svg class="flag" viewBox="0 0 60 30" width="24" height="12" aria-hidden="true" '
    'focusable="false">'
    '<rect width="60" height="30" fill="#012169"/>'
    '<path d="M0,0 L60,30 M60,0 L0,30" stroke="#ffffff" stroke-width="6"/>'
    '<path d="M0,0 L60,30 M60,0 L0,30" stroke="#c8102e" stroke-width="3"/>'
    '<path d="M30,0 L30,30 M0,15 L60,15" stroke="#ffffff" stroke-width="10"/>'
    '<path d="M30,0 L30,30 M0,15 L60,15" stroke="#c8102e" stroke-width="6"/>'
    "</svg>"
)

FLAG_OF = {"zh": FLAG_CN, "en": FLAG_EN}

# 页面底部会写上生成日期（「最后更新」的近似值，CI 每次推送都会重建）。
BUILD_DATE = date.today().isoformat()

# 搜索索引里每页保留的正文长度上限。
# ⚠️ 这里以前写死 6000：36 KB 的「移植计划与状态」页只索引了前 6000 个字符，
# 页面后 83% 的正文**在搜索里根本不存在**（索引文件本身没问题，是内容被截断了）。
# 现在按最长的一页留余量（英文的移植计划页正文约 50 K 字符，是同内容里最长的），
# 真的超了会打印警告，不再悄悄丢内容。
SEARCH_TEXT_LIMIT = 60000

# 页面清单 / page manifest。
#   每个「逻辑页」一条，中英各自的源文件与输出路径都写在同一条里：
#   src  : docs/ 下的 markdown 源文件（单一事实来源），按语言分
#   out  : 生成到 dist/ 的目标路径，按语言分（英文比中文多一层 en/）
#   group: 侧栏分组 id（见 GROUPS）
#   text : 侧栏 / 索引页显示的名字，按语言分
#   desc : 索引页 / <meta description> 的一行说明，按语言分
#   ⚠️ 某种语言缺 src/out 时该语言的这一页会被跳过（切换器会退回对方首页），
#      所以「英文翻好没有」只取决于有没有写 docs/en/<名字>.md。
PAGES = [
    {
        "group": "wiki",
        "src": {"zh": "index.md", "en": "en/index.md"},
        "out": {"zh": "docs/index.html", "en": "en/docs/index.html"},
        "text": {"zh": "Wiki 目录", "en": "Wiki index"},
        "desc": {
            "zh": "本站收录的全部文档一览。",
            "en": "Every document on this site at a glance.",
        },
    },
    {
        "group": "wiki",
        "src": {"zh": "derma_basic_guide.md", "en": "en/derma_basic_guide.md"},
        "out": {"zh": "docs/derma_basic_guide.html", "en": "en/docs/derma_basic_guide.html"},
        "text": {"zh": "Derma 基础指南", "en": "Derma basics"},
        "desc": {
            "zh": "在 HL2SB 里写 GMod 风格 UI；与 GMod 不同的地方、本 fork 的坑。",
            "en": "Writing GMod-style UI in HL2SB: what differs from GMod, and this fork's gotchas.",
        },
    },
    {
        "group": "wiki",
        "src": {"zh": "gmod_lua_port_plan.md", "en": "en/gmod_lua_port_plan.md"},
        "out": {"zh": "docs/gmod_lua_port_plan.html", "en": "en/docs/gmod_lua_port_plan.html"},
        "text": {"zh": "GMod Lua 移植计划与状态", "en": "GMod Lua port plan & status"},
        "desc": {
            "zh": "把 GMod 的 Lua 层搬进引擎的路线图、缺口映射与移植状态总表。",
            "en": "Roadmap, gap-to-engine mapping and status table for porting GMod's Lua layer.",
        },
    },
    {
        "group": "api",
        "src": {"zh": "file_find.md", "en": "en/file_find.md"},
        "out": {"zh": "docs/file_find.html", "en": "en/docs/file_find.html"},
        "text": {"zh": "file.Find", "en": "file.Find"},
        "desc": {
            "zh": "列出文件夹里的文件与目录：签名、pathID 支持情况、与 GMod 的差异（已实现）。",
            "en": "List files and directories in a folder: signature, pathID support, "
                  "differences from GMod (implemented).",
        },
    },
    {
        "group": "guide",
        "src": {"zh": "gmod_compat_layer.md", "en": "en/gmod_compat_layer.md"},
        "out": {"zh": "docs/gmod_compat_layer.html", "en": "en/docs/gmod_compat_layer.html"},
        "text": {"zh": "GMod Lua 兼容层", "en": "GMod Lua compatibility layer"},
        "desc": {
            "zh": "兼容层由哪些部分组成、加载顺序、已知缺口。",
            "en": "What the compatibility layer is made of, its load order, and known gaps.",
        },
    },
    {
        "group": "guide",
        "src": {"zh": "build_and_run.md", "en": "en/build_and_run.md"},
        "out": {"zh": "docs/build_and_run.html", "en": "en/docs/build_and_run.html"},
        "text": {"zh": "构建与运行", "en": "Build & run"},
        "desc": {
            "zh": "编译 client/server、部署 DLL、在哪里改 Lua。",
            "en": "Compile client/server, deploy the DLLs, where to edit Lua.",
        },
    },
    {
        "group": "about",
        "src": {"zh": "about.md", "en": "en/about.md"},
        "out": {"zh": "docs/about.html", "en": "en/docs/about.html"},
        "text": {"zh": "关于 / 版权", "en": "About / copyright"},
        "desc": {
            "zh": "项目来源、许可与致谢。",
            "en": "Project origin, license and credits.",
        },
    },
]

# 分组顺序 / group order for the sidebar（id, 各语言显示名）。
GROUPS = [
    ("wiki", {"zh": "Wiki", "en": "Wiki"}),
    ("api", {"zh": "API 参考", "en": "API reference"}),
    ("guide", {"zh": "使用文档", "en": "Guides"}),
    ("about", {"zh": "关于", "en": "About"}),
]

# 旧锚点兼容（文档内部已存在的 #锚点 链接，按 GFM 风格的 id 生成，
# 这里补一个 hidden alias，保证老链接不会失效）。
ANCHOR_ALIASES = {
    "gmod_lua_port_plan.md": {
        "9-移植状态与经验v3-增补2026-09-12--09-13":
            "9-移植状态与经验v3-增补2026-09-12-09-13",
    },
}

# --------------------------------------------------------------------------
# Lua 语法高亮 / build-time Lua syntax highlighting
# --------------------------------------------------------------------------
# 高亮在构建期由 Python 完成，产物只是多了 <span class="tok-*">，
# 所以页面运行时依旧零依赖（没有 CDN、没有高亮库、没有 fetch）。
# 词法分类刻意做得小而保守：只认 Lua 的关键字/字符串/数字/注释/运算符，
# 以及三类标识符（`.`/`:` 后面的方法名、大写开头的类名、库表名）。
#
# 颜色对齐上游 GMod wiki（https://wiki.facepunch.com/styles/gmod.css 的
# `.markdown .code span.*`，代码块底色 #333、基础前景 #d0d0d0）：
#   keyword #03a9f4 · string #ecce39 · comment #4caf50 · number #eee
#   className #81d0da · method #7cd7e0 · methoddef #95e439
#   operator/brackets #9c9c9c · builtinValue #7bd6ff

LUA_LANGS = frozenset(["lua", "glua", "luau"])

_LUA_KEYWORDS = frozenset("""
and break do else elseif end for function goto if in local not or repeat return
then until while continue
""".split())

# 不是关键字，但 GMod wiki 用 builtinValue 单独上色
_LUA_BUILTIN_VALUES = frozenset(["true", "false", "nil"])

# GMod / HL2SB 里常见的库表与全局函数名：按 className 上色
_LUA_LIBRARIES = frozenset("""
_G vgui draw surface derma hook file util table string math os io coroutine debug
net render cam concommand cvars gameevent killicon language scripted_ents weapons
team player ents engine chat effects constraint physenv sound list
Color Vector Angle Matrix Material RenderTarget CreateMaterial CreateFont
print PrintTable Msg Error NoError Warning ScrW ScrH IsValid CurTime FrameTime
RealTime SysTime tostring tonumber type pairs ipairs next select assert unpack
require setmetatable getmetatable rawget rawset pcall xpcall
""".split())

_LUA_ID_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_LUA_NUM_RE = re.compile(
    r"0[xX][0-9a-fA-F]*(?:\.[0-9a-fA-F]*)?(?:[pP][-+]?[0-9]+)?"
    r"|(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][-+]?[0-9]+)?")
_LUA_LONG_OPEN_RE = re.compile(r"\[(=*)\[")
_LUA_OP_RE = re.compile(
    r"\.\.\.|\.\.|==|~=|<=|>=|!=|&&|\|\||::|[=+\-*/%^#<>(){}[\];:,.&|!~?]")
_LUA_CONST_RE = re.compile(r"[A-Z][A-Z0-9_]*\Z")

# 词法类别 -> CSS class（样式见 assets/style.css 的「Lua 高亮 / tokens」一节）
LUA_TOKEN_CLASSES = {
    "kw": "tok-keyword",
    "str": "tok-string",
    "num": "tok-number",
    "com": "tok-comment",
    "op": "tok-op",
    "meth": "tok-method",
    "cls": "tok-class",
    "def": "tok-def",
    "bi": "tok-builtin",
}


def _lua_tokens(src: str) -> list[tuple[str, str]]:
    """把一段 Lua 切成 (类别, 文本) —— 只做词法，不做语法分析。"""
    toks: list[tuple[str, str]] = []
    i, n = 0, len(src)
    prev = ""          # 上一个「有意义的」token 文本（空白不算）
    while i < n:
        ch = src[i]

        if ch in " \t\r\n":
            j = i
            while j < n and src[j] in " \t\r\n":
                j += 1
            toks.append(("ws", src[i:j]))
            i = j
            continue

        # 注释：--[[ 长注释 ]]、-- 行注释、GLua 的 // 与 /* */
        if src.startswith("--", i):
            m = _LUA_LONG_OPEN_RE.match(src, i + 2)
            if m:
                close = "]" + m.group(1) + "]"
                end = src.find(close, m.end())
                end = n if end < 0 else end + len(close)
            else:
                end = src.find("\n", i)
                end = n if end < 0 else end
            toks.append(("com", src[i:end]))
            i = end
            prev = "com"
            continue
        if src.startswith("/*", i):
            end = src.find("*/", i + 2)
            end = n if end < 0 else end + 2
            toks.append(("com", src[i:end]))
            i = end
            prev = "com"
            continue
        if src.startswith("//", i):
            end = src.find("\n", i)
            end = n if end < 0 else end
            toks.append(("com", src[i:end]))
            i = end
            prev = "com"
            continue

        # 长字符串 [[ ... ]] / [==[ ... ]==]
        if ch == "[":
            m = _LUA_LONG_OPEN_RE.match(src, i)
            if m:
                close = "]" + m.group(1) + "]"
                end = src.find(close, m.end())
                end = n if end < 0 else end + len(close)
                toks.append(("str", src[i:end]))
                i = end
                prev = "str"
                continue

        # 短字符串 / 字符
        if ch in "\"'":
            j = i + 1
            while j < n:
                c = src[j]
                if c == "\\":
                    j += 2
                    continue
                j += 1
                if c == ch or c == "\n":
                    break
            toks.append(("str", src[i:j]))
            i = j
            prev = "str"
            continue

        # 数字
        if ch.isdigit() or (ch == "." and i + 1 < n and src[i + 1].isdigit()):
            m = _LUA_NUM_RE.match(src, i)
            if m:
                toks.append(("num", m.group(0)))
                i = m.end()
                prev = "num"
                continue

        # 标识符
        m = _LUA_ID_RE.match(src, i)
        if m:
            word = m.group(0)
            if prev in (".", ":"):
                kind = "meth"
            elif word in _LUA_KEYWORDS:
                kind = "kw"
            elif word in _LUA_BUILTIN_VALUES:
                kind = "bi"
            elif prev == "function":
                kind = "def"
            elif (word in _LUA_LIBRARIES or word[:1].isupper()
                  or _LUA_CONST_RE.match(word)):
                kind = "cls"
            else:
                kind = "plain"
            toks.append((kind, word))
            i = m.end()
            prev = word
            continue

        # 运算符 / 标点
        m = _LUA_OP_RE.match(src, i)
        if m:
            op = m.group(0)
            toks.append(("op", op))
            i = m.end()
            prev = op
            continue

        # 兜底：认不出来的字符原样保留
        toks.append(("plain", ch))
        i += 1
        prev = "plain"
    return toks


def highlight_lua(src: str) -> str:
    """Lua 源码 -> 带 <span class="tok-*"> 的 HTML（已转义）。"""
    out: list[str] = []
    for kind, text in _lua_tokens(src):
        cls = LUA_TOKEN_CLASSES.get(kind)
        if cls:
            out.append('<span class="%s">%s</span>' % (cls, esc_code(text)))
        else:
            out.append(esc_code(text))
    return "".join(out)


def highlight_code(code: str, lang: str) -> str:
    """按围栏语言高亮；目前只有 Lua 一族有高亮器，其它语言原样转义。"""
    if (lang or "").strip().lower() in LUA_LANGS:
        return highlight_lua(code)
    return esc_code(code)


# --------------------------------------------------------------------------
# Markdown 渲染器 / tiny markdown renderer
# --------------------------------------------------------------------------

_PH = "\x00PH%d\x00"
_BR = "\x00BR\x00"

_ENTITY_MAP = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
}


def esc(text: str) -> str:
    """HTML 转义（用于正文文本，先转义再交给 inline 处理，最后会被解回实体）。"""
    return "".join(_ENTITY_MAP.get(ch, ch) for ch in text)


def esc_code(text: str) -> str:
    """代码块用的转义，结果直接作为最终文本（不做实体还原）。"""
    return _html.escape(text, quote=False)


def slugify(text: str) -> str:
    """接近 GitHub 的 anchor 规则（保留中日韩字符）。"""
    s = re.sub(r"<[^>]+>", "", text)
    s = unescape(s)
    s = s.strip().lower()
    s = re.sub(r"[^\w\u3400-\u9fff\- ]+", "", s, flags=re.UNICODE)
    s = re.sub(r"\s+", "-", s)
    return s.strip("-")


def unescape(text: str) -> str:
    return (_html.unescape(text)
            .replace("&lt;", "<").replace("&gt;", ">")
            .replace("&quot;", '"').replace("&#39;", "'"))


def inline(text: str) -> str:
    """行内标记 -> HTML。输入应当已经过 esc()。"""
    store: list[str] = []

    def stash(value: str) -> str:
        store.append(value)
        return _PH % (len(store) - 1)

    # 1. 行内代码 `...`（用 lookaround 保证不会跨多个代码段匹配，
    #    否则 `` `**` 或 `x/**` `` 这种行会把结尾的反引号吃掉）
    def _code(m: re.Match) -> str:
        body = unescape(m.group(2))
        return stash("<code>" + esc_code(body) + "</code>")

    text = re.sub(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)", _code, text, flags=re.S)

    # 2. 图片 ![alt](src)
    def _img(m: re.Match) -> str:
        alt = unescape(m.group(1))
        src = _html.unescape(m.group(2)).strip()
        return stash('<img src="%s" alt="%s" loading="lazy">'
                     % (esc_code(src), esc_code(alt)))

    text = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)", _img, text)

    # 3. 链接 [text](href)
    def _link(m: re.Match) -> str:
        label = inline(m.group(1))
        href = _html.unescape(m.group(2)).strip()
        extra = ""
        if href.startswith(("http://", "https://")):
            extra = ' target="_blank" rel="noopener"'
        return stash('<a href="%s"%s>%s</a>' % (esc_code(href), extra, label))

    text = re.sub(r"\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)", _link, text)

    # 4. 裸 URL
    text = re.sub(
        r"(?<![\"'=(>])\b(https?://[^\s<>\"'）)，。]+)",
        lambda m: stash('<a href="%s" target="_blank" rel="noopener">%s</a>'
                        % (esc_code(m.group(1)), m.group(1))),
        text)

    # 5. 强调
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text, flags=re.S)
    text = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<em>\1</em>", text)
    text = re.sub(r"(?<![\w_])__([^_\n]+?)__(?![\w_])", r"<strong>\1</strong>", text)
    text = re.sub(r"~~(.+?)~~", r"<del>\1</del>", text, flags=re.S)

    out = unescape(text)
    for i, value in enumerate(store):
        out = out.replace(_PH % i, value)
    return out


_HR_RE = re.compile(r"^(?:-{3,}|\*{3,}|_{3,})\s*$")
_HEAD_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})\s*([\w+#.-]*)\s*$")
_TABLE_SEP_RE = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?$")
_QUOTE_RE = re.compile(r"^>\s?(.*)$")
_UL_RE = re.compile(r"^([-*+])\s+(.*)$")
_OL_RE = re.compile(r"^(\d+)[.)]\s+(.*)$")
_ATTR_RE = re.compile(r"\s*\{#([^}]+)\}\s*$")


def _split_row(row: str) -> list[str]:
    row = row.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|") and not row.endswith("\\|"):
        row = row[:-1]
    return [c.strip() for c in row.split("|")]


class MarkdownRenderer:
    def __init__(self, ui: dict | None = None):
        self.toc: list[dict] = []
        self._used_ids: set[str] = set()
        self._lines: list[str] = []
        self._i = 0
        self._para: list[str] = []
        self._body_h1_seen = 0
        self._doc_title = ""
        # 界面文案（复制按钮的「复制 / Copied」按语言走，见 UI）
        self.ui = ui or {}

    # -- 对外入口 ---------------------------------------------------------
    def render(self, text: str, doc_title: str = "") -> str:
        self._doc_title = doc_title
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = text.replace("\u00a0", " ")
        self._lines = text.split("\n")
        self._i = 0
        self._para = []
        blocks: list[str] = []
        while self._i < len(self._lines):
            line = self._lines[self._i]
            if not line.strip():
                self._flush(blocks)
                self._i += 1
                continue
            if _HR_RE.match(line):
                self._flush(blocks)
                blocks.append("<hr>")
                self._i += 1
                continue
            m = _FENCE_RE.match(line)
            if m:
                self._flush(blocks)
                blocks.append(self._fence(m))
                continue
            m = _HEAD_RE.match(line)
            if m:
                self._flush(blocks)
                level = len(m.group(1))
                if level == 1 and self._body_h1_seen == 0:
                    self._body_h1_seen += 1
                    # 第一个一级标题就是文档标题：模板已经渲染过 .doc-title，
                    # 两者相同（或一方包含另一方，例如「HL2SB Derma 基础指南」）时不再重复渲染。
                    head_text = self._heading_text(m.group(2))
                    if head_text == self._doc_title or (
                            head_text and (head_text in self._doc_title
                                           or self._doc_title in head_text)):
                        self._i += 1
                        continue
                rendered = self._heading(m)
                blocks.append(rendered)
                self._i += 1
                continue
            if line.lstrip().startswith(">"):
                self._flush(blocks)
                blocks.append(self._quote())
                continue
            if self._is_table_start():
                self._flush(blocks)
                blocks.append(self._table())
                continue
            if _UL_RE.match(line) or _OL_RE.match(line):
                self._flush(blocks)
                blocks.append(self._list())
                continue
            self._para.append(line.strip())
            self._i += 1
        self._flush(blocks)
        return "\n".join(b for b in blocks if b)

    # -- 内部工具 ---------------------------------------------------------
    def _flush(self, blocks: list[str]) -> None:
        if not self._para:
            return
        body = "\n".join(self._para)
        self._para = []
        # 段落内部软换行 -> <br>（文档里大量依赖这一点）。
        # 先换成哨兵字符再走 inline()，否则「跨行的 **粗体**」会被 HTML 标签挡住而渲染失败。
        html = inline(esc(body).replace("\n", _BR))
        blocks.append("<p>%s</p>" % html.replace(_BR, "<br>\n"))

    def _unique_id(self, base: str) -> str:
        candidate = base or "section"
        n = 1
        while candidate in self._used_ids:
            n += 1
            candidate = "%s-%d" % (base, n)
        self._used_ids.add(candidate)
        return candidate

    @staticmethod
    def _heading_text(raw: str) -> str:
        """标题的纯文本（去掉 {#anchor}、行尾 #、markdown 标记）。"""
        text = _ATTR_RE.sub("", raw).strip()
        text = re.sub(r"\s+#+\s*$", "", text).strip()
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        text = re.sub(r"`(.+?)`", r"\1", text)
        return text.strip()

    def _heading(self, m: re.Match) -> str:
        level = len(m.group(1))
        raw = m.group(2).strip()
        explicit = None
        am = _ATTR_RE.search(raw)
        if am:
            explicit = am.group(1)
            raw = _ATTR_RE.sub("", raw).strip()
        raw = re.sub(r"\s+#+\s*$", "", raw).strip()
        hid = self._unique_id(explicit or slugify(raw))
        label = inline(esc(raw))
        if level >= 2:
            self.toc.append({"id": hid, "text": unescape(re.sub(r"<[^>]+>", "", label)),
                             "level": level})
        return '<h%d id="%s">%s<a class="anchor" href="#%s" aria-hidden="true">#</a></h%d>' % (
            level, hid, label, hid, level)

    def _codeblock(self, lang: str, code: str) -> str:
        """一个代码块（含语言标签与「复制」按钮）；Lua 一族在这里就被高亮。"""
        label = ('<span class="code-lang">%s</span>' % esc_code(lang)) if lang else ""
        copy_label = self.ui.get("copy", "复制")
        copied_label = self.ui.get("copied", "已复制")
        return ('<div class="codeblock">'
                '<div class="code-head">%s<button class="copy-btn" type="button" '
                'data-copy="1" data-copied="%s">%s</button></div>'
                '<pre><code%s>%s</code></pre></div>'
                % (label, esc_code(copied_label), esc_code(copy_label),
                   (' class="language-%s"' % esc_code(lang)) if lang else "",
                   highlight_code(code, lang)))

    def _read_fence_body(self, marker: str) -> str:
        """从当前位置读到收尾围栏，返回代码正文（self._i 停在围栏之后）。"""
        buf: list[str] = []
        while self._i < len(self._lines):
            line = self._lines[self._i]
            if line.strip().startswith(marker[0] * 3):
                self._i += 1
                break
            buf.append(line)
            self._i += 1
        return "\n".join(buf)

    def _fence(self, m: re.Match) -> str:
        marker = m.group(1)
        lang = (m.group(2) or "").strip()
        self._i += 1
        return self._codeblock(lang, self._read_fence_body(marker))

    def _quote(self) -> str:
        buf: list[str] = []
        while self._i < len(self._lines):
            line = self._lines[self._i]
            if not line.strip():
                # 引用块里的空行：向前看一行还是引用就继续
                nxt = self._lines[self._i + 1] if self._i + 1 < len(self._lines) else ""
                if nxt.lstrip().startswith(">"):
                    buf.append("")
                    self._i += 1
                    continue
                break
            qm = _QUOTE_RE.match(line)
            if not qm:
                break
            buf.append(qm.group(1))
            self._i += 1
        # 引用块里允许简单列表
        body_lines: list[str] = []
        bullets: list[str] = []

        def flush_bullets() -> None:
            if bullets:
                body_lines.append("<ul>%s</ul>"
                                  % "".join("<li>%s</li>" % b for b in bullets))
                bullets.clear()

        for ln in buf:
            bm = _UL_RE.match(ln)
            if bm:
                bullets.append(inline(esc(bm.group(2))))
            else:
                flush_bullets()
                body_lines.append(ln)
        flush_bullets()
        html = inline(esc("\n".join(body_lines)).replace("\n", _BR))
        return "<blockquote>%s</blockquote>" % html.replace(_BR, "<br>\n")

    def _is_table_start(self) -> bool:
        if self._i + 1 >= len(self._lines):
            return False
        head, sep = self._lines[self._i], self._lines[self._i + 1]
        if "|" not in head:
            return False
        return bool(_TABLE_SEP_RE.match(sep.strip())) and "|" in sep

    def _table(self) -> str:
        head = _split_row(self._lines[self._i])
        seps = _split_row(self._lines[self._i + 1])
        aligns: list[str] = []
        for cell in seps:
            if cell.startswith(":") and cell.endswith(":"):
                aligns.append("center")
            elif cell.endswith(":"):
                aligns.append("right")
            else:
                aligns.append("left")
        self._i += 2
        rows: list[list[str]] = []
        while self._i < len(self._lines):
            line = self._lines[self._i]
            if not line.strip() or "|" not in line:
                break
            rows.append(_split_row(line))
            self._i += 1

        def cell(tag: str, content: str, idx: int) -> str:
            align = aligns[idx] if idx < len(aligns) else "left"
            return '<%s style="text-align:%s">%s</%s>' % (
                tag, align, inline(esc(content)), tag)

        out = ['<div class="table-wrap"><table>', "<thead><tr>"]
        for idx, c in enumerate(head):
            out.append(cell("th", c, idx))
        out.append("</tr></thead><tbody>")
        for row in rows:
            out.append("<tr>")
            for idx in range(len(head)):
                out.append(cell("td", row[idx] if idx < len(row) else "", idx))
            out.append("</tr>")
        out.append("</tbody></table></div>")
        return "".join(out)

    def _list(self) -> str:
        first = self._lines[self._i]
        ordered = bool(_OL_RE.match(first))
        tag = "ol" if ordered else "ul"
        # 每一项是 list[str | tuple[("code"), html]]：
        # 缩进的 ``` 围栏属于它所在的那条列表项，要和正文区分开渲染成代码块
        # （否则会被 inline() 当成一段行内 `code`，既不换行也不高亮）。
        items: list[list] = []
        current: list = []
        while self._i < len(self._lines):
            line = self._lines[self._i]
            if not line.strip():
                break
            fm = _FENCE_RE.match(line)
            if fm and current:
                self._i += 1
                lang = (fm.group(2) or "").strip()
                current.append(("code", self._codeblock(
                    lang, self._read_fence_body(fm.group(1)))))
                continue
            if len(line) > 0 and line[0] in " \t" and current:
                current.append(line.strip())
                self._i += 1
                continue
            m = _OL_RE.match(line) if ordered else _UL_RE.match(line)
            if not m:
                break
            if current:
                items.append(current)
            current = [m.group(2)]
            self._i += 1
        if current:
            items.append(current)
        return "<%s>%s</%s>" % (
            tag, "".join(self._item_html(it) for it in items), tag)

    @staticmethod
    def _item_html(parts: list) -> str:
        # 整条列表项的多个物理行要放在一起走 inline()：
        # 跨行的 **粗体** / `代码` 只在这种情况下才能正确配对。
        out: list[str] = []
        buf: list[str] = []

        def flush() -> None:
            if not buf:
                return
            joined = esc("\n".join(buf)).replace("\n", _BR)
            out.append(inline(joined).replace(_BR, "<br>\n"))
            buf.clear()

        for part in parts:
            if isinstance(part, str):
                buf.append(part)
            else:
                flush()
                out.append(part[1])
        flush()
        return "<li>%s</li>" % "".join(out)


def render_markdown(text: str, doc_title: str = "",
                    ui: dict | None = None) -> tuple[str, list[dict]]:
    r = MarkdownRenderer(ui)
    return r.render(text, doc_title), r.toc

# --------------------------------------------------------------------------
# 模板 / templates
# --------------------------------------------------------------------------

PAGE_TMPL = """<!DOCTYPE html>
<html lang="$$HTMLLANG$$" data-theme="auto">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$$TITLE$$ · $$SITENAME$$</title>
<meta name="description" content="$$DESC$$">
<link rel="stylesheet" href="$$ROOT$$assets/style.css">
<link rel="icon" type="image/svg+xml" href="$$ROOT$$assets/favicon.svg">
$$ALTERNATES$$
<script>(function(){try{var t=localStorage.getItem('hl2sb-theme');if(t==='dark'||t==='light'){document.documentElement.setAttribute('data-theme',t);}}catch(e){}})();</script>
</head>
<body data-lb-close="$$LB_CLOSE$$" data-lb-open="$$LB_OPEN$$">
<a class="skip-link" href="#content">$$SKIP$$</a>
<header class="topbar">
  <button class="icon-btn nav-toggle" type="button" aria-label="$$NAV_TOGGLE$$" aria-expanded="false">☰</button>
  <a class="brand" href="$$BRAND_HREF$$">
    <span class="brand-mark">HL2<em>SB</em></span>
    <span class="brand-sub">$$BRAND_SUB$$</span>
  </a>
  <div class="topbar-spacer"></div>
  <button class="search-open icon-btn" type="button" aria-label="$$SEARCH$$">🔍<span class="search-open-text">$$SEARCH$$</span></button>
  $$LANG_SWITCH$$
  <button class="icon-btn theme-toggle" type="button" aria-label="$$THEME$$"><span class="theme-icon">◐</span></button>
</header>
<div class="layout">
  <aside class="sidebar" id="sidebar">
$$SIDEBAR$$
  </aside>
  <main class="content" id="content">
$$BODY$$
  </main>
</div>
<div class="search-overlay" id="searchOverlay" hidden
     data-index="$$ROOT$$$$SEARCH_INDEX$$"
     data-idle="$$SEARCH_IDLE$$" data-loading="$$SEARCH_LOADING$$" data-none="$$SEARCH_NONE$$">
  <div class="search-panel" role="dialog" aria-modal="true" aria-label="$$SEARCH_DIALOG$$">
    <input type="search" id="searchInput" placeholder="$$SEARCH_PH$$" autocomplete="off">
    <div class="search-results" id="searchResults"><p class="muted">$$SEARCH_IDLE$$</p></div>
    <div class="search-hint">$$SEARCH_HINT$$</div>
  </div>
</div>
<footer class="footer">
  <div class="footer-inner">
    <p>$$FOOTER1$$</p>
    <p class="muted">$$FOOTER2$$</p>
    <p class="muted">
      <a href="$$REPO_ENGINE$$" target="_blank" rel="noopener">$$FOOTER_ENGINE$$</a> ·
      <a href="$$REPO_GAME$$" target="_blank" rel="noopener">$$FOOTER_GAME$$</a> ·
      <a href="$$REPO_SITE$$" target="_blank" rel="noopener">$$FOOTER_SITE$$</a> ·
      <a href="$$ABOUT_HREF$$">$$FOOTER_ABOUT$$</a>
    </p>
    <p class="muted small">$$FOOTER_NOTE$$</p>
  </div>
</footer>
<script src="$$ROOT$$assets/app.js" defer></script>
</body>
</html>
"""

DOC_PAGE_TMPL = """<nav class="crumbs"><a href="$$HOME_HREF$$">$$CRUMB_HOME$$</a><span class="sep">/</span><span>$$GROUP$$</span><span class="sep">/</span><span class="current">$$TITLE$$</span></nav>
<article class="doc">
$$ARTICLE$$
</article>
<div class="page-foot">
  <p class="muted">$$SRC_NOTE$$<code>docs/$$SRC$$</code> · $$SRC_NOTE_TAIL$$ · $$GENERATED$$ $$BUILDDATE$$</p>
  <p><a href="$$EDIT_URL$$" target="_blank" rel="noopener">$$EDIT_LABEL$$</a></p>
</div>
"""

# 首页正文（按语言）。文档链接用 $$DOCPREFIX$$，中文是 "docs/"，英文是 "en/docs/"。
HOME_TMPL = {
    "zh": """<section class="hero">
  <h1>HL2SB 文档站</h1>
  <p class="lead">HL2SB（<strong>Half-Life 2: Sandbox</strong>）是一个 Source 引擎分支，目标是在 Source SDK 2013 的引擎上<strong>原样运行 Garry's Mod 的 Lua</strong> —— Derma 面板、Spawnmenu、SWEP、killicon……尽量做到 GMod 的脚本一行不改就能跑。</p>
  <div class="hero-actions">
    <a class="btn primary" href="$$DOCPREFIX$$derma_basic_guide.html">读 Derma 基础指南</a>
    <a class="btn" href="$$DOCPREFIX$$build_and_run.html">自己编译运行</a>
    <a class="btn" href="$$DOCPREFIX$$index.html">全部文档</a>
  </div>
  <ul class="hero-meta">
    <li><span class="k">引擎</span> nillerusr/source-engine（Source SDK 2013）分支 <code>lua_playermodel_menu</code></li>
    <li><span class="k">Lua</span> Lua 5.4.6 + GLua 语法扩展（<code>continue</code>、<code>! != &amp;&amp; ||</code>、<code>//</code>）</li>
    <li><span class="k">游戏内容</span> 与引擎配对的纯文本内容仓库（cfg / resource / lua / materials 定义）</li>
    <li><span class="k">平台</span> Windows（waf + MSVC 构建）</li>
  </ul>
</section>

<section class="cards">
  <h2>它现在能做什么</h2>
  <div class="card-grid">
    <div class="card"><h3>Derma / VGUI</h3><p>GMod 的 <code>vgui.Create</code>、<code>DFrame</code>、<code>DPanel</code>、<code>DButton</code>、<code>DListView</code> … 面板与皮肤系统，已按 GMod 的 Lua 实现接上。</p><p class="muted small">详见 <a href="$$DOCPREFIX$$derma_basic_guide.html">Derma 基础指南</a></p></div>
    <div class="card"><h3>GMod 兼容层</h3><p><code>hook</code>、<code>surface</code>、<code>Color</code>、<code>draw</code>、<code>killicon</code>、<code>file</code>、<code>vgui</code> 等库按 GMod 的签名补齐，缺的补在引擎 C++ 侧。</p><p class="muted small">详见 <a href="$$DOCPREFIX$$gmod_compat_layer.html">GMod Lua 兼容层</a></p></div>
    <div class="card"><h3>Lua SWEP / 武器</h3><p>引擎按 GMod 的继承链驱动 Lua 武器：<code>PrimaryAttack</code> / <code>SecondaryAttack</code> / <code>Deploy</code>，含弹药、模型、槽位数据。</p><p class="muted small">详见 <a href="$$DOCPREFIX$$gmod_lua_port_plan.html">移植计划与状态</a></p></div>
    <div class="card"><h3>HUD / 击杀播报</h3><p>GMod 原版 <code>cl_deathnotice.lua</code> 移植版：killicon 图标、淡出、队伍配色；另有 GMod 内容贴图（PNG）直读。</p><p class="muted small">详见 <a href="$$DOCPREFIX$$gmod_lua_port_plan.html">移植计划与状态</a></p></div>
  </div>
</section>

<section class="prose">
  <h2>快速开始</h2>
  <p>HL2SB 由两个仓库组成：<strong>引擎源码</strong>（C++，编出 client / server DLL）与<strong>游戏内容</strong>（cfg / resource / lua / materials，只收录文本资源）。运行流程是：编译引擎 → 把 DLL 放进游戏内容的 <code>bin/</code> → 启动游戏 → 在控制台里用 <code>lua_dofile_cl</code> 跑脚本。</p>
  <ol class="steps">
    <li><a href="$$REPO_ENGINE$$" target="_blank" rel="noopener">引擎仓库</a>：编译 <code>client</code> / <code>server</code>（<code>cmd /c ".\\waf.bat build --targets=client,server"</code>）。</li>
    <li>把 <code>build\\game\\client\\client.dll</code>、<code>build\\game\\server\\server.dll</code> 复制到游戏内容的 <code>bin\\</code> 目录。</li>
    <li><a href="$$REPO_GAME$$" target="_blank" rel="noopener">游戏内容仓库</a>：把它作为 mod 目录，用引擎启动器启动；DLL 只在游戏启动时加载，换 DLL 必须<strong>完全重启</strong>。</li>
    <li>进图后控制台里 <code>lua_dofile_cl skins/hl2sb_default.lua</code> 之类即可跑 Lua。</li>
  </ol>
  <p class="callout"><strong>提示：</strong>中国用户常从零开始 —— 建议先读 <a href="$$DOCPREFIX$$build_and_run.html">构建与运行</a>，再读 <a href="$$DOCPREFIX$$derma_basic_guide.html">Derma 基础指南</a>。</p>
</section>

<section class="prose">
  <h2>当前状态</h2>
  <p class="muted">这一节随开发推进更新；细节与逐项勾选见 <a href="$$DOCPREFIX$$gmod_lua_port_plan.html">GMod Lua 移植计划与状态</a>。</p>
  $$STATUS$$
</section>

<section class="prose">
  <h2>仓库</h2>
  <div class="table-wrap"><table>
    <thead><tr><th>仓库</th><th>内容</th></tr></thead>
    <tbody>
      <tr><td><a href="$$REPO_ENGINE$$" target="_blank" rel="noopener">source-engine-mod</a></td><td>引擎源码（nillerusr source-engine + HL2SB 改动），分支 <code>lua_playermodel_menu</code></td></tr>
      <tr><td><a href="$$REPO_GAME$$" target="_blank" rel="noopener">hl2sb-gamefile</a></td><td>游戏内容（cfg / resource / lua / materials / gamemodes），只收录可编辑的文本资源</td></tr>
      <tr><td><a href="$$REPO_SITE$$" target="_blank" rel="noopener">hl2sb.github.io</a></td><td>本站文档的源文件与静态生成器</td></tr>
    </tbody>
  </table></div>
</section>
""",
    "en": """<section class="hero">
  <h1>HL2SB documentation</h1>
  <p class="lead">HL2SB (<strong>Half-Life 2: Sandbox</strong>) is a Source engine fork whose goal is to <strong>run Garry's Mod's Lua unchanged</strong> on the Source SDK 2013 engine — Derma panels, spawnmenu, SWEPs, killicons… ideally with GMod scripts running without a single edit.</p>
  <div class="hero-actions">
    <a class="btn primary" href="$$DOCPREFIX$$derma_basic_guide.html">Read the Derma guide</a>
    <a class="btn" href="$$DOCPREFIX$$build_and_run.html">Build it yourself</a>
    <a class="btn" href="$$DOCPREFIX$$index.html">All documents</a>
  </div>
  <ul class="hero-meta">
    <li><span class="k">Engine</span> nillerusr/source-engine (Source SDK 2013), branch <code>lua_playermodel_menu</code></li>
    <li><span class="k">Lua</span> Lua 5.4.6 + GLua syntax extensions (<code>continue</code>, <code>! != &amp;&amp; ||</code>, <code>//</code>)</li>
    <li><span class="k">Game content</span> a text-only content repo paired with the engine (cfg / resource / lua / materials)</li>
    <li><span class="k">Platform</span> Windows (waf + MSVC)</li>
  </ul>
</section>

<section class="cards">
  <h2>What it can do today</h2>
  <div class="card-grid">
    <div class="card"><h3>Derma / VGUI</h3><p>GMod's <code>vgui.Create</code>, <code>DFrame</code>, <code>DPanel</code>, <code>DButton</code>, <code>DListView</code> … panel and skin system, wired up the way GMod's own Lua does it.</p><p class="muted small">See <a href="$$DOCPREFIX$$derma_basic_guide.html">Derma basics</a></p></div>
    <div class="card"><h3>GMod compatibility layer</h3><p><code>hook</code>, <code>surface</code>, <code>Color</code>, <code>draw</code>, <code>killicon</code>, <code>file</code>, <code>vgui</code> and friends are filled in to GMod's signatures; whatever is missing is added on the engine's C++ side.</p><p class="muted small">See <a href="$$DOCPREFIX$$gmod_compat_layer.html">GMod Lua compatibility layer</a></p></div>
    <div class="card"><h3>Lua SWEPs / weapons</h3><p>The engine drives Lua weapons through GMod's inheritance chain: <code>PrimaryAttack</code> / <code>SecondaryAttack</code> / <code>Deploy</code>, with ammo, models and slot data.</p><p class="muted small">See <a href="$$DOCPREFIX$$gmod_lua_port_plan.html">Port plan &amp; status</a></p></div>
    <div class="card"><h3>HUD / kill feed</h3><p>A port of GMod's own <code>cl_deathnotice.lua</code>: killicon icons, fade-out, team colours; plus GMod content textures (PNG) read directly.</p><p class="muted small">See <a href="$$DOCPREFIX$$gmod_lua_port_plan.html">Port plan &amp; status</a></p></div>
  </div>
</section>

<section class="prose">
  <h2>Quick start</h2>
  <p>HL2SB is two repositories: the <strong>engine source</strong> (C++, builds the client / server DLLs) and the <strong>game content</strong> (cfg / resource / lua / materials — text resources only). The flow is: build the engine → drop the DLLs into the content repo's <code>bin/</code> → launch the game → run scripts from the console with <code>lua_dofile_cl</code>.</p>
  <ol class="steps">
    <li><a href="$$REPO_ENGINE$$" target="_blank" rel="noopener">Engine repo</a>: build <code>client</code> / <code>server</code> (<code>cmd /c ".\\waf.bat build --targets=client,server"</code>).</li>
    <li>Copy <code>build\\game\\client\\client.dll</code> and <code>build\\game\\server\\server.dll</code> into the content repo's <code>bin\\</code>.</li>
    <li><a href="$$REPO_GAME$$" target="_blank" rel="noopener">Game content repo</a>: use it as the mod directory and launch it with the engine launcher; DLLs are loaded only at process start, so swapping them requires a <strong>full restart</strong>.</li>
    <li>Once a map is loaded, <code>lua_dofile_cl skins/hl2sb_default.lua</code> (and friends) runs Lua from the console.</li>
  </ol>
  <p class="callout"><strong>Tip:</strong> new here? Read <a href="$$DOCPREFIX$$build_and_run.html">Build &amp; run</a> first, then the <a href="$$DOCPREFIX$$derma_basic_guide.html">Derma guide</a>.</p>
</section>

<section class="prose">
  <h2>Current status</h2>
  <p class="muted">This section is updated as development continues; details and the item-by-item checklist live in <a href="$$DOCPREFIX$$gmod_lua_port_plan.html">GMod Lua port plan &amp; status</a>.</p>
  $$STATUS$$
</section>

<section class="prose">
  <h2>Repositories</h2>
  <div class="table-wrap"><table>
    <thead><tr><th>Repo</th><th>Contents</th></tr></thead>
    <tbody>
      <tr><td><a href="$$REPO_ENGINE$$" target="_blank" rel="noopener">source-engine-mod</a></td><td>Engine source (nillerusr source-engine + HL2SB changes), branch <code>lua_playermodel_menu</code></td></tr>
      <tr><td><a href="$$REPO_GAME$$" target="_blank" rel="noopener">hl2sb-gamefile</a></td><td>Game content (cfg / resource / lua / materials / gamemodes) — editable text resources only</td></tr>
      <tr><td><a href="$$REPO_SITE$$" target="_blank" rel="noopener">hl2sb.github.io</a></td><td>Sources and static generator for this site</td></tr>
    </tbody>
  </table></div>
</section>
""",
}


# --------------------------------------------------------------------------
# 站点骨架 / sidebar、语言切换 / language switcher
# --------------------------------------------------------------------------

def rel_root(out_path: str) -> str:
    """页面相对 dist 根的前缀（"../" * 深度）—— assets/ 与站点根都在 dist/。"""
    return "../" * out_path.count("/")


def rel_link(from_out: str, to_out: str) -> str:
    """dist/ 里两个输出文件之间的相对链接（跨语言、跨深度都适用）。"""
    return os.path.relpath(to_out, os.path.dirname(from_out) or ".").replace("\\", "/")


def page_of(out_path: str):
    """按输出路径找回清单里的逻辑页（语言切换器要拿它的对照页）。"""
    for page in PAGES:
        for code in LANG_CODES:
            if page["out"].get(code) == out_path:
                return page
    return None


def build_sidebar(current_out: str, lang: str) -> str:
    root = rel_root(current_out)
    ui = UI[lang]
    parts = ['<form class="side-search" role="search" onsubmit="return false;">',
             '  <input type="search" id="sideSearch" placeholder="%s" aria-label="%s">'
             % (esc(ui["side_search_ph"]), esc(ui["search"])),
             "</form>"]
    parts.append('<nav class="side-nav">')
    for gid, labels in GROUPS:
        entries = [p for p in PAGES if p["group"] == gid and p["out"].get(lang)]
        if not entries:
            continue
        parts.append('<div class="side-group"><div class="side-group-title">%s</div><ul>'
                     % esc(labels[lang]))
        for p in entries:
            out = p["out"][lang]
            active = ' class="active" aria-current="page"' if out == current_out else ""
            parts.append('<li><a href="%s%s"%s>%s</a></li>'
                         % (root, out, active, esc(p["text"][lang])))
        parts.append("</ul></div>")
    parts.append('<div class="side-group"><div class="side-group-title">%s</div><ul>'
                 % esc(ui["side_project"]))
    parts.append('<li><a href="%s%s">%s</a></li>'
                 % (root, HOME_OF[lang], esc(ui["side_home"])))
    parts.append('<li><a href="%s" target="_blank" rel="noopener">%s</a></li>'
                 % (SITE["repo_site"], esc(ui["side_repo"])))
    parts.append("</ul></div>")
    parts.append("</nav>")
    parts.append('<div class="side-foot small">%s</div>' % ui["side_hint"])
    return "\n".join(parts)


# 不在 PAGES 里成对出现的固定页面（404）也要能双向切换，这里显式配对。
EXTRA_PAIRS = [{"zh": "404.html", "en": "en/404.html"}]


def counterpart_out(out_path: str, lang: str) -> str:
    """同一页面的另一种语言输出路径；没有翻译版就退回对方首页。"""
    other = OTHER_LANG[lang]
    page = page_of(out_path)
    if page and page["out"].get(other):
        return page["out"][other]
    for pair in EXTRA_PAIRS:
        if pair.get(lang) == out_path and pair.get(other):
            return pair[other]
    return HOME_OF[other]


def lang_switch_html(out_path: str, lang: str) -> str:
    """右上角的语言切换器。

    显示的是**目标语言**的旗帜 + 短名（中文页上显示英国旗 + EN），点一下切到对照页。
    ⚠️ 旗帜是内联 SVG，不是国旗 emoji：Windows 浏览器不渲染 🇨🇳/🇬🇧，会变成 "CN"/"GB"。
    """
    other = OTHER_LANG[lang]
    target = counterpart_out(out_path, lang)
    ui = UI[lang]
    title = ui["lang_switch_title"]
    return ('<a class="lang-switch" href="%s" hreflang="%s" lang="%s" title="%s" '
            'aria-label="%s">%s<span class="lang-label">%s</span></a>'
            % (esc_code(rel_link(out_path, target)), LANG_BY_CODE[other]["html_lang"],
               other, esc(title), esc(title), FLAG_OF[other],
               esc(LANG_BY_CODE[other]["short"])))


def alternates_html(out_path: str, lang: str) -> str:
    """<link rel="alternate" hreflang> —— 两种语言互指，便于搜索引擎与手工发现。"""
    lines = []
    for l in LANGUAGES:
        target = out_path if l["code"] == lang else counterpart_out(out_path, lang)
        lines.append('<link rel="alternate" hreflang="%s" href="%s">'
                     % (l["html_lang"], esc_code(rel_link(out_path, target))))
    return "\n".join(lines)


def build_toc(toc: list[dict], lang: str) -> str:
    items = [t for t in toc if t["level"] in (2, 3)]
    if not items:
        return ""
    out = ['<details class="toc" open><summary>%s</summary><ul>' % esc(UI[lang]["toc"])]
    for t in items:
        cls = ' class="lv3"' if t["level"] == 3 else ""
        out.append('<li%s><a href="#%s">%s</a></li>' % (cls, t["id"], esc(t["text"])))
    out.append("</ul></details>")
    return "\n".join(out)


def about_out_of(lang: str) -> str:
    for p in PAGES:
        if p["group"] == "about" and p["out"].get(lang):
            return p["out"][lang]
    return HOME_OF[lang]


def wrap_page(out_path: str, lang: str, title: str, desc: str, body: str) -> str:
    """填页面骨架。所有会显示给读者的字都来自 UI[lang] / SITE，模板里不再写死语言。"""
    ui = UI[lang]
    root = rel_root(out_path)
    page = (PAGE_TMPL
            .replace("$$HTMLLANG$$", LANG_BY_CODE[lang]["html_lang"])
            .replace("$$TITLE$$", esc(title))
            .replace("$$SITENAME$$", esc(SITE["name"][lang]))
            .replace("$$DESC$$", esc(desc))
            .replace("$$ROOT$$", root)
            .replace("$$ALTERNATES$$", alternates_html(out_path, lang))
            .replace("$$LB_CLOSE$$", esc(ui["lightbox_close"]))
            .replace("$$LB_OPEN$$", esc(ui["lightbox_open"]))
            .replace("$$SKIP$$", esc(ui["skip"]))
            .replace("$$NAV_TOGGLE$$", esc(ui["nav_toggle"]))
            .replace("$$BRAND_HREF$$", esc_code(rel_link(out_path, HOME_OF[lang])))
            .replace("$$BRAND_SUB$$", esc(ui["brand_sub"]))
            .replace("$$SEARCH$$", esc(ui["search"]))
            .replace("$$LANG_SWITCH$$", lang_switch_html(out_path, lang))
            .replace("$$THEME$$", esc(ui["theme"]))
            .replace("$$SIDEBAR$$", build_sidebar(out_path, lang))
            .replace("$$BODY$$", body)
            .replace("$$SEARCH_INDEX$$", INDEX_OF[lang])
            .replace("$$SEARCH_IDLE$$", esc(ui["search_idle"]))
            .replace("$$SEARCH_LOADING$$", esc(ui["search_loading"]))
            .replace("$$SEARCH_NONE$$", esc(ui["search_none"]))
            .replace("$$SEARCH_DIALOG$$", esc(ui["search_dialog"]))
            .replace("$$SEARCH_PH$$", esc(ui["search_ph"]))
            .replace("$$SEARCH_HINT$$", esc(ui["search_hint"]))
            .replace("$$FOOTER1$$", ui["footer_p1"])
            .replace("$$FOOTER2$$", ui["footer_p2"])
            .replace("$$FOOTER_ENGINE$$", esc(ui["footer_engine"]))
            .replace("$$FOOTER_GAME$$", esc(ui["footer_game"]))
            .replace("$$FOOTER_SITE$$", esc(ui["footer_site"]))
            .replace("$$ABOUT_HREF$$", esc_code(rel_link(out_path, about_out_of(lang))))
            .replace("$$FOOTER_ABOUT$$", esc(ui["footer_about"]))
            .replace("$$REPO_ENGINE$$", SITE["repo_engine"])
            .replace("$$REPO_GAME$$", SITE["repo_game"])
            .replace("$$REPO_SITE$$", SITE["repo_site"])
            .replace("$$FOOTER_NOTE$$", ui["footer_note"])
            .replace("$$YEAR$$", str(SITE["year"])))
    return page


# --------------------------------------------------------------------------
# 内部锚点兼容 / anchor aliases
# --------------------------------------------------------------------------

def apply_anchor_aliases(md_name: str, html: str) -> str:
    for old, new in ANCHOR_ALIASES.get(md_name, {}).items():
        if 'id="%s"' % new in html:
            html = html.replace('id="%s"' % new,
                                'id="%s" data-alias="%s"' % (new, old), 1)
            html = html.replace(
                '<h2 id="%s"' % new,
                '<span id="%s" class="anchor-alias" aria-hidden="true"></span><h2 id="%s"'
                % (old, new), 1)
        else:
            print("  ! alias target missing: %s -> %s" % (md_name, new))
    return html


# --------------------------------------------------------------------------
# 构建 / build
# --------------------------------------------------------------------------

# 文档里出现的本机绝对路径 -> 公开仓库里的相对路径。
# 只改**渲染出来的 HTML**，docs/ 下的 Markdown 原文一字不动（原文是唯一事实来源）。
PUBLISHED_PATHS = [
    (r"[A-Za-z]:\\srceng\\hl2sb\\lua\\docs\\", "docs/"),
    (r"[A-Za-z]:\\srceng\\hl2sb\\lua\\", "lua/"),
    (r"[A-Za-z]:\\srceng\\hl2sb\\", "游戏内容仓库根目录/"),
    (r"[A-Za-z]:\\srceng\\", "引擎基础库目录/"),
    (r"[A-Za-z]:\\project\\source-engine\\", "引擎源码仓库/"),
    (r"[A-Za-z]:\\games\\garrysmod\\", "GMod 安装目录/"),
    (r"[A-Za-z]:\\project\\luacheck\\", "离线 Lua harness/"),
]

# 站内/站外链接重写：把页面里的 AGENTS.md 提及指到引擎仓库。
AGENTS_ENGINE_URL = "%s/blob/lua_playermodel_menu/AGENTS.md" % SITE["repo_engine"]


def rewrite_links(html: str) -> str:
    """把正文里被反引号包起来的 AGENTS.md 变成可点击的链接。"""
    if "AGENTS.md" in html:
        html = html.replace(
            "<code>AGENTS.md</code>",
            '<code><a href="%s" target="_blank" rel="noopener">AGENTS.md</a></code>'
            % AGENTS_ENGINE_URL)
    return html


def sanitize_paths(html: str) -> str:
    for pattern, repl in PUBLISHED_PATHS:
        html = re.sub(pattern, repl, html)
    return html

def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def strip_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end < 0:
        return {}, text
    meta = {}
    for line in text[4:end].splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"')
    return meta, text[end + 4:].lstrip("\n")


def build(out_dir: str) -> int:
    print("HL2SB docs build")
    print("  repo : %s" % REPO_ROOT)
    print("  out  : %s" % out_dir)

    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(os.path.join(out_dir, "assets"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "docs"), exist_ok=True)

    # 静态资源：assets/ 下的手写文件整体复制（style.css / app.js / favicon.svg，
    # 以及 docs/*.md 里用 `../assets/img/...` 引用的截图）。
    for base, _dirs, files in os.walk(ASSETS_DIR):
        rel = os.path.relpath(base, ASSETS_DIR)
        out_dir_assets = (os.path.join(out_dir, "assets") if rel == "."
                          else os.path.join(out_dir, "assets", rel))
        os.makedirs(out_dir_assets, exist_ok=True)
        for name in sorted(files):
            shutil.copy2(os.path.join(base, name),
                         os.path.join(out_dir_assets, name))

    search_indexes = {code: [] for code in LANG_CODES}
    pages_written = []
    skipped = []

    for page in PAGES:
        for code in LANG_CODES:
            src_name = page["src"].get(code)
            out_path = page["out"].get(code)
            if not src_name or not out_path:
                continue
            src_path = os.path.join(DOCS_DIR, *src_name.split("/"))
            if not os.path.isfile(src_path):
                # 某种语言还没翻译时不该让整个站点挂掉：跳过并记账，
                # 该页的切换器会自动退回对方首页（counterpart_out）。
                print("  ! missing source: docs/%s -> 跳过 %s" % (src_name, out_path))
                skipped.append(out_path)
                continue
            raw = read_text(src_path)
            meta, body_md = strip_frontmatter(raw)
            title = meta.get("title", page["text"][code])
            html, toc = render_markdown(body_md, title, UI[code])
            html = rewrite_links(html)
            html = sanitize_paths(html)
            # 锚点别名按**逻辑页**（中文源文件名）查，两种语言都补同一条 ——
            # 英文页里那句指向旧锚点 `#...--09-13` 的正文链接才不会断。
            html = apply_anchor_aliases(page["src"].get("zh", src_name), html)

            article = '<h1 class="doc-title">%s</h1>\n' % esc(title)
            article += build_toc(toc, code)
            article += html

            doc_body = (DOC_PAGE_TMPL
                        .replace("$$HOME_HREF$$", esc_code(rel_link(out_path, HOME_OF[code])))
                        .replace("$$CRUMB_HOME$$", esc(UI[code]["crumb_home"]))
                        .replace("$$GROUP$$", esc(group_label(page["group"], code)))
                        .replace("$$TITLE$$", esc(page["text"][code]))
                        .replace("$$SRC$$", src_name)
                        .replace("$$SRC_NOTE$$", esc(UI[code]["src_note"]))
                        .replace("$$SRC_NOTE_TAIL$$", esc(UI[code]["src_note_tail"]))
                        .replace("$$GENERATED$$", esc(UI[code]["generated"]))
                        .replace("$$BUILDDATE$$", BUILD_DATE)
                        .replace("$$EDIT_URL$$",
                                 "%s/blob/main/docs/%s" % (SITE["repo_site"], src_name))
                        .replace("$$EDIT_LABEL$$", esc(UI[code]["edit"]))
                        .replace("$$ARTICLE$$", article))
            out_file = os.path.join(out_dir, *out_path.split("/"))
            os.makedirs(os.path.dirname(out_file), exist_ok=True)
            with open(out_file, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(wrap_page(out_path, code, title, page["desc"][code], doc_body))
            pages_written.append(out_path)
            print("  + %-42s <- docs/%s" % (out_path, src_name))

            plain = re.sub(r"<[^>]+>", " ", html)
            plain = unescape(re.sub(r"\s+", " ", plain))
            if len(plain) > SEARCH_TEXT_LIMIT:
                # 截断只影响「正文命中」，标题与 headings 仍然全部可搜。
                print("  ! %s 正文 %d 字符 > 搜索上限 %d，尾部不会被搜到"
                      % (out_path, len(plain), SEARCH_TEXT_LIMIT))
            search_indexes[code].append({
                "url": out_path,
                "title": title,
                "group": group_label(page["group"], code),
                "lang": code,
                "headings": [t["text"] for t in toc],
                "text": plain[:SEARCH_TEXT_LIMIT],
            })

    # 首页：每种语言一份（中文在 dist/index.html，英文在 dist/en/index.html）
    for code in LANG_CODES:
        home_out = HOME_OF[code]
        home_body = HOME_TMPL[code].replace("$$STATUS$$", render_status_table(code))
        home_body = (home_body
                     # 首页到自己语言的 docs/ 目录：中文 dist/docs/、英文 dist/en/docs/
                     .replace("$$DOCPREFIX$$",
                              rel_link(home_out, "docs/" if code == "zh" else "en/docs/") + "/")
                     .replace("$$REPO_ENGINE$$", SITE["repo_engine"])
                     .replace("$$REPO_GAME$$", SITE["repo_game"])
                     .replace("$$REPO_SITE$$", SITE["repo_site"]))
        home_file = os.path.join(out_dir, *home_out.split("/"))
        os.makedirs(os.path.dirname(home_file), exist_ok=True)
        with open(home_file, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(wrap_page(home_out, code, SITE["name"][code],
                               SITE["tagline"][code], home_body))
        pages_written.append(home_out)
        print("  + %s" % home_out)

    # 搜索索引：每种语言一份（中文沿用老文件名，英文是 search-index.en.json）。
    # 页面通过 <div id="searchOverlay" data-index="..."> 告诉 app.js 自己该取哪一份。
    for code in LANG_CODES:
        idx_path = os.path.join(out_dir, *INDEX_OF[code].split("/"))
        os.makedirs(os.path.dirname(idx_path), exist_ok=True)
        with open(idx_path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(search_indexes[code], fh, ensure_ascii=False, indent=1)
        print("  + %-42s (%d 条)" % (INDEX_OF[code], len(search_indexes[code])))

    # .nojekyll：确保 GitHub Pages 不做 Jekyll 处理
    # （根目录与 docs/ 各放一份；Actions 部署时不需要，但保留着没有坏处）
    for name in (".nojekyll", "docs/.nojekyll", "en/.nojekyll"):
        path = os.path.join(out_dir, *name.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("")

    # 404：Pages 上未知路径回首页（根目录那份才是 GitHub Pages 会用的；
    # en/404.html 供直接命中英文路径时使用）
    for code in LANG_CODES:
        out_path = "404.html" if code == "zh" else "en/404.html"
        body = (UI[code]["notfound_body"]
                .replace("$$HOME$$", rel_link(out_path, HOME_OF[code]))
                .replace("$$INDEX$$", rel_link(out_path, PAGES[0]["out"][code])))
        path = os.path.join(out_dir, *out_path.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(wrap_page(out_path, code, UI[code]["notfound_title"],
                               UI[code]["notfound_desc"], body))
        pages_written.append(out_path)
        print("  + %s" % out_path)

    if skipped:
        print("  ! %d 页因为缺源文件被跳过：%s" % (len(skipped), ", ".join(skipped)))
    print("  = %d pages, %s search entries"
          % (len(pages_written),
             " + ".join("%s %d" % (c, len(search_indexes[c])) for c in LANG_CODES)))
    return 0


def group_label(gid: str, lang: str) -> str:
    """分组 id -> 该语言的显示名（侧栏、面包屑、搜索索引都用它）。"""
    for g, labels in GROUPS:
        if g == gid:
            return labels[lang]
    return gid


# 首页「当前状态」表（按语言）
STATUS_ROWS = {
    "zh": [
        ("GMod Lua 运行时", "✅", "Lua 5.4.6 + GLua 语法扩展；<code>lua_run_cl</code> / "
                                "<code>lua_dofile[_cl]</code> / <code>lua_dostring_cl</code> 可用"),
        ("<code>lua/autorun</code>", "✅", "客户端与服务端都加载，按文件名 A-Z 排序，语义与 GMod 一致"),
        ("Derma 面板", "✅", "22 个控件已注册（DFrame 为本 fork 的纯 Lua 实现，见指南第 2 节）"),
        ("皮肤 / skin", "✅", "<code>derma.DefineSkin</code> / <code>SkinHook</code>；"
                               "<code>derma.RefreshSkins</code> 未实现"),
        ("Spawnmenu / 生成菜单", "⚠️", "条目与分类可用，细节仍在推进"),
        ("Lua SWEP（GMod 武器）", "⚠️", "继承链与开火驱动已通，部分 GMod 独有全局仍需替换"),
        ("击杀播报 / killicon", "✅", "GMod 原版 <code>cl_deathnotice.lua</code> 移植版"),
        ("GMod 内容贴图（PNG）", "✅", "引擎侧直接解码 PNG 并在 <code>.vmt</code> 缺失时合成材质"),
        ("<code>derma.RefreshSkins</code> 等少数 API", "❌", "详见各文档的「已知差异」一节"),
    ],
    "en": [
        ("GMod Lua runtime", "✅", "Lua 5.4.6 + GLua syntax extensions; <code>lua_run_cl</code> / "
                                   "<code>lua_dofile[_cl]</code> / <code>lua_dostring_cl</code> work"),
        ("<code>lua/autorun</code>", "✅", "Loaded on client and server, sorted A-Z by file name — "
                                           "same semantics as GMod"),
        ("Derma panels", "✅", "22 controls registered (DFrame is this fork's own pure-Lua control, "
                               "see section 2 of the guide)"),
        ("Skins", "✅", "<code>derma.DefineSkin</code> / <code>SkinHook</code>; "
                       "<code>derma.RefreshSkins</code> is not implemented"),
        ("Spawnmenu", "⚠️", "Entries and categories work, details still in progress"),
        ("Lua SWEPs (GMod weapons)", "⚠️", "Inheritance chain and firing are wired up; some "
                                           "GMod-only globals still need replacing"),
        ("Kill feed / killicon", "✅", "A port of GMod's own <code>cl_deathnotice.lua</code>"),
        ("GMod content textures (PNG)", "✅", "The engine decodes PNG directly and synthesises a "
                                              "material when the <code>.vmt</code> is missing"),
        ("<code>derma.RefreshSkins</code> and a few other APIs", "❌",
         "See the \"known differences\" section of each document"),
    ],
}

STATUS_HEAD = {"zh": ("能力", "状态", "说明"), "en": ("Capability", "Status", "Notes")}


def render_status_table(lang: str) -> str:
    c1, c2, c3 = STATUS_HEAD[lang]
    out = ['<div class="table-wrap"><table><thead><tr><th>%s</th><th>%s</th><th>%s</th>'
           "</tr></thead><tbody>" % (esc(c1), esc(c2), esc(c3))]
    for name, state, note in STATUS_ROWS[lang]:
        out.append("<tr><td>%s</td><td class=\"state\">%s</td><td>%s</td></tr>"
                   % (name, state, note))
    out.append("</tbody></table></div>")
    return "".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the HL2SB docs site into dist/")
    ap.add_argument("--out", default=os.path.join(REPO_ROOT, "dist"))
    args = ap.parse_args()
    code = build(os.path.abspath(args.out))
    if code == 0:
        print("done.")
    return code


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    raise SystemExit(main())
