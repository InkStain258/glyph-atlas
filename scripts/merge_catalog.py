# -*- coding: utf-8 -*-
"""合并 font-catalog.json：把 fonts/incoming/<id>/license.json 提升为主数据条目。

背景：font-scout 曾整份重写 font-catalog.json（41 条 → 18 条），第二轮 16 款
与北师大说文小篆的条目丢失。本脚本以「现有 catalog」为基底，逐条补回
fonts/incoming/ 下每一项的四件套元数据，并把重复条目降级为 superseded。

用法：
    python -X utf8 scripts/merge_catalog.py            # 写入
    python -X utf8 scripts/merge_catalog.py --dry-run  # 只报告

输出：重写 data/font-catalog.json（保留 schema_version/project/... 顶层字段）
"""
import argparse
import glob
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG = os.path.join(ROOT, "data", "font-catalog.json")
INCOMING = os.path.join(ROOT, "fonts", "incoming")

# 由本项目编译/授权、不来自上游字库包的古文字体
EXTRA = [
    {
        "id": "beishida",
        "status": "shipped",
        "group": "ancient",
        "name_zh": "說文小篆",
        "name_en": "ShuoWen XiaoZhuan (BNU)",
        "era": "東漢（《說文解字》成書，100–121 年）；字庫 1997 年由北師大製作",
        "style": "篆書",
        "style_detail": "小篆；字庫據《說文解字》篆文整理，Big5/GBK 舊碼位，本項目轉為 Unicode",
        "license_spdx": "PROJECT-GRANT",
        "license_name": "項目組授權（北師大文學院）",
        "license_url": "",
        "copyright": "Proprietary for Sinica, all right reserved. / 北師大文學院項目組授權本項目使用",
        "author": "北京師範大學文學院（字庫製作）；glyph-atlas 做 cmap 轉換",
        "attribution_required": True,
        "modification_allowed": True,
        "redistribution_allowed": False,
        "commercial_use_allowed": False,
        "reserved_font_name": None,
        "source_url": ".dsh/skills/chinese-seal-research/assets/fonts/BeiShiDaShuoWenXiaoZhuan-1.ttf",
        "file": "fonts/ancient/beishida/glyphs.ttf",
        "format": "TTF",
        "bytes": 6508036,
        "sha256": "",
        "num_glyphs": 19879,
        "cmap_entries": 18438,
        "gb2312_l1": 2783,
        "gb2312_l2": 2055,
        "gbk": 15985,
        "num_chars": 18438,
        "note": "原字庫 cmap 僅有 platformID=3/platEncID=4（Big5），瀏覽器按 Unicode 查不到；"
                "本項目逐碼 Big5→Unicode 重寫 cmap（format 4 + format 12），字形未改。"
                "nameID 0 原文保留，未改寫版權聲明。",
    },
]

# 与已入库字体重复、只需保留一条的旧条目
SUPERSEDED = {
    "beishida-shuowen-xiaozhuan": (
        "beishida",
        "与本项目已入库的 beishida 为同一款北师大说文小篆字体，"
        "授权已完成、cmap 已转 Unicode，故本条目降级为 superseded，不再列出。",
    ),
}


