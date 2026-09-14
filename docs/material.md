---
title: Material / CreateMaterial
---

# Material / CreateMaterial

这两个全局是 Lua 拿到 [IMaterial](imaterial.html)（材质对象）的主要入口：
`Material( path )` 按名字取一个**已存在的**材质，`CreateMaterial( name, params )` 现场造一个新的。

> **HL2SB 状态：✅ 两个都已实现（引擎侧 C++ 绑定）。**
> `Material()`：客户端是**真正的材质系统查询**（`game/client/lua/litexture.cpp:476`，
> `materials->FindMaterial( name, TEXTURE_GROUP_VGUI, false )`，注册在 `:606`-`:607`）；
> 服务端另有一份**返回 table 的假对象**（`public/lua/materialsystem/limaterial.cpp:445`，注册在 `:490`-`:494`）。
> `CreateMaterial()`：`litexture.cpp:520`，注册在 `:618`-`:619`，**只在客户端**。
> 佐证：`litexture.cpp` 只在 `game/client/client_lua.vpc:54` 里，
> 部署的 `client.dll` 里能搜到 `CreateMaterial` / `Material` 字符串，`server.dll` 里**只有 `Material`、没有 `CreateMaterial`**。
>
> ⚠️ 和 GMod 有两处**签名级**差异：`Material()` 只返回 1 个值（GMod 还返回耗时），
> `CreateMaterial()` 是 **2 个参数**（GMod 是 3 个）—— 详见 §4。

## 1. Material( path )

```text
-- 客户端
IMaterial Material( string materialName )
-- 服务端（返回的不是 IMaterial，见下）
table Material( string materialName )
```

| # | 参数 | 类型 | 说明 |
|---|---|---|---|
| 1 | `materialName` | `string` | 材质名或路径（相对 `materials/`）。也可以直接指向图片文件名（见 §3 的 PNG 说明） |

解析过程（客户端）：`FindMaterial` → 材质字典里找**磁盘创建的**材质 → 找不到就读
`materials/<名字>.vmt`（`materialsystem/cmaterialsystem.cpp:2774`-`:2812`）。
如果 `.vmt` 不存在、而这个名字能解析成图片，引擎会**现场合成一个 `UnlitGeneric` 材质**
（`$basetexture` 指向图片 + translucent/vertexcolor/vertexalpha/nolod，
`cmaterialsystem.cpp:2831`-`:2849`），并且用你给的名字命名，所以 `mat:GetName()` 报的是 `.png`
（`:2867`-`:2869`）—— 这就是 GMod 那种「材质名直接写 `.png`」能用的原因。

| 返回情况 | 结果 |
|---|---|
| 找到 / 合成成功 | `IMaterial`（客户端）。⚠️ 非 error 材质会被 `IncrementReferenceCount()` **钉住**防驱逐（`litexture.cpp:502`-`:505`） |
| 找不到，且不是图片 | 通常是 `___error` 材质（`mat:IsError()` 为 true，`litexture.cpp:472`-`:474` 的注释）；只有 `FindMaterial` 真的给出 NULL 才返回 `nil`（`:481`-`:485`） |

**服务端的 `Material()`** 是另一种东西（`limaterial.cpp:387`-`:411` 的注释解释了原因：
GMod 的实体脚本会在**文件作用域**调用 `Material()`，例如 `ent_nyan_bomb.lua` 开头那两行在
`if ( CLIENT ) then ... return end` **之前**，而客户端的 `Material()` 那个 Lua proxy 在没有
`_CLIENT` 时直接 return —— 于是脚本抛错、`scripted_ents` 注册不上、`ents.Create` 静默返回 NULL）。
它返回一个 **table**，字段/方法：`__path`、`GetName()`（返回路径）、`IsError()`（恒 false）、
`Width()`/`Height()`/`GetTextureID()`（恒 0）、`GetColor()`（恒白色）、`GetTexture()`（再返回一个小 table）
—— 形状和客户端那个 Lua proxy 一致，**故意不碰材质系统**（服务端 DLL 里不做这件事）。

## 2. CreateMaterial( name, params )

```text
IMaterial CreateMaterial( string name, table params )
```

| # | 参数 | 类型 | 说明 |
|---|---|---|---|
| 1 | `name` | `string` | 材质名（⚠️ **不会去重**，见 §4） |
| 2 | `params` | `table` | 平表。`shader` 键选着色器（默认 `"UnlitGeneric"`），**其它每个键都变成一条 VMT 变量** |

