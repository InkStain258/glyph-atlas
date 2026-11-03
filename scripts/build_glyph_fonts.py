#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_glyph_fonts.py — 把 hanzi-glyphs-svg 的古文字形 SVG 编译成可用的 Web 字体。

为什么要这一步：
  hanzi-glyphs-svg 只提供逐字 SVG（18.7 万条），没有字体文件。要在纯前端工具里
  「一个字同屏看十几个朝代」，逐字发 SVG 请求不可行（文件数太多、无法预取）。
  编译成字体后，浏览器一次加载一个书体文件即可，且能享用浏览器的字形缓存。

一个难点：同一个字在一个书体里有多个写法（金文 26 个时代、楚简来自不同出土文献）。
字体里一个码位只能有一个默认字形，所以：
  - 默认字形 = 该字在该层的第一条（index.csv 顺序，作者已按时代/文献排好）
  - 其余写法挂到 GSUB 的 ss01..ss09 —— 前端用 font-feature-settings 切换，
    既能看「演变链」，又不必为每种写法单独出一个字体文件。

用法：
  python scripts/build_glyph_fonts.py --src .src/hanzi-glyphs-svg-main
  python scripts/build_glyph_fonts.py --src ... --layers seal oracle --limit 300
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from collections import OrderedDict, defaultdict

from fontTools.pens.boundsPen import ControlBoundsPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.svgLib.path import parse_path

UPEM = 1000
MAX_VARIANTS = 9          # ss01..ss09
DEFAULT_ADVANCE = 1000

# 只编译这些层（现代六层直接用真实 OFL 字体，没必要从 SVG 重建）
ANCIENT_LAYERS = ["oracle", "bronze", "seal", "clerical", "chu", "chuanchao", "qinwenzi"]

LAYER_META = {
    "oracle":    dict(name_zh="甲骨文",   era="商",                 era_order=1,
                      license="CC0-1.0 (漢典摹本 10,213) / CC BY 4.0 (JGW 1,203)",
                      note="字形来自汉典拓片摹本与 JGW 参数化矢量数据集"),
    "bronze":    dict(name_zh="金文",     era="商—戰國",            era_order=2,
                      license="CC0-1.0",
                      note="青铜器拓片摹本，题记带器名/集成号/时代"),
    "chu":       dict(name_zh="楚文字",   era="戰國·楚",            era_order=3,
                      license="CC0-1.0",
                      note="楚系简帛，题记带出土文献与简号"),
    "qinwenzi":  dict(name_zh="秦系簡牘", era="戰國·秦—秦",         era_order=4,
                      license="CC0-1.0",
                      note="睡虎地秦简一路的简牍文字"),
    "chuanchao": dict(name_zh="傳抄古文", era="漢以後傳抄",         era_order=5,
                      license="CC0-1.0",
                      note="历代辗转抄写的先秦文字（《汗简》《古文四声韵》一路）"),
    "seal":      dict(name_zh="小篆",     era="秦—漢",              era_order=6,
                      license="CC0-1.0",
                      note="《说文》刻本系统，题记带部次与形制（正篆/古文/籀文/或体）"),
    "clerical":  dict(name_zh="隶书",     era="戰國末—東漢",        era_order=7,
                      license="CC0-1.0",
                      note="汉碑、汉印、秦汉简牍"),
}

RE_SVG_TAG = re.compile(r"<svg\b[^>]*>", re.I)
RE_VIEWBOX = re.compile(r'viewBox\s*=\s*["\']\s*([-\d.]+)[,\s]+([-\d.]+)[,\s]+([-\d.]+)[,\s]+([-\d.]+)', re.I)
RE_PATH_D = re.compile(r'<path\b[^>]*?\bd\s*=\s*"([^"]+)"', re.I | re.S)
RE_TRANSFORM = re.compile(r'transform\s*=\s*["\']', re.I)


class AutoClosePen:
    """把未闭合的轮廓补上 closePath —— TrueType 的轮廓必须是闭合的。"""

    def __init__(self, out):
        self.out = out
        self.open = False

    def moveTo(self, pt):
        if self.open:
            self.out.closePath()
        self.open = True
        self.out.moveTo(pt)

    def lineTo(self, pt):
        self.out.lineTo(pt)

    def curveTo(self, *pts):
        self.out.curveTo(*pts)

    def qCurveTo(self, *pts):
        self.out.qCurveTo(*pts)

    def closePath(self):
        if self.open:
            self.out.closePath()
            self.open = False

    def endPath(self):
        if self.open:
            self.out.closePath()
            self.open = False

    def addComponent(self, *a, **k):
        pass


