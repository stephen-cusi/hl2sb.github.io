---
title: CreateSound / CSoundPatch
---

# CreateSound / CSoundPatch

`CreateSound` **binds a piece of sound to an entity** and hands you back an object you can play, change the
volume of, change the pitch of, and fade out. In GMod its return value is
[CSoundPatch](https://wiki.facepunch.com/gmod/CSoundPatch) (the engine's looping sound object, on which `C_BaseEntity::EmitSound` and all ambient looping sounds are built).

> **HL2SB status: ✅ implemented (engine-side C++ binding, client + server).**
> Entry point: `game/shared/lua/lutil_shared.cpp:999` (`luasrc_CreateSound`), registered as the global `CreateSound`
> at `:1075`-`:1076`. This same copy is compiled into **both client.dll and server.dll**
> (`game/client/client_lua.vpc:90`, `game/server/server_lua.vpc:61`);
> the `CreateSound` string can be found in the deployed `client.dll` / `server.dll`.
>
> **The return value differs from GMod**: what is returned here is an **ordinary Lua table (channel object)**,
> not a `CSoundPatch` userdata; internally, however, it is driven by a **real `CSoundEnvelopeController` + `CSoundPatch`**
> (`:659`-`:674`, `:794`-`:796`), and the method set is the **union** of GMod's
> `CSoundPatch` and `IGModAudioChannel` (`:1031`-`:1058`).
> The differences are listed item by item in §5.

## 1. Signature and arguments {#1-签名与参数}

```text
table channel = CreateSound( Entity targetEnt, string soundName )
```

| # | Argument | Type | Description |
|---|---|---|---|
| 1 | `targetEnt` | `Entity` | The entity the sound is attached to (it decides the sound source position and the lifetime). Read with `lua_toentity` (`:1000`); **passing a non-entity yields `nil`** |
| 2 | `soundName` | `string` | A sound path or soundscript name, for example `"weapons/nyan/nyan_loop.wav"` (`:1001`) |

Upstream GMod's signature has one more argument:

```text
CSoundPatch CreateSound( Entity targetEnt, string soundName, CRecipientFilter filter = nil )
```

⚠️ **HL2SB does not read the third argument** (`luasrc_CreateSound` only takes the first two, `:1000`-`:1001`).
The filter is a `CPASAttenuationFilter( pEntity, pszSound )` that the binding builds itself when binding (`:789`);
on the client it additionally adds `UsePredictionRules()` (`:790`-`:792`) — so the thing called "play it only to
certain players" is **impossible** in HL2SB (that GMod argument was only ever effective on the server anyway).

## 2. Return value and lifetime {#2-返回值与生命周期}

| Case | Return |
|---|---|
| The entity is null, or the sound name is an empty string | `nil` (`:1003`-`:1006`) |
| Normal | a table (the channel object), with the fields below |

The internal fields on the channel object (`__hl2sb_*`, `:676`-`:682`): `__hl2sb_ent` (entity), `__hl2sb_sound` (name),
`__hl2sb_volume` (the remembered volume, default 1), `__hl2sb_channel` (the channel, always `CHAN_STATIC`, `:1019`),
`__hl2sb_playing`, `__hl2sb_paused`, `__hl2sb_patch` (**light userdata**, created lazily).

There are four key points to the lifetime:

* **The engine object is only created on the first `Play()`** (`:742`-`:802`): `CreateSound` itself only builds
  the table, so "created but never played" does not occupy a sound channel.
* Before creating the patch, the server **does one extra precache** (`:781`-`:787`) —
  the engine's `SV_StartSound` rejects waves that have not been precached (the
  `SV_StartSound: ... not precached` in the log is exactly that).
* `Stop()` / `Pause()` **`SoundDestroy()` the real patch** (`:815`) —
  this is the only way to actually stop a looping sound; the next `Play()` creates a new one.
* ⚠️ **Once the owner entity is gone, that patch must not be touched again**: the engine's controller removes
  a patch whose entity is already gone from the update table (`game/shared/soundenvelope.cpp:500`-`:513`), but
  **does not free** it. Therefore, when the entity is null, the binding **just forgets the pointer** (and prints
  a one-time warning) and never dereferences it (`:742`-`:763`, `:810`-`:829`) — this is protection against use-after-free, not "unimplemented".

