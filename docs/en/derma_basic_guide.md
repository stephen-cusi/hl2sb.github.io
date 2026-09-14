# HL2SB Derma Basic Guide

> The HL2SB version, written against the [GMod Derma Basic Guide](https://wiki.facepunch.com/gmod/Derma_Basic_Guide).
> Anything that is the same is not explained again; **the things that differ, this fork's gotchas, and the "why"** are all marked with ⚠️.
> Every single item in this article has been verified in this repo (engine source location / console output / screenshot).

---

## 0. Runtime environment (the first thing that is different from GMod) {#0-运行环境和-gmod-不一样的第一件事}

In GMod you type `lua_run` in the console, or drop a file into `lua/autorun/`. The HL2SB commands are:

| Command | Effect | Note |
|---|---|---|
| `lua_run_cl <one line of code>` | Executes a snippet of Lua on the client | **The argument is everything else on the line**, so one command can only hold one statement; join several statements on one line with `;` |
| `lua_dofile <file>` / `lua_dofile_cl <file>` | Executes a server / client Lua file | The path is **relative to the `lua/` root**, **must include `.lua`**, and **must not have a `lua/` prefix** |
| `lua_dostring_cl <string>` | Same as `lua_run_cl` | — |

⚠️ **Do not paste several lines of commands at once**: the console will treat the following lines as arguments of the first command.
Counter-example (a real error):
```
lua_dofile_cl skins/hl2sb_default.lualua_run_cl for k,p in pairs(vgui.GetAll()) do ...
[Lua] FAILED ...\lua\skins\hl2sb_default.lualua_run_cl for k,...: No such file or directory
```
The correct way is one command per line:
```
lua_dofile_cl skins/hl2sb_default.lua
lua_dofile_cl hl2sb_test_window.lua
```

⚠️ Before you have entered a map, `lua_run_cl` reports `Lua is not initialized yet (enter a map first)`.

---

## 1. The first window (the original text of section 1 of the GMod guide, verified to work as-is in HL2SB) {#1-第一个窗口gmod-指南第-1-节的原文在-hl2sb-里已验证可直接用}

```lua
local Frame = vgui.Create( "DFrame" )
Frame:SetPos( 5, 5 )
Frame:SetSize( 300, 150 )
Frame:SetTitle( "Name window" )
Frame:SetVisible( true )
Frame:SetDraggable( false )
Frame:ShowCloseButton( true )
Frame:MakePopup()
```

How to run it from the console (pick one):
```
lua_run_cl local f=vgui.Create("DFrame") f:SetPos(5,5) f:SetSize(300,150) f:SetTitle("Name window") f:SetVisible(true) f:SetDraggable(false) f:ShowCloseButton(true) f:MakePopup()
```
Or write it into the file `lua/myframe.lua` and then `lua_dofile_cl myframe.lua`.

The binding locations in HL2SB for the 7 methods this code uses (all of them are there; whichever is missing reports `attempt to call a nil value (method 'x')`):

| Method | Binding location |
|---|---|
| `SetPos` / `SetSize` / `SetVisible` / `MakePopup` | `public/lua/vgui_controls/lPanel.cpp` |
| `SetTitle` | `game/client/lua/scripted_controls/lFrame.cpp` |
| `SetDraggable` / `IsDraggable` / `ShowCloseButton` | `lFrame.cpp` (aliases on the engine `Frame` metatable: → `SetMoveable` / `IsMoveable` / `SetCloseButtonVisible`) |

---

## 2. ⚠️ HL2SB's DFrame is a "pure Lua control", not the engine's C Frame {#2-hl2sb-的-dframe-是纯-lua-控件不是引擎的-c-frame}

GMod's `DFrame` is based on the engine's `EditablePanel`/`Frame`; **HL2SB's `DFrame` is written entirely in Lua** (`lua/vgui/DFrame.lua`, and the comment at the top of the file literally says "Built on the scripted Panel rather than the engine's C Frame"), because this fork's `LFrame` has no Lua dispatch for `ApplySchemeSettings`, and the close button is held by C++.

This brings three consequences you must remember:

1. **chrome (title bar / buttons / dragging) all lives in `lua/vgui/DFrame.lua`**:
   `Init` creates `m_pCloseButton` / `m_pMinimizeButton` / `m_pMaximizeButton` / `m_pBody`,
   `PerformLayout` lays out the three buttons from right to left, `Paint` goes through the skin's `Frame` / `FrameTitle`.
   Want to change the window's appearance → change this file + the skin, **do not** go and change the engine `Frame`.
2. **Methods on the engine `Frame` metatable have no effect on DFrame** (it goes through the Panel metatable). So GMod methods like
   `SetDraggable` / `ShowCloseButton` **each have their own Lua implementation** in `DFrame.lua`.
3. **Content must be placed in the client area**: `DFrame:GetClientArea()` returns `0, 24, w, h-24`, and a child panel's `y` must start at **24** (the title bar height):
   ```lua
   local pnl = vgui.Create( "DPanel", Frame )
   pnl:SetPos( 0, 24 )
   pnl:SetSize( Frame:GetWide(), Frame:GetTall() - 24 )
   ```

### DFrame existing API {#dframe-现有-api}

| Method | Description |
|---|---|
| `SetTitle` / `GetTitle` | Title |
| `GetClientArea` | Content area `0, 24, w, h-24` |
| `SetDraggable(b)` / `IsDraggable()` | Whether the title bar can be dragged (GMod defaults to **draggable**) |
| `ShowCloseButton(b)` / `IsCloseButtonVisible()` | `✕` |
| `SetMinimizeButtonVisible(b)` / `SetMaximizeButtonVisible(b)` / `IsMinimizeButtonVisible()` / `IsMaximizeButtonVisible()` | **Hidden** by default (same as GMod); must be turned on explicitly |
| `Minimize()` / `Restore()` / `Maximize()` / `IsMaximized()` | The behavior of `—` / `□` / `❐` |
| `SetSizable` / `SetDeleteOnClose` / `SetTitleBarVisible` / `SetMinimizeButtonVisible`… | Other chrome methods commonly used by guides/plugins |
| `Close()` | Hide + optional `Remove()`, dispatches `self.OnClose` |
| `ShowMinimizeButton` / `ShowMaximizeButton` | GMod 12 old spelling, kept |

---

## 3. ⚠️ The `Paint` override gotcha (verified in this repo) {#3-覆盖-paint-的坑本仓库实测}

After you override `Paint` on a **container-class** panel (`DFrame`, `DPanel`), its **child panels are not drawn at all**:

```lua
-- verified in-game: written this way, the frame's own red rectangle is drawn, but body/label/button/title-bar buttons are not drawn at all
Frame.Paint = function( s, w, h )
    surface.DrawSetColor( 255, 0, 0, 255 )
    surface.DrawOutlinedRect( 0, 0, w, h )
end
```
Control experiment (not overriding `Paint`, only attaching child panels) → the orange block, the green block, the button and the title-bar buttons are **all normal**.

**Conclusion / usage**:
- To draw decorations on a container, **prefer not to override `Paint`**; draw with a **child panel**, or change the skin's `SKIN:Paint*` hooks;
- If you absolutely must override it, remember that it eats the entire subtree — right now this is a relationship problem between the engine-side `LPanel::Paint` (`game/client/lua/scripted_controls/lPanel.cpp:88`) and child panel traversal, not yet fixed.

---

## 4. Fonts: ⚠️ Do not shadow the fonts in the scheme (the full version of the Marlett lesson) {#4-字体-不要遮蔽-scheme-里的字体marlett-那一课的完整版}

The three buttons in the top-right corner of the window, `—` `□` `✕`, use the **Marlett** font (GMod's default skin is the same), and the glyphs are:
`r` = close, `0` = minimize, `1` = maximize, `2` = restore.

In HL2SB **`resource/clientscheme.res` already defines it**, and with the symbol charset:
```
"Marlett" { "1" { "name" "Marlett"  "tall" "14"  "weight" "0"  "symbol" "1" } }
```
The font file is there as well: `resource/marlett.ttf`.

⚠️ **Never ever** write `surface.CreateFont( "Marlett", { … } )` again — the resolution order of `surface.SetFont(name)` is
**"Lua-registered fonts → scheme fonts"**, and the copy you create yourself will **override** the good one in the scheme; once it fails to resolve,
the engine **silently falls back to Verdana**, and the icons on screen turn into the letters `0 1 r` (this repo has stepped on this; it is already fixed).

The correct usage (this is what the skin does right now):
```lua
local font = "Marlett"           -- use the name from the scheme directly
derma.DrawText( font, x, y, "r", Color( 230, 230, 230, 255 ) )
```

Engine-side supporting hardening (`public/lua/vgui/LISurface.cpp`, already compiled and deployed):
when `surface.CreateFont` fails it no longer silently swaps the font — it first retries once without antialiasing / with `weight 400`,
and only if that still fails does it `Warning` and name it (font name, size, weight), so you can see it straight in the log.

Other font conventions:
- Skin/scheme fonts: `DermaDefault`, `DermaDefaultBold`, `DermaLarge` (created in `lua/includes/modules/gmod_vgui.lua` following GMod's `derma/init.lua`);
- Custom fonts: `surface.CreateFont( name, fontData )`, where `fontData` uses the GMod fields (`font`/`size`/`weight`/`antialias`/`extended`/`shadow`/…); `extended` is a no-op in this engine (`0,0` is the correct one, see `AGENTS.md` §5.4);
- To get a handle **by name**: `surface.SetFont(name)` / `draw.GetFont(name)`; `surface.GetTextSize( name, text )` (this repo's implementation wants the two parameters `(font, text)`).

---

## 5. Skin system {#5-皮肤skin系统}

- Skin file: `lua/skins/hl2sb_default.lua`, registered with `derma.DefineSkin( "HL2SBDefault", "...", SKIN )`;
- Hook function name = `"Paint" .. Hook`: `PaintFrame` / `PaintFrameTitle` / `PaintCloseButton` / `PaintMinimizeButton` / `PaintMaximizeButton` / `PaintSlider` / …
- Calling from a panel: `derma.SkinHook( "Paint", "Frame", self, w, h )`
- Colors are gathered in the table at the top of that file (`FrameTitle`, `FrameTitleIdle`, `Background`, `Text`…); change the palette there.
  The current `FrameTitle = Color( 37, 101, 166 )` (blue); to match GMod's default skin gray, just change this one line.
- ⚠️ **`derma.RefreshSkins()` is not implemented in this repo** (only `DefineSkin` / `SkinHook` / `SetSkin`).
  After changing the skin, to make **new windows** see the effect: `lua_dofile_cl skins/hl2sb_default.lua`, then `Remove()` the old window and `vgui.Create` again.

---

## 6. Common controls quick reference (the 22 registered in this repo) {#6-常用控件速查本仓库已注册的-22-个}

```
DPanel  DLabel  DButton  DImageButton  DTextEntry  DCheckBox
DScrollBar  DScrollPanel  DScroller  DSlider  DNumSlider
DFrame  DListView  DListView_Line  DMenu  DMenuBar  DTooltip
DCollapsibleCategory  DCategoryList  DPropertySheet  DNotify  NoticePanel
```

Minimal example (verified to display in this repo):

```lua
-- console: lua_dofile_cl mypanel.lua
local f = vgui.Create( "DFrame" )
f:SetPos( 60, 60 ) f:SetSize( 350, 220 ) f:SetTitle( "Test panel" )
f:ShowCloseButton( true )
f:SetMinimizeButtonVisible( true )
f:SetMaximizeButtonVisible( true )
f:MakePopup()

-- content goes in the client area (y starts at 24)
local body = vgui.Create( "DPanel", f )
body:SetPos( 0, 24 ) body:SetSize( 350, 196 )

local lbl = vgui.Create( "DLabel", f )
lbl:SetPos( 10, 30 ) lbl:SetText( "hello derma" ) lbl:SizeToContents()

local btn = vgui.Create( "DButton", f )
btn:SetText( "Click me I'm pretty!" )
btn:SetPos( 100, 100 ) btn:SetSize( 150, 30 )
btn.DoClick = function() print( "clicked" ) end
```

![HL2SB verified in-game: a Test panel with only the window created and the body area still empty](../../assets/img/derma/test-panel-empty.png)

*Figure 1: what it looks like when the code above only runs as far as `f:MakePopup()` — blue title bar, the three Marlett glyph buttons `—` `□` `✕`, and an empty body area (literally "first the window, then the content").*

![HL2SB verified in-game: the complete Test panel after adding a label, a panel and a button](../../assets/img/derma/test-panel-example.png)

*Figure 2: after body / label / button have also been added (the complete minimal example) — the green label, the orange panel, and the "Click me I'm pretty!" button below; a first-person in-game capture.*

Panel lifecycle (same names as GMod, all dispatched in this repo):

| Hook | When | Typical use |
|---|---|---|
| `PANEL:Init()` | On `vgui.Create` | Create child controls, set the default size |
| `panel.Paint( w, h )` | Every frame | Self-drawing (⚠️ see section 3) |
| `panel:PerformLayout( w, h )` | On size change | Position child controls |
| `panel:Think()` | Every frame | Logic (panels that need a tick must register a tick signal, see `AGENTS.md` §5.1) |
| `panel:OnMousePressed/Released`, `OnCursorMoved` | Mouse | Custom dragging (this is how `DFrame` implements it) |
| `DoClick` / `OnValueChanged` / `OnChange` / `OnValueChange` / `OnCheckButtonChecked` / `OnTextChanged` | Interaction | Callbacks (`SetChecked` also fires `OnCheckButtonChecked`) |
| `panel:Remove()`, `OnClose` | Close | Cleanup |

---

## 7. Debugging practice (this repo's rules) {#7-排查手法本仓库的规矩}

| Symptom | Where to look first |
|---|---|
| `attempt to call a nil value (method 'X')` | That method is not bound → decide whether this control is an **engine class** or a **pure Lua control** (`lua/vgui/*.lua`): for Lua controls add it in `lua/vgui/`, for engine classes add it in `lPanel.cpp` / `lFrame.cpp` / `lButton.cpp` … |
| The panel is created but not displayed | Print the panel tree: `p:GetClassName() / GetPos / GetSize / IsVisible / GetParent` (this is exactly what `lua/hl2sb_test_window.lua` does in this repo); then tell apart "not created", "created but not painted", "eaten by the parent panel's Paint" (section 3) |
| Icons/text turn into other glyphs | The font is shadowed or fell back (section 4); look in the log for `surface.CreateFont( ... ) did not resolve` |
| The skin was changed but has no effect | `derma.RefreshSkins` does not exist; recreate the window (section 5) |
| The panel does not receive mouse input | See `AGENTS.md` §5.0 "the whole Lua panel subtree does not receive mouse input" |
| Lua errors but does not crash | Many hooks are **deregistered** by `hook.lua` when they error; after fixing, re-enter the map / restart (`AGENTS.md` §5.4) |

Engine command / log locations: `D:\srceng\hl2sb\ds_debug.log`, crash dumps `D:\srceng\hl2sb\dumps\`.

---

## 8. Known differences / not implemented (relative to GMod) {#8-已知差异-未实现相对-gmod}

| Item | Status |
|---|---|
| `derma.RefreshSkins()` | ❌ Not implemented |
| Child panels are not drawn after overriding a container's `Paint` | ⚠️ Known issue (section 3), not fixed |
| `DFrame` based on the engine Frame | ❌ This fork is a pure Lua implementation (section 2); child panels must work out the 24px themselves |
| The `Entity` global | ❌ Not present in this repo (GMod's `gmod_compatibility/sh_init.lua` is not loaded either) |
| `surface.DrawSetTextureFile` parameters 3/4 | ⚠️ This repo's binding wants a `number`, GMod passes a boolean (`lua/vgui/DImageButton.lua:26` reports `bad argument #3 ... (number expected, got boolean)`), **to be fixed** |
| `derma.RefreshSkins`, the `extended` of `surface.CreateFont` | See above |

---

## 9. One-page cheat sheet {#9-一页速记}

```lua
-- 1) window: create → size/position → title → three buttons → MakePopup
local f = vgui.Create( "DFrame" )
f:SetPos( 60, 60 ); f:SetSize( 350, 220 ); f:SetTitle( "Test panel" )
f:ShowCloseButton( true ); f:SetMinimizeButtonVisible( true ); f:SetMaximizeButtonVisible( true )
f:MakePopup()

-- 2) content: y coordinates start at 24 (title bar); do not override Paint on f
local body = vgui.Create( "DPanel", f ); body:SetPos( 0, 24 ); body:SetSize( 350, 196 )

-- 3) fonts: use scheme font names (DermaDefault / DermaDefaultBold / DermaLarge / Marlett), don't CreateFont the same name yourself
derma.DrawText( "DermaDefaultBold", 8, 4, "hi", Color( 235, 235, 235 ) )
```

How to run:
```
lua_dofile_cl myframe.lua
```
