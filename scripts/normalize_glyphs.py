# -*- coding: utf-8 -*-
"""逐字归一化：把各古文字层的字形摆到同一个视觉框里。

为什么需要：各来源的字体设计框不一样——
  - hanzi-glyphs-svg 编译的七层：build_glyph_fonts.py 已按「长边缩到 860、中心放 (500,380)」
  - 开元小篆：上游 viewBox 0 -880 1000 1000，字形水平靠左、竖直居中在 500
  - 北師大說文小篆：upem 1024、ascent 820，字形中心在 513/306，整体偏大 14%
不归一化的话，同一字在不同层里一个大一个小、一个高一个低，没法比对。

做法：每个字形做一次刚性变换（等比缩放 + 平移），不改字形结构：
  长边 → upem * long_ratio（默认 0.86，对应 1000 upem 下的 860）
  包围盒中心 → (upem*0.5, upem*0.38)
并把 hhea / OS/2 的竖直度量统一成 ascent 0.88*upem / descent 0.12*upem，
让各层的基线落在同一位置。

用法：
    python -X utf8 scripts/normalize_glyphs.py in.ttf out.ttf [--long-ratio 0.86]
"""
import argparse
import os

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont


def glyph_bounds(glyphset, name):
    bp = BoundsPen(glyphset)
    glyphset[name].draw(bp)
    return bp.bounds


def normalize(font, long_ratio=0.86, cx_ratio=0.5, cy_ratio=0.38, verbose=False):
    upem = font["head"].unitsPerEm
    asc = round(upem * 0.88)
    desc = -round(upem * 0.12)
    font["hhea"].ascent = asc
    font["hhea"].descent = desc
    font["hhea"].lineGap = 0
    if "OS/2" in font:
        os2 = font["OS/2"]
        os2.sTypoAscender = asc
        os2.sTypoDescender = desc
        os2.sTypoLineGap = 0
        os2.usWinAscent = asc
        os2.usWinDescent = -desc

    glyf = font["glyf"]
    glyphset = font.getGlyphSet()
    order = font.getGlyphOrder()

    bounds = {}
    for name in order:
        if glyf[name].isComposite():
            continue
        bounds[name] = glyph_bounds(glyphset, name)

    cx = upem * cx_ratio
    cy = upem * cy_ratio
    target = upem * long_ratio
    moved = 0
    for name in order:
        b = bounds.get(name)
        if not b:
            continue
        x0, y0, x1, y1 = b
        w, h = x1 - x0, y1 - y0
        span = max(w, h)
        if span <= 0:
            continue
        s = target / span
        mx, my = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        pen = TTGlyphPen(glyphset)
        glyphset[name].draw(TransformPen(pen, (s, 0, 0, s, cx - mx * s, cy - my * s)))
        g = pen.glyph()
        glyf[name] = g
        moved += 1

    # 水平推进统一成 upem，字面居中：浏览器按 advance 居中时不会偏
    hmtx = font["hmtx"]
    for name in order:
        adv, lsb = hmtx[name]
        b = glyph_bounds(font.getGlyphSet(), name)
        lsb = int(round(b[0])) if b else 0
        hmtx[name] = (upem, lsb)

    for name in order:
        if glyf[name].numberOfContours != 0:
            glyf[name].recalcBounds(glyf)

    if verbose:
        print("normalized %d glyphs, upem=%d, asc/desc=%d/%d" % (moved, upem, asc, desc))
    return moved


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--long-ratio", type=float, default=0.86)
    args = ap.parse_args()
    font = TTFont(args.src)
    normalize(font, long_ratio=args.long_ratio, verbose=True)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    font.save(args.out)
    print("saved", args.out, "%.2f MB" % (os.path.getsize(args.out) / 1048576))


if __name__ == "__main__":
    main()