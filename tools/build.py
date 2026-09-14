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
    "name": "HL2SB 文档",
    "tagline": "Half-Life 2: Sandbox —— 跑 Garry's Mod Lua 的 Source 引擎分支",
    "repo_engine": "https://github.com/stephen-cusi/source-engine-mod",
    "repo_game": "https://github.com/stephen-cusi/hl2sb-gamefile",
    "repo_site": "https://github.com/stephen-cusi/hl2sb.github.io",
    "pages_url_personal": "https://stephen-cusi.github.io/hl2sb.github.io/",
    "pages_url_org": "https://hl2sb.github.io/",
    "year": date.today().year,
}

# 页面底部会写上生成日期（「最后更新」的近似值，CI 每次推送都会重建）。
BUILD_DATE = date.today().isoformat()

# 页面清单 / page manifest。
#   src  : docs/ 下的 markdown 源文件（单一事实来源）
#   out  : 生成到 dist/ 的目标路径
#   group: 侧栏分组
#   desc : 侧栏 / 索引页的一行说明
#   text : 侧栏 / 索引页显示的名字
PAGES = [
    {
        "src": "index.md",
        "out": "docs/index.html",
        "nav": "wiki",
        "group": "Wiki",
        "text": "Wiki 目录",
        "desc": "本站收录的全部文档一览。",
    },
    {
        "src": "derma_basic_guide.md",
        "out": "docs/derma_basic_guide.html",
        "nav": "wiki",
        "group": "Wiki",
        "text": "Derma 基础指南",
        "desc": "在 HL2SB 里写 GMod 风格 UI；与 GMod 不同的地方、本 fork 的坑。",
    },
    {
        "src": "gmod_lua_port_plan.md",
        "out": "docs/gmod_lua_port_plan.html",
        "nav": "wiki",
        "group": "Wiki",
        "text": "GMod Lua 移植计划与状态",
        "desc": "把 GMod 的 Lua 层搬进引擎的路线图、缺口映射与移植状态总表。",
    },
    {
        "src": "gmod_compat_layer.md",
        "out": "docs/gmod_compat_layer.html",
        "nav": "guide",
        "group": "使用文档",
        "text": "GMod Lua 兼容层",
        "desc": "兼容层由哪些部分组成、加载顺序、已知缺口。",
    },
    {
        "src": "build_and_run.md",
        "out": "docs/build_and_run.html",
        "nav": "guide",
        "group": "使用文档",
        "text": "构建与运行",
        "desc": "编译 client/server、部署 DLL、在哪里改 Lua。",
    },
    {
        "src": "about.md",
        "out": "docs/about.html",
        "nav": "about",
        "group": "关于",
        "text": "关于 / 版权",
        "desc": "项目来源、许可与致谢。",
    },
]

# 分组顺序 / group order for the sidebar.
GROUPS = ["Wiki", "使用文档", "关于"]

# 旧锚点兼容（文档内部已存在的 #锚点 链接，按 GFM 风格的 id 生成，
# 这里补一个 hidden alias，保证老链接不会失效）。
ANCHOR_ALIASES = {
    "gmod_lua_port_plan.md": {
        "9-移植状态与经验v3-增补2026-09-12--09-13":
            "9-移植状态与经验v3-增补2026-09-12-09-13",
    },
}

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
    def __init__(self):
        self.toc: list[dict] = []
        self._used_ids: set[str] = set()
        self._lines: list[str] = []
        self._i = 0
        self._para: list[str] = []
        self._body_h1_seen = 0
        self._doc_title = ""

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

    def _fence(self, m: re.Match) -> str:
        marker = m.group(1)
        lang = (m.group(2) or "").strip()
        self._i += 1
        buf: list[str] = []
        while self._i < len(self._lines):
            line = self._lines[self._i]
            if line.strip().startswith(marker[0] * 3):
                self._i += 1
                break
            buf.append(line)
            self._i += 1
        code = "\n".join(buf)
        label = ('<span class="code-lang">%s</span>' % esc_code(lang)) if lang else ""
        return ('<div class="codeblock">'
                '<div class="code-head">%s<button class="copy-btn" type="button" '
                'data-copy="1">复制</button></div>'
                '<pre><code%s>%s</code></pre></div>'
                % (label, (' class="language-%s"' % esc_code(lang)) if lang else "",
                   esc_code(code)))

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
        items: list[list[str]] = []
        current: list[str] = []
        while self._i < len(self._lines):
            line = self._lines[self._i]
            if not line.strip():
                break
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
    def _item_html(parts: list[str]) -> str:
        # 整条列表项的多个物理行要放在一起走 inline()：
        # 跨行的 **粗体** / `代码` 只在这种情况下才能正确配对。
        joined = esc("\n".join(parts)).replace("\n", _BR)
        return "<li>%s</li>" % inline(joined).replace(_BR, "<br>\n")


