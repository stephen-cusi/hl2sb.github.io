---
title: Wiki 目录
---

# Wiki 目录

本站收录 HL2SB 项目现有的全部文档，每篇都保留原始 Markdown（在 `docs/` 文件夹里），
页面由 `tools/build.py` **预渲染**成静态 HTML —— 没有 CDN、没有运行时依赖，离线也能看。

## 入门

| 文档 | 内容 |
|---|---|
| [构建与运行](build_and_run.html) | 编译引擎的 client / server，部署 DLL 到哪里，改 Lua 为什么不一定要重编，GMod Lua 兼容层大致长什么样。 |
| [Derma 基础指南](derma_basic_guide.html) | 在 HL2SB 里写 GMod 风格的 UI。对照 GMod 官方 Derma Basic Guide，**只写不一样的地方和这个 fork 的坑**。 |
| [GMod Lua 兼容层](gmod_compat_layer.html) | 兼容层由哪些部分组成（引擎绑定 + Lua 扩展 + GMod 原版文件）、加载顺序、已知缺口。 |

## 开发与状态

| 文档 | 内容 |
|---|---|
| [GMod Lua 移植计划与状态](gmod_lua_port_plan.html) | 把 GMod 的 Lua 层搬进引擎的路线图：环境差异、缺口 → 引擎落点映射、执行顺序，以及最新的移植状态总表与经验。 |

## 关于

| 文档 | 内容 |
|---|---|
| [关于 / 版权](about.html) | 项目来源、许可与致谢。 |

---

## 文档里最常被查的几件事

* **控制台命令**：`lua_run_cl <一行代码>` / `lua_dofile[_cl] <文件>` / `lua_dostring_cl <字符串>` ——
  参数是「本行剩余的全部内容」，**不要一次粘多行**。见 [Derma 基础指南 §0](derma_basic_guide.html#0-运行环境和-gmod-不一样的第一件事)。
* **DFrame 是本 fork 的纯 Lua 控件**，内容要放在 `y = 24` 起：
  [§2](derma_basic_guide.html#2-hl2sb-的-dframe-是纯-lua-控件不是引擎的-c-frame)。
* **覆盖容器面板的 `Paint` 会让整棵子树不绘制**：
  [§3](derma_basic_guide.html#3-覆盖-paint-的坑本仓库实测)。
* **不要用 `surface.CreateFont("Marlett", ...)` 遮蔽方案字体**：
  [§4](derma_basic_guide.html#4-字体不要遮蔽-scheme-里的字体marlett-那一课的完整版)。
* **DLL 只在游戏启动时加载**，改完 C++ 必须完全重启：
  [构建与运行](build_and_run.html)。
