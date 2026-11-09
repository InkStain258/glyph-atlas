/* 以形查字 · 拓片工作台
   纯前端形状反查：图像 → 二值掩膜 → 归一化 → 146B 指纹 → 与预建索引比对。
   指纹编码与 scripts/build_shape_index.py 逐位同构。 */
(function () {
  "use strict";

  var N = 64, INNER = 56, G = 16, STRIDE = 146, WORK = 400;
  var LAYERS = window.GA_LAYERS || [];
  var SHAPE_INDEX = window.GA_SHAPE_INDEX || [];
  var SAMPLES = window.GA_SHAPE_SAMPLES || [];
  var LAYER_BY_ID = {};
  LAYERS.forEach(function (l) { LAYER_BY_ID[l.id] = l; });

  var LS_KEY = "ga.shape.ledger.v1";
  var LS_CFG = "ga.shape.cfg.v1";

  var state = {
    thr: 128, inv: false, den: 1, wt: 0, rot: 0, trim: 0, wgt: 70,
    layers: ["seal", "oracle", "bronze"], num: 48, sort: "sim", view: "glyph",
    markfilter: "all", srcLabel: "—", srcChar: null,
    all: [], shown: [], sel: {}, drawerIdx: -1, busy: false
  };
  var loaded = {};      // lid -> {chars,grid,proj,aspect,ink,n,meta}
  var loading = {};     // lid -> Promise
  var cssLoaded = {};
  var metaLoaded = {};
  var ledger = [];
  var undoSnap = null;
  var sourceImg = null; // HTMLImageElement | HTMLCanvasElement
  var qd = null;        // 当前查询指纹
  var fpOverride = null; // 一次性：直接用索引指纹当查询（?ch= 入口）
  var strokes = [];     // 手绘笔画
  var drawing = false, curStroke = null;

  var $ = function (id) { return document.getElementById(id); };
  var clamp = function (v, a, b) { return v < a ? a : v > b ? b : v; };

  /* ================= 工具 ================= */
  function toast(msg, kind, actionLabel, action) {
    var t = document.createElement("div");
    t.className = "toast" + (kind ? " " + kind : "");
    var s = document.createElement("span"); s.textContent = msg; t.appendChild(s);
    if (actionLabel) {
      var b = document.createElement("button"); b.textContent = actionLabel;
      b.onclick = function () { action(); t.remove(); };
      t.appendChild(b);
    }
    $("toasts").appendChild(t);
    setTimeout(function () {
      t.style.transition = "opacity .3s,transform .3s";
      t.style.opacity = "0"; t.style.transform = "translateY(10px)";
      setTimeout(function () { t.remove(); }, 320);
    }, actionLabel ? 6200 : 2800);
  }
  function setStatus(s) { $("navstat").textContent = s; }
  function prog(p) {
    var el = $("prog");
    if (p == null) { el.classList.remove("show"); return; }
    el.classList.add("show"); el.firstChild.style.width = (p * 100).toFixed(1) + "%";
  }
  function cp(ch) {
    var c = ch.codePointAt(0);
    return "U+" + c.toString(16).toUpperCase();
  }
  function eraOf(lid) {
    var l = LAYER_BY_ID[lid] || {};
    return l.era_short || l.era || (SHAPE_INDEX.filter(function (x) { return x.id === lid; })[0] || {}).name || "—";
  }
  function nameOf(lid) {
    var l = LAYER_BY_ID[lid];
    if (l && l.name_zh) return l.name_zh;
    var s = SHAPE_INDEX.filter(function (x) { return x.id === lid; })[0];
    return s ? s.name : lid;
  }
  function markOf(ch, lid) {
    for (var i = 0; i < ledger.length; i++)
      if (ledger[i].ch === ch && ledger[i].lid === lid) return ledger[i];
    return null;
  }
  function saveLedger() {
    try { localStorage.setItem(LS_KEY, JSON.stringify(ledger)); } catch (e) {}
    renderLedger();
  }
  function saveCfg() {
    try {
      localStorage.setItem(LS_CFG, JSON.stringify({
        thr: state.thr, inv: state.inv, den: state.den, wt: state.wt, rot: state.rot,
        trim: state.trim, wgt: state.wgt, layers: state.layers, num: state.num,
        sort: state.sort, view: state.view
      }));
    } catch (e) {}
  }

  /* ================= 图层加载 ================= */
  function ensureCss(lid) {
    if (cssLoaded[lid]) return;
    cssLoaded[lid] = true;
    var l = document.createElement("link");
    l.rel = "stylesheet"; l.href = "css/" + lid + ".css";
    document.head.appendChild(l);
  }
  function ensureMeta(lid) {
    if (metaLoaded[lid]) return metaLoaded[lid];
    var l = LAYER_BY_ID[lid] || {};
    if (l.kind !== "glyph-svg") { metaLoaded[lid] = Promise.resolve(null); return metaLoaded[lid]; }
    metaLoaded[lid] = new Promise(function (res) {
      var s = document.createElement("script");
      s.src = "data/meta/" + lid + ".js";
      s.onload = function () { res((window.GA_META || {})[lid] || null); };
      s.onerror = function () { res(null); };
      document.head.appendChild(s);
    });
    return metaLoaded[lid];
  }
  function loadLayer(lid) {
    if (loaded[lid]) return Promise.resolve(loaded[lid]);
    if (loading[lid]) return loading[lid];
    ensureCss(lid);
    loading[lid] = new Promise(function (res, rej) {
      var s = document.createElement("script");
      s.src = "data/shape/" + lid + ".js";
      s.onload = function () {
        var p = (window.GA_SHAPE || {})[lid];
        if (!p) { rej(new Error("no payload " + lid)); return; }
        try { loaded[lid] = decode(p); res(loaded[lid]); }
        catch (e) { rej(e); }
      };
      s.onerror = function () { rej(new Error("load fail " + lid)); };
      document.head.appendChild(s);
    });
    return loading[lid];
  }
  function decode(p) {
    var bin = atob(p.b64), raw = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) raw[i] = bin.charCodeAt(i);
    var n = p.n, S = p.stride || STRIDE;
    var grid = new Uint8Array(n * 256), proj = new Uint8Array(n * 32);
    var aspect = new Uint8Array(n), ink = new Uint8Array(n);
    for (var i = 0; i < n; i++) {
      var o = i * S, gb = i * 256, pb = i * 32, j, b;
      for (j = 0; j < 128; j++) { b = raw[o + j]; grid[gb + j * 2] = b >> 4; grid[gb + j * 2 + 1] = b & 15; }
      for (j = 0; j < 8; j++) { b = raw[o + 128 + j]; proj[pb + j * 2] = b >> 4; proj[pb + j * 2 + 1] = b & 15; }
      for (j = 0; j < 8; j++) { b = raw[o + 136 + j]; proj[pb + 16 + j * 2] = b >> 4; proj[pb + 16 + j * 2 + 1] = b & 15; }
      aspect[i] = raw[o + 144]; ink[i] = raw[o + 145];
    }
    var chars = Array.from(p.chars);
    if (chars.length !== n) chars = chars.slice(0, n);
    return { id: p.id, n: n, chars: chars, grid: grid, proj: proj, aspect: aspect, ink: ink, meta: p };
  }
  function ensureLayers() {
    var want = state.layers.slice();
    var total = want.length, done = 0;
    prog(0.02);
    return Promise.all(want.map(function (lid) {
      return loadLayer(lid).then(function (r) {
        done++; prog(0.02 + 0.5 * done / Math.max(1, total)); return r;
      }).catch(function (e) {
        toast("圖層 " + nameOf(lid) + " 載入失敗", "err");
        state.layers = state.layers.filter(function (x) { return x !== lid; });
        renderLayerChips(); return null;
      });
    }));
  }

  /* ================= 图像处理 ================= */
  function toWork(src) {
    var w = src.naturalWidth || src.width, h = src.naturalHeight || src.height;
    var s = Math.min(1, WORK / Math.max(w, h));
    var c = document.createElement("canvas");
    c.width = Math.max(8, Math.round(w * s)); c.height = Math.max(8, Math.round(h * s));
    var x = c.getContext("2d", { willReadFrequently: true });
    x.fillStyle = "#000"; x.fillRect(0, 0, c.width, c.height);
    x.drawImage(src, 0, 0, c.width, c.height);
    return c;
  }
  function binarize(canvas) {
    var W = canvas.width, H = canvas.height;
    var d = canvas.getContext("2d", { willReadFrequently: true }).getImageData(0, 0, W, H).data;
    var m = new Uint8Array(W * H), border = 0, bn = 0;
    for (var y = 0; y < H; y++) for (var x = 0; x < W; x++) {
      var i = y * W + x, o = i * 4;
      var lum = 0.299 * d[o] + 0.587 * d[o + 1] + 0.114 * d[o + 2];
      m[i] = (state.inv ? lum < state.thr : lum > state.thr) ? 1 : 0;
      if (x < 3 || y < 3 || x >= W - 3 || y >= H - 3) { border += lum; bn++; }
    }
    return { m: m, W: W, H: H, borderLum: bn ? border / bn : 0 };
  }
  function morph(src, W, H, dilate) {
    var tmp = new Uint8Array(W * H), out = new Uint8Array(W * H), x, y, k, v, s, xx, yy;
    for (y = 0; y < H; y++) for (x = 0; x < W; x++) {
      v = dilate ? 0 : 1;
      for (k = -1; k <= 1; k++) {
        xx = x + k; s = (xx < 0 || xx >= W) ? 0 : src[y * W + xx];
        v = dilate ? (v | s) : (v & s);
      }
      tmp[y * W + x] = v;
    }
    for (y = 0; y < H; y++) for (x = 0; x < W; x++) {
      v = dilate ? 0 : 1;
      for (k = -1; k <= 1; k++) {
        yy = y + k; s = (yy < 0 || yy >= H) ? 0 : tmp[yy * W + x];
        v = dilate ? (v | s) : (v & s);
      }
      out[y * W + x] = v;
    }
    return out;
  }
  function maskToCanvas(m, W, H) {
    var c = document.createElement("canvas"); c.width = W; c.height = H;
    var x = c.getContext("2d"), im = x.createImageData(W, H), d = im.data;
    for (var i = 0; i < m.length; i++) {
      var o = i * 4, v = m[i] ? 255 : 0;
      d[o] = d[o + 1] = d[o + 2] = 255; d[o + 3] = v;
    }
    x.putImageData(im, 0, 0);
    return c;
  }
  function rotateCanvas(c, deg) {
    if (!deg) return c;
    var W = c.width, H = c.height;
    var o = document.createElement("canvas"); o.width = W; o.height = H;
    var x = o.getContext("2d", { willReadFrequently: true });
    x.translate(W / 2, H / 2); x.rotate(deg * Math.PI / 180);
    x.drawImage(c, -W / 2, -H / 2);
    return o;
  }
  function canvasToMask(c) {
    var W = c.width, H = c.height;
    var d = c.getContext("2d", { willReadFrequently: true }).getImageData(0, 0, W, H).data;
    var m = new Uint8Array(W * H);
    for (var i = 0; i < m.length; i++) m[i] = d[i * 4 + 3] > 127 ? 1 : 0;
    return { m: m, W: W, H: H };
  }
  function bbox(m, W, H) {
    var x0 = W, y0 = H, x1 = -1, y1 = -1;
    for (var y = 0; y < H; y++) for (var x = 0; x < W; x++) if (m[y * W + x]) {
      if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y;
    }
    return x1 < 0 ? null : { x0: x0, y0: y0, x1: x1, y1: y1, w: x1 - x0 + 1, h: y1 - y0 + 1 };
  }
  /* 与 Python 的 round()/np.rint() 一致：四舍六入五取偶 */
  function rint(v) {
    var f = Math.floor(v), d = v - f;
    if (d > 0.5) return f + 1;
    if (d < 0.5) return f;
    return (f & 1) ? f + 1 : f;
  }
  /* 面积平均缩放，逐位等价于 PIL 的 Image.BOX。
     不能用 canvas 的 drawImage 平滑：Chrome 的高质量缩小不是盒式滤波，
     会让指纹与离线指引起系统性偏差（实测同一个字相似度从 98% 掉到 88%）。 */
  function boxResize(src, sw, sh, dw, dh) {
    var out = new Uint8Array(dw * dh), xs = sw / dw, ys = sh / dh;
    for (var dy = 0; dy < dh; dy++) {
      var y0 = dy * ys, y1 = (dy + 1) * ys;
      var iy0 = Math.floor(y0), iy1 = Math.min(sh, Math.ceil(y1));
      for (var dx = 0; dx < dw; dx++) {
        var x0 = dx * xs, x1 = (dx + 1) * xs;
        var ix0 = Math.floor(x0), ix1 = Math.min(sw, Math.ceil(x1));
        var sum = 0, wsum = 0;
        for (var yy = iy0; yy < iy1; yy++) {
          var wy = Math.min(y1, yy + 1) - Math.max(y0, yy);
          if (wy <= 0) continue;
          for (var xx = ix0; xx < ix1; xx++) {
            var wx = Math.min(x1, xx + 1) - Math.max(x0, xx);
            if (wx <= 0) continue;
            var w = wx * wy;
            sum += src[yy * sw + xx] * w; wsum += w;
          }
        }
        out[dy * dw + dx] = wsum ? rint(sum / wsum) : 0;
      }
    }
    return out;
  }
  function normalizeMask(m, W, H, bb) {
    var s = INNER / Math.max(bb.w, bb.h);
    var tw = Math.max(1, rint(bb.w * s)), th = Math.max(1, rint(bb.h * s));
    var crop = new Uint8Array(bb.w * bb.h);
    for (var y = 0; y < bb.h; y++) for (var x = 0; x < bb.w; x++)
      crop[y * bb.w + x] = m[(bb.y0 + y) * W + bb.x0 + x] ? 255 : 0;
    var small = boxResize(crop, bb.w, bb.h, tw, th);
    var a = new Uint8Array(N * N);
    var ox = Math.floor((N - tw) / 2), oy = Math.floor((N - th) / 2);
    for (var j = 0; j < th; j++) for (var i2 = 0; i2 < tw; i2++)
      a[(oy + j) * N + ox + i2] = small[j * tw + i2];
    return a;
  }
  function encode(alpha, w, h) {
    var q = new Uint8Array(256), gy, gx, y, x, s;
    for (gy = 0; gy < G; gy++) for (gx = 0; gx < G; gx++) {
      s = 0;
      for (y = 0; y < 4; y++) for (x = 0; x < 4; x++) s += alpha[(gy * 4 + y) * N + (gx * 4 + x)];
      q[gy * G + gx] = clamp(rint(s / 16 / 255 * 15), 0, 15);
    }
    var rows = new Float32Array(G), cols = new Float32Array(G), rmax = 0, cmax = 0, i;
    for (gy = 0; gy < G; gy++) for (gx = 0; gx < G; gx++) {
      rows[gy] += q[gy * G + gx]; cols[gx] += q[gy * G + gx];
    }
    for (i = 0; i < G; i++) { if (rows[i] > rmax) rmax = rows[i]; if (cols[i] > cmax) cmax = cols[i]; }
    var proj = new Uint8Array(32);
    for (i = 0; i < G; i++) {
      proj[i] = clamp(rint((rmax ? rows[i] / rmax : 0) * 15), 0, 15);
      proj[16 + i] = clamp(rint((cmax ? cols[i] / cmax : 0) * 15), 0, 15);
    }
    var ar = clamp(w / h, 0.25, 4);
    var aspect = rint((ar - 0.25) / 3.75 * 255);
    var inkc = 0; for (i = 0; i < alpha.length; i++) if (alpha[i] > 127) inkc++;
    return { grid: q, proj: proj, aspect: aspect, ink: rint(inkc / alpha.length * 255), ar: ar, alpha: alpha };
  }

  function process() {
    if (!sourceImg) return null;
    var wc = toWork(sourceImg);
    var b = binarize(wc), m = b.m, W = b.W, H = b.H, i;
    for (i = 0; i < state.den; i++) { m = morph(m, W, H, false); m = morph(m, W, H, true); }
    if (state.wt > 0) for (i = 0; i < state.wt; i++) m = morph(m, W, H, true);
    else if (state.wt < 0) for (i = 0; i < -state.wt; i++) m = morph(m, W, H, false);
    var mc = maskToCanvas(m, W, H);
    if (state.rot) { mc = rotateCanvas(mc, state.rot); var r = canvasToMask(mc); m = r.m; W = r.W; H = r.H; }
    var bb = bbox(m, W, H);
    if (!bb) return null;
    if (state.trim > 0) {
      var t = state.trim / 100, dx = Math.round(bb.w * t), dy = Math.round(bb.h * t);
      var nm = new Uint8Array(W * H);
      for (var y = bb.y0 + dy; y <= bb.y1 - dy; y++)
        for (var x = bb.x0 + dx; x <= bb.x1 - dx; x++) nm[y * W + x] = m[y * W + x];
      m = nm; bb = bbox(m, W, H);
      if (!bb) return null;
    }
    var alpha = normalizeMask(m, W, H, bb);
    var d = encode(alpha, bb.w, bb.h);
    d.mask = m; d.W = W; d.H = H; d.bb = bb; d.borderLum = b.borderLum;
    return d;
  }

  /* 回归自检用：暴露当前查询指纹与某层某字的索引指纹 */
  window.GA_SHAPE_DEBUG = function (lid, ch) {
    var o = { q: qd ? { aspect: qd.aspect, ink: qd.ink, ar: qd.ar, bb: qd.bb, W: qd.W, H: qd.H,
      maskSum: (function () { var t = 0; for (var i = 0; i < qd.mask.length; i++) t += qd.mask[i]; return t; })(),
      alphaSum: (function () { var t = 0; for (var i = 0; i < qd.alpha.length; i++) t += qd.alpha[i]; return t; })(),
      grid: Array.prototype.slice.call(qd.grid), proj: Array.prototype.slice.call(qd.proj) } : null };
    if (lid && loaded[lid]) {
      var L = loaded[lid], i = L.chars.indexOf(ch);
      o.idx = i < 0 ? null : { i: i, aspect: L.aspect[i], ink: L.ink[i],
        grid: Array.prototype.slice.call(L.grid, i * 256, i * 256 + 64),
        proj: Array.prototype.slice.call(L.proj, i * 32, i * 32 + 32) };
    }
    return o;
  };

  /* ================= 检索 ================= */
  function search(q) {
    var w = state.wgt / 100, out = [], lids = state.layers;
    for (var li = 0; li < lids.length; li++) {
      var L = loaded[lids[li]]; if (!L) continue;
      var grid = L.grid, proj = L.proj, asp = L.aspect, chars = L.chars, n = L.n;
      for (var i = 0; i < n; i++) {
        var gb = i * 256, pb = i * 32, gd = 0, pd = 0, k, dv;
        for (k = 0; k < 256; k++) { dv = q.grid[k] - grid[gb + k]; gd += dv < 0 ? -dv : dv; }
        for (k = 0; k < 32; k++) { dv = q.proj[k] - proj[pb + k]; pd += dv < 0 ? -dv : dv; }
        gd /= 3840; pd /= 480;
        var ad = Math.abs(q.aspect - asp[i]) / 255;
        var sim = 1 - (w * gd + (1 - w) * pd + 0.10 * ad);
        if (sim < 0) sim = 0;
        out.push({ ch: chars[i], lid: L.id, i: i, sim: sim, g: 1 - gd, p: 1 - pd, a: 1 - ad });
      }
    }
    out.sort(function (a, b) { return b.sim - a.sim; });
    return out;
  }
  var GB1 = null, GB2 = null;
  function freqRank(ch) {
    if (GB1 === null) {
      GB1 = {}; GB2 = {};
      var m = (window.GA_IDS && window.GA_IDS.meta) || {};
      (m.gb1 || "").split("").forEach(function (c) { GB1[c] = 1; });
      (m.gb2 || "").split("").forEach(function (c) { GB2[c] = 1; });
    }
    return GB1[ch] ? 2 : GB2[ch] ? 1 : 0;
  }
  function applySort(arr) {
    var a = arr.slice();
    if (state.sort === "era") a.sort(function (x, y) {
      var ex = (LAYER_BY_ID[x.lid] || {}).era_order || 99, ey = (LAYER_BY_ID[y.lid] || {}).era_order || 99;
      return ex - ey || y.sim - x.sim;
    });
    else if (state.sort === "freq") a.sort(function (x, y) { return freqRank(y.ch) - freqRank(x.ch) || y.sim - x.sim; });
    else if (state.sort === "layer") a.sort(function (x, y) {
      return state.layers.indexOf(x.lid) - state.layers.indexOf(y.lid) || y.sim - x.sim;
    });
    return a;
  }
  function applyFilter(arr) {
    if (state.markfilter === "all") return arr;
    return arr.filter(function (r) {
      var m = markOf(r.ch, r.lid);
      if (state.markfilter === "unmarked") return !m;
      return m && m.mark === state.markfilter;
    });
  }

  /* ================= 渲染 ================= */
  var RAMP = [[11, 10, 9], [40, 32, 26], [79, 184, 148], [232, 180, 76], [255, 95, 69], [244, 237, 224]];
  function rampColor(v) {
    var t = clamp(v / 15, 0, 1) * (RAMP.length - 1), i = Math.floor(t), f = t - i;
    var a = RAMP[i], b = RAMP[Math.min(RAMP.length - 1, i + 1)];
    return "rgb(" + Math.round(a[0] + (b[0] - a[0]) * f) + "," + Math.round(a[1] + (b[1] - a[1]) * f) + "," + Math.round(a[2] + (b[2] - a[2]) * f) + ")";
  }
  function drawFP(cv, grid) {
    var x = cv.getContext("2d"), S = cv.width / G;
    x.clearRect(0, 0, cv.width, cv.height);
    x.fillStyle = "#0a0908"; x.fillRect(0, 0, cv.width, cv.height);
    for (var gy = 0; gy < G; gy++) for (var gx = 0; gx < G; gx++) {
      var v = grid[gy * G + gx];
      if (!v) continue;
      x.fillStyle = rampColor(v);
      x.fillRect(gx * S, gy * S, Math.ceil(S), Math.ceil(S));
    }
  }
  function drawMaskPreview(d) {
    var cv = $("cvmask"), x = cv.getContext("2d");
    x.fillStyle = "#000"; x.fillRect(0, 0, cv.width, cv.height);
    if (!d) { $("pvmask").textContent = "—"; return; }
    var c = maskToCanvas(d.mask, d.W, d.H);
    var s = Math.min(cv.width / d.W, cv.height / d.H);
    var w = d.W * s, h = d.H * s;
    x.drawImage(c, (cv.width - w) / 2, (cv.height - h) / 2, w, h);
    x.strokeStyle = "rgba(217,58,43,.85)"; x.lineWidth = 1;
    var bb = d.bb;
    x.strokeRect((cv.width - w) / 2 + bb.x0 * s, (cv.height - h) / 2 + bb.y0 * s, bb.w * s, bb.h * s);
    var cnt = 0; for (var i = 0; i < d.mask.length; i++) cnt += d.mask[i];
    $("pvmask").textContent = d.W + "×" + d.H;
    $("stpx").textContent = cnt > 9999 ? (cnt / 1000).toFixed(1) + "k" : cnt;
  }
  function renderPreview() {
    var t0 = performance.now();
    /* fpOverride：从字形查询页带字过来时，直接用索引里的原始指纹，
       避免「指纹→画布→再二值化」的二次量化损失（自比对因此是 100%）。
       一次性：任何控件改动后的下一次 run 都会回到正常处理链。 */
    if (fpOverride) { qd = fpOverride; fpOverride = null; }
    else qd = process();
    drawMaskPreview(qd);
    if (qd) {
      drawFP($("cvfp"), qd.grid);
      $("pvfp").textContent = "16×16";
      $("stink").textContent = (qd.ink / 255 * 100).toFixed(1);
      $("star").textContent = qd.ar.toFixed(2);
    } else {
      var x = $("cvfp").getContext("2d"); x.fillStyle = "#0a0908"; x.fillRect(0, 0, 128, 128);
      $("pvfp").textContent = "無墨"; $("stink").textContent = "—"; $("star").textContent = "—"; $("stpx").textContent = "0";
    }
    return performance.now() - t0;
  }
  function simClass(s) { return s >= 0.9 ? "hi" : s >= 0.72 ? "mid" : "lo"; }

  function renderResults() {
    renderCfgFlag();
    var host = $("results");
    var pool = applyFilter(applySort(state.all));
    state.shown = pool.slice(0, state.num);
    $("rcount").textContent = pool.length.toLocaleString();
    $("rmeta").textContent = state.srcLabel + " · " + state.layers.map(nameOf).join("／") +
      (pool.length > state.num ? "（顯示前 " + state.num + "）" : "");
    host.innerHTML = "";
    if (!state.shown.length) {
      var e = document.createElement("div"); e.className = "empty";
      e.innerHTML = '<div class="big">空</div><p>' +
        (state.all.length ? "此篩選下沒有候選。" : "沒有得到指紋——掩膜裡沒有墨。") + "</p>" +
        "<small>" + (state.all.length ? "把「候選篩選」改回全部，或放寬檢索圖層。" :
          "試著調整二值化閾值、切換反相，或關掉去噪。") + "</small>";
      host.appendChild(e); return;
    }
    var frag = document.createDocumentFragment();
    state.shown.forEach(function (r, idx) {
      var mk = markOf(r.ch, r.lid);
      var d = document.createElement("div");
      d.className = "res" + (state.sel[r.ch + "|" + r.lid] ? " sel" : "") + (mk && mk.mark === "no" ? " excluded" : "");
      d.style.animationDelay = Math.min(idx * 11, 420) + "ms";
      var g = document.createElement("div"); g.className = "glyph";
      if (state.view === "fp") {
        var cv = document.createElement("canvas"); cv.width = 96; cv.height = 96;
        var L = loaded[r.lid];
        drawFP(cv, L.grid.subarray(r.i * 256, r.i * 256 + 256));
        g.appendChild(cv);
      } else {
        var sp = document.createElement("span"); sp.className = "ch";
        sp.style.fontFamily = '"' + r.lid + '", serif';
        sp.textContent = r.ch; g.appendChild(sp);
      }
      var rk = document.createElement("span"); rk.className = "rank"; rk.textContent = idx + 1; g.appendChild(rk);
      var sm = document.createElement("span"); sm.className = "sim " + simClass(r.sim);
      sm.textContent = (r.sim * 100).toFixed(0) + "%"; g.appendChild(sm);
      if (mk) { var mb = document.createElement("span"); mb.className = "mark " + mk.mark;
        mb.textContent = mk.mark === "yes" ? "已確認" : mk.mark === "maybe" ? "存疑" : "已排除"; g.appendChild(mb); }
      var pk = document.createElement("span"); pk.className = "pick"; pk.textContent = "✓";
      pk.title = "選取（批量標記）";
      pk.onclick = function (ev) { ev.stopPropagation(); toggleSel(r); };
      g.appendChild(pk);
      d.appendChild(g);
      var bar = document.createElement("div"); bar.className = "bar";
      var bi = document.createElement("i"); bi.style.width = (r.sim * 100).toFixed(1) + "%"; bar.appendChild(bi);
      d.appendChild(bar);
      var f = document.createElement("div"); f.className = "foot";
      f.innerHTML = '<span class="c"></span><span class="lay"></span>';
      f.firstChild.textContent = r.ch;
      f.lastChild.textContent = nameOf(r.lid);
      d.appendChild(f);
      d.onclick = function () { openDrawer(idx); };
      frag.appendChild(d);
    });
    host.appendChild(frag);
    updateSelUI();
  }
  function toggleSel(r) {
    var k = r.ch + "|" + r.lid;
    if (state.sel[k]) delete state.sel[k]; else state.sel[k] = r;
    renderResults();
  }
  function updateSelUI() {
    var n = Object.keys(state.sel).length;
    $("rsel").hidden = !n; $("rsel").textContent = "已選 " + n;
    $("bulkyes").disabled = !n; $("bulkno").disabled = !n;
  }

  var DEFAULTS = { thr: 128, inv: false, den: 1, wt: 0, rot: 0, trim: 0, wgt: 70 };
  function renderCfgFlag() {
    var off = [];
    if (state.thr !== DEFAULTS.thr) off.push("閾值");
    if (state.inv !== DEFAULTS.inv) off.push("反相");
    if (state.den !== DEFAULTS.den) off.push("去噪");
    if (state.wt !== DEFAULTS.wt) off.push("粗細");
    if (state.rot !== DEFAULTS.rot) off.push("旋轉");
    if (state.trim !== DEFAULTS.trim) off.push("裁邊");
    if (state.wgt !== DEFAULTS.wgt) off.push("權重");
    var e = $("cfgflag"); if (!e) return;
    e.textContent = off.length ? "已調：" + off.join("·") : "即時生效";
    e.className = off.length ? "hint off" : "hint";
    e.title = off.length ? "這些參數會記在本機，下次打開仍然生效。按「重設參數」回到預設。" : "";
  }

  function renderLayerChips() {
    var host = $("layers"); host.innerHTML = "";
    SHAPE_INDEX.forEach(function (s) {
      var b = document.createElement("button");
      b.className = "chip" + (state.layers.indexOf(s.id) >= 0 ? " on" : "") + (loading[s.id] && !loaded[s.id] ? " load" : "");
      b.innerHTML = '<span></span><i class="n"></i>';
      b.firstChild.textContent = s.name;
      b.lastChild.textContent = (s.n / 1000).toFixed(1) + "k";
      b.title = nameOf(s.id) + " · " + s.n.toLocaleString() + " 字形 · " + (s.bytes / 1048576).toFixed(2) + " MB";
      b.onclick = function () {
        var i = state.layers.indexOf(s.id);
        if (i >= 0) { if (state.layers.length === 1) { toast("至少保留一個圖層", "warn"); return; } state.layers.splice(i, 1); }
        else state.layers.push(s.id);
        $("vlay").textContent = state.layers.length;
        renderLayerChips(); saveCfg(); run();
      };
      host.appendChild(b);
    });
    $("vlay").textContent = state.layers.length;
  }

  function renderSamples() {
    var host = $("samples"); host.innerHTML = "";
    SAMPLES.forEach(function (s, i) {
      var b = document.createElement("button");
      b.className = "samp"; b.title = s.label + "（正確答案：" + s.char + "）";
      var im = document.createElement("img");
      im.src = "data:image/png;base64," + s.png; im.alt = s.label; im.loading = "lazy";
      b.appendChild(im);
      var cap = document.createElement("b"); cap.textContent = s.label; b.appendChild(cap);
      b.onclick = function () { useSample(i); };
      host.appendChild(b);
    });
  }
  function useSample(i) {
    var s = SAMPLES[i]; if (!s) return;
    var im = new Image();
    im.onload = function () {
      sourceImg = im; state.srcLabel = s.label; state.srcChar = s.char;
      state.inv = !!s.invert; $("inv").checked = state.inv;
      $("srcname").textContent = s.label;
      if (s.layer && state.layers.indexOf(s.layer) < 0) {
        state.layers.push(s.layer); renderLayerChips(); saveCfg();
        toast("已把「" + nameOf(s.layer) + "」加入檢索層", null);
      }
      Array.prototype.forEach.call($("samples").children, function (c, j) { c.classList.toggle("on", j === i); });
      $("drawbox").classList.remove("show"); $("bdraw").classList.remove("on");
      run();
    };
    im.src = "data:image/png;base64," + s.png;
  }

  /* ================= 抽屉 ================= */
  function openDrawer(idx) {
    var r = state.shown[idx]; if (!r) return;
    state.drawerIdx = idx;
    $("dtitle").textContent = r.ch + " · " + nameOf(r.lid);
    $("dsim").textContent = "相似 " + (r.sim * 100).toFixed(1) + "%";
    $("dsim").className = "pill " + (r.sim >= 0.9 ? "ok" : r.sim >= 0.72 ? "" : "warn");
    var ch = $("dch"); ch.textContent = r.ch; ch.style.fontFamily = '"' + r.lid + '", serif';
    ensureCss(r.lid);
    var L = loaded[r.lid];
    drawFP($("dfp"), L.grid.subarray(r.i * 256, r.i * 256 + 256));
    $("dkchar").textContent = r.ch;
    $("dkcp").textContent = cp(r.ch);
    $("dklayer").textContent = nameOf(r.lid);
    $("dkera").textContent = eraOf(r.lid);
    $("dksrc").textContent = "載入中…";
    $("dkvar").textContent = "—";
    ensureMeta(r.lid).then(function (meta) {
      if (state.drawerIdx !== idx) return;
      if (meta && meta[r.ch]) {
        var rows = meta[r.ch];
        var srcs = rows.map(function (x) { return x[1]; }).filter(Boolean);
        $("dksrc").textContent = srcs.length ? srcs.slice(0, 6).join(" · ") : "（上游未記出處）";
        $("dkvar").textContent = rows.length + " 種寫法";
      } else {
        $("dksrc").textContent = "字庫層，無逐字出處";
        $("dkvar").textContent = "1 種";
      }
    });
    $("bgrid").style.width = (r.g * 100).toFixed(1) + "%"; $("bgridv").textContent = (r.g * 100).toFixed(1);
    $("bproj").style.width = (r.p * 100).toFixed(1) + "%"; $("bprojv").textContent = (r.p * 100).toFixed(1);
    $("baspect").style.width = (r.a * 100).toFixed(1) + "%"; $("baspectv").textContent = (r.a * 100).toFixed(1);
    var mk = markOf(r.ch, r.lid);
    Array.prototype.forEach.call(document.querySelectorAll(".mk"), function (b) {
      b.classList.toggle("on", !!mk && mk.mark === b.dataset.m);
    });
    $("dnote").value = mk && mk.note ? mk.note : "";
    $("dopen").href = "index.html?q=" + encodeURIComponent(r.ch);
    $("scrim").classList.add("show"); $("drawer").classList.add("show");
    $("drawer").setAttribute("aria-hidden", "false");
  }
  function closeDrawer() {
    $("scrim").classList.remove("show"); $("drawer").classList.remove("show");
    $("drawer").setAttribute("aria-hidden", "true"); state.drawerIdx = -1;
  }
  function setMark(mark) {
    var r = state.shown[state.drawerIdx]; if (!r) return;
    undoSnap = JSON.stringify(ledger);
    var ex = markOf(r.ch, r.lid);
    if (ex) { ex.mark = mark; ex.sim = r.sim; ex.ts = Date.now(); ex.note = $("dnote").value; }
    else ledger.push({ ch: r.ch, lid: r.lid, layer: nameOf(r.lid), mark: mark,
      sim: r.sim, note: $("dnote").value, query: state.srcLabel, ts: Date.now() });
    saveLedger(); renderResults();
    Array.prototype.forEach.call(document.querySelectorAll(".mk"), function (b) {
      b.classList.toggle("on", b.dataset.m === mark);
    });
    toast(r.ch + " 已標為「" + (mark === "yes" ? "確認" : mark === "maybe" ? "存疑" : "排除") + "」",
      mark === "no" ? "warn" : null, "復原", function () {
        ledger = JSON.parse(undoSnap); saveLedger(); renderResults();
        Array.prototype.forEach.call(document.querySelectorAll(".mk"), function (b) { b.classList.remove("on"); });
      });
  }
  function bulkMark(mark) {
    var keys = Object.keys(state.sel); if (!keys.length) return;
    undoSnap = JSON.stringify(ledger);
    keys.forEach(function (k) {
      var r = state.sel[k], ex = markOf(r.ch, r.lid);
      if (ex) { ex.mark = mark; ex.sim = r.sim; ex.ts = Date.now(); }
      else ledger.push({ ch: r.ch, lid: r.lid, layer: nameOf(r.lid), mark: mark,
        sim: r.sim, note: "", query: state.srcLabel, ts: Date.now() });
    });
    state.sel = {}; saveLedger(); renderResults();
    toast(keys.length + " 個候選已標為「" + (mark === "yes" ? "確認" : "排除") + "」", null, "復原", function () {
      ledger = JSON.parse(undoSnap); saveLedger(); renderResults();
    });
  }
  function renderLedger() {
    $("lcount").textContent = ledger.length + " 條";
    var host = $("lbody");
    if (!ledger.length) {
      host.innerHTML = '<div class="lempty">尚未標注。點候選字 → 在詳情裡確認或排除，記錄會留在本機。</div>';
      return;
    }
    var rows = ledger.slice().sort(function (a, b) { return b.ts - a.ts; });
    var h = '<table class="ltable"><thead><tr><th>字</th><th>圖層</th><th>判定</th><th>相似</th><th>查詢來源</th><th>筆記</th><th></th></tr></thead><tbody>';
    rows.forEach(function (r) {
      h += "<tr><td class='g'>" + esc(r.ch) + "</td><td>" + esc(r.layer || nameOf(r.lid)) + "</td>" +
        "<td><span class='tag " + r.mark + "'>" + (r.mark === "yes" ? "確認" : r.mark === "maybe" ? "存疑" : "排除") + "</span></td>" +
        "<td style='font-family:var(--mono)'>" + (r.sim * 100).toFixed(0) + "%</td>" +
        "<td>" + esc(r.query || "—") + "</td><td>" + esc((r.note || "").slice(0, 40)) + "</td>" +
        "<td><button class='del' data-k='" + esc(r.ch + "|" + r.lid) + "' title='刪除'>✕</button></td></tr>";
    });
    h += "</tbody></table>";
    host.innerHTML = h;
    Array.prototype.forEach.call(host.querySelectorAll(".del"), function (b) {
      b.onclick = function () {
        undoSnap = JSON.stringify(ledger);
        var k = b.dataset.k;
        ledger = ledger.filter(function (r) { return (r.ch + "|" + r.lid) !== k; });
        saveLedger(); renderResults();
        toast("已刪除 1 條", "warn", "復原", function () { ledger = JSON.parse(undoSnap); saveLedger(); renderResults(); });
      };
    });
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  /* ================= 导出 ================= */
  function download(name, text, mime) {
    var b = new Blob([text], { type: mime || "text/plain;charset=utf-8" });
    var u = URL.createObjectURL(b), a = document.createElement("a");
    a.href = u; a.download = name; document.body.appendChild(a); a.click();
    setTimeout(function () { URL.revokeObjectURL(u); a.remove(); }, 400);
  }
  function stamp() { return new Date().toISOString().slice(0, 19).replace(/[:T]/g, ""); }
  function exportCandidates(fmt) {
    var pool = applyFilter(applySort(state.all)).slice(0, state.num);
    if (!pool.length) { toast("沒有可匯出的候選", "warn"); return; }
    if (fmt === "json") {
      download("shape-candidates-" + stamp() + ".json", JSON.stringify({
        tool: "glyph-atlas/shape", exported: new Date().toISOString(),
        query: state.srcLabel, params: { thr: state.thr, inv: state.inv, den: state.den, wt: state.wt, rot: state.rot, trim: state.trim, wgt: state.wgt },
        layers: state.layers.map(function (l) { return { id: l, name: nameOf(l) }; }),
        candidates: pool.map(function (r, i) {
          var mk = markOf(r.ch, r.lid);
          return { rank: i + 1, char: r.ch, codepoint: cp(r.ch), layer: r.lid, layer_name: nameOf(r.lid),
            similarity: +r.sim.toFixed(4), grid: +r.g.toFixed(4), projection: +r.p.toFixed(4),
            mark: mk ? mk.mark : null, note: mk ? mk.note : "" };
        })
      }, null, 2), "application/json;charset=utf-8");
    } else {
      var csv = "\uFEFFrank,char,codepoint,layer,layer_name,similarity,grid,projection,mark,note\n";
      pool.forEach(function (r, i) {
        var mk = markOf(r.ch, r.lid);
        csv += [i + 1, r.ch, cp(r.ch), r.lid, nameOf(r.lid), r.sim.toFixed(4), r.g.toFixed(4), r.p.toFixed(4),
          mk ? mk.mark : "", '"' + String(mk && mk.note ? mk.note : "").replace(/"/g, '""') + '"'].join(",") + "\n";
      });
      download("shape-candidates-" + stamp() + ".csv", csv, "text/csv;charset=utf-8");
    }
    toast("已匯出 " + pool.length + " 條候選");
  }
  function exportLedger() {
    if (!ledger.length) { toast("台賬是空的", "warn"); return; }
    var csv = "\uFEFFchar,codepoint,layer,layer_name,verdict,similarity,query,note,timestamp\n";
    ledger.forEach(function (r) {
      csv += [r.ch, cp(r.ch), r.lid, r.layer || nameOf(r.lid), r.mark, (r.sim || 0).toFixed(4),
        '"' + String(r.query || "").replace(/"/g, '""') + '"',
        '"' + String(r.note || "").replace(/"/g, '""') + '"',
        new Date(r.ts).toISOString()].join(",") + "\n";
    });
    download("shape-ledger-" + stamp() + ".csv", csv, "text/csv;charset=utf-8");
    toast("已匯出台賬 " + ledger.length + " 條");
  }

  /* ================= 主流程 ================= */
  var runTimer = null;
  function run(debounce) {
    clearTimeout(runTimer);
    runTimer = setTimeout(doRun, debounce == null ? 90 : debounce);
  }
  var pendingRun = false;
  function finishRun() {
    state.busy = false;
    if (pendingRun) { pendingRun = false; run(0); }
  }
  function doRun() {
    if (state.busy) { pendingRun = true; return; }
    state.busy = true; setStatus("檢索中");
    var t0 = performance.now();
    var pms = renderPreview();
    ensureLayers().then(function () {
      prog(0.6);
      if (!qd) {
        state.all = []; renderResults(); prog(null);
        $("rtime").textContent = "—"; setStatus("無墨");
        finishRun(); return;
      }
      return new Promise(function (res) { setTimeout(res, 16); }).then(function () {
        var ts = performance.now();
        state.all = search(qd);
        var sms = performance.now() - ts;
        prog(0.95);
        renderResults();
        var total = state.layers.reduce(function (a, l) { return a + (loaded[l] ? loaded[l].n : 0); }, 0);
        $("rtime").textContent = "比對 " + total.toLocaleString() + " 字形 · " + sms.toFixed(0) + " ms";
        $("rtime").className = "pill " + (sms < 220 ? "ok" : "warn");
        setStatus("就緒");
        if (state.srcChar && state.all.length) {
          var hit = -1;
          for (var i = 0; i < Math.min(state.all.length, 60); i++)
            if (state.all[i].ch === state.srcChar) { hit = i; break; }
          if (hit === 0) toast("樣本自檢：正確字「" + state.srcChar + "」排名第 1", null);
          else if (hit > 0) toast("樣本自檢：正確字「" + state.srcChar + "」排名第 " + (hit + 1), "warn");
        }
        prog(null); finishRun();
      });
    }).catch(function (e) {
      prog(null); finishRun(); setStatus("錯誤");
      toast("檢索失敗：" + e.message, "err");
    });
  }

  /* ================= 手绘 ================= */
  function drawCtx() { return $("draw").getContext("2d"); }
  function repaintDraw() {
    var c = $("draw"), x = drawCtx();
    x.fillStyle = "#000"; x.fillRect(0, 0, c.width, c.height);
    x.strokeStyle = "#fff"; x.lineCap = "round"; x.lineJoin = "round";
    strokes.forEach(function (st) {
      if (!st.pts.length) return;
      x.lineWidth = st.w; x.beginPath();
      x.moveTo(st.pts[0][0], st.pts[0][1]);
      for (var i = 1; i < st.pts.length; i++) x.lineTo(st.pts[i][0], st.pts[i][1]);
      if (st.pts.length === 1) x.lineTo(st.pts[0][0] + .01, st.pts[0][1]);
      x.stroke();
    });
  }
  function drawPos(ev) {
    var c = $("draw"), r = c.getBoundingClientRect();
    var t = ev.touches ? ev.touches[0] : ev;
    return [(t.clientX - r.left) / r.width * c.width, (t.clientY - r.top) / r.height * c.height];
  }
  function commitDraw() {
    var c = $("draw");
    sourceImg = c; state.srcLabel = "手繪筆畫"; state.srcChar = null;
    $("srcname").textContent = "手繪 · " + strokes.length + " 筆";
    Array.prototype.forEach.call($("samples").children, function (x) { x.classList.remove("on"); });
    run(140);
  }

  /* ================= 输入 ================= */
  function acceptImage(src, label, autoInv) {
    var im = new Image();
    im.onload = function () {
      sourceImg = im; state.srcLabel = label; state.srcChar = null;
      $("srcname").textContent = label;
      Array.prototype.forEach.call($("samples").children, function (x) { x.classList.remove("on"); });
      $("drawbox").classList.remove("show"); $("bdraw").classList.remove("on");
      if (autoInv) {
        var wc = toWork(im), b = binarize(wc);
        var want = b.borderLum > 128;
        if (want !== state.inv) { state.inv = want; $("inv").checked = want; }
      }
      run(0);
    };
    im.onerror = function () { toast("圖像無法讀取", "err"); };
    im.src = src;
  }
  function acceptFile(f) {
    if (!f || !/^image\//.test(f.type)) { toast("請給圖片檔", "warn"); return; }
    var fr = new FileReader();
    fr.onload = function () { acceptImage(fr.result, f.name.length > 18 ? f.name.slice(0, 17) + "…" : f.name, true); };
    fr.readAsDataURL(f);
  }

  /* ================= 绑定 ================= */
  function bindRange(id, key, fmt, vid) {
    var el = $(id);
    el.value = state[key];
    $(vid).textContent = fmt(state[key]);
    el.addEventListener("input", function () {
      state[key] = +el.value; $(vid).textContent = fmt(state[key]); saveCfg(); run();
    });
  }
  function bind() {
    bindRange("thr", "thr", function (v) { return v; }, "vthr");
    bindRange("den", "den", function (v) { return v; }, "vden");
    bindRange("wt", "wt", function (v) { return v > 0 ? "+" + v : v; }, "vwt");
    bindRange("rot", "rot", function (v) { return v + "°"; }, "vrot");
    bindRange("trim", "trim", function (v) { return v + "%"; }, "vtrim");
    bindRange("wgt", "wgt", function (v) { return v; }, "vw");

    $("inv").checked = state.inv;
    $("inv").addEventListener("change", function () { state.inv = this.checked; saveCfg(); run(0); });

    $("nminus").onclick = function () { state.num = clamp(state.num - 12, 12, 120); $("vnum").textContent = state.num; saveCfg(); renderResults(); };
    $("nplus").onclick = function () { state.num = clamp(state.num + 12, 12, 120); $("vnum").textContent = state.num; saveCfg(); renderResults(); };
    $("sort").value = state.sort;
    $("sort").onchange = function () { state.sort = this.value; saveCfg(); renderResults(); };
    $("markfilter").value = state.markfilter;
    $("markfilter").onchange = function () { state.markfilter = this.value; renderResults(); };
    Array.prototype.forEach.call($("view").children, function (b) {
      b.classList.toggle("on", b.dataset.v === state.view);
      b.onclick = function () {
        state.view = b.dataset.v;
        Array.prototype.forEach.call($("view").children, function (x) { x.classList.toggle("on", x === b); });
        saveCfg(); renderResults();
      };
    });

    $("reset").onclick = function () {
      state.thr = 128; state.inv = false; state.den = 1; state.wt = 0; state.rot = 0;
      state.trim = 0; state.wgt = 70;
      ["thr", "den", "wt", "rot", "trim", "wgt"].forEach(function (k) { $(k).value = state[k]; });
      $("inv").checked = false;
      $("vthr").textContent = 128; $("vden").textContent = 1; $("vwt").textContent = 0;
      $("vrot").textContent = "0°"; $("vtrim").textContent = "0%"; $("vw").textContent = 70;
      saveCfg(); run(0); toast("參數已重設");
    };
    $("rand").onclick = function () { useSample(Math.floor(Math.random() * SAMPLES.length)); };
    $("run").onclick = function () { run(0); };

    $("file").onchange = function () { if (this.files[0]) acceptFile(this.files[0]); this.value = ""; };
    var dz = $("drop");
    ["dragenter", "dragover"].forEach(function (e) {
      dz.addEventListener(e, function (ev) { ev.preventDefault(); dz.classList.add("over"); });
    });
    ["dragleave", "drop"].forEach(function (e) {
      dz.addEventListener(e, function (ev) { ev.preventDefault(); dz.classList.remove("over"); });
    });
    dz.addEventListener("drop", function (ev) {
      var f = ev.dataTransfer.files && ev.dataTransfer.files[0];
      if (f) acceptFile(f);
    });
    window.addEventListener("dragover", function (e) { e.preventDefault(); });
    window.addEventListener("drop", function (e) { e.preventDefault(); });
    document.addEventListener("paste", function (ev) {
      var items = ev.clipboardData && ev.clipboardData.items; if (!items) return;
      for (var i = 0; i < items.length; i++) if (/^image\//.test(items[i].type)) {
        acceptFile(items[i].getAsFile()); ev.preventDefault(); return;
      }
    });
    $("bpaste").onclick = function () {
      if (!navigator.clipboard || !navigator.clipboard.read) {
        toast("此瀏覽器不支援讀剪貼簿，請用 Ctrl+V", "warn"); return;
      }
      navigator.clipboard.read().then(function (items) {
        for (var i = 0; i < items.length; i++) {
          var t = items[i].types.filter(function (x) { return /^image\//.test(x); })[0];
          if (t) return items[i].getType(t).then(function (b) { acceptFile(new File([b], "clipboard.png", { type: b.type })); });
        }
        toast("剪貼簿裡沒有圖片", "warn");
      }).catch(function () { toast("剪貼簿權限被拒，請用 Ctrl+V", "warn"); });
    };

    $("bdraw").onclick = function () {
      var box = $("drawbox"), on = !box.classList.contains("show");
      box.classList.toggle("show", on); this.classList.toggle("on", on);
      if (on) { repaintDraw(); if (!strokes.length) toast("在格子裡畫出筆畫，放開即檢索"); }
    };
    $("bw").oninput = function () { $("bwv").textContent = this.value; };
    $("dclear").onclick = function () {
      if (!strokes.length) return;
      var snap = strokes.slice(); strokes = []; repaintDraw(); commitDraw();
      toast("畫布已清空", "warn", "復原", function () { strokes = snap; repaintDraw(); commitDraw(); });
    };
    $("dundo").onclick = function () { if (strokes.length) { strokes.pop(); repaintDraw(); commitDraw(); } };
    var dc = $("draw");
    function down(ev) {
      ev.preventDefault(); drawing = true;
      curStroke = { w: +$("bw").value * (dc.width / dc.getBoundingClientRect().width), pts: [drawPos(ev)] };
      strokes.push(curStroke); repaintDraw();
    }
    function move(ev) { if (!drawing) return; ev.preventDefault(); curStroke.pts.push(drawPos(ev)); repaintDraw(); }
    function up() { if (!drawing) return; drawing = false; curStroke = null; commitDraw(); }
    dc.addEventListener("mousedown", down); dc.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
    dc.addEventListener("touchstart", down, { passive: false });
    dc.addEventListener("touchmove", move, { passive: false });
    dc.addEventListener("touchend", up);

    $("bulkyes").onclick = function () { bulkMark("yes"); };
    $("bulkno").onclick = function () { bulkMark("no"); };
    $("expjson").onclick = function () { exportCandidates("json"); };
    $("expcsv").onclick = function () { exportCandidates("csv"); };
    $("lexp").onclick = exportLedger;
    $("lclear").onclick = function () {
      if (!ledger.length) return;
      undoSnap = JSON.stringify(ledger); ledger = []; saveLedger(); renderResults();
      toast("台賬已清空", "warn", "復原", function () { ledger = JSON.parse(undoSnap); saveLedger(); renderResults(); });
    };

    $("dclose").onclick = closeDrawer;
    $("scrim").onclick = closeDrawer;
    Array.prototype.forEach.call(document.querySelectorAll(".mk"), function (b) {
      b.onclick = function () { setMark(b.dataset.m); };
    });
    $("dnote").addEventListener("input", function () {
      var r = state.shown[state.drawerIdx]; if (!r) return;
      var mk = markOf(r.ch, r.lid);
      if (mk) { mk.note = this.value; saveLedger(); }
    });
    $("dcopy").onclick = function () {
      var r = state.shown[state.drawerIdx]; if (!r) return;
      if (navigator.clipboard && navigator.clipboard.writeText)
        navigator.clipboard.writeText(r.ch).then(function () { toast("已複製「" + r.ch + "」"); },
          function () { toast("複製失敗", "err"); });
      else toast("此環境不支援剪貼簿", "warn");
    };
    $("dnext").onclick = function () {
      var n = state.drawerIdx + 1;
      if (n >= state.shown.length) { toast("已是最候一個候選", "warn"); return; }
      openDrawer(n);
    };
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeDrawer();
      if (!$("drawer").classList.contains("show")) return;
      if (e.key === "ArrowDown" || e.key === "j") { e.preventDefault(); $("dnext").click(); }
      if (e.key === "ArrowUp" || e.key === "k") {
        e.preventDefault(); if (state.drawerIdx > 0) openDrawer(state.drawerIdx - 1);
      }
      if (e.target.tagName === "TEXTAREA") return;
      if (e.key === "1") setMark("yes");
      if (e.key === "2") setMark("maybe");
      if (e.key === "3") setMark("no");
    });
  }

  /* ================= 启动 ================= */
  function boot() {
    try {
      var c = JSON.parse(localStorage.getItem(LS_CFG) || "null");
      if (c) {
        ["thr", "inv", "den", "wt", "rot", "trim", "wgt", "num", "sort", "view"].forEach(function (k) {
          if (c[k] != null) state[k] = c[k];
        });
        if (Array.isArray(c.layers) && c.layers.length) {
          var valid = c.layers.filter(function (l) { return SHAPE_INDEX.some(function (s) { return s.id === l; }); });
          if (valid.length) state.layers = valid;
        }
      }
      ledger = JSON.parse(localStorage.getItem(LS_KEY) || "[]");
      if (!Array.isArray(ledger)) ledger = [];
    } catch (e) { ledger = []; }

    $("vnum").textContent = state.num;
    renderLayerChips(); renderSamples(); renderLedger(); bind();
    /* 规模数字从索引算，不写死，避免重建后与文案对不上 */
    $("htotal").textContent = SHAPE_INDEX.reduce(function (a, s) { return a + s.n; }, 0).toLocaleString();

    var qs = new URLSearchParams(location.search);
    var qch = qs.get("ch");
    if (qch) {
      // 从字形查询页带字过来：用该字在首个检索层里的字形当样本
      var lid = state.layers[0];
      loadLayer(lid).then(function (L) {
        var i = L.chars.indexOf(qch);
        if (i < 0) { toast("「" + qch + "」在 " + nameOf(lid) + " 裡沒有字形，改用內建樣本", "warn"); useSample(0); return; }
        var cv = document.createElement("canvas"); cv.width = 128; cv.height = 128;
        var g = L.grid.subarray(i * 256, i * 256 + 256);
        drawFP(cv, g);
        /* 由 16×16 密度网格重建 64×64 归一化掩膜：每格铺成 4×4 常量块。
           encode() 再按 4×4 盒式平均取回来，量化值逐格不变 → 自比对 100%。 */
        var al = new Uint8Array(N * N), mk = new Uint8Array(N * N);
        var gy, gx, y, x, v;
        for (gy = 0; gy < G; gy++) for (gx = 0; gx < G; gx++) {
          v = Math.round(g[gy * G + gx] / 15 * 255);
          for (y = 0; y < 4; y++) for (x = 0; x < 4; x++) {
            al[(gy * 4 + y) * N + gx * 4 + x] = v;
            mk[(gy * 4 + y) * N + gx * 4 + x] = v > 127 ? 1 : 0;
          }
        }
        var ar = 0.25 + L.aspect[i] / 255 * 3.75;
        var d = encode(al, Math.round(56 * ar), 56);
        d.aspect = L.aspect[i]; d.ar = ar; d.ink = L.ink[i];
        d.mask = mk; d.W = N; d.H = N;
        var x0 = N, y0 = N, x1 = -1, y1 = -1;
        for (y = 0; y < N; y++) for (x = 0; x < N; x++) if (mk[y * N + x]) {
          if (x < x0) x0 = x; if (x > x1) x1 = x;
          if (y < y0) y0 = y; if (y > y1) y1 = y;
        }
        d.bb = x1 < 0 ? { x0: 0, y0: 0, w: N, h: N } : { x0: x0, y0: y0, w: x1 - x0 + 1, h: y1 - y0 + 1 };
        fpOverride = d;
        sourceImg = cv; state.srcLabel = nameOf(lid) + "·" + qch + "（指紋）"; state.srcChar = qch;
        $("srcname").textContent = state.srcLabel;
        state.inv = false; $("inv").checked = false;
        run(0);
      });
      return;
    }
    useSample(0);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();