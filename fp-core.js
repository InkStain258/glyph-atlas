/* 指纹核心（識印 · 歷代字形查詢平台）
   指纹口径唯一来源：shape.js（以形查字）与 seal.js（印章考据）共用本文件。
   ⚠ 这里的数学必须与 scripts/build_shape_index.py 逐位同构，改动会让全部离线索引失效。
   常量与 build_shape_index.py 一致：N=64, INNER=56, G=16。 */
(function () {
  "use strict";
  var N = 64, INNER = 56, G = 16;
  function clamp(v, a, b) { return v < a ? a : v > b ? b : v; }

  /* 四舍六入五取偶，对齐 Python round() */
  function rint(v) {
    var f = Math.floor(v), d = v - f;
    if (d > 0.5) return f + 1;
    if (d < 0.5) return f;
    return (f & 1) ? f + 1 : f;
  }

  /* 盒式重采样（逐输出像素按面积覆盖率加权平均），等价 PIL Image.BOX。
     不能用 canvas drawImage 的平滑缩小：Chrome 的高质量缩放不是盒式滤波，
     同一个字相似度会从 98% 掉到 88%。 */
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

  /* 掩膜 → 64×64 归一化（长边缩到 INNER=56，居中，y 不翻转：掩膜已是屏幕坐标） */
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

  /* 64×64 alpha → 146B 指纹：16×16 密度（4bit）+ 32 投影（4bit）+ 长宽比 + 墨量 */
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

  function bbox(m, W, H) {
    var x0 = W, y0 = H, x1 = -1, y1 = -1;
    for (var y = 0; y < H; y++) for (var x = 0; x < W; x++) if (m[y * W + x]) {
      if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y;
    }
    return x1 < 0 ? null : { x0: x0, y0: y0, x1: x1, y1: y1, w: x1 - x0 + 1, h: y1 - y0 + 1 };
  }

  /* 掩膜直出指纹（假设 m 已经是墨=1 的二值掩膜，且已裁到内容范围可选） */
  function fingerprint(m, W, H, useBBox) {
    var bb = bbox(m, W, H);
    if (!bb) return null;
    var alpha = normalizeMask(m, W, H, bb);
    var d = encode(alpha, bb.w, bb.h);
    d.bb = bb; d.W = W; d.H = H; d.mask = m;
    return d;
  }

  window.GA_FP = {
    N: N, INNER: INNER, G: G,
    clamp: clamp, rint: rint, boxResize: boxResize,
    normalizeMask: normalizeMask, encode: encode, bbox: bbox, fingerprint: fingerprint
  };
})();
