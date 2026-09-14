---
title: Build & run
---

# Build & run

This page is for **people using this branch**: how to compile the engine, where the DLLs go, when the game must be restarted,
and roughly how GMod's Lua compatibility layer is put together.

> The target is Windows + MSVC. The build goes through the project's waf scripts; the source tree is the complete engine source,
> not just an SDK shell — so missing GMod functions can really be added on the engine side.

## 0. You need two repos {#0-你需要两个仓库}

| Repo | What it is |
|---|---|
| [source-engine-mod](https://github.com/stephen-cusi/source-engine-mod) | **engine source** (nillerusr source-engine + HL2SB changes), branch `lua_playermodel_menu` |
| [hl2sb-gamefile](https://github.com/stephen-cusi/hl2sb-gamefile) | **game content**: `cfg` / `resource` / `lua` / `materials` (text only) / `gamemodes` / `gameinfo.txt`. Only editable text assets are included; binary assets (models, textures, sounds) do not go into version control |

At deploy time their relationship is: **the engine builds the DLL → the DLL goes into the game content's `bin\` → the engine launcher starts the game content directory**.

## 1. Compiling {#1-编译}

Run this in the engine source directory (note that you must use `waf.bat`, which sets up UTF-8 / the code page):

```powershell
cd <engine source directory>
cmd /c ".\waf.bat build --targets=client,server"   # builds client.dll + server.dll in one go
```

You can also build them separately, or build GameUI:

```powershell
cmd /c ".\waf.bat build --targets=client"
cmd /c ".\waf.bat build --targets=server"
cmd /c ".\waf.bat build --targets=GameUI"
```

**Do not run `python .\waf build` directly**: when MSVC outputs Chinese, Python reports `UnicodeEncodeError: 'gbk' codec ...`.
`waf.bat` sets `PYTHONIOENCODING=UTF-8` and the code page, so using it handles this correctly.

The artifacts are in:

* `build\game\client\client.dll`
* `build\game\server\server.dll`
* `build\gameui\GameUI.dll`

## 2. Deploying: where the DLLs go {#2-部署dll-放到哪里}

This is the place that is easiest to get wrong, because **there are two `bin` directories** with completely different roles:

| Artifact | Copy to | Notes |
|---|---|---|
| `build\game\client\client.dll` | `<game content>\bin\client.dll` | the mod's own client |
| `build\game\server\server.dll` | `<game content>\bin\server.dll` | the mod's own server |
| `build\gameui\GameUI.dll` | `<engine base library dir>\GameUI.dll` | replaces the engine's UI module (**not** into the mod's `bin`) |

⚠️ **Never put the mod's `client.dll` / `server.dll` into the engine base libraries directory** (the one that already has
`engine.dll` / `tier0.dll` / `materialsystem.dll` / `vgui2.dll`). That is the platform library shared by all mods;
putting them there pollutes it, and may also make the game load from the wrong location.

Before deploying, first make sure the game is not running, otherwise the DLLs are in use and the copy will fail.

## 3. When the game must be restarted {#3-什么时候要重启游戏}

| What you changed | How it takes effect |
|---|---|
| C++ (engine, client, server) | **the game must be fully exited and started again**. DLLs are only loaded at process start; changing maps does not count |
| gameinfo / cfg | restart the game (some cvars can be changed directly in the console) |
| Lua scripts | re-enter the map; or hot-load client scripts directly with the console `lua_dofile_cl <path>` |
| materials / models | re-enter the map |

Lua scripts are read when a map is loaded; `.lua` files must be **UTF-8 without BOM**.

## 4. Trying Lua in-game {#4-在游戏里试-lua}

HL2SB's console commands (**not** GMod's `lua_run`):

| Command | Effect |
|---|---|
| `lua_run_cl <one line of code>` | executes on the client. The argument is **everything remaining on the line**, so one command can only hold one statement; join several statements onto one line with `;` |
| `lua_dofile[_cl] <file>` | runs a server / client Lua file. The path is **relative to the `lua/` root**, **must include `.lua`**, and does not take a `lua/` prefix |
| `lua_dostring_cl <string>` | same as `lua_run_cl` |

⚠️ Do not paste multiple lines of commands at once — the console will treat the remaining lines as arguments of the first command.
Before you have entered a map, `lua_run_cl` reports `Lua is not initialized yet`.

To write your first UI window see **[Derma Basic Guide](derma_basic_guide.html)**.

## 5. What GMod's Lua compatibility layer looks like {#5-gmod-的-lua-兼容层长什么样}

The Lua in the engine is **Lua 5.4.6** (not GMod's LuaJIT, and not 5.1), and it additionally carries GLua's syntax extensions,
so the constructs used in GMod scripts such as `continue`, `!` / `!=`, `&&` / `||`, and `//` comments run directly;
`module()` / `package.seeall` are also given a compatibility layer. The compatibility layer consists of three layers:

1. **C++ bindings on the engine side** — missing GMod functions are filled in on the engine side as much as possible, rather than shimmed in Lua.
   For example `surface.*` (drawing, fonts), `vgui.*`, `file.*`, `ConVar` / `GetConVar`, `Color`,
   and GMod's `vgui.GetAll()`. This way GMod's original files can be copied over directory by directory, changing as few lines as possible.
2. **Lua-side extension and compatibility modules** — GMod-style `surface` / `draw` / `hook` / `util` / `killicon` /
   `derma` / `vgui` libraries, plus enum aliases (such as `KEY_*`, `DOCK`).
3. **GMod's original files** — skins, Derma controls, `derma/init.lua`, kill notifications and so on come directly from GMod,
   with the localized places marked by comments at the head of the file.

**Load order** (executed on every map load):

```
lua/includes/extensions      ← GMod-style extension libraries
lua/includes/modules         ← hook / killicon / various modules
lua/game/shared
lua/game/client              ← client scripts (the server does not load this directory)
...finally  gamemode
```

Afterwards `lua/autorun/` is also run in GMod's order: first `lua/autorun/*.lua` (not recursive),
then `lua/autorun/client/**` or `lua/autorun/server/**` (recursive), **sorted by filename A-Z**.

Whichever script you wrote, which directory to put it in, and whether it is client or server — check against the tables in
[GMod Lua compatibility layer](gmod_compat_layer.html) and
[Port plan and status](gmod_lua_port_plan.html).

## 6. Known differences (read here before you hit them) {#6-已知差异踩之前先看这里}

| Item | Status |
|---|---|
| Some controls in `lua/derma` (`DCheckBox` / `DTextEntry` / `DPropertySheet` …) | ⚠️ the underlying dispatch is still being filled in; they draw, but interaction may not be complete |
| `derma.RefreshSkins()` | ❌ not implemented; after changing skins you must rebuild the window |
| Overriding the `Paint` of a container panel | ⚠️ makes child panels not draw, see [Guide §3](derma_basic_guide.html#3-覆盖-paint-的坑本仓库实测) |
| A few GMod-only globals (such as `Entity`) | ❌ do not exist; they must be replaced when porting GMod addons |

For the complete list see [Derma Basic Guide §8](derma_basic_guide.html#8-已知差异-未实现相对-gmod) and
[Port plan and status](gmod_lua_port_plan.html#9-移植状态与经验v3-增补2026-09-12-09-13).