def render_markdown(text: str, doc_title: str = "") -> tuple[str, list[dict]]:
    r = MarkdownRenderer()
    return r.render(text, doc_title), r.toc

# --------------------------------------------------------------------------
# 模板 / templates
# --------------------------------------------------------------------------

PAGE_TMPL = """<!DOCTYPE html>
<html lang="zh-CN" data-theme="auto">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$$TITLE$$ · $$SITENAME$$</title>
<meta name="description" content="$$DESC$$">
<link rel="stylesheet" href="$$ROOT$$assets/style.css">
<link rel="icon" type="image/svg+xml" href="$$ROOT$$assets/favicon.svg">
<script>(function(){try{var t=localStorage.getItem('hl2sb-theme');if(t==='dark'||t==='light'){document.documentElement.setAttribute('data-theme',t);}}catch(e){}})();</script>
</head>
<body>
<a class="skip-link" href="#content">跳到正文</a>
<header class="topbar">
  <button class="icon-btn nav-toggle" type="button" aria-label="切换导航" aria-expanded="false">☰</button>
  <a class="brand" href="$$ROOT$$index.html">
    <span class="brand-mark">HL2<em>SB</em></span>
    <span class="brand-sub">文档站</span>
  </a>
  <div class="topbar-spacer"></div>
  <button class="search-open icon-btn" type="button" aria-label="搜索">🔍<span class="search-open-text">搜索</span></button>
  <button class="icon-btn theme-toggle" type="button" aria-label="切换主题"><span class="theme-icon">◐</span></button>
</header>
<div class="layout">
  <aside class="sidebar" id="sidebar">
$$SIDEBAR$$
  </aside>
  <main class="content" id="content">
$$BODY$$
  </main>
</div>
<div class="search-overlay" id="searchOverlay" hidden>
  <div class="search-panel" role="dialog" aria-modal="true" aria-label="站内搜索">
    <input type="search" id="searchInput" placeholder="搜索文档…（标题与正文）" autocomplete="off">
    <div class="search-results" id="searchResults"><p class="muted">输入关键词开始搜索。</p></div>
    <div class="search-hint">↑↓ 选择 · Enter 打开 · Esc 关闭</div>
  </div>
</div>
<footer class="footer">
  <div class="footer-inner">
    <p><strong>HL2SB</strong> —— Half-Life 2: Sandbox，基于 Source SDK 2013 / nillerusr source-engine 的引擎分支，运行 Garry's Mod 的 Lua。</p>
    <p class="muted">引擎源码与 SDK 代码仅供非商业用途；Half-Life、Source、Garry's Mod 及相关商标归 Valve / Facepunch 所有。本站文档除特别说明外与上游保持一致。</p>
    <p class="muted">
      <a href="$$REPO_ENGINE$$" target="_blank" rel="noopener">引擎仓库</a> ·
      <a href="$$REPO_GAME$$" target="_blank" rel="noopener">游戏内容仓库</a> ·
      <a href="$$REPO_SITE$$" target="_blank" rel="noopener">本站源码</a> ·
      <a href="$$ROOT$$docs/about.html">关于 / 版权</a>
    </p>
    <p class="muted small">© $$YEAR$$ HL2SB 贡献者 · 由 <code>tools/build.py</code> 预渲染为静态 HTML（无 CDN、无外部依赖）</p>
  </div>
</footer>
<script src="$$ROOT$$assets/app.js" defer></script>
</body>
</html>
"""

DOC_PAGE_TMPL = """<nav class="crumbs"><a href="$$ROOT$$index.html">首页</a><span class="sep">/</span><span>$$GROUP$$</span><span class="sep">/</span><span class="current">$$TITLE$$</span></nav>
<article class="doc">
$$ARTICLE$$
</article>
<div class="page-foot">
  <p class="muted">源文件：<code>docs/$$SRC$$</code> · 本页由该 Markdown 预渲染生成，原文是唯一事实来源 · 生成于 $$BUILDDATE$$</p>
  <p><a href="$$EDIT_URL$$" target="_blank" rel="noopener">在 GitHub 上查看 / 编辑这一页 ↗</a></p>
</div>
"""