值的映射规则（`litexture.cpp:534`-`:552`）：`number` → `SetFloat`、`boolean` → `SetInt` 0/1、
`string` → `SetString`；**其它类型（包括嵌套表）一律被忽略**。
所以 GMod 的 `Proxies` 子表在这里**不生效**（那是 `matproxy` 的事，本 fork 还没做，
见 [移植计划 §9.7](gmod_lua_port_plan.html#97-还没做的按优先级供下一次接着干)）。

返回：成功给出 `IMaterial`（同样 `IncrementReferenceCount()` 钉住，`:563`）；
`materials->CreateMaterial()` 失败或返回 error 材质时给 `nil`（`:557`-`:561`）。

## 3. 示例

**例 1：取一个已有材质并画出来（客户端）**

```lua
local mat = Material( "vgui/wave.png" )     -- 没有 .vmt 也没关系：引擎会合成 UnlitGeneric

if ( mat and !mat:IsError() ) then
	surface.SetMaterial( mat )
	surface.SetDrawColor( 255, 255, 255, 255 )
	surface.DrawTexturedRect( 50, 50, 128, 128 )
end
```

**例 2：CreateMaterial —— 注意签名和「把返回值存起来」**

```lua
-- GMod 的写法是 3 个参数：
--     CreateMaterial( "colortexshp", "VertexLitGeneric", { ["$basetexture"] = "color/white" } )
-- HL2SB 把 shader 放进第 2 个表里：
local mat = CreateMaterial( "hl2sb_colortex", {
	shader         = "VertexLitGeneric",
	["$basetexture"] = "color/white",
	["$model"]       = 1,
	["$translucent"] = 1,
	["$vertexalpha"] = 1,
	["$vertexcolor"] = 1,
} )

-- ⚠️ 只能靠这个返回值：Material( "hl2sb_colortex" ) 找不到它（原因见 §4）
if ( mat ) then
	surface.SetMaterial( mat )
end
```

**例 3：服务端的 `Material()`（返回值只能转交给别的 API）**

```lua
-- 文件作用域调用是安全的（这就是服务端那份实现存在的理由）
local icon = Material( "nyan/cat.png" )

print( icon:GetName() )    -- "nyan/cat.png"
print( icon:IsError() )    -- false（服务端不做查询，所以永远不是 error）
-- 想真正用这个材质，要在客户端再取一次
```

## 4. 与 GMod 的差异 / 注意

| 差异 | 细节 | 源码 |
|---|---|---|
| `Material()` 少一个返回值 | GMod 返回 `IMaterial, number`（第二个是耗时），这里只返回材质 | `litexture.cpp:476`-`:509` |
| `Material()` 忽略第 2 个参数 | GMod 的 `pngParameters`（`"noclamp smooth"` 之类）不支持 | `litexture.cpp:478` 只读第 1 个参数 |
| **`Material()` 找不到 `CreateMaterial()` 造的材质** | 字典查找带 `bManuallyCreated` 标志：`FindMaterial` 传 `false`（只匹配**磁盘创建**的材质），而 `CreateMaterial` 造的材质带 `MATERIAL_IS_MANUALLY_CREATED` 标志（`cmaterial.cpp:496`-`:498`） | `cmaterialsystem.cpp:2801`、`cmaterialdict.h:146`-`:161`、`cmaterialdict.cpp:65` |
| **`!` 前缀不被处理** | GMod 文档让你写 `Material( "!我的材质" )`；本引擎的 `FindMaterialEx` 只做小写 / 去扩展名 / 斜杠修正（`:2782`-`:2812` 里没有剥 `!` 的代码），所以它会去找 `materials/!我的材质.vmt` | `cmaterialsystem.cpp` 同上 |
| `CreateMaterial()` 签名不同 | GMod：`( name, shaderName, materialData )`；这里：`( name, paramsTable )`，shader 放进表里 | `litexture.cpp:520`-`:529` |
| `Proxies` 子表被忽略 | 只认 number / boolean / string 三种值，嵌套表直接跳过 | `litexture.cpp:543`-`:549` |
| **同名材质不去重** | 上游文档说「同名材质已存在就不会新建」；这里 `IMaterialSystem::CreateMaterial` **每次都新建**（`cmaterialsystem.cpp:2708`-`:2715`，注释还写着 "currently only used by the editor!"），所以反复调用会堆出同名材质。`litexture.cpp:517`-`:518` 的注释说「创建（或替换）…… 之后 `Material( name )` 能找到它」——按上面的字典语义这**不成立** | `cmaterialsystem.cpp:2708`-`:2715`、`:2721`-`:2743`（对比：带 `true` 标志的 `FindProceduralMaterial` 才是查找/复用） |
| `CreateMaterial()` 仅客户端 | 服务端 Lua 里它是 `nil`；`server.dll` 里没有这个字符串 | `client_lua.vpc:54`、`lsrcinit.cpp:182`-`:191` |
| 菜单（GameUI）状态没有 | 菜单 Lua state 只开了一小撮库，`ITexture` / `IMaterial` 都不在其中 —— GMod 上游标注 `Material` 在 menu 状态可用 | `game/shared/lua/luamanager.cpp`（菜单库清单里没有它们） |
| 服务端的 `Material()` 不是材质 | 是 table；`Width`/`Height`/`GetTextureID` 恒 0、`GetColor` 恒白。**别拿它去 `surface.SetMaterial`**（服务端也没 `surface`） | `limaterial.cpp:412`-`:474` |

## 5. 相关页面

* [IMaterial](imaterial.html) —— 拿到的对象有哪些方法、和 GMod 差在哪。
* [CreateSound / CSoundPatch](csoundpatch.html) —— 另一个「引擎对象 + GMod 名字」的绑定，坑的形状很像。
* [GMod Lua 兼容层](gmod_compat_layer.html) —— `.png` 直读、材质合成这些兼容层改动的位置。
* 上游：[Material](https://wiki.facepunch.com/gmod/Global.Material) ·
  [CreateMaterial](https://wiki.facepunch.com/gmod/Global.CreateMaterial) ·
  [IMaterialSystem::FindMaterial](https://github.com/pmrowla/hl2sdk-csgo/blob/master/public/materialsystem/imaterialsystem.h)。
