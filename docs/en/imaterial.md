---
title: IMaterial
---

# IMaterial

`IMaterial` is the engine's **material object** (what a `.vmt` looks like in memory once it has been
read in). In GMod's Lua it is a userdata: you can ask it for its name and its shader, get the texture
behind `$basetexture`, sample a color by coordinates, and change material variables.

> **HL2SB status: ✅ the class exists, and now you can**obtain it**.** The binding is in
> `public/lua/materialsystem/limaterial.cpp` (metatable name `IMaterial`, `:482`-`:488`; the method
> table `IMaterialmeta` is at `:335`-`:384`, 46 methods + `__tostring` in total), **compiled into
> both client.dll and server.dll** (`client_lua.vpc:127`, `server_lua.vpc:93`).
> The entry points are `Material()` / `CreateMaterial()` / `Entity:GetMaterials()`
> (see the table in §1); the names GMod commonly uses — `GetTexture` / `Width` / `Height` /
> `IsError` / `GetColor` — are added on the **client** at `game/client/lua/litexture.cpp:582`-`:604`.
>
> ⚠️ **The two realms do not have the same method set**: those 5 names above exist only on the
> client (`litexture.cpp` is not in `server_lua.vpc`), and the `IMaterial` the server gets has only
> the engine's 46 native methods.

## 1. How to obtain an IMaterial {#1-怎么拿到一个-imaterial}

| Entry point | Realm | Returns | Source |
|---|---|---|---|
| [Material( path )](material.html) | Client | `IMaterial` (or `nil`) | `litexture.cpp:476` |
| [Material( path )](material.html) | Server | ⚠️ **fake table object**, not an IMaterial | `limaterial.cpp:445` |
| [CreateMaterial( name, params )](material.html) | Client | `IMaterial` | `litexture.cpp:520` |
| `Entity:GetMaterials()` | Client + server (both have this binding) | `table` (a 1-based table of IMaterials) + `integer` (the count) | `game/shared/lua/lbaseanimating_shared.cpp:272`-`:306` |
| `IMaterial:GetMaterialPage()` | Both realms | `IMaterial` (a material page; `GetMaterialPage` is at `limaterial.cpp:113`) | `limaterial.cpp:347` |

⚠️ About `Entity:GetMaterials()`: what it asks is `g_pStudioRender->GetMaterialList()`
(`lbaseanimating_shared.cpp:287`) — that path has **only been tested on the client**, and whether the
server (which has no studio render) can use it is **unverified**, so do not depend on it on the server.

**Example: obtain an IMaterial and ask it a few questions** (client)

```lua
local mat = Material( "gwenskin/gmoddefault.png" )

print( mat:GetName() )              -- image materials keep the name you gave
print( mat:GetShaderName() )        -- the shader the engine synthesised for the image
print( mat:GetTextureGroupName() )  -- Material() uses TEXTURE_GROUP_VGUI
print( mat:Width() )                -- width of $basetexture
print( mat:Height() )               -- height
print( mat:IsError() )              -- not an error material when synthesis succeeded

mat:SetShader( "UnlitGeneric" )     -- only a handful of write operations exist
mat:RecomputeStateSnapshots()       -- what GMod calls Recompute()
```

**Output:**
```text
gwenskin/gmoddefault.png
UnlitGeneric
VGUI textures
512
512
false
```

## 2. Mapping GMod's IMaterial methods {#2-gmod-的-imaterial-方法对照}

