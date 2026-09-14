/* HL2SB 文档站前端脚本 —— 无依赖，所有路径都是相对的（任意 base path 可用）。
   功能：主题切换（默认深色）、移动端侧栏抽屉、Ctrl+K / 斜杠 搜索、锚点、代码复制、
   截图点击放大（自己实现的极简 lightbox，不引入任何外部库）。 */
(function () {
  "use strict";

  var doc = document;
  var root = doc.documentElement;

  /* ---------------- 主题 ---------------- */
  function currentTheme() {
    var t = root.getAttribute("data-theme");
    if (t === "dark" || t === "light") return t;
    // 默认深色（GMod wiki 的侧栏/顶栏风格）；没有存过偏好时跟随系统只在系统为浅色时用浅色
    try {
      if (window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches) {
        return "light";
      }
    } catch (e) {}
    return "dark";
  }

  function applyTheme(t) {
    root.setAttribute("data-theme", t);
    try { localStorage.setItem("hl2sb-theme", t); } catch (e) {}
    var btn = doc.querySelector(".theme-toggle .theme-icon");
    if (btn) btn.textContent = t === "dark" ? "☾" : "☀";
  }

  applyTheme(currentTheme());

  doc.addEventListener("click", function (ev) {
    var t = ev.target.closest ? ev.target.closest(".theme-toggle") : null;
    if (t) {
      applyTheme(currentTheme() === "dark" ? "light" : "dark");
      return;
    }
    var n = ev.target.closest ? ev.target.closest(".nav-toggle") : null;
    if (n) {
      var open = doc.body.classList.toggle("nav-open");
      n.setAttribute("aria-expanded", open ? "true" : "false");
      return;
    }
    // 点击遮罩关闭抽屉
    if (doc.body.classList.contains("nav-open") && !ev.target.closest(".sidebar") &&
        !ev.target.closest(".nav-toggle")) {
      doc.body.classList.remove("nav-open");
    }
  });

  doc.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape") {
      doc.body.classList.remove("nav-open");
      closeLightbox();
    }
  });

  /* ---------------- 截图点击放大 / lightbox ----------------
     上游 GMod wiki 的示例图不可点击；这里按常见文档站的做法补一个极简放大层：
     纯 DOM + CSS，没有任何依赖，图片本身仍是同一个相对路径的 PNG。 */
  var lb = null;

  function ensureLightbox() {
    if (lb) return lb;
    lb = doc.createElement("div");
    lb.className = "lightbox";
    lb.hidden = true;
    lb.setAttribute("role", "dialog");
    lb.setAttribute("aria-modal", "true");
    lb.setAttribute("aria-label", "放大的截图（点击或按 Esc 关闭）");
    var big = doc.createElement("img");
    big.alt = "";
    var cap = doc.createElement("div");
    cap.className = "lb-caption";
    lb.appendChild(big);
    lb.appendChild(cap);
    lb.addEventListener("click", function () { closeLightbox(); });
    doc.body.appendChild(lb);
    return lb;
  }

  function openLightbox(img) {
    var box = ensureLightbox();
    var big = box.querySelector("img");
    var cap = box.querySelector(".lb-caption");
    var alt = img.getAttribute("alt") || "";
    big.src = img.getAttribute("src");
    big.alt = alt;
    // 示例截图是按游戏像素 1:1 裁出来的（比如 386x256），直接 1:1 放到大屏上
    // 并不算「放大」；这里按视口算一个不超过 2 倍的缩放，保证看得清又不糊成一团。
    var nw = img.naturalWidth || 0;
    var nh = img.naturalHeight || 0;
    if (nw && nh) {
      var scale = Math.min(
        (window.innerWidth * 0.96) / nw,
        (window.innerHeight - 76) / nh,
        2);
      big.style.width = Math.round(nw * scale) + "px";
      big.style.height = Math.round(nh * scale) + "px";
    } else {
      big.style.width = "";
      big.style.height = "";
    }
    cap.textContent = alt;
    box.hidden = false;
    doc.body.style.overflow = "hidden";
  }

  function closeLightbox() {
    if (!lb || lb.hidden) return;
    lb.hidden = true;
    lb.querySelector("img").removeAttribute("src");
    doc.body.style.overflow = "";
  }

  (function initLightbox() {
    var imgs = doc.querySelectorAll(".doc img, .prose img");
    Array.prototype.forEach.call(imgs, function (img) {
      img.setAttribute("tabindex", "0");
      img.setAttribute("role", "button");
      img.setAttribute("aria-label", "放大截图：" + (img.getAttribute("alt") || ""));
      img.addEventListener("click", function () { openLightbox(img); });
      img.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter" || ev.key === " " || ev.key === "Spacebar") {
          ev.preventDefault();
          openLightbox(img);
        }
      });
    });
  })();

  /* ---------------- 代码块复制 ---------------- */
  doc.addEventListener("click", function (ev) {
    var btn = ev.target.closest ? ev.target.closest(".copy-btn") : null;
    if (!btn) return;
    var box = btn.closest(".codeblock");
    var code = box ? box.querySelector("pre code") : null;
    if (!code) return;
    var text = code.innerText;
    var done = function () {
      var old = btn.textContent;
      btn.textContent = "已复制";
      setTimeout(function () { btn.textContent = old; }, 1200);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, function () { fallback(text, done); });
    } else {
      fallback(text, done);
    }
  });

  function fallback(text, done) {
    try {
      var ta = doc.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      doc.body.appendChild(ta);
      ta.select();
      doc.execCommand("copy");
      doc.body.removeChild(ta);
      done();
    } catch (e) {}
  }

  /* ---------------- 搜索 ---------------- */
  var overlay = doc.getElementById("searchOverlay");
  var input = doc.getElementById("searchInput");
  var results = doc.getElementById("searchResults");
  var sideInput = doc.getElementById("sideSearch");
  var index = null;
  var loading = false;
  var hits = [];
  var sel = 0;

  /* 站点根前缀。模板里这个脚本是用 `$$ROOT$$assets/app.js` 加载的（根目录页面是
     `assets/app.js`，`docs/` 下的页面是 `../assets/app.js`），所以从自己这个 <script>
     的 src 就能算出「相对于当前页面的站点根」，再拼索引路径与结果链接。

     ⚠️ 不要改回按页面相对的写死路径：`docs/*.html` 里的 `assets/search-index.json`
     会解析成 `docs/assets/search-index.json`（构建产物里没有这个目录 → 404），
     索引加载失败后 index 变成空数组，搜索在任何文档页上都只会显示「没有匹配的页面」；
     同理结果链接 `e.url` 是 `docs/xxx.html`，不拼前缀会变成 `docs/docs/xxx.html`。 */
  var SITE_ROOT = (function () {
    var el = doc.currentScript;
    if (!el) {
      var list = doc.getElementsByTagName("script");
      for (var i = 0; i < list.length; i++) {
        var s = list[i].getAttribute("src") || "";
        if (/(^|\/)assets\/app\.js(\?|$)/.test(s)) { el = list[i]; break; }
      }
    }
    var src = (el && el.getAttribute("src")) || "assets/app.js";
    return src.replace(/assets\/app\.js(\?.*)?$/, "");
  })();

  function loadIndex(cb) {
    if (index) { cb(); return; }
    if (loading) return;
    loading = true;
    var req = new XMLHttpRequest();
    req.open("GET", SITE_ROOT + "assets/search-index.json", true);
    req.onload = function () {
      loading = false;
      try { index = JSON.parse(req.responseText); } catch (e) { index = []; }
      cb();
    };
    req.onerror = function () {
      loading = false;
      index = [];
      cb();
    };
    req.send();
  }

  function openSearch(seed) {
    if (!overlay) return;
    overlay.hidden = false;
    if (seed && input) { input.value = seed; }
    loadIndex(function () {
      if (input) { input.focus(); input.select(); }
      run();
    });
  }

  function closeSearch() {
    if (overlay) overlay.hidden = true;
  }

  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function mark(snippet, terms) {
    var safe = esc(snippet);
    terms.forEach(function (t) {
      if (t.length < 1) return;
      try {
        safe = safe.replace(new RegExp("(" + t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")", "gi"),
                            "<mark>$1</mark>");
      } catch (e) {}
    });
    return safe;
  }

  function snippet(text, terms, q) {
    var lower = text.toLowerCase();
    var at = lower.indexOf(q);
    if (at < 0) at = 0;
    var start = Math.max(0, at - 60);
    var out = (start > 0 ? "…" : "") + text.slice(start, start + 190) + (text.length > start + 190 ? "…" : "");
    return out;
  }

  function score(entry, terms, q) {
    var s = 0;
    var title = (entry.title || "").toLowerCase();
    var heads = (entry.headings || []).join(" ").toLowerCase();
    var text = (entry.text || "").toLowerCase();
    if (title.indexOf(q) >= 0) s += 100;
    terms.forEach(function (t) {
      if (title.indexOf(t) >= 0) s += 40;
      if (heads.indexOf(t) >= 0) s += 12;
      var n = text.split(t).length - 1;
      s += Math.min(n, 12) * 2;
    });
    return s;
  }

  function run() {
    if (!results) return;
    var q = (input && input.value || "").trim().toLowerCase();
    if (!q) {
      results.innerHTML = '<p class="muted" style="padding:8px 12px">输入关键词开始搜索。</p>';
      hits = [];
      return;
    }
    if (index === null) {
      results.innerHTML = '<p class="muted" style="padding:8px 12px">正在加载索引…</p>';
      return;
    }
    var terms = q.split(/\s+/).filter(Boolean);
    var found = [];
    index.forEach(function (entry) {
      var sc = score(entry, terms, q);
      if (sc > 0) found.push({ e: entry, s: sc });
    });
    found.sort(function (a, b) { return b.s - a.s; });
    found = found.slice(0, 24);
    hits = found.map(function (h) { return h.e; });
    sel = 0;
    if (!found.length) {
      results.innerHTML = '<p class="muted" style="padding:8px 12px">没有匹配的页面。</p>';
      return;
    }
    var html = "";
    found.forEach(function (h, i) {
      var e = h.e;
      var extra = "";
      if (e.headings && e.headings.length) {
        var hitHead = e.headings.filter(function (x) {
          return terms.some(function (t) { return x.toLowerCase().indexOf(t) >= 0; });
        })[0];
        if (hitHead) extra = " › " + hitHead;
      }
      html += '<a class="hit' + (i === 0 ? " sel" : "") + '" href="' + esc(SITE_ROOT + e.url) + '">' +
              '<span class="hit-t">' + esc(e.title) + extra + "</span>" +
              '<span class="hit-g">' + esc(e.group || "") + "</span>" +
              '<span class="hit-s">' + mark(snippet(e.text || "", terms, q), terms) + "</span></a>";
    });
    results.innerHTML = html;
  }

  function move(d) {
    var nodes = results ? results.querySelectorAll(".hit") : [];
    if (!nodes.length) return;
    nodes[sel] && nodes[sel].classList.remove("sel");
    sel = (sel + d + nodes.length) % nodes.length;
    nodes[sel].classList.add("sel");
    nodes[sel].scrollIntoView({ block: "nearest" });
  }

  if (input) {
    input.addEventListener("input", run);
    input.addEventListener("keydown", function (ev) {
      if (ev.key === "ArrowDown") { ev.preventDefault(); move(1); }
      else if (ev.key === "ArrowUp") { ev.preventDefault(); move(-1); }
      else if (ev.key === "Enter") {
        var nodes = results ? results.querySelectorAll(".hit") : [];
        if (nodes[sel]) window.location.href = nodes[sel].getAttribute("href");
      } else if (ev.key === "Escape") { closeSearch(); }
    });
  }

  doc.addEventListener("click", function (ev) {
    if (ev.target.classList && ev.target.classList.contains("search-open")) {
      openSearch("");
      return;
    }
    if (ev.target === overlay) closeSearch();
  });

  if (sideInput) {
    sideInput.addEventListener("focus", function () { openSearch(sideInput.value || ""); });
    sideInput.addEventListener("keydown", function (ev) {
      if (ev.key === "Enter") { ev.preventDefault(); openSearch(sideInput.value || ""); }
    });
  }

  doc.addEventListener("keydown", function (ev) {
    var typing = /^(INPUT|TEXTAREA|SELECT)$/.test((ev.target.tagName || "").toUpperCase());
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "k") {
      ev.preventDefault();
      openSearch("");
      return;
    }
    if (ev.key === "/" && !typing) {
      ev.preventDefault();
      openSearch("");
    }
  });
})();
