---
title: IMaterial
---

# IMaterial

`IMaterial` 是引擎的**材质对象**（`.vmt` 被读进来之后在内存里的样子）。
GMod 的 Lua 里它是个用户数据：可以问名字、问着色器、拿 `$basetexture` 对应的贴图、
按坐标采样颜色，也可以改材质变量。

> **HL2SB 状态：✅ 类存在，而且现在**拿得到**了。**
> 绑定在 `public/lua/materialsystem/limaterial.cpp`（元表名 `IMaterial`，
> `:482`-`:488`；方法表 `IMaterialmeta` 在 `:335`-`:384`，共 46 个方法 + `__tostring`），
> **client.dll 与 server.dll 都编**（`client_lua.vpc:127`、`server_lua.vpc:93`）。
> 取得入口是 `Material()` / `CreateMaterial()` / `Entity:GetMaterials()`
> （见 §1 的表）；GMod 常用的 `GetTexture` / `Width` / `Height` / `IsError` / `GetColor`
> 这几个名字是 `game/client/lua/litexture.cpp:582`-`:604` 在**客户端**补上去的。
>
> ⚠️ **两端方法集不一样**：上面那 5 个名字只在客户端有（`litexture.cpp` 不在 `server_lua.vpc` 里），
> 服务端拿到的 `IMaterial` 只有引擎原生的 46 个方法。

## 1. 怎么拿到一个 IMaterial

| 入口 | 端 | 返回 | 源码 |
|---|---|---|---|
| [Material( path )](material.html) | 客户端 | `IMaterial`（或 `nil`） | `litexture.cpp:476` |
| [Material( path )](material.html) | 服务端 | ⚠️ **table 假对象**，不是 IMaterial | `limaterial.cpp:445` |
| [CreateMaterial( name, params )](material.html) | 客户端 | `IMaterial` | `litexture.cpp:520` |
| `Entity:GetMaterials()` | 客户端 + 服务端（都有这个绑定） | `table`（1 起索引的 IMaterial 表）+ `integer`（数量） | `game/shared/lua/lbaseanimating_shared.cpp:272`-`:306` |
| `IMaterial:GetMaterialPage()` | 两端 | `IMaterial`（材质页，`GetMaterialPage` 在 `limaterial.cpp:113`） | `limaterial.cpp:347` |

⚠️ 关于 `Entity:GetMaterials()`：它去问的是 `g_pStudioRender->GetMaterialList()`
（`lbaseanimating_shared.cpp:287`）—— 那条路**只在客户端实测过**，
服务端（没有 studio render）能不能用**没有验证**，别在服务端依赖它。

## 2. GMod 的 IMaterial 方法对照

