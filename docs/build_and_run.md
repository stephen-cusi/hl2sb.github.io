---
title: 构建与运行
---

# 构建与运行

这一页是给**使用这个分支的人**看的：怎么把引擎编译出来、DLL 放哪里、什么时候必须重启游戏，
以及 GMod 的 Lua 兼容层大致是怎么搭起来的。

> 目标是 Windows + MSVC。构建走工程里的 waf 脚本，源码树是完整的引擎源码，
> 不是只有 SDK 的壳子 —— 所以缺的 GMod 函数可以真的加在引擎侧。

## 0. 你需要两个仓库

| 仓库 | 是什么 |
|---|---|
| [source-engine-mod](https://github.com/stephen-cusi/source-engine-mod) | **引擎源码**（nillerusr source-engine + HL2SB 改动），分支 `lua_playermodel_menu` |
| [hl2sb-gamefile](https://github.com/stephen-cusi/hl2sb-gamefile) | **游戏内容**：`cfg` / `resource` / `lua` / `materials`(仅文本) / `gamemodes` / `gameinfo.txt`。只收录可编辑的文本资源，二进制资源（模型、贴图、声音）不进版本控制 |

部署时它们的关系是：**引擎编出 DLL → DLL 放进游戏内容的 `bin\` → 用引擎启动器启动游戏内容目录**。

## 1. 编译

在引擎源码目录里跑（注意要用 `waf.bat`，它会设好 UTF-8 / 代码页）：

```powershell
cd <引擎源码目录>
cmd /c ".\waf.bat build --targets=client,server"   # 一次编出 client.dll + server.dll
```

也可以分开编，或者编 GameUI：

```powershell
cmd /c ".\waf.bat build --targets=client"
cmd /c ".\waf.bat build --targets=server"
cmd /c ".\waf.bat build --targets=GameUI"
```

**别直接 `python .\waf build`**：MSVC 输出中文时 Python 会报 `UnicodeEncodeError: 'gbk' codec ...`。
`waf.bat` 里设了 `PYTHONIOENCODING=UTF-8` 和代码页，用它能正常处理。

产物在：

* `build\game\client\client.dll`
* `build\game\server\server.dll`
* `build\gameui\GameUI.dll`

## 2. 部署：DLL 放到哪里

这是最容易搞错的地方，因为**有两个 `bin` 目录**，作用完全不同：

| 产物 | 复制到 | 说明 |
|---|---|---|
| `build\game\client\client.dll` | `<游戏内容>\bin\client.dll` | mod 自己的客户端 |
| `build\game\server\server.dll` | `<游戏内容>\bin\server.dll` | mod 自己的服务端 |
| `build\gameui\GameUI.dll` | `<引擎基础库目录>\GameUI.dll` | 覆盖引擎的 UI 模块（**不是**放进 mod 的 `bin`） |

⚠️ **mod 的 `client.dll` / `server.dll` 绝不要放进引擎基础库目录**（就是那个已经有
`engine.dll` / `tier0.dll` / `materialsystem.dll` / `vgui2.dll` 的目录）。那里是所有 mod 共用的
平台库，放进去会污染它，也可能让游戏从错误的位置加载。

部署前先确认游戏没在跑，否则 DLL 被占用、复制会失败。

## 3. 什么时候要重启游戏

| 你改了什么 | 生效方式 |
|---|---|
| C++（引擎、client、server） | **必须完全退出游戏再启动**。DLL 只在进程启动时加载，换地图不算 |
| gameinfo / cfg | 重启游戏（部分 cvar 可以控制台直接改） |
| Lua 脚本 | 重进地图；或者控制台 `lua_dofile_cl <路径>` 直接热加载客户端脚本 |
| 材质 / 模型 | 重进地图 |

Lua 脚本是在地图加载时读取的；`.lua` 文件必须是 **UTF-8 无 BOM**。

## 4. 在游戏里试 Lua

HL2SB 的控制台命令（**不是** GMod 的 `lua_run`）：

| 命令 | 作用 |
|---|---|
| `lua_run_cl <一行代码>` | 客户端执行。参数是**本行剩余的全部内容**，所以一条命令只能放一句，多句用 `;` 拼一行 |
| `lua_dofile[_cl] <文件>` | 执行服务端 / 客户端 Lua 文件。路径**相对 `lua/` 根目录**、**要带 `.lua`**、不写 `lua/` 前缀 |
| `lua_dostring_cl <字符串>` | 同 `lua_run_cl` |

⚠️ 别一次粘贴多行命令 —— 控制台会把剩下的行当成第一条命令的参数。
还没进地图时 `lua_run_cl` 会提示 `Lua is not initialized yet`。

写第一个 UI 窗口看 **[Derma 基础指南](derma_basic_guide.html)**。

## 5. GMod 的 Lua 兼容层长什么样

引擎里的 Lua 是 **Lua 5.4.6**（不是 GMod 的 LuaJIT，也不是 5.1），另外带上了 GLua 的语法扩展，
所以 `continue`、`!` / `!=`、`&&` / `||`、`//` 注释这些 GMod 脚本里的写法能直接跑；
`module()` / `package.seeall` 也做了兼容层。兼容层由三层构成：

1. **引擎侧的 C++ 绑定** —— 缺的 GMod 函数尽量补在引擎里，而不是在 Lua 里做 shim。
   例如 `surface.*`（绘图、字体）、`vgui.*`、`file.*`、`ConVar` / `GetConVar`、`Color`，
   以及 GMod 的 `vgui.GetAll()`。这样 GMod 的原文件可以整目录拷过来、尽量一行不改。
2. **Lua 侧的扩展与兼容模块** —— GMod 风格的 `surface` / `draw` / `hook` / `util` / `killicon` /
   `derma` / `vgui` 等库，以及枚举枚举别名（`KEY_*`、`DOCK` 之类）。
3. **GMod 的原版文件** —— 皮肤、Derma 控件、`derma/init.lua`、击杀播报等直接来自 GMod，
   本地化的地方在文件头用注释标明。

**加载顺序**（每次地图加载执行）：

```
lua/includes/extensions      ← GMod 风格扩展库
lua/includes/modules         ← hook / killicon / 各类模块
lua/game/shared
lua/game/client              ← 客户端脚本（服务端不加载这个目录）
...最后  gamemode
```

之后还会按 GMod 的顺序跑 `lua/autorun/`：先 `lua/autorun/*.lua`（不递归），
再 `lua/autorun/client/**` 或 `lua/autorun/server/**`（递归），**按文件名 A-Z 排序**。

写了什么脚本、放到哪个目录、客户端还是服务端，对照
[GMod Lua 兼容层](gmod_compat_layer.html) 和
[移植计划与状态](gmod_lua_port_plan.html) 里的表。

## 6. 已知差异（踩之前先看这里）

| 项 | 状态 |
|---|---|
| `lua/derma` 的部分控件（`DCheckBox` / `DTextEntry` / `DPropertySheet` …） | ⚠️ 底层分发仍在补，能画但交互可能不全 |
| `derma.RefreshSkins()` | ❌ 未实现；改完皮肤要重建窗口 |
| 覆盖容器面板的 `Paint` | ⚠️ 会让子面板不绘制，见 [指南 §3](derma_basic_guide.html#3-覆盖-paint-的坑本仓库实测) |
| 少数 GMod 独有全局（如 `Entity`） | ❌ 不存在，移植 GMod 插件时要替换 |

完整清单见 [Derma 基础指南 §8](derma_basic_guide.html#8-已知差异-未实现相对-gmod) 与
[移植计划与状态](gmod_lua_port_plan.html#9-移植状态与经验v3-增补2026-09-12-09-13)。
