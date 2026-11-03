# -*- coding: utf-8 -*-
"""把 fonts/modern/<id>/original.ttf 收窄成 GBK 子集，写到 fonts/modern/<id>/subset.ttf。

为什么收窄到 GBK：
- 现代字体动辄 20~26 MB，全量切片会让分片数翻倍，而古籍标注真正要查的是
  古文字层已经覆盖的形；现代层的价值是“同一字在不同书体下的样子”。
- GBK 21,791 字已含 GB2312 6763 与大部分常用繁体，够用。
- 极罕见的 Ext-B 字在古文字层里有，现代层没有就如实显示“无”。

OFL 1.1 §3：修改版不得继续使用保留字体名 → 子集统一改名为 `GA-<id> Subset`，
版权行（nameID 0）与许可声明（13/14）原样保留。

用法：
    python scripts/build_modern_fonts.py                # 全部 shipped 字体
    python scripts/build_modern_fonts.py --only lxgwwenkai zhuque
"""
import argparse
import json
import os

from fontTools.ttLib import TTFont
from fontTools import subset
from normalize_glyphs import normalize

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODERN = os.path.join(ROOT, "fonts", "modern")
INCOMING = os.path.join(ROOT, "fonts", "incoming")
CATALOG = os.path.join(ROOT, "data", "font-catalog.json")
OUT = os.path.join(ROOT, "data", "layers-modern.json")

# 侧栏分组：古文字层由 kind 判定；现代层按「刻本源流 / 现代字库」两档摆
GROUP = {
    "shuowen-seal-kaiyuan": "ancient",  # 說文小篆：归「古文字·字形源」，不摆进现代字库
    "zenoldmincho": "print",    # 江户–明治老明朝复刻
    "kaiseitokumin": "print",   # 明治活字复刻（古书籍明朝）
    "newtegomin": "print",      # 明治木活字复刻
    "yujisyuku": "print",       # 毛笔楷 / 写经风
    "grassseal": "print",       # 小篆复刻
    "iansui": "print",          # 台繁手写楷
}

# 不进 web 的层：hanamin-b 在 GBK 范围内只有 6 个字，字形全部集中在 Ext-B，
# 独立成层只会让侧栏多一个永远空白的开关；字库本身仍保留在 fonts/ 与版权页。
SKIP_WEB = {"hanamin-b": "GBK 内仅 6 字，字形集中在 Ext-B"}

# 古文字层的时代序（1–7 为 hanzi-glyphs-svg 七层，6.5/6.6 为两款说文小篆字库）
ERA_ORDER = {"beishida": 6.5, "shuowen-seal-kaiyuan": 6.6}

# 需要逐字归一的层：上游设计框与 hanzi-glyphs-svg 七层不一致
NORMALIZE = {"shuowen-seal-kaiyuan"}

# 侧栏时代一行放不下长句，这里给短写
ERA_SHORT = {"shuowen-seal-kaiyuan": "東漢·《說文解字》清刻本"}

# 侧栏短名：上游全名太长，中文界面里会挤成一坨
SHORT = {
    "shuowen-seal-kaiyuan": "開元小篆",
    "grassseal": "草篆", "zenoldmincho": "禅老明朝", "newtegomin": "新泰戈明",
    "iansui": "芫荽", "kaiseitokumin": "古书籍明朝", "yujisyuku": "悠司肅",
    "babelstone-han": "巴别石汉字", "hanamin-a": "花园明朝A",
    "zcoolxiaowei": "站酷小薇体", "chiron-sung-hk": "昭源宋体",
    "fandol-fang": "Fandol 仿宋", "fandol-hei": "Fandol 黑",
    "fandol-kai": "Fandol 楷", "fandol-song": "Fandol 宋", "kleeone": "Klee One",
}


