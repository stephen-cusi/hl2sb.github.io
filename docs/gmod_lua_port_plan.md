# GMod Lua 移植计划 v2 — HL2SB

> 撰写 2026-09-11。**v1 的策略已作废**，见下面「策略变更」。
> 路径基准：`D:\srceng\hl2sb\lua`（下面相对路径都相对它）。
> 引擎侧基准：`D:\project\source-engine`。
>
> ⚠️ **2026-09-13 增补**：**最新的进度盘点与经验在 [§9](#9-移植状态与经验v3-增补2026-09-12--09-13)**。
> §1–§8 是 09-11 的规划视角（缺口 → 落点映射），仍然有效但**不再反映已完成情况**；
> **想知道"现在到哪一步了 / 还有什么坑"直接读 §9**。
> 引擎侧的逐条硬事实另见 `D:\project\source-engine\AGENTS.md`。

---

## 0. 策略变更（v1 → v2）

| | v1（作废） | **v2（本版）** |
|---|---|---|
| 总方针 | 「移植到 HL2SB，但**用 HL2SB 的 Lua 风格**」 | **GMod 的 Lua 原样拿过来，尽量零改写** |
| 缺函数怎么办 | 在 Lua 侧写 shim / 换 HL2SB 写法 / 干脆不做 | **在引擎 C++ 侧补绑定** |
| 判定标准 | 能不能用 HL2SB 现有原语表达 | **能不能让 GMod 原文件一行不改跑起来** |

**为什么 v2 成立**：这个仓库是**完整引擎源码**，不是 SDK2013 那种闭源壳。
`D:\project\source-engine` 有 **74 个顶层模块**、其中 **36 个带 `wscript`** 可独立编译：

```
engine  vgui2  vguimatsurface  materialsystem  studiorender  filesystem  inputsystem
tier0  tier1  tier2  tier3  mathlib  vphysics  soundsystem  soundemittersystem
datacache  vpklib  vtf  bitmap  choreoobjects  dmxloader  particles  scenefilecache
unicode  unitlib  video  appframework  datamodel  serverbrowser  stub_steam  togl/togles
launcher  launcher_main  dedicated  dedicated_main  gameui  lua
```
另外 `thirdparty/` 里有 **curl**、SDL、mbedtls 等。
**结论**：GMod 的 Lua 之所以「缺函数」，几乎每一项都能在引擎里找到对应模块去实现
（`surface.*` → `vguimatsurface`、`render/cam.*` → `materialsystem`、`file.*` → `filesystem`、
`net.*` → `engine/net_chan` + `tier1/bitbuf`、`http.*` → `thirdparty/curl`……）。
**把改写工作从 Lua 挪到 C++，收益是：GMod 文件可以整目录拷，而且以后所有 GMod addon 一起能用。**

**唯一"允许改 Lua"的情况**：GMod 文件里写死了 HL2SB 物理上不存在的东西
（例如 GMod 的 `net.Receive` 事件名、`util.AddNetworkString` 的注册时机）。
这类改动必须 **`-- HL2SB:` 注释标明 + 尽量只在文件头做适配**，并登记到本文件的 §5。

---

## 1. 环境对照（**已更正**，v1 这里全错）

| 维度 | GMod | HL2SB（真实） | v1 写的 |
|---|---|---|---|
| Lua 版本 | LuaJIT 2.0（GLua 扩展） | **Lua 5.4.6**（`lua/src/lua.h:25 LUA_VERSION_NUM 504`），带 GLua 语法扩展（`continue` / `!` / `!=` / `&&` / `\|\|` / `//` / `/* */`）和**从 5.1 回移**的 `module()`+`package.seeall` | ❌ 写成 5.1 |
| `autorun` | 加载 | **加载**（`luasrc_dofolder_sorted()`：`lua/autorun/*.lua` 不递归 + `client|server/**` 递归，按文件名 A-Z） | ❌ 写成不加载 |
| `utf8` 库 | 自己的 `utf8.lua` | **原生有**（`linit.c:51 luaopen_utf8` + `lua/src/lutf8lib.c` 在编译列表里） | ❌ 说要自写 len/sub |
| `Color` | table，`.r/.g/.b/.a` 是字段 | **table，`.r/.g/.b/.a` 就是数字字段**（`public/lua/lColor.cpp:41-44` + `:164-175`）。大写 `col:GetR()` 等是方法 | ❌ 写成 userdata + 方法 |
| 模块机制 | `module("x")` + 全局 `x.*` | 同 | ✅ |
| 编码 | 随意 | **UTF-8 无 BOM**（`resource/*.txt` 例外：UTF-16LE+BOM） | ✅ |

> ⚠️ **v1 的 §0「关键结论」整段建立在 5.1 上，已失效。** 5.1→5.4 的差异（`luaL_checkint`
> 不再接受小数、`unpack`→`table.unpack`、`setfenv/getfenv` 移除等）都已经被引擎/兼容层处理过，
> 详见 `AGENTS.md` §5.4 的「Lua 5.4 最坑的一处迁移差异」。

---

## 2. 现状盘点：GMod 的 Lua 树 vs 我们

### 2.1 GMod 侧体量（拿来多少）

| 目录 | .lua 数 | 用途 |
|---|---|---|
| `lua/includes/modules/` | 38 | 库（`hook`/`net`/`file`/`render`/`draw`…） |
| `lua/includes/extensions/` | 29（含子目录） | 扩展（`string`/`table`/`math`/`player`/`ents`/`util`/`panel`…） |
| `lua/vgui/` | **93** | Derma 控件 |
| `lua/derma/` | 7 | Derma 框架本体 |
| `lua/skins/` | 1 | 默认皮肤 |
| `lua/menu/` | 27 | 主菜单 |
| `lua/autorun/` | 35 | 自动加载 |
| `lua/postprocess/` | 14 | 后处理 |
| `lua/entities` `weapons` `drive` `matproxy` | 6/3/3/3 | 脚本实体/武器 |

### 2.2 `includes/modules` 机械差集

**两边同名（10）**：`baseclass` `concommand` `draw` `gamemode` `hook` `killicon` `list` `player_manager` `team` `undo`

**GMod 有、我们没有（28）**：
`ai_schedule` `ai_task` `cleanup` `constraint` `construct` `controlpanel` `cookie` `cvars`
`drive` `duplicator` `effects` `halo` `http` `markup` `matproxy` `menubar` `notification`
`numpad` `presets` `properties` `saverestore` `scripted_ents` `search` `spawnmenu`
`usermessage` `utf8` `weapons` `widget`

**我们自造、GMod 没有（11）**：
`ammo` `cvar` `entity` `gmod_compatibility` `gmod_vgui` `hl2sb_lua_errors`
`language` `resource` `save` `timer` `weapon`

> 🔎 **注意「同名 ≠ 同内容」**：`draw`/`hook`/`killicon`/`team`/`list`/`undo`/`gamemode`/`concommand`
> 现在都是**我们改写过的版本**。按 v2 策略，这些要**逐步换回 GMod 原文件**（前提是先把它们依赖的
> 绑定补齐），否则永远是"像 GMod 但不是"。

### 2.3 `includes/extensions` 差集

**GMod 有、我们没有（12）**：
`angle` `coroutine` `debug` `entity_iter` `ents` `file` `game` `motionsensor`
`player_auth` `player` `util` `vector`

**我们自造的兼容层（7）**：
`gmod_compat` `gmod_globals` `gmod_surface` `gmod_util` `keyvalues` `panel` `vgui`

> 🔎 自造兼容层的定位：**临时脚手架**。每补好一个引擎绑定，就删掉对应的 shim，
> 最终目标是「引擎绑定 = GMod 语义；Lua 侧 = GMod 原文件」。

### 2.3.1 ⚠️ 已经在仓库里、但**关着**的那套：`gmod_compatibility/`

`lua/includes/modules/gmod_compatibility/` 是从 **Experiment: Source** 整包 vendored 过来的
GMod 兼容层，规模不小：

| 文件 | 大小 | 内容 |
|---|---|---|
| `sh_init.lua` | **67 KB** | `bit`/`gamemode`/`hook`/`timer`/`net`/`DeriveGamemode`/`include`/`Msg`/`jit` 桩、`util.*`（Precache/TraceLine/JSON/CRC…）、`ents.*`（Create/GetAll/FindByClass/FindInSphere…）、`player`、`sql`、`FindMetaTable`/`RegisterMetaTable` |
| `sh_enumerations.lua` | 17 KB | `_E` 各枚举表 |
| `sh_color.lua` / `sh_file.lua` / `vgui_base.lua` / `cl_awesomium.lua` | 小 | 分块补齐 |

入口 `lua/includes/modules/gmod_compatibility.lua` 被
**`GMOD_COMPATIBILITY = GMOD_COMPATIBILITY or false`** 关着 —— 因为它的开头是
`require("bitwise") / require("gamemodes") / require("hooks") / require("timers")`，
这四个名字在我们这儿不存在（我们是 `bit` 库 / `gamemode.lua` / `hook.lua` / `timer.lua`）。

**处置（按 v2 策略）**：**不复活它**。它是 Experiment 的**重命名式**兼容层
（`net = Networks`、`player = Players`、`include = Include`），与 HL2SB 的路线
（**保留 GMod 原生名字 + 引擎补绑定**）冲突，两套并存只会互相打架。
但它是**极佳的「GMod 代码到底需要什么」清单**，排缺口时当参考读。


### 2.4 已经完成的引擎侧绑定（`luasrclib.h` / `lsrcinit.cpp`）

`surface` `vgui` + `Panel` `Label` `TextEntry` `Button` `EditablePanel` `CheckButton` `Frame`
`PropertyDialog` `PropertyPage` `ModelPanel`、`Color` `Vector` `QAngle` `matrix3x4_t` `vmatrix`、
`CTakeDamageInfo` `CEffectData` `CGameTrace` `CRecipientFilter` `CPASFilter`、
`CBaseEntity`/`_shared` `CBasePlayer`/`_shared` `CBaseCombatWeapon` `CBaseAnimating`/`_shared`
`CBaseFlex_shared` `CHL2MP_Player`/`_shared`、`ConCommand` `ConVar` `cvar` `FCVAR`、`dbg`
`debugoverlay` `engine` `enginevgui` `filesystem`(Files/FileHandle) `gpGlobals` `input`
`GameEvents`(gameevent.Listen) `gEntList` `hl2sb` `IMaterial` `Localizations`
`networkstringtable` `net` `physenv` `prediction` `random` `scheme`(IScheme/HScheme/HFont)
`steamapicontext` `UTIL` `system`、`ScriptedEntities`、共享枚举 `_E`（`ACTIVITY`/`BUTTON`/`FL`/`LIFE`/…）

---

## 3. 缺口 → **引擎落点**映射（本版核心）

> 读法：左列是 GMod Lua 直接调用的东西；中列是它落在引擎哪个模块；
> 右列是「原文件能不能直接拷」的判定。

### 3.1 绘制 / UI

| GMod 需要 | 引擎落点 | 说明 |
|---|---|---|
| `surface.DrawTexturedRectRotated( x,y,w,h,rot )` | `public/lua/vgui/LISurface.cpp`（**client.dll**）→ 用现成的 `ISurface::DrawTexturedPolygon`（`public/vgui/ISurface.h:311`） | ⚠️ `x,y` 是**中心**。**不用动 ISurface 虚表**，只重编 client.dll。详见 `D:\project\_session_extract\圆角HUD改动清单.md` |
| `surface.DrawTexturedRectUV( x,y,w,h,u0,v0,u1,v1 )` | 同上（现在 `gmod_surface.lua` 用 `DrawTexturedSubRect` 拼的，可下沉到 C++） | `DrawTexturedSubRect` 的 UV 已是 0..1 归一化（`MatSystemSurface.cpp:1655`） |
| `surface.DisableClipping( bool )` / `EnableClipping` | `vguimatsurface/MatSystemSurface.cpp`（**要加虚函数 + bump `VGUI_SURFACE_INTERFACE_VERSION`**，全量重编） | 路线 C，成本高。`draw.*`/两个 HUD 不需要它，**先不做** |
| `surface.CreateFont( name, {font=,size=,weight=,antialias=,extended=} )` | 现可 Lua 包（`CreateFont()+SetFontGlyphSet()`），或下沉到 `LISurface.cpp` | Derma 大量用「字符串字体名 + 表参数」，**必须补** |
| `surface.SetFont( name )` 返回值当句柄用 | **已做**（`LISurface.cpp`，提交 `23d472d6`） | — |
| `surface.GetTextSize( text )` 一参数形态 | Lua 层即可，但要放 **`lua/autorun/client/`**（在 `font.lua` **之后**） | `font.lua` 现在把它重定义成 `(font, text)` |
| `draw.NoTexture()` / `draw.RoundedBox` 的 corner 路径 | `lua/includes/modules/draw.lua`（GMod 原版可直接拷，仅需上面两个 surface 函数就位） | 现在 `RoundedBoxEx` 被改成实心矩形，见 §5 |
| `draw.GetFont` / `draw.GetFontHeight` | 需要 `surface.GetFontHeight`? → GMod 是从 `surface.GetTextSize`/FontMetrics 拿的 | 已做（`draw.lua` 有 `GetFont`） |
| `render.*`（`SetDrawColor`/`SetMaterial`/`DrawTexturedRect`/`CullMode`/`SetRT`/`OverrideBlend`…） | **新** `game/client/lua/lrender.cpp` → `IMaterialSystem` + `IMatRenderContext`（模块 `materialsystem`） | `luasrclib.h` 已有 `Renders` 名，但注册表里没看到实现 → 需新建 |
| `cam.*`（`Start3D`/`End3D`/`Start2D`/`End2D`/`Start`/`End`） | 同上（`lrender.cpp` 或 `lcam.cpp`） | 依赖 `IMatRenderContext::Push3DView` |
| `view.*`（`RenderView`/`GetViewModel`） | `game/client/lua/` | 低优先级 |
| `vgui.Create` / `vgui.Register` / `vgui.GetControlTable` | **已有一版**（`gmod_vgui.lua` + C++ `game/client/lua/scripted_controls/LPanel : public vgui::Panel`） | 需要跟 GMod 的 `scriptedpanels.lua` 对齐（`GetTable` vs `GetRefTable`、`CreateFromTable`、`vgui.Exists`…） |
| `DisableClipping`（Derma 用） | 见上 | —— |
| `ModelImage` / `SpawnIcon` 的模型缩略图 | `game/client` 的 `CModelPanel`/`CModelImage`（`vgui_controls`） | GMod 是运行时渲染，HL2SB 缺绑定；玩家模型菜单已踩过 |
| `surface.GetTextureID` / `SetTexture` / `DrawRect` / `SetDrawColor` / `SetTextColor` / `SetTextPos` / `DrawText` / `Material(path)` / `DrawTexturedRectUV` | **已在** `lua/includes/extensions/gmod_surface.lua`（Lua 层） | 长期应下沉到 C++，但**能用** |

### 3.2 网络

| GMod 需要 | 引擎落点 | 说明 |
|---|---|---|
| `net.Start/Write*/Read*/Send/Receive/Broadcast` | `game/shared/lua/lnet.cpp`（**已有雏形**：自建 usermessage `"LuaNet"`）→ 扩成 GMod 语义 | 底层用 `bf_write`/`CBaseClient`/`engine/net_chan`（模块 `engine`、`tier1`）。`extensions/net.lua` 已有 |
| `util.AddNetworkString` | **已 shim**（`gmod_util.lua:85`）→ 长期移到 C++ | — |
| `usermessage.Hook` / `SendUserMessage` | 同上（GMod 的 usermessage 是 net 的特例） | — |
| `net.ReadHeader` / `MAX_EDICT_BITS` 等常量 | `public/const.h` 等 | — |

### 3.3 文件 / 网络 IO

| GMod 需要 | 引擎落点 | 说明 |
|---|---|---|
| `file.Read/Write/Exists/Delete/Find/Time/Open/Size` | `public/lua/lfilesystem.cpp`（**已实现**：`file.Find` 在 `:1169`，注册进 `file_funcs[]` 在 `:1414`，`luaopen_Files` 在 `:1419`；GMod 拼写别名 `file` 在 `lsrcinit.cpp:553`） | ✅ GMod 的路径语义已经映射完（`s_GModPathIDs` `:618`：`DATA` → `MOD` + `data/` 前缀、`LUA` → `GAME` + `lua/` 前缀、非法 pathID → `nil, nil`）。`file.Find` 的签名 / 默认 `nameasc` / 两个返回值与上游一致，差异（addon 标题 ID 不支持、`MOD` 含 addons、无 realm 区分）逐条记在 [file.Find](file_find.html) |
| `http.Fetch/Post`、`HTTP()` | **`thirdparty/curl` 已在仓库里**；落 `game/client/lua/lhttp.cpp` + 主线程回调队列 | GMod 的 `http` 是异步 + `onSuccess/onFailure` |
| `cookie.*` | 同上 / `steamapicontext` 的 ISteamUser + `filesystem` | — |
| `util.TableToJSON` / `util.JSONToTable` | 引擎里已有 JSON（`tier1` 有 `CUtlBuffer`+JSON? 需查）或绑 `thirdparty` | — |

### 3.4 实体 / 玩家 / 队伍

| GMod 需要 | 引擎落点 | 说明 |
|---|---|---|
| `ents.GetAll` / `FindByClass` / `FindByName` / `Iterator` / `Create` | `game/server`+`game/shared` 的 `gEntList`（模块已有 `Entities` 表）→ 补 `ents.*` 别名 | `gEntList` 现有 `FirstEnt/NextEnt/FindEntityByClassname/FindEntityByName`；`ents.Create` 走 server 的 `CreateEntityByName` |
| `player.GetAll` / `Iterator` / `GetBySteamID*` | `game/shared/lua/lbaseplayer_shared.cpp` | `player.GetAll` **已做**；其余补 |
| `team.*` | `game/shared/hl2mp/hl2mp_gamerules.cpp`（HL2MP 有队伍）+ Lua 层 | `team.lua` 已有半成品 |
| `scripted_ents.Register/Get/GetStored` / `weapons.*` | `game/shared/lua/basescripted.cpp` + `weapon_hl2mpbase_scriptedweapon.cpp` | 我们已有等价注册表（`ScriptedEntities` 库）→ 补 GMod 名字 |
| `halo.Add/Render`、`effects.Create/Register` | `game/shared` 的 `CEffects` + temp entity | `Effects` 库已有（server） |
| `util.TraceLine(表)` | `lgametrace.cpp`（**已有 GMod 字段别名**） | 只差「表参数」形态 |
| `Entity:CallOnRemove` / `entmeta:*` | **已 shim**（`gmod_util.lua:121`，靠 `EntityRemoved` 钩子） | 长期移到 C++（`CBaseEntity::OnRemove`） |
| `ents.FindInSphere/Box` 等 | `game/server` | — |

### 3.5 明确**不做**（或不在 Lua 层做）

| 项 | 原因 |
|---|---|
| `matproxy.lua` | GMod 的 matproxy 是**引擎 C++ 注册的 proxy** + LuaJIT。照搬 Lua 没用；要用 `game/client` 的 `IMaterialProxy` 自己实现（我们已有 `CPlayerColorProxy` 先例） |
| `utf8.lua`（GMod 那份） | **不需要**。Lua 5.4 原生 `utf8` 库已在（`linit.c:51`） |
| `lua/menu/**`（27 个） | 是 GMod 主菜单（GameUI 域）。可以做，但和 HL2SB 自己的菜单冲突，**最后再说** |
| `lua/postprocess/**`（14 个） | 依赖 `render.*` + `DrawColorModify` 全家桶 → **`render.*` 做完才轮到它** |
| `saverestore` / `duplicator` / `presets` / `cleanup` | 依赖实体序列化 + Derma UI；排在 Derma 之后 |
| `drive` / `numpad` / `properties` | 依赖驾驶/物理/输入绑定；低价值 |

---

## 4. UI 路线（`vgui` + `derma` + `skins` = 101 个文件）

这是「GMod 原样跑」的最大一块，也是最能体现 v2 策略价值的地方。

**已经有的地基**（前面调研确认）：

| 层 | 现状 |
|---|---|
| C++ 面板基类 | ✅ `game/client/lua/scripted_controls/LPanel : public vgui::Panel`（真 vgui2 派生） |
| C++ 具体控件 | ✅ `lButton` `lLabel` `lTextEntry` `lFrame` `lCheckButton` `lModelPanel` `lPropertyDialog` `lPropertyPage` |
| C++ vgui 库导出 | ✅ `luaopen_vgui` 逐个导 `Button/EditablePanel/Panel/CheckButton/Frame/PropertyDialog/PropertyPage/ModelPanel` |
| Lua `vgui.register` | ✅ Team Sandbox 版（`lua/includes/extensions/vgui.lua`） |
| GMod 拼写 + 最小 Derma | ✅ `lua/includes/modules/gmod_vgui.lua`（`vgui.Register`/`vgui.Create`/`derma.DefineControl` + 最小 DPanel/DFrame/DLabel/DTextEntry/DButton） |

**要补的（按依赖顺序）：**

1. `surface.CreateFont( name, table )`（GMod 形式）—— Derma 全局依赖
2. `surface.DrawTexturedRectRotated`（§3.1）—— 圆角
3. `vgui.Create/Register` 与 GMod `scriptedpanels.lua` **语义对齐**：
   - `panel:GetTable()` vs 我们的 `GetRefTable()`（加别名即可）
   - `baseclass.Set/Get`（我们已有）
   - `vgui.CreateFromTable` / `vgui.RegisterTable` / `vgui.RegisterFile` / `vgui.Exists`
   - ⚠️ `vgui.Frame` 的 metatable 在本引擎**不带 Panel 方法** → 要么修 C++，要么 `DFrame` 走 `Panel` 基类（现在 `gmod_vgui.lua` 就是这么绕的）
4. `DisableClipping`（Derma/`dragdrop`/`dnumberwang` 用）—— 需要路线 C（改 ISurface）
5. `derma.DefineSkin` / `SkinHook` / `lua/skins/default.lua`
6. 然后 **`lua/vgui/*.lua`(93) + `lua/derma/*.lua`(7) + `lua/skins/*.lua` 整目录原样拷**

> 只需先打通 1–5，之后 101 个文件是**复制粘贴**，不是改写。这就是 v2 的价值。

---

## 5. 关键更正 & 待办修正（相对 v1 / 相对现状）

### 5.1 v1 的错误（已在本版修正）

1. **Lua 版本 5.1 → 5.4.6**（连带：`uv`/`unpack`/`setfenv` 等 5.1 假设全部作废）
2. **`autorun` 现在会加载**（旧文写"不会被加载"，且据此让所有脚本避开 autorun）
3. **`Color` 是 table 不是 userdata**（旧文 §「关键坑备忘」教的 `col:r()` 写法是错的，
   直接 `col.r` 拿数字就对）
4. **`utf8` 不需要移植**（5.4 原生）
5. `surface.GetTextureID / SetTexture / DrawRect / DrawTexturedRectUV / Material()` **已就位**
   （只剩 `DrawTexturedRectRotated`）
6. `killicon` / `resource` / `list` / `team` / `baseclass` / `timer` / `net.lua` /
   `hook.Add`+`Remove`+`GetTable` / `gameevent.Listen` **已就位**

### 5.2 现存但行为不完整的（v2 要修）

| 项 | 现状 | 要改成 |
|---|---|---|
| `draw.RoundedBoxEx` | ✅ **已修**（提交 `976e52d`）：GMod 原版 body + 四角 `DrawTexturedRectUV`。旧版"整块变白"的根因就是**画贴图前没 `surface.SetTexture`**，绑的还是引擎默认白贴图 | —— |
| `hl2sb_cl_hudpickup.lua` | ✅ **已修**（提交 `976e52d`）：GMod 原版 4×`DrawTexturedRectRotated` + 4×`DrawRect`；`GM.PickupHistoryCorner` 也照 GMod 设了 | —— |
| `DermaDefault` / `DermaDefaultBold` | ✅ **已修**（提交 `976e52d`）：在 `gmod_vgui.lua` 里按 GMod 的 `lua/derma/init.lua` 用 `surface.CreateFont(name, FontData)` 建；拾取 HUD 不再映射成 `Default` | —— |
| `draw.lua` / `hook.lua` / `killicon.lua` / `team.lua` / `list.lua` / `undo.lua` / `concommand.lua` / `gamemode.lua` | 都是**改写版** | 逐步换回 GMod 原文件（前提是 §3 的绑定就位） |
| 自造兼容层（`gmod_globals` / `gmod_util` / `gmod_surface` / `gmod_compat` / `gmod_vgui` / `panel` / `vgui` / `resource` / `language` / `save` / `timer` / `ammo` / `cvar` / `entity` / `weapon`） | 临时脚手架 | 每补好一个引擎绑定就删一个 |

### 5.3 必须记住的引擎侧坑（详见 `AGENTS.md` §5.4）

- `RETURN_LUA_*` 宏已从「`lua_gettop(L) == 1` 绝对判断」改成 `> 0`（修栈泄漏）
- `m_nTableReference` 双重 unref 已修（游戏内突然崩溃的头号根因）
- Lua 5.4 的 `luaL_checkint` 已改成接受浮点（否则 HUD 每帧抛错、静默不画）
- `hook.lua` 出错即**永久注销**钩子；`hook.call` 同名事件自环会卡死（已加守卫）
- `lua/includes/modules/*.lua` 会被**执行两次** → 不要写 `X = X or <本文件定义>`
- 改 `lua/includes/modules/*.lua` 必须**完全重启游戏**（模块重入守卫）
- 新 `.cpp` 必须进对应 `.vpc`，否则进不了 build（`AGENTS.md` §2）

---

## 6. 执行顺序（v2 版勾选表）

> `[x]` 已完成并验证 / `[~]` 已写未验证 / `[ ]` 未动

### P0 — 让「GMod 原文件」能跑起来的地基

- [x] 引擎：Lua 5.4.6 + GLua 语法（`continue` / `!` / `!=` / `&&` / `||` / 注释）
- [x] 引擎：`luaL_checkint` 接受浮点（`lua/etc/lua.hpp`）
- [x] 引擎：`RETURN_LUA_*` 栈泄漏修复（`luamanager.h` 25 处）
- [x] 引擎：`m_nTableReference` 双重 unref 修复
- [x] 引擎：`autorun` 加载 + 排序（`luasrc_dofolder_sorted()`）
- [x] 引擎：全局 `IsValid` / `player.GetAll` / `player:UniqueID()`
- [x] 引擎：`surface.SetFont(name)`、`surface.GetTextSize` 的 ANSI→Unicode 修复
- [x] 引擎：`gameevent.Listen`
- [x] Lua：`string` / `table` / `math` 扩展
- [x] Lua：`hook.Run` / `hook.Add` / `hook.Remove` / `hook.GetTable`
- [~] Lua：`gmod_globals.lua`（`CurTime`/`ScrW`/`ScrH`/`CreateConVar`/`GetConVar*`/`Sound`/`Model`/`Angle`/`ACT_*`）→ **长期应下沉到 C++**
- [x] **引擎：`surface.CreateFont( name, table )`（GMod 形式）** ← Derma 前置
      引擎提交 `85333918`。实现 `FontData` 全部字段；句柄存进**每个 Lua state 的
      registry 名字表**，`surface.SetFont(name)` 先查它再查 scheme。旧的无参形态保留。
- [x] **引擎：`surface.DrawTexturedRectRotated`**（`LISurface.cpp`，走 `DrawTexturedPolygon`）
      引擎提交 `85333918`。`x,y` 是**中心**、角度制、屏幕逆时针。
      只重编 client.dll，**没动 ISurface 虚表**。
- [x] **引擎：`surface.DrawTexturedRectUV`**（同上，转 `DrawTexturedSubRect`）—— Lua shim 里的那份改为不生效
- [x] **引擎：按名字加载 `lua/includes/init.lua`**（GMod 的 bootstrap）+ 加载失败可诊断
      ~~引擎提交 `1991571d`~~ → **已被 `ab073409` 取代**：原来用
      `luasrc_dofolder_sorted( L, LUA_PATH_INCLUDES, false )` **扫目录**，而 `init.lua`
      自己就 include 了 `util.lua` 和 `vgui_base.lua` → 这两个被跑**第二遍**，
      第二遍 `vgui_base.lua` 让 54 个 `lua/vgui/*` 全部走进
      `derma.DefineControl` 的「重载」分支 → `ReloadClass()` → `vgui.GetAll()`（当时不存在）
      → **54 行 FAILED、一个控件都没注册上**。
      现在用 `luasrc_dofile_includes( L, "init.lua" )`（`luamanager.cpp`），两个 realm 都按名字加载。
      ⚠️ **教训**：`init.lua` 里的 include 列表 = 唯一的加载清单；往里加文件要改 `init.lua`，
      不能靠目录扫描「顺便」加载。
- [x] **引擎：服务端也加载 `lua/includes/init.lua`，但 client-only 部分要 `if ( CLIENT )` 挡**
      引擎提交 `ab073409`（游戏侧 `lua/includes/init.lua` 提交 `25f059f`）。
      服务端原本跑 derma/vgui_base，而 `derma/init.lua` 第 24 行就索引 `surface`（服务端为 nil）
      → 全局 `derma` 从未创建 → 54 个控件再报一遍 `(global 'derma')`。
      被挡的三个：`extensions/client/panel.lua`、`derma/init.lua`、`vgui_base.lua`。
      ⚠️ `util.lua` **不能挡**（服务端 `autorun/server/hl2sb_falldamage.lua` 要 `GetConVar`）。
      离线验证：`D:\project\luacheck\test_gmod_includes_server.lua`（6 项断言，含「client-only
      文件一个都不许进」的拒绝式断言）。
- [x] **Lua：GMod 的 `lua/includes/util.lua`**（逐字节拷贝，含 `AccessorFunc` /
      `FORCE_*` / `type` 谓词 / `Lerp` / `Either` …）—— 游戏提交 `c34b213`，
      离线验证 **45/45 全局齐全**（`D:\project\luacheck\test_gmod_includes.lua`）。
      `lua/includes/init.lua` 是**唯一**的改写点，头部已注明原因。
- [x] **引擎：GMod 的小写库全局名 + `include()` 搜索路径** —— 引擎提交 `47bbd18d`
      - `lsrcinit.cpp` 加 `luasrc_install_lib_aliases()`：把 `Systems`/`Files`/`UTIL`/
        `Renders`/`Sounds`/`Chats`/`ParticleSystems`/`ScriptedEntities` 别名成
        GMod 的 `system`/`file`/`util`/`render`/`sound`/`chat`/`particle`/`scripted_ents`
        （`Entities`/`player`/`gameevent` 早就在各自打开处别名了）
      - `luamanager.cpp` 的 `luasrc_include`：先按调用文件相对路径（**老行为不变**），
        再回落 `lua/` → `lua/includes/` → 裸路径。这是 `vgui_base.lua` 能 include
        `vgui/DFrame.lua`（真实位置 `lua/vgui/`）的关键
      - ⚠️ **`ab073409` 修正：别名必须「合并」，不能「按引用替换」。**
        `lua_setglobal` 版把 GMod 名的库整张顶掉，而两个 realm 拼写不一致
        （客户端 `lcdll_util.cpp` 注册 `UTIL`，共享 `lutil_shared.cpp` 注册 `util`）
        → 客户端 `util = UTIL` **删掉了** `util.PrecacheModel` / `PrecacheSound` /
        `TraceLine`，症状是 `util.lua:225: attempt to call a nil value (field 'PrecacheModel')`。
        **而那个 C 实现一直都在**（`lutil_shared.cpp:160`，注册在 `:214`）——
        查「字段是 nil」先怀疑有东西换了那张表。
        现在逐键 `lua_next` 合并（目标表已有的保留）。
- [x] **Lua：GMod 的 `lua/derma/`(7) + `lua/vgui/`(93) + `lua/skins/`(1) +
      `lua/includes/vgui_base.lua`** —— 游戏提交 `cc304ef`，**101 个文件全部哈希一致**。
      `lua/includes/init.lua` 按 GMod 的顺序接上：`util.lua` → `derma/init.lua` → `vgui_base.lua`
- [x] ~~⛔ 当前卡点：`vgui.Register: base class 'DLabel' does not exist`~~ —— **已解**
      游戏提交 `bef656b`：GMod 的 `lua/includes/extensions/client/` 整棵树已拷入并在
      `includes/init.lua` 里于 derma **之前**加载（`panel.lua` → `panel/scriptedpanels.lua`
      等 9 个文件）。GMod 的 `vgui.Register` 走 `PanelFactory` + `baseclass`，不再要求
      base 已注册进 `vgui[]`。`gmod_vgui.lua` 里的 `vgui.Register`/`Create` 已成为死代码
      （待删，见 P4）。
      ⚠️ 当时的另一层原因见上面 `ab073409` 那条（双载把 54 个控件逼进重载分支）。
- [x] **引擎：全局 `GetConVar_Internal( name )`** —— 引擎提交 `ab073409`
      （`public/lua/tier1/lconvar.cpp`）。GMod 的 `util.lua:572` 起**无条件**重定义
      `GetConVar` / `GetConVarNumber` / `GetConVarString` / `GetConVarBool`，内部调它
      （`:575`）→ 缺它就是 **击杀/死亡 HUD + undo 一起失效**。
      与 `ConVar(name, def, …)` 的区别：**不创建**（未知名字返回 nil，GMod 契约），
      且先查 `m_ConVarDatabase`（`luasrc_ConVar` 不调 `RegisterConCommand`，
      `FindVar` 找不到 Lua 建的 convar）。
      ⚠️ 只有 `tier1/lconvar.cpp` 参与编译，`public/lua/lconvar.cpp` 是死代码。
- [x] **引擎：`vgui.GetAll()`** —— 引擎提交 `ab073409`
      （`lvgui_controls.cpp`）：Lua registry 里一张**弱值**表，由 `vgui.Create` 分发追加。
      `derma.lua` 的 `FindPanelsByClass()` 重载控件定义时要它；addon 也用它找/关窗口。
      ⚠️ 修掉双载后它不再是致命路径（只有真重载才走 `ReloadClass`）。
- [ ] Lua：`surface.GetTextSize(text)` 一参数形态（放 `lua/autorun/client/`）
- [ ] 引擎：`Material()` 下沉为真正的 C 绑定（绑定后把 `lua/includes/` 挪回
      extensions **之前**，与 GMod 顺序一致；见两个调用点的 TODO(port)）
- [ ] 引擎：`CreateConVar` 做成真绑定（GMod 契约 `(name, default, flags, helptext, min, max)`）。
      现在的 Lua shim 是 `ConVar(name, def, flags, help, min, max)`，而引擎的 `ConVar` 是
      `(name, default, flags, help, **bMin, fMin, bMax, fMax**) —— `min`/`max` 数字落在布尔位上。
      **不崩**，只影响范围钳制。`util.lua` 的 `CreateClientConVar` 调的就是它。
- [ ] 引擎：`debug.Trace()`（GMod 的 `debug` 库有，我们的 `dbg` 库没有）。
      GMod 的 `util.lua` 在 `AccessorFunc(nil, …)` 的警告路径上会调它
      （`util.lua:270` 附近，报 `field 'Trace'`）。目前服务端不再加载 `panel.lua`，
      这条路径暂时踩不到。

### P1 — 绘制/HUD 收尾（可直接看到效果）

- [x] Lua：GMod 版 `killicon.lua` + `lua/game/client/gmod_deathnotice.lua`（游戏内验证）
- [x] Lua：GMod 拾取 HUD 主体（`hl2sb_cl_hudpickup.lua`）
- [x] `draw.RoundedBoxEx` 圆角 —— **恢复了**，游戏提交 `976e52d`（见 §5.2）
- [x] 拾取条换回 GMod 原版 8 行（4 角 + 4 边）—— 游戏提交 `976e52d`
- [x] `DermaDefault` / `DermaDefaultBold` / `DermaLarge` 字体 —— 走 GMod 的做法
      （`surface.CreateFont(name, FontData)`，写在 `gmod_vgui.lua`），不改 `clientscheme.res`
- [ ] **`lua/includes/modules/draw.lua` 换回 GMod 原文件**（前提：`NoTexture` + 字体名走
      `CreateFont` 化；`RoundedBoxEx` 现在已经是 GMod 原版了）
- [ ] `render.*` / `cam.*`（→ 解锁 `postprocess`）

### P2 — 引擎绑定大件

- [ ] `ents.*` 查找族（`gEntList` 已有底层）
- [ ] `player.*` 补全（`Iterator`/`GetBySteamID`）
- [ ] `team.*` 接 HL2MP gamerules
- [ ] `file.*`（GMod 路径语义）
- [ ] `net.*` 全套（`lnet.cpp` 扩展，GMod 语义的 Write/Read/Send/Receive/Broadcast）
- [ ] `usermessage.*`
- [ ] `http.*` / `cookie.*`（用 `thirdparty/curl`）
- [ ] `scripted_ents.*` / `weapons.*` 的 GMod 名字
- [ ] `util.*` 补全（`TableToJSON`/`JSONToTable`/`TraceHull`/…）

### P3 — UI 大件（Derma）

- [ ] `vgui.Create/Register` 与 GMod `scriptedpanels.lua` 语义对齐
- [ ] `panel:GetTable()` 别名 + `baseclass` 对齐
- [ ] `derma.DefineSkin` / `SkinHook` / `lua/skins/default.lua`
- [ ] **整目录拷 `lua/vgui/`(93) + `lua/derma/`(7) + `lua/skins/`(1)**
- [ ] （可选）路线 C：`ISurface::DisableClipping` + `DrawTexturedRectRotated` 下沉进 vguimatsurface
- [ ] `spawnmenu` / `menubar` / `widget` / `properties` / `controlpanel` / `search` / `notification`
- [ ] `construct` / `constraint` / `duplicator` / `presets` / `cleanup` / `saverestore`

### P4 — 明确延后

- [ ] `lua/menu/**`（27，和本仓菜单冲突）
- [ ] `drive` / `numpad` / `properties`（物理/输入）
- [ ] `matproxy.lua`（**不在 Lua 层做**，用 C++ `IMaterialProxy`）
- [ ] **削减 `lua/includes/modules/gmod_vgui.lua`**（当前最大的剩余脚手架）：
      它的 `vgui.Register` / `vgui.Create` 已被 GMod 的 `scriptedpanels.lua` 取代（死代码），
      它自带的 5 个最小控件（DPanel/DFrame/DLabel/DTextEntry/DButton）也与 `lua/vgui/` 冲突，
      它建的三个 Derma 字体已由 GMod 的 `lua/derma/init.lua` 建。
      应只保留 GMod 原版**没有**的部分：`vgui.GetWorldPanel` / `vgui.GetHoveredPanel`、
      `derma.SkinHook` 之类真正缺的，其余删掉。
      ⚠️ 删之前先确认 `derma/init.lua` 已经先于它加载（现在 `includes/init.lua` 的顺序是对的）。

---

## 7. 工程约定 v2

1. **优先零改写**：GMod 文件能拷就拷。要改 → 先问「能不能在引擎里补」。
2. 必须改 Lua 时：
   - 改动集中在**文件头**，用 `-- HL2SB:` 标注，并在本文件 §5 登记；
   - **不要**为了绕开缺函数而换语义（那正是 v1 的病根）。
3. 引擎新增绑定的规矩：
   - 新 `.cpp` **必须进 `.vpc`**（`client_lua.vpc` / shared / server 对应 target）；
   - 优先**改已有 `.cpp`**（`LISurface.cpp` / `lnet.cpp` / `lbaseentity_shared.cpp`…）而不是加新文件；
   - 加绑定后**在 `luasrclib.h` 定义名 + `lsrcinit.cpp` 注册**，否则 Lua 看不到；
   - 改 `client.dll` → 必须**完全重启游戏**；改 Lua → 重进地图即可。
4. 编码 **UTF-8 无 BOM**，改完跑 `python tools\check_lua_utf8.py`。
5. 离线验证：`D:\project\luacheck\lua_syntax.exe`（由引擎 Lua 源码编译的 **5.4.6**）+ mock 测试样板
   （`test_gmod_deathnotice.lua` 40 项断言就是范例）。
6. **harness 只负责「定位」，引擎源码负责「裁决」**：harness 报「缺全局 X」时，先去引擎源码
   确认 X 是不是真全局（`Vector`/`Angle`/`Color`/`CLIENT`/`vgui.Label` 都是真全局，
   被 harness 误报过 4 次）。是真全局 → 补 harness 的 mock，**不要去引擎里加**。
   见 §5.4.3 的两个 includes harness。
7. **别名 / 注册 / 覆盖的通用规则**：
   - 给同一个库起第二个名字时，**只能合并，不能替换**（GMod 名与 Experiment 名两边都可能已存在，
     `lua_setglobal` 会静默删掉一整库的函数）。见 §5.4.3(3)。
   - 报「字段是 nil」时，**先怀疑有东西把它那张表换掉了**，再怀疑缺绑定。
   - 引擎的 bootstrap 按**名字**加载（`luasrc_dofile_includes`），不要改成扫目录 ——
     扫目录会把 `init.lua` 已经 include 的文件再跑一遍，而 GMod 的 Lua 层对「第二次定义」
     的反应是走**重载**分支（`derma.DefineControl`），不是无操作。
6. 每次换掉一个自造 shim / 拷一个 GMod 原文件，**都在本文件勾选并记一行**。

---

## 8. 参考

### 8.1 目录

| | 路径 |
|---|---|
| GMod Lua 源头 | `D:\games\garrysmod\garrysmod\lua\` |
| GMod wiki 文档（已抓） | `D:\gmod_wiki_docs\{libraries,globals,classes,hooks,guides}\` |
| HL2SB 游戏 Lua | `D:\srceng\hl2sb\lua\` |
| 引擎绑定注册表 | `source-engine\game\shared\lua\lsrcinit.cpp` + `luasrclib.h` |
| 引擎模块（74 个顶层） | `D:\project\source-engine\` |
| 圆角 HUD 改动清单 | `D:\project\_session_extract\圆角HUD改动清单.md` |
| 引擎须知（坑） | `D:\project\source-engine\AGENTS.md` |

### 8.2 GMod 关键原文件（要拷的目标）

| 文件 | 用途 |
|---|---|
| `lua\includes\modules\draw.lua` | `RoundedBox`/`SimpleText`/`NoTexture`… |
| `lua\includes\extensions\client\panel\scriptedpanels.lua` | `vgui.Create/Register` 的 **GMod 权威实现** |
| `lua\derma\derma.lua` + `derma\init.lua` | Derma 框架本体 |
| `lua\vgui\*.lua`（93） | 全部 Derma 控件 |
| `lua\gamemodes\base\gamemode\cl_hudpickup.lua` | 拾取 HUD（圆角的**权威实现**） |
| `lua\gamemodes\base\gamemode\cl_deathnotice.lua` | 击杀播报（**注意：无圆角底板**） |
| `lua\includes\extensions\client\render.lua` | `render.*` 语义参考 |

---

## 附录 A：GMod docking 移植规格(2026-09-12 调研定稿)

**背景**:`notification.lua:172` 的 `self:DockPadding( 3, 3, 3, 3 )` 失败 —— 见 §2 的进度表第 10 层。
全仓库搜索确认 **本 fork 的 vgui2 完全没有 docking**:`SetDockPadding` / `SetDock(` / `DOCK_FILL` 零匹配;
`public/lua/vgui_controls/lPanel.cpp` 的方法表里也没有 `Dock`/`DockPadding`/`DockMargin`。
而 GMod 的 `Panel:Dock` 是 **C++**(证据:`lua/includes/extensions/client/panel.lua:500` **调用** `self:Dock( pnl:GetDock() )` 却没定义它们)。

### A.1 枚举(来源:https://wiki.facepunch.com/gmod/Enums/DOCK)

⚠️ **没有 `DOCK_` 前缀**,就是裸名字:

| 全局名 | 值 |
|---|---|
| `NODOCK` | 0 |
| `FILL` | 1 |
| `LEFT` | 2 |
| `RIGHT` | 3 |
| `TOP` | 4 |
| `BOTTOM` | 5 |

>`notification.lua:174` 写的是 `self.Label:Dock( FILL )` —— 用裸 `FILL`。
>我们这边 `FILL` 目前是 nil(只在**关掉的** `includes/modules/gmod_compatibility/sh_enumerations.lua:160` 定义过)。

### A.2 语义(来源:https://wiki.facepunch.com/gmod/Panel:Dock)

- `Panel:Dock( dockType )` —— 让面板朝某方向停靠,**自动改它的位置和尺寸**。
- `Panel:DockPadding( l, t, r, b )` —— **内侧**间距,影响**停靠进本面板的子面板**。
- `Panel:DockMargin( l, t, r, b )` —— **外侧**间距,影响**本面板作为停靠兄弟时的位置/尺寸**。
- ⚠️ 排序:**用 `Panel:SetZPos` 保证子面板顺序**(不是纯创建顺序)。
- 布局改动后想立刻拿到正确 bounds → `Panel:InvalidateParent()`(GMod 文档明说)。

### A.3 落点:改哪些文件

| 文件 | 改什么 |
|---|---|
| `public\vgui_controls\Panel.h` | 字段 `m_iDockType` / `m_iDockMargin[4]` / `m_iDockPadding[4]`;方法 `SetDock/GetDock/SetDockPadding/GetDockPadding/SetDockMargin/GetDockMargin`;停靠回合函数 |
| `vgui2\vgui_controls\Panel.cpp` | 实现上述方法 + 停靠回合。**关键集成点 = `Panel::InternalPerformLayout()`(第 3845 行)** —— 它先清 `NEEDS_LAYOUT` 再调虚拟 `PerformLayout()`(第 3859,空实现);`:1109`(SetSize)与 `:3887`(InvalidateLayout)都走它。**停靠回合放在这里,Lua 重写 `PANEL:PerformLayout` 无法绕过** —— 这是 GMod 能生效的原因 |
| `public\lua\vgui_controls\lPanel.cpp` | 绑 `Dock`/`GetDock`/`DockPadding`/`GetDockPadding`/`DockMargin`/`GetDockMargin`;注册裸全局 `NODOCK/FILL/LEFT/RIGHT/TOP/BOTTOM` |
| 构建 | 重编 **`vgui2` + `client`**,部署 `D:\srceng\bin\vgui2.dll` + `D:\srceng\hl2sb\bin\client.dll` |

### A.4 ABI 决定(已定)

**加 `VGUI2_API` 导出、不动 vtable** —— 避免 vgui2 ABI 变化导致全量重编。

### A.5 停靠回合算法(按 GMod 行为)

```
可用矩形 = 本面板客户区向内收 DockPadding
按 ZPos 顺序遍历子面板(仅 IsVisible 且 m_iDockType != NODOCK):
  矩形再按该子面板的 DockMargin 内收,得到它的最终 bounds:
    FILL   -> 吃掉当前整个可用矩形
    TOP    -> 贴顶,高度取子面板已有高度(或 0 时按比例),然后可用矩形上边下移
    BOTTOM -> 同理贴底,下边上移
    LEFT   -> 贴左,宽度取子面板宽度,然后左边右移
    RIGHT  -> 同理贴右,右边左移
  SetPos/SetSize 到该子面板
```

### A.6 验证

改完重进地图,`hl2sb_notification` 的 `OnUndo` 不该再报错,右上角出现通知条。
**顺便**:所有 `lua/vgui/*`(dpanel/dlabel/dtree/dlistview…)的排版都依赖 docking —— 这一步是 Derma 布局的基础设施,不只修通知条。

---

## 9. 移植状态与经验（v3 增补，2026-09-12 → 09-13）

> 本节是**最新**的进度与教训，覆盖 §6 的勾选表。写于 2026-09-13 02:00，
> 引擎分支 `lua_playermodel_menu`，内容仓库分支 `master`。
> 引擎改动都在 `D:\project\source-engine`（提交号见下表），内容改动在 `D:\srceng\hl2sb`。

### 9.1 状态总表（✅ 已通 / ⚠️ 部分 / ❌ 未做）

| 领域 | 状态 | 关键提交 | 说明 |
|---|---|---|---|
| Lua 5.4.6 + GLua 语法（`continue`/`!`/`!=`/`&&`/`||`/注释） | ✅ | — | 早于本轮 |
| `luaL_checkint` 接受浮点 | ✅ | — | 否则 HUD 每帧抛错、静默不画 |
| `RETURN_LUA_*` 栈泄漏 / `m_nTableReference` 双重 unref | ✅ | — | §5.3 |
| `autorun` 加载 + A-Z 排序 | ✅ | — | |
| `lua/includes/` 按**名字**加载 `init.lua`（不扫目录） | ✅ | `ab073409` | 修掉「54 个 vgui 控件重载失败」 |
| 库别名**合并**而非替换（`util`/`UTIL`） | ✅ | `ab073409` | 修掉 `util.PrecacheModel` 消失 |
| `GetConVar_Internal` / `vgui.GetAll` | ✅ | `ab073409` | GMod `util.lua` 无条件覆盖 convar 家族 |
| `surface.CreateFont(name, FontData)` / `DrawTexturedRectRotated` / `DrawTexturedRectUV` | ✅ | `85333918` | |
| PNG 贴图（`.vmt`/`.vtf` 缺失时回退图片）+ `IMaterial:GetColor` 采样 PNG | ✅ | — | GMod 皮肤紫黑/全白两个根因 |
| VGUI 面板「能画不能点」整条链（`LLabel` 分发、鼠标穿透、docking 字段、`vgui.GetAll`） | ⚠️ | — | `LCheckButton`/`LTextEntry`/`LEditablePanel` 的 Lua 分发**仍未补** |
| Derma docking（`DOCK_*` 枚举 + `Panel:Dock` 算法） | ✅ | — | §附录 A 的规格已实现 |
| 击杀播报（GMod `cl_deathnotice` 原版 + `killicon` + 别名 25 条） | ✅ | 内容 `e216a44` | `AddDeathNotice` 只注册钩子（避免双行） |
| 拾取 HUD（GMod `cl_hudpickup` 原版） | ✅ | `976e52d` | `DrawTexturedRectRotated` 是前提 |
| 撤消 / 通知（`undo.lua` + `hl2sb_notification`） | ✅ | `976e52d` | |
| **Lua SWEP 运行时**（`Think`/`Tick`/`ItemPostFrame`/`Deploy`/`Holster`/`SetupDataTables`） | ✅ | `ff23965e` `ce3fe84c` 等 | 引擎按 GMod 语义驱动开火键，不做 ammo/空仓点击 |
| SWEP 网络变量（`SWEP:NetworkVar` → 生成 `Get*/Set*`） | ✅ | 内容 `2e23bc2` | `weapon_fists`/`gmod_camera`/`medkit` 都靠它 |
| 弹药类型（`game.AddAmmoType` → `luasrc_ApplyAmmoTypes`） | ✅ | `0f8aa930` | `[Ammo] applied 11 Lua ammo definition(s)` |
| 武器 selection HUD 图标 / SWEP 图标 | ✅ | `9c911e72` `0f8aa930` | `swep.png` 默认图（内容 `9b7b479`） |
| viewmodel 动画（activity 解析 + 每帧重启语义） | ✅ | `5e9ee523` | 见 9.4「模型里的 activity」 |
| **玩家最大生命值网络化** | ✅ | `50d1f475` | 见 9.3，本轮最重要的一个 |
| 音效：`Sound()` 预缓存 + 失败可重试 + 缺脚本诊断 | ✅ | `5e9ee523` `7f8fc863` | |
| 弹道特效（`TE_HL2MPFireBullets` 带 tracer 名、send/recv 对齐） | ✅ | `19f75da6` `6399bff2` `990795e2` | |
| Nyan Gun 插件（崩溃/图标/弹药/材质/拖尾） | ✅ | `019e4e26` `0f8aa930` `0bb6baa5` | 只剩彩虹条（8.4） |
| Admin Gun 插件（`pist_weagon` 原版不改跑起来） | ✅ | `4d7fd82b` 等 | `Sound()` 全局是前提 |
| `Entity:GetCurrentCommand` / `IsConstraint` / `SendLua` / `GetInternalVariable` / NULL 实体语义 | ✅ | `6a704bbb` `7f8fc863` | 见 9.5「武器 Lua 报错清零」 |
| `matproxy`（GMod 的 **Lua 材质代理**，`lua/matproxy/*.lua`） | ❌ | — | 见 9.7，需要桥接 + `IMaterial:SetVector` + `Player:GetWeaponColor` |
| 彩虹条（`render.DrawBeam`） | ❌ | `8e5a92a3` `ee53a370` `9e0ef643` | 链路数据全对，屏幕上还是没有；已降优先级 |
| NPC 的 `m_iMaxHealth` / 客户端的 `m_takedamage` | ❌ | — | 见 9.7，本轮只做了玩家 |

**内容仓库里仍然存在的自造 shim**（v2 §5.2 说的「每补好一个绑定就删一个」，目前还剩）：
`gmod_globals.lua` / `gmod_util.lua` / `gmod_surface.lua` / `gmod_compat.lua` / `gmod_vgui.lua` /
`gmod_isvalid.lua` / `modules/{panel,vgui,resource,language,save,cvar,entity,weapon}.lua`。
⚠️ 但 `gmod_globals.lua` 现在**不只是脚手架**：它承担「两个 realm 的 `Sound`/`Model`/`AddCSLuaFile`
等价物 + 服务端 `render`/`net.Receive` 桩 + `CreateConVar` 参数位序修正」，删之前要逐项确认有引擎绑定顶上。

### 9.2 这一轮新增的经验：**构建 / 部署 / 线格式**

1. ⚠️⚠️ **改客户端头文件（加成员 → `sizeof` 变）必须整包重编。**
   waf **只按 .cpp 内容哈希**，头文件不在依赖图里。做法：删掉对象目录再 build：

   ```powershell
   Remove-Item D:\project\source-engine\build\game\client -Recurse -Force
   Remove-Item D:\project\source-engine\build\game\shared -Recurse -Force
   cd D:\project\source-engine; cmd /c ".\waf.bat build --targets=client,server"
   ```

   `game/shared` 要一起删：共享 `.cpp` 在 **client 目标**下也会 include `cbase.h` → 客户端头文件。
   全量约 **4 分钟**（1602 个 task）。不这么做会链进按旧布局编译的 .o → 堆损坏。
2. ⚠️ **`IMPLEMENT_NETWORK_VAR_FOR_DERIVED` 只覆盖 `CNetworkVarForDerived` 已声明的虚函数
   → 不新增 vtable 槽位**；而**加成员**会改 `sizeof`。前者可以放心改，后者必须整包重编。
3. ⚠️⚠️ **线格式改动必须 client.dll + server.dll 一起换，而且 recv prop 和 send prop 是
   「按 index」配对的，不是按名字。** 这个坑本项目踩过一次（`TE_HL2MPFireBullets` 的
   send/recv 错位，客户端 `m_flSpread` 收成了 `m_bDoImpacts`），这轮又差点踩：
   往 `DT_BasePlayer` 加 prop 时，**在两张表里都紧跟在同一个锚点后面**（这次是 `m_iHealth`）
   是最稳的做法，改完再 grep 两边确认顺序。
4. **判断「build 到底干活了没有」**：看 `build\game\client\client.dll` 的 `LastWriteTime`，
   或**在 DLL 里搜一个只可能来自这次改动的字符串**（这次是 `m_iMaxHealth` —— 修之前
   GMod 的 client.dll 有、我们的没有，修完就有了，一行命令就能验证）。
5. **部署路径**：`build\game\client\client.dll` → `D:\srceng\hl2sb\bin\client.dll`；
   `build\game\server\server.dll` → `D:\srceng\hl2sb\bin\server.dll`；
   永远先留 `*.bak_<时间戳>`，再比对两边 SHA256。
   **DLL 只在进程启动时加载 → 必须完全重启游戏。**

### 9.3 这一轮新增的经验：**客户端/服务端分歧是「症状全在画面」的根源**

这是本轮最有价值的一条，直接解释了两天的误判：

> **本地玩家的 viewmodel 是 PREDICTED 实体**，它的动画序列由**客户端预测**决定；
> 服务端那次成功的 `SendWeaponAnim` **不会**画到玩家屏幕上。
> （`C_BaseViewModel::UpdateAnimationParity` 的注释写得很直白：predicting 时不用 animation parity，
> 因为动画是客户端自己改的。）

推论：**只要 Lua 逻辑在客户端和服务端算出不同结果，玩家看到的就一定是「客户端那份」**，
而服务端照旧正确 —— 于是表现为「功能生效了（血加了、伤害出了），但动画/音效不对」。

本轮的实例（提交 `50d1f475`）：

| | 服务端 | 客户端（修前） |
|---|---|---|
| `m_iMaxHealth` | 真的是 100（`CNetworkVarForDerived`，`Spawn` 里 `= m_iHealth`） | **不存在**，`C_BaseEntity::GetMaxHealth()` 写死 `return 1` |
| `m_iHealth` | ✅ | ✅（`DT_BasePlayer` 里有） |
| `weapon_medkit` 的 `health >= maxhealth` | `80 >= 100` → 治疗成功 | `80 >= 1` → **永远「已满血」** → `HealFail` |
| 结果 | 血加上了、服务端播了治疗动画 | **放拒绝音（`WallHealth.Deny`）+ 不出动画** |

而「治疗别人有动画、治疗自己没动画」这个奇怪现象也随之解释清楚了：
客户端的 `C_BaseEntity::GetHealth()` 对**没网络化 health 的实体默认返回 0**，
`0 >= 1` 为假 → NPC 那条路反而「成功」了。

**排查这类问题的通用手法**：
- 别只看服务端日志有没有报错；**在客户端和服务端各自打一行点**（`HL2SB_WarnOnce` 的 key 里带 realm）。
- **问「客户端知不知道这回事」**：`GetMaxHealth` / `GetInternalVariable` / 任何 `C_NetworkVar`
  在客户端都可能**根本不存在**。先 grep 客户端那一侧的类定义，再看服务端。
- 对照 **GMod 自己的 DLL 里有没有那个符号**：
  ```powershell
  $t=[System.Text.Encoding]::ASCII.GetString([IO.File]::ReadAllBytes('D:\games\garrysmod\bin\client.dll'))
  $t.Contains('m_iMaxHealth')   # GMod: True   我们修前: False
  ```
  这一招又快又硬 —— GMod 有的我们该有，GMod 没有的就别去 DLL 里找（见 9.7 的 matproxy）。

### 9.4 这一轮新增的经验：**模型里的 activity / 武器实体自己的模型**

- ⚠️ **磁盘上的 `mstudioseqdesc_t.activity` 恒为 -1**：studiomdl 只写 activity **名字**，
  编号是运行时由游戏 DLL 按名字填的。**不要指望从 .mdl 里读出 activity 编号。**
- 离线取证工具（不用起游戏）：
  ```powershell
  cd D:\project\source-engine\tools
  python studiomdl_inspect.py <model.mdl>        # 每个序列的 activity 名 / 骨骼 / IK
  python mdl_activity_scan.py --csv out.csv <root>   # 批量
  ```
  实测数据（留着做对照）：

  | 模型 | 序列数 | activity 名 |
  |---|---|---|
  | `models/weapons/c_medkit.mdl` | 6 | `ACT_VM_DRAW` / `HOLSTER` / `IDLE` / `PRIMARYATTACK` |
  | `models/weapons/w_medkit.mdl` | **1** | 只有一个叫 `idle` 的，**没有任何 ACT_** |
  | `models/weapons/c_smg1.mdl` | 14 | 全套 12 个 `ACT_VM_*`（**没有 `ACT_VM_HOLSTER`**） |
  | `models/weapons/w_smg1.mdl` | 3 | `ACT_VM_IDLE`、`ACT_RANGE_ATTACK_SMG1` |

- ⚠️⚠️ **「模型里有什么」≠「运行时用哪个模型」。** 我一度以为 medkit 卡在 `w_medkit.mdl`
  没有 ACT_VM_*，但运行时日志一句话就否掉了：
  `weaponModel='models/weapons/c_medkit.mdl' resolves=1`。原因是
  **`CBaseCombatWeapon::Equip()` 在玩家持有武器时会把武器实体自己的模型换成 VIEWMODEL**
  （`basecombatweapon_shared.cpp:1003-1006`，`SetActivity()` 也在做同样的切换）。
  **教训：这类「运行时到底是哪个对象/哪个模型」的问题，只能靠引擎侧打点，不能靠推断。**
- 正确的动画链路（记下来省一次翻源码）：
  ```
  SendWeaponAnim(act)
    -> SetIdealActivity(act)                        // basecombatweapon_shared.cpp:2355
         idealSequence = SelectWeightedSequence(act)   // ← 用【武器实体自己的模型】
         if (idealSequence == -1) return false;        // ← 失败就在这里静默返回
         -> SendViewModelAnim(seq)                     // :1098
              -> vm->SendViewModelMatchingSequence(seq)  // 真正驱动 VM
  ```
  `CHL2MPScriptedWeapon::SendWeaponAnim` 现在多了一层**安全网**：武器自己的模型解析不出来时，
  改在 **viewmodel 实体**上解析再推给它（提交 `5e9ee523`）。这不是 medkit 的解药
  （medkit 本来 `resolves=1`），但把「静默 no-op」变成了「要么动、要么留一行日志」。
- **`ACT_*` 常量核对**：`gmod_globals.lua` 里手写的 `ACT_VM_*` / `ACT_HL2MP_*` / `ACT_MP_*`
  已逐个对着 `game/shared/ai_activity.h` 的枚举核实过（1749 个 activity，全部一致）。
  脚本：`D:\project\luacheck\check_act_values.py`。**改这些常量后要重跑它。**

### 9.5 这一轮新增的经验：**把「Lua 报错」清干净的两步法**

1. **日志实测**：把 `ds_debug.log` 的错误行归一化分组（去掉行号/路径/数字），按次数排序。
   ⚠️ **`Lua initialized` 每关出现两次：先服务端、后客户端**；判据是那一段里有没有
   `lua/autorun/client -> N file(s)`（只有客户端那段打印）。
2. **静态扫描兜底**（日志只证明「跑到过」的路径）：
   `D:\project\luacheck\scan_weapon_methods.py` —— 抽出武器/实体/特效脚本里所有
   `obj:Method(` 调用，减去「引擎注册名（绑定表 `{"X", fn}` + `lua_setglobal` + `lua_setfield`）」
   与「内容仓库里任何 Lua 定义」，剩下的就是候选缺口。

   ⚠️ 已知误报来源（这些名字是**运行时生成**的，脚本看不见）：
   - `AccessorFunc( ENT, "m_x", "X" )` → `GetX`/`SetX`
   - `SWEP:NetworkVar( "Float", 0, "Zoom" )` → `GetZoom`/`SetZoom`
   - `gmod_compat.lua` 的 `Alias( entmeta, "EntIndex", entmeta.entindex )`

**本轮靠它抓到的真缺口**：`weapon_medkit/shared.lua:117` 的
`ent:GetInternalVariable( "m_takedamage" )` —— `CanHeal()` 每次治疗都调，只有 trace 打空
（`ent` 是 NULL）时才被 `ent:IsPlayer()` 挡掉，所以**给活着的玩家/NPC 治疗必定抛错**，
而日志里 0 次（历史治疗全打在 NULL trace 上）。已绑定（提交 `7f8fc863`），
实现是 `GetDataDescMap()` + `baseMap` 链（和 `GetKeyValue` 同一手法），
名字不存在/数组/`FIELD_EMBEDDED`/函数指针一律推 `nil`。

### 9.6 这一轮新增的经验：**日志里会出现的一类「死代码」陷阱**

⚠️⚠️ **`lua/includes/extensions/gmod_globals.lua` 在服务端有个裸 `return`**
（`if ( not _CLIENT )` 块的末尾）：**写在它后面的代码在服务端永远不执行。**
我上一轮把服务端的 `render`/`net.Receive` 桩加在**文件末尾** → 完全没生效，
日志证明「gmod_globals 已加载，但 `properties.lua:175` / `halo.lua:7` 两条错误照旧」。
**这类「文件已加载但错误照旧」只能靠日志发现，光读 Lua 看不出来。**

其余同类：
- `lua/includes/modules/*.lua` **两个 realm 都会加载** → client-only 的库
  （`halo` / `properties`）要在文件里用 `if ( CLIENT )` 或加服务端桩，否则每关一条红字。
- `hook.lua` 出错即**永久注销**钩子 → HUD 只要抛错一帧就再也不画（改完必须重进地图）。
- `hook.call` 同名事件自环 = 卡死（已加重入守卫）。
- `lua/includes/modules/*.lua` 会被**执行两次** → 不要写 `X = X or <本文件定义>`。

### 9.7 还没做的（按优先级，供下一次接着干）

1. **`matproxy` 桥接**（GMod 的 **Lua 材质代理**；现在每次加载两条
   `proxy "PlayerWeaponColor" not found!`）。⚠️ 关键事实：**GMod 自己的 `bin/*.dll` 里
   搜不到 `PlayerWeaponColor`** —— 它真的是 `lua/matproxy/player_weapon_color.lua`
   （`matproxy.Add{ name=..., init=..., bind=... }`，写 `resultVar $selfillumtint`）。
   本仓库 `lua/includes/modules/matproxy.lua` **存在但完全是死代码**（注释写
   "Called by engine"，而引擎从不调它）。要修得三件事一起做：
   - 引擎桥接：`CreateProxy` 里先问 `matproxy.ShouldOverrideProxy(name)`，
     命中就建一个 `IMaterialProxy`（`Init` → `matproxy.Init(name, uname, mat, values)`，
     `OnBind` → `matproxy.Call(uname, mat, ent)`）。✅ 可行路径：
     `GetMaterialProxyFactory()` / `SetMaterialProxyFactory()` **在公开接口
     `IMaterialSystem` 上**，且客户端**已有先例**——
     `game/client/c_viewmodel_attachment.cpp` 的 `CPlayerColorProxyFactory`
     就是「包装旧工厂、保留链」的写法，扩它即可，**不需要重编 engine.dll**。
   - `IMaterial:SetVector( name, vec )`（`public/lua/materialsystem/limaterial.cpp` 目前只有 `GetName`/`IsError`）。
   - `Player:GetWeaponColor()` / `SetWeaponColor()`（引擎完全没有；GMod 是**联网**变量）。
2. **NPC 的 `m_iMaxHealth` 与客户端的 `m_takedamage`**（本轮只网络化了玩家，提交 `50d1f475`）。
   要彻底对齐 GMod，就在 `DT_BaseEntity` 上加（GMod 的 client.dll 两个字符串都有），
   或者给 NPC/共享表加。⚠️ 加在 `DT_BaseEntity` = 每个实体多一个 prop，带宽代价要自己权衡。
3. **`HL2SB_PrecacheOnce` 是进程级缓存**（512 名上限）：`util.PrecacheModel` 因此可能在
   后续地图上跳过重新 precache。已加 `HL2SB_PrecacheForget` 让**失败的** precache 可以重试，
   但**成功过的**仍然不会按地图重来。
4. **Derma 控件的 Lua 分发**：`LCheckButton` / `LTextEntry` / `LEditablePanel` 仍未补
   （影响 DCheckBox / DTextEntry / DPropertySheet）。
5. **彩虹条**（`render.DrawBeam`）：链路数据全对（TE 到了、特效建了、89 帧、
   `Render` 被调、材质 `error=0`、几何在视野前方），屏幕上仍然什么都没有。
   已排除：`CBeamSegDraw` 只吃 sprite 系材质（§10.4）；`GetDynamicMesh` 不带材质 = 顶点格式不对。
   已改成手搓面向摄像机四边形 + 传材质，仍未显示。**下一步应该换一个已知能显示的材质
   （比如 `sprites/redglow1.vmt`）做对照实验**，先确认「能显示」再回去查彩虹贴图。
6. `lrender.cpp` 的 `s_MatCache` / `g_pHL2SBLastBoundMaterial` **只加引用不释放**（永久 pin 材质）；
   `c_te_effect_dispatch.cpp` 的调试名列表是 8 槽定长，第 9 个 effect 开始不再报告。
7. `AGENTS.md` 已**超出 harness 指令预算**（150 KB vs 65 KB 上限，约第 700 行之后不再自动加载）。
   要么新结论写在文件靠前，要么把 §5 那批稳定的小节合并压缩。

### 9.8 v3 追加勾选（补 §6 的表）

- [x] 引擎：`vgui.GetAll()`（面板注册表）
- [x] 引擎：`GetConVar_Internal` / 库别名合并 / `lua/includes` 按名字加载
- [x] 引擎：`surface.CreateFont(name, FontData)` / `DrawTexturedRectRotated` / `DrawTexturedRectUV`
- [x] 引擎：PNG 贴图回退 + `IMaterial:GetColor` 采样
- [x] 引擎：Derma docking（`DOCK_*` + `Panel:Dock` 算法）
- [x] 引擎：Lua SWEP 运行时（`Think`/`Tick`/`ItemPostFrame`/`SetupDataTables`/`NetworkVar`）
- [x] 引擎：`game.AddAmmoType` → `CAmmoDef` 桥接
- [x] 引擎：`Entity:GetCurrentCommand`（GMod `cmd:` 快照）/ `IsConstraint` / `SendLua` / `GetInternalVariable`
- [x] 引擎：NULL 实体对所有方法返回 `false`（GMod 语义）
- [x] 引擎：玩家 `m_iMaxHealth` 网络化（`DT_BasePlayer`，send/recv 同位置）
- [x] 引擎：`util.PrecacheSound` 失败可重试 + 缺 soundscript 一次性告警
- [x] 引擎：`TE_HL2MPFireBullets` 带 tracer 名（send/recv 对齐）
- [x] 内容：服务端 `render` / `net.Receive` 桩（放在 `gmod_globals.lua` 的裸 `return` **之前**）
- [x] 内容：Nyan Gun 插件（崩溃/图标/弹药/材质/拖尾）
- [x] 内容：`pist_weagon`（The Ultimate Admin Gun Fixed）原版不改跑起来
- [ ] 引擎：`matproxy` 桥接 + `IMaterial:SetVector` + `Player:GetWeaponColor`
- [ ] 引擎：NPC `m_iMaxHealth` / 客户端 `m_takedamage` 网络化
- [ ] 引擎：彩虹条（`render.DrawBeam`）
- [ ] 引擎：`LCheckButton` / `LTextEntry` / `LEditablePanel` 的 Lua 分发

