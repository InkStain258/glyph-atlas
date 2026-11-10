#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""给每个字体层打上侧栏分组（group），并同步所有派生数据。

为什么要单独一个脚本：`group` 是「展示归类」，不是字体本身的属性，
但它同时出现在 data/font-catalog.json（版权页数据源）、data/layers*.json
（查询页侧栏）、data/font-library.json（字体库索引）三处。手改容易漏。

四个分组：
  ancient      古文字 · 字形源（甲骨到隸書，含說文小篆）
  calligraphy  書法 · 手寫（楷 / 行 / 草 / 篆的毛笔与手写字体）
  print        刻本 · 活字（宋元明清刻本、江户明治活字复刻）
  modern       現代 · 排版（思源、得意黑这类现代印刷字体）

用法：python -X utf8 scripts/set_groups.py
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

GROUP = {
    # ---- 書法 · 手寫 ----
    "grassseal": "calligraphy",           # 草篆（小篆复刻，笔意）
    "lxgwseal": "calligraphy",            # 霞鹜篆书
    "iansui": "calligraphy",              # 芫荽（台繁手写楷）
    "kleeone": "calligraphy",             # Klee One（教科书楷书）
    "longcang": "calligraphy",            # 龙藏体
    "lxgwwenkai": "calligraphy",          # 霞鹜文楷
    "mashanzheng": "calligraphy",         # 马善政毛笔楷
    "yujisyuku": "calligraphy",           # 悠司肃（写经风楷）
    "zhimangxing": "calligraphy",         # 志莽行书
    "liujianmaocao": "calligraphy",       # 刘建毛草
    # ---- 刻本 · 活字 ----
    "huiwenmincho": "print",              # 汇文明朝体
    "kaiseitokumin": "print",             # 古书籍明朝（明治活字）
    "newtegomin": "print",                # 新テゴミン（明治木活字）
    "zenoldmincho": "print",              # 禅老明朝（江户–明治）
    "babelstone-han": "print",            # 巴别石汉字（宋体骨架）
    "hanamin-a": "print",                 # 花园明朝A
    "hanamin-b": "print",                 # 花园明朝B（仅归档，GBK 内只 6 字）
    "chiron-sung-hk": "print",            # 昭源宋体
    "fandol-song": "print",               # Fandol 宋
    "fandol-fang": "print",               # Fandol 仿宋
    "fandol-kai": "print",                # Fandol 楷（书籍正文楷）
    "zhuque": "print",                    # 朱雀仿宋
    # ---- 現代 · 排版 ----
    "notoserifsc": "modern",
    "notosanssc": "modern",
    "smileysans": "modern",
    "fandol-hei": "modern",
    "zcoolxiaowei": "modern",
    # ---- 古文字 ----
    "oracle": "ancient", "bronze": "ancient", "chu": "ancient",
    "qinwenzi": "ancient", "chuanchao": "ancient", "seal": "ancient",
    "clerical": "ancient", "beishida": "ancient",
    "shuowen-seal-kaiyuan": "ancient",
}

FILES = ["data/font-catalog.json", "data/font-library.json",
         "data/layers.json", "data/layers-modern.json", "data/layers-ancient.json"]


def patch_list(path):
    if not os.path.exists(path):
        return 0
    data = json.load(open(path, encoding="utf-8"))
    rows = data if isinstance(data, list) else data.get("fonts", [])
    n = 0
    for r in rows:
        fid = r.get("id")
        if fid in GROUP:
            r["group"] = GROUP[fid]
            n += 1
    json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False,
              separators=(",", ":"))
    return n


def main():
    for rel in FILES:
        p = os.path.join(ROOT, *rel.split("/"))
        print("%-28s %3d 条" % (rel, patch_list(p)))


if __name__ == "__main__":
    main()
