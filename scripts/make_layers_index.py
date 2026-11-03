# -*- coding: utf-8 -*-
"""生成 data/layers-ancient.json（古文字 7 层的元数据）。

早期是直接沿用 build_glyph_fonts.py 的分批产物，分批跑会互相覆盖；
这里改成从最终产物反推：字数/字形数从 data/meta/<layer>.json 数，异写数从 TTF 的 GSUB 数。
这样无论分几批编译，重新跑一遍本脚本就能得到一致的索引。
"""
import json
import os

from fontTools.ttLib import TTFont

META = {
    "oracle": dict(name_zh="甲骨文", era="商", era_order=1, license="CC0-1.0 / CC BY 4.0",
                   note="漢典拓片摹本为主；JGW 参数化矢量 1,203 条为 CC BY 4.0，需署名+注明修改"),
    "bronze": dict(name_zh="金文", era="西周—戰國", era_order=2, license="CC0-1.0",
                   note="器铭摹本，出处记为「器名 集成编号 分期」"),
    "chu": dict(name_zh="楚文字", era="戰國·楚", era_order=3, license="CC0-1.0",
                note="楚簡/帛書字形，出处记为「簡號 / 合編號 / 組」"),
    "qinwenzi": dict(name_zh="秦系簡牘", era="戰國末—秦", era_order=4, license="CC0-1.0",
                     note="睡虎地等秦簡字形"),
    "chuanchao": dict(name_zh="傳抄古文", era="漢—宋（傳抄）", era_order=5, license="CC0-1.0",
                      note="《汗簡》《古文四聲韻》一系传抄字形，时代标的是传抄年代非原始年代"),
    "seal": dict(name_zh="小篆", era="秦—漢", era_order=6, license="CC0-1.0",
                 note="《说文》刻本系统，题记带部次与形制（正篆/古文/籀文/或体）"),
    "clerical": dict(name_zh="隸書", era="西漢—東漢", era_order=7, license="CC0-1.0",
                     note="漢典书法实例 + 中研院小學堂隸變庫摹本，含西漢/東漢年代与出处"),
}


def count_gsub(ttf):
    f = TTFont(ttf)
    n = 0
    if "GSUB" in f:
        for fr in f["GSUB"].table.FeatureList.FeatureRecord:
            if fr.FeatureTag.startswith("ss"):
                n += len(fr.Feature.LookupListIndex)
    # 直接数替代字形更准：glyph 名里带 .v
    n = sum(1 for g in f.getGlyphOrder() if ".v" in g)
    f.close()
    return n


def main():
    out = []
    for lid, m in META.items():
        mp = f"data/meta/{lid}.json"
        ttf = f"fonts/ancient/{lid}/glyphs.ttf"
        if not os.path.exists(ttf):
            ttf = f"fonts/gen/{lid}.ttf"
        if not (os.path.exists(mp) and os.path.exists(ttf)):
            print(f"skip {lid}")
            continue
        meta = json.load(open(mp, encoding="utf-8"))
        glyphs = sum(len(v) for v in meta.values())
        variants = count_gsub(ttf)
        rec = dict(id=lid, **m)
        rec.update(kind="glyph-svg", chars=len(meta), glyphs=glyphs, variants=variants)
        out.append(rec)
        print(f"{lid:10s} chars={len(meta):6d} glyphs={glyphs:6d} variants={variants:5d}")
    out.sort(key=lambda r: r["era_order"])
    json.dump(out, open("data/layers-ancient.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"wrote data/layers-ancient.json ({len(out)} layers)")


if __name__ == "__main__":
    main()