# GMod Lua port plan v2 — HL2SB

> Written 2026-09-11. **v1's strategy is void**, see "Strategy change" below.
> Path base: `D:\srceng\hl2sb\lua` (the relative paths below are all relative to it).
> Engine-side base: `D:\project\source-engine`.
>
> ⚠️ **2026-09-13 addendum**: **the latest progress inventory and lessons learned are in [§9](#9-移植状态与经验v3-增补2026-09-12--09-13)**.
> §1–§8 are the 09-11 planning perspective (gap → landing point mapping); they remain valid but **no longer reflect what has been completed**;
> **if you want to know "which step we are at now / what pitfalls are left", read §9 directly**.
> The item-by-item hard engine-side facts are also in `D:\project\source-engine\AGENTS.md`.

---

## 0. Strategy change (v1 → v2) {#0-策略变更v1-v2}

| | v1 (void) | **v2 (this version)** |
|---|---|---|
| Overall policy | "Port to HL2SB, but **in HL2SB's Lua style**" | **Take GMod's Lua as-is; rewrite as little as possible** |
| What to do about missing functions | Write a shim on the Lua side / switch to the HL2SB way / just don't do it | **Add the binding on the engine C++ side** |
| Criterion | Whether it can be expressed with HL2SB's existing primitives | **Whether the original GMod file can run with not one line changed** |

**Why v2 holds**: this repo is **complete engine source**, not a closed-source shell like SDK2013.
`D:\project\source-engine` has **74 top-level modules**, of which **36 carry a `wscript`** and can be compiled independently:

```
engine  vgui2  vguimatsurface  materialsystem  studiorender  filesystem  inputsystem
tier0  tier1  tier2  tier3  mathlib  vphysics  soundsystem  soundemittersystem
datacache  vpklib  vtf  bitmap  choreoobjects  dmxloader  particles  scenefilecache
unicode  unitlib  video  appframework  datamodel  serverbrowser  stub_steam  togl/togles
launcher  launcher_main  dedicated  dedicated_main  gameui  lua
```
Besides that, `thirdparty/` contains **curl**, SDL, mbedtls, etc.
**Conclusion**: for nearly every item that makes GMod's Lua "missing functions", a corresponding module can be found in the engine to implement it
(`surface.*` → `vguimatsurface`, `render/cam.*` → `materialsystem`, `file.*` → `filesystem`,
`net.*` → `engine/net_chan` + `tier1/bitbuf`, `http.*` → `thirdparty/curl`, …).
**Moving the rewriting work from Lua to C++ pays off as: GMod files can be copied whole-directory, and afterwards every GMod addon works with them too.**

**The only case where "modifying Lua" is allowed**: when a GMod file hard-codes something that physically does not exist in HL2SB
(for example GMod's `net.Receive` event name, or the registration timing of `util.AddNetworkString`).
Such changes must be **marked with a `-- HL2SB:` comment + limited to adapting the file header as much as possible**, and registered in §5 of this file.

---

## 1. Environment comparison (**corrected**, v1 got everything here wrong) {#1-环境对照已更正v1-这里全错}

| Dimension | GMod | HL2SB (actual) | What v1 wrote |
|---|---|---|---|
| Lua version | LuaJIT 2.0 (GLua extensions) | **Lua 5.4.6** (`lua/src/lua.h:25 LUA_VERSION_NUM 504`), with GLua syntax extensions (`continue` / `!` / `!=` / `&&` / `\|\|` / `//` / `/* */`) and `module()`+`package.seeall` **back-ported from 5.1** | ❌ written as 5.1 |
| `autorun` | loaded | **loaded** (`luasrc_dofolder_sorted()`: `lua/autorun/*.lua` non-recursive + `client|server/**` recursive, by filename A-Z) | ❌ written as not loaded |
| `utf8` library | its own `utf8.lua` | **native** (`linit.c:51 luaopen_utf8` + `lua/src/lutf8lib.c` in the compile list) | ❌ said to write len/sub yourself |
| `Color` | table, `.r/.g/.b/.a` are fields | **table, `.r/.g/.b/.a` are plain numeric fields** (`public/lua/lColor.cpp:41-44` + `:164-175`). The capitalized `col:GetR()` etc. are methods | ❌ written as userdata + methods |
| Module mechanism | `module("x")` + global `x.*` | same | ✅ |
| Encoding | whatever | **UTF-8 without BOM** (`resource/*.txt` is the exception: UTF-16LE+BOM) | ✅ |

> ⚠️ **v1's whole §0 "key conclusions" was built on 5.1 and is void.** The 5.1→5.4 differences (`luaL_checkint`
> no longer accepting non-integers, `unpack`→`table.unpack`, `setfenv/getfenv` removed, etc.) have all already been handled by the engine/compatibility layer;
> see "the most painful migration difference in Lua 5.4" in `AGENTS.md` §5.4.

---

## 2. Current inventory: GMod's Lua tree vs ours {#2-现状盘点gmod-的-lua-树-vs-我们}

### 2.1 GMod-side size (how much is coming over) {#21-gmod-侧体量拿来多少}

| Directory | .lua count | Purpose |
|---|---|---|
| `lua/includes/modules/` | 38 | libraries (`hook`/`net`/`file`/`render`/`draw`…) |
| `lua/includes/extensions/` | 29 (including subdirectories) | extensions (`string`/`table`/`math`/`player`/`ents`/`util`/`panel`…) |
| `lua/vgui/` | **93** | Derma controls |
| `lua/derma/` | 7 | the Derma framework itself |
| `lua/skins/` | 1 | default skin |
| `lua/menu/` | 27 | main menu |
| `lua/autorun/` | 35 | auto-loading |
| `lua/postprocess/` | 14 | post-processing |
| `lua/entities` `weapons` `drive` `matproxy` | 6/3/3/3 | scripted entities/weapons |

### 2.2 `includes/modules` mechanical set difference {#22-includesmodules-机械差集}

**Same name on both sides (10)**: `baseclass` `concommand` `draw` `gamemode` `hook` `killicon` `list` `player_manager` `team` `undo`

**GMod has, we don't (28)**:
`ai_schedule` `ai_task` `cleanup` `constraint` `construct` `controlpanel` `cookie` `cvars`
`drive` `duplicator` `effects` `halo` `http` `markup` `matproxy` `menubar` `notification`
`numpad` `presets` `properties` `saverestore` `scripted_ents` `search` `spawnmenu`
`usermessage` `utf8` `weapons` `widget`

**We made ourselves, GMod doesn't have (11)**:
`ammo` `cvar` `entity` `gmod_compatibility` `gmod_vgui` `hl2sb_lua_errors`
`language` `resource` `save` `timer` `weapon`

> 🔎 **Note that "same name ≠ same content"**: `draw`/`hook`/`killicon`/`team`/`list`/`undo`/`gamemode`/`concommand`
> are all **versions we rewrote** right now. Under the v2 strategy these must be **switched back, step by step, to the original GMod files** (on the premise that the
> bindings they depend on are filled in first), otherwise they will forever be "like GMod but not GMod".

### 2.3 `includes/extensions` set difference {#23-includesextensions-差集}

**GMod has, we don't (12)**:
`angle` `coroutine` `debug` `entity_iter` `ents` `file` `game` `motionsensor`
`player_auth` `player` `util` `vector`

**Our self-made compatibility layer (7)**:
`gmod_compat` `gmod_globals` `gmod_surface` `gmod_util` `keyvalues` `panel` `vgui`

> 🔎 The positioning of the self-made compatibility layer: **temporary scaffolding**. Each time an engine binding is filled in, delete the corresponding shim;
> the end goal is "engine binding = GMod semantics; Lua side = original GMod files".

### 2.3.1 ⚠️ The one already in the repo but **switched off**: `gmod_compatibility/` {#231-已经在仓库里但关着的那套gmod_compatibility}

`lua/includes/modules/gmod_compatibility/` is a GMod compatibility layer vendored wholesale from **Experiment: Source**,
and it is not small:

| File | Size | Content |
|---|---|---|
| `sh_init.lua` | **67 KB** | `bit`/`gamemode`/`hook`/`timer`/`net`/`DeriveGamemode`/`include`/`Msg`/`jit` stubs, `util.*` (Precache/TraceLine/JSON/CRC…), `ents.*` (Create/GetAll/FindByClass/FindInSphere…), `player`, `sql`, `FindMetaTable`/`RegisterMetaTable` |
| `sh_enumerations.lua` | 17 KB | the `_E` enum tables |
| `sh_color.lua` / `sh_file.lua` / `vgui_base.lua` / `cl_awesomium.lua` | small | piecemeal fill-ins |

The entry point `lua/includes/modules/gmod_compatibility.lua` is
**switched off by `GMOD_COMPATIBILITY = GMOD_COMPATIBILITY or false`** —— because its start does
`require("bitwise") / require("gamemodes") / require("hooks") / require("timers")`,
and these four names do not exist on our side (we have the `bit` library / `gamemode.lua` / `hook.lua` / `timer.lua`).

**Disposition (per the v2 strategy)**: **do not revive it**. It is Experiment's **renaming-style** compatibility layer
(`net = Networks`, `player = Players`, `include = Include`), and it conflicts with HL2SB's route
(**keep the native GMod names + add engine bindings**); having the two coexist would only make them fight each other.
But it is an **excellent checklist of "what GMod code actually needs"** — read it as a reference when ordering gaps.


### 2.4 Engine-side bindings already done (`luasrclib.h` / `lsrcinit.cpp`) {#24-已经完成的引擎侧绑定luasrclibh-lsrcinitcpp}

`surface` `vgui` + `Panel` `Label` `TextEntry` `Button` `EditablePanel` `CheckButton` `Frame`
`PropertyDialog` `PropertyPage` `ModelPanel`, `Color` `Vector` `QAngle` `matrix3x4_t` `vmatrix`,
`CTakeDamageInfo` `CEffectData` `CGameTrace` `CRecipientFilter` `CPASFilter`,
`CBaseEntity`/`_shared` `CBasePlayer`/`_shared` `CBaseCombatWeapon` `CBaseAnimating`/`_shared`
`CBaseFlex_shared` `CHL2MP_Player`/`_shared`, `ConCommand` `ConVar` `cvar` `FCVAR`, `dbg`
`debugoverlay` `engine` `enginevgui` `filesystem`(Files/FileHandle) `gpGlobals` `input`
`GameEvents`(gameevent.Listen) `gEntList` `hl2sb` `IMaterial` `Localizations`
`networkstringtable` `net` `physenv` `prediction` `random` `scheme`(IScheme/HScheme/HFont)
`steamapicontext` `UTIL` `system`, `ScriptedEntities`, shared enums `_E` (`ACTIVITY`/`BUTTON`/`FL`/`LIFE`/…)

---

## 3. Gap → **engine landing point** mapping (the core of this version) {#3-缺口-引擎落点映射本版核心}

> How to read it: the left column is what GMod Lua calls directly; the middle column is which engine module it lands in;
> the right column is the verdict on "can the original file be copied directly".

### 3.1 Drawing / UI {#31-绘制-ui}

| GMod needs | Engine landing point | Notes |
|---|---|---|
| `surface.DrawTexturedRectRotated( x,y,w,h,rot )` | `public/lua/vgui/LISurface.cpp` (**client.dll**) → use the existing `ISurface::DrawTexturedPolygon` (`public/vgui/ISurface.h:311`) | ⚠️ `x,y` is the **center**. **The ISurface vtable does not need to be touched**, only client.dll is rebuilt. See `D:\project\_session_extract\圆角HUD改动清单.md` |
| `surface.DrawTexturedRectUV( x,y,w,h,u0,v0,u1,v1 )` | same as above (right now `gmod_surface.lua` assembles it with `DrawTexturedSubRect`, can be sunk into C++) | `DrawTexturedSubRect`'s UV is already normalized 0..1 (`MatSystemSurface.cpp:1655`) |
| `surface.DisableClipping( bool )` / `EnableClipping` | `vguimatsurface/MatSystemSurface.cpp` (**needs a new virtual function + a bump of `VGUI_SURFACE_INTERFACE_VERSION`**, full rebuild) | route C, high cost. `draw.*`/the two HUDs don't need it, **not doing it for now** |
| `surface.CreateFont( name, {font=,size=,weight=,antialias=,extended=} )` | can be wrapped in Lua for now (`CreateFont()+SetFontGlyphSet()`), or sunk into `LISurface.cpp` | Derma uses "string font name + table argument" a lot, **must be added** |
| `surface.SetFont( name )` return value used as a handle | **done** (`LISurface.cpp`, commit `23d472d6`) | — |
| `surface.GetTextSize( text )` one-argument form | enough at the Lua layer, but it must go in **`lua/autorun/client/`** (after `font.lua`) | `font.lua` currently redefines it as `(font, text)` |
| `draw.NoTexture()` / the corner path of `draw.RoundedBox` | `lua/includes/modules/draw.lua` (GMod's original can be copied directly; only the two surface functions above need to be in place) | right now `RoundedBoxEx` has been changed into a solid rectangle, see §5 |
| `draw.GetFont` / `draw.GetFontHeight` | needs `surface.GetFontHeight`? → GMod gets it from `surface.GetTextSize`/FontMetrics | done (`draw.lua` has `GetFont`) |
| `render.*` (`SetDrawColor`/`SetMaterial`/`DrawTexturedRect`/`CullMode`/`SetRT`/`OverrideBlend`…) | **new** `game/client/lua/lrender.cpp` → `IMaterialSystem` + `IMatRenderContext` (module `materialsystem`) | `luasrclib.h` already has the `Renders` name, but no implementation is visible in the registry → it needs to be created |
| `cam.*` (`Start3D`/`End3D`/`Start2D`/`End2D`/`Start`/`End`) | same as above (`lrender.cpp` or `lcam.cpp`) | depends on `IMatRenderContext::Push3DView` |
| `view.*` (`RenderView`/`GetViewModel`) | `game/client/lua/` | low priority |
| `vgui.Create` / `vgui.Register` / `vgui.GetControlTable` | **one version already exists** (`gmod_vgui.lua` + C++ `game/client/lua/scripted_controls/LPanel : public vgui::Panel`) | needs to be aligned with GMod's `scriptedpanels.lua` (`GetTable` vs `GetRefTable`, `CreateFromTable`, `vgui.Exists`…) |
| `DisableClipping` (used by Derma) | see above | —— |
| `ModelImage` / `SpawnIcon` model thumbnails | `game/client`'s `CModelPanel`/`CModelImage` (`vgui_controls`) | GMod renders it at runtime, HL2SB lacks the binding; the player model menu has already been through this |
| `surface.GetTextureID` / `SetTexture` / `DrawRect` / `SetDrawColor` / `SetTextColor` / `SetTextPos` / `DrawText` / `Material(path)` / `DrawTexturedRectUV` | **already in** `lua/includes/extensions/gmod_surface.lua` (Lua layer); `Material()` itself is now a **real C binding** (client `litexture.cpp:476`, server `limaterial.cpp:445`), and the Lua proxy is only installed when `Material == nil` | the rest can still be sunk into C++ long term, but **it works**. See [Material / CreateMaterial](material.html) |

### 3.2 Network {#32-网络}

| GMod needs | Engine landing point | Notes |
|---|---|---|
| `net.Start/Write*/Read*/Send/Receive/Broadcast` | `game/shared/lua/lnet.cpp` (**a prototype already exists**: a self-made usermessage `"LuaNet"`) → expand into GMod semantics | the bottom layer uses `bf_write`/`CBaseClient`/`engine/net_chan` (modules `engine`, `tier1`). `extensions/net.lua` already exists |
| `util.AddNetworkString` | **already shimmed** (`gmod_util.lua:85`) → long term move it to C++ | — |
| `usermessage.Hook` / `SendUserMessage` | same as above (GMod's usermessage is a special case of net) | — |
| `net.ReadHeader` / `MAX_EDICT_BITS` and other constants | `public/const.h` etc. | — |

### 3.3 Files / network IO {#33-文件-网络-io}

| GMod needs | Engine landing point | Notes |
|---|---|---|
| `file.Read/Write/Exists/Delete/Find/Time/Open/Size` | `public/lua/lfilesystem.cpp` (**already implemented**: `file.Find` at `:1169`, registered into `file_funcs[]` at `:1414`, `luaopen_Files` at `:1419`; the GMod spelling alias `file` at `lsrcinit.cpp:553`) | ✅ GMod's path semantics are already fully mapped (`s_GModPathIDs` `:618`: `DATA` → `MOD` + `data/` prefix, `LUA` → `GAME` + `lua/` prefix, illegal pathID → `nil, nil`). `file.Find`'s signature / default `nameasc` / two return values match upstream, and the differences (addon title IDs unsupported, `MOD` includes addons, no realm distinction) are recorded item by item in [file.Find](file_find.html) |
| `http.Fetch/Post`, `HTTP()` | **`thirdparty/curl` is already in the repo**; it lands in `game/client/lua/lhttp.cpp` + a main-thread callback queue | GMod's `http` is asynchronous + `onSuccess/onFailure` |
| `cookie.*` | same as above / `steamapicontext`'s ISteamUser + `filesystem` | — |
| `util.TableToJSON` / `util.JSONToTable` | the engine already has JSON (`tier1` has `CUtlBuffer`+JSON? needs checking) or bind `thirdparty` | — |

### 3.4 Entities / players / teams {#34-实体-玩家-队伍}

| GMod needs | Engine landing point | Notes |
|---|---|---|
| `ents.GetAll` / `FindByClass` / `FindByName` / `Iterator` / `Create` | `gEntList` in `game/server`+`game/shared` (the module already has the `Entities` table) → add the `ents.*` aliases | `gEntList` currently has `FirstEnt/NextEnt/FindEntityByClassname/FindEntityByName`; `ents.Create` goes through the server's `CreateEntityByName` |
| `player.GetAll` / `Iterator` / `GetBySteamID*` | `game/shared/lua/lbaseplayer_shared.cpp` | `player.GetAll` **already done**; the rest to be added |
| `team.*` | `game/shared/hl2mp/hl2mp_gamerules.cpp` (HL2MP has teams) + the Lua layer | `team.lua` already has a half-finished version |
| `scripted_ents.Register/Get/GetStored` / `weapons.*` | `game/shared/lua/basescripted.cpp` + `weapon_hl2mpbase_scriptedweapon.cpp` | we already have an equivalent registry (the `ScriptedEntities` library) → add the GMod names |
| `halo.Add/Render`, `effects.Create/Register` | `game/shared`'s `CEffects` + temp entity | the `Effects` library already exists (server) |
| `util.TraceLine(table)` | `lgametrace.cpp` (**already has the GMod field aliases**) | only the "table argument" form is missing |
| `Entity:CallOnRemove` / `entmeta:*` | **already shimmed** (`gmod_util.lua:121`, via the `EntityRemoved` hook) | long term move it to C++ (`CBaseEntity::OnRemove`) |
| `ents.FindInSphere/Box` etc. | `game/server` | — |

### 3.5 Explicitly **not doing** (or not doing at the Lua layer) {#35-明确不做或不在-lua-层做}

| Item | Reason |
|---|---|
| `matproxy.lua` | GMod's matproxy is a **proxy registered by engine C++** + LuaJIT. Copying the Lua is useless; you have to implement it yourself with `game/client`'s `IMaterialProxy` (we already have the `CPlayerColorProxy` precedent) |
| `utf8.lua` (GMod's copy) | **not needed**. Lua 5.4's native `utf8` library is already there (`linit.c:51`) |
| `lua/menu/**` (27 files) | it is GMod's main menu (the GameUI domain). It can be done, but it conflicts with HL2SB's own menu, **so last** |
| `lua/postprocess/**` (14 files) | depends on `render.*` + the whole `DrawColorModify` family → **it only gets its turn after `render.*` is done** |
| `saverestore` / `duplicator` / `presets` / `cleanup` | depends on entity serialization + the Derma UI; queued after Derma |
| `drive` / `numpad` / `properties` | depends on driving/physics/input bindings; low value |

---

## 4. UI route (`vgui` + `derma` + `skins` = 101 files) {#4-ui-路线vgui-derma-skins-101-个文件}

This is the biggest block for "running GMod as-is", and also the place that best shows the value of the v2 strategy.

**The foundation that already exists** (confirmed by the earlier investigation):

| Layer | Current state |
|---|---|
| C++ panel base class | ✅ `game/client/lua/scripted_controls/LPanel : public vgui::Panel` (a real vgui2 derivation) |
| C++ concrete controls | ✅ `lButton` `lLabel` `lTextEntry` `lFrame` `lCheckButton` `lModelPanel` `lPropertyDialog` `lPropertyPage` |
| C++ vgui library export | ✅ `luaopen_vgui` exports `Button/EditablePanel/Panel/CheckButton/Frame/PropertyDialog/PropertyPage/ModelPanel` one by one |
| Lua `vgui.register` | ✅ the Team Sandbox version (`lua/includes/extensions/vgui.lua`) |
| GMod spelling + minimal Derma | ✅ `lua/includes/modules/gmod_vgui.lua` (`vgui.Register`/`vgui.Create`/`derma.DefineControl` + minimal DPanel/DFrame/DLabel/DTextEntry/DButton) |

**What needs to be added (in dependency order):**

1. `surface.CreateFont( name, table )` (the GMod form) —— a global Derma dependency
2. `surface.DrawTexturedRectRotated` (§3.1) —— rounded corners
3. `vgui.Create/Register` **semantically aligned** with GMod's `scriptedpanels.lua`:
   - `panel:GetTable()` vs our `GetRefTable()` (just add an alias)
   - `baseclass.Set/Get` (we already have it)
   - `vgui.CreateFromTable` / `vgui.RegisterTable` / `vgui.RegisterFile` / `vgui.Exists`
   - ⚠️ the metatable of `vgui.Frame` **does not carry the Panel methods** in this engine → either fix the C++, or have `DFrame` go through the `Panel` base class (which is exactly how `gmod_vgui.lua` works around it now)
4. `DisableClipping` (used by Derma/`dragdrop`/`dnumberwang`) —— needs route C (modify ISurface)
5. `derma.DefineSkin` / `SkinHook` / `lua/skins/default.lua`
6. then **copy `lua/vgui/*.lua`(93) + `lua/derma/*.lua`(7) + `lua/skins/*.lua` as whole directories, unchanged**

> Only 1–5 need to be opened up first; after that the 101 files are **copy-paste**, not rewriting. That is the value of v2.

---

## 5. Key corrections & pending fixes (relative to v1 / relative to the current state) {#5-关键更正-待办修正相对-v1-相对现状}

### 5.1 v1's errors (corrected in this version) {#51-v1-的错误已在本版修正}

1. **Lua version 5.1 → 5.4.6** (and with it: the 5.1 assumptions such as `uv`/`unpack`/`setfenv` are all void)
2. **`autorun` now gets loaded** (the old text said "will not be loaded", and on that basis made all scripts avoid autorun)
3. **`Color` is a table, not userdata** (the `col:r()` spelling taught by the old text's §"key pitfall memo" is wrong;
   taking the number directly with `col.r` is right)
4. **`utf8` does not need porting** (native in 5.4)
5. `surface.GetTextureID / SetTexture / DrawRect / DrawTexturedRectUV / Material()` **are in place**
   (only `DrawTexturedRectRotated` is left)
6. `killicon` / `resource` / `list` / `team` / `baseclass` / `timer` / `net.lua` /
   `hook.Add`+`Remove`+`GetTable` / `gameevent.Listen` **are in place**

### 5.2 Existing but behaviourally incomplete (v2 must fix) {#52-现存但行为不完整的v2-要修}

| Item | Current state | Should become |
|---|---|---|
| `draw.RoundedBoxEx` | ✅ **fixed** (commit `976e52d`): GMod's original body + `DrawTexturedRectUV` on the four corners. The root cause of the old "whole block turns white" was exactly that **`surface.SetTexture` was not called before drawing the texture** — it was still bound to the engine's default white texture | —— |
| `hl2sb_cl_hudpickup.lua` | ✅ **fixed** (commit `976e52d`): GMod's original 4×`DrawTexturedRectRotated` + 4×`DrawRect`; `GM.PickupHistoryCorner` was also set the GMod way | —— |
| `DermaDefault` / `DermaDefaultBold` | ✅ **fixed** (commit `976e52d`): built in `gmod_vgui.lua` the way GMod's `lua/derma/init.lua` does, with `surface.CreateFont(name, FontData)`; the pickup HUD is no longer mapped to `Default` | —— |
| `draw.lua` / `hook.lua` / `killicon.lua` / `team.lua` / `list.lua` / `undo.lua` / `concommand.lua` / `gamemode.lua` | all are the **rewritten versions** | switch back to the original GMod files step by step (on the premise that the §3 bindings are in place) |
| self-made compatibility layer (`gmod_globals` / `gmod_util` / `gmod_surface` / `gmod_compat` / `gmod_vgui` / `panel` / `vgui` / `resource` / `language` / `save` / `timer` / `ammo` / `cvar` / `entity` / `weapon`) | temporary scaffolding | each time one engine binding is filled in, delete one |

### 5.3 Engine-side pitfalls that must be remembered (see `AGENTS.md` §5.4) {#53-必须记住的引擎侧坑详见-agentsmd-54}

- The `RETURN_LUA_*` macros have been changed from the "`lua_gettop(L) == 1` absolute test" to `> 0` (fixes a stack leak)
- `m_nTableReference`'s double unref has been fixed (the number-one root cause of sudden in-game crashes)
- Lua 5.4's `luaL_checkint` has been changed to accept floats (otherwise the HUD throws an error every frame and silently draws nothing)
- `hook.lua` **permanently unregisters** the hook as soon as it errors; `hook.call` with a same-named event that loops on itself hangs (a guard has been added)
- `lua/includes/modules/*.lua` gets **executed twice** → do not write `X = X or <definition in this file>`
- Changing `lua/includes/modules/*.lua` requires **completely restarting the game** (module re-entry guard)
- A new `.cpp` must go into the corresponding `.vpc`, otherwise it never makes it into the build (`AGENTS.md` §2)

---

## 6. Execution order (v2 checklist) {#6-执行顺序v2-版勾选表}

> `[x]` done and verified / `[~]` written but not verified / `[ ]` untouched

### P0 — The foundation that lets "original GMod files" run {#p0-让gmod-原文件能跑起来的地基}

- [x] Engine: Lua 5.4.6 + GLua syntax (`continue` / `!` / `!=` / `&&` / `||` / comments)
- [x] Engine: `luaL_checkint` accepts floats (`lua/etc/lua.hpp`)
- [x] Engine: `RETURN_LUA_*` stack leak fix (25 places in `luamanager.h`)
- [x] Engine: `m_nTableReference` double unref fix
- [x] Engine: `autorun` loading + sorting (`luasrc_dofolder_sorted()`)
- [x] Engine: global `IsValid` / `player.GetAll` / `player:UniqueID()`
- [x] Engine: ANSI→Unicode fix for `surface.SetFont(name)`, `surface.GetTextSize`
- [x] Engine: `gameevent.Listen`
- [x] Lua: `string` / `table` / `math` extensions
- [x] Lua: `hook.Run` / `hook.Add` / `hook.Remove` / `hook.GetTable`
- [~] Lua: `gmod_globals.lua` (`CurTime`/`ScrW`/`ScrH`/`CreateConVar`/`GetConVar*`/`Sound`/`Model`/`Angle`/`ACT_*`) → **long term it should be sunk into C++**
- [x] **Engine: `surface.CreateFont( name, table )` (the GMod form)** ← the Derma prerequisite.
      Engine commit `85333918`. Implements every field of `FontData`; the handle is stored in the **registry name table of each Lua state**,
      and `surface.SetFont(name)` checks it before the scheme. The old no-argument form is kept.
- [x] **Engine: `surface.DrawTexturedRectRotated`** (`LISurface.cpp`, going through `DrawTexturedPolygon`)
      Engine commit `85333918`. `x,y` is the **center**, degrees, counter-clockwise on screen.
      Only client.dll is rebuilt, **the ISurface vtable was not touched**.
- [x] **Engine: `surface.DrawTexturedRectUV`** (same as above, converted to `DrawTexturedSubRect`) —— the copy in the Lua shim is changed to have no effect
- [x] **Engine: load `lua/includes/init.lua` by name** (GMod's bootstrap) + load failures are diagnosable
      ~~Engine commit `1991571d`~~ → **superseded by `ab073409`**: it originally used
      `luasrc_dofolder_sorted( L, LUA_PATH_INCLUDES, false )` to **scan the directory**, while `init.lua`
      itself already includes `util.lua` and `vgui_base.lua` → those two got run a **second time**,
      and the second run of `vgui_base.lua` pushed all 54 `lua/vgui/*` files into
      `derma.DefineControl`'s "reload" branch → `ReloadClass()` → `vgui.GetAll()` (which did not exist at the time)
      → **54 lines of FAILED, not one control registered**.
      Now it uses `luasrc_dofile_includes( L, "init.lua" )` (`luamanager.cpp`), and both realms load by name.
      ⚠️ **Lesson**: the include list inside `init.lua` = the only load manifest; adding a file to it means changing `init.lua`,
      and you cannot rely on a directory scan to load it "incidentally".
- [x] **Engine: the server also loads `lua/includes/init.lua`, but the client-only parts must be blocked with `if ( CLIENT )`**
      Engine commit `ab073409` (game-side `lua/includes/init.lua` commit `25f059f`).
      The server originally ran derma/vgui_base, and line 24 of `derma/init.lua` indexes `surface` (nil on the server)
      → the global `derma` was never created → the 54 controls reported `(global 'derma')` all over again.
      The three that got blocked: `extensions/client/panel.lua`, `derma/init.lua`, `vgui_base.lua`.
      ⚠️ `util.lua` **must not be blocked** (the server's `autorun/server/hl2sb_falldamage.lua` needs `GetConVar`).
      Offline verification: `D:\project\luacheck\test_gmod_includes_server.lua` (6 assertions, including the refusal-style assertion
      "not a single client-only file may get in").
- [x] **Lua: GMod's `lua/includes/util.lua`** (a byte-for-byte copy, including `AccessorFunc` /
      `FORCE_*` / `type` predicates / `Lerp` / `Either` …) —— game commit `c34b213`,
      offline verification **45/45 globals present** (`D:\project\luacheck\test_gmod_includes.lua`).
      `lua/includes/init.lua` is the **only** rewrite point, and the reason is already noted in its header.
- [x] **Engine: GMod's lowercase library global names + the `include()` search path** —— engine commit `47bbd18d`
      - `lsrcinit.cpp` adds `luasrc_install_lib_aliases()`: it aliases `Systems`/`Files`/`UTIL`/
        `Renders`/`Sounds`/`Chats`/`ParticleSystems`/`ScriptedEntities` to
        GMod's `system`/`file`/`util`/`render`/`sound`/`chat`/`particle`/`scripted_ents`
        (`Entities`/`player`/`gameevent` were already aliased where each is opened)
      - `luamanager.cpp`'s `luasrc_include`: first by the calling file's relative path (**old behaviour unchanged**),
        then falling back to `lua/` → `lua/includes/` → bare path. This is the key to `vgui_base.lua` being able to include
        `vgui/DFrame.lua` (whose real location is `lua/vgui/`)
      - ⚠️ **`ab073409` correction: an alias must "merge", it must not "replace by reference".**
        The `lua_setglobal` version knocked out the whole GMod-named library, and the two realms spell things inconsistently
        (the client's `lcdll_util.cpp` registers `UTIL`, the shared `lutil_shared.cpp` registers `util`)
        → on the client `util = UTIL` **deleted** `util.PrecacheModel` / `PrecacheSound` /
        `TraceLine`, and the symptom was `util.lua:225: attempt to call a nil value (field 'PrecacheModel')`.
        **And that C implementation had been there all along** (`lutil_shared.cpp:160`, registered at `:214`) ——
        when investigating "the field is nil", first suspect that something swapped that table out.
        Now it merges key by key with `lua_next` (what the destination table already has is kept).
- [x] **Lua: GMod's `lua/derma/`(7) + `lua/vgui/`(93) + `lua/skins/`(1) +
      `lua/includes/vgui_base.lua`** —— game commit `cc304ef`, **all 101 files hash-identical**.
      `lua/includes/init.lua` hooks them up in GMod's order: `util.lua` → `derma/init.lua` → `vgui_base.lua`
- [x] ~~⛔ current blocker: `vgui.Register: base class 'DLabel' does not exist`~~ —— **resolved**
      Game commit `bef656b`: GMod's entire `lua/includes/extensions/client/` tree has been copied in and is loaded in
      `includes/init.lua` **before** derma (`panel.lua` → `panel/scriptedpanels.lua`, 9 files in all).
      GMod's `vgui.Register` goes through `PanelFactory` + `baseclass` and no longer requires
      the base to be registered into `vgui[]`. The `vgui.Register`/`Create` in `gmod_vgui.lua` have become dead code
      (to be deleted, see P4).
      ⚠️ The other layer of the cause at the time is the `ab073409` item above (the double load forced the 54 controls into the reload branch).
- [x] **Engine: global `GetConVar_Internal( name )`** —— engine commit `ab073409`
      (`public/lua/tier1/lconvar.cpp`). GMod's `util.lua:572` onwards **unconditionally** redefines
      `GetConVar` / `GetConVarNumber` / `GetConVarString` / `GetConVarBool`, calling it internally
      (`:575`) → without it, **the kill/death HUD and undo both stop working**.
      Difference from `ConVar(name, def, …)`: it **does not create** (an unknown name returns nil, the GMod contract),
      and it checks `m_ConVarDatabase` first (`luasrc_ConVar` does not call `RegisterConCommand`,
      so `FindVar` cannot find a convar created from Lua).
      ⚠️ Only `tier1/lconvar.cpp` takes part in the build; `public/lua/lconvar.cpp` is dead code.
- [x] **Engine: `vgui.GetAll()`** —— engine commit `ab073409`
      (`lvgui_controls.cpp`): a **weak-valued** table in the Lua registry, appended to by the `vgui.Create` dispatch.
      `derma.lua`'s `FindPanelsByClass()` needs it when reloading a control definition; addons also use it to find/close windows.
      ⚠️ After the double load was fixed it is no longer a fatal path (only a real reload goes through `ReloadClass`).
- [ ] Lua: the one-argument form `surface.GetTextSize(text)` (put it in `lua/autorun/client/`)
- [x] Engine: `Material()` is now a real C binding (client `litexture.cpp:476`, server `limaterial.cpp:445`;
      the client Lua proxy is only installed when `Material == nil`). What is left is IMaterial's **material variable reads/writes**, see §9.7 and [IMaterial](imaterial.html)
- [ ] Engine: make `CreateConVar` a real binding (the GMod contract `(name, default, flags, helptext, min, max)`).
      The current Lua shim is `ConVar(name, def, flags, help, min, max)`, while the engine's `ConVar` is
      `(name, default, flags, help, **bMin, fMin, bMax, fMax**) —— the `min`/`max` numbers land in the boolean slots.
      It **does not crash**, it only affects range clamping. `util.lua`'s `CreateClientConVar` calls exactly this.
- [ ] Engine: `debug.Trace()` (GMod's `debug` library has it, our `dbg` library does not).
      GMod's `util.lua` calls it on the warning path of `AccessorFunc(nil, …)`
      (around `util.lua:270`, reporting `field 'Trace'`). The server no longer loads `panel.lua` now,
      so that path is not hit for the time being.

### P1 — Drawing/HUD wrap-up (the effect is directly visible) {#p1-绘制hud-收尾可直接看到效果}

- [x] Lua: GMod's `killicon.lua` + `lua/game/client/gmod_deathnotice.lua` (verified in-game)
- [x] Lua: the main body of the GMod pickup HUD (`hl2sb_cl_hudpickup.lua`)
- [x] `draw.RoundedBoxEx` rounded corners —— **restored**, game commit `976e52d` (see §5.2)
- [x] the pickup bar switched back to GMod's original 8 lines (4 corners + 4 edges) —— game commit `976e52d`
- [x] `DermaDefault` / `DermaDefaultBold` / `DermaLarge` fonts —— following GMod's way
      (`surface.CreateFont(name, FontData)`, written in `gmod_vgui.lua`), without touching `clientscheme.res`
- [ ] **switch `lua/includes/modules/draw.lua` back to the original GMod file** (premise: `NoTexture` + font names go
      through `CreateFont`; `RoundedBoxEx` is already GMod's original now)
- [ ] `render.*` / `cam.*` (→ unlocks `postprocess`)

### P2 — Big engine bindings {#p2-引擎绑定大件}

- [ ] the `ents.*` lookup family (`gEntList` already has the bottom layer)
- [ ] complete `player.*` (`Iterator`/`GetBySteamID`)
- [ ] `team.*` hooked up to HL2MP gamerules
- [ ] `file.*` (GMod path semantics)
- [ ] the full `net.*` set (`lnet.cpp` extended, GMod-semantic Write/Read/Send/Receive/Broadcast)
- [ ] `usermessage.*`
- [ ] `http.*` / `cookie.*` (using `thirdparty/curl`)
- [ ] the GMod names for `scripted_ents.*` / `weapons.*`
- [ ] complete `util.*` (`TableToJSON`/`JSONToTable`/`TraceHull`/…)

### P3 — Big UI pieces (Derma) {#p3-ui-大件derma}

- [ ] `vgui.Create/Register` semantically aligned with GMod's `scriptedpanels.lua`
- [ ] the `panel:GetTable()` alias + `baseclass` alignment
- [ ] `derma.DefineSkin` / `SkinHook` / `lua/skins/default.lua`
- [ ] **copy the whole directories `lua/vgui/`(93) + `lua/derma/`(7) + `lua/skins/`(1)**
- [ ] (optional) route C: sink `ISurface::DisableClipping` + `DrawTexturedRectRotated` into vguimatsurface
- [ ] `spawnmenu` / `menubar` / `widget` / `properties` / `controlpanel` / `search` / `notification`
- [ ] `construct` / `constraint` / `duplicator` / `presets` / `cleanup` / `saverestore`

### P4 — Explicitly deferred {#p4-明确延后}

- [ ] `lua/menu/**` (27, conflicts with this repo's menu)
- [ ] `drive` / `numpad` / `properties` (physics/input)
- [ ] `matproxy.lua` (**not done at the Lua layer**, use C++ `IMaterialProxy`)
- [ ] **trim `lua/includes/modules/gmod_vgui.lua`** (currently the largest remaining scaffolding):
      its `vgui.Register` / `vgui.Create` have already been replaced by GMod's `scriptedpanels.lua` (dead code),
      its own 5 minimal controls (DPanel/DFrame/DLabel/DTextEntry/DButton) also conflict with `lua/vgui/`,
      and the three Derma fonts it creates are already created by GMod's `lua/derma/init.lua`.
      Only the parts that GMod's original **does not have** should be kept: `vgui.GetWorldPanel` / `vgui.GetHoveredPanel`,
      `derma.SkinHook` and the like that are genuinely missing; delete the rest.
      ⚠️ Before deleting, first confirm that `derma/init.lua` is already loaded before it (the order in `includes/init.lua` is correct right now).

---

## 7. Engineering conventions v2 {#7-工程约定-v2}

1. **Zero rewriting preferred**: if a GMod file can be copied, copy it. If it must be changed → first ask "can it be filled in inside the engine".
2. When Lua must be changed:
   - keep the changes concentrated in the **file header**, marked with `-- HL2SB:`, and registered in §5 of this file;
   - **do not** change semantics just to work around a missing function (that is exactly v1's root disease).
3. Rules for new engine bindings:
   - a new `.cpp` **must go into the `.vpc`** (`client_lua.vpc` / shared / the matching server target);
   - prefer **modifying an existing `.cpp`** (`LISurface.cpp` / `lnet.cpp` / `lbaseentity_shared.cpp`…) over adding new files;
   - after adding a binding, **define the name in `luasrclib.h` + register it in `lsrcinit.cpp`**, otherwise Lua cannot see it;
   - change `client.dll` → a **complete game restart** is required; change Lua → re-entering the map is enough.
4. Encoding is **UTF-8 without BOM**; when done, run `python tools\check_lua_utf8.py`.
5. Offline verification: `D:\project\luacheck\lua_syntax.exe` (compiled from the engine's Lua source, **5.4.6**) + mock test templates
   (`test_gmod_deathnotice.lua` with its 40 assertions is the example).
6. **The harness only "locates"; the engine source "adjudicates"**: when the harness reports "missing global X", first go to the engine source
   and confirm whether X is a real global (`Vector`/`Angle`/`Color`/`CLIENT`/`vgui.Label` are all real globals,
   and have been false-reported by the harness 4 times). If it is a real global → fix the harness's mock, **do not go and add it in the engine**.
   See the two includes harnesses in §5.4.3.
7. **General rules for aliases / registration / overriding**:
   - when giving the same library a second name, it **may only be merged, never replaced** (both the GMod name and the Experiment name may already exist,
     and `lua_setglobal` will silently delete a whole library's functions). See §5.4.3(3).
   - when "the field is nil" is reported, **first suspect that something swapped that table out**, and only then suspect a missing binding.
   - the engine's bootstrap loads **by name** (`luasrc_dofile_includes`); do not change it to scan directories ——
     scanning directories runs the files that `init.lua` already included a second time, and GMod's Lua layer reacts to a "second definition"
     by going down the **reload** branch (`derma.DefineControl`), not by doing nothing.
6. Every time a self-made shim is swapped out / a GMod original is copied, **tick it in this file and record one line**.

---

## 8. References {#8-参考}

### 8.1 Directories {#81-目录}

| | Path |
|---|---|
| GMod Lua source | `D:\games\garrysmod\garrysmod\lua\` |
| GMod wiki docs (already scraped) | `D:\gmod_wiki_docs\{libraries,globals,classes,hooks,guides}\` |
| HL2SB game Lua | `D:\srceng\hl2sb\lua\` |
| Engine binding registry | `source-engine\game\shared\lua\lsrcinit.cpp` + `luasrclib.h` |
| Engine modules (74 top-level) | `D:\project\source-engine\` |
| Rounded HUD change list | `D:\project\_session_extract\圆角HUD改动清单.md` |
| Engine must-knows (pitfalls) | `D:\project\source-engine\AGENTS.md` |

### 8.2 Key GMod original files (copy targets) {#82-gmod-关键原文件要拷的目标}

| File | Purpose |
|---|---|
| `lua\includes\modules\draw.lua` | `RoundedBox`/`SimpleText`/`NoTexture`… |
| `lua\includes\extensions\client\panel\scriptedpanels.lua` | the **authoritative GMod implementation** of `vgui.Create/Register` |
| `lua\derma\derma.lua` + `derma\init.lua` | the Derma framework itself |
| `lua\vgui\*.lua` (93) | all Derma controls |
| `lua\gamemodes\base\gamemode\cl_hudpickup.lua` | pickup HUD (the **authoritative implementation** of the rounded corners) |
| `lua\gamemodes\base\gamemode\cl_deathnotice.lua` | kill notices (**note: no rounded background panel**) |
| `lua\includes\extensions\client\render.lua` | `render.*` semantic reference |

---

## Appendix A: GMod docking port specification (2026-09-12, investigation finalized) {#附录-agmod-docking-移植规格2026-09-12-调研定稿}

**Background**: `self:DockPadding( 3, 3, 3, 3 )` at `notification.lua:172` fails —— see layer 10 of the progress table in §2.
A whole-repo search confirms that **this fork's vgui2 has no docking at all**: `SetDockPadding` / `SetDock(` / `DOCK_FILL` have zero matches;
the method table of `public/lua/vgui_controls/lPanel.cpp` also has no `Dock`/`DockPadding`/`DockMargin`.
And GMod's `Panel:Dock` is **C++** (evidence: `lua/includes/extensions/client/panel.lua:500` **calls** `self:Dock( pnl:GetDock() )` yet never defines them).

### A.1 Enum (source: https://wiki.facepunch.com/gmod/Enums/DOCK) {#a1-枚举来源httpswikifacepunchcomgmodenumsdock}

⚠️ **there is no `DOCK_` prefix**, they are just bare names:

| Global name | Value |
|---|---|
| `NODOCK` | 0 |
| `FILL` | 1 |
| `LEFT` | 2 |
| `RIGHT` | 3 |
| `TOP` | 4 |
| `BOTTOM` | 5 |

>`notification.lua:174` writes `self.Label:Dock( FILL )` —— using the bare `FILL`.
>On our side `FILL` is currently nil (it was only ever defined in the **switched-off** `includes/modules/gmod_compatibility/sh_enumerations.lua:160`).

### A.2 Semantics (source: https://wiki.facepunch.com/gmod/Panel:Dock) {#a2-语义来源httpswikifacepunchcomgmodpaneldock}

- `Panel:Dock( dockType )` —— makes the panel dock towards some direction, **automatically changing its position and size**.
- `Panel:DockPadding( l, t, r, b )` —— the **inner** spacing, affecting **child panels docked into this panel**.
- `Panel:DockMargin( l, t, r, b )` —— the **outer** spacing, affecting **this panel's position/size when it is a docked sibling**.
- ⚠️ Ordering: **use `Panel:SetZPos` to guarantee child panel order** (not pure creation order).
- After a layout change, if you want correct bounds immediately → `Panel:InvalidateParent()` (the GMod docs say so explicitly).

### A.3 Landing point: which files to change {#a3-落点改哪些文件}

| File | What to change |
|---|---|
| `public\vgui_controls\Panel.h` | fields `m_iDockType` / `m_iDockMargin[4]` / `m_iDockPadding[4]`; methods `SetDock/GetDock/SetDockPadding/GetDockPadding/SetDockMargin/GetDockMargin`; the docking pass function |
| `vgui2\vgui_controls\Panel.cpp` | implement the methods above + the docking pass. **The key integration point = `Panel::InternalPerformLayout()` (line 3845)** —— it clears `NEEDS_LAYOUT` first and then calls the virtual `PerformLayout()` (line 3859, an empty implementation); `:1109` (SetSize) and `:3887` (InvalidateLayout) both go through it. **Putting the docking pass here means a Lua override of `PANEL:PerformLayout` cannot bypass it** —— this is why it works in GMod |
| `public\lua\vgui_controls\lPanel.cpp` | bind `Dock`/`GetDock`/`DockPadding`/`GetDockPadding`/`DockMargin`/`GetDockMargin`; register the bare globals `NODOCK/FILL/LEFT/RIGHT/TOP/BOTTOM` |
| Build | rebuild **`vgui2` + `client`**, deploy `D:\srceng\bin\vgui2.dll` + `D:\srceng\hl2sb\bin\client.dll` |

### A.4 ABI decision (settled) {#a4-abi-决定已定}

**Add a `VGUI2_API` export, do not touch the vtable** —— to avoid a vgui2 ABI change forcing a full rebuild.

### A.5 Docking pass algorithm (following GMod's behaviour) {#a5-停靠回合算法按-gmod-行为}

```
available rect = this panel's client area shrunk inward by DockPadding
iterate the child panels in ZPos order (only IsVisible and m_iDockType != NODOCK):
  the rect is then shrunk inward by that child's DockMargin, giving its final bounds:
    FILL   -> eat the entire current available rect
    TOP    -> stick to the top, height taken from the child's existing height (or proportional when 0), then the available rect's top edge moves down
    BOTTOM -> same, stick to the bottom, the bottom edge moves up
    LEFT   -> stick to the left, width taken from the child's width, then the left edge moves right
    RIGHT  -> same, stick to the right, the right edge moves left
  SetPos/SetSize to that child panel
```

### A.6 Verification {#a6-验证}

After the change, re-enter the map: `hl2sb_notification`'s `OnUndo` should no longer error, and a notification bar appears in the top-right corner.
**By the way**: the layout of all `lua/vgui/*` (dpanel/dlabel/dtree/dlistview…) depends on docking —— this step is Derma layout infrastructure, not just a fix for the notification bar.

---

## 9. Port status and lessons learned (v3 addendum, 2026-09-12 → 09-13) {#9-移植状态与经验v3-增补2026-09-12-09-13}

> This section holds the **latest** progress and lessons, and supersedes the §6 checklist. Written 2026-09-13 02:00,
> engine branch `lua_playermodel_menu`, content repo branch `master`.
> All engine changes are in `D:\project\source-engine` (commit numbers in the table below), content changes in `D:\srceng\hl2sb`.

### 9.1 Overall status table (✅ working / ⚠️ partial / ❌ not done) {#91-状态总表-已通-部分-未做}

| Area | Status | Key commit | Notes |
|---|---|---|---|
| Lua 5.4.6 + GLua syntax (`continue`/`!`/`!=`/`&&`/`||`/comments) | ✅ | — | earlier than this round |
| `luaL_checkint` accepts floats | ✅ | — | otherwise the HUD throws an error every frame and silently draws nothing |
| `RETURN_LUA_*` stack leak / `m_nTableReference` double unref | ✅ | — | §5.3 |
| `autorun` loading + A-Z sorting | ✅ | — | |
| `lua/includes/` loads `init.lua` **by name** (does not scan directories) | ✅ | `ab073409` | fixed "54 vgui controls fail to reload" |
| library aliases **merge** instead of replacing (`util`/`UTIL`) | ✅ | `ab073409` | fixed `util.PrecacheModel` disappearing |
| `GetConVar_Internal` / `vgui.GetAll` | ✅ | `ab073409` | GMod's `util.lua` unconditionally overrides the convar family |
| `surface.CreateFont(name, FontData)` / `DrawTexturedRectRotated` / `DrawTexturedRectUV` | ✅ | `85333918` | |
| PNG textures (fall back to an image when `.vmt`/`.vtf` are missing) + `IMaterial:GetColor` sampling a PNG | ✅ | — | the two root causes of GMod skins being purple-black / all-white |
| The whole chain of "VGUI panels can draw but cannot be clicked" (`LLabel` dispatch, mouse passthrough, docking fields, `vgui.GetAll`) | ⚠️ | — | the Lua dispatch of `LCheckButton`/`LTextEntry`/`LEditablePanel` is **still not filled in** |
| Derma docking (`DOCK_*` enums + `Panel:Dock` algorithm) | ✅ | — | the specification in §Appendix A has been implemented |
| Kill notices (GMod's original `cl_deathnotice` + `killicon` + 25 aliases) | ✅ | content `e216a44` | `AddDeathNotice` only registers the hook (to avoid double lines) |
| Pickup HUD (GMod's original `cl_hudpickup`) | ✅ | `976e52d` | `DrawTexturedRectRotated` is the prerequisite |
| Undo / notifications (`undo.lua` + `hl2sb_notification`) | ✅ | `976e52d` | |
| **Lua SWEP runtime** (`Think`/`Tick`/`ItemPostFrame`/`Deploy`/`Holster`/`SetupDataTables`) | ✅ | `ff23965e` `ce3fe84c` etc. | the engine drives the fire key with GMod semantics; no ammo/empty-mag clicking |
| SWEP network variables (`SWEP:NetworkVar` → generates `Get*/Set*`) | ✅ | content `2e23bc2` | `weapon_fists`/`gmod_camera`/`medkit` all rely on it |
| Ammo types (`game.AddAmmoType` → `luasrc_ApplyAmmoTypes`) | ✅ | `0f8aa930` | `[Ammo] applied 11 Lua ammo definition(s)` |
| Weapon selection HUD icon / SWEP icon | ✅ | `9c911e72` `0f8aa930` | `swep.png` default image (content `9b7b479`) |
| viewmodel animation (activity resolution + per-frame restart semantics) | ✅ | `5e9ee523` | see 9.4 "activity in the model" |
| **Player max health networked** | ✅ | `50d1f475` | see 9.3, the single most important one this round |
| Sound: `Sound()` precache + retry on failure + missing-script diagnosis | ✅ | `5e9ee523` `7f8fc863` | |
| Bullet effects (`TE_HL2MPFireBullets` with a tracer name, send/recv aligned) | ✅ | `19f75da6` `6399bff2` `990795e2` | |
| Nyan Gun plugin (crash/icon/ammo/material/trail) | ✅ | `019e4e26` `0f8aa930` `0bb6baa5` | only the rainbow beam is left (8.4) |
| Admin Gun plugin (`pist_weagon` original runs unchanged) | ✅ | `4d7fd82b` etc. | the global `Sound()` is the prerequisite |
| `Entity:GetCurrentCommand` / `IsConstraint` / `SendLua` / `GetInternalVariable` / NULL entity semantics | ✅ | `6a704bbb` `7f8fc863` | see 9.5 "zeroing out weapon Lua errors" |
| `matproxy` (GMod's **Lua material proxy**, `lua/matproxy/*.lua`) | ❌ | — | see 9.7, needs a bridge + `IMaterial:SetVector` + `Player:GetWeaponColor` |
| Rainbow beam (`render.DrawBeam`) | ❌ | `8e5a92a3` `ee53a370` `9e0ef643` | all the chain data is correct and it is still not on screen; deprioritized |
| NPC `m_iMaxHealth` / client `m_takedamage` | ❌ | — | see 9.7, this round only did the player |

**Self-made shims still present in the content repo** (v2 §5.2's "each time a binding is filled in, delete one" — this is what is left for now):
`gmod_globals.lua` / `gmod_util.lua` / `gmod_surface.lua` / `gmod_compat.lua` / `gmod_vgui.lua` /
`gmod_isvalid.lua` / `modules/{panel,vgui,resource,language,save,cvar,entity,weapon}.lua`.
⚠️ But `gmod_globals.lua` is now **not just scaffolding**: it carries "the `Sound`/`Model`/`AddCSLuaFile`
equivalents for the two realms + the server-side `render`/`net.Receive` stubs + a fix of the `CreateConVar` argument positions", so before deleting it, confirm item by item that an engine binding covers each one.

### 9.2 New lessons from this round: **build / deploy / wire format** {#92-这一轮新增的经验构建-部署-线格式}

1. ⚠️⚠️ **Changing a client header (adding a member → `sizeof` changes) requires a full rebuild.**
   waf **only hashes .cpp content**; headers are not in the dependency graph. The way to do it: delete the object directories and build again:

   ```powershell
   Remove-Item D:\project\source-engine\build\game\client -Recurse -Force
   Remove-Item D:\project\source-engine\build\game\shared -Recurse -Force
   cd D:\project\source-engine; cmd /c ".\waf.bat build --targets=client,server"
   ```

   `game/shared` must be deleted along with it: shared `.cpp` files also include `cbase.h` → a client header, under the **client target**.
   A full build takes about **4 minutes** (1602 tasks). Not doing this links in .o files compiled against the old layout → heap corruption.
2. ⚠️ **`IMPLEMENT_NETWORK_VAR_FOR_DERIVED` only overrides virtual functions already declared by `CNetworkVarForDerived`
   → it does not add vtable slots**; whereas **adding a member** changes `sizeof`. The former can be changed freely, the latter requires a full rebuild.
3. ⚠️⚠️ **A wire-format change must swap client.dll + server.dll together, and recv props and send props are
   paired "by index", not by name.** This project stepped on this pitfall once (`TE_HL2MPFireBullets`'s
   send/recv misalignment, where the client received `m_bDoImpacts` into `m_flSpread`), and this round nearly stepped on it again:
   when adding a prop to `DT_BasePlayer`, **putting it right after the same anchor in both tables** (this time `m_iHealth`)
   is the most robust approach; after the change, grep both sides to confirm the order.
4. **Judging "whether the build actually did anything"**: look at the `LastWriteTime` of `build\game\client\client.dll`,
   or **search the DLL for a string that can only come from this change** (this time `m_iMaxHealth` —— before the fix
   GMod's client.dll had it and ours did not; after the fix it does, and a single command verifies it).
5. **Deployment paths**: `build\game\client\client.dll` → `D:\srceng\hl2sb\bin\client.dll`;
   `build\game\server\server.dll` → `D:\srceng\hl2sb\bin\server.dll`;
   always keep a `*.bak_<timestamp>` first, then compare the SHA256 of both sides.
   **A DLL is only loaded at process start → the game must be fully restarted.**

### 9.3 New lessons from this round: **client/server divergence is the root cause of "all the symptoms are on screen"** {#93-这一轮新增的经验客户端服务端分歧是症状全在画面的根源}

This is the most valuable item of this round; it directly explains two days of misjudgements:

> **The local player's viewmodel is a PREDICTED entity**, and its animation sequence is decided by **client prediction**;
> that successful `SendWeaponAnim` on the server **will not** be drawn on the player's screen.
> (The comment in `C_BaseViewModel::UpdateAnimationParity` says it very plainly: when predicting, animation parity is not used,
> because the animation is changed by the client itself.)

Corollary: **as long as the Lua logic computes different results on the client and on the server, what the player sees is always "the client's copy"**,
while the server stays correct as usual —— so it shows up as "the feature worked (health went up, damage came out), but the animation/sound is wrong".

The instance from this round (commit `50d1f475`):

| | Server | Client (before the fix) |
|---|---|---|
| `m_iMaxHealth` | really is 100 (`CNetworkVarForDerived`, `= m_iHealth` in `Spawn`) | **does not exist**, `C_BaseEntity::GetMaxHealth()` hard-codes `return 1` |
| `m_iHealth` | ✅ | ✅ (it is in `DT_BasePlayer`) |
| `weapon_medkit`'s `health >= maxhealth` | `80 >= 100` → heal succeeds | `80 >= 1` → **always "already at full health"** → `HealFail` |
| Result | health went up, the server played the heal animation | **plays the denial sound (`WallHealth.Deny`) + no animation** |

And the strange phenomenon of "healing someone else has an animation, healing yourself has none" is explained along with it:
the client's `C_BaseEntity::GetHealth()` **returns 0 by default for entities whose health is not networked**,
and `0 >= 1` is false → the NPC path actually "succeeded".

**The general technique for investigating this kind of problem**:
- Do not only look at whether the server log reports an error; **print a marker line on the client and on the server each** (the key of `HL2SB_WarnOnce` carries the realm).
- **Ask "does the client know about this"**: `GetMaxHealth` / `GetInternalVariable` / any `C_NetworkVar`
  may **simply not exist** on the client. grep the class definition on the client side first, then look at the server.
- Compare against **whether GMod's own DLL has that symbol**:
   ```powershell
   $t=[System.Text.Encoding]::ASCII.GetString([IO.File]::ReadAllBytes('D:\games\garrysmod\bin\client.dll'))
   $t.Contains('m_iMaxHealth')   # GMod: True   ours before the fix: False
   ```
  This trick is fast and hard —— what GMod has, we should have; what GMod does not have, do not go looking for in the DLL (see matproxy in 9.7).

### 9.4 New lessons from this round: **activity in the model / the weapon entity's own model** {#94-这一轮新增的经验模型里的-activity-武器实体自己的模型}

- ⚠️ **`mstudioseqdesc_t.activity` on disk is always -1**: studiomdl only writes the activity **name**,
  and the number is filled in at runtime by the game DLL, by name. **Do not expect to read activity numbers out of a .mdl.**
- Offline evidence-gathering tools (no need to start the game):
  ```powershell
  cd D:\project\source-engine\tools
  python studiomdl_inspect.py <model.mdl>        # each sequence's activity name / bones / IK
  python mdl_activity_scan.py --csv out.csv <root>   # batch
  ```
  Measured data (kept for comparison):

  | Model | Sequence count | activity names |
  |---|---|---|
  | `models/weapons/c_medkit.mdl` | 6 | `ACT_VM_DRAW` / `HOLSTER` / `IDLE` / `PRIMARYATTACK` |
  | `models/weapons/w_medkit.mdl` | **1** | only one called `idle`, **no ACT_ at all** |
  | `models/weapons/c_smg1.mdl` | 14 | the full set of 12 `ACT_VM_*` (**no `ACT_VM_HOLSTER`**) |
  | `models/weapons/w_smg1.mdl` | 3 | `ACT_VM_IDLE`, `ACT_RANGE_ATTACK_SMG1` |

- ⚠️⚠️ **"what is in the model" ≠ "which model is used at runtime".** I once thought medkit was stuck on `w_medkit.mdl`
  having no ACT_VM_*, but a single line of runtime log dismissed that:
  `weaponModel='models/weapons/c_medkit.mdl' resolves=1`. The reason is that
  **when the player is holding the weapon, `CBaseCombatWeapon::Equip()` swaps the weapon entity's own model for the VIEWMODEL**
  (`basecombatweapon_shared.cpp:1003-1006`; `SetActivity()` does the same swap too).
  **Lesson: for this kind of question — "which object/model is it actually at runtime" — you can only rely on engine-side instrumentation, not on inference.**
- The correct animation chain (write it down to save one trip through the source):
  ```
  SendWeaponAnim(act)
    -> SetIdealActivity(act)                        // basecombatweapon_shared.cpp:2355
         idealSequence = SelectWeightedSequence(act)   // ← uses [the weapon entity's OWN model]
         if (idealSequence == -1) return false;        // ← failure returns silently right here
         -> SendViewModelAnim(seq)                     // :1098
              -> vm->SendViewModelMatchingSequence(seq)  // actually drives the VM
  ```
  `CHL2MPScriptedWeapon::SendWeaponAnim` now has an extra **safety net**: when the weapon's own model cannot be resolved,
  it resolves on the **viewmodel entity** instead and then pushes it there (commit `5e9ee523`). This is not the cure for medkit
  (medkit already had `resolves=1`), but it turns a "silent no-op" into "either it moves, or a line is left in the log".
- **`ACT_*` constant verification**: the hand-written `ACT_VM_*` / `ACT_HL2MP_*` / `ACT_MP_*` in `gmod_globals.lua`
  have each been checked against the enum in `game/shared/ai_activity.h` (1749 activities, all consistent).
  Script: `D:\project\luacheck\check_act_values.py`. **Re-run it after changing these constants.**

### 9.5 New lessons from this round: **the two-step method for cleaning up "Lua errors"** {#95-这一轮新增的经验把lua-报错清干净的两步法}

1. **Log measurement**: normalize and group the error lines of `ds_debug.log` (strip line numbers/paths/numbers), and sort by count.
   ⚠️ **`Lua initialized` appears twice per map load: the server first, then the client**; the criterion is whether that block contains
   `lua/autorun/client -> N file(s)` (only the client block prints that).
2. **Static scan as a backstop** (the log only proves paths that were "reached"):
   `D:\project\luacheck\scan_weapon_methods.py` —— it extracts every
   `obj:Method(` call in weapon/entity/effect scripts, subtracts "engine registration names (the binding table `{"X", fn}` + `lua_setglobal` + `lua_setfield`)"
   and "any Lua definition in the content repo", and what is left is the candidate gaps.

   ⚠️ Known sources of false positives (these names are **generated at runtime**, so the script cannot see them):
   - `AccessorFunc( ENT, "m_x", "X" )` → `GetX`/`SetX`
   - `SWEP:NetworkVar( "Float", 0, "Zoom" )` → `GetZoom`/`SetZoom`
   - `gmod_compat.lua`'s `Alias( entmeta, "EntIndex", entmeta.entindex )`

**The real gap it caught this round**: `ent:GetInternalVariable( "m_takedamage" )` at
`weapon_medkit/shared.lua:117` —— `CanHeal()` calls it on every heal, and only when the trace came back empty
(`ent` is NULL) is it blocked by `ent:IsPlayer()`, so **healing a live player/NPC always throws**,
while it was 0 times in the log (all historical heals landed on a NULL trace). Now bound (commit `7f8fc863`),
implemented as `GetDataDescMap()` + the `baseMap` chain (the same technique as `GetKeyValue`),
and a nonexistent name/array/`FIELD_EMBEDDED`/function pointer all push `nil`.

### 9.6 New lessons from this round: **a class of "dead code" trap that shows up in the log** {#96-这一轮新增的经验日志里会出现的一类死代码陷阱}

⚠️⚠️ **`lua/includes/extensions/gmod_globals.lua` has a bare `return` on the server**
(at the end of the `if ( not _CLIENT )` block): **code written after it never executes on the server.**
Last round I added the server-side `render`/`net.Receive` stubs at the **end of the file** → they had no effect at all,
and the log proved it: "gmod_globals is loaded, but the two errors `properties.lua:175` / `halo.lua:7` are still there".
**This class of "the file is loaded but the errors are still there" can only be found via the log; just reading the Lua will not show it.**

Other cases of the same kind:
- `lua/includes/modules/*.lua` is **loaded by both realms** → a client-only library
  (`halo` / `properties`) must use `if ( CLIENT )` in the file or add a server-side stub, otherwise one red line per map load.
- `hook.lua` **permanently unregisters** the hook as soon as it errors → the HUD stops drawing forever once it throws for a single frame (after fixing it, the map must be re-entered).
- `hook.call` with a same-named event looping on itself = hang (a re-entry guard has been added).
- `lua/includes/modules/*.lua` gets **executed twice** → do not write `X = X or <definition in this file>`.

### 9.7 Not done yet (by priority, for the next session to pick up) {#97-还没做的按优先级供下一次接着干}

1. **`matproxy` bridge** (GMod's **Lua material proxy**; right now two
   `proxy "PlayerWeaponColor" not found!` lines on every load). ⚠️ Key fact: **`PlayerWeaponColor` cannot be found by searching GMod's own `bin/*.dll`**
   —— it really is `lua/matproxy/player_weapon_color.lua`
   (`matproxy.Add{ name=..., init=..., bind=... }`, writing `resultVar $selfillumtint`).
   This repo's `lua/includes/modules/matproxy.lua` **exists but is completely dead code** (its comment says
   "Called by engine", yet the engine never calls it). Fixing it needs three things done together:
   - engine bridge: in `CreateProxy`, first ask `matproxy.ShouldOverrideProxy(name)`,
     and on a hit create an `IMaterialProxy` (`Init` → `matproxy.Init(name, uname, mat, values)`,
     `OnBind` → `matproxy.Call(uname, mat, ent)`). ✅ Viable path:
     `GetMaterialProxyFactory()` / `SetMaterialProxyFactory()` are **on the public interface
     `IMaterialSystem`**, and the client **already has a precedent** ——
     `CPlayerColorProxyFactory` in `game/client/c_viewmodel_attachment.cpp`
     is exactly the "wrap the old factory, keep the chain" style; just extend it, **no need to rebuild engine.dll**.
   - `IMaterial:SetVector( name, vec )` (`public/lua/materialsystem/limaterial.cpp` already has 46 native methods; what is missing is the whole **material variable read/write** family: `SetVector`/`SetFloat`/`SetInt`/`SetString`/`SetMatrix`/`SetTexture` are all absent — see [IMaterial §7](imaterial.html#7-与-gmod-的差异-注意)).
   - `Player:GetWeaponColor()` / `SetWeaponColor()` (the engine has nothing at all; in GMod it is a **networked** variable).
2. **NPC `m_iMaxHealth` and client `m_takedamage`** (this round only networked the player, commit `50d1f475`).
   To fully align with GMod, add it on `DT_BaseEntity` (GMod's client.dll has both strings),
   or add it to NPC/the shared table. ⚠️ Adding it on `DT_BaseEntity` = one more prop per entity; the bandwidth cost is yours to weigh.
3. **`HL2SB_PrecacheOnce` is a process-level cache** (512-name cap): `util.PrecacheModel` can therefore
   skip re-precaching on later maps. `HL2SB_PrecacheForget` has been added so that **failed** precaches can be retried,
   but **ones that already succeeded** still do not get redone per map.
4. **Derma control Lua dispatch**: `LCheckButton` / `LTextEntry` / `LEditablePanel` are still not filled in
   (affecting DCheckBox / DTextEntry / DPropertySheet).
5. **Rainbow beam** (`render.DrawBeam`): all the chain data is correct (the TE arrived, the effect was created, 89 frames,
   `Render` was called, the material has `error=0`, the geometry is in front of the view), and there is still nothing on screen.
   Already ruled out: `CBeamSegDraw` only accepts sprite-family materials (§10.4); `GetDynamicMesh` without a material = the vertex format is wrong.
   It has been changed to a hand-built camera-facing quad + passing the material, and it still does not show. **The next step should be to swap in a material
   known to display (for example `sprites/redglow1.vmt`) for a control experiment**, confirming "it can display" first before going back to check the rainbow texture.
6. `lrender.cpp`'s `s_MatCache` / `g_pHL2SBLastBoundMaterial` **only add references and never release them** (permanently pinning the material);
   `c_te_effect_dispatch.cpp`'s debug name list is a fixed 8 slots, and from the 9th effect on it stops reporting.
7. `AGENTS.md` has **exceeded the harness instruction budget** (150 KB vs the 65 KB cap; roughly after line 700 it is no longer auto-loaded).
   Either write new conclusions earlier in the file, or merge and compress the batch of stable sections in §5.

### 9.8 v3 addendum checklist (supplementing the §6 table) {#98-v3-追加勾选补-6-的表}

- [x] Engine: `vgui.GetAll()` (panel registry)
- [x] Engine: `GetConVar_Internal` / library alias merging / `lua/includes` loaded by name
- [x] Engine: `surface.CreateFont(name, FontData)` / `DrawTexturedRectRotated` / `DrawTexturedRectUV`
- [x] Engine: PNG texture fallback + `IMaterial:GetColor` sampling
- [x] Engine: Derma docking (`DOCK_*` + `Panel:Dock` algorithm)
- [x] Engine: Lua SWEP runtime (`Think`/`Tick`/`ItemPostFrame`/`SetupDataTables`/`NetworkVar`)
- [x] Engine: `game.AddAmmoType` → `CAmmoDef` bridge
- [x] Engine: `Entity:GetCurrentCommand` (GMod `cmd:` snapshot) / `IsConstraint` / `SendLua` / `GetInternalVariable`
- [x] Engine: a NULL entity returns `false` for all methods (GMod semantics)
- [x] Engine: player `m_iMaxHealth` networked (`DT_BasePlayer`, send/recv in the same position)
- [x] Engine: `util.PrecacheSound` retry on failure + one-time warning for a missing soundscript
- [x] Engine: `TE_HL2MPFireBullets` with a tracer name (send/recv aligned)
- [x] Content: server-side `render` / `net.Receive` stubs (placed **before** the bare `return` in `gmod_globals.lua`)
- [x] Content: Nyan Gun plugin (crash/icon/ammo/material/trail)
- [x] Content: `pist_weagon` (The Ultimate Admin Gun Fixed) original runs unchanged
- [ ] Engine: `matproxy` bridge + `IMaterial:SetVector` + `Player:GetWeaponColor`
- [ ] Engine: NPC `m_iMaxHealth` / client `m_takedamage` networked
- [ ] Engine: rainbow beam (`render.DrawBeam`)
- [ ] Engine: Lua dispatch for `LCheckButton` / `LTextEntry` / `LEditablePanel`

