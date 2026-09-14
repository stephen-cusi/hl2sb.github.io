---
title: GMod Lua compatibility layer
---

# GMod Lua compatibility layer

HL2SB's goal is to **take GMod's Lua as-is and change as few lines as possible**. So the default
answer to a missing function is not to write a shim in Lua, but to **add bindings on the engine
C++ side** — this repo is the complete engine source, `surface.*` maps to vguimatsurface,
`render/cam.*` maps to materialsystem, `file.*` maps to filesystem, `net.*` maps to the engine's
network channel…… so nearly every item can land in some module and be implemented there.

Lua is only changed when GMod hard-codes "something that does not physically exist in HL2SB"
(for example GMod's network event names), and such changes must be marked with a comment at the
top of the file.

## 1. Runtime environment (differences from GMod) {#1-运行时环境和-gmod-的差异}

| Dimension | GMod | HL2SB |
|---|---|---|
| Lua version | LuaJIT 2.0 (GLua) | **Lua 5.4.6** + GLua syntax extensions |
| Syntax extensions | `continue` / `!` / `!=` / `&&` / `||` / `//` / `/* */` | ✅ Also supported (`module()` / `package.seeall` were backported in the compatibility layer too) |
| Native libraries | ships its own `utf8.lua` | native `utf8` library |
| `Color` | table, `.r/.g/.b/.a` are fields | likewise a table + numeric fields (the capitalized methods `col:GetR()` exist too) |
| Module mechanism | `module("x")` + global `x.*` | identical |
| File encoding | anything goes | **UTF-8 without BOM** (`resource/*.txt` is the exception; localization tokens need UTF-16LE+BOM) |

⚠️ The intuition of "Lua 5.1 semantics" is often wrong here: for example 5.1's `lua_tointeger`
truncates the fraction, while 5.4's strict integer check throws an error outright. The engine side
has already implemented compatibility following the 5.1 behavior, so when writing new scripts just
follow the GMod way.

## 2. The three-layer structure of the compatibility layer {#2-兼容层的三层结构}

### Layer 1: engine-side C++ bindings {#第一层引擎侧的-c-绑定}

The engine registers the globals and library methods GMod needs. The point of this layer existing
is to let GMod's original files run directly:

* **Drawing / UI**: `surface.*` (including the GMod-named `SetDrawColor` / `DrawRect` / `DrawText` /
  `SetTexture` / `SetMaterial` / `CreateFont` / `DrawTexturedRect` etc.), `vgui.*`,
  `derma.*`, `draw.*` (rounded corners, text alignment constants).
* **General**: `Color`, `hook`, `concommand`, `cvars` (the `ConVar` / `GetConVar` family),
  `gameevent`, `file` (GMod's `extensions/file.lua` rewrites `file.*` using this handle).
* **Engine globals**: entry points that GMod scripts call unconditionally, such as
  `GetConVar_Internal`, `vgui.GetAll()`.

### Layer 2: Lua-side extensions and compatibility modules {#第二层lua-侧的扩展与兼容模块}

GMod-style libraries and shims, loaded under `lua/includes/`:

* `extensions/` — `gmod_surface.lua` (GMod's `surface` name layer), `gmod_vgui.lua`
  (Derma default fonts `DermaDefault` / `DermaDefaultBold` / `DermaLarge` etc.).
* `modules/` — `hook.lua`, `killicon.lua`, `gmod_compatibility/` (enum aliases:
  `KEY_*`, `DOCK`, `TEXT_ALIGN_*` and the like, because names like `IN_*` / `KEY_CONTROL_LEFT`
  are what the engine exposes).
* `derma/` — control definitions, `derma.lua`, `skins/`.

### Layer 3: GMod's original files {#第三层gmod-的原版文件}

Files that ship with GMod are carried over as-is as far as possible: Derma controls, skins,
`derma/init.lua`, the kill feed `cl_deathnotice.lua` and so on. The localized spots are written in
file header comments, and there are commonly only a few kinds:

* **Event source**: GMod receives usermessages with `net.Receive`, HL2SB changes this to hook events;
* **Load timing**: `lua/game/client` loads before the gamemode, so `_GAMEMODE` may be nil when loading;
* **Name differences**: a GMod constant may live under another table in HL2SB (for example `draw.TEXT_ALIGN_RIGHT`).

## 3. Load order {#3-加载顺序}

Every map load (client `LevelInitPreEntity` / server DLL load) follows this order:

```
lua/includes/extensions      ← GMod-style extension libraries (must come before includes/init.lua)
lua/includes/modules         ← hook / killicon / various modules
lua/game/shared
lua/game/client              ← client scripts (the server does not load this directory)
lua/autorun/*.lua            ← non-recursive, by filename A-Z
lua/autorun/client|server/** ← recursive, by filename A-Z
luasrc_LoadWeapons()         ← weapons
luasrc_LoadGamemode()        ← gamemode last
```

Key points:

* `lua/includes/init.lua` is loaded **by name** (not by scanning the directory), it `include`s
  `util.lua` and `vgui_base.lua` itself. Adding new files to the top level of `lua/includes/`
  requires listing them in `init.lua`.
* The server also loads `lua/includes/init.lua`, so **client-only things must be guarded with
  `if ( CLIENT )`**.
* `lua/autorun/` is the same as GMod: the `/server` and `/client` subdirectories are recursed
  separately, and execution is **guaranteed to be sorted by filename A-Z**.

## 4. Known gaps / differences from GMod {#4-已知缺口-与-gmod-的差异}

| Item | Status |
|---|---|
| `derma.RefreshSkins()` | ❌ Not implemented (only `DefineSkin` / `SkinHook` / `SetSkin`) |
| Child panels are not drawn after overriding a container panel's `Paint` | ⚠️ Known issue, not fixed |
| Lua dispatch for some controls (`DCheckBox` / `DTextEntry` / `DPropertySheet` …) | ⚠️ still being filled in |
| Argument semantics of a few bindings such as `surface.DrawTexturedRectRotated` | ✅ Already aligned with GMod; note that `x, y` is the rectangle center and `rot` is in degrees |
| Argument order of `CreateConVar`'s min/max | ⚠️ Not exactly consistent with GMod; it does not crash, but no range clamping is done |
| GMod-only globals such as `Entity` | ❌ Does not exist, replace it when porting addons |
| `debug.Trace()` | ❌ GMod has it, HL2SB does not |

The per-item root causes and the verified in-game process are in
[Port plan and status](gmod_lua_port_plan.html) and
[Derma basic guide](derma_basic_guide.html).

## 5. Advice for addon authors {#5-给插件作者的建议}

* Write it the GMod way first; when it reports `attempt to call a nil value (method 'X')`, first
  decide whether this control is an **engine class** or a **pure Lua control**, then decide where
  to patch.
* Using `hook.Add` (the GMod spelling) rather than the engine-lineage `hook.add` is also fine,
  both work; but **do not both register a hook and define a gamemode method for the same event**,
  because that dispatches twice.
* A script that errors is unregistered by the hook system, so inside HUD paint hooks it is
  recommended to wrap with `pcall`, otherwise a single exception goes permanently silent.
* After changing Lua, remember to re-enter the map (or hot-reload with `lua_dofile_cl`); after
  changing C++ you must fully restart the game.