def from_license_json(path):
    """fonts/incoming/<id>/license.json → catalog 条目"""
    d = json.load(open(path, encoding="utf-8"))
    fid = d["id"]
    inc = os.path.dirname(path)
    orig = d.get("original_file") or ""
    file_rel = "fonts/incoming/%s/%s" % (fid, orig) if orig else ""
    if file_rel and not os.path.exists(os.path.join(ROOT, file_rel)):
        cands = [x for x in os.listdir(inc) if x.lower().endswith((".ttf", ".otf", ".ttc"))]
        file_rel = "fonts/incoming/%s/%s" % (fid, cands[0]) if cands else ""
    fmt = os.path.splitext(file_rel)[1].lstrip(".").upper() or "TTF"
    return {
        "id": fid,
        "status": "shipped",
        "group": "ancient" if d.get("style") in ("篆书", "篆書") and "說文" in (d.get("name_zh") or "") else "modern",
        "name_zh": d.get("name_zh") or fid,
        "name_en": d.get("name_en") or "",
        "era": d.get("era") or "",
        "style": d.get("style") or "",
        "style_detail": d.get("style_detail") or "",
        "license_spdx": d.get("license_spdx") or "UNKNOWN",
        "license_name": d.get("license_name") or "",
        "license_url": d.get("license_url") or "",
        "copyright": d.get("copyright_holder") or "",
        "author": d.get("author") or "",
        "attribution_required": bool(d.get("attribution_required")),
        "modification_allowed": bool(d.get("modification_allowed")),
        "redistribution_allowed": bool(d.get("redistribution_allowed")),
        "commercial_use_allowed": bool(d.get("commercial_use_allowed")),
        "reserved_font_name": d.get("reserved_font_name"),
        "source_url": d.get("source_url") or "",
        "file": file_rel,
        "format": fmt,
        "bytes": d.get("bytes") or 0,
        "sha256": d.get("sha256") or "",
        "num_glyphs": d.get("num_glyphs") or 0,
        "cmap_entries": d.get("cmap_entries") or 0,
        "gb2312_l1": d.get("gb2312_l1") or 0,
        "gb2312_l2": d.get("gb2312_l2") or 0,
        "gbk": d.get("gbk") or 0,
        "num_chars": d.get("gbk") or d.get("cmap_entries") or 0,
        "downloaded_at": d.get("downloaded_at") or "",
        "note": d.get("notes") or "",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cat = json.load(open(CATALOG, encoding="utf-8"))
    by_id = {f["id"]: f for f in cat["fonts"]}

    added, updated = [], []
    for path in sorted(glob.glob(os.path.join(INCOMING, "*", "license.json"))):
        e = from_license_json(path)
        old = by_id.get(e["id"])
        if old and old.get("status") == "shipped" and old.get("file"):
            # 已有条目：只补 group / 覆盖率 / 许可布尔位，不覆盖人工核验过的字段
            for k in ("group", "gb2312_l1", "gb2312_l2", "gbk", "num_chars",
                      "attribution_required", "modification_allowed",
                      "redistribution_allowed", "commercial_use_allowed"):
                if e.get(k) not in (None, "", 0, False) or k.startswith("attribution") or k.endswith("_allowed"):
                    old.setdefault(k, e[k])
            old.setdefault("group", e["group"])
            updated.append(e["id"])
        else:
            by_id[e["id"]] = e
            added.append(e["id"])

    for e in EXTRA:
        if e["id"] in by_id:
            by_id[e["id"]].update({k: v for k, v in e.items() if k not in ("status",)})
            updated.append(e["id"])
        else:
            by_id[e["id"]] = dict(e)
            added.append(e["id"])

    for fid, (tgt, why) in SUPERSEDED.items():
        if fid in by_id:
            by_id[fid]["status"] = "superseded"
            by_id[fid]["superseded_by"] = tgt
            by_id[fid]["note"] = why
            updated.append(fid)

    fonts = sorted(by_id.values(), key=lambda f: (
        0 if f.get("group") == "ancient" else (1 if f.get("status") == "shipped" else 2),
        f.get("era_order") or 0, f["id"]))

    shipped = [f for f in fonts if f.get("status") == "shipped"]
    quar = [f for f in fonts if f.get("status") == "quarantine"]
    styles = sorted({f.get("style") for f in shipped if f.get("style")})
    summary = cat.get("summary") or {}
    summary.update({
        "shipped_count": len(shipped),
        "quarantine_count": len(quar),
        "superseded_count": len([f for f in fonts if f.get("status") == "superseded"]),
        "total_count": len(fonts),
        "styles_covered": styles,
        "shipped_total_bytes": sum(int(f.get("bytes") or 0) for f in shipped),
        "ancient_group": [f["id"] for f in shipped if f.get("group") == "ancient"],
        "php_note": "",
    })
    summary.pop("php_note", None)
    # 书体 → id 索引重建
    s2i = {}
    for f in shipped:
        s2i.setdefault(f.get("style") or "其他", []).append(f["id"])
    summary["style_to_ids"] = {k: sorted(v) for k, v in sorted(s2i.items())}
    missing = [s for s in ("隶书", "魏碑") if s not in styles]
    summary["styles_missing"] = missing
    cat["summary"] = summary
    cat["fonts"] = fonts

    print("新增 %d：%s" % (len(added), " ".join(added)))
    print("补齐 %d：%s" % (len(updated), " ".join(updated)))
    print("合计 %d 条（shipped %d / quarantine %d / superseded %d）"
          % (len(fonts), len(shipped), len(quar), summary["superseded_count"]))
    for f in shipped:
        print("  %-24s %-10s %-8s %s" % (f["id"], f.get("group", "modern"),
                                         f.get("license_spdx"), f.get("name_zh")))
    if args.dry_run:
        print("\n--dry-run：未写入")
        return
    json.dump(cat, open(CATALOG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n写入", CATALOG, os.path.getsize(CATALOG), "B")


if __name__ == "__main__":
    main()