## 3. Methods {#3-方法}

GMod's `CSoundPatch` methods ([upstream list](https://wiki.facepunch.com/gmod/CSoundPatch)) and how they map here:

| GMod method | HL2SB | Behavior / source |
|---|---|---|
| `Play()` | ✅ | `controller.Play( patch, volume, PITCH_NORM )` (`:840`). ⚠️ **returns a boolean** (whether a patch was created); GMod's returns nil |
| `Stop()` | ✅ | `SoundDestroy()` + clear playing (`:848`-`:853`) |
| `ChangeVolume( volume, deltaTime = 0 )` | ✅ | a real **ramp**: `SoundChangeVolume( patch, v, t )` (`:879`-`:890`) |
| `ChangePitch( pitch, deltaTime = 0 )` | ✅ | `SoundChangePitch( patch, p, t )` (`:916`-`:926`) |
| `FadeOut( seconds = 0.5 )` | ⚠️ | lowers the volume to 0 within `seconds` (`:929`-`:942`), **but does not destroy the patch**: `IsPlaying()` is still true, and you have to `Stop()` yourself. Also the default is 0.5 (GMod's seconds argument is required) |
| `GetPitch()` | ✅ | `SoundGetPitch()`; returns `PITCH_NORM` when there is no patch (`:972`-`:983`) |
| `GetVolume()` | ⚠️ | returns the **remembered** volume (the value of the last `SetVolume`/`ChangeVolume`/`FadeOut`, default 1), not the engine's current volume (`:966`-`:970`) |
| `IsPlaying()` | ✅ | the remembered playing flag; always false once the entity is gone (`:903`-`:913`) |
| `GetDSP()` / `SetDSP()` | ❌ | not bound |
| `GetSoundLevel()` / `SetSoundLevel()` | ❌ | not bound (creation always uses `SNDLVL_NORM`, `:796`) |
| `GetSoundName()` | ❌ | not bound (the name is in the `__hl2sb_sound` field, but it is not public API) |
| `PlayEx( volume, pitch )` | ❌ | not bound; the equivalent is `SetVolume`/`SetPitch` first and then `Play()` |

Besides that there is another batch of **IGModAudioChannel family** methods (GMod's `CSoundPatch` does not have
them, but the return value of `sound.PlayFile` does, and addons mix the two):

| Method | Behavior / source |
|---|---|
| `Pause()` | same as `Stop()` but remembers paused (`:855`-`:860`) |
| `SetVolume( v )` | changes the volume immediately (equivalent to `ChangeVolume( v, 0 )`, `:862`-`:872`) |
| `SetPitch( p )` | changes the pitch immediately (equivalent to `ChangePitch( p, 0 )`, `:892`-`:901`) |
| `IsPaused()` / `IsFinished()` / `IsValid()` | see `:945`-`:964`: `IsFinished` = the entity still exists and it is neither playing nor paused |
| `Is3D()` → false, `GetTime()` / `GetState()` / `GetPlaybackRate()` → 0 | placeholders (`:994`-`:997`, `:1046`-`:1049`) |
| `SetTime` / `SetPlaybackRate` / `EnableLooping` / `Set3DPosition` / `SetPos` | **accepted but does nothing** (`:1053`-`:1057`); whether it loops is decided by the wave itself, and seeking / 3D positioning is not implemented |

## 4. Example {#4-示例}

**Example 1: looping sound + crossfade (how Nyan Gun uses it)**

```lua
-- The client holds the channel; ramping the volume from 0 to 1 is a ramp, not a hard cut
local channel = CreateSound( LocalPlayer(), "weapons/nyan/nyan_loop.wav" )

print( channel ~= nil )       -- a valid entity and name give you an object
print( channel:IsValid() )    -- the owner entity is still there
print( channel:IsPlaying() )  -- not played yet
print( channel:Is3D() )       -- placeholder implementation, always false

if ( channel ) then
	channel:SetVolume( 0 )
	channel:Play()
	print( channel:IsPlaying() )   -- after Play
	print( channel:GetVolume() )   -- the remembered volume (just set to 0)

	channel:ChangeVolume( 1, 0.2 ) -- a 0.2 second ramp
	print( channel:GetVolume() )

	channel:FadeOut( 0.4 )         -- ramps to 0 but does **not** destroy the patch
	print( channel:GetVolume() )
	print( channel:IsPlaying() )   -- ⚠️ still true, which is why Stop() is needed below

	channel:Stop()                 -- really stop it (destroys the patch)
	print( channel:IsPlaying() )
end
```

**Output:**
```text
true
true
false
false
true
0
1
0
true
false
```

**Example 2: one-shot sound effect (stops once it has finished playing)**

```lua
local channel = CreateSound( ent, "phx/hmetal1.wav" )

print( channel ~= nil )        -- it was created
print( channel:IsFinished() )  -- ⚠️ true: it already counts as "finished" before Play
channel:Play()
print( channel:IsPlaying() )   -- true
channel:Stop()
print( channel:IsPlaying() )   -- false
```

**Output:**
```text
true
true
true
false
```

**Example 3: created on the server, sounding from the entity's position**

```lua
-- Server side: the wave has to be precached first; the binding does one for you (lutil_shared.cpp:781-787)
local channel = CreateSound( self, "ambient/machines/machine_loop1.wav" )

print( channel ~= nil )    -- the server can create one too (client.dll and server.dll both build this binding)
if ( channel ) then
	channel:Play()
end
```

**Output:**
```text
true
```

## 5. Differences from GMod / cautions {#5-与-gmod-的差异-注意}

| Difference | Detail | Source |
|---|---|---|
| The return value is not a `CSoundPatch` | it is an ordinary table; no metatable, no `Type()` name. **Do not use type checks other than `IsValid()` on it, or `debug.getmetatable`** | `:1008`-`:1030` |
| Method set | the union of `CSoundPatch` ∩ `IGModAudioChannel`: it has the extra `Pause`/`SetVolume`/`SetPitch`/`IsPaused`/`IsFinished`/`IsValid`, and lacks `GetDSP`/`SetDSP`/`GetSoundLevel`/`SetSoundLevel`/`GetSoundName`/`PlayEx` | `:1031`-`:1058` |
| the `filter` argument is ignored | you cannot play to only some players; both sides use `CPASAttenuationFilter` | `:789` |
| the channel is fixed at `CHAN_STATIC` | you cannot choose `CHAN_VOICE` etc.; at any one moment the same wave can have only one patch **on the same entity** (an engine limitation, the same in GMod) | `:1019`, `:794` |
| `FadeOut` does not end the sound | it only lowers it to 0; `IsPlaying()` is still true, `GetVolume()` becomes 0 | `:929`-`:942` |
| `GetVolume` is "the remembered value" | not the engine's live volume; if nothing was set after `Play()` it is 1 | `:966`-`:970` |
| `Play()` returns a boolean | GMod returns nil; testing `if ( ch:Play() )` **works** in this fork (but do not write that into an addon as GMod behavior) | `:844` |
| sample rate | the same as GMod: only 11025 / 22050 / 44100 Hz are supported, otherwise the engine reports `Invalid sample rate` (a limitation of the upstream documentation) | upstream wiki |

## 6. Related pages {#6-相关页面}

* [Material / CreateMaterial](material.html) — another "get an engine object" entry point, with a very similar shape of pitfalls (the return value differs from GMod).
* [IMaterial](imaterial.html) — the material object itself.
* [GMod Lua compatibility layer](gmod_compat_layer.html) — where this kind of binding sits in the compatibility layer.
* Upstream: [CreateSound](https://wiki.facepunch.com/gmod/Global.CreateSound) ·
  [CSoundPatch](https://wiki.facepunch.com/gmod/CSoundPatch) ·
  [`CSoundPatch`'s engine implementation (soundenvelope)](https://github.com/pmrowla/hl2sdk-csgo/blob/master/game/shared/soundenvelope.cpp).