class MinPathPen:
    """丢弃「点数不足 3 的轮廓」。

    上游 SVG 里混着一些退化记录（例如一道 2 点的折线），转成 TrueType 轮廓后
    面积为零，渲染出来是一片空白。更糟的是它还会被当成「主形」写进 cmap，
    让整个字看起来是空的（字形其实躺在 ss01 之后）。这里按子路径缓冲，
    点数够才转发给 TTGlyphPen。
    """

    def __init__(self, out):
        self.out = out
        self.buf = []
        self.n = 0

    def moveTo(self, pt):
        self.flush()
        self.buf = [("m", pt)]
        self.n = 1

    def lineTo(self, pt):
        self.buf.append(("l", pt))
        self.n += 1

    def curveTo(self, *pts):
        self.buf.append(("c", pts))
        self.n += 1

    def qCurveTo(self, *pts):
        self.buf.append(("q", pts))
        self.n += 1

    def closePath(self):
        self.buf.append(("z", None))
        self.flush()

    def endPath(self):
        self.flush()

    def flush(self):
        if self.n >= 3:
            for op, arg in self.buf:
                if op == "m":
                    self.out.moveTo(arg)
                elif op == "l":
                    self.out.lineTo(arg)
                elif op == "c":
                    self.out.curveTo(*arg)
                elif op == "q":
                    self.out.qCurveTo(*arg)
                elif op == "z":
                    self.out.closePath()
        self.buf = []
        self.n = 0

    def addComponent(self, *a, **k):
        pass


def read_svg(path):
    """返回 [path d 字符串]。"""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            txt = f.read()
    except OSError:
        return []
    return RE_PATH_D.findall(txt)


def svg_to_ttglyph(d_list, target=860.0, max_err=0.55):
    """把 SVG 轮廓转成 TTGlyph。

    关键：这些 SVG 的 viewBox 极不统一——有的 0 0 400 400，有的 0 0 17 8，
    有的大量是贴着字形的紧包围盒。若按 viewBox 缩放，同一个字会大小差几倍。
    所以这里一律**按字形自身的包围盒**做归一：长边缩到 target（1000 单位里的
    860，留 70 边距），居中放进字身框。这样 18 万个来自不同拓片/摹本的字形
    在同一个字体里视觉大小一致。
    """
    recs = []
    bp = ControlBoundsPen(None)
    for d in d_list:
        if not d.strip():
            continue
        try:
            rec = DecomposingRecordingPen(None)
            parse_path(d, rec)
            if not rec.value:
                continue
            rec.replay(bp)
            recs.append(rec)
        except Exception:
            continue
    if not recs or not bp.bounds:
        return None
    x0, y0, x1, y1 = bp.bounds
    w, h = x1 - x0, y1 - y0
    if w <= 1e-6 or h <= 1e-6:
        return None
    s = target / max(w, h)
    # x: 居中到 [0,1000]；y: SVG 向下、字体向上，翻转后把字形垂直中心放到 380
    cx = UPEM / 2.0
    cy = 380.0
    tf = (s, 0.0, 0.0, -s, cx - (x0 + x1) / 2.0 * s, cy + (y0 + y1) / 2.0 * s)
    ttpen = TTGlyphPen(None)
    mpp = MinPathPen(ttpen)
    for rec in recs:
        acp = AutoClosePen(mpp)
        cu2qu = Cu2QuPen(acp, max_err, reverse_direction=True)
        rec.replay(TransformPen(cu2qu, tf))
    acp.closePath()
    try:
        g = ttpen.glyph()
    except Exception:
        return None
    # 一个轮廓都不剩，说明这一条记录没有可用字形
    if getattr(g, "numberOfContours", 0) <= 0:
        return None
    return g


def load_layer(src, layer, limit=None, verbose=True):
    """读 index.csv，返回 OrderedDict: char -> [ (period, source, file, sha) ... ]"""
    ldir = os.path.join(src, "glyphs", layer)
    idx = os.path.join(ldir, "index.csv")
    if not os.path.exists(idx):
        return None, ldir
    groups = OrderedDict()
    rows = 0
    skipped = 0
    with open(idx, "r", encoding="utf-8-sig", newline="") as f:
        rd = csv.DictReader(f)
        for row in rd:
            ch = (row.get("modern_char") or "").strip()
            fn = (row.get("file") or "").strip()
            if len(ch) != 1 or not fn:
                skipped += 1
                continue
            fp = os.path.join(ldir, fn)
            if not os.path.exists(fp):
                skipped += 1
                continue
            groups.setdefault(ch, []).append(
                (row.get("period") or "", row.get("source_book") or row.get("variant") or "", fn,
                 row.get("sha256") or ""))
            rows += 1
            if limit and len(groups) >= limit:
                break
    if verbose:
        print(f"  [{layer}] rows={rows} chars={len(groups)} skipped={skipped}", flush=True)
    return groups, ldir