HOME_TMPL = """<section class="hero">
  <h1>HL2SB 文档站</h1>
  <p class="lead">HL2SB（<strong>Half-Life 2: Sandbox</strong>）是一个 Source 引擎分支，目标是在 Source SDK 2013 的引擎上<strong>原样运行 Garry's Mod 的 Lua</strong> —— Derma 面板、Spawnmenu、SWEP、killicon……尽量做到 GMod 的脚本一行不改就能跑。</p>
  <div class="hero-actions">
    <a class="btn primary" href="docs/derma_basic_guide.html">读 Derma 基础指南</a>
    <a class="btn" href="docs/build_and_run.html">自己编译运行</a>
    <a class="btn" href="docs/index.html">全部文档</a>
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
    <div class="card"><h3>Derma / VGUI</h3><p>GMod 的 <code>vgui.Create</code>、<code>DFrame</code>、<code>DPanel</code>、<code>DButton</code>、<code>DListView</code> … 面板与皮肤系统，已按 GMod 的 Lua 实现接上。</p><p class="muted small">详见 <a href="docs/derma_basic_guide.html">Derma 基础指南</a></p></div>
    <div class="card"><h3>GMod 兼容层</h3><p><code>hook</code>、<code>surface</code>、<code>Color</code>、<code>draw</code>、<code>killicon</code>、<code>file</code>、<code>vgui</code> 等库按 GMod 的签名补齐，缺的补在引擎 C++ 侧。</p><p class="muted small">详见 <a href="docs/gmod_compat_layer.html">GMod Lua 兼容层</a></p></div>
    <div class="card"><h3>Lua SWEP / 武器</h3><p>引擎按 GMod 的继承链驱动 Lua 武器：<code>PrimaryAttack</code> / <code>SecondaryAttack</code> / <code>Deploy</code>，含弹药、模型、槽位数据。</p><p class="muted small">详见 <a href="docs/gmod_lua_port_plan.html">移植计划与状态</a></p></div>
    <div class="card"><h3>HUD / 击杀播报</h3><p>GMod 原版 <code>cl_deathnotice.lua</code> 移植版：killicon 图标、淡出、队伍配色；另有 GMod 内容贴图（PNG）直读。</p><p class="muted small">详见 <a href="docs/gmod_lua_port_plan.html">移植计划与状态</a></p></div>
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
  <p class="callout"><strong>提示：</strong>中国用户常从零开始 —— 建议先读 <a href="docs/build_and_run.html">构建与运行</a>，再读 <a href="docs/derma_basic_guide.html">Derma 基础指南</a>。</p>
</section>

<section class="prose">
  <h2>当前状态</h2>
  <p class="muted">这一节随开发推进更新；细节与逐项勾选见 <a href="docs/gmod_lua_port_plan.html">GMod Lua 移植计划与状态</a>。</p>
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
"""

SEARCH_HINT = '按 <kbd>/</kbd> 或 <kbd>Ctrl</kbd>+<kbd>K</kbd> 搜索'


# --------------------------------------------------------------------------
# 站点骨架 / sidebar
# --------------------------------------------------------------------------

NAV_SNIPPET = """
  <form class="side-search" role="search" onsubmit="return false;">
    <input type="search" id="sideSearch" placeholder="搜索文档…" aria-label="搜索文档">
  </form>
"""


def build_sidebar(current_out: str, depth: int) -> str:
    root = "../" * depth
    parts = [NAV_SNIPPET]
    parts.append('<nav class="side-nav">')
    for group in GROUPS:
        entries = [p for p in PAGES if p["group"] == group]
        if not entries:
            continue
        parts.append('<div class="side-group"><div class="side-group-title">%s</div><ul>'
                     % esc(group))
        for p in entries:
            active = ""
            if p["out"] == current_out:
                active = ' class="active" aria-current="page"'
            parts.append('<li><a href="%s%s"%s>%s</a></li>'
                         % (root, p["out"], active, esc(p["text"])))
        parts.append("</ul></div>")
    parts.append('<div class="side-group"><div class="side-group-title">项目</div><ul>')
    parts.append('<li><a href="%sindex.html">首页</a></li>' % root)
    parts.append('<li><a href="%sdocs/build_and_run.html">构建与运行</a></li>' % root)
    parts.append('<li><a href="%sdocs/about.html">关于 / 版权</a></li>' % root)
    parts.append("</ul></div>")
    parts.append("</nav>")
    parts.append('<div class="side-foot small">%s</div>' % SEARCH_HINT)
    return "\n".join(parts)


def rel_root(out_path: str) -> str:
    depth = out_path.count("/")
    return "../" * depth


def build_toc(toc: list[dict]) -> str:
    items = [t for t in toc if t["level"] in (2, 3)]
    if not items:
        return ""
    out = ['<details class="toc" open><summary>本页目录</summary><ul>']
    for t in items:
        cls = ' class="lv3"' if t["level"] == 3 else ""
        out.append('<li%s><a href="#%s">%s</a></li>' % (cls, t["id"], esc(t["text"])))
    out.append("</ul></details>")
    return "\n".join(out)


