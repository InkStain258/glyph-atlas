# -*- coding: utf-8 -*-
"""把 fonts/gen/<layer>.ttf 切成按需懒加载的 WOFF2 分片，并生成前端数据与 CSS。

为什么切片
----------
18 个层合计 woff2 约 80 MB，一次性加载不可行。用 @font-face + unicode-range
把每层切成若干块，浏览器只会下载「页面上真的用到的字」所在的块。
实测首屏一个字通常只触发 1~2 块 / 层。

分片顺序
--------
先把 GB2312 一级字（3755）排在前，再二级字，最后其余字按码位排序 ——
常用字落在最前面的块里，冷僻字落在后面的块里。

按「估算字节预算」切而不是按字数切：不同层单字平均字节差 3 倍
（甲骨 >1500B，小篆 ~550B），按字数切会让甲骨的分片大 3 倍。

输出（全部可用 file:// 直接打开，不需要 web server）
--------
web/css/<layer>.css        @font-face + unicode-range
web/fonts/<layer>-<n>.woff2
web/data/layers.js         window.GA_LAYERS
web/data/variants.js       window.GA_VARIANTS
web/data/meta/<layer>.js   window.GA_META['<layer>']
"""
import argparse
import json
import os

from fontTools.ttLib import TTFont
from fontTools import subset


def gb2312_lists():
    l1, l2 = [], []
    for b1 in range(0xB0, 0xF8):
        for b2 in range(0xA1, 0xFF):
            try:
                ch = bytes([b1, b2]).decode("gb2312")
            except UnicodeDecodeError:
                continue
            (l1 if b1 <= 0xD7 else l2).append(ch)
    return l1, l2


def ranges_from_sorted(cps):
    out = []
    for cp in cps:
        if out and cp == out[-1][1] + 1:
            out[-1][1] = cp
        else:
            out.append([cp, cp])
    return out


def css_unicode_range(ranges):
    parts = []
    for a, b in ranges:
        parts.append(f"U+{a:X}" if a == b else f"U+{a:X}-{b:X}")
    return ",".join(parts)


