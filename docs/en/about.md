---
title: About / Copyright
---

# About / Copyright

## What is HL2SB {#hl2sb-是什么}

**HL2SB (Half-Life 2: Sandbox)** is a Source engine fork whose goal is to let **Garry's Mod's Lua
run on the Source SDK 2013 engine as-is** — Derma panels, Spawnmenu, Lua SWEPs, killicons,
and the GMod-style content pipeline, keeping GMod scripts unchanged line for line wherever possible.

It is based on nillerusr's source-engine (the community port fork of Source SDK 2013),
plus HL2SB's own engine changes and GMod compatibility layer.

## Repositories {#仓库}

| Repo | Contents |
|---|---|
| [source-engine-mod](https://github.com/stephen-cusi/source-engine-mod) | Engine source (C++). Working branch `lua_playermodel_menu` |
| [hl2sb-gamefile](https://github.com/stephen-cusi/hl2sb-gamefile) | Game content: `cfg` / `resource` / `lua` / `materials` (text) / `gamemodes` / `gameinfo.txt`. Only editable text assets are included |
| [hl2sb.github.io](https://github.com/stephen-cusi/hl2sb.github.io) | This site: the docs' Markdown source files + the static generator |

## How this site is built {#本站怎么构建}

* All documentation is in the repo as **Markdown files** under `docs/`; they are the single source of truth;
* `tools/build.py` (pure Python standard library, zero dependencies) **pre-renders** them into static HTML in `dist/`;
* All in-site links and assets are **relative paths**, so the site works whether it is hosted at `https://<user>.github.io/hl2sb.github.io/`
  or `https://hl2sb.github.io/`;
* No CDN, no external fonts, no frontend framework — just hand-written CSS and a small piece of vanilla JavaScript.

Local preview:

```powershell
python tools/build.py                     # generate dist/
python -m http.server 8080 --directory dist
```

## License and Credits {#许可与致谢}

* **Source SDK 2013 / Source engine code**: under Valve's Source SDK license, **non-commercial use only**.
  The content and source code on this site are subject to the same restriction.
* **Half-Life, Source, Steam** are trademarks of Valve Corporation;
  **Garry's Mod** and its Wiki content are the work of Facepunch Studios. This site's Derma and porting docs are
  cross-references to and supplements for the upstream documentation; the copyright of the original GMod files (`cl_deathnotice.lua`, Derma controls, skins, etc.)
  belongs to their authors.
* The engine fork comes from [nillerusr/source-engine](https://github.com/nillerusr/source-engine) (a Source SDK 2013 port).
* The docs' visual style is inspired by the [Garry's Mod Wiki](https://wiki.facepunch.com/gmod/).

If you have a copyright concern or need some content taken down, please open an issue in the repo.
