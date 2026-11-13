# -*- coding: utf-8 -*-
"""验证字体包完整性，并打包成单个 zip。"""
import os, sys, json, hashlib, zipfile
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.abspath(os.path.join(ROOT, "..", "dist", "glyph-atlas-font-pack"))
ZIP = OUT + ".zip"

CERT = "可商用证明.md"
SIX = ["{id}.ttf", "LICENSE.txt", "license.json", "NOTICE.md", CERT, "demo.png"]

# 协议全文头部特征 -> 与 license.json 的 spdx 对应
LIC_MARK = {
    "OFL-1.1": "SIL OPEN FONT LICENSE",
    "CC0-1.0": "CC0 1.0",
    "CC-BY-4.0": "ATTRIBUTION 4.0 INTERNATIONAL",
    "PD": "PUBLIC DOMAIN",
    "GPL-2.0": "GNU GENERAL PUBLIC LICENSE",
    "GPL-3.0+FE": "AS A SPECIAL EXCEPTION",
    "Arphic-PL-1.0": "ARPHIC PUBLIC LICENSE",
}

def main():
    errs, warns = [], []
    dirs = sorted(d for d in os.listdir(os.path.join(OUT, "fonts"))
                  if os.path.isdir(os.path.join(OUT, "fonts", d)))
    print("dirs:", len(dirs))
    if len(dirs) != 43:
        errs.append("font count != 43: %d" % len(dirs))

    shapes = {}
    licenses_used = set()
    total_ttf = 0
    for d in dirs:
        dd = os.path.join(OUT, "fonts", d)
        for pat in SIX:
            f = os.path.join(dd, pat.replace("{id}", d))
            if not os.path.isfile(f):
                errs.append("%s MISSING %s" % (d, pat))
        # license.json
        p = os.path.join(dd, "license.json")
        if os.path.isfile(p):
            try:
                lj = json.load(open(p, encoding="utf-8"))
            except Exception as e:
                errs.append("%s license.json PARSE %s" % (d, e)); lj = {}
            spdx = lj.get("license_spdx", "")
            extra = lj.get("license_spdx_extra") or ""
            licenses_used.add(spdx)
            # 协议全文一致性
            lp = os.path.join(dd, "LICENSE.txt")
            if os.path.isfile(lp):
                lic = open(lp, encoding="utf-8").read()
                up = lic.upper()
                mark = LIC_MARK.get(spdx)
                if mark and mark not in up:
                    errs.append("%s LICENSE.txt not %s (spdx=%s)" % (d, mark, spdx))
                if spdx == "PD" and "SIL OPEN FONT LICENSE" in up:
                    errs.append("%s PD but OFL template" % d)
                # 只有声明了 CC-BY-4.0 附加条款的，才要求附上其全文
                if extra == "CC-BY-4.0" and LIC_MARK["CC-BY-4.0"] not in up:
                    errs.append("%s 声明 CC-BY-4.0 附加但正文缺失" % d)
        # demo 有墨
        dp = os.path.join(dd, "demo.png")
        if os.path.isfile(dp):
            im = Image.open(dp).convert("L")
            ink = sum(1 for px in im.getdata() if px < 110)
            if ink < 3000:
                errs.append("%s demo.png LOW INK %d" % (d, ink))
            if d == "hanamin-b":
                print("hanamin-b ink:", ink)
        # 证书措辞
        cp = os.path.join(dd, CERT)
        if os.path.isfile(cp):
            cert = open(cp, encoding="utf-8").read()
            for line in cert.splitlines():
                if line.startswith("| 字库形态"):
                    shapes[d] = line
            if "| **商业使用** | **允许** |" not in cert:
                errs.append("%s cert missing commercial=allowed" % d)
        tp = os.path.join(dd, d + ".ttf")
        if os.path.isfile(tp):
            total_ttf += os.path.getsize(tp)

    # 根目录文件
    for f in ["README.md", "INDEX.md", "manifest.json", "manifest.csv"]:
        if not os.path.isfile(os.path.join(OUT, f)):
            errs.append("root MISSING " + f)
    licdir = os.path.join(OUT, "LICENSES")
    lics = sorted(os.listdir(licdir)) if os.path.isdir(licdir) else []
    print("LICENSES/:", lics)

    # manifest 与实物对账
    mp = os.path.join(OUT, "manifest.json")
    if os.path.isfile(mp):
        m = json.load(open(mp, encoding="utf-8"))
        print("manifest fonts:", m.get("font_count"), "declared bytes:", m.get("total_ttf_bytes"))
        if m.get("font_count") != 43:
            errs.append("manifest font_count != 43")
        ids = {r["id"] for r in m.get("fonts", [])}
        if ids != set(dirs):
            errs.append("manifest id set mismatch: %s" % (ids ^ set(dirs)))
        for r in m.get("fonts", []):
            p = os.path.join(OUT, "fonts", r["id"], r["id"] + ".ttf")
            if os.path.isfile(p):
                h = hashlib.sha256(open(p, "rb").read()).hexdigest()
                if h != r.get("ttf_sha256"):
                    errs.append("%s sha256 mismatch" % r["id"])
    print("actual total ttf bytes:", total_ttf)

    print("\n--- 证书字库形态措辞分布 ---")
    vals = {}
    for d, s in shapes.items():
        vals.setdefault(s, []).append(d)
    for s, ds in vals.items():
        print("  %-2d  %s" % (len(ds), s))

    print("\n=== ERRORS: %d ===" % len(errs))
    for e in errs:
        print("  !", e)
    if errs:
        print("VALIDATION FAILED - not packing")
        sys.exit(1)

    # 打包
    if os.path.exists(ZIP):
        os.remove(ZIP)
    n = 0
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for base, _, files in os.walk(OUT):
            for fn in sorted(files):
                full = os.path.join(base, fn)
                rel = os.path.relpath(full, os.path.dirname(OUT))
                z.write(full, rel.replace(os.sep, "/"))
                n += 1
    print("\nZIP:", ZIP)
    print("files:", n, "bytes:", os.path.getsize(ZIP))
    print("VALIDATION OK")

if __name__ == "__main__":
    main()
