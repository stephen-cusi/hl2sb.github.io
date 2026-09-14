---
title: 关于 / 版权
---

# 关于 / 版权

## HL2SB 是什么

**HL2SB（Half-Life 2: Sandbox）** 是一个 Source 引擎分支，目标是让 **Garry's Mod 的 Lua
在 Source SDK 2013 的引擎上原样运行** —— Derma 面板、Spawnmenu、Lua SWEP、killicon、
GMod 风格的内容管线，尽量做到 GMod 的脚本一行不改。

它基于 nillerusr 的 source-engine（Source SDK 2013 的社区移植分支），
再加上 HL2SB 自己的引擎改动与 GMod 兼容层。

## 仓库

| 仓库 | 内容 |
|---|---|
| [source-engine-mod](https://github.com/stephen-cusi/source-engine-mod) | 引擎源码（C++）。工作分支 `lua_playermodel_menu` |
| [hl2sb-gamefile](https://github.com/stephen-cusi/hl2sb-gamefile) | 游戏内容：`cfg` / `resource` / `lua` / `materials`(文本) / `gamemodes` / `gameinfo.txt`。只收录可编辑的文本资源 |
| [hl2sb.github.io](https://github.com/stephen-cusi/hl2sb.github.io) | 本站：文档的 Markdown 源文件 + 静态生成器 |

## 本站怎么构建

* 所有文档都是仓库里 `docs/` 下的 **Markdown 文件**，它们是唯一的事实来源；
* `tools/build.py`（纯 Python 标准库，零依赖）把它们**预渲染**成 `dist/` 里的静态 HTML；
* 站内所有链接与资源都是**相对路径**，所以放在 `https://<user>.github.io/hl2sb.github.io/`
  或 `https://hl2sb.github.io/` 都能正常工作；
* 没有 CDN、没有外部字体、没有前端框架 —— 只有手写的 CSS 和一小段原生 JavaScript。

本地预览：

```powershell
python tools/build.py                     # 生成 dist/
python -m http.server 8080 --directory dist
```

## 许可与致谢

* **Source SDK 2013 / Source 引擎代码**：按 Valve 的 Source SDK 许可，**仅供非商业用途**。
  本站内容与源码同样受此限制。
* **Half-Life、Source、Steam** 是 Valve Corporation 的商标；
  **Garry's Mod** 及其 Wiki 内容是 Facepunch Studios 的成果。本站的 Derma 与移植文档是对
  上游文档的对照与补充，GMod 原版文件（`cl_deathnotice.lua`、Derma 控件、皮肤等）
  的版权归其作者所有。
* 引擎分支来自 [nillerusr/source-engine](https://github.com/nillerusr/source-engine)（Source SDK 2013 移植）。
* 文档视觉风格参考 [Garry's Mod Wiki](https://wiki.facepunch.com/gmod/)。

如有版权问题或需要下架某些内容，请在仓库里开 issue。
