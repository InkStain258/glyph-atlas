# 用 fontTools 直接统计每个字形的「有效墨迹面积」，找出仍然空白的字形
import sys
from fontTools.ttLib import TTFont
from fontTools.pens.areaPen import AreaPen
from fontTools.pens.boundsPen import BoundsPen

def report(path, chars):
    f = TTFont(path)
    cm = f.getBestCmap(); gs = f.getGlyphSet()
    out = []
    for ch in chars:
        gn = cm.get(ord(ch))
        if not gn:
            out.append((ch, None, None)); continue
        ap = AreaPen(gs); gs[gn].draw(ap)
        bp = BoundsPen(gs); gs[gn].draw(bp)
        out.append((ch, abs(ap.value), bp.bounds))
    print(path, "->")
    for ch, area, bb in out:
        flag = "BLANK" if (area is None or area < 1000) else "ok"
        print("   %s area=%s bbox=%s %s" % (ch, ("%.0f" % area) if area is not None else "-", bb, flag))

if __name__ == "__main__":
    report(sys.argv[1], sys.argv[2])
