# hl2sb.github.io

**HL2SB 文档站** —— 把项目里的 wiki 文档预渲染成一个静态站点，用 GitHub Pages 发布。

* 站点在线地址（当前账号）：<https://stephen-cusi.github.io/hl2sb.github.io/>
* 如果把仓库转到 `hl2sb` 组织，则地址变成 <https://hl2sb.github.io/>
  （站内全部链接都是相对路径，**两种地址都能用，不需要改任何东西**）

## 这个仓库里有什么

```
docs/                 文档的 Markdown 源文件 —— 唯一的事实来源
  index.md              Wiki 目录
  derma_basic_guide.md  Derma 基础指南（来自 hl2sb 游戏内容仓库 lua/docs/）
  gmod_lua_port_plan.md GMod Lua 移植计划与状态（同上）
  gmod_compat_layer.md  GMod Lua 兼容层说明
  build_and_run.md      构建与运行
  about.md              关于 / 版权
assets/               手写 CSS、原生 JS、SVG favicon（无 CDN、无外部字体）
  img/                  文档里的截图（构建时整棵树原样复制到 dist/assets/img/）
tools/build.py        静态生成器（纯 Python 标准库，零依赖）
tools/verify.py       站点自检（链接、渲染、外部依赖、HTTP 200）
dist/                 生成结果（构建产物，可直接用任意静态服务器预览）
.github/workflows/pages.yml   推送到 main 时构建并发布到 GitHub Pages
```

## 本地构建与预览

需要 Python 3.9+，不需要任何第三方包。

```powershell
python tools/build.py                       # docs/ -> dist/
python tools/verify.py                      # 自检（会自己起一个临时 http.server）
python -m http.server 8080 --directory dist # 手动预览 http://127.0.0.1:8080/
```

只想改样式：编辑 `assets/style.css`；改导航/首页：编辑 `tools/build.py` 里的 `PAGES` 与
`HOME_TMPL`；改内容：编辑 `docs/*.md`，然后重新 `python tools/build.py`。

## 加一篇新文档

1. 把 `.md` 放进 `docs/`（可以带 `--- title: 标题 ---` frontmatter）；
2. 在 `tools/build.py` 的 `PAGES` 里加一条（`src` / `out` / `group` / `text` / `desc`）；
3. 重新构建：`python tools/build.py`；
4. 需要的话，在 `.github/workflows/pages.yml` 之外不用做任何事 —— CI 会在推送后自动重建。

## 约定

* **`docs/` 下的 Markdown 是唯一事实来源**，HTML 是生成物，不要手改 `dist/`。
* 站内链接一律**相对路径**，这样仓库名/组织名怎么变都不影响。
* **截图/图片**：文件放进 `assets/img/`（按主题分子目录，例如
  `assets/img/derma/`，全小写、连字符），Markdown 里用

  ```markdown
  ![一句说明](../assets/img/derma/test-panel-example.png)

  *图注：读者应该看到什么。*
  ```

  写 `../assets/img/...` 而不是 `assets/img/...`：这条相对路径**相对生成后的
  `docs/*.html`**（页面在 `docs/` 下一层，所以要多一个 `../`），同时也正好相对
  `docs/` 在 GitHub 上的位置 —— 于是「站点页面」和「GitHub 上看 Markdown」两种
  场景都能直接显示；`tools/build.py` 会把 `assets/` 整棵树复制到 `dist/assets/`，
  `tools/verify.py` 与 `tools/preview_check.py` 会检查文件存在、是合法 PNG、有 alt
  文本、并且在子路径部署下 HTTP 200。图注写成图片下面**单独一段的 `*斜体*`**，
  样式由 `assets/style.css` 里的 `.doc img` / `.doc p > em:only-child` 负责。
* 不引入 CDN、外部字体或前端框架（保持离线可用、体积小）。
* 文档内容与上游仓库保持同步：`docs/derma_basic_guide.md`、`docs/gmod_lua_port_plan.md`
  是从 hl2sb 游戏内容仓库复制过来的，更新时请原样覆盖。

## 许可

文档内容与引擎代码同受 Source SDK 2013 的非商业许可约束；
Half-Life / Source / Steam 是 Valve 的商标，Garry's Mod 属于 Facepunch Studios。
详见站点上的「关于 / 版权」页与 [LICENSE-NOTICE.md](LICENSE-NOTICE.md)。
