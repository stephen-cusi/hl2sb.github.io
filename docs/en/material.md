---
title: Material / CreateMaterial
---

# Material / CreateMaterial

These two globals are Lua's main entry points for getting an [IMaterial](imaterial.html) (material object):
`Material( path )` fetches an **already existing** material by name, `CreateMaterial( name, params )` builds a new one on the fly.

> **HL2SB status: ✅ both are implemented (engine-side C++ bindings).**
> `Material()`: on the client it is a **real material system query** (`game/client/lua/litexture.cpp:476`,
> `materials->FindMaterial( name, TEXTURE_GROUP_VGUI, false )`, registered at `:606`-`:607`);
> on the server there is a separate **fake object that returns a table** (`public/lua/materialsystem/limaterial.cpp:445`, registered at `:490`-`:494`).
> `CreateMaterial()`: `litexture.cpp:520`, registered at `:618`-`:619`, **client only**.
> Corroboration: `litexture.cpp` is only in `game/client/client_lua.vpc:54`,
> the deployed `client.dll` has the `CreateMaterial` / `Material` strings in it, while `server.dll` has **only `Material`, no `CreateMaterial`**.
>
> ⚠️ There are two **signature-level** differences from GMod: `Material()` returns only 1 value (GMod also returns the elapsed time),
> `CreateMaterial()` takes **2 arguments** (GMod takes 3) — see §4 for details.

## 1. Material( path ) {#1-material-path}

```text
-- client
IMaterial Material( string materialName )
-- server (what it returns is not an IMaterial, see below)
table Material( string materialName )
```

| # | Argument | Type | Description |
|---|---|---|---|
| 1 | `materialName` | `string` | Material name or path (relative to `materials/`). It can also point directly at an image filename (see the PNG note in §3) |

How it is resolved (client): `FindMaterial` → look in the material dictionary for a **file-created** material → if that fails, read
`materials/<name>.vmt` (`materialsystem/cmaterialsystem.cpp:2774`-`:2812`).
If the `.vmt` does not exist but the name can be resolved as an image, the engine **synthesises an `UnlitGeneric` material on the fly**
(`$basetexture` pointing at the image + translucent/vertexcolor/vertexalpha/nolod,
`cmaterialsystem.cpp:2831`-`:2849`), and names it with the name you gave, so `mat:GetName()` reports the `.png`
(`:2867`-`:2869`) — this is why GMod's habit of "writing the `.png` directly as the material name" works.

| Return case | Result |
|---|---|
| Found / synthesised successfully | `IMaterial` (client). ⚠️ A non-error material is **pinned** against eviction by `IncrementReferenceCount()` (`litexture.cpp:502`-`:505`) |
| Not found, and not an image | Usually the `___error` material (`mat:IsError()` is true, the comment at `litexture.cpp:472`-`:474`); `nil` is returned only when `FindMaterial` really gives NULL (`:481`-`:485`) |

**The server-side `Material()`** is a different thing (the comment at `limaterial.cpp:387`-`:411` explains why:
GMod entity scripts call `Material()` at **file scope**, for example the two lines at the start of `ent_nyan_bomb.lua` come
**before** `if ( CLIENT ) then ... return end`, while the client's `Material()` Lua proxy returns directly when there is no
`_CLIENT` — so the script throws an error, `scripted_ents` cannot register, and `ents.Create` silently returns NULL).
It returns a **table**, fields/methods: `__path`, `GetName()` (returns the path), `IsError()` (always false),
`Width()`/`Height()`/`GetTextureID()` (always 0), `GetColor()` (always white), `GetTexture()` (returns another small table)
— the shape matches the client's Lua proxy, and it **deliberately does not touch the material system** (the server DLL does not do this).

## 2. CreateMaterial( name, params ) {#2-creatematerial-name-params}

```text
IMaterial CreateMaterial( string name, table params )
```

| # | Argument | Type | Description |
|---|---|---|---|
| 1 | `name` | `string` | Material name (⚠️ **it does not de-duplicate**, see §4) |
| 2 | `params` | `table` | Flat table. The `shader` key picks the shader (default `"UnlitGeneric"`), and **every other key becomes one VMT variable** |

