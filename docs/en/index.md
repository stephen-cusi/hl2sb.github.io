---
title: Wiki index
---

# Wiki index

This site collects every document the HL2SB project has. Each one keeps its original Markdown
(in the `docs/` folder) and is **pre-rendered** to static HTML by `tools/build.py` — no CDN, no
runtime dependencies, readable offline too.

## Getting started {#入门}

| Document | Contents |
|---|---|
| [Build & run](build_and_run.html) | Building the engine's client / server, where the DLLs go, why editing Lua does not always need a rebuild, and what the GMod Lua compatibility layer looks like. |
| [Derma basics](derma_basic_guide.html) | Writing GMod-style UI in HL2SB. Against GMod's official Derma Basic Guide it documents **only what differs and this fork's gotchas**. |
| [GMod Lua compatibility layer](gmod_compat_layer.html) | What the compatibility layer is made of (engine bindings + Lua extensions + GMod's own files), its load order, and the known gaps. |

## API reference {#api-参考}

| Document | Contents |
|---|---|
| [file.Find](file_find.html) | Listing the files and directories in a folder. **Implemented** (engine-side C++ binding), with pathID support, `sorting` values and the item-by-item differences from GMod. |

## Development & status {#开发与状态}

| Document | Contents |
|---|---|
| [GMod Lua port plan & status](gmod_lua_port_plan.html) | The roadmap for moving GMod's Lua layer into the engine: environment differences, gap → engine landing points, execution order, plus the latest port status table and lessons learned. |

## About {#关于}

| Document | Contents |
|---|---|
| [About / license](about.html) | Project origin, license and credits. |

---

## The things people look up most {#文档里最常被查的几件事}

* **Console commands**: `lua_run_cl <one line of code>` / `lua_dofile[_cl] <file>` /
  `lua_dostring_cl <string>` — the argument is "everything left on the line", so
  **never paste several lines at once**. See
  [Derma basics §0](derma_basic_guide.html#0-运行环境和-gmod-不一样的第一件事).
* **DFrame is this fork's own pure-Lua control**, so its content has to start at `y = 24`:
  [§2](derma_basic_guide.html#2-hl2sb-的-dframe-是纯-lua-控件不是引擎的-c-frame).
* **Overriding the `Paint` of a container panel stops the whole subtree from drawing**:
  [§3](derma_basic_guide.html#3-覆盖-paint-的坑本仓库实测).
* **Do not shadow a scheme font with `surface.CreateFont("Marlett", ...)`**:
  [§4](derma_basic_guide.html#4-字体-不要遮蔽-scheme-里的字体marlett-那一课的完整版).
* **DLLs are loaded only at process start**, so a C++ change needs a full restart:
  [Build & run](build_and_run.html).