def build_font(layer, groups, ldir, out_ttf, max_variants=MAX_VARIANTS, verbose=True):
    t0 = time.time()
    glyph_order = [".notdef"]
    glyphs = {}
    metrics = {}
    cmap = {}
    feature_map = defaultdict(list)   # ssNN -> [(base, alt)]
    char_meta = {}
    stats = dict(chars=0, glyphs=0, variants=0, empty=0, transform_warn=0)

    # .notdef：一个空心方框
    ttpen = TTGlyphPen(None)
    ttpen.moveTo((80, 0))
    ttpen.lineTo((920, 0))
    ttpen.lineTo((920, 880))
    ttpen.lineTo((80, 880))
    ttpen.closePath()
    ttpen.moveTo((150, 80))
    ttpen.lineTo((150, 800))
    ttpen.lineTo((850, 800))
    ttpen.lineTo((850, 80))
    ttpen.closePath()
    glyphs[".notdef"] = ttpen.glyph()
    metrics[".notdef"] = (DEFAULT_ADVANCE, 80)

    for ch, items in groups.items():
        cp = ord(ch)
        if cp > 0x10FFFF:
            continue
        seen = set()
        picked = []
        for it in items:
            key = it[3] or (it[0], it[1], it[2])
            if key in seen:
                continue
            seen.add(key)
            picked.append(it)
            if len(picked) >= max_variants:
                break
        built = []
        for period, source, fn, sha in picked:
            fp = os.path.join(ldir, fn)
            ds = read_svg(fp)
            if not ds:
                stats["empty"] += 1
                continue
            g = svg_to_ttglyph(ds)
            if g is None:
                stats["empty"] += 1
                continue
            try:
                g.recalcBounds(None)
                xmin = g.xMin
            except Exception:
                stats["empty"] += 1
                continue
            built.append((g, xmin, period, source))
        if not built:
            continue

        base_name = "uni%04X" % cp if cp <= 0xFFFF else "u%05X" % cp
        g0, xmin0, _, _ = built[0]
        glyph_order.append(base_name)
        glyphs[base_name] = g0
        metrics[base_name] = (DEFAULT_ADVANCE, xmin0)
        cmap[cp] = base_name
        stats["chars"] += 1
        stats["glyphs"] += 1

        weights = []
        for i, (g, xmin, period, source) in enumerate(built[1:], start=2):
            if i - 1 > 9:
                break
            alt = "%s.v%d" % (base_name, i)
            glyph_order.append(alt)
            glyphs[alt] = g
            metrics[alt] = (DEFAULT_ADVANCE, xmin)
            feature_map["ss%02d" % (i - 1)].append((base_name, alt))
            stats["glyphs"] += 1
            stats["variants"] += 1
            weights.append([period, source])

        char_meta[ch] = [[built[0][2], built[0][3]]] + weights

    if verbose:
        print(f"  [{layer}] built {stats['chars']} chars / {stats['glyphs']} glyphs "
              f"({stats['variants']} variants, {stats['empty']} empty) in {time.time()-t0:.1f}s", flush=True)

    from fontTools.fontBuilder import FontBuilder

    fb = FontBuilder(UPEM, isTTF=True)
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=880, descent=-120)
    meta = LAYER_META.get(layer, {})
    family = "GlyphAtlas-%s" % layer
    fb.setupNameTable({
        "familyName": family,
        "styleName": "Regular",
        "uniqueFontIdentifier": "%s-Regular" % family,
        "fullName": "%s Regular" % family,
        "psName": "%s-Regular" % family,
        "version": "Version 1.000",
        "copyright": "Derived from hanzi-glyphs-svg. Per-layer licence: %s" % meta.get("license", ""),
        "licenseDescription": meta.get("license", ""),
        "licenseInfoURL": "https://github.com/zhouyongh/hanzi-glyphs-svg",
    })
    fb.setupOS2(sTypoAscender=880, sTypoDescender=-120, sTypoLineGap=0,
                usWinAscent=880, usWinDescent=200,
                sxHeight=500, sCapHeight=700, achVendID="GLYP",
                fsType=0, usWeightClass=400, usWidthClass=5,
                panose=dict(bFamilyType=5, bSerifStyle=2, bWeight=5, bProportion=3,
                            bContrast=0, bStrokeVariation=0, bArmStyle=0,
                            bLetterForm=0, bMidline=0, bXHeight=0))
    fb.setupPost()

    if feature_map:
        fea = ["languagesystem DFLT dflt;", "languagesystem latn dflt;", "languagesystem hani dflt;"]
        for feat, pairs in sorted(feature_map.items()):
            fea.append("feature %s {" % feat)
            fea.append("  script DFLT;")
            for base, alt in pairs:
                fea.append("    sub %s by %s;" % (base, alt))
            fea.append("} %s;" % feat)
        fea_text = "\n".join(fea) + "\n"
        try:
            from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
            addOpenTypeFeaturesFromString(fb.font, fea_text)
            if verbose:
                print(f"  [{layer}] GSUB ok: {len(feature_map)} features, "
                      f"{sum(len(v) for v in feature_map.values())} subs", flush=True)
        except Exception as e:
            print(f"  [{layer}] !! GSUB failed, variants only reachable by glyph name: {e}", flush=True)

    os.makedirs(os.path.dirname(out_ttf), exist_ok=True)
    fb.save(out_ttf)
    stats["ttf_bytes"] = os.path.getsize(out_ttf)

    # WOFF2
    woff2_path = os.path.splitext(out_ttf)[0] + ".woff2"
    try:
        from fontTools.ttLib import TTFont
        f = TTFont(out_ttf, recalcBBoxes=False)
        f.flavor = "woff2"
        f.save(woff2_path)
        stats["woff2_bytes"] = os.path.getsize(woff2_path)
    except Exception as e:
        print(f"  [{layer}] woff2 failed: {e}", flush=True)
        stats["woff2_bytes"] = 0

    return stats, char_meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="hanzi-glyphs-svg 解压后的根目录")
    ap.add_argument("--out", default="fonts/gen", help="字体输出目录")
    ap.add_argument("--data", default="data", help="元数据输出目录")
    ap.add_argument("--layers", nargs="*", default=ANCIENT_LAYERS)
    ap.add_argument("--limit", type=int, default=None, help="每层最多处理多少个字（调试用）")
    args = ap.parse_args()

    os.makedirs(args.data, exist_ok=True)
    os.makedirs(os.path.join(args.data, "meta"), exist_ok=True)

    layers_out = []
    for layer in args.layers:
        print(f"== {layer} ==", flush=True)
        groups, ldir = load_layer(args.src, layer, args.limit)
        if not groups:
            print(f"  skip {layer}: no data", flush=True)
            continue
        ttf = os.path.join(args.out, "%s.ttf" % layer)
        stats, char_meta = build_font(layer, groups, ldir, ttf)
        meta = LAYER_META.get(layer, {})
        rec = dict(id=layer, **meta)
        rec.update(stats)
        rec["font_ttf"] = ttf.replace("\\", "/")
        rec["font_woff2"] = ttf.replace("\\", "/")[:-4] + ".woff2"
        rec["charset"] = "".join(sorted(char_meta.keys(), key=ord))
        layers_out.append(rec)
        mpath = os.path.join(args.data, "meta", "%s.json" % layer)
        with open(mpath, "w", encoding="utf-8") as f:
            json.dump(char_meta, f, ensure_ascii=False, separators=(",", ":"))
        print("  meta -> %s (%.1f KB)" % (mpath, os.path.getsize(mpath) / 1024), flush=True)

    lpath = os.path.join(args.data, "layers.json")
    with open(lpath, "w", encoding="utf-8") as f:
        json.dump(layers_out, f, ensure_ascii=False, indent=1)
    print("wrote", lpath, flush=True)

    print("\n== summary ==")
    tot_ttf = tot_w2 = 0
    for r in layers_out:
        tot_ttf += r.get("ttf_bytes", 0)
        tot_w2 += r.get("woff2_bytes", 0)
        print("%-12s %6d chars %7d glyphs  ttf %6.1f MB  woff2 %6.1f MB" % (
            r["id"], r.get("chars", 0), r.get("glyphs", 0),
            r.get("ttf_bytes", 0) / 1e6, r.get("woff2_bytes", 0) / 1e6))
    print("%-12s %53s ttf %6.1f MB  woff2 %6.1f MB" % ("TOTAL", "", tot_ttf / 1e6, tot_w2 / 1e6))


if __name__ == "__main__":
    main()