The rules for mapping values (`litexture.cpp:534`-`:552`): `number` → `SetFloat`, `boolean` → `SetInt` 0/1,
`string` → `SetString`; **any other type (including nested tables) is ignored outright**.
So GMod's `Proxies` subtable **has no effect** here (that is `matproxy`'s business, and this fork has not done it yet,
see the [port plan §9.7](gmod_lua_port_plan.html#97-还没做的按优先级供下一次接着干)).

Return: on success it gives an `IMaterial` (likewise pinned with `IncrementReferenceCount()`, `:563`);
when `materials->CreateMaterial()` fails or returns an error material it gives `nil` (`:557`-`:561`).

## 3. Examples {#3-示例}

**Example 1: fetch an image material and draw it (client)**

```lua
-- materials/gwenskin/gmoddefault.png is 512x512; having no matching .vmt is fine:
-- the engine synthesises an UnlitGeneric material for it (cmaterialsystem.cpp:2831-2849)
local mat = Material( "gwenskin/gmoddefault.png" )

print( mat:IsError() )      -- synthesis succeeded, so it is not an error material
print( mat:GetName() )      -- image materials keep the name you gave
print( mat:Width() )        -- width of the texture behind $basetexture
print( mat:Height() )       -- height

if ( !mat:IsError() ) then
	surface.SetMaterial( mat )
	surface.SetDrawColor( 255, 255, 255, 255 )
	surface.DrawTexturedRect( 50, 50, 128, 128 )
end
```

**Output:**
```text
false
gwenskin/gmoddefault.png
512
512
```

**Example 2: CreateMaterial — note the signature and "store the return value"**

```lua
-- GMod's spelling is 3 arguments:
--     CreateMaterial( "colortexshp", "VertexLitGeneric", { ["$basetexture"] = "color/white" } )
-- HL2SB puts the shader into the 2nd table:
local mat = CreateMaterial( "hl2sb_colortex", {
	shader           = "VertexLitGeneric",
	["$basetexture"] = "gwenskin/gmoddefault.png",
	["$translucent"] = 1,
} )

print( mat ~= nil )                              -- it was created
print( mat:GetName() )                           -- the name you passed
print( mat:GetShaderName() )                     -- whatever the shader key selected
print( Material( "hl2sb_colortex" ):IsError() )  -- ⚠️ true: Material() cannot find it (see §4)
```

**Output:**
```text
true
hl2sb_colortex
VertexLitGeneric
true
```

**Example 3: the server-side `Material()` (the return value can only be handed to another API)**

```lua
-- Calling it at file scope is safe (this is the reason that server-side implementation exists)
local icon = Material( "nyan/cat.png" )

print( icon:GetName() )    -- the server just stores that string
print( icon:IsError() )    -- false (the server does no query, so it is never an error)
print( icon:Width() )      -- 0 (the server never touches the material system)
-- To actually use this material, fetch it once more on the client
```

**Output:**
```text
nyan/cat.png
false
0
```

## 4. Differences from GMod / gotchas {#4-与-gmod-的差异-注意}

| Difference | Detail | Source |
|---|---|---|
| `Material()` returns one value fewer | GMod returns `IMaterial, number` (the second being the elapsed time); here only the material is returned | `litexture.cpp:476`-`:509` |
| `Material()` ignores the 2nd argument | GMod's `pngParameters` (`"noclamp smooth"` and the like) are not supported | `litexture.cpp:478` reads only the 1st argument |
| **`Material()` cannot find a material made by `CreateMaterial()`** | The dictionary lookup carries the `bManuallyCreated` flag: `FindMaterial` passes `false` (matching only **file-created** materials), while a material made by `CreateMaterial` carries the `MATERIAL_IS_MANUALLY_CREATED` flag (`cmaterial.cpp:496`-`:498`) | `cmaterialsystem.cpp:2801`, `cmaterialdict.h:146`-`:161`, `cmaterialdict.cpp:65` |
| **the `!` prefix is not handled** | GMod's documentation has you write `Material( "!my_material" )`; this engine's `FindMaterialEx` only lowercases / strips the extension / corrects the slashes (there is no code stripping `!` in `:2782`-`:2812`), so it goes looking for `materials/!my_material.vmt` | `cmaterialsystem.cpp`, same as above |
| `CreateMaterial()` has a different signature | GMod: `( name, shaderName, materialData )`; here: `( name, paramsTable )`, with the shader put inside the table | `litexture.cpp:520`-`:529` |
| The `Proxies` subtable is ignored | Only the three value types number / boolean / string are recognized; nested tables are skipped outright | `litexture.cpp:543`-`:549` |
| **materials with the same name are not de-duplicated** | The upstream documentation says "if a material with the same name already exists it will not be created anew"; here `IMaterialSystem::CreateMaterial` **creates a new one every single time** (`cmaterialsystem.cpp:2708`-`:2715`, where the comment even reads "currently only used by the editor!"), so calling it repeatedly piles up materials with the same name. The comment at `litexture.cpp:517`-`:518` says "create (or replace) … after that `Material( name )` can find it" — under the dictionary semantics above this **does not hold** | `cmaterialsystem.cpp:2708`-`:2715`, `:2721`-`:2743` (by contrast: `FindProceduralMaterial` with the `true` flag is the one that looks up / reuses) |
| `CreateMaterial()` is client-only | In server Lua it is `nil`; that string is not in `server.dll` | `client_lua.vpc:54`, `lsrcinit.cpp:182`-`:191` |
| Missing in the menu (GameUI) state | The menu Lua state opens only a small handful of libraries, and `ITexture` / `IMaterial` are not among them — upstream GMod marks `Material` as available in the menu state | `game/shared/lua/luamanager.cpp` (they are not in the menu library list) |
| The server's `Material()` is not a material | It is a table; `Width`/`Height`/`GetTextureID` are always 0 and `GetColor` is always white. **Do not pass it to `surface.SetMaterial`** (the server has no `surface` either) | `limaterial.cpp:412`-`:474` |

## 5. Related pages {#5-相关页面}

* [IMaterial](imaterial.html) — what methods the object you get has, and where it differs from GMod.
* [CreateSound / CSoundPatch](csoundpatch.html) — another "engine object + GMod name" binding, with gotchas of a very similar shape.
* [GMod Lua compatibility layer](gmod_compat_layer.html) — where the compatibility-layer changes such as reading `.png` directly and synthesising materials live.
* Upstream: [Material](https://wiki.facepunch.com/gmod/Global.Material) ·
  [CreateMaterial](https://wiki.facepunch.com/gmod/Global.CreateMaterial) ·
  [IMaterialSystem::FindMaterial](https://github.com/pmrowla/hl2sdk-csgo/blob/master/public/materialsystem/imaterialsystem.h).
