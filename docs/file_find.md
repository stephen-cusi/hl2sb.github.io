---
title: file.Find
---

# file.Find

`file.Find` 列出一个文件夹里的**文件**和**子目录** —— 它是 GMod 脚本里最常用的文件枚举入口
（Spawnmenu 找 `settings/spawnlist/*.txt`、addon 找 `lua/autorun/*.lua`、内容对话框找隔壁的
Source 游戏，全都靠它）。参数里的 `name` 是「文件夹 + 通配符」，返回值是**两个表**：
文件一个、目录一个。

> **HL2SB 状态：✅ 已实现 —— 引擎侧 C++ 绑定，不是 Lua shim。**
> 实现：`public/lua/lfilesystem.cpp:1169`（`file_Find`），注册进 `file_funcs[]` 的那行在 `:1414`，
> 由 `:1419` 的 `luaopen_Files` 开出 `Files` 库，再经 GMod 拼写别名 `file` 暴露
> （`game/shared/lua/lsrcinit.cpp:553`）。`client.dll` 与 `server.dll` 都编这一份
> （`game/client/client_lua.vpc:116` / `game/server/server_lua.vpc:88`），
> 菜单（GameUI）状态另外单独开了一遍（`game/shared/lua/luamanager.cpp:345`）。
>
> **与 GMod 的关系**：签名、默认排序、两个返回值、以及「非法 pathID → `nil, nil`」
> 都与上游 [file.Find](https://wiki.facepunch.com/gmod/file.Find) 一致；
> **差异集中在 pathID 的覆盖面**（§4）和 `sorting` 值的宽容度（§5）—— 那两节里的每一条都能在源码里指到行号。

## 1. 签名与参数

```text
table files, table dirs = file.Find( string name, string pathID, string sorting )
```

| # | 参数 | 类型 | 说明（沿用 GMod 的措辞） |
|---|---|---|---|
| 1 | `name` | `string` | 要搜索的通配符。`models/*.mdl` 会列出 `models/` 里的 **.mdl** 文件。`*` 是唯一决定「这串算不算通配符」的字符（`file_Find` `:1180`）；**没有 `*` 时整个参数被当成文件夹名，引擎自己补 `/*`**（`:1183`-`:1188`），所以 `file.Find( "gamemodes", "GAME" )` 等价于 `file.Find( "gamemodes/*", "GAME" )`。 |
| 2 | `pathID` | `string` | 到哪个搜索路径里找。取值见 §4 的表（上游列表：[File Search Paths](https://wiki.facepunch.com/gmod/File_Search_Paths)）。**传别的字符串不会报错，而是返回 `nil, nil`**（`:1218`-`:1223`）。 |
| 3 | `sorting` | `string` | 可选的排序方式，默认 `nameasc`（`:1227`）。取值见 §1.1。 |

参数是怎么读的（`file_Find` `:1170` / `:1206` / `:1228`）：第 1 个是 `luaL_checkstring`（**必填**），
第 2、3 个是 `lua_tostring` —— 也就是说**只认字符串**：`nil` 等于省略，数字会被就地转成字符串当
pathID 用（`:1206`）。⚠️ 这点和 `file.Exists` 家族不一样：那边用 `HL2SB_GetPathArg`，会接受
`true`/`false`（`lfilesystem.cpp:726`-`:733`），`file.Find` **不吃布尔值**。

### 1.1 sorting 的取值

| 值 | 含义 | 来源 |
|---|---|---|
| `nameasc`（默认） | 按名字升序 | 上游文档；`file_Find` `:1227` |
| `namedesc` | 按名字降序 | `:1245`-`:1246` |
| `dateasc` / `datedesc` | 按修改时间升 / 降 | `:1237`-`:1238`（`date` 与 `time` 都走这条） |
| `sizeasc` / `sizedesc` | 按文件大小升 / 降 | `:1239`-`:1240` |
| `typeasc` / `typedesc` | 文件在前 / 目录在前 | `:1241`-`:1242` |
| `extasc` / `extdesc` | 按扩展名升 / 降 | `:1243`-`:1244` |

匹配方式是**子串**（不是精确相等）：值先转小写（`:1233`），含 `desc` 就是降序（`:1235`），
再按 `time`/`date` → `size` → `type` → `ext` 的顺序认（`:1237`-`:1244`）。
**认不出来的值不报错，静默回落成 `nameasc`**（`:1225`-`:1247`）；
排序主键相同的条目一律用**名字升序**做 tie-break（`HL2SB_FindCmp` `:1101`-`:1106`）。

## 2. 返回值

| # | 类型 | 说明 |
|---|---|---|
| 1 | `table` | 找到的**文件**名表；`pathID` 非法时是 `nil`。名字是**裸名**，不含文件夹前缀。 |
| 2 | `table` | 找到的**目录**名表；`pathID` 非法时是 `nil`。名字同样是裸名，**没有结尾的 `/`**。 |

四个要点（都在 `file_Find` 里）：

* **目录名不带尾斜杠**：目录和文件一样是把 `FindFirstEx` 给的名字原样塞进表里
  （`:1336`）。上游 wiki 的示例输出（`Folder: ctp`）也是这样，需要拼路径时自己加 `/`。
* **只搜一层，不递归**：搜索模式永远是 `<folder>/<glob>`（`:1210`），
  引擎的 `FindFirstEx` 对每条搜索路径只做一次 `FS_FindFirstFile`（`filesystem/basefilesystem.cpp:4076`-`:4078`），
  递归要自己写（见 §3 例 2）。
* **`.` 开头的条目不返回**：`.`、`..` 和点文件都被跳过（`:1269`-`:1270`）。
* **同名条目会去重**：同一个相对名字可能同时来自 GAME 和 MOD（本 fork 把两者成对搜，见 §4），
  所以会按「目录标记 + 名字（不区分大小写）」去重（`:1297`-`:1314`）。

`nil` 与空表的区别很重要，上游文档那句话说的是前者：

```lua
-- pathID 非法 -> 两个 nil
local files, dirs = file.Find( "*", "NOT_A_PATH_ID" )   -- files == nil, dirs == nil

-- pathID 合法、但文件夹不存在或为空 -> 两个空表
files, dirs = file.Find( "no/such/folder/*", "GAME" )   -- files == {}, dirs == {}
```

所以 GMod 脚本里那句 `if ( !files ) then return end` 挡的是**非法 pathID**，
挡不住空文件夹（源码 `:1214`-`:1217` 特意说明了这一点）。

## 3. 示例

**例 1：列出一个文件夹（默认 `nameasc`）**

```lua
local files, dirs = file.Find( "settings/spawnlist/*.txt", "GAME" )

if ( !files ) then return end        -- 只有 pathID 非法才会是 nil

for _, name in ipairs( files ) do
	print( "FILE", name )            -- 裸文件名，如 "hl2_weapons.txt"
end

for _, name in ipairs( dirs ) do
	print( "DIR ", name )            -- 目录名没有尾斜杠；拼路径时自己加 "/"
end
```

**例 2：递归展开一个目录树（GMod 的惯用写法）**

```lua
local function ListRecursive( path, pathID )
	local files, dirs = file.Find( path .. "/*", pathID )
	if ( !files ) then return end

	for _, name in ipairs( files ) do
		print( path .. "/" .. name )
	end
	for _, name in ipairs( dirs ) do
		ListRecursive( path .. "/" .. name, pathID )
	end
end

ListRecursive( "lua/entities", "GAME" )
```

**例 3：`LUA` 是 `lua/` 子树，`DATA` 是 `data/` 子树**

```lua
-- "LUA"/"lcl"/"lsv"/"LuaMenu" 都映射到 GAME + "lua/" 前缀
local weapons = file.Find( "weapons/*.lua", "LUA", "namedesc" )

-- "DATA" 映射到 MOD + "data/" 前缀（就是 GMod 的 garrysmod/data）
file.Write( "hl2sb_demo/notes.txt", "hello" )
local dataFiles = file.Find( "hl2sb_demo/*", "DATA" )

print( weapons[ 1 ], dataFiles[ 1 ] )   -- 例如 "weapon_hl2mpbase.lua"  "notes.txt"
```

**例 4：排序参数真的生效**

```lua
local asc  = file.Find( "addons/*", "MOD", "nameasc" )
local desc = file.Find( "addons/*", "MOD", "namedesc" )
local big  = file.Find( "addons/*", "MOD", "sizedesc" )

print( asc[ 1 ], desc[ 1 ], big[ 1 ] )
```

> 想就地核对上面每一条，可以用游戏内容仓库里的探针 `lua/file_find_test.lua`
> （控制台 `lua_dofile_cl file_find_test.lua`；它会逐条打印文件/目录个数、
> 非法 pathID 的 `nil, nil`、合法空目录的两个空表、以及 nameasc/namedesc 的结果）。

## 4. pathID 支持情况

`file.Find` 的 pathID 由 `HL2SB_ResolveFindPathID`（`lfilesystem.cpp:1118`-`:1158`）解析，
映射表是 `s_GModPathIDs`（`:618`-`:641`）；**表里没有、但引擎确实注册过的 ID 会原样透传**
（`:1148`-`:1155`，判据是 `HL2SB_PathIDExists`），其余一律 `nil, nil`（`:1157`）。

| pathID | HL2SB 行为 | 说明 |
|---|---|---|
| `"GAME"` | ✅ | 搜索 GAME **和** MOD 两条路径（`:1142`-`:1145`），结果去重 |
| `"MOD"` / `"garrysmod"` | ✅ | 同上，MOD 优先（`:1143`） |
| `"LUA"` / `"lcl"` / `"lsv"` / `"LuaMenu"` | ✅ | GAME + 前缀 `lua/`（`:628`-`:633`） |
| `"DATA"` / `"WRITE"` | ✅ | MOD + 前缀 `data/`（`:634`-`:635`） |
| `"THIRDPARTY"` / `"WORKSHOP"` | ⚠️ 近似 | MOD + 前缀 `addons/`（`:639`-`:640`）；本引擎没有独立的 workshop 树 |
| `"BSP"` | ✅ | 透传；引擎注册了这个 ID（`filesystem/basefilesystem.cpp:386`），指向当前地图的 pack 文件 |
| `"BASE_PATH"` / `"EXECUTABLE_PATH"` | ✅ | 透传；引擎自己注册（`public/filesystem_init.cpp:1106` / `:1101`） |
| `"GAMEBIN"` / `"DOWNLOAD"` / `"PLATFORM"` / `"CONFIG"` / `"MOD_WRITE"` / `"GAME_WRITE"` / `"DEFAULT_WRITE_PATH"` | ✅ | 透传；gameinfo.txt 注册（见 `lfilesystem.cpp:605`-`:607` 的注释） |
| 已挂载的游戏名（`"hl2"`、`"cstrike"`…） | ✅ | 透传；引擎为每个挂载的游戏加一条搜索路径（`:1148`-`:1150`） |
| `""` / `"ALL"` / `"NULL"` | ⚠️ 额外宽容 | 都当成 GAME（`:620`-`:623`）；上游文档没列这三个 |
| 省略（`nil`） | ⚠️ 额外宽容 | 当成空字符串 → 搜 GAME + MOD（`:1122`-`:1128`）；上游把这个参数标成必填 |
| Workshop addon 的**标题**（GMod 的动态 ID） | ❌ | `nil, nil` —— 本引擎没有「按 addon 标题寻址」的搜索路径（`:1148`-`:1157`） |
| 其它任意字符串 | ❌ | `nil, nil`（pathID 名字本身**大小写不敏感**，`:650` 用 `V_stricmp`） |

## 5. 与 GMod 的差异 / 注意

| 差异 | 细节 | 源码 |
|---|---|---|
| `MOD` 的含义 | GMod 的 `MOD` 是「garrysmod 文件夹，**不含 addons**」；本 fork 把 addon 挂进了 mod 树，所以这里的 `MOD` **含 addons** | `:624`-`:626` |
| `GAME` 与 `MOD` 成对搜 | 查 `"GAME"` 时会连 `"MOD"` 一起搜、反之亦然，然后去重；GMod 对每个 ID 是严格的 | `:1136`-`:1145` |
| 每个 realm 的 `lua/` 不分开 | GMod 的 `lcl` / `lsv` / `LuaMenu` 是三个不同的树；这里只有一个 `lua/` 树，四个拼写等价 | `:629`-`:633` |
| `THIRDPARTY` / `WORKSHOP` 是近似 | 都指 `addons/`；`.gma` 直接挂在 `hl2sb/addons/` 下 | `:636`-`:640` |
| addon 标题不能用 | 见 §4 最后两行。注意 `file.Exists` 这类绑定遇到未知 ID 会退化成「搜遍所有路径」，**`file.Find` 不会**，它老老实实返回 `nil, nil` | `:1148`-`:1157` vs `:687`-`:695` |
| `sorting` 更宽容 | 上游只文档化了 `nameasc`/`namedesc`/`dateasc`/`datedesc`；这里另外接受 `size*` / `type*` / `ext*`，并且**未知值静默回落 nameasc**（GMod 侧未知值的行为我们没有验证） | `:1225`-`:1247` |
| 只有 `*` 是通配符 | `?` 不算：`file.Find( "models/?.mdl", "GAME" )` 会被当成文件夹 `models/?.mdl` 再补 `/*`，等于什么都没找到。`**` 也不是递归通配符 —— 这个绑定只做单层搜索 | `:1180`, `:1210` |
| 大小写 | 排序、去重、pathID 名都用 `Q_stricmp` / `V_stricmp`（**不敏感**）；名字匹配交给引擎的 `FindFirstFile`（Windows 上不敏感）。上游 wiki 那条「`lua/MyFolder/*` 在 Linux 上不按预期工作」的限制，对本站的目标平台（Windows）不适用 | `:1104`, `:1166`, `:650` |
| 目录名无尾斜杠 | 与上游示例一致，但和「目录都带 `/`」的直觉相反，拼路径时容易漏 | `:1336` |
| 重复条目的大小 / 时间 | 去重发生在请求的排序**之前**（先按名字排好让同名的挨在一起），而 `CUtlVector::Sort` 不稳定，所以同一个名字在 GAME 和 MOD 里都存在时**留下哪一份是任意的** —— 于是 `sizeasc` / `dateasc` 下这一个名字的位置由任一副本的大小/时间决定 | `:1297`-`:1314` |
| `data/` 下的名字转小写 | 是写侧（`file.Write` / `file.Rename`）的规则，**`file.Find` 本身不折叠大小写**，返回的是磁盘上的真实名字 | `:749`-`:754` |

⚠️ **别把兼容层里那份 `file.Find` 当成实际行为**：`lua/includes/modules/gmod_compatibility/sh_file.lua:34`
另有一份 Lua 包装，它会**丢掉 `sorting` 参数**并打印
`file.Find Sorting is not supported in the GMod compatibility layer!`。
但它是 Experiment: Source 的移植件，被 `GMOD_COMPATIBILITY = false` 挡在门外
（`lua/includes/modules/gmod_compatibility.lua:30`-`:34`），**默认不加载** ——
所以实际生效的是 §1 的引擎绑定，`sorting` 是有效的。

## 6. 相关页面

* [GMod Lua 兼容层](gmod_compat_layer.html) —— 引擎绑定 / Lua 扩展 / GMod 原版文件这三层，
  以及 `file.*` 在兼容层里的位置。
* [Derma 基础指南](derma_basic_guide.html) —— 在 HL2SB 里写 GMod 风格 UI 的实测笔记（同样的排查方法也适用于文件枚举）。
* [GMod Lua 移植计划与状态](gmod_lua_port_plan.html) —— 缺口总表与逐项状态。
* 上游：[file.Find](https://wiki.facepunch.com/gmod/file.Find) ·
  [file](https://wiki.facepunch.com/gmod/file) ·
  [File Search Paths](https://wiki.facepunch.com/gmod/File_Search_Paths)。
