#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 BabelStone IDS（表意文字描述序列）整理成前端可直接加载的部件索引。

数据源：https://babelstone.co.uk/CJK/IDS.TXT
  Andrew West（魏安），Unicode 16.0，2025-06-27，97,680 条。
  许可：IDS 描述是事实，不受版权保护；作者明确「任何人可为个人或商业目的
  自由使用本文件中的 IDS 数据，无需请求许可、无需署名」，并放弃对呈现格式
  的版权主张、允许 fork 或作为新数据集的基础。

输出：
  web/data/ids.js      window.GA_IDS = {meta:{...}, src:[ "字IDS", ... ]}
  data/ids/LICENSE-IDS.txt   许可原文摘录 + 出处 + 整理说明

条目格式：每条是「字 + IDS 序列」，字在 [0]，其后为 IDS（可能为空 = 独体字）。
`{nn}` 是 BabelStone 用于无编码部件的占位符（如 与 = ⿹{22}一），原样保留；
`〾`（U+303E 表意变化指示符）在解析前剥离。
"""
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, ".cache", "ids", "IDS_BABEL.TXT")
OUT_JS = os.path.join(ROOT, "web", "data", "ids.js")
OUT_LIC = os.path.join(ROOT, "data", "ids", "LICENSE-IDS.txt")

# 12 个标准 IDC + 2 个 BabelStone 扩展（⿽ 包围右上、㇯ 减法）
IDC_ARITY = {
    "\u2ff0": 2, "\u2ff1": 2, "\u2ff2": 3, "\u2ff3": 3, "\u2ff4": 2, "\u2ff5": 2,
    "\u2ff6": 2, "\u2ff7": 2, "\u2ff8": 2, "\u2ff9": 2, "\u2ffa": 2, "\u2ffb": 2,
    "\u2ffd": 2, "\u31ef": 2,
}

LICENSE_EXCERPT = """BabelStone IDS（表意文字描述序列）
数据源 : https://babelstone.co.uk/CJK/IDS.TXT
维护者 : Andrew West（魏安）<babelstone@gmail.com>
版本   : Unicode 16.0（2024-09），文件日期 2025-06-27，共 97,680 条
许可   : 事实数据，不受版权保护；作者明确许可自由使用（原文摘录如下）

  Under U.S. copyright law, data (i.e. a collection of facts) is not eligible
  to copyright protection, and as IDS descriptions for CJK ideographs are facts
  not original creative compositions, IDS sequences in themselves are not
  eligible for copyright protection (that is to say, you could no more copyright
  彼 = ⿰彳皮 than you could copyright 1 + 1 = 2). Therefore, anyone is free to
  make use of the IDS data provided in this file for personal or commercial
  purposes without asking permission or providing attribution. I furthermore
  waive any copyright claims to the presentation format of the data in this
  file, and anyone is free to fork the file, or use it as the basis for a new
  IDS data set.

本项目改动（如实记录）:
  1. 只取「字 + IDS」两列，丢弃 U+ 码位列与 $(GKPTJ…) 地区字形标记；
  2. `〾`(U+303E) 表意变化指示符前缀剥离；`{nn}` 无编码部件占位符原样保留；
  3. 重新序列化为前端可直接加载的 JS 数组，未改动任何 IDS 序列内容。
  4. 前端只在本地解析、检索，不做任何再分发为「IDS 数据集」的行为。
"""


def _gb2312_level(level):
    """GB2312 一级/二级字表（按区位顺序），用于前端排序时把常用字排前面。"""
    lo, hi = (0xB0A1, 0xD7F9) if level == 1 else (0xD8A1, 0xF7FE)
    out = []
    for hi_byte in range(lo >> 8, (hi >> 8) + 1):
        for lo_byte in range(0xA1, 0xFF):
            b = bytes([hi_byte, lo_byte])
            try:
                ch = b.decode("gb2312")
            except Exception:
                continue
            if len(ch) == 1 and ch >= "\u4e00":
                out.append(ch)
    return "".join(out)


def main():
    if not os.path.exists(SRC):
        sys.exit("缺少 " + SRC)
    raw = io.open(SRC, encoding="utf-8-sig", errors="replace").read()
    entries = []
    skipped = 0
    for line in raw.splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            skipped += 1
            continue
        ch, desc = parts[1], parts[2]
        if len(ch) != 1:
            skipped += 1
            continue
        m = re.match(r"^\^?(.*?)\$?\(([A-Z]+)\)$", desc)
        ids = m.group(1) if m else desc
        ids = ids.replace("\u303e", "").strip()
        if ids.startswith("^"):
            ids = ids[1:]
        entries.append(ch + ids)

    entries.sort(key=lambda s: ord(s[0]))

    meta = {
        "src": "BabelStone IDS",
        "url": "https://babelstone.co.uk/CJK/IDS.TXT",
        "author": "Andrew West (魏安)",
        "unicode": "16.0",
        "file_date": "2025-06-27",
        "entries": len(entries),
        "license": "public-domain-facts",
        "license_file": "../../data/ids/LICENSE-IDS.txt",
        "note": "IDS 描述为事实数据，作者明确许可自由使用、无需署名。",
        "gb1": _gb2312_level(1),
        "gb2": _gb2312_level(2),
    }

    os.makedirs(os.path.dirname(OUT_LIC), exist_ok=True)
    io.open(OUT_LIC, "w", encoding="utf-8").write(LICENSE_EXCERPT)

    body = json.dumps(entries, ensure_ascii=False, separators=(",", ":"))
    meta_js = json.dumps(meta, ensure_ascii=False, separators=(",", ":"))
    js = ("/* BabelStone IDS · Unicode 16.0 · 事实数据，作者声明可自由使用\n"
          "   每条 = 字 + 表意文字描述序列（IDS）。由 scripts/build_ids.py 生成 */\n"
          "window.GA_IDS={meta:" + meta_js + ",src:" + body + "};\n")
    os.makedirs(os.path.dirname(OUT_JS), exist_ok=True)
    io.open(OUT_JS, "w", encoding="utf-8").write(js)

    # 统计：我们的字体层里有多少字能查到结构（层用 has 码位区间描述字集）
    layers = json.load(io.open(os.path.join(ROOT, "data", "layers.json"), encoding="utf-8"))
    have = set(ord(e[0]) for e in entries)
    cov = {}
    for L in layers:
        cps = []
        for lo, hi in L.get("has") or []:
            if hi - lo > 20000:
                continue
            cps.extend(range(lo, hi + 1))
        n = sum(1 for cp in cps if cp in have)
        cov[L["id"]] = (n, len(cps), round(n / max(1, len(cps)) * 100, 1))
    report = {
        "entries": len(entries),
        "skipped": skipped,
        "js_bytes": os.path.getsize(OUT_JS),
        "coverage": cov,
    }
    io.open(os.path.join(ROOT, ".tmp_ids_report.json"), "w", encoding="utf-8").write(
        json.dumps(report, ensure_ascii=False, indent=1))
    print("entries %d  skipped %d  js %.2f MB" % (len(entries), skipped,
                                                  os.path.getsize(OUT_JS) / 1048576))
    for k, v in sorted(cov.items()):
        print("  %-12s %6d / %6d  %5.1f%%" % (k, v[0], v[1], v[2]))


if __name__ == "__main__":
    main()