# -*- coding: utf-8 -*-
"""生成版权页数据：web/data/licenses.js

版权页（licenses.html）不加载任何字体分片，卡片数据全部来自这里；
协议全文按 SPDX 去重，多个字体共用一份，避免几十 KB 的重复。

输入：data/font-library.json（由 make_font_library.py 生成）+ fonts/license-texts/*.txt
输出：web/data/licenses.js → window.GA_LICENSES = {texts, fonts}
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(ROOT, "data", "font-library.json")
TEXTS = os.path.join(ROOT, "fonts", "license-texts")
OUT = os.path.join(ROOT, "web", "data", "licenses.js")

MONO = {
    "oracle": "甲", "bronze": "金", "chu": "楚", "qinwenzi": "秦",
    "chuanchao": "傳", "seal": "篆", "clerical": "隸",
    "beishida": "說", "shuowen-seal-kaiyuan": "開",
}

NOTE_HEAD = {
    "OFL-1.1": "可自由使用、修改、再分发，含商用；修改版不得使用保留字体名，且须继续按 OFL 分发。",
    "CC0-1.0": "公有领域奉献：无义务、无须署名，可商用、可改、可再分发。",
    "CC-BY-4.0": "可商用、可改、可再分发，但必须署名、注明改动并附协议链接。",
    "PD": "公有领域：无著作权限制，本页仍自愿署明来源。",
    "Arphic-PL-1.0": "文鼎公共许可（Arphic Public License）：可自由使用、修改、再分发，含商用；修改版须沿用本许可，且不得使用原字体名。",
    "GPL-3.0+FE": "GNU GPL v3 附字体例外：作为字体嵌入文档不触发 GPL；单独分发字体或其修改版时须按 GPL 提供源码。",
}


def read_text(spdx):
    fn = {
        "OFL-1.1": "OFL-1.1.txt", "CC0-1.0": "CC0-1.0.txt",
        "CC-BY-4.0": "CC-BY-4.0.txt", "CC-BY-ND-3.0": "CC-BY-ND-3.0.txt",
        "IPA-1.0": "IPA-1.0.txt", "PD": "PD.txt",
    }.get(spdx) or (spdx + ".txt")
    if not fn:
        return ""
    p = os.path.join(TEXTS, fn)
    return open(p, encoding="utf-8").read() if os.path.exists(p) else ""


def main():
    lib = json.load(open(LIB, encoding="utf-8"))
    texts, fonts = {}, []
    for f in lib["fonts"]:
        spdx = f.get("license_spdx") or "UNKNOWN"
        for sp in (spdx, f.get("license_spdx_extra")):
            if sp and sp not in texts and f.get("shipped"):
                texts[sp] = {
                    "name": f.get("license_name") if sp == spdx else sp,
                    "url": f.get("license_url") if sp == spdx else "https://creativecommons.org/licenses/by/4.0/",
                    "body": read_text(sp),
                    "summary": NOTE_HEAD.get(sp, ""),
                }
        if False:
            texts[spdx] = {
                "name": f.get("license_name") or spdx,
                "url": f.get("license_url") or "",
                "body": read_text(spdx),
                "summary": NOTE_HEAD.get(spdx, ""),
            }
        kind = f.get("kind")
        in_ancient_group = kind in ("ancient-compiled", "ancient-font") or f.get("group") == "ancient"
        grp = "ancient" if in_ancient_group else (f.get("group") or "modern")
        folder = (("fonts/ancient/" + f["id"]) if kind in ("ancient-compiled", "ancient-font") else (
            ("fonts/modern/" + f["id"]) if kind == "modern-font" else ("fonts/quarantine/" + f["id"])))
        fonts.append({
            "id": f["id"],
            "kind": kind,
            "group": grp,
            "name_zh": f.get("name_zh") or f["id"],
            "name_en": f.get("name_en") or "",
            "era": f.get("era") or "",
            "era_order": f.get("era_order") or 0,
            "style": f.get("style") or "",
            "style_detail": f.get("style_detail") or "",
            "license_spdx": spdx,
            "license_spdx_extra": f.get("license_spdx_extra"),
            "license_name": f.get("license_name") or spdx,
            "license_url": f.get("license_url") or "",
            "copyright_holder": f.get("copyright_holder") or "",
            "author": f.get("author") or "",
            "attribution_required": bool(f.get("attribution_required")),
            "attribution_text": f.get("attribution_text") or "",
            "modification_allowed": bool(f.get("modification_allowed")),
            "redistribution_allowed": bool(f.get("redistribution_allowed")),
            "commercial_use_allowed": bool(f.get("commercial_use_allowed")),
            "source_url": f.get("source_url") or "",
            "source_detail": f.get("source_detail") or "",
            "chars": f.get("chars") or 0,
            "glyphs": f.get("glyphs") or 0,
            "variants": f.get("variants") or 0,
            "mono": MONO.get(f["id"], (f.get("name_zh") or f["id"])[0]),
            "folder": folder,
            "license_file": folder + "/LICENSE.txt",
            "notice_file": folder + "/NOTICE.md",
            "shipped": bool(f.get("shipped")),
            "web_shipped": bool(f.get("web_shipped", True)),
            "reject_reason": f.get("reject_reason") or "",
            "quarantine_basis": f.get("quarantine_basis"),
            "file_removed": bool(f.get("file_removed")),
        })

    GRANK = {"ancient": 0, "calligraphy": 1, "print": 2, "modern": 3}
    fonts.sort(key=lambda x: (0 if x["shipped"] else 1, GRANK.get(x["group"], 9),
                              x["era_order"], x["name_zh"]))
    payload = {
        "generated_at": lib.get("generated_at"),
        "texts": texts,
        "fonts": fonts,
        "counts": {
            "shipped": sum(1 for x in fonts if x["shipped"]),
            "rejected": sum(1 for x in fonts if not x["shipped"]),
            "ancient": sum(1 for x in fonts if x["shipped"] and x["group"] == "ancient"),
            "calligraphy": sum(1 for x in fonts if x["shipped"] and x["group"] == "calligraphy"),
            "print": sum(1 for x in fonts if x["shipped"] and x["group"] == "print"),
            "modern": sum(1 for x in fonts if x["shipped"] and x["group"] == "modern"),
        },
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    open(OUT, "w", encoding="utf-8").write("window.GA_LICENSES=" + body + ";\n")
    # 查询页页头只要一个数字，单开一个小文件，免得为 120 KB 的版权数据买单
    cnt_file = os.path.join(os.path.dirname(OUT), "fontcount.js")
    with open(cnt_file, "w", encoding="utf-8") as fh:
        fh.write("window.GA_FONTCOUNT=%d;" % payload["counts"]["shipped"] + chr(10))

    print("wrote %s  %.1f KB  (%d fonts, %d texts)"
          % (OUT, os.path.getsize(OUT) / 1024, len(fonts), len(texts)))

if __name__ == "__main__":
    main()