Upstream [IMaterial](https://wiki.facepunch.com/gmod/IMaterial) documents 24 methods; here is how
they map in this fork:

| GMod method | HL2SB | Notes |
|---|---|---|
| `GetName()` | ✅ | `limaterial.cpp:128` (engine-native) |
| `GetColor( x, y )` | ✅ | On the client it is HL2SB's PNG pixel sampling (`litexture.cpp:428`); the server's native version goes through `GetLowResColorSample` (`limaterial.cpp:322`) — see §4 |
| `GetTexture( param )` | ✅ Client | `litexture.cpp:271`; the server does **not** have this name |
| `Width()` / `Height()` | ✅ Client | `litexture.cpp:312` / `:320`, the texture size of `$basetexture` |
| `IsError()` | ✅ Client | `litexture.cpp:328`. On the server use the native name `IsErrorMaterial()` |
| `GetShader()` | ⚠️ Different name | The native version is called **`GetShaderName()`** (`limaterial.cpp:153`); GMod's short name was not added |
| `SetShader( name )` | ✅ (different behavior) | `limaterial.cpp:268` really calls `IMaterial::SetShader`; in GMod this method is **deprecated and does nothing** |
| `Recompute()` | ⚠️ Different name | The native version is called **`RecomputeStateSnapshots()`** (`limaterial.cpp:243`) |
| `GetFloat( name )` / `SetFloat( name, f )` | ❌ | **No material variable read/write**, see §7 |
| `GetInt( name )` / `SetInt( name, i )` | ❌ | Same as above |
| `GetString( name )` / `SetString( name, s )` | ❌ | Same as above |
| `GetVector( name )` / `SetVector( name, vec )` | ❌ | Same as above (`matproxy` needs it, see the [port plan](gmod_lua_port_plan.html#97-还没做的按优先级供下一次接着干)) |
| `GetVectorLinear( name )` / `GetVector4D( name )` / `SetVector4D( ... )` | ❌ | Same as above |
| `GetMatrix( name )` / `SetMatrix( name, m )` | ❌ | Same as above |
| `GetKeyValues()` | ❌ | Not present |
| `SetTexture( name, tex )` | ❌ | Not present (**read-only**, no write) |
| `SetUndefined( name )` / `SetDynamicImage( path )` | ❌ | Not present |

## 3. Engine-native methods (46, present in both realms) {#3-引擎原生方法46-个两端都有}

These are exposed directly by Valve's own Lua bindings; they are not in GMod's documentation, but
addons occasionally run into them:

| Group | Methods |
|---|---|
| Names / origin | `GetName` · `GetShaderName` · `GetTextureGroupName` · `GetEnumerationID` · `GetMorphFormat` · `__tostring` |
| Modulation | `AlphaModulate` · `ColorModulate` · `GetAlphaModulation` · `GetColorModulation` · `SetUseFixedFunctionBakedLighting` |
| Is / Needs (boolean queries) | `IsAlphaTested` · `IsErrorMaterial` · `IsSpriteCard` · `IsTranslucent` · `IsTwoSided` · `IsVertexLit` · `HasProxy` · `InMaterialPage` · `UsesEnvCubemap` · `WasReloadedFromWhitelist` · `NeedsFullFrameBufferTexture` · `NeedsLightmapBlendAlpha` · `NeedsPowerOfTwoFrameBufferTexture` · `NeedsSoftwareLighting` · `NeedsSoftwareSkinning` · `NeedsTangentSpace` |
| Size / counts / queries | `GetMappingWidth` · `GetMappingHeight` · `GetMaterialPage` · `GetTextureMemoryBytes` · `GetNumAnimationFrames` · `GetNumPasses` · `ShaderParamCount` · `GetReflectivity` · `GetMaterialVarFlag` · `GetPropertyFlag` |
| Refresh | `RecomputeStateSnapshots` · `Refresh` · `RefreshPreservingMaterialVars` |
| Writes (a few) | `SetMaterialVarFlag( flag, bool )` · `SetShader( name )` |
| **Reference counting (manual)** | `AddRef` · `Release` · `IncrementReferenceCount` · `DecrementReferenceCount` · `DeleteIfUnreferenced` |

## 4. The 5 names HL2SB adds on the client {#4-hl2sb-在客户端补的-5-个名字}

`litexture.cpp:582`-`:604` hangs GMod's names onto the `IMaterial` metatable on the client:

* `GetTexture( varName = "$basetexture" )` (`:271`): it looks up the `IMaterialVar` first; once the
  variable is gone it **falls back by name** to the material system to find a texture (`:250`-`:300`,
  one of the root causes of the "skin texture not found" class of problems).
* `Width()` / `Height()` (`:312` / `:320`): the size of the texture that `$basetexture` points to.
* `IsError()` (`:328`): the GMod spelling of `IsErrorMaterial()`.
* `GetColor( x, y )` (`:428`): HL2SB-specific **PNG pixel sampling** (with a cache).
  The native `GetColor` at `limaterial.cpp:322` uses the engine's `GetLowResColorSample`, which for
  procedural textures (read straight from PNG) comes out **all black** — this is also the root cause
  of the derma_gwen skin being all white. Both realms use the same name, and **the copy that wins on
  the client is the `litexture.cpp` one**: `luaopen_IMaterial` (`lsrcinit.cpp:114`) runs first and
  `luaopen_ITexture` (`:187`) runs after, the latter overwriting the former.

⚠️ So `GetColor` has **two implementations** across the two realms: the client samples image pixels,
the server goes through low-resolution sampling (and the server's IMaterial only has the native
copy, with no `GetTexture`/`Width`/`Height`/`IsError`).

## 5. Lifetime / reference counting {#5-生命周期-引用计数}

* The metatable has **no `__gc`** (it is not in the method table `limaterial.cpp:335`-`:384`), so Lua
  collecting the userdata does **not** release the material — the reference count has to be managed
  by hand: `AddRef` / `IncrementReferenceCount` to add, `DecrementReferenceCount` / `Release` /
  `DeleteIfUnreferenced` to subtract.
* Both `Material()` and `CreateMaterial()` call `IncrementReferenceCount()` once for you
  (`litexture.cpp:504` / `:563`; the comment states this is to prevent the material from being
  evicted and re-parsed mid-way) — that is, **every call adds one more reference**, so fetching
  materials repeatedly in a long loop leaks references.
* The engine's own materials are held by the material system; `Refresh()` is poison for **procedural
  materials with no `.vmt`** (`litexture.cpp:487`-`:495` records the actual test: refreshing every
  frame gives `CMaterial::PrecacheVars: error loading vmt file`).

## 6. Which states have it {#6-哪些状态里有}

| State | IMaterial / Material |
|---|---|
| Client | ✅ |
| Server | ⚠️ The class itself is there (metatable + 46 methods), but the only entry points are `Entity:GetMaterials()` (unverified) and `Material()`'s fake table object |
| Menu (GameUI) | ❌ The menu Lua state opens only a small handful of libraries, and neither `IMaterial` nor `ITexture` is among them (`game/shared/lua/luamanager.cpp`); upstream GMod's `Material` is marked as available in all three states — "client / server / menu" |

## 7. Differences from GMod / caveats {#7-与-gmod-的差异-注意}

| Difference | Details |
|---|---|
| **No material variable read/write** | `GetFloat`/`SetFloat`/`GetInt`/`SetInt`/`GetString`/`SetString`/`GetVector`/`SetVector`/`GetMatrix`/`SetMatrix`/`GetKeyValues`/`SetTexture` are all missing. This is the biggest single gap relative to GMod, and the place where the `matproxy` port is stuck (it needs `IMaterial:SetVector`) |
| Names are not exactly the same | `GetShader` → `GetShaderName`; `Recompute` → `RecomputeStateSnapshots`; `IsError` exists only on the client (the server uses `IsErrorMaterial`) |
| The server is missing 5 methods | `GetTexture` / `Width` / `Height` / `IsError` are added by the client |
| `GetColor` has two implementations | client PNG sampling, server low-resolution sampling; behavior may differ |
| `SetShader` is in fact "more real" | GMod deprecated it into a no-op; here it really calls into the engine (it may trigger a material re-parse, so do not hammer it inside render hooks) |
| The way to obtain one has changed | `Material("!name")` cannot get the result of `CreateMaterial` (see [Material / CreateMaterial §4](material.html#4-与-gmod-的差异-注意)) — save the return value of `CreateMaterial` |
| No `__gc` | see §5: forget `Release` and you leak a reference |

## 8. Related pages {#8-相关页面}

* [Material / CreateMaterial](material.html) — how to obtain an IMaterial, and the pitfalls of those two globals.
* [CreateSound / CSoundPatch](csoundpatch.html) — the same class of "engine object binding".
* [GMod Lua compatibility layer](gmod_compat_layer.html) — the three layers of engine bindings + Lua extensions + GMod's original files.
* Upstream: [IMaterial](https://wiki.facepunch.com/gmod/IMaterial) ·
  [IMaterialSystem](https://github.com/pmrowla/hl2sdk-csgo/blob/master/public/materialsystem/imaterialsystem.h).
