/* 印章考據 · 識印 歷代字形查詢平台
   整幅書影 → 朱印定位 → 印面拆字 → 逐格取指紋 → 篆書圖層比對

   全部純前端：圖片不離開本機，不上傳、不落盤。
   指紋數學一律走 fp-core.js（window.GA_FP），與 scripts/build_shape_index.py
   逐位同構；此處只做「輸入側」——色相分離、連通域、XY 切分。 */
(function () {
  "use strict";

  var $ = function (id) { return document.getElementById(id); };
  var FP = window.GA_FP;
  var N = FP.N, INNER = FP.INNER, G = FP.G, STRIDE = FP.STRIDE;

  /* ============ 常量 ============ */
  var DETECT_MAX = 1800;      // 檢測時把長邊縮到這個值（大圖降採樣，小印仍可辨）
  var SEAL_WORK = 320;        // 單枚印面的工作長邊（小印面也放大到這裡再切）
  var HUE_RED = 357.3;        // 朱砂/印泥的參考色相（度）
  var MAX_CELLS = 9;

  var state = {
    img: null, iw: 0, ih: 0,
    seals: [], active: -1,
    zoom: 1, showBox: true,
    order: "rc", autoSplit: true,
    cur: null,                 // 當前印面的解算結果
    cells: [],
    layers: ["seal", "beishida", "shuowen-seal-kaiyuan", "liushuwenmai-xiaozhuan", "grassseal"],
    num: 6,
    busy: false
  };

  /* ============ 小工具 ============ */
  function mkCanvas(w, h) {
    var c = document.createElement("canvas");
    c.width = Math.max(1, Math.round(w));
    c.height = Math.max(1, Math.round(h));
    return c;
  }
  function ctx2d(c) { return c.getContext("2d", { willReadFrequently: true }); }
  function nameOf(lid) {
    var L = (window.GA_LAYERS || []).filter(function (x) { return x.id === lid; })[0];
    return L ? (L.name_zh || lid) : lid;
  }
  function toast(msg, kind) {
    var t = document.createElement("div");
    t.className = "toast" + (kind ? " " + kind : "");
    t.textContent = msg;
    (document.getElementById("toasts") || document.body).appendChild(t);
    setTimeout(function () { t.classList.add("out"); }, 2600);
    setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 3100);
  }
  function rgb2hsv(d, o) {
    var r = d[o] / 255, g = d[o + 1] / 255, b = d[o + 2] / 255;
    var mx = r > g ? (r > b ? r : b) : (g > b ? g : b);
    var mn = r < g ? (r < b ? r : b) : (g < b ? g : b);
    var dd = mx - mn, h = 0;
    if (dd > 0) {
      if (mx === r) h = ((g - b) / dd) % 6;
      else if (mx === g) h = (b - r) / dd + 2;
      else h = (r - g) / dd + 4;
      h *= 60;
      if (h < 0) h += 360;
    }
    return { h: h, s: mx ? dd / mx : 0, v: mx };
  }
  function hueDist(a, b) {
    var d = Math.abs(a - b) % 360;
    return d > 180 ? 360 - d : d;
  }

  /* ============ 圖片載入 ============ */
  function setImage(src, label) {
    var im = new Image();
    im.onload = function () {
      var w = im.naturalWidth, h = im.naturalHeight;
      if (Math.max(w, h) > 4096) {           // 長卷保護：createImageBitmap / canvas 都會 OOM
        var s = 4096 / Math.max(w, h);
        var c = mkCanvas(w * s, h * s);
        ctx2d(c).drawImage(im, 0, 0, c.width, c.height);
        im = new Image();
        im.onload = function () { finish(im, c.width, c.height, label); };
        im.src = c.toDataURL("image/png");
        return;
      }
      finish(im, w, h, label);
    };
    im.onerror = function () { toast("圖片解不開，換個格式再試", "err"); };
    im.src = src;
  }
  function finish(im, w, h, label) {
    state.img = im; state.iw = w; state.ih = h;
    state.seals = []; state.active = -1; state.cur = null; state.cells = [];
    $("ph").style.display = "none";
    $("splitCard").hidden = true;
    $("stg").textContent = (label || "書影") + " · " + w + "×" + h;
    layout();
    renderList();
    detect();
  }

  /* ============ 畫布 ============ */
  function layout() {
    var wrap = $("canvaswrap"), stage = $("stage");
    if (!state.img) return;
    var availW = Math.max(320, wrap.clientWidth - 2);
    var availH = Math.max(260, Math.round(window.innerHeight * 0.60));
    var fit = Math.min(availW / state.iw, availH / state.ih);
    var s = Math.max(fit, 0.02) * state.zoom;
    var dpr = Math.min(2, window.devicePixelRatio || 1);
    var cw = Math.round(state.iw * s), ch = Math.round(state.ih * s);
    stage.width = Math.round(cw * dpr); stage.height = Math.round(ch * dpr);
    stage.style.width = cw + "px"; stage.style.height = ch + "px";
    var c = ctx2d(stage);
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.imageSmoothingQuality = "high";
    c.drawImage(state.img, 0, 0, cw, ch);
    if (state.showBox) drawBoxes(c, cw, ch, s);
    state.dispScale = s;
  }
  function drawBoxes(c, cw, ch, s) {
    for (var i = 0; i < state.seals.length; i++) {
      var b = state.seals[i];
      var x = b.x * s, y = b.y * s, w = b.w * s, h = b.h * s;
      var on = i === state.active;
      c.save();
      c.lineWidth = on ? 2.2 : 1.4;
      c.strokeStyle = on ? "#9e2b1e" : "rgba(158,43,30,.55)";
      if (on) { c.shadowColor = "rgba(158,43,30,.35)"; c.shadowBlur = 9; }
      c.strokeRect(x + .5, y + .5, w, h);
      c.restore();
      c.save();
      c.font = "600 " + Math.max(11, Math.min(15, w / 3)) + "px ui-monospace,Consolas,monospace";
      var tag = String(i + 1);
      var tw = c.measureText(tag).width + 10;
      c.fillStyle = on ? "#9e2b1e" : "rgba(158,43,30,.82)";
      c.fillRect(x, Math.max(0, y - 20), tw, 18);
      c.fillStyle = "#fff8f2";
      c.fillText(tag, x + 5, Math.max(13, y - 7));
      c.restore();
    }
  }

  /* ============ 朱印檢測 ============ */
  function detect() {
    if (!state.img) return;
    var iw = state.iw, ih = state.ih;
    var s = Math.min(1, DETECT_MAX / Math.max(iw, ih));
    if ($("whole").checked) {
      state.seals = [{ x: 0, y: 0, w: iw, h: ih, dens: 1, px: iw * ih, idx: 0 }];
      state.active = 0;
      renderList(); layout(); selectSeal(0);
      return;
    }
    var W = Math.max(8, Math.round(iw * s)), H = Math.max(8, Math.round(ih * s));
    var c = mkCanvas(W, H), x = ctx2d(c);
    x.fillStyle = "#fff"; x.fillRect(0, 0, W, H);
    x.drawImage(state.img, 0, 0, W, H);
    var d = x.getImageData(0, 0, W, H).data;

    var tol = +$("tol").value, sat = +$("sat").value / 100;
    var vlo = 0.20, vhi = 0.93;
    var m = new Uint8Array(W * H), redc = new Float32Array(W * H), lumo = new Float32Array(W * H);
    var i, o, hsv;
    for (i = 0; i < W * H; i++) {
      o = i * 4;
      hsv = rgb2hsv(d, o);
      var ok = hueDist(hsv.h, HUE_RED) <= tol && hsv.s >= sat && hsv.v >= vlo && hsv.v <= vhi;
      m[i] = ok ? 1 : 0;
      redc[i] = d[o] - 0.82 * d[o + 1] - 0.42 * d[o + 2];
      lumo[i] = 0.299 * d[o] + 0.587 * d[o + 1] + 0.114 * d[o + 2];
    }
    // 膨脹（8 鄰域，半徑 2）把斷開的筆畫與印框連起來
    var dil = dilate(m, W, H, 2);
    var comps = components(dil, W, H);

    var minSide = +$("min").value * s;          // 原圖 px → 工作 px
    var minPx = Math.max(40, (+$("min").value * s) * (+$("min").value * s) * 0.35);
    var minDens = +$("den").value / 100;
    var out = [];
    for (i = 0; i < comps.length; i++) {
      var C = comps[i];
      var side = Math.max(C.w, C.h);
      if (side < minSide) continue;
      if (C.px < minPx) continue;
      var dn = C.px / Math.max(1, C.w * C.h);
      if (dn < minDens) continue;
      // 對比度用「亮度」：白文印整片是紅底，紅度分佈扁平，但字與底亮度落差明顯
      var vals = [];
      for (var k = 0; k < C.list.length; k += 1) vals.push(lumo[C.list[k]]);
      vals.sort(function (a, b) { return a - b; });
      var p995 = vals[Math.min(vals.length - 1, Math.floor(vals.length * 0.995))];
      var p20 = vals[Math.floor(vals.length * 0.2)];
      if (p995 - p20 < 14 && dn < 0.55) continue;
      var pad = Math.round(side * 0.04);
      out.push({
        x: Math.max(0, (C.x0 - pad) / s), y: Math.max(0, (C.y0 - pad) / s),
        w: Math.min(iw, (C.w + pad * 2) / s), h: Math.min(ih, (C.h + pad * 2) / s),
        dens: dn, px: C.px, contrast: p995 - p20
      });
    }
    // 合併「印框 + 框內字塊」：一枚朱文印常被拆成多個連通域
    out.sort(function (a, b) { return (b.w * b.h) - (a.w * a.h); });
    var merged = [];
    for (i = 0; i < out.length; i++) {
      var A = out[i], inside = false;
      for (var j = 0; j < merged.length; j++) {
        var B = merged[j];
        var ix = Math.max(0, Math.min(A.x + A.w, B.x + B.w) - Math.max(A.x, B.x));
        var iy = Math.max(0, Math.min(A.y + A.h, B.y + B.h) - Math.max(A.y, B.y));
        var inter = ix * iy;
        if (inter >= A.w * A.h * 0.85) { inside = true; break; }
      }
      if (!inside) merged.push(A);
    }
    out = merged;
    out.sort(function (a, b) { return a.y - b.y || a.x - b.x; });
    out.forEach(function (b, n) { b.idx = n; });
    state.seals = out;
    state.active = out.length ? 0 : -1;
    renderList(); layout();
    $("stg").textContent = (state.seals.length ? "檢出 " + state.seals.length + " 枚印面"
      : "未檢出印面") + " · " + iw + "×" + ih;
    if (out.length) selectSeal(0);
    else { $("splitCard").hidden = true; }
  }

  function dilate(m, W, H, r) {
    var t = m.slice(), out = new Uint8Array(W * H);
    for (var y = 0; y < H; y++) for (var x = 0; x < W; x++) {
      var v = 0;
      for (var dy = -r; dy <= r && !v; dy++) for (var dx = -r; dx <= r; dx++) {
        var yy = y + dy, xx = x + dx;
        if (yy < 0 || yy >= H || xx < 0 || xx >= W) continue;
        if (t[yy * W + xx]) { v = 1; break; }
      }
      out[y * W + x] = v;
    }
    return out;
  }

  /* 8 鄰域連通域（BFS），只收集觸點座標用於密度／對比統計 */
  function components(m, W, H) {
    var seen = new Uint8Array(W * H), res = [];
    var stack = new Int32Array(W * H);
    for (var i0 = 0; i0 < W * H; i0++) {
      if (!m[i0] || seen[i0]) continue;
      var sp = 0; stack[sp++] = i0; seen[i0] = 1;
      var x0 = W, y0 = H, x1 = 0, y1 = 0, px = 0, list = [];
      while (sp) {
        var i = stack[--sp];
        var x = i % W, y = (i - x) / W;
        px++; list.push(i);
        if (x < x0) x0 = x; if (y < y0) y0 = y;
        if (x > x1) x1 = x; if (y > y1) y1 = y;
        for (var dy = -1; dy <= 1; dy++) for (var dx = -1; dx <= 1; dx++) {
          if (!dx && !dy) continue;
          var yy = y + dy, xx = x + dx;
          if (yy < 0 || yy >= H || xx < 0 || xx >= W) continue;
          var j = yy * W + xx;
          if (m[j] && !seen[j]) { seen[j] = 1; stack[sp++] = j; }
        }
      }
      res.push({ x0: x0, y0: y0, x1: x1, y1: y1,
                 w: x1 - x0 + 1, h: y1 - y0 + 1, px: px, list: list });
    }
    return res;
  }

  /* ============ 印面 → 字格 ============ */
  function selectSeal(n) {
    try {
      state.active = n;
      layout();
      var b = state.seals[n];
      if (!b) return;
      var S = state.seals;
      var el = $("sealList").children;
      for (var i = 0; i < el.length; i++) el[i].classList.toggle("on", i === n);
      // 印面裁切：長邊放大到 SEAL_WORK 再做色相分離（小印面也能切字）
      var scale = Math.min(8, Math.max(1, SEAL_WORK / Math.max(b.w, b.h)));
      var cw = Math.max(8, Math.round(b.w * scale)), ch = Math.max(8, Math.round(b.h * scale));
      var c = mkCanvas(cw, ch), x = ctx2d(c);
      x.imageSmoothingQuality = "high";
      x.drawImage(state.img, b.x, b.y, b.w, b.h, 0, 0, cw, ch);
      var d = x.getImageData(0, 0, cw, ch).data;
      var tol = +$("tol").value, sat = +$("sat").value / 100;
      var red = new Uint8Array(cw * ch), dens = 0;
      for (var i2 = 0; i2 < cw * ch; i2++) {
        var o = i2 * 4, hsv = rgb2hsv(d, o);
        var ok = hueDist(hsv.h, HUE_RED) <= tol && hsv.s >= sat && hsv.v >= 0.20 && hsv.v <= 0.93;
        red[i2] = ok ? 1 : 0; dens += red[i2];
      }
      dens /= cw * ch;
      // 白文：紅底白字 → 字取非紅，且只取紅塊 bbox 之內（否則周邊白紙算筆畫）
      var bai = dens > 0.5;
      var m = new Uint8Array(cw * ch), framed = false, i3;
      if (bai) {
        var bbRed = FP.bbox(red, cw, ch);
        if (bbRed) {
          for (var yy1 = bbRed.y0; yy1 < bbRed.y0 + bbRed.h; yy1++)
            for (var xx1 = bbRed.x0; xx1 < bbRed.x0 + bbRed.w; xx1++) {
              var ii1 = yy1 * cw + xx1;
              m[ii1] = red[ii1] ? 0 : 1;
            }
        }
      } else {
        for (i3 = 0; i3 < cw * ch; i3++) m[i3] = red[i3];
      }

      // 先按墨跡外框精裁（detect 給印面加了 4% padding，最外沿是白紙）
      var bb0 = FP.bbox(m, cw, ch);
      if (!bb0) { toast("這枚印面提不出筆畫，換個容差再試", "err"); return; }
      var m1 = new Uint8Array(bb0.w * bb0.h);
      for (var yy0 = 0; yy0 < bb0.h; yy0++) for (var xx0 = 0; xx0 < bb0.w; xx0++)
        m1[yy0 * bb0.w + xx0] = m[(bb0.y0 + yy0) * cw + (bb0.x0 + xx0)];
      m = m1; cw = bb0.w; ch = bb0.h;

      // 朱文：印框（方框/圓環）是貼著外沿的連通域，丟掉它才切得出字間空隙
      if (!bai) {
        var fr = dropEdgeComponents(m, cw, ch, 2);
        m = fr.m; framed = fr.dropped;
      }

      var bb = FP.bbox(m, cw, ch);
      if (!bb) { toast("這枚印面提不出筆畫，換個容差再試", "err"); return; }
      // 精裁到筆畫外框
      var m2 = new Uint8Array(bb.w * bb.h);
      for (var yy = 0; yy < bb.h; yy++) for (var xx = 0; xx < bb.w; xx++)
        m2[yy * bb.w + xx] = m[(bb.y0 + yy) * cw + (bb.x0 + xx)];

      state.cur = { box: b, W: bb.w, H: bb.h, mask: m2, bai: bai, framed: framed, dens: dens };
      renderSealPrev();
      buildCells();
    } catch (e) {
      toast("這枚印面解析失敗：" + (e && e.message ? e.message : e), "err");
    }
  }

  /* 剝掉最外一圈連通的印框：從四邊往內走，直到整行/整列墨量掉下來 */
  function stripFrame(m, W, H) {
    function rowFrac(y, x0, x1) { var s = 0; for (var x = x0; x < x1; x++) s += m[y * W + x]; return s / Math.max(1, x1 - x0); }
    function colFrac(x, y0, y1) { var s = 0; for (var y = y0; y < y1; y++) s += m[y * W + x]; return s / Math.max(1, y1 - y0); }
    var x0 = 0, y0 = 0, x1 = W, y1 = H, cut = false;
    var lim = Math.floor(Math.min(W, H) * 0.18), g = 0;
    while (y0 < y1 - 10 && rowFrac(y0, x0, x1) > 0.55 && g++ < lim) { y0++; cut = true; }
    g = 0;
    while (y1 > y0 + 10 && rowFrac(y1 - 1, x0, x1) > 0.55 && g++ < lim) { y1--; cut = true; }
    g = 0;
    while (x0 < x1 - 10 && colFrac(x0, y0, y1) > 0.55 && g++ < lim) { x0++; cut = true; }
    g = 0;
    while (x1 > x0 + 10 && colFrac(x1 - 1, y0, y1) > 0.55 && g++ < lim) { x1--; cut = true; }
    var out = new Uint8Array((x1 - x0) * (y1 - y0));
    for (var y = y0; y < y1; y++) for (var x = x0; x < x1; x++)
      out[(y - y0) * (x1 - x0) + (x - x0)] = m[y * W + x];
    return { m: out, W: x1 - x0, H: y1 - y0, cut: cut };
  }

  /* 丟掉貼著外沿的連通域（印框、圓環）。整枚都貼邊時保留原樣。 */
  function dropEdgeComponents(m, W, H, ring) {
    var seen = new Uint8Array(W * H), keep = new Uint8Array(W * H);
    var stack = new Int32Array(W * H), dropped = 0, kept = 0;
    for (var i0 = 0; i0 < W * H; i0++) {
      if (!m[i0] || seen[i0]) continue;
      var sp = 0, edge = false, cells = [];
      stack[sp++] = i0; seen[i0] = 1;
      while (sp) {
        var i = stack[--sp], x = i % W, y = (i - x) / W;
        cells.push(i);
        if (x < ring || y < ring || x >= W - ring || y >= H - ring) edge = true;
        for (var dy = -1; dy <= 1; dy++) for (var dx = -1; dx <= 1; dx++) {
          if (!dx && !dy) continue;
          var yy = y + dy, xx = x + dx;
          if (yy < 0 || yy >= H || xx < 0 || xx >= W) continue;
          var j = yy * W + xx;
          if (m[j] && !seen[j]) { seen[j] = 1; stack[sp++] = j; }
        }
      }
      if (edge) { dropped++; continue; }
      kept++;
      for (var k = 0; k < cells.length; k++) keep[cells[k]] = 1;
    }
    if (!kept) return { m: m, dropped: false };   // 全貼邊 → 當作沒有框
    return { m: keep, dropped: dropped > 0 };
  }

  /* 以「墨列／墨行的連續段」切字。
     比找投影谷穩：一個字內部的筆畫間隙很窄，不會被當成分割點；
     而字與字之間是整條空白帶，天然可切。 */
  function inkRuns(profile, n, minGap, minLen) {
    var runs = [], i = 0, start = -1, gap = 0;
    for (i = 0; i < n; i++) {
      if (profile[i] > 0) { if (start < 0) start = i; gap = 0; }
      else if (start >= 0) {
        gap++;
        if (gap >= minGap) { runs.push([start, i - gap + 1]); start = -1; gap = 0; }
      }
    }
    if (start >= 0) runs.push([start, n]);
    return runs.filter(function (r) { return r[1] - r[0] >= minLen; });
  }

  function segmentCells(m, W, H, maxCells) {
    var gx = Math.max(3, Math.round(W * 0.035)), gy = Math.max(3, Math.round(H * 0.03));
    var minW = Math.max(5, Math.round(W * 0.07)), minH = Math.max(5, Math.round(H * 0.07));
    var colP = new Float32Array(W), x, y, i, j, s, t;
    for (x = 0; x < W; x++) { s = 0; for (y = 0; y < H; y++) s += m[y * W + x]; colP[x] = s; }
    var cols = inkRuns(colP, W, gx, minW);
    if (!cols.length) return [{ x: 0, y: 0, w: W, h: H }];
    var cells = [];
    for (i = 0; i < cols.length; i++) {
      var a = cols[i][0], b = cols[i][1], cw = b - a;
      var rowP = new Float32Array(H);
      for (y = 0; y < H; y++) { t = 0; for (x = a; x < b; x++) t += m[y * W + x]; rowP[y] = t; }
      var rows = inkRuns(rowP, H, gy, minH);
      if (!rows.length) rows = [[0, H]];
      for (j = 0; j < rows.length; j++)
        cells.push({ x: a, y: rows[j][0], w: cw, h: rows[j][1] - rows[j][0] });
    }
    if (cells.length <= 1 || cells.length > maxCells) return [{ x: 0, y: 0, w: W, h: H }];
    // 合理性檢查：任何一格的長寬比過分，說明切錯了（如把「川」拆成三欄）
    for (i = 0; i < cells.length; i++) {
      var ar = cells[i].w / Math.max(1, cells[i].h);
      if (ar < 0.40 || ar > 2.5) return [{ x: 0, y: 0, w: W, h: H }];
    }
    return cells;
  }

  /* 按印面閱讀順序重排字格（rc 直行右至左 / cr 橫行右至左 / lt 橫行左至右） */
  function orderCells(rects, W, H, mode) {
    var list = rects.slice();
    // 先按行聚類（中心 y 相差 < 半格高算同一行）
    list.sort(function (a, b) { return (a.y + a.h / 2) - (b.y + b.h / 2); });
    var rows = [], cur = [], cy = -1e9;
    list.forEach(function (r) {
      var c = r.y + r.h / 2;
      if (!cur.length || c - cy < r.h * 0.5) { cur.push(r); cy = cur.length ? (cy + c) / 2 : c; }
      else { rows.push(cur); cur = [r]; cy = c; }
    });
    if (cur.length) rows.push(cur);
    rows.forEach(function (row) { row.sort(function (a, b) { return a.x - b.x; }); });
    var ord = [];
    if (mode === "rc") {
      // 直行：欄由右至左
      var cols = {};
      list.forEach(function (r) { var k = Math.round((r.x + r.w / 2) / (W / 4)); (cols[k] = cols[k] || []).push(r); });
      Object.keys(cols).map(Number).sort(function (a, b) { return b - a; }).forEach(function (k) {
        cols[k].sort(function (a, b) { return a.y - b.y; }).forEach(function (r) { ord.push(r); });
      });
      return ord;
    }
    rows.forEach(function (row) {
      if (mode === "cr") row.reverse();
      row.forEach(function (r) { ord.push(r); });
    });
    return ord;
  }

  /* 只讀調試出口：查看當前印面掩膜的列／行投影，便於判斷切分是否合理 */
  window.GA_SEAL_DEBUG = function () {
    var C = state.cur; if (!C) return null;
    var colP = [], rowP = [], x, y, s;
    for (x = 0; x < C.W; x++) { s = 0; for (y = 0; y < C.H; y++) s += C.mask[y * C.W + x]; colP.push(s); }
    for (y = 0; y < C.H; y++) { s = 0; for (x = 0; x < C.W; x++) s += C.mask[y * C.W + x]; rowP.push(s); }
    return { W: C.W, H: C.H, dens: C.dens, bai: C.bai, framed: C.framed,
             cells: state.cells.length, seals: state.seals.length,
             colP: colP, rowP: rowP };
  };

  /* ============ 字格渲染與檢索 ============ */
  function renderSealPrev() {
    var C = state.cur, host = $("sealprev");
    host.innerHTML = "";
    if (!C) return;
    var pvS = Math.min(150 / C.W, 320 / C.H);
    var c = mkCanvas(Math.max(24, Math.round(C.W * pvS)), Math.max(24, Math.round(C.H * pvS)));
    var x = ctx2d(c);
    var img = x.createImageData(C.W, C.H);
    for (var i = 0; i < C.W * C.H; i++) {
      var on = C.mask[i];
      img.data[i * 4] = on ? 260 - 234 : 247;      // 墨 26 → 纸 247
      img.data[i * 4 + 1] = on ? 24 : 243;
      img.data[i * 4 + 2] = on ? 21 : 234;
      img.data[i * 4 + 3] = 255;
    }
    var tmp = mkCanvas(C.W, C.H); ctx2d(tmp).putImageData(img, 0, 0);
    x.imageSmoothingQuality = "high";
    x.drawImage(tmp, 0, 0, c.width, c.height);
    c.className = "sp";
    host.appendChild(c);
    var tag = document.createElement("div");
    tag.className = "sptag";
    tag.innerHTML = (C.bai ? "白文" : "朱文") + (C.framed ? " · 已剝框" : "") +
      " · <b>" + C.W + "×" + C.H + "</b>";
    host.appendChild(tag);
  }

  function buildCells() {
    var C = state.cur;
    if (!C) return;
    var rects;
    if (state.autoSplit && state.cells.length !== 1) {
      rects = segmentCells(C.mask, C.W, C.H, MAX_CELLS);
    } else rects = [{ x: 0, y: 0, w: C.W, h: C.H }];
    // 墨量過少的格子丟掉（多為印框殘留）
    rects = rects.filter(function (r) {
      var s = 0;
      for (var y = 0; y < r.h; y++) for (var x = 0; x < r.w; x++) s += C.mask[(r.y + y) * C.W + (r.x + x)];
      r.ink = s / (r.w * r.h);
      return r.ink > 0.02;
    });
    if (!rects.length) rects = [{ x: 0, y: 0, w: C.W, h: C.H, ink: 1 }];
    state.cells = orderCells(rects, C.W, C.H, state.order).map(function (r) {
      var m = new Uint8Array(r.w * r.h);
      for (var y = 0; y < r.h; y++) for (var x = 0; x < r.w; x++)
        m[y * r.w + x] = C.mask[(r.y + y) * C.W + (r.x + x)];
      return { rect: r, mask: m, W: r.w, H: r.h, hits: [], q: null };
    });
    $("splitCard").hidden = false;
    $("cellhint").textContent = state.cells.length + " 格 · 逐格比對";
    renderCells();
    searchAll();
  }

  function renderCells() {
    var host = $("cells"); host.innerHTML = "";
    if (!state.cells.length) { host.innerHTML = '<div class="empty2">沒有字格</div>'; return; }
    state.cells.forEach(function (cell, i) {
      var d = document.createElement("div");
      d.className = "cell2";
      var cv = mkCanvas(96, 96 * (cell.H / cell.W));
      var x = ctx2d(cv);
      var im = x.createImageData(cell.W, cell.H);
      for (var k = 0; k < cell.W * cell.H; k++) {
        im.data[k * 4] = cell.mask[k] ? 26 : 255;
        im.data[k * 4 + 1] = cell.mask[k] ? 24 : 253;
        im.data[k * 4 + 2] = cell.mask[k] ? 21 : 248;
        im.data[k * 4 + 3] = 255;
      }
      var t = mkCanvas(cell.W, cell.H); ctx2d(t).putImageData(im, 0, 0);
      x.imageSmoothingQuality = "high";
      x.drawImage(t, 0, 0, cv.width, cv.height);
      var wrap = document.createElement("div");
      wrap.className = "cv"; wrap.appendChild(cv);
      var ord = document.createElement("div");
      ord.className = "ord"; ord.textContent = i + 1;
      d.appendChild(ord); d.appendChild(wrap);
      var list = document.createElement("div");
      list.className = "top";
      if (!cell.hits.length) list.innerHTML = '<div class="alt wait">比對中…</div>';
      else cell.hits.slice(0, state.num).forEach(function (h, j) {
        var row = document.createElement("div");
        row.className = "res" + (j === 0 ? " best" : "");
        row.innerHTML = '<span class="ch">' + esc(h.ch) + '</span>' +
          '<span class="pct">' + Math.round(h.sim * 100) + '%</span>' +
          '<span class="alt">' + esc(shortName(h.lid)) + '</span>';
        row.title = nameOf(h.lid) + " · " + Math.round(h.sim * 100) + "%";
        row.onclick = function () { goChar(h.ch); };
        list.appendChild(row);
      });
      d.appendChild(list);
      host.appendChild(d);
    });
  }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]; }); }
  function shortName(lid) {
    var L = (window.GA_LAYERS || []).filter(function (x) { return x.id === lid; })[0];
    return L && L.mono ? L.mono : nameOf(lid).slice(0, 2);
  }
  function goChar(ch) { location.href = "shape.html?ch=" + encodeURIComponent(ch); }

  /* ============ 圖層載入與比對 ============ */
  var loaded = {}, loading = {}, cssDone = {};
  function ensureCss(lid) {
    if (cssDone[lid]) return;
    cssDone[lid] = 1;
    var l = document.createElement("link");
    l.rel = "stylesheet"; l.href = "css/" + lid + ".css";
    document.head.appendChild(l);
  }
  function loadLayer(lid) {
    if (loaded[lid]) return Promise.resolve(loaded[lid]);
    if (loading[lid]) return loading[lid];
    loading[lid] = new Promise(function (res, rej) {
      var s = document.createElement("script");
      s.src = "data/shape/" + lid + ".js";
      s.onload = function () {
        var p = (window.GA_SHAPE || {})[lid];
        if (!p) { rej(new Error("no payload")); return; }
        try { loaded[lid] = decodeLayer(p); res(loaded[lid]); } catch (e) { rej(e); }
      };
      s.onerror = function () { rej(new Error("load fail")); };
      document.head.appendChild(s);
    });
    return loading[lid];
  }
  function decodeLayer(p) {
    var bin = atob(p.b64), raw = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) raw[i] = bin.charCodeAt(i);
    var n = p.n, S = p.stride || STRIDE;
    var grid = new Uint8Array(n * 256), proj = new Uint8Array(n * 32);
    var aspect = new Uint8Array(n), ink = new Uint8Array(n);
    for (var i2 = 0; i2 < n; i2++) {
      var o = i2 * S, gb = i2 * 256, pb = i2 * 32, j, b;
      for (j = 0; j < 128; j++) { b = raw[o + j]; grid[gb + j * 2] = b >> 4; grid[gb + j * 2 + 1] = b & 15; }
      for (j = 0; j < 8; j++) { b = raw[o + 128 + j]; proj[pb + j * 2] = b >> 4; proj[pb + j * 2 + 1] = b & 15; }
      for (j = 0; j < 8; j++) { b = raw[o + 136 + j]; proj[pb + 16 + j * 2] = b >> 4; proj[pb + 16 + j * 2 + 1] = b & 15; }
      aspect[i2] = raw[o + 144]; ink[i2] = raw[o + 145];
    }
    var chars = Array.from(p.chars).slice(0, n);
    return { id: p.id, n: n, chars: chars, grid: grid, proj: proj, aspect: aspect, ink: ink };
  }
  function searchAll() {
    if (!state.cells.length) return;
    var want = state.layers.slice(), need = want.filter(function (l) { return !loaded[l]; });
    if (need.length) need.forEach(ensureCss);
    Promise.all(want.map(function (lid) {
      return loadLayer(lid).catch(function () { return null; });
    })).then(function () {
      state.cells.forEach(function (cell) {
        var q = FP.fingerprint(cell.mask, cell.W, cell.H);
        cell.q = q;
        cell.hits = search(q, want);
      });
      renderCells();
      $("cellhint").textContent = state.cells.length + " 格 · 已比對 " +
        want.filter(function (l) { return loaded[l]; }).length + " 層";
    });
  }
  function search(q, lids) {
    var w = 0.70, out = [];
    for (var li = 0; li < lids.length; li++) {
      var L = loaded[lids[li]]; if (!L) continue;
      for (var i = 0; i < L.n; i++) {
        var gb = i * 256, pb = i * 32, gd = 0, pd = 0, k, dv;
        for (k = 0; k < 256; k++) { dv = q.grid[k] - L.grid[gb + k]; gd += dv < 0 ? -dv : dv; }
        for (k = 0; k < 32; k++) { dv = q.proj[k] - L.proj[pb + k]; pd += dv < 0 ? -dv : dv; }
        gd /= 3840; pd /= 480;
        var ad = Math.abs(q.aspect - L.aspect[i]) / 255;
        var sim = 1 - (w * gd + (1 - w) * pd + 0.10 * ad);
        out.push({ ch: L.chars[i], lid: L.id, sim: sim < 0 ? 0 : sim });
      }
    }
    out.sort(function (a, b) { return b.sim - a.sim; });
    // 同字去重：只保留每字最高分那一條（不同圖層的同一字仍分開展示）
    return out.slice(0, 60);
  }

  /* ============ 印面列表 ============ */
  function renderList() {
    var host = $("sealList"); host.innerHTML = "";
    if (!state.seals.length) {
      host.innerHTML = '<div class="empty2">上傳書影後自動列出</div>';
      $("listhint").textContent = "尚未檢測";
      var dc0 = $("dcount"); if (dc0) dc0.textContent = "—";
      return;
    }
    state.seals.forEach(function (b, i) {
      var d = document.createElement("div");
      d.className = "si" + (i === state.active ? " on" : "");
      var c = mkCanvas(60, 60);
      var x = ctx2d(c);
      x.imageSmoothingQuality = "high";
      var side = Math.min(b.w, b.h);
      x.drawImage(state.img, b.x + (b.w - side) / 2, b.y + (b.h - side) / 2, side, side, 0, 0, 60, 60);
      d.appendChild(c);
      var t = document.createElement("div");
      t.className = "meta";
      t.innerHTML = '<b>' + (i + 1) + '</b><span>' + Math.round(b.w) + '×' + Math.round(b.h) + '</span>' +
        '<i>' + (b.dens > 0.5 ? "白文" : "朱文") + '</i>';
      d.appendChild(t);
      d.onclick = function () { selectSeal(i); };
      host.appendChild(d);
    });
    $("listhint").textContent = state.seals.length + " 枚";
    var dc = $("dcount"); if (dc) dc.textContent = state.seals.length + " 枚";
  }

  /* ============ 圖層選擇 ============ */
  function renderLayers() {
    var host = $("slayers"); host.innerHTML = "";
    var idx = window.GA_SHAPE_INDEX || [];
    var want = ["seal", "beishida", "shuowen-seal-kaiyuan", "liushuwenmai-xiaozhuan",
                "yunzhuan-duren", "grassseal", "clerical", "bronze", "oracle"];
    want.forEach(function (lid) {
      var it = idx.filter(function (x) { return x.id === lid; })[0];
      if (!it) return;
      var b = document.createElement("button");
      b.className = "lyr" + (state.layers.indexOf(lid) >= 0 ? " on" : "");
      b.innerHTML = '<i>' + (it.mono || "·") + '</i>' + esc(it.name || lid);
      b.onclick = function () {
        var k = state.layers.indexOf(lid);
        if (k >= 0) state.layers.splice(k, 1); else state.layers.push(lid);
        if (!state.layers.length) state.layers.push("seal");
        b.classList.toggle("on");
        searchAll();
      };
      host.appendChild(b);
    });
  }

  /* ============ 示範樣本 ============ */
  function renderSamples() {
    var host = $("samples"), arr = window.GA_SEAL_SAMPLES || [];
    host.innerHTML = "";
    if (!arr.length) { host.style.display = "none"; return; }
    arr.forEach(function (s) {
      var b = document.createElement("button");
      b.className = "samp";
      b.title = s.label;
      var im = document.createElement("img");
      im.src = s.png; im.alt = s.label;
      b.appendChild(im);
      b.onclick = function () {
        Array.prototype.forEach.call(host.children, function (c) { c.classList.remove("on"); });
        b.classList.add("on");
        $("srcname").textContent = s.label;
        setImage(s.png, s.label);
      };
      host.appendChild(b);
    });
  }

  /* ============ 綁定 ============ */
  function bindRange(id, vid, fmt) {
    var el = $(id), v = $(vid);
    var upd = function () { v.textContent = fmt ? fmt(+el.value) : el.value; };
    el.addEventListener("input", function () { upd(); if (state.img) detect(); });
    upd();
  }
  function bind() {
    bindRange("tol", "vtol");
    bindRange("sat", "vsat", function (x) { return (x / 100).toFixed(2); });
    bindRange("min", "vmin");
    bindRange("den", "vden", function (x) { return (x / 100).toFixed(2); });

    $("run").onclick = function () { detect(); };
    $("whole").onchange = function () { detect(); };
    $("showbox").onchange = function () { state.showBox = $("showbox").checked; layout(); };
    $("zoomin").onclick = function () { state.zoom = Math.min(8, state.zoom * 1.35); layout(); };
    $("zoomout").onclick = function () { state.zoom = Math.max(1, state.zoom / 1.35); layout(); };
    $("order").onchange = function () { state.order = $("order").value; if (state.cur) buildCells(); };
    $("autosplit").onchange = function () {
      state.autoSplit = $("autosplit").checked;
      if (state.cur) buildCells();
    };
    $("bpaste").onclick = function () {
      if (!navigator.clipboard || !navigator.clipboard.read) { toast("這個瀏覽器不支援讀剪貼簿", "err"); return; }
      navigator.clipboard.read().then(function (items) {
        for (var i = 0; i < items.length; i++) {
          var t = items[i].types.filter(function (x) { return x.indexOf("image/") === 0; })[0];
          if (t) {
            items[i].getType(t).then(function (blob) {
              var fr = new FileReader();
              fr.onload = function () { setImage(fr.result, "剪貼簿"); };
              fr.readAsDataURL(blob);
            });
            return;
          }
        }
        toast("剪貼簿裡沒有圖片", "err");
      }).catch(function () { toast("讀剪貼簿被拒絕了", "err"); });
    };
    $("file").onchange = function (e) {
      var f = e.target.files && e.target.files[0];
      if (!f) return;
      var fr = new FileReader();
      fr.onload = function () { setImage(fr.result, f.name); };
      fr.readAsDataURL(f);
    };
    var drop = $("drop");
    ["dragenter", "dragover"].forEach(function (ev) {
      drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.add("over"); });
    });
    ["dragleave", "drop"].forEach(function (ev) {
      drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.remove("over"); });
    });
    drop.addEventListener("drop", function (e) {
      var f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
      if (!f) return;
      var fr = new FileReader();
      fr.onload = function () { setImage(fr.result, f.name); };
      fr.readAsDataURL(f);
    });
    drop.addEventListener("click", function () { $("file").click(); });
    document.addEventListener("paste", function (e) {
      var items = e.clipboardData && e.clipboardData.items;
      if (!items) return;
      for (var i = 0; i < items.length; i++) {
        if (items[i].type.indexOf("image/") === 0) {
          var f = items[i].getAsFile();
          var fr = new FileReader();
          fr.onload = function () { setImage(fr.result, "剪貼簿"); };
          fr.readAsDataURL(f);
          return;
        }
      }
    });
    window.addEventListener("resize", function () { if (state.img) layout(); });
  }

  function boot() {
    renderLayers();
    renderSamples();
    bind();
    $("navstat").textContent = (window.GA_SHAPE_INDEX || []).reduce(function (a, s) { return a + s.n; }, 0).toLocaleString() + " 字形";
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();