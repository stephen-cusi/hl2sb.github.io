---
title: GMod Lua 兼容层
---

# GMod Lua 兼容层

HL2SB 的目标是 **GMod 的 Lua 原样拿过来、尽量一行不改**。所以「缺函数」的默认解法不是
在 Lua 里写 shim，而是**在引擎 C++ 侧补绑定** —— 这个仓库是完整引擎源码，
`surface.*` 对应 vguimatsurface、`render/cam.*` 对应 materialsystem、`file.*` 对应 filesystem、
`net.*` 对应 engine 的网络通道……所以几乎每一项都能落到某个模块里实现。

只有 GMod 里写死了「HL2SB 物理上不存在的东西」时才改 Lua（例如 GMod 的网络事件名），
这类改动必须在文件头用注释标明。

## 1. 运行时环境（和 GMod 的差异）

| 维度 | GMod | HL2SB |
|---|---|---|
| Lua 版本 | LuaJIT 2.0（GLua） | **Lua 5.4.6** + GLua 语法扩展 |
| 语法扩展 | `continue` / `!` / `!=` / `&&` / `||` / `//` / `/* */` | ✅ 同样支持（`module()` / `package.seeall` 也回移了兼容层） |
| 原生库 | 自带 `utf8.lua` | 原生 `utf8` 库 |
| `Color` | table，`.r/.g/.b/.a` 是字段 | 同样是 table + 数字字段（大写方法 `col:GetR()` 也有） |
| 模块机制 | `module("x")` + 全局 `x.*` | 一致 |
| 文件编码 | 随意 | **UTF-8 无 BOM**（`resource/*.txt` 例外，本地化 token 要 UTF-16LE+BOM） |

⚠️ 「Lua 5.1 语义」的直觉在这里经常是错的：例如 5.1 的 `lua_tointeger` 会截断小数，
而 5.4 严格的整数检查会直接抛错。引擎侧已经按 5.1 的行为做了兼容，写新脚本时按 GMod 写法即可。

## 2. 兼容层的三层结构

### 第一层：引擎侧的 C++ 绑定

引擎里注册了 GMod 需要的全局与库方法。这一层存在的意义是让 GMod 原文件能直接跑：

* **绘制 / UI**：`surface.*`（含 GMod 名字的 `SetDrawColor` / `DrawRect` / `DrawText` /
  `SetTexture` / `SetMaterial` / `CreateFont` / `DrawTexturedRect` 等）、`vgui.*`、
  `derma.*`、`draw.*`（圆角、文本对齐常量）。
* **通用**：`Color`、`hook`、`concommand`、`cvars`（`ConVar` / `GetConVar` 家族）、
  `gameevent`、`file`（GMod 的 `extensions/file.lua` 就是拿它的句柄重写 `file.*` 的）。
* **引擎全局**：`GetConVar_Internal`、`vgui.GetAll()` 这类 GMod 脚本会无条件调用的入口。

### 第二层：Lua 侧的扩展与兼容模块

GMod 风格的库与 shim，加载在 `lua/includes/` 下：

* `extensions/` —— `gmod_surface.lua`（GMod 的 `surface` 名字层）、`gmod_vgui.lua`
  （Derma 默认字体 `DermaDefault` / `DermaDefaultBold` / `DermaLarge` 等）。
* `modules/` —— `hook.lua`、`killicon.lua`、`gmod_compatibility/`（枚举别名：
  `KEY_*`、`DOCK`、`TEXT_ALIGN_*` 之类，因为引擎发布的是 `IN_*` / `KEY_CONTROL_LEFT` 这样的名字）。
* `derma/` —— 控件定义、`derma.lua`、`skins/`。

### 第三层：GMod 的原版文件

GMod 自带的文件被尽量原样搬过来：Derma 控件、皮肤、`derma/init.lua`、
击杀播报 `cl_deathnotice.lua` 等。本地化的地方写在文件头注释里，常见只有几类：

* **事件来源**：GMod 用 `net.Receive` 收 usermessage，HL2SB 改成 hook 事件；
* **加载时机**：`lua/game/client` 比 gamemode 先加载，所以加载时 `_GAMEMODE` 可能是 nil；
* **名字差异**：GMod 的常量在 HL2SB 里可能在另一个表下（例如 `draw.TEXT_ALIGN_RIGHT`）。

## 3. 加载顺序

每次地图加载（客户端 `LevelInitPreEntity` / 服务端 DLL 加载）按这个顺序：

```
lua/includes/extensions      ← GMod 风格扩展库（要先于 includes/init.lua）
lua/includes/modules         ← hook / killicon / 各类模块
lua/game/shared
lua/game/client              ← 客户端脚本（服务端不加载这个目录）
lua/autorun/*.lua            ← 不递归，按文件名 A-Z
lua/autorun/client|server/** ← 递归，按文件名 A-Z
luasrc_LoadWeapons()         ← 武器
luasrc_LoadGamemode()        ← gamemode 最后
```

要点：

* `lua/includes/init.lua` 是**按名字**加载的（不是扫目录），它自己 `include` 了
  `util.lua` 和 `vgui_base.lua`。往 `lua/includes/` 顶层加新文件要写进 `init.lua`。
* 服务端也会加载 `lua/includes/init.lua`，**client-only 的东西必须用 `if ( CLIENT )` 挡住**。
* `lua/autorun/` 与 GMod 一致：客户端 `/server` 与 `/client` 子目录分别递归，
  且**保证按文件名 A-Z 排序**后执行。

## 4. 已知缺口 / 与 GMod 的差异

| 项 | 状态 |
|---|---|
| `derma.RefreshSkins()` | ❌ 未实现（只有 `DefineSkin` / `SkinHook` / `SetSkin`） |
| 覆盖容器面板的 `Paint` 后子面板不绘制 | ⚠️ 已知问题，未修 |
| 部分控件的 Lua 分发（`DCheckBox` / `DTextEntry` / `DPropertySheet` …） | ⚠️ 仍在补 |
| `surface.DrawTexturedRectRotated` 等少数绑定的参数语义 | ✅ 已按 GMod 对齐，注意 `x, y` 是矩形中心、`rot` 是度 |
| `CreateConVar` 的 min/max 参数位序 | ⚠️ 与 GMod 不完全一致，不崩但不做范围钳制 |
| `Entity` 等 GMod 独有全局 | ❌ 不存在，移植插件时要替换 |
| `debug.Trace()` | ❌ GMod 有，HL2SB 没有 |

逐条根因与实测过程在 [移植计划与状态](gmod_lua_port_plan.html) 和
[Derma 基础指南](derma_basic_guide.html) 里。

## 5. 给插件作者的建议

* 先按 GMod 的写法写；报 `attempt to call a nil value (method 'X')` 时先判断这个控件是
  **引擎类**还是**纯 Lua 控件**，再决定补哪里。
* 用 `hook.Add`（GMod 拼写）而不是引擎血统的 `hook.add` 也可以，两者都能用；
  但**同一个事件不要既注册 hook 又定义 gamemode 方法**，那样会派发两次。
* 脚本出错会被 hook 系统注销，所以 HUD 绘制钩子里建议用 `pcall` 包住，
  否则一次异常就永久静默。
* 改完 Lua 记得重进地图（或 `lua_dofile_cl` 热加载）；改完 C++ 必须完全重启游戏。