def gbk_chars():
    out = []
    for b1 in range(0x81, 0xFF):
        for b2 in range(0x40, 0xFF):
            try:
                ch = bytes([b1, b2]).decode("gbk")
            except UnicodeDecodeError:
                continue
            if len(ch) == 1:
                out.append(ch)
    return out


def find_original(fid):
    for p in (os.path.join(MODERN, fid, "original.ttf"),
              os.path.join(MODERN, fid, "original.otf"),
              os.path.join(INCOMING, fid, "original.ttf"),
              os.path.join(INCOMING, fid, "original.otf")):
        if os.path.exists(p):
            return p
    # fonts/incoming/<id>/ 下可能直接放着上游文件名（如 BabelStoneHan.ttf）
    d = os.path.join(INCOMING, fid)
    if os.path.isdir(d):
        for fn in sorted(os.listdir(d)):
            if fn.lower().endswith((".ttf", ".otf")) and not fn.startswith("subset"):
                return os.path.join(d, fn)
    return None


def rename_subset(font, fid):
    new = "GA-%s Subset" % fid
    for rec in font["name"].names:
        if rec.nameID in (1, 3, 4, 6, 16, 17, 18, 20, 21):
            try:
                rec.string = new
            except Exception:
                pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None)
    args = ap.parse_args()

    cat = json.load(open(CATALOG, encoding="utf-8"))
    gbk = gbk_chars()
    print(f"GBK baseline: {len(gbk)} chars")
    os.makedirs(MODERN, exist_ok=True)

    old = {}
    if os.path.exists(OUT):
        for L in json.load(open(OUT, encoding="utf-8")):
            old[L["id"]] = L
    layers = dict(old)

    for f in cat["fonts"]:
        if f.get("status") != "shipped":
            continue
        fid = f["id"]
        if args.only and fid not in args.only:
            continue
        if fid in SKIP_WEB:
            print(f"{fid:16s} skip: {SKIP_WEB[fid]}")
            continue
        src = find_original(fid)
        if not src:
            print(f"!! missing original for {fid}")
            continue
        font = TTFont(src)
        have = font.getBestCmap()
        wanted = [ord(c) for c in gbk if ord(c) in have]
        print(f"{fid:16s} cmap={len(have):6d} keep={len(wanted):6d}", end="  ")

        opts = subset.Options()
        opts.layout_features = ["*"]
        opts.name_IDs = ["*"]
        opts.hinting = False
        opts.drop_tables = ["DSIG"]
        sub = subset.Subsetter(options=opts)
        sub.populate(unicodes=wanted)
        sub.subset(font)
        if fid in NORMALIZE:
            n = normalize(font)
            print(f"norm {n}g", end="  ")
        rename_subset(font, fid)

        dst_dir = os.path.join(MODERN, fid)
        os.makedirs(dst_dir, exist_ok=True)
        out = os.path.join(dst_dir, "subset.ttf")
        font.flavor = None
        font.save(out)
        font.close()
        print(f"-> {os.path.getsize(out)/1048576:.2f} MB")

        p = old.get(fid, {})
        p.update({
            "id": fid,
            "name_zh": SHORT.get(fid, f.get("name_zh")),
            "era": ERA_SHORT.get(fid, f.get("era", "")),
            "era_order": ERA_ORDER.get(fid, 90),
            "style": f.get("style", ""),
            "style_detail": f.get("style_detail", ""),
            "license": f.get("license_spdx", ""),
            "license_url": f.get("license_url", ""),
            "source_url": f.get("source_url", ""),
            "kind": "modern-font",
            "group": GROUP.get(fid, "modern"),
            "note": f.get("encoding_note", ""),
            "chars": len(wanted),
            "glyphs": len(wanted),
            "variants": 0,
        })
        layers[fid] = p

    out_layers = [layers[k] for k in sorted(layers, key=lambda k: k)]
    json.dump(out_layers, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"wrote {OUT} ({len(out_layers)} layers)")


if __name__ == "__main__":
    main()