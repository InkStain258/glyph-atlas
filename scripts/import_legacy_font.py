#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 Big5 / GBK 码位的旧式字库转成 Unicode cmap 的现代 TTF。

背景：北师大说文小篆这类字库的 cmap 是 platformID=3, platEncID=4（Big5），
浏览器按 Unicode 查字必然查不到。这里逐码解码成字符，重写 cmap，字形表原样保留。

用法：
  python scripts/import_legacy_font.py --src x.ttf --out y.ttf \
      [--encoding big5] [--family "GlyphAtlas-beishida"] [--keep-name]

许可提醒：转换后仍是「修改版」，若上游声明了保留名，必须改 nameID 1/3/4/6。
"""
import argparse
import os
import sys

from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable

BIG5_ALIASES = ["big5", "big5hkscs", "cp950"]
GBK_ALIASES = ["gbk", "gb18030", "cp936"]


def decode_code(code, encodings):
    """把一个 16 位码位解码成字符；解不出来返回 None。"""
    raw = bytes([(code >> 8) & 0xFF, code & 0xFF]) if code > 0xFF else bytes([code & 0xFF])
    for enc in encodings:
        try:
            s = raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
        if len(s) == 1:
            return s
    return None


def build_unicode_map(font, encodings):
    """旧 cmap → {字符: 字形名}。"""
    mapping = {}
    skipped = 0
    for sub in font["cmap"].tables:
        for code, gname in sub.cmap.items():
            ch = decode_code(code, encodings)
            if ch is None:
                skipped += 1
                continue
            mapping.setdefault(ch, gname)
    return mapping, skipped


def write_cmap(font, mapping):
    """用 Unicode 子表替换原 cmap（format 4 覆盖 BMP，format 12 覆盖全平面）。"""
    bmp = {ord(ch): g for ch, g in mapping.items() if ord(ch) <= 0xFFFF}
    full = {ord(ch): g for ch, g in mapping.items()}

    t4 = CmapSubtable.newSubtable(4)
    t4.platformID, t4.platEncID, t4.language = 3, 1, 0
    t4.cmap = bmp

    t12 = CmapSubtable.newSubtable(12)
    t12.platformID, t12.platEncID, t12.language = 3, 10, 0
    t12.cmap = full

    t0 = CmapSubtable.newSubtable(4)
    t0.platformID, t0.platEncID, t0.language = 0, 3, 0
    t0.cmap = bmp

    cmap = newTable("cmap")
    cmap.tableVersion = 0
    cmap.tables = [t0, t4, t12]
    font["cmap"] = cmap


def rename(font, family):
    name = font["name"]
    for nid in (1, 3, 4, 6, 16, 17, 18, 20, 21):
        name.setName(family, nid, 3, 1, 0x409)
        if name.getName(nid, 1, 0, 0):
            name.setName(family, nid, 1, 0, 0)
    # 版权与许可（ID 0/13/14）保持原样，不得篡改。


def coverage(mapping):
    gb1 = gb2 = gbk = 0
    for hi in range(0xB0, 0xF8):
        for lo in range(0xA1, 0xFF):
            try:
                ch = bytes([hi, lo]).decode("gb2312")
            except UnicodeDecodeError:
                continue
            if ch in mapping:
                if hi <= 0xD7:
                    gb1 += 1
                else:
                    gb2 += 1
    for hi in range(0x81, 0xFF):
        for lo in list(range(0x40, 0x7F)) + list(range(0x80, 0xFF)):
            try:
                ch = bytes([hi, lo]).decode("gbk")
            except UnicodeDecodeError:
                continue
            if ch in mapping:
                gbk += 1
    return gb1, gb2, gbk


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--encoding", default="big5", choices=["big5", "gbk"])
    ap.add_argument("--family", default=None, help="改后的 family name；不给则原样保留")
    ap.add_argument("--keep-name", action="store_true")
    ap.add_argument("--woff2", action="store_true", help="同时输出同名 .woff2")
    ap.add_argument("--normalize", action="store_true",
                    help="逐字归一：长边→0.86*upem、中心 (0.5upem, 0.38upem)，与其它古文字层视觉一致")
    args = ap.parse_args()

    encodings = BIG5_ALIASES if args.encoding == "big5" else GBK_ALIASES
    font = TTFont(args.src)

    subs = [(getattr(t, "platformID", None), getattr(t, "platEncID", None), len(t.cmap)) for t in font["cmap"].tables]
    print("source cmap subtables:", subs)

    mapping, skipped = build_unicode_map(font, encodings)
    print("mapped chars: %d  (skipped codes: %d)" % (len(mapping), skipped))

    # 关键：原字体 19,877 个 Big5 码位里只有约 1.1 万个真字形，其余是空轮廓占位符。
    # 若把这些空字形也写进 cmap，网页会显示「有字形」却渲染成一片空白（比缺字更误导）。
    # 所以先按 ink 过滤：没有轮廓的映射直接丢弃，cmap 只保留真能画的字。
    gs = font.getGlyphSet()
    inked = set()
    for gn in font.getGlyphOrder():
        bp = BoundsPen(gs)
        try:
            gs[gn].draw(bp)
        except Exception:
            continue
        if bp.bounds:
            inked.add(gn)
    keep = {u: gn for u, gn in mapping.items() if gn in inked}
    dropped = len(mapping) - len(keep)
    print("cmap: keep %d  drop-empty %d" % (len(keep), dropped))
    mapping = keep

    # 有歧义时留个记录：同一字符命中多个字形只取第一个
    for sub in font["cmap"].tables:
        sub.cmap = {}

    write_cmap(font, mapping)
    if args.normalize:
        from normalize_glyphs import normalize
        n = normalize(font, verbose=True)
        print("normalized glyphs:", n)

    if args.family and not args.keep_name:
        rename(font, args.family)
        print("renamed family ->", args.family)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    font.save(args.out)
    print("saved:", args.out, "%.2f MB" % (os.path.getsize(args.out) / 1048576))

    if args.woff2:
        base = os.path.splitext(args.out)[0]
        f2 = TTFont(args.out)
        f2.flavor = "woff2"
        f2.save(base + ".woff2")
        print("saved:", base + ".woff2", "%.2f MB" % (os.path.getsize(base + ".woff2") / 1048576))

    gb1, gb2, gbk = coverage(mapping)
    print("coverage GB2312 L1=%d L2=%d  GBK=%d" % (gb1, gb2, gbk))
    print("sample:", "".join(sorted(mapping)[:20]))


if __name__ == "__main__":
    sys.exit(main())
