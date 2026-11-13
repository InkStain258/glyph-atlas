#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_font_pack.py — 导出「可商用」字体包。

每个字体一个目录：
  <id>.ttf        字体文件
  demo.png        1200x675 演示图（用该字体本身渲染）
  LICENSE.txt     协议全文（以 fonts/license-texts 的权威全文为准，重新拼装）
  可商用证明.md    可商用判定依据、义务、证据链
  license.json    结构化条款
  NOTICE.md       来源 / 署名 / 改动说明

仅收录 commercial_use_allowed == True 的字库。
用法：python -X utf8 scripts/make_font_pack.py [--out ../dist/glyph-atlas-font-pack]
"""
import argparse
import datetime
import hashlib
import json
import os
import shutil

from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAPER = (247, 243, 234)
INK = (26, 24, 21)
INK2 = (95, 87, 74)
INK3 = (148, 139, 124)
RULE = (221, 211, 189)
ACCENT = (158, 43, 30)
BADGE_BG = (240, 232, 216)
GRID = (226, 217, 200)
GRID_SOFT = (240, 234, 222)

SYS_BOLD = "C:/Windows/Fonts/msyhbd.ttc"
SYS_REG = "C:/Windows/Fonts/msyh.ttc"

HEAD_CANDIDATES = "永受嘉福長樂未央天地玄黃宇宙洪荒"
BODY1 = "天地玄黃　宇宙洪荒　日月盈昃　辰宿列張"
BODY2 = "學而時習之不亦說乎　有朋自遠方來不亦樂乎"
BODY3 = "春眠不覺曉　處處聞啼鳥　夜來風雨聲　花落知多少"
GRID_CANDIDATES = "永受嘉福長樂未央日月山川天心水木人王大上下中"
GRID_TAIL = "天地玄黃宇宙洪荒"

LIC_LABEL = {
    "OFL-1.1": "SIL OFL 1.1",
    "CC0-1.0": "CC0 1.0",
    "CC-BY-4.0": "CC BY 4.0",
    "PD": "公有領域",
    "GPL-2.0": "GPL v2",
    "GPL-3.0+FE": "GPL v3 + 字體例外",
    "Arphic-PL-1.0": "文鼎公共許可",
    "PROJECT-GRANT": "項目組授權",
}

LIC_TEXT_FILE = {
    "OFL-1.1": "OFL-1.1.txt",
    "CC0-1.0": "CC0-1.0.txt",
    "CC-BY-4.0": "CC-BY-4.0.txt",
    "PD": "PD.txt",
    "GPL-2.0": "GPL-2.0.txt",
    "GPL-3.0+FE": "GPL-3.0+FE.txt",
    "Arphic-PL-1.0": "Arphic-PL-1.0.txt",
}

LIC_URL = {
    "OFL-1.1": "https://openfontlicense.org/",
    "CC0-1.0": "https://creativecommons.org/publicdomain/zero/1.0/",
    "CC-BY-4.0": "https://creativecommons.org/licenses/by/4.0/",
    "PD": "https://creativecommons.org/publicdomain/mark/1.0/",
    "GPL-2.0": "https://www.gnu.org/licenses/old-licenses/gpl-2.0.html",
    "GPL-3.0+FE": "https://www.gnu.org/licenses/gpl-3.0.html",
    "Arphic-PL-1.0": "https://www.arphic.com/",
}

# 可商用判定依据（引用协议原文关键句）+ 必须履行的义务
LIC_BASIS = {
    "OFL-1.1": (
        "SIL Open Font License 1.1 · PERMISSION & CONDITIONS 第 2 条原文：\n"
        "    “Original or Modified Versions of the Font Software may be bundled,\n"
        "     redistributed and/or sold with any software, provided that each copy\n"
        "     contains the above copyright notice and this license.”\n"
        "协议明确允许「随软件销售」，即商业使用无障碍（禁止的是把字体软件本身单独售卖）。",
        ["不得把字体软件单独售卖（可随产品/文档/软件一起分发、销售）",
         "每份副本须保留版权声明与本协议全文",
         "修改版不得使用保留字体名（Reserved Font Name）",
         "衍生字体须继续以 OFL 1.1 分发，不得改换许可",
         "不得用原作者/版权方名义为修改版背书"]),
    "CC0-1.0": (
        "CC0 1.0 Universal · Section 2（Waiver）原文：权利人 “waives, abandons, and\n"
        "surrenders” 全部著作权及相关权利，任何人可为任何目的（含商业目的）复制、\n"
        "修改、分发、表演该作品，无需许可、无需付费、无需署名。",
        ["无（CC0 为无条件公有领域奉献，署名属自愿而非义务）"]),
    "CC-BY-4.0": (
        "Creative Commons Attribution 4.0 · Section 2（Scope）原文：\n"
        "    “You may exercise the Licensed Rights ... for any purpose,\n"
        "     including commercial purposes.”\n"
        "明确包含商业目的，但署名与注明修改是强制条件。",
        ["须保留并展示作者/来源署名",
         "须注明是否对材料作了修改",
         "须附本协议链接（或全文）"]),
    "PD": (
        "字体 name 表版权字段（nameID 0）原文即为 “Public Domain”。\n"
        "权利人已将著作财产权奉献于公有领域，任何人可复制、修改、分发、商用，\n"
        "无须署名、无须注明改动。本项目仍如实署明来源，属自愿而非义务。",
        ["无（公有领域，署名属自愿）"]),
    "GPL-2.0": (
        "GNU General Public License v2 · Section 0 原文：本许可授予 “the right to\n"
        "copy and distribute” 且 “you may charge a fee for the physical act of\n"
        "transferring a copy”。GPL 从不限制商业使用，只要求衍生作品继续开源。\n"
        "字体以 TTF 形式提供，本身即为可修改的源形态，满足 GPL 的传源要求。",
        ["再分发（含商用）须继续以 GPL v2 提供完整协议",
         "须随附可修改的源形态（本包直接提供 TTF，满足要求）",
         "须保留版权声明与无担保声明",
         "若分发修改版，须显著标注改动与日期"]),
    "GPL-3.0+FE": (
        "GNU GPL v3 同样不限制商业使用；本字体附带 Font Exception（字体例外），\n"
        "明确允许把字体嵌入文档/作品而不使该文档受 GPL 约束。\n"
        "字体以 TTF 形式提供，本身即为可修改的源形态。",
        ["再分发字体本身须继续以 GPL v3 + Font Exception 提供",
         "嵌入文档/作品不受 GPL 传染（Font Exception 已豁免）",
         "须保留版权声明、协议全文与无担保声明"]),
    "Arphic-PL-1.0": (
        "Arphic Public License · Preamble 原文：\n"
        "    “The ARPHIC PUBLIC LICENSE specifically permits and encourages you\n"
        "     to use this software”\n"
        "许可未对使用目的作任何商业/非商业区分，且明确允许复制与分发。",
        ["须随附本许可全文与文鼎科技的版权声明",
         "修改版须同样以 Arphic Public License 分发",
         "不得改动本许可文档本身"]),
}


def sysfont(path, size, index=0):
    try:
        return ImageFont.truetype(path, size, index=index)
    except Exception:
        return ImageFont.load_default()


def get_charset(font_path):
    f = TTFont(font_path, fontNumber=0, lazy=True)
    cmap = f.getBestCmap() or {}
    chars = set()
    for cp in cmap:
        if 0x20 <= cp <= 0x2FFF or 0x3400 <= cp <= 0x9FFF or 0xF900 <= cp <= 0xFAFF or 0x20000 <= cp <= 0x3FFFF:
            try:
                chars.add(chr(cp))
            except ValueError:
                pass
    f.close()
    return chars


def filt(text, charset):
    return "".join(ch for ch in text if ch in ("　", " ") or ch in charset).strip()


def fit_font(draw, text, path, max_w, start, floor=16):
    size = start
    while size > floor:
        f = ImageFont.truetype(path, size)
        if draw.textbbox((0, 0), text, font=f)[2] <= max_w:
            return f
        size -= 4
    return ImageFont.truetype(path, floor)


def draw_header(d, W, mono, name_zh, name_en, lic_label):
    d.rectangle([24, 24, W - 24, 675 - 24], outline=RULE, width=1)
    d.rounded_rectangle([60, 52, 132, 124], radius=6, fill=ACCENT)
    d.text((96, 60), mono, font=sysfont(SYS_BOLD, 46), fill=(255, 248, 242), anchor="ma")
    d.text((152, 56), name_zh, font=sysfont(SYS_BOLD, 34), fill=INK)
    d.text((154, 98), (name_en or "").upper(), font=sysfont(SYS_REG, 15), fill=INK3)
    f = sysfont(SYS_REG, 20)
    tw = d.textbbox((0, 0), lic_label, font=f)[2]
    x = W - 60 - (tw + 24)
    d.rounded_rectangle([x, 62, x + tw + 24, 100], radius=19, fill=BADGE_BG, outline=RULE)
    d.text((x + 12, 69), lic_label, font=f, fill=ACCENT)
    d.line([60, 148, W - 60, 148], fill=RULE, width=1)
    return 176


def bmp_cjk_count(charset):
    """BMP 内的汉字数（常用字样张够不够用的判断依据；扩展 B 区分不影响判断）。"""
    return sum(1 for c in charset
               if 0x3400 <= ord(c) <= 0x9FFF or 0xF900 <= ord(c) <= 0xFAFF)


def cjk_count(charset):
    """统计真正可用作样张的汉字数（排除标点/符号）。"""
    return sum(1 for c in charset
               if (0x3400 <= ord(c) <= 0x9FFF or 0xF900 <= ord(c) <= 0xFAFF
                   or 0x20000 <= ord(c) <= 0x3FFFF))


def pick_grid_chars(charset):
    """优先常用字；不足 12 个则从 CJK 汉字（含扩展区）里补足，避免拿到标点。"""
    pool = [c for c in GRID_CANDIDATES if c in charset][:12]
    if len(pool) < 12:
        cjk = [c for c in sorted(charset, key=ord)
               if (0x3400 <= ord(c) <= 0x9FFF or 0xF900 <= ord(c) <= 0xFAFF
                   or 0x20000 <= ord(c) <= 0x3FFFF)]
        for c in cjk:
            if len(pool) >= 12:
                break
            if c not in pool:
                pool.append(c)
    return pool[:12]


def render_demo(font_path, out_png, name_zh, name_en, lic_label, meta_line, mono, grid_mode=False):
    W, H = 1200, 675
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    top = draw_header(d, W, mono, name_zh, name_en, lic_label)

    charset = get_charset(font_path)

    if grid_mode:
        pool = pick_grid_chars(charset) or ["?"]
        cols = 6 if len(pool) > 6 else len(pool)
        rows = (len(pool) + cols - 1) // cols
        cw = min(150, (W - 140) // cols)
        gs = int(cw * 0.84)
        x0 = (W - cw * cols) // 2
        y0 = top + max(6, (300 - cw * rows) // 2)
        # 小字量的古文字层用系统字体做格中字符标签会更乱，直接用字形本身
        f = ImageFont.truetype(font_path, gs)
        for i, ch in enumerate(pool):
            cx = x0 + (i % cols) * cw
            cy = y0 + (i // cols) * cw
            d.rectangle([cx, cy, cx + cw, cy + cw], outline=GRID)
            d.line([cx + cw // 2, cy, cx + cw // 2, cy + cw], fill=GRID_SOFT)
            d.line([cx, cy + cw // 2, cx + cw, cy + cw // 2], fill=GRID_SOFT)
            d.line([cx, cy, cx + cw, cy + cw], fill=GRID_SOFT)
            d.line([cx + cw, cy, cx, cy + cw], fill=GRID_SOFT)
            bb = d.textbbox((0, 0), ch, font=f)
            gw, gh = bb[2] - bb[0], bb[3] - bb[1]
            d.text((cx + (cw - gw) / 2 - bb[0], cy + (cw - gh) / 2 - bb[1]), ch, font=f, fill=INK)
        y = y0 + cw * rows + 30
        tail = "　".join([c for c in GRID_TAIL if c in charset])
        if tail and y < H - 150:
            f2 = fit_font(d, tail, font_path, W - 160, 40, 20)
            tw = d.textbbox((0, 0), tail, font=f2)[2]
            d.text(((W - tw) / 2, y), tail, font=f2, fill=INK2)
    else:
        head = "".join([c for c in HEAD_CANDIDATES if c in charset])[:8]
        if not head:
            head = "".join(pick_grid_chars(charset))[:8] or "".join(sorted(charset))[:8]
        f_head = fit_font(d, head, font_path, W - 160, 128, 56)
        tw = d.textbbox((0, 0), head, font=f_head)[2]
        d.text(((W - tw) / 2, top + 16), head, font=f_head, fill=INK)
        y = top + 196
        for text, size, color in ((filt(BODY1, charset), 44, INK2),
                                  (filt(BODY2, charset), 32, INK2),
                                  (filt(BODY3, charset), 26, INK3)):
            if not text:
                continue
            f = fit_font(d, text, font_path, W - 160, size, 16)
            tw = d.textbbox((0, 0), text, font=f)[2]
            d.text(((W - tw) / 2, y), text, font=f, fill=color)
            y += int(size * 1.6)

    d.line([60, H - 92, W - 60, H - 92], fill=RULE, width=1)
    d.text((60, H - 76), meta_line, font=sysfont(SYS_REG, 18), fill=INK3)
    d.text((W - 60, H - 76), "GLYPH ATLAS · 歷代字形庫", font=sysfont(SYS_REG, 18), fill=INK3, anchor="ra")

    img.save(out_png, "PNG", optimize=True)


def build_license_txt(spdx, spdx_extra):
    """以 fonts/license-texts 的权威全文为准重新拼装，杜绝源目录里回退错模板。"""
    ldir = os.path.join(ROOT, "fonts", "license-texts")
    parts = []
    main = os.path.join(ldir, LIC_TEXT_FILE.get(spdx, spdx + ".txt"))
    if spdx_extra:
        parts.append("本字体包含两种许可的材料，分别适用于对应字形：\n"
                     "  · %s\n  · %s\n\n" % (spdx, spdx_extra))
    if os.path.exists(main):
        parts.append(open(main, encoding="utf-8").read())
    else:
        parts.append("许可全文见 %s 与同目录 可商用证明.md\n" % LIC_URL.get(spdx, ""))
    if spdx_extra:
        extra = os.path.join(ldir, LIC_TEXT_FILE.get(spdx_extra, spdx_extra + ".txt"))
        parts.append("\n\n========== %s ==========\n\n" % spdx_extra)
        if os.path.exists(extra):
            parts.append(open(extra, encoding="utf-8").read())
    return "".join(parts)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def certificate(f, row, spdx_extra, lic_fname):
    """每个字体一份「可商用证明」：判定 + 依据 + 义务 + 证据链。"""
    spdx = row["spdx"]
    basis, duties = LIC_BASIS.get(spdx, ("（见同目录 LICENSE.txt 协议全文）", ["详见协议全文"]))
    name = row["name"]
    fid = row["id"]
    L = []
    L.append("# %s · 可商用证明\n\n" % name)
    L.append("> 本文件是「歷代字形庫 · 可商用字體包」随附的授权证明，用于说明\n"
             "> 本字体为何可用于商业用途、依据何处、以及必须履行哪些义务。\n"
             "> 协议全文以同目录 `LICENSE.txt` 为准，本文件为便于查阅的判读摘要。\n\n")
    L.append("## 一、判定\n\n")
    L.append("| 项目 | 内容 |\n|---|---|\n")
    L.append("| 字体名称 | %s（%s） |\n" % (name, row["en"] or fid))
    L.append("| 字体 ID | `%s` |\n" % fid)
    L.append("| 许可 SPDX | `%s`（%s） |\n" % (spdx, row["label"]))
    L.append("| **商业使用** | **允许** |\n")
    L.append("| 修改 | %s |\n" % ("允许" if f.get("modification_allowed") else "不允许"))
    L.append("| 再分发 | %s |\n" % ("允许" if f.get("redistribution_allowed") else "不允许"))
    L.append("| 需署名 | %s |\n" % ("是" if f.get("attribution_required") else "否"))
    if spdx == "PD":
        shape = "GBK 子集（本项目派生版，已改名；公有领域无保留字体名限制）"
    elif str(f.get("kind", "")).startswith("ancient"):
        shape = "本项目依上游字形数据编译（非商业字库的复制）"
    else:
        shape = "GBK 子集（已改名 GA-%s Subset）" % fid
    if f.get("web_shipped") is False:
        shape += "；未在网页启用，主要收录 CJK 扩展 B 区罕用字"
    L.append("| 字库形态 | %s |\n" % shape)
    L.append("| 许可原文 | 同目录 `LICENSE.txt`；`LICENSES/%s` |\n" % lic_fname)
    L.append("| 官方地址 | %s |\n" % LIC_URL.get(spdx, ""))
    L.append("| 上游来源 | %s |\n" % (f.get("source_url") or "见 NOTICE.md"))
    L.append("| 版权/授权人 | %s |\n" % (f.get("copyright_holder") or "见 NOTICE.md"))
    L.append("| 导出日期 | %s |\n\n" % datetime.date.today().isoformat())
    L.append("## 二、可商用判定依据\n\n```\n%s\n```\n\n" % basis)
    if spdx_extra:
        L.append("**注意**：本字体另含 `%s` 授权的字形（对应协议全文已一并附在 `LICENSE.txt`），"
                 "该部分须按其条款署名并注明修改。\n\n" % spdx_extra)
    L.append("## 三、使用本字体须履行的义务\n\n")
    for i, x in enumerate(duties, 1):
        L.append("%d. %s\n" % (i, x))
    L.append("\n## 四、证据链\n\n")
    L.append("1. `LICENSE.txt` —— 上游许可全文（未改写），由 `fonts/license-texts/` 权威副本拼装。\n")
    L.append("2. `license.json` —— 结构化条款（SPDX、可商用/可修改/可再分发/署名等布尔值）。\n")
    L.append("3. `NOTICE.md` —— 上游来源、作者、本项目所做改动（子集化、改名、字形编译）。\n")
    L.append("4. 字体 `name` 表版权字段原文已在 `NOTICE.md` / `license.json` 中留档。\n")
    L.append("5. 上游发布地址见上表「上游来源」，可回溯核验。\n\n")
    L.append("## 五、免责\n\n本证明是本项目基于上游公开许可文本作出的判读，不构成法律意见；"
             "如对具体使用场景有疑问，请以上游协议原文与权利人声明为准。\n")
    return "".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "..", "dist", "glyph-atlas-font-pack"))
    args = ap.parse_args()
    out = os.path.abspath(args.out)

    lib = json.load(open(os.path.join(ROOT, "data", "font-library.json"), encoding="utf-8"))
    cat = json.load(open(os.path.join(ROOT, "data", "font-catalog.json"), encoding="utf-8"))
    catmap = {f["id"]: f for f in cat["fonts"]}

    fonts = [f for f in lib["fonts"] if f.get("shipped") and f.get("commercial_use_allowed")]
    print("fonts in pack:", len(fonts))

    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(os.path.join(out, "fonts"), exist_ok=True)
    os.makedirs(os.path.join(out, "LICENSES"), exist_ok=True)

    rows, used = [], {}
    fonts.sort(key=lambda x: (0 if str(x.get("kind", "")).startswith("ancient") else 1,
                              x.get("era_order", 90), x.get("name_zh", "")))
    for f in fonts:
        fid = f["id"]
        if str(f.get("kind", "")).startswith("ancient"):
            src = os.path.join(ROOT, "fonts", "ancient", fid, "glyphs.ttf")
        else:
            src = os.path.join(ROOT, "fonts", "modern", fid, "subset.ttf")
            if not os.path.exists(src):
                src = os.path.join(ROOT, "fonts", "modern", fid, "original.ttf")
        if not os.path.exists(src):
            print("MISSING", fid)
            continue
        ddir = os.path.join(out, "fonts", fid)
        os.makedirs(ddir, exist_ok=True)
        ttf = os.path.join(ddir, fid + ".ttf")
        shutil.copy2(src, ttf)

        c = catmap.get(fid, {})
        spdx = f.get("license_spdx", "")
        spdx_extra = f.get("license_spdx_extra")
        label = LIC_LABEL.get(spdx, spdx)
        chars = int(c.get("num_chars") or f.get("chars") or c.get("cmap_entries") or 0)
        # 未在网页启用的字库（如花园明朝 B）num_chars 是 GBK 交集数，会与实际收录严重不符，
        # 改用真实 cmap 规模，避免演示图出现 12 个字却写「收字 6」的矛盾。
        if f.get("web_shipped") is False:
            chars = int(c.get("cmap_entries") or chars)
        glyphs = int(c.get("num_glyphs") or f.get("glyphs") or 0)
        mono = f.get("mono") or (f.get("name_zh") or "字")[0]
        meta_line = "收字 {:,} · 字形 {:,} · 許可 {} · 檔案 {}".format(chars, glyphs, label, fid + ".ttf")

        # 协议全文：重新拼装权威副本，覆盖源目录可能存在的回退错模板
        lic_fname = LIC_TEXT_FILE.get(spdx, spdx + ".txt")
        open(os.path.join(ddir, "LICENSE.txt"), "w", encoding="utf-8").write(
            build_license_txt(spdx, spdx_extra))
        for name in ("NOTICE.md", "license.json"):
            s = os.path.join(os.path.dirname(src), name)
            if os.path.exists(s):
                shutil.copy2(s, os.path.join(ddir, name))

        grp = c.get("group")
        if not grp:
            grp = "ancient" if str(f.get("kind", "")).startswith("ancient") else "modern"
        row = {"id": fid, "name": f.get("name_zh"), "en": f.get("name_en"), "spdx": spdx,
               "spdx_extra": spdx_extra, "label": label, "chars": chars, "glyphs": glyphs,
               "era": f.get("era") or "", "style": f.get("style") or "",
               "group": grp, "holder": f.get("copyright_holder") or "",
               "source_url": f.get("source_url") or "",
               "attribution_required": bool(f.get("attribution_required")),
               "modification_allowed": bool(f.get("modification_allowed")),
               "redistribution_allowed": bool(f.get("redistribution_allowed")),
               "ttf_sha256": sha256(ttf), "ttf_bytes": os.path.getsize(ttf),
               "lic_file": "LICENSE.txt"}
        rows.append(row)

        open(os.path.join(ddir, "可商用证明.md"), "w", encoding="utf-8").write(
            certificate(f, row, spdx_extra, lic_fname))

        grid_mode = str(f.get("kind", "")).startswith("ancient") or bmp_cjk_count(get_charset(ttf)) < 1200
        render_demo(ttf, os.path.join(ddir, "demo.png"),
                    f.get("name_zh") or fid, f.get("name_en") or fid, label, meta_line, mono, grid_mode)

        lsrc = os.path.join(ROOT, "fonts", "license-texts", lic_fname)
        if os.path.exists(lsrc):
            used[lic_fname] = lsrc
        if spdx_extra:
            ef = LIC_TEXT_FILE.get(spdx_extra, spdx_extra + ".txt")
            esrc = os.path.join(ROOT, "fonts", "license-texts", ef)
            if os.path.exists(esrc):
                used[ef] = esrc
        print("ok", fid)

    for fn, path in used.items():
        shutil.copy2(path, os.path.join(out, "LICENSES", fn))

    write_readme(out, rows)
    write_manifest(out, rows)
    print("DONE", len(rows), "fonts ->", out)


def group_key(r):
    return r["group"] or "modern"


def write_readme(out, rows):
    groups = [("ancient", "古文字 · 字形源"), ("calligraphy", "書法 · 手寫"),
              ("print", "刻本 · 活字"), ("modern", "現代 · 排版")]
    L = []
    L.append("# 歷代字形庫 · 可商用字體包\n\n")
    L.append("由 **Glyph Atlas 歷代字形查詢** 導出，收錄 **%d 款** 明確可商用的字體，每款一個目錄。\n\n" % len(rows))
    L.append("## 目錄結構\n\n```\n")
    L.append("fonts/<id>/\n  <id>.ttf        字體檔\n  demo.png        演示圖（用該字體本身渲染）\n")
    L.append("  LICENSE.txt     許可全文（權威副本重新拼裝）\n  可商用证明.md   可商用判定依據、義務、證據鏈\n")
    L.append("  license.json    結構化條款\n  NOTICE.md       來源與改動說明\n")
    L.append("LICENSES/         各許可全文\nINDEX.md          字體索引表\nmanifest.json     完整清單（含 SHA-256）\nmanifest.csv      同清單，試算表可直接開\n```\n\n")
    L.append("## 收錄原則\n\n")
    L.append("- 只收**明確允許商業使用**的字體：SIL OFL 1.1 / CC0 1.0 / CC BY 4.0 / 公有領域 / GPL v2 / GPL v3 + 字體例外 / 文鼎公共許可。\n")
    L.append("- 每款都附**許可全文**（`LICENSE.txt`）與**可商用證明**（`可商用证明.md`），兩者可互相印證。\n")
    L.append("- 未收錄 **北師大說文小篆**：項目組書面授權僅限學習研究、禁止商用。\n")
    L.append("- **花園明朝 B** 已收錄：GBK 內僅 6 字，主體為 CJK 擴展 B 區罕用字，未在本工具網頁啓用，隨包提供以備核對生僻字。\n")
    L.append("- 14 款隔離字體（許可不明、禁改、或來源權屬存疑）不在包內。\n\n")

    for key, title in groups:
        sub = [r for r in rows if group_key(r) == key]
        if not sub:
            continue
        L.append("## %s（%d 款）\n\n| # | 字體 | ID | 許可 | 收字 | 字形 |\n|---|---|---|---|---|---|\n" % (title, len(sub)))
        for i, r in enumerate(sub, 1):
            L.append("| %d | %s | `%s` | %s | %s | %s |\n" % (i, r["name"], r["id"], r["label"],
                                                              format(r["chars"], ","), format(r["glyphs"], ",")))
        L.append("\n")

    L.append("## 授權提示（摘要，完整義務見各目錄 `可商用證明.md`）\n\n")
    L.append("- **OFL 1.1**：可商用、可修改、可再分發；修改版不得使用保留字體名，且須繼續以 OFL 分發。本包內現代字庫是 GBK 子集，已改名為 `GA-<id> Subset`。\n")
    L.append("- **GPL v2 / GPL v3 + FE**：可商用；再分發字體本身須繼續以同一 GPL 提供，並附可修改源檔——包內直接給的就是 TTF，滿足要求；Font Exception 允許嵌入文檔而不傳染 GPL。\n")
    L.append("- **CC0 / 公有領域**：無條件可用，無署名義務。\n")
    L.append("- **CC BY 4.0**（甲骨文部分字形）：可商用，但須署名、註明修改、附協議連結。\n")
    L.append("- **文鼎公共許可**：可商用；須隨附許可全文與文鼎版權聲明，衍生版同協議分發。\n\n")
    L.append("---\n\n由 Glyph Atlas 自動生成 · %s\n" % datetime.date.today().isoformat())
    open(os.path.join(out, "README.md"), "w", encoding="utf-8").write("".join(L))

    I = ["# 字體索引\n\n| 字體 | 許可 | 收字 | 目錄 |\n|---|---|---|---|\n"]
    for r in rows:
        I.append("| %s | %s | %s | `fonts/%s/` |\n" % (r["name"], r["label"], format(r["chars"], ","), r["id"]))
    open(os.path.join(out, "INDEX.md"), "w", encoding="utf-8").write("".join(I))


def write_manifest(out, rows):
    m = {
        "project": "Glyph Atlas 歷代字形庫 · 可商用字體包",
        "generated_at": datetime.date.today().isoformat(),
        "filter": "commercial_use_allowed == true AND shipped == true",
        "font_count": len(rows),
        "total_ttf_bytes": sum(r["ttf_bytes"] for r in rows),
        "fonts": rows,
    }
    open(os.path.join(out, "manifest.json"), "w", encoding="utf-8").write(
        json.dumps(m, ensure_ascii=False, indent=2))
    # CSV 便于 Excel 核对
    import csv
    with open(os.path.join(out, "manifest.csv"), "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "name", "name_en", "group", "spdx", "spdx_extra", "license_label",
                    "chars", "glyphs", "commercial_use", "attribution_required",
                    "modification_allowed", "redistribution_allowed",
                    "source_url", "ttf_bytes", "ttf_sha256", "license_file", "proof_file"])
        for r in rows:
            w.writerow([r["id"], r["name"], r["en"], r["group"], r["spdx"], r["spdx_extra"] or "",
                        r["label"], r["chars"], r["glyphs"], "true",
                        str(r["attribution_required"]).lower(), str(r["modification_allowed"]).lower(),
                        str(r["redistribution_allowed"]).lower(), r["source_url"],
                        r["ttf_bytes"], r["ttf_sha256"], "fonts/%s/LICENSE.txt" % r["id"],
                        "fonts/%s/可商用证明.md" % r["id"]])


if __name__ == "__main__":
    main()