def wrap_page(out_path: str, title: str, desc: str, body: str) -> str:
    root = rel_root(out_path)
    page = (PAGE_TMPL
            .replace("$$TITLE$$", title)
            .replace("$$SITENAME$$", SITE["name"])
            .replace("$$DESC$$", desc)
            .replace("$$ROOT$$", root)
            .replace("$$SIDEBAR$$", build_sidebar(out_path, out_path.count("/")))
            .replace("$$BODY$$", body)
            .replace("$$REPO_ENGINE$$", SITE["repo_engine"])
            .replace("$$REPO_GAME$$", SITE["repo_game"])
            .replace("$$REPO_SITE$$", SITE["repo_site"])
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

    # 静态资源
    for name in ("style.css", "app.js", "favicon.svg"):
        shutil.copy2(os.path.join(ASSETS_DIR, name),
                     os.path.join(out_dir, "assets", name))

    search_index = []
    pages_written = []

    for page in PAGES:
        src_path = os.path.join(DOCS_DIR, page["src"])
        if not os.path.isfile(src_path):
            print("  ! missing source: %s" % src_path)
            return 2
        raw = read_text(src_path)
        meta, body_md = strip_frontmatter(raw)
        title = meta.get("title", page["text"])
        html, toc = render_markdown(body_md, title)
        html = rewrite_links(html)
        html = sanitize_paths(html)
        html = apply_anchor_aliases(page["src"], html)

        root = rel_root(page["out"])
        article = '<h1 class="doc-title">%s</h1>\n' % esc(title)
        article += build_toc(toc)
        article += html

        doc_body = (DOC_PAGE_TMPL
                    .replace("$$ROOT$$", root)
                    .replace("$$GROUP$$", esc(page["group"]))
                    .replace("$$TITLE$$", esc(page["text"]))
                    .replace("$$SRC$$", page["src"])
                    .replace("$$BUILDDATE$$", BUILD_DATE)
                    .replace("$$EDIT_URL$$",
                             "%s/blob/main/docs/%s" % (SITE["repo_site"], page["src"]))
                    .replace("$$ARTICLE$$", article))
        out_file = os.path.join(out_dir, *page["out"].split("/"))
        os.makedirs(os.path.dirname(out_file), exist_ok=True)
        with open(out_file, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(wrap_page(page["out"], title, page["desc"], doc_body))
        pages_written.append(page["out"])
        print("  + %-36s <- docs/%s" % (page["out"], page["src"]))

        plain = re.sub(r"<[^>]+>", " ", html)
        plain = unescape(re.sub(r"\s+", " ", plain))
        search_index.append({
            "url": page["out"],
            "title": title,
            "group": page["group"],
            "headings": [t["text"] for t in toc],
            "text": plain[:6000],
        })

    # 首页
    status = render_status_table()
    home_body = HOME_TMPL.replace("$$STATUS$$", status)
    home_body = (home_body
                 .replace("$$REPO_ENGINE$$", SITE["repo_engine"])
                 .replace("$$REPO_GAME$$", SITE["repo_game"])
                 .replace("$$REPO_SITE$$", SITE["repo_site"]))
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(wrap_page("index.html", "HL2SB 文档站", SITE["tagline"], home_body))
    pages_written.append("index.html")
    print("  + index.html")

    # 搜索索引
    with open(os.path.join(out_dir, "assets", "search-index.json"), "w",
              encoding="utf-8", newline="\n") as fh:
        json.dump(search_index, fh, ensure_ascii=False, indent=1)

    # .nojekyll：确保 GitHub Pages 不做 Jekyll 处理
    with open(os.path.join(out_dir, ".nojekyll"), "w", encoding="utf-8") as fh:
        fh.write("")

    # 404：Pages 上未知路径回首页
    with open(os.path.join(out_dir, "404.html"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(wrap_page("404.html", "页面不存在",
                           "找不到这个页面",
                           '<div class="prose"><h1>404</h1>'
                           '<p>这个页面不存在。回到 <a href="index.html">首页</a> '
                           '或 <a href="docs/index.html">文档目录</a>。</p></div>'))
    pages_written.append("404.html")

    print("  = %d pages, %d search entries" % (len(pages_written), len(search_index)))
    return 0


def render_status_table() -> str:
    rows = [
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
    ]
    out = ['<div class="table-wrap"><table><thead><tr><th>能力</th><th>状态</th><th>说明</th>'
           "</tr></thead><tbody>"]
    for name, state, note in rows:
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