def plan_shards(ttf_path, budget_bytes=280_000, min_chars=48):
    font = TTFont(ttf_path)
    cmap = set(font.getBestCmap().keys())
    font.close()
    n = len(cmap)
    size = os.path.getsize(ttf_path)
    avg = max(1, size // max(1, n))
    per_shard = max(min_chars, budget_bytes // avg)

    l1, l2 = gb2312_lists()
    ordered, seen = [], set()
    for ch in l1 + l2:
        cp = ord(ch)
        if cp in cmap and cp not in seen:
            ordered.append(cp)
            seen.add(cp)
    for cp in sorted(cmap):
        if cp not in seen:
            ordered.append(cp)
            seen.add(cp)

    shards = [ordered[i:i + per_shard] for i in range(0, len(ordered), per_shard)]
    return shards, avg, size


def js_assign(expr, obj, path):
    """写 `window.<expr>=<json>`；expr 必须是合法的 JS 属性表达式。"""
    with open(path, "w", encoding="utf-8") as f:
        f.write("window." + expr + "=")
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")


def js_meta(lid, obj, path):
    """元数据单独写：不能拼成 window.(...)['x']，那样是语法错误；也统一由 make_meta_js.py 负责。"""
    with open(path, "w", encoding="utf-8") as f:
        f.write("window.GA_META=window.GA_META||{};\n")
        f.write("window.GA_META[%s]=%s;\n" % (json.dumps(lid),
                                              json.dumps(obj, ensure_ascii=False,
                                                         separators=(",", ":"))))


def resolve_font(lid, root):
    """字体文件位置：古文字在 fonts/ancient/<id>/glyphs.ttf，现代在 fonts/modern/<id>/subset.ttf。"""
    cands = []
    if root:
        cands += [os.path.join(root, lid + ".ttf"), os.path.join(root, lid, "glyphs.ttf"),
                  os.path.join(root, lid, "subset.ttf")]
    cands += [os.path.join("fonts", "ancient", lid, "glyphs.ttf"),
              os.path.join("fonts", "modern", lid, "subset.ttf")]
    for p in cands:
        if os.path.exists(p):
            return p
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fonts", default="", help="字体根目录；留空则按 fonts/ancient/<id>/glyphs.ttf、fonts/modern/<id>/subset.ttf 查找")
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="web")
    ap.add_argument("--budget", type=int, default=300_000)
    ap.add_argument("--only", default="", help="逗号分隔的层 id，只处理这些层并与已有产物合并")
    args = ap.parse_args()

    layers = []
    for name in ("layers-ancient.json", "layers-modern.json"):
        p = os.path.join(args.data, name)
        if os.path.exists(p):
            layers.extend(json.load(open(p, encoding="utf-8")))

    only = [x for x in args.only.split(",") if x]
    if only:
        layers = [l for l in layers if l["id"] in only]
        if not layers:
            raise SystemExit(f"--only {args.only} 没匹配到任何层")

    font_dir = os.path.join(args.out, "fonts")
    css_dir = os.path.join(args.out, "css")
    data_dir = os.path.join(args.out, "data")
    meta_dir = os.path.join(data_dir, "meta")
    for d in (font_dir, css_dir, meta_dir):
        os.makedirs(d, exist_ok=True)

    out_layers = []
    total = 0
    for layer in layers:
        lid = layer["id"]
        ttf = resolve_font(lid, args.fonts)
        if not ttf:
            print(f"skip {lid}: no ttf")
            continue
        shards, avg, size = plan_shards(ttf, args.budget)
        total_bytes = 0
        sinfo = []
        css_lines = []
        all_cps = []
        alt_lost = 0
        for i, cps in enumerate(shards):
            cps = sorted(cps)
            all_cps.extend(cps)
            # 每个分片都从原始 TTF 重新加载：Subsetter.subset() 会就地裁剪 font 对象
            font = TTFont(ttf)
            opts = subset.Options()
            opts.layout_features = ["*"]
            opts.name_IDs = ["*"]
            sub = subset.Subsetter(options=opts)
            sub.populate(unicodes=cps)
            sub.subset(font)

            ng = len(font.getGlyphOrder())
            want = len(cps)
            if layer.get("variants") and ng <= want:
                alt_lost += 1

            sname = f"{lid}-{i}"
            woff2_path = os.path.join(font_dir, sname + ".woff2")
            tmp_ttf = os.path.join(font_dir, sname + ".ttf")
            font.flavor = None
            font.save(tmp_ttf)
            font.close()
            f2 = TTFont(tmp_ttf)
            f2.flavor = "woff2"
            f2.save(woff2_path)
            f2.close()
            os.remove(tmp_ttf)
            b = os.path.getsize(woff2_path)
            total_bytes += b

            rs = ranges_from_sorted(cps)
            sinfo.append({"file": sname + ".woff2", "chars": len(cps), "bytes": b})
            css_lines.append(
                "@font-face{font-family:'%s';src:url('../fonts/%s.woff2') format('woff2');"
                "font-display:block;unicode-range:%s}"
                % (lid, sname, css_unicode_range(rs))
            )
        open(os.path.join(css_dir, lid + ".css"), "w", encoding="utf-8").write(
            "\n".join(css_lines))

        layer["shards"] = sinfo
        layer["bytes"] = total_bytes
        layer["has"] = ranges_from_sorted(sorted(all_cps))
        for k in ("charset", "font_ttf", "font_woff2"):
            layer.pop(k, None)

        # 元数据 → JS
        mp = os.path.join(args.data, "meta", lid + ".json")
        if os.path.exists(mp):
            meta = json.load(open(mp, encoding="utf-8"))
            js_meta(lid, meta, os.path.join(meta_dir, lid + ".js"))
            layer["hasMeta"] = True
        else:
            layer["hasMeta"] = False

        total += total_bytes
        out_layers.append(layer)
        print(f"{lid:14s} chars={len(all_cps):6d} shards={len(sinfo):3d} "
              f"woff2={total_bytes/1048576:6.2f} MB  avg={avg}B/char  "
              + (f"ALT-LOST in {alt_lost} shards" if alt_lost else "alt ok"))

    prev_path = os.path.join(args.data, "layers.json")
    if only and os.path.exists(prev_path):
        prev = json.load(open(prev_path, encoding="utf-8"))
        prev = [l for l in prev if l["id"] not in only]
        out_layers = prev + out_layers
        out_layers.sort(key=lambda r: (r.get("era_order", 99), r["id"]))

    js_assign("GA_LAYERS", out_layers, os.path.join(data_dir, "layers.js"))
    vp = os.path.join(args.data, "variants.json")
    if os.path.exists(vp):
        js_assign("GA_VARIANTS", json.load(open(vp, encoding="utf-8")),
                  os.path.join(data_dir, "variants.js"))

    json.dump(out_layers, open(os.path.join(args.data, "layers.json"), "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    print(f"\nTOTAL {len(out_layers)} layers, {total/1048576:.2f} MB woff2, "
          f"{sum(len(l['shards']) for l in out_layers)} shards")


if __name__ == "__main__":
    main()
