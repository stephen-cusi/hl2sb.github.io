---
title: CreateSound / CSoundPatch
---

# CreateSound / CSoundPatch

`CreateSound` 把一段声音**绑到一个实体上**并交给你一个可以播放、调音量、调音高、淡出的对象。
GMod 里它的返回值是 [CSoundPatch](https://wiki.facepunch.com/gmod/CSoundPatch)（引擎的循环声对象，
`C_BaseEntity::EmitSound` 和所有环境循环音都建立在它上面）。

> **HL2SB 状态：✅ 已实现（引擎侧 C++ 绑定，客户端 + 服务端）。**
> 入口：`game/shared/lua/lutil_shared.cpp:999`（`luasrc_CreateSound`），注册成全局 `CreateSound`
> 在 `:1075`-`:1076`。这一份同时编进 **client.dll 与 server.dll**
> （`game/client/client_lua.vpc:90`、`game/server/server_lua.vpc:61`），
> 部署的 `client.dll` / `server.dll` 里都能搜到 `CreateSound` 字符串。
>
> **返回值与 GMod 不同**：这里返回的是一个**普通 Lua table（通道对象）**，
> 不是 `CSoundPatch` 用户数据；但它内部由**真正的 `CSoundEnvelopeController` + `CSoundPatch`**
> 驱动（`:659`-`:674`、`:794`-`:796`），方法集是 GMod 的
> `CSoundPatch` 与 `IGModAudioChannel` 的**并集**（`:1031`-`:1058`）。
> 差异逐条列在 §5。

## 1. 签名与参数

```text
table channel = CreateSound( Entity targetEnt, string soundName )
```

| # | 参数 | 类型 | 说明 |
|---|---|---|---|
| 1 | `targetEnt` | `Entity` | 声音挂靠的实体（决定音源位置与生命周期）。用 `lua_toentity` 读（`:1000`），**传非实体得到 `nil`** |
| 2 | `soundName` | `string` | 声音路径或 soundscript 名字，例如 `"weapons/nyan/nyan_loop.wav"`（`:1001`） |

上游 GMod 的签名多一个参数：

```text
CSoundPatch CreateSound( Entity targetEnt, string soundName, CRecipientFilter filter = nil )
```

⚠️ **第三个参数 HL2SB 不读**（`luasrc_CreateSound` 只取前两个，`:1000`-`:1001`）。
过滤器是绑定时自己建的 `CPASAttenuationFilter( pEntity, pszSound )`（`:789`），
客户端额外加 `UsePredictionRules()`（`:790`-`:792`）—— 所以“只放给某些玩家”这件事
在 HL2SB 里**做不到**（GMod 那个参数本来也只在服务端有效）。

## 2. 返回值与生命周期

| 情况 | 返回 |
|---|---|
| 实体为空、或声音名字为空串 | `nil`（`:1003`-`:1006`） |
| 正常 | 一个 table（通道对象），字段见下 |

通道对象上的内部字段（`__hl2sb_*`，`:676`-`:682`）：`__hl2sb_ent`（实体）、`__hl2sb_sound`（名字）、
`__hl2sb_volume`（记住的音量，默认 1）、`__hl2sb_channel`（声道，恒为 `CHAN_STATIC`，`:1019`）、
`__hl2sb_playing`、`__hl2sb_paused`、`__hl2sb_patch`（**light userdata**，懒创建）。

生命周期有四条要点：

* **引擎对象是第一次 `Play()` 才建的**（`:742`-`:802`）：`CreateSound` 本身只造 table，
  所以“建了但没播”不占声音通道。
* 服务端在创建 patch 前会**补一次 precache**（`:781`-`:787`）——
  引擎的 `SV_StartSound` 拒绝没 precache 过的波形（日志里的
  `SV_StartSound: ... not precached` 就是它）。
* `Stop()` / `Pause()` 会 **`SoundDestroy()` 掉真正的 patch**（`:815`）——
  这是唯一能真正停掉循环音的方式；下一次 `Play()` 会重新建一个。
* ⚠️ **拥有者实体消失后不能再碰那个 patch**：引擎的控制器会把实体已消失的 patch
  从更新表里摘掉（`game/shared/soundenvelope.cpp:500`-`:513`），但**不释放**它。
  因此绑定在实体为空时会**只是忘掉指针**（并打一条一次性警告），绝不解引用
  （`:742`-`:763`、`:810`-`:829`）—— 这是防 use-after-free，不是“没实现”。

## 3. 方法

GMod 的 `CSoundPatch` 方法（[上游列表](https://wiki.facepunch.com/gmod/CSoundPatch)）在这里的对应情况：

| GMod 方法 | HL2SB | 行为 / 源码 |
|---|---|---|
| `Play()` | ✅ | `controller.Play( patch, 音量, PITCH_NORM )`（`:840`）。⚠️ **返回 boolean**（有没有建出 patch），GMod 的返回 nil |
| `Stop()` | ✅ | `SoundDestroy()` + 清 playing（`:848`-`:853`） |
| `ChangeVolume( volume, deltaTime = 0 )` | ✅ | 真正的**斜坡**：`SoundChangeVolume( patch, v, t )`（`:879`-`:890`） |
| `ChangePitch( pitch, deltaTime = 0 )` | ✅ | `SoundChangePitch( patch, p, t )`（`:916`-`:926`） |
| `FadeOut( seconds = 0.5 )` | ⚠️ | 把音量在 `seconds` 内降到 0（`:929`-`:942`），**但不销毁 patch**：`IsPlaying()` 仍是 true，需要自己再 `Stop()`。另外默认值是 0.5（GMod 的秒数是必填） |
| `GetPitch()` | ✅ | `SoundGetPitch()`；没有 patch 时返回 `PITCH_NORM`（`:972`-`:983`） |
| `GetVolume()` | ⚠️ | 返回**记住的**音量（最后一次 `SetVolume`/`ChangeVolume`/`FadeOut` 的值，默认 1），不是引擎当前的音量（`:966`-`:970`） |
| `IsPlaying()` | ✅ | 记住的 playing 标记；实体没了恒为 false（`:903`-`:913`） |
| `GetDSP()` / `SetDSP()` | ❌ | 未绑定 |
| `GetSoundLevel()` / `SetSoundLevel()` | ❌ | 未绑定（创建时固定用 `SNDLVL_NORM`，`:796`） |
| `GetSoundName()` | ❌ | 未绑定（名字在 `__hl2sb_sound` 字段里，但不是公开 API） |
| `PlayEx( volume, pitch )` | ❌ | 未绑定；等价写法是先 `SetVolume`/`SetPitch` 再 `Play()` |

另外还有一批 **IGModAudioChannel 家族**的方法（GMod 的 `CSoundPatch` 没有，但
`sound.PlayFile` 的返回值有，插件会混着用）：

| 方法 | 行为 / 源码 |
|---|---|
| `Pause()` | 同 `Stop()` 但记住 paused（`:855`-`:860`） |
| `SetVolume( v )` | 立刻改音量（等价 `ChangeVolume( v, 0 )`，`:862`-`:872`） |
| `SetPitch( p )` | 立刻改音高（等价 `ChangePitch( p, 0 )`，`:892`-`:901`） |
| `IsPaused()` / `IsFinished()` / `IsValid()` | 见 `:945`-`:964`：`IsFinished` = 实体还在且既没播也没暂停 |
| `Is3D()` → false、`GetTime()` / `GetState()` / `GetPlaybackRate()` → 0 | 占位（`:994`-`:997`、`:1046`-`:1049`） |
| `SetTime` / `SetPlaybackRate` / `EnableLooping` / `Set3DPosition` / `SetPos` | **接受但什么都不做**（`:1053`-`:1057`）；循环与否由波形自己决定，跳转/3D 摆位没有实现 |

## 4. 示例

**例 1：循环音 + 交叉淡入淡出（Nyan Gun 的用法）**

```lua
-- 客户端持有通道；音量从 0 拉到 1 是斜坡，不是硬切
local channel = CreateSound( LocalPlayer(), "weapons/nyan/nyan_loop.wav" )
if ( channel ) then
	channel:SetVolume( 0 )
	channel:Play()

	-- 开火：0.2 秒内淡入
	channel:ChangeVolume( 1, 0.2 )

	-- 松开：0.4 秒内淡出，然后真正停掉（FadeOut 不会销毁 patch）
	channel:FadeOut( 0.4 )
	timer.Simple( 0.4, function()
		if ( channel:IsValid() ) then channel:Stop() end
	end )
end
```

**例 2：一次性音效（播完即止）**

```lua
local channel = CreateSound( ent, "phx/hmetal1.wav" )
if ( channel ) then
	channel:Play()
	-- 播完判断：既没播也没暂停，而且实体还在
	if ( channel:IsFinished() ) then channel:Stop() end
end
```

**例 3：服务端创建、靠实体位置发声**

```lua
-- 服务端：波表要先 precache，绑定会替你补一次（lutil_shared.cpp:781-787）
local channel = CreateSound( self, "ambient/machines/machine_loop1.wav" )
if ( channel ) then
	channel:Play()
end
-- 实体没了（武器被丢/玩家离开）时不要再碰 channel：绑定会拒绝，引擎不回收那块内存
```

## 5. 与 GMod 的差异 / 注意

| 差异 | 细节 | 源码 |
|---|---|---|
| 返回值不是 `CSoundPatch` | 是普通 table；没有 metatable、没有 `Type()` 名字。**不要在它上面用 `IsValid()` 以外的类型判断或 `debug.getmetatable`** | `:1008`-`:1030` |
| 方法集 | `CSoundPatch` ∩ `IGModAudioChannel` 的并集：多出 `Pause`/`SetVolume`/`SetPitch`/`IsPaused`/`IsFinished`/`IsValid`，缺 `GetDSP`/`SetDSP`/`GetSoundLevel`/`SetSoundLevel`/`GetSoundName`/`PlayEx` | `:1031`-`:1058` |
| `filter` 参数被忽略 | 无法只放给某些玩家；两端都用 `CPASAttenuationFilter` | `:789` |
| 声道固定 `CHAN_STATIC` | 不能选 `CHAN_VOICE` 等；同一时刻同一波形在**同一实体**上只能有一个 patch（引擎限制，GMod 也一样） | `:1019`、`:794` |
| `FadeOut` 不结束声音 | 只降到 0；`IsPlaying()` 仍为 true，`GetVolume()` 变 0 | `:929`-`:942` |
| `GetVolume` 是“记住的值” | 不是引擎实时音量；`Play()` 之后没设过就是 1 | `:966`-`:970` |
| `Play()` 返回 boolean | GMod 返回 nil，判断 `if ( ch:Play() )` 在本 fork 里是**能用的**（但别把这条当 GMod 行为写进插件） | `:844` |
| 采样率 | 与 GMod 相同：只支持 11025 / 22050 / 44100 Hz，否则引擎报 `Invalid sample rate`（上游文档的限制） | 上游 wiki |

## 6. 相关页面

* [Material / CreateMaterial](material.html) —— 另一个“取引擎对象”的入口，坑的形状很像（返回值与 GMod 不同）。
* [IMaterial](imaterial.html) —— 材质对象本身。
* [GMod Lua 兼容层](gmod_compat_layer.html) —— 这类绑定在兼容层里的位置。
* 上游：[CreateSound](https://wiki.facepunch.com/gmod/Global.CreateSound) ·
  [CSoundPatch](https://wiki.facepunch.com/gmod/CSoundPatch) ·
  [`CSoundPatch` 的引擎实现（soundenvelope）](https://github.com/pmrowla/hl2sdk-csgo/blob/master/game/shared/soundenvelope.cpp)。
