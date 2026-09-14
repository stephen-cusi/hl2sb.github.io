---
title: file.Find
---

# file.Find

`file.Find` lists the **files** and **subdirectories** in a folder — it is the most commonly used file
enumeration entry point in GMod scripts (Spawnmenu looking for `settings/spawnlist/*.txt`, addons
looking for `lua/autorun/*.lua`, the content dialog looking at the neighboring Source games, all rely
on it). The `name` argument is "folder + wildcard", and the return value is **two tables**: one for
files, one for directories.

> **HL2SB status: ✅ implemented — an engine-side C++ binding, not a Lua shim.**
> Implementation: `public/lua/lfilesystem.cpp:1169` (`file_Find`); the line that registers it into
> `file_funcs[]` is at `:1414`; `luaopen_Files` at `:1419` opens the `Files` library, which is then
> exposed through the GMod spelling alias `file`
> (`game/shared/lua/lsrcinit.cpp:553`). `client.dll` and `server.dll` both compile this copy
> (`game/client/client_lua.vpc:116` / `game/server/server_lua.vpc:88`);
> the menu (GameUI) state opens a separate one of its own (`game/shared/lua/luamanager.cpp:345`).
>
> **Relationship to GMod**: the signature, the default sorting, the two return values, and
> "invalid pathID → `nil, nil`" all match upstream
> [file.Find](https://wiki.facepunch.com/gmod/file.Find);
> **the differences are concentrated in pathID coverage** (§4) and the leniency of `sorting` values
> (§5) — every item in those two sections can be pointed at a line number in the source.

## 1. Signature and arguments {#1-签名与参数}

```text
table files, table dirs = file.Find( string name, string pathID, string sorting )
```

| # | Argument | Type | Description (following GMod's wording) |
|---|---|---|---|
| 1 | `name` | `string` | The wildcard to search for. `models/*.mdl` lists the **.mdl** files in `models/`. `*` is the only character that decides whether the string counts as a wildcard (`file_Find` `:1180`); **when there is no `*`, the whole argument is treated as a folder name and the engine appends `/*` itself** (`:1183`-`:1188`), so `file.Find( "gamemodes", "GAME" )` is equivalent to `file.Find( "gamemodes/*", "GAME" )`. |
| 2 | `pathID` | `string` | Which search path to look in. For the values see the table in §4 (upstream list: [File Search Paths](https://wiki.facepunch.com/gmod/File_Search_Paths)). **Passing any other string does not error; it returns `nil, nil`** (`:1218`-`:1223`). |
| 3 | `sorting` | `string` | Optional sorting method, default `nameasc` (`:1227`). For the values see §1.1. |

How the arguments are read (`file_Find` `:1170` / `:1206` / `:1228`): the 1st is `luaL_checkstring`
(**required**), the 2nd and 3rd are `lua_tostring` — that is, **only strings are accepted**: `nil`
means omitted, and a number is converted to a string in place and used as the pathID (`:1206`).
⚠️ This differs from the `file.Exists` family: that one uses `HL2SB_GetPathArg`, which accepts
`true`/`false` (`lfilesystem.cpp:726`-`:733`), while `file.Find` **does not eat booleans**.

### 1.1 Values of sorting {#11-sorting-的取值}

| Value | Meaning | Source |
|---|---|---|
| `nameasc` (default) | Ascending by name | Upstream documentation; `file_Find` `:1227` |
| `namedesc` | Descending by name | `:1245`-`:1246` |
| `dateasc` / `datedesc` | Ascending / descending by modification time | `:1237`-`:1238` (both `date` and `time` go through this) |
| `sizeasc` / `sizedesc` | Ascending / descending by file size | `:1239`-`:1240` |
| `typeasc` / `typedesc` | Files first / directories first | `:1241`-`:1242` |
| `extasc` / `extdesc` | Ascending / descending by extension | `:1243`-`:1244` |

Matching is by **substring** (not exact equality): the value is lowercased first (`:1233`), containing
`desc` means descending (`:1235`), and then it is recognized in the order `time`/`date` → `size` →
`type` → `ext` (`:1237`-`:1244`). **An unrecognized value does not error; it silently falls back to
`nameasc`** (`:1225`-`:1247`); entries with the same sorting key always use **ascending name** as the
tie-break (`HL2SB_FindCmp` `:1101`-`:1106`).

## 2. Return values {#2-返回值}

| # | Type | Description |
|---|---|---|
| 1 | `table` | Table of found **file** names; `nil` when the `pathID` is invalid. Names are **bare names**, without the folder prefix. |
| 2 | `table` | Table of found **directory** names; `nil` when the `pathID` is invalid. Names are likewise bare, **with no trailing `/`**. |

Four key points (all inside `file_Find`):

* **Directory names carry no trailing slash**: like files, directories are put into the table exactly
  as `FindFirstEx` gave the name (`:1336`). The upstream wiki's example output (`Folder: ctp`) is the
  same; add `/` yourself when you need to build a path.
* **Only one level is searched, no recursion**: the search pattern is always `<folder>/<glob>` (`:1210`),
  and the engine's `FindFirstEx` performs a single `FS_FindFirstFile` per search path (`filesystem/basefilesystem.cpp:4076`-`:4078`);
  recursion has to be written yourself (see §3 example 2).
* **Entries starting with `.` are not returned**: `.`, `..` and dot files are all skipped (`:1269`-`:1270`).
* **Entries with the same name are de-duplicated**: the same relative name can come from both GAME and
  MOD (this fork searches the two as a pair, see §4), so de-duplication is by "directory flag + name
  (case-insensitive)" (`:1297`-`:1314`).

The difference between `nil` and an empty table matters; the upstream documentation's sentence refers
to the former:

```lua
-- invalid pathID -> two nils
local files, dirs = file.Find( "*", "NOT_A_PATH_ID" )   -- files == nil, dirs == nil

-- valid pathID, but the folder does not exist or is empty -> two empty tables
files, dirs = file.Find( "no/such/folder/*", "GAME" )   -- files == {}, dirs == {}
```

So the `if ( !files ) then return end` line in GMod scripts guards against an **invalid pathID**; it
does not guard against an empty folder (the source calls this out specifically at `:1214`-`:1217`).

## 3. Examples {#3-示例}

The **Output** of every snippet below is computed from the actual files in this repo's game content
(`D:\srceng\hl2sb`); with your own content the numbers and names will of course differ.

**Example 1: list one folder (default `nameasc`)**

```lua
local files, dirs = file.Find( "weapons/*", "LUA" )

print( #files )          -- no files at this level
print( #dirs )           -- subdirectories only
print( dirs[ 1 ] )       -- nameasc: the first one
print( dirs[ #dirs ] )   -- and the last one
```

**Output:**
```text
0
6
gmod_camera
weapon_medkit
```

**Example 2: recursively expand a directory tree (the idiomatic GMod way)**

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

**Output:** (files of the current folder first, then subdirectories by name — 8 files in total)
```text
lua/entities/sent_ball.lua
lua/entities/prop_example/cl_init.lua
lua/entities/prop_example/init.lua
lua/entities/prop_example/shared.lua
lua/entities/prop_scripted/cl_init.lua
lua/entities/prop_scripted/init.lua
lua/entities/prop_scripted/shared.lua
lua/entities/trigger_scripted/init.lua
```

**Example 3: `LUA` is the `lua/` subtree, `DATA` is the `data/` subtree**

```lua
-- "LUA"/"lcl"/"lsv"/"LuaMenu" all map to GAME + the "lua/" prefix
local weapons = file.Find( "weapons/*.lua", "LUA" )

-- "DATA" maps to MOD + the "data/" prefix (i.e. GMod's garrysmod/data)
file.Write( "hl2sb_demo/notes.txt", "hello" )
local dataFiles = file.Find( "hl2sb_demo/*", "DATA" )

print( #weapons )        -- no .lua directly under lua/weapons (they all live in subfolders)
print( dataFiles[ 1 ] )  -- the file just written (the write side lowercases names under data/)
```

**Output:**
```text
0
notes.txt
```

**Example 4: the sorting argument really takes effect**

```lua
local _, asc  = file.Find( "addons/*", "MOD", "nameasc" )
local _, desc = file.Find( "addons/*", "MOD", "namedesc" )

print( asc[ 1 ] )
print( desc[ 1 ] )
```

**Output:** (the 5 folders in this repo's `hl2sb/addons/`, sorted case-insensitively)
```text
example_addon
The Ultimate Admin Gun Fixed
```

> To check each of the above in place, you can use the probe `lua/file_find_test.lua` from the game
> content repo (console `lua_dofile_cl file_find_test.lua`; it prints item by item the file/directory
> counts, the `nil, nil` of an invalid pathID, the two empty tables of a valid empty directory, and
> the results of nameasc/namedesc).

## 4. pathID support {#4-pathid-支持情况}

The pathID of `file.Find` is resolved by `HL2SB_ResolveFindPathID` (`lfilesystem.cpp:1118`-`:1158`);
the mapping table is `s_GModPathIDs` (`:618`-`:641`); **IDs that are not in the table but that the
engine has actually registered are passed through as-is** (`:1148`-`:1155`, the test being
`HL2SB_PathIDExists`), and everything else is `nil, nil` (`:1157`).

| pathID | HL2SB behavior | Description |
|---|---|---|
| `"GAME"` | ✅ | Searches both the GAME **and** MOD paths (`:1142`-`:1145`), results de-duplicated |
| `"MOD"` / `"garrysmod"` | ✅ | Same as above, MOD first (`:1143`) |
| `"LUA"` / `"lcl"` / `"lsv"` / `"LuaMenu"` | ✅ | GAME + prefix `lua/` (`:628`-`:633`) |
| `"DATA"` / `"WRITE"` | ✅ | MOD + prefix `data/` (`:634`-`:635`) |
| `"THIRDPARTY"` / `"WORKSHOP"` | ⚠️ approximate | MOD + prefix `addons/` (`:639`-`:640`); this engine has no separate workshop tree |
| `"BSP"` | ✅ | Passed through; the engine has this ID registered (`filesystem/basefilesystem.cpp:386`), pointing at the current map's pack file |
| `"BASE_PATH"` / `"EXECUTABLE_PATH"` | ✅ | Passed through; the engine registers them itself (`public/filesystem_init.cpp:1106` / `:1101`) |
| `"GAMEBIN"` / `"DOWNLOAD"` / `"PLATFORM"` / `"CONFIG"` / `"MOD_WRITE"` / `"GAME_WRITE"` / `"DEFAULT_WRITE_PATH"` | ✅ | Passed through; registered by gameinfo.txt (see the comment at `lfilesystem.cpp:605`-`:607`) |
| mounted game names (`"hl2"`, `"cstrike"`…) | ✅ | Passed through; the engine adds a search path for each mounted game (`:1148`-`:1150`) |
| `""` / `"ALL"` / `"NULL"` | ⚠️ extra leniency | All treated as GAME (`:620`-`:623`); upstream documentation does not list these three |
| omitted (`nil`) | ⚠️ extra leniency | Treated as an empty string → searches GAME + MOD (`:1122`-`:1128`); upstream marks this argument as required |
| Workshop addon **title** (GMod's dynamic IDs) | ❌ | `nil, nil` — this engine has no search path that addresses by addon title (`:1148`-`:1157`) |
| any other string | ❌ | `nil, nil` (pathID names themselves are **case-insensitive**, `:650` uses `V_stricmp`) |

## 5. Differences from GMod / gotchas {#5-与-gmod-的差异-注意}

| Difference | Detail | Source |
|---|---|---|
| the meaning of `MOD` | GMod's `MOD` is "the garrysmod folder, **not including addons**"; this fork mounts addons into the mod tree, so `MOD` here **includes addons** | `:624`-`:626` |
| `GAME` and `MOD` are searched as a pair | Looking up `"GAME"` also searches `"MOD"` and vice versa, then de-duplicates; GMod is strict for each ID | `:1136`-`:1145` |
| the per-realm `lua/` is not separate | GMod's `lcl` / `lsv` / `LuaMenu` are three different trees; here there is only one `lua/` tree, and the four spellings are equivalent | `:629`-`:633` |
| `THIRDPARTY` / `WORKSHOP` are approximate | Both point at `addons/`; `.gma` files are mounted directly under `hl2sb/addons/` | `:636`-`:640` |
| addon titles cannot be used | See the last two rows of §4. Note that bindings like `file.Exists` degrade to "search all paths" on an unknown ID, whereas **`file.Find` does not** — it honestly returns `nil, nil` | `:1148`-`:1157` vs `:687`-`:695` |
| `sorting` is more lenient | Upstream only documents `nameasc`/`namedesc`/`dateasc`/`datedesc`; here `size*` / `type*` / `ext*` are additionally accepted, and **an unknown value silently falls back to nameasc** (we have not verified the GMod side's behavior for unknown values) | `:1225`-`:1247` |
| only `*` is a wildcard | `?` does not count: `file.Find( "models/?.mdl", "GAME" )` is treated as the folder `models/?.mdl` and then gets `/*` appended, which amounts to finding nothing. `**` is not a recursive wildcard either — this binding only does single-level searches | `:1180`, `:1210` |
| case | sorting, de-duplication and pathID names all use `Q_stricmp` / `V_stricmp` (**insensitive**); name matching is left to the engine's `FindFirstFile` (insensitive on Windows). The upstream wiki's restriction that "`lua/MyFolder/*` does not work as expected on Linux" does not apply to this site's target platform (Windows) | `:1104`, `:1166`, `:650` |
| directory names have no trailing slash | Consistent with the upstream example, but contrary to the intuition that "directories all carry `/`", so it is easy to miss when building a path | `:1336` |
| size / time of duplicate entries | De-duplication happens **before** the requested sorting (names are sorted first so that identical names end up next to each other), and `CUtlVector::Sort` is not stable, so when the same name exists in both GAME and MOD, **which copy is kept is arbitrary** — hence under `sizeasc` / `dateasc` the position of that one name is decided by either copy's size/time | `:1297`-`:1314` |
| names under `data/` are lowercased | This is a write-side rule (`file.Write` / `file.Rename`); **`file.Find` itself does not fold case**, it returns the real names on disk | `:749`-`:754` |

⚠️ **Do not mistake the `file.Find` in the compatibility layer for the actual behavior**:
`lua/includes/modules/gmod_compatibility/sh_file.lua:34` has another Lua wrapper that **discards the
`sorting` argument** and prints
`file.Find Sorting is not supported in the GMod compatibility layer!`.
But it is a port from Experiment: Source and is shut out by `GMOD_COMPATIBILITY = false`
(`lua/includes/modules/gmod_compatibility.lua:30`-`:34`), so it is **not loaded by default** —
what actually takes effect is the engine binding of §1, and `sorting` is valid.

## 6. Related pages {#6-相关页面}

* [GMod Lua compatibility layer](gmod_compat_layer.html) — the three layers: engine bindings / Lua
  extensions / original GMod files, and where `file.*` sits in the compatibility layer.
* [Derma basic guide](derma_basic_guide.html) — verified in-game notes on writing GMod-style UI in
  HL2SB (the same troubleshooting method also applies to file enumeration).
* [GMod Lua port plan and status](gmod_lua_port_plan.html) — the overall gap table and per-item status.
* Upstream: [file.Find](https://wiki.facepunch.com/gmod/file.Find) ·
  [file](https://wiki.facepunch.com/gmod/file) ·
  [File Search Paths](https://wiki.facepunch.com/gmod/File_Search_Paths).