上游 [IMaterial](https://wiki.facepunch.com/gmod/IMaterial) 文档化了 24 个方法，
在本 fork 里的对应情况：

| GMod 方法 | HL2SB | 说明 |
|---|---|---|
| `GetName()` | ✅ | `limaterial.cpp:128`（引擎原生） |
| `GetColor( x, y )` | ✅ | 客户端是 HL2SB 的 PNG 像素采样（`litexture.cpp:428`）；服务端原生版走 `GetLowResColorSample`（`limaterial.cpp:322`）—— 见 §4 |
| `GetTexture( param )` | ✅ 客户端 | `litexture.cpp:271`；服务端**没有**这个名字 |
| `Width()` / `Height()` | ✅ 客户端 | `litexture.cpp:312` / `:320`，取 `$basetexture` 的贴图尺寸 |
| `IsError()` | ✅ 客户端 | `litexture.cpp:328`。服务端请用原生名字 `IsErrorMaterial()` |
| `GetShader()` | ⚠️ 名字不同 | 原生版叫 **`GetShaderName()`**（`limaterial.cpp:153`），没补 GMod 的短名 |
| `SetShader( name )` | ✅（行为不同） | `limaterial.cpp:268` 真的调用 `IMaterial::SetShader`；GMod 里这个方法**已废弃、什么都不做** |
| `Recompute()` | ⚠️ 名字不同 | 原生版叫 **`RecomputeStateSnapshots()`**（`limaterial.cpp:243`） |
| `GetFloat( name )` / `SetFloat( name, f )` | ❌ | **没有材质变量读写**，见 §7 |
| `GetInt( name )` / `SetInt( name, i )` | ❌ | 同上 |
| `GetString( name )` / `SetString( name, s )` | ❌ | 同上 |
| `GetVector( name )` / `SetVector( name, vec )` | ❌ | 同上（`matproxy` 需要它，见 [移植计划](gmod_lua_port_plan.html#97-还没做的按优先级供下一次接着干)） |
| `GetVectorLinear( name )` / `GetVector4D( name )` / `SetVector4D( ... )` | ❌ | 同上 |
| `GetMatrix( name )` / `SetMatrix( name, m )` | ❌ | 同上 |
| `GetKeyValues()` | ❌ | 没有 |
| `SetTexture( name, tex )` | ❌ | 没有（**只读**不到写） |
| `SetUndefined( name )` / `SetDynamicImage( path )` | ❌ | 没有 |

## 3. 引擎原生方法（46 个，两端都有）

这些是 Valve 自己的 Lua 绑定直接暴露出来的，GMod 文档里没有，但插件偶尔会碰到：

| 组 | 方法 |
|---|---|
| 名字 / 来源 | `GetName` · `GetShaderName` · `GetTextureGroupName` · `GetEnumerationID` · `GetMorphFormat` · `__tostring` |
| 调制 | `AlphaModulate` · `ColorModulate` · `GetAlphaModulation` · `GetColorModulation` · `SetUseFixedFunctionBakedLighting` |
| 是否 / 需要（布尔查询） | `IsAlphaTested` · `IsErrorMaterial` · `IsSpriteCard` · `IsTranslucent` · `IsTwoSided` · `IsVertexLit` · `HasProxy` · `InMaterialPage` · `UsesEnvCubemap` · `WasReloadedFromWhitelist` · `NeedsFullFrameBufferTexture` · `NeedsLightmapBlendAlpha` · `NeedsPowerOfTwoFrameBufferTexture` · `NeedsSoftwareLighting` · `NeedsSoftwareSkinning` · `NeedsTangentSpace` |
| 尺寸 / 计数 / 查询 | `GetMappingWidth` · `GetMappingHeight` · `GetMaterialPage` · `GetTextureMemoryBytes` · `GetNumAnimationFrames` · `GetNumPasses` · `ShaderParamCount` · `GetReflectivity` · `GetMaterialVarFlag` · `GetPropertyFlag` |
| 刷新 | `RecomputeStateSnapshots` · `Refresh` · `RefreshPreservingMaterialVars` |
| 写（少数） | `SetMaterialVarFlag( flag, bool )` · `SetShader( name )` |
| **引用计数（手动）** | `AddRef` · `Release` · `IncrementReferenceCount` · `DecrementReferenceCount` · `DeleteIfUnreferenced` |

## 4. HL2SB 在客户端补的 5 个名字

`litexture.cpp:582`-`:604` 在客户端把 GMod 的名字挂到 `IMaterial` 元表上：

* `GetTexture( varName = "$basetexture" )`（`:271`）：先查 `IMaterialVar`；变量没了就**按名字回退**
  去材质系统找贴图（`:250`-`:300`，这是「皮肤贴图找不到」那一类问题的根因之一）。
* `Width()` / `Height()`（`:312` / `:320`）：取 `$basetexture` 那张贴图的尺寸。
* `IsError()`（`:328`）：`IsErrorMaterial()` 的 GMod 拼写。
* `GetColor( x, y )`（`:428`）：HL2SB 特有的**PNG 像素采样**（带缓存）。
  原生 `limaterial.cpp:322` 的 `GetColor` 用的是引擎的 `GetLowResColorSample`，
  对程序化贴图（PNG 直读）会**全黑**——这也是 derma_gwen 皮肤全白的根因。
  两边同名，**客户端最终生效的是 `litexture.cpp` 那份**：`luaopen_IMaterial`（`lsrcinit.cpp:114`）
  先跑、`luaopen_ITexture`（`:187`）后跑，后者覆盖前者。

⚠️ 所以 `GetColor` 在两个端是**两种实现**：客户端采样图片像素，服务端走低分辨率采样
（服务端的 IMaterial 也只有原生那份，没有 `GetTexture`/`Width`/`Height`/`IsError`）。

## 5. 生命周期 / 引用计数

* 元表里**没有 `__gc`**（方法表 `limaterial.cpp:335`-`:384` 里没有），
  所以 Lua 回收用户数据**不会**释放材质 —— 引用计数得自己管：
  `AddRef` / `IncrementReferenceCount` 加，`DecrementReferenceCount` / `Release` /
  `DeleteIfUnreferenced` 减。
* `Material()` 和 `CreateMaterial()` 都会替你 `IncrementReferenceCount()` 一次
  （`litexture.cpp:504` / `:563`，注释写明是为了防材质被驱逐后中途重解析）——
  也就是说**每调用一次就多一份引用**，长循环里反复取材质是漏引用。
* 引擎自己的材质由材质系统持有；`Refresh()` 对**没有 `.vmt` 的程序化材质**是毒的
  （`litexture.cpp:487`-`:495` 记录了实测：每帧刷 `CMaterial::PrecacheVars: error loading vmt file`）。

## 6. 哪些状态里有

| 状态 | IMaterial / Material |
|---|---|
| 客户端 | ✅ |
| 服务端 | ⚠️ 类本身在（元表 + 46 个方法），但入口只有 `Entity:GetMaterials()`（未验证）与 `Material()` 的 table 假对象 |
| 菜单（GameUI） | ❌ 菜单 Lua state 只开了一小撮库，`IMaterial` / `ITexture` 都不在其中（`game/shared/lua/luamanager.cpp`）；GMod 上游的 `Material` 是标注「客户端 / 服务端 / 菜单」三态可用的 |

## 7. 与 GMod 的差异 / 注意

| 差异 | 细节 |
|---|---|
| **没有材质变量读写** | `GetFloat`/`SetFloat`/`GetInt`/`SetInt`/`GetString`/`SetString`/`GetVector`/`SetVector`/`GetMatrix`/`SetMatrix`/`GetKeyValues`/`SetTexture` 全都没有。这是相对 GMod 最大的一块缺口，也是 `matproxy` 移植卡住的地方（需要 `IMaterial:SetVector`） |
| 名字不完全一样 | `GetShader` → `GetShaderName`；`Recompute` → `RecomputeStateSnapshots`；`IsError` 只在客户端有（服务端用 `IsErrorMaterial`） |
| 服务端少 5 个方法 | `GetTexture` / `Width` / `Height` / `IsError` 是客户端补的 |
| `GetColor` 两个实现 | 客户端 PNG 采样、服务端低分辨率采样，行为可能不同 |
| `SetShader` 反而「更真」 | GMod 把它废弃成空操作，这里会真调引擎（可能触发材质重解析，别在渲染钩子里狂调） |
| 拿得到的方式变了 | `Material("!名字")` 拿不到 `CreateMaterial` 的结果（见 [Material / CreateMaterial §4](material.html#4-与-gmod-的差异-注意)）—— 请保存 `CreateMaterial` 的返回值 |
| 没有 `__gc` | 见 §5：忘掉 `Release` 就是漏引用 |

## 8. 相关页面

* [Material / CreateMaterial](material.html) —— 怎么拿到 IMaterial，以及那两个全局的坑。
* [CreateSound / CSoundPatch](csoundpatch.html) —— 同类的「引擎对象绑定」。
* [GMod Lua 兼容层](gmod_compat_layer.html) —— 引擎绑定 + Lua 扩展 + GMod 原版文件这三层。
* 上游：[IMaterial](https://wiki.facepunch.com/gmod/IMaterial) ·
  [IMaterialSystem](https://github.com/pmrowla/hl2sdk-csgo/blob/master/public/materialsystem/imaterialsystem.h)。
