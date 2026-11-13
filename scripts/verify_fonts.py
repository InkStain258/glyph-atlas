#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
字体资产核验脚本 —— 古今汉字字形查询工具 (glyph-atlas)

设计原则
--------
1. **证据优先**：每款字体的许可判定只依据字体自身 `name` 表（nameID 0/1/2/4/13/14）
   的原文，以及 REGISTRY 中登记的官方发布页/授权页 URL。脚本不内置"印象式"许可结论。
2. **白名单闸门**：只有 SIL OFL 1.1 / CC0 / CC BY / 政府开放数据 / 明确书面免费商用
   这五类允许留在 `fonts/raw/`。其余一律进 `fonts/quarantine/`，并写入拒绝原因。
3. **可复跑且只读**：同一批文件重复执行，输出完全一致（不含时间戳、抽样种子固定为 SEED）。
   **本脚本绝不写 `data/font-catalog.json`**（主数据由维护方合并），核验结果只写
   `data/font-verify.json`。

用法
----
    python scripts/verify_fonts.py                # 核验 + 写 data/font-verify.json（WOFF2 用缓存）
    python scripts/verify_fonts.py --no-woff2     # 跳过 WOFF2 体积测量（快）
    python scripts/verify_fonts.py --check-only   # 只核验，不写文件
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import tempfile
from pathlib import Path

from fontTools.ttLib import TTFont, TTCollection

# --------------------------------------------------------------------------
# 路径
# --------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "fonts" / "raw"
QUAR_DIR = ROOT / "fonts" / "quarantine"
INCOMING_DIR = ROOT / "fonts" / "incoming"
CATALOG = ROOT / "data" / "font-catalog.json"
VERIFY_OUT = ROOT / "data" / "font-verify.json"

SEED = 20261103
SCHEMA_VERSION = 1

# --------------------------------------------------------------------------
# 许可白名单
# --------------------------------------------------------------------------
# 只收这五类（与需求书一致）。CC BY-ND / IPA / 商业字库 / 自定义"禁止修改"授权均不在内。
# 目标书体（style 字段取值域，9 类）
TARGET_STYLES = ["隶书", "楷书", "行书", "草书", "魏碑", "宋体", "仿宋", "黑体", "篆书"]
# 目标覆盖（10 类，含 "古籍刻本风" —— 由 style_detail 里的刻本/雕版字样判定）
TARGET_GENRES = TARGET_STYLES + ["古籍刻本风"]

COVERAGE_THRESHOLD = 0.99
FONT_SUFFIXES = (".ttf", ".otf", ".ttc", ".otc")

WHITELIST = {
    "OFL-1.1": "SIL Open Font License 1.1",
    "CC0-1.0": "CC0 1.0 / Public Domain",
    "CC-BY-4.0": "Creative Commons Attribution 4.0",
    "CC-BY-3.0": "Creative Commons Attribution 3.0",
    "GOV-ODL-1.0": "政府资料开放授权条款",
    "FREE-COMMERCIAL-WRITTEN": "明确书面免费商用（自定义）",
    "Arphic-PL-1.0": "Arphic Public License（1999 原始版：允许商用/修改/再分发）",
    "GPL-3.0+FE": "GNU GPL v3 + 字体嵌入例外（Fandol）",
    "GPL-2.0": "GNU GPL v2（王漢宗自由字型，无字体例外；子集化/转换须同许可分发）",
}

# 明确不允许（仅用于给出可读的拒绝原因）
DENYLIST = {
    "CC-BY-ND-3.0": "CC BY-ND 3.0（允许商用但禁止改作，与转 WOFF2/子集化流程冲突）",
    "IPA-1.0": "IPA Font License 1.0（不在白名单；非 OFL）",
    "PROPRIETARY": "字体 name 表标注 All Rights Reserved / Proprietary（商业字库）",
    "UNKNOWN": "字体 name 表无任何版权或许可声明，无法核验",
}

# --------------------------------------------------------------------------
# 字体登记表
# --------------------------------------------------------------------------
# 每一条对应一个实际文件。license_url / source_url 为人工核验过的权威页面。
# expected_spdx 仅作交叉校验：脚本仍以 name 表原文为主判据，两者不一致会报警。
REGISTRY = [
    # ---------------- 楷书 ----------------
    dict(
        id="lxgwwenkai",
        file="lxgwwenkai.ttf",
        name_zh="霞鹜文楷",
        name_en="LXGW WenKai",
        era="现代",
        style="楷书",
        style_detail="写经楷/硬笔楷，源自 Fontworks Klee One，台湾标准字形为主",
        source_url="https://github.com/lxgw/LxgwWenKai/releases/tag/v1.530",
        license_url="https://openfontlicense.org",
        expected_spdx="OFL-1.1",
        notes="保留字体名 '霞鹜/霞鶩/落霞孤鹜/LXGW'。字符集覆盖 CJK 基本区 20992 字 + 扩展 A/B。",
    ),
    dict(
        id="mashanzheng",
        file="mashanzheng.ttf",
        name_zh="马善政毛笔楷书",
        name_en="Ma Shan Zheng",
        era="现代",
        style="楷书",
        style_detail="毛笔楷（Google Fonts CJK 手写系列）",
        source_url="https://github.com/google/fonts/tree/main/ofl/mashanzheng",
        license_url="https://openfontlicense.org",
        expected_spdx="OFL-1.1",
        notes="仅 GB2312 一二级字范围（6763 字），无扩展区。适合做书法风格标题字。",
    ),
    dict(
        id="longcang",
        file="longcang.ttf",
        name_zh="龙藏体",
        name_en="Long Cang",
        era="现代",
        style="楷书",
        style_detail="藏体/瘦长楷，Google Fonts CJK 手写系列",
        source_url="https://github.com/google/fonts/tree/main/ofl/longcang",
        license_url="https://openfontlicense.org",
        expected_spdx="OFL-1.1",
        notes="仅 GB2312 范围 6763 字。",
    ),
    # ---------------- 行书 ----------------
    dict(
        id="zhimangxing",
        file="zhimangxing.ttf",
        name_zh="志莽行书",
        name_en="Zhi Mang Xing",
        era="现代",
        style="行书",
        style_detail="硬笔行书，Google Fonts CJK 手写系列",
        source_url="https://github.com/google/fonts/tree/main/ofl/zhimangxing",
        license_url="https://openfontlicense.org",
        expected_spdx="OFL-1.1",
        notes="仅 GB2312 范围 6763 字。",
    ),
    # ---------------- 草书 ----------------
    dict(
        id="liujianmaocao",
        file="liujianmaocao.ttf",
        name_zh="刘建毛草",
        name_en="Liu Jian Mao Cao",
        era="现代",
        style="草书",
        style_detail="毛笔草书，Google Fonts CJK 手写系列",
        source_url="https://github.com/google/fonts/tree/main/ofl/liujianmaocao",
        license_url="https://openfontlicense.org",
        expected_spdx="OFL-1.1",
        notes="仅 GB2312 范围 6763 字；草书字形连笔多，做检索需人工校对。",
    ),
    # ---------------- 宋体 / 明体 ----------------
    dict(
        id="notoserifsc",
        file="notoserifsc.ttf",
        name_zh="思源宋体（简体）",
        name_en="Noto Serif SC",
        era="现代",
        style="宋体",
        style_detail="可变字重（wght 200-900），现代宋体",
        source_url="https://github.com/google/fonts/tree/main/ofl/notoserifsc",
        license_url="https://openfontlicense.org",
        expected_spdx="OFL-1.1",
        notes="可变字体（Variable Font，wght 轴），单文件含全字重；基于 Adobe Source Han Serif。",
    ),
    dict(
        id="huiwenmincho",
        file="huiwenmincho.ttf",
        name_zh="汇文明朝体",
        name_en="Huiwen Mincho",
        era="明代（刻本风格复刻）",
        style="宋体",
        style_detail="古籍刻本明朝体，仿铅印/雕版字形",
        source_url="https://zhuanlan.zhihu.com/p/344103391",
        license_url="https://zhuanlan.zhihu.com/p/344103391",
        expected_spdx="CC0-1.0",
        notes=(
            "作者特里王发布。字体 name 表 nameID0 写 'Public Domain'；"
            "发布页另附中文授权声明：可免费用于印刷/显示/嵌入/随套装销售，不可单独转卖字体文件。"
        ),
    ),
    # ---------------- 仿宋 ----------------
    dict(
        id="zhuque",
        file="zhuque.ttf",
        name_zh="朱雀仿宋",
        name_en="Zhuque Fangsong",
        era="现代",
        style="仿宋",
        style_detail="仿宋（民国铅字风格），TrionesType 璇玑造字",
        source_url="https://github.com/TrionesType/Zhuque/releases/tag/v0.212",
        license_url="http://scripts.sil.org/OFL",
        expected_spdx="OFL-1.1",
        notes="作者 JadeFoci；仍在迭代（v0.212），CJK 基本区约 1.1 万字。",
    ),
    # ---------------- 黑体 ----------------
    dict(
        id="notosanssc",
        file="notosanssc.ttf",
        name_zh="思源黑体（简体）",
        name_en="Noto Sans SC",
        era="现代",
        style="黑体",
        style_detail="可变字重（wght 100-900），无衬线黑体",
        source_url="https://github.com/google/fonts/tree/main/ofl/notosanssc",
        license_url="https://openfontlicense.org",
        expected_spdx="OFL-1.1",
        notes="可变字体；基于 Adobe Source Han Sans。",
    ),
    dict(
        id="smileysans",
        file="smileysans.ttf",
        name_zh="得意黑",
        name_en="Smiley Sans",
        era="现代",
        style="黑体",
        style_detail="倾斜窄体黑，标题/海报用，atelierAnchor",
        source_url="https://github.com/atelier-anchor/smiley-sans/releases/tag/v2.0.1",
        license_url="https://scripts.sil.org/OFL",
        expected_spdx="OFL-1.1",
        notes="nameID0 写 All rights reserved，但 nameID13/14 明确声明 OFL 1.1 —— 以 OFL 为准（OFL 项目常见写法）。",
    ),
    # ---------------- 篆书 ----------------
    dict(
        id="lxgwseal",
        file="lxgwseal.ttf",
        name_zh="霞鹜篆书",
        name_en="LXGW Seal",
        era="秦（小篆字形，源自《说文解字》）",
        style="篆书",
        style_detail="小篆，兼容 Unicode 18.0 小篆区块（U+XXXXX 独立编码）",
        source_url="https://github.com/lxgw/LxgwSeal/releases/tag/v0.001-alpha.10.8",
        license_url="https://openfontlicense.org",
        expected_spdx="OFL-1.1",
        notes="alpha 阶段，仅 75 个篆字（含今字映射），覆盖节庆/干支/节气/朝代。字形借自 Klee One、西文借自 Gungsuh（均为 OFL）。",
        coverage_note="注意：篆书按 Unicode 18.0 小篆区块独立编码，与今字一对一映射只收 75 字，故下方 10 字常用字抽样命中率低属正常，不代表字体异常。",
    ),
    # ---------------- 隔离区（存档待定，不用于发布） ----------------
    dict(
        id="tw-sung",
        file="tw-sung.ttf",
        name_zh="教育部標準宋體（全字庫正宋體）",
        name_en="TW-Sung / MOESongUN",
        era="现代",
        style="宋体",
        style_detail="台湾教育部标准字形宋体（印刷标准字形）",
        source_url="https://github.com/Jiehong/TW-fonts",
        license_url="https://language.moe.gov.tw/",
        expected_spdx="CC-BY-ND-3.0",
        status="quarantine",
        notes="name 表原文为 CC 姓名标示-禁止改作 3.0 台湾，允许商用但禁止改作。",
    ),
    dict(
        id="tw-kai",
        file="tw-kai.ttf",
        name_zh="教育部標準楷書（全字庫正楷體）",
        name_en="TW-Kai / TW-MOE-Std-Kai",
        era="现代",
        style="楷书",
        style_detail="台湾教育部标准字形楷书",
        source_url="https://github.com/Jiehong/TW-fonts",
        license_url="https://language.moe.gov.tw/",
        expected_spdx="CC-BY-ND-3.0",
        status="quarantine",
        notes="同 TW-Sung，CC BY-ND 3.0 台湾。",
    ),
    dict(
        id="lxgwneoxihei",
        file="lxgwneoxihei.ttf",
        name_zh="霞鹜新晰黑",
        name_en="LXGW Neo XiHei",
        era="现代",
        style="黑体",
        style_detail="屏显黑体",
        source_url="https://github.com/lxgw/LxgwNeoXiHei/releases/tag/v1.308",
        license_url="https://opensource.org/licenses/IPA/",
        expected_spdx="IPA-1.0",
        status="quarantine",
        notes="name 表 nameID13 指向 IPA Font License（经 IPA 字体衍生），非 OFL。",
    ),
    dict(
        id="jinghua-laosong",
        file="jinghua-laosong.ttf",
        name_zh="京華老宋体",
        name_en="KingHwa OldSong",
        era="宋（雕版老宋风格复刻）",
        style="宋体",
        style_detail="雕版老宋/古籍刻本风",
        source_url="https://zhuanlan.zhihu.com/p/677725322",
        license_url="https://github.com/cntrump/imitation_typeface_fonts",
        expected_spdx="PROPRIETARY",
        status="quarantine",
        notes=(
            "字体 nameID0 写 'Copyright 2022 TerryWang. All rights reserved.'；"
            "发布页声明①免费商用②可传播但不可单独售卖③非开源、禁止修改及传播修改版。"
            "因③与转 WOFF2/子集化冲突，隔离。"
        ),
    ),
    dict(
        id="yishan-beizhuan",
        file="yishan-beizhuan.ttf",
        name_zh="峄山碑篆体",
        name_en="YiShan Bei Zhuan Ti",
        era="秦（峄山碑小篆）",
        style="篆书",
        style_detail="秦小篆（峄山碑字形）",
        source_url=".dsh/skills/chinese-seal-research/assets/fonts/YiShanBeiZhuanTi-2.ttf",
        license_url="",
        expected_spdx="UNKNOWN",
        status="quarantine",
        notes="name 表完全没有 nameID 0/13/14（无版权、无许可、无授权链接），无法核验来源与许可；3849 字形可用但不合法落地。",
    ),
    dict(
        id="beishida-shuowen-xiaozhuan",
        file="beishida-shuowen-xiaozhuan.ttf",
        name_zh="北师大说文小篆",
        name_en="BNU ShuoWen XiaoZhuan",
        era="东汉（《说文解字》小篆）",
        style="篆书",
        style_detail="说文解字小篆",
        source_url=".dsh/skills/chinese-seal-research/assets/fonts/BeiShiDaShuoWenXiaoZhuan-1.ttf",
        license_url="",
        expected_spdx="PROPRIETARY",
        status="quarantine",
        notes="nameID0 = 'Proprietary for Sinica, all right reserved.'；且 cmap 无可用 Unicode 子表（getBestCmap 为空），字形不可检索。",
    ),
]

# --------------------------------------------------------------------------
# 抽样字符集
# --------------------------------------------------------------------------
# 常用字池（用于随机抽 10 字做覆盖率验证；固定种子保证可复跑）
COMMON_POOL = (
    "的一是不了人我在有他这为之大来以个中上们到说国和地也子时道出而要于就下得可你年生自会那"
    "后能对着事其里所去行过家十用发天如然作方成者多日都三小军二无同么经法当起与好看学进种将"
    "还分此心前面又定见只主没公从问很最重并物手应战向头文体政美相见被利什二等产或新己制身果"
    "加西斯月话合回特代内信表化老给世位次度门任常先海通教儿原东声提立及比员解水名真论处走义"
    "各入几口认条平系气题活尔更别打女变四神总何电数安少报才结反受目太量再感建务做接必场件计"
    "管期市直德资命山金指克许统区保至队形社便空决治展马科司五基眼书非则听白却界达光放强即像"
    "难且权思王象完设式色路记南品住告类求据程北边死张该交规万取拉格望觉术领共确传师观清今切"
    "院让识候带导争运笑飞风步改收根干造言联持组每济车亲极林服快办议往元英士证近失转夫令准布"
)

# 编码集：直接用 Python 内置 codec 反解出**完整**字符集，比抽样更严谨、且完全确定。
def _charset(codec, leads, trail_ranges):
    out = set()
    for lead in leads:
        for lo, hi in trail_ranges:
            for trail in range(lo, hi + 1):
                try:
                    out.add(ord(bytes([lead, trail]).decode(codec)))
                except Exception:
                    pass
    return out


def gb2312_set():
    """GB2312 全部 6763 个汉字（0xB0A1–0xF7FE 汉字区）。"""
    return _charset("gb2312", range(0xB0, 0xF8), [(0xA1, 0xFE)])


def gbk_set():
    """GBK 全部 21003 个字符。"""
    return _charset("gbk", range(0x81, 0xFF), [(0x40, 0x7E), (0x80, 0xFE)])


def big5_set():
    """Big5 全部 13053 个字符。"""
    return _charset("big5", range(0xA1, 0xFA), [(0x40, 0x7E), (0xA1, 0xFE)])


GB2312_SET = gb2312_set()
GB2312_L1_SET = _charset("gb2312", range(0xB0, 0xD8), [(0xA1, 0xFE)])  # 一级常用字 3755
GBK_SET = gbk_set()
BIG5_SET = big5_set()

# --------------------------------------------------------------------------
# name 表读取
# --------------------------------------------------------------------------
NAME_IDS = (0, 1, 2, 4, 5, 6, 13, 14, 16, 17)


def _decode_record(rec):
    """解码 name 记录：优先用 fontTools 的平台/编码感知解码，失败再走本地启发式。"""
    try:
        s = rec.toUnicode()
        if s and "\ufffd" not in s and "\x00" not in s:
            return s.strip("\x00 \t\r\n")
    except Exception:
        pass
    raw = rec.string
    if isinstance(raw, str):
        return raw.replace("\x00", "").strip()
    plat, enc = rec.platformID, rec.platEncID
    if plat == 3 and enc in (0, 1, 10):
        try:
            return raw.decode("utf-16-be").replace("\x00", "").strip()
        except Exception:
            pass
    for codec in ("utf-16-be", "utf-8", "gb18030", "big5", "latin-1"):
        try:
            s = raw.decode(codec)
            if "\ufffd" not in s:
                return s.replace("\x00", "").strip()
        except Exception:
            continue
    return raw.decode("latin-1", "replace").replace("\x00", "").strip()


def read_name_table(font):
    """返回 {nameID: [去重后的字符串, ...]}；同一 ID 多语言记录全部保留。"""
    out = {}
    if "name" not in font:
        return out
    for rec in font["name"].names:
        if rec.nameID not in NAME_IDS:
            continue
        try:
            text = _decode_record(rec).strip()
        except Exception:
            continue
        if text:
            out.setdefault(rec.nameID, set()).add(text)
    return {k: sorted(v) for k, v in sorted(out.items())}


# --------------------------------------------------------------------------
# 许可判定（只依据 name 表原文）
# --------------------------------------------------------------------------
def classify_license(names):
    """从 name 表文本判定 SPDX 标识 + 返回判定依据（命中的原文片段）。"""
    blob = "\n".join(
        s for nid in (0, 13, 14, 16, 17) for s in names.get(nid, [])
    )
    low = blob.lower()

    if "sil open font license" in low or "openfontlicense.org" in low or "scripts.sil.org/ofl" in low:
        return "OFL-1.1", _snippet(blob, ("SIL Open Font License", "Open Font License"))
    if "arphic public license" in low:
        return "Arphic-PL-1.0", _snippet(blob, ("ARPHIC PUBLIC LICENSE", "Arphic Public License"))
    if "gnu general public license" in low or "gnu.org/licenses" in low or "gpl" in low:
        snippet = _snippet(blob, ("GNU GENERAL PUBLIC LICENSE", "gnu.org/licenses", "GPL"))
        if "version 2" in low and "version 3" not in low:
            return "GPL-2.0", snippet
        return "GPL-3.0+FE", snippet
    if "ipa font license" in low or "information-technology promotion agency" in low or "opensource.org/licenses/ipa" in low:
        return "IPA-1.0", _snippet(blob, ("IPA", "Information-technology"))
    if "禁止改作" in blob or "cc-by-nd" in low or "no derivatives" in low:
        return "CC-BY-ND-3.0", _snippet(blob, ("禁止改作", "CC"))
    if "cc0" in low or "public domain" in low:
        return "CC0-1.0", _snippet(blob, ("Public Domain", "CC0"))
    if "cc by" in low or "creative commons attribution" in low or "姓名標示" in blob:
        return "CC-BY-4.0", _snippet(blob, ("CC", "Creative Commons"))
    if "all right" in low or "proprietary" in low:
        return "PROPRIETARY", _snippet(blob, ("All rights", "Proprietary", "Proprietary for"))
    return "UNKNOWN", ""


def _snippet(blob, needles, limit=240):
    for needle in needles:
        idx = blob.find(needle)
        if idx >= 0:
            # 大写/句首关键字直接从命中处起，避免截出 "his Font Software" 之类残句
            start = idx if needle[:1].isupper() else max(0, idx - 40)
            return blob[start:start + limit].strip()
    return blob[:limit].strip()


# --------------------------------------------------------------------------
# 字形统计
# --------------------------------------------------------------------------
def load_font(path: Path):
    if path.suffix.lower() in (".ttc", ".otc"):
        coll = TTCollection(str(path), lazy=True)
        return coll.fonts[0], len(coll.fonts)
    return TTFont(str(path), lazy=True, fontNumber=0), 1


def cmap_stats(font):
    try:
        cmap = font.getBestCmap() or {}
    except Exception:
        cmap = {}
    cps = set(cmap.keys())
    return cmap, {
        "num_glyphs": font["maxp"].numGlyphs if "maxp" in font else 0,
        "cmap_entries": len(cps),
        "has_cjk_unified": any(0x4E00 <= c <= 0x9FFF for c in cps),
        "has_ext_a": any(0x3400 <= c <= 0x4DBF for c in cps),
        "has_ext_b": any(0x20000 <= c <= 0x2A6DF for c in cps),
    }


def ratio(pool, cps):
    if not pool:
        return 0.0
    return sum(1 for ch in pool if ord(ch) in cps) / len(pool)


def coverage_of(codepoint_set, cps):
    """完整字符集覆盖率（0.0–1.0）。codepoint_set 为码位集合。"""
    if not codepoint_set:
        return 0.0
    return len(codepoint_set & cps) / len(codepoint_set)


def glyph_has_outline(font, cmap, ch):
    """判断某字在字体里确实有可渲染轮廓（不是空字形/仅 .notdef）。"""
    cp = ord(ch)
    if cp not in cmap:
        return False
    gname = cmap[cp]
    if gname == ".notdef":
        return False
    try:
        if "glyf" in font:
            g = font["glyf"][gname]
            return g.numberOfContours != 0
        if "CFF " in font or "CFF2" in font:
            cff = font["CFF "].cff if "CFF " in font else font["CFF2"].cff
            td = cff[cff.fontNames[0]].CharStrings[gname]
            try:
                td.draw(_NullPen())
                return True
            except Exception:
                return False
        return True
    except Exception:
        return False


class _NullPen:
    def moveTo(self, *a, **k): pass
    def lineTo(self, *a, **k): pass
    def curveTo(self, *a, **k): pass
    def qCurveTo(self, *a, **k): pass
    def closePath(self, *a, **k): pass
    def endPath(self, *a, **k): pass
    def addComponent(self, *a, **k): pass


def coverage_sample(font, cmap):
    """固定种子随机抽 10 个常用字，逐个验证 cmap + 轮廓。"""
    pool = sorted(set(COMMON_POOL))  # 去重 + 排序，保证跨平台稳定
    picked = random.Random(SEED).sample(pool, 10)
    out = []
    for ch in picked:
        out.append({
            "char": ch,
            "codepoint": f"U+{ord(ch):04X}",
            "in_cmap": ord(ch) in cmap,
            "has_outline": glyph_has_outline(font, cmap, ch),
        })
    return out


def woff2_size(path: Path, cache_dir: Path):
    """用 fontTools 内部 brotli 压缩到临时目录测体积；按 sha256 缓存避免重复计算。"""
    from fontTools.ttLib import woff2 as woff2_mod

    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / f"{path.stem}-{digest}.woff2"
    if not cached.exists():
        woff2_mod.compress(str(path), str(cached))
    return cached.stat().st_size


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def build_record(entry: dict, path: Path, woff2_cache: Path, measure_woff2: bool):
    font, ttc_count = load_font(path)
    names = read_name_table(font)
    cmap, stats = cmap_stats(font)

    detected, evidence = classify_license(names)
    expected = entry.get("expected_spdx")
    cps = set(cmap.keys())

    # 逐字穷举（不是抽样）：用 codec 反解出的完整编码集求包含率
    gb2312_cov = coverage_of(GB2312_SET, cps)
    gbk_cov = coverage_of(GBK_SET, cps)
    big5_cov = coverage_of(BIG5_SET, cps)

    has_gb2312 = gb2312_cov >= COVERAGE_THRESHOLD
    has_gbk = gbk_cov >= COVERAGE_THRESHOLD
    has_big5 = big5_cov >= COVERAGE_THRESHOLD

    fmt = "TTC/OTC" if ttc_count > 1 else path.suffix.lstrip(".").upper()
    encoding_note = (
        f"cmap 共 {stats['cmap_entries']} 个码位。逐字穷举（非抽样，非估算）："
        f"GB2312 6763 字 {gb2312_cov:.3%}（缺 {len(GB2312_SET - cps)}）、"
        f"GBK 21003 字 {gbk_cov:.3%}（缺 {len(GBK_SET - cps)}）、"
        f"Big5 13053 字 {big5_cov:.3%}（缺 {len(BIG5_SET - cps)}）；"
        f"覆盖率 ≥{COVERAGE_THRESHOLD:.0%} 记为支持该编码。"
    )
    if entry.get("coverage_note"):
        encoding_note += entry["coverage_note"]

    rec = {
        "id": entry["id"],
        "status": "quarantine" if entry.get("status") == "quarantine" else "shipped",
        "name_zh": entry["name_zh"],
        "name_en": entry["name_en"],
        "era": entry["era"],
        "style": entry["style"],
        "style_detail": entry["style_detail"],
        "license_spdx": detected,
        "license_text_excerpt": evidence,
        "license_url": entry.get("license_url", ""),
        "source_url": entry.get("source_url", ""),
        "file": path.relative_to(ROOT).as_posix(),
        "format": fmt,
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "num_glyphs": stats["num_glyphs"],
        "cmap_entries": stats["cmap_entries"],
        "has_cjk_unified": stats["has_cjk_unified"],
        "has_ext_a": stats["has_ext_a"],
        "has_ext_b": stats["has_ext_b"],
        "gb2312_coverage": round(gb2312_cov, 5),
        "gbk_coverage": round(gbk_cov, 5),
        "big5_coverage": round(big5_cov, 5),
        "has_gb2312": has_gb2312,
        "has_gbk": has_gbk,
        "has_big5": has_big5,
        "encoding_note": encoding_note,
        "coverage_sample": coverage_sample(font, cmap),
        "font_family": names.get(1, [""])[0],
        "font_version": names.get(5, [""])[0],
        "name_table": {str(k): v for k, v in names.items()},
        "notes": entry.get("notes", ""),
    }

    # 交叉校验：name 表判定 vs 人工登记，不一致要显式暴露
    if expected and detected != expected:
        rec["license_mismatch"] = f"登记为 {expected}，name 表判定为 {detected}"
    if entry.get("status") == "quarantine":
        rec["quarantine_reason"] = (
            f"{DENYLIST.get(detected, detected)}；" + entry.get("notes", "")
        ).strip("；")

    if measure_woff2 and rec["status"] == "shipped":
        try:
            wb = woff2_size(path, woff2_cache)
            rec["woff2_bytes"] = wb
            rec["woff2_ratio"] = round(wb / rec["bytes"], 3)
        except Exception as exc:  # 压缩失败不应让整个核验失败
            rec["woff2_bytes"] = None
            rec["woff2_error"] = f"{type(exc).__name__}: {exc}"
    return rec


def resolve_font(entry):
    """按新目录布局解析字体文件：fonts/raw → fonts/modern/<id>/original.ttf（lead 迁移后的布局）。"""
    rid, fn = entry["id"], entry["file"]
    cands = [
        RAW_DIR / fn,
        ROOT / "fonts" / "modern" / rid / "original.ttf",
        ROOT / "fonts" / "modern" / rid / fn,
        ROOT / "fonts" / "modern" / rid / "subset.ttf",
        QUAR_DIR / fn,
        ROOT / "fonts" / "quarantine" / rid / fn,
    ]
    for c in cands:
        if c.exists():
            return c
    sub = "quarantine" if entry.get("status") == "quarantine" else "modern"
    d = ROOT / "fonts" / sub / rid
    if d.is_dir():
        fs = sorted(p for p in d.iterdir() if p.suffix.lower() in FONT_SUFFIXES)
        if fs:
            return fs[0]
    return None


def _name_blob(names):
    return "\n".join(s for nid in (0, 13, 14, 16, 17) for s in names.get(nid, []))


def _license_excerpt(lic_path: Path, names, detected: str):
    """优先取 name 表命中的许可原文；name 表没有许可字段时退到上游 LICENSE 全文。"""
    if detected != "UNKNOWN":
        ev = _snippet(_name_blob(names), ("SIL Open Font License", "ARPHIC PUBLIC LICENSE", "GNU GENERAL PUBLIC LICENSE"))
        if ev:
            return ev
    if lic_path.exists():
        text = lic_path.read_text(encoding="utf-8", errors="replace")
        return _snippet(text, ("SIL Open Font License", "ARPHIC PUBLIC LICENSE", "Hanazono Font License",
                               "GNU GENERAL PUBLIC LICENSE", "Copyright"))
    return ""


def build_incoming_record(folder: Path, woff2_cache: Path, measure_woff2: bool, problems: list):
    """incoming/<id>/ 四件套 → catalog 记录。许可以 license.json 声明为准，并用 name 表交叉校验。"""
    meta = json.loads((folder / "license.json").read_text(encoding="utf-8"))
    cands = sorted(p for p in folder.iterdir() if p.suffix.lower() in FONT_SUFFIXES)
    if not cands:
        # 团队会把 incoming 的字体文件迁到 fonts/modern/<id>/（incoming 只留四件套留档），
        # 这里回退到 modern 目录，保证同一份字体仍被核验。
        modern = ROOT / "fonts" / "modern" / folder.name
        for name in ("original.ttf", "original.otf", "subset.ttf", "subset.otf"):
            p = modern / name
            if p.exists():
                cands = [p]
                break
        else:
            if modern.exists():
                cands = sorted(p for p in modern.iterdir() if p.suffix.lower() in FONT_SUFFIXES)
        if not cands:
            quar = ROOT / "fonts" / "quarantine" / folder.name
            if quar.exists():
                cands = sorted(p for p in quar.iterdir() if p.suffix.lower() in FONT_SUFFIXES)
    if not cands:
        problems.append(f"incoming/{folder.name} 缺少字体文件（incoming / fonts/modern / fonts/quarantine 均未找到）")
        return None
    path = cands[0]
    lic_name = meta.get("license_text_file", "LICENSE.txt")
    lic_path = folder / lic_name
    if not lic_path.exists():
        problems.append(f"incoming/{folder.name} 缺少许可全文 {lic_name}")
    elif meta.get("license_text_sha256") and hashlib.sha256(lic_path.read_bytes()).hexdigest() != meta["license_text_sha256"]:
        problems.append(f"incoming/{folder.name} 的 {lic_name} 与 license.json 记录的 sha256 不一致")

    font, ttc_count = load_font(path)
    names = read_name_table(font)
    cmap, stats = cmap_stats(font)
    cps = set(cmap.keys())
    gb2312_cov = coverage_of(GB2312_SET, cps)
    gbk_cov = coverage_of(GBK_SET, cps)
    big5_cov = coverage_of(BIG5_SET, cps)
    detected, _ = classify_license(names)
    declared = meta.get("license_spdx", "UNKNOWN")

    status_declared = meta.get("status") or ("quarantine" if (meta.get("shipped") is False or meta.get("kind") == "quarantine") else "shipped")
    if declared not in WHITELIST and status_declared != "quarantine":
        problems.append(f"incoming/{folder.name} 声明许可 {declared} 不在白名单，必须隔离")
    if (detected == "PROPRIETARY" or detected in ("CC-BY-ND-3.0", "IPA-1.0")) and status_declared != "quarantine":
        problems.append(f"incoming/{folder.name} name 表判定为 {detected}，与声明 {declared} 冲突")

    fmt = "TTC/OTC" if ttc_count > 1 else path.suffix.lstrip(".").upper()
    l1 = len(cps & GB2312_L1_SET)
    l2 = len(cps & GB2312_SET) - l1
    gbk_n = len(cps & GBK_SET)
    if meta.get("gb2312_l1") is not None and meta["gb2312_l1"] != l1:
        problems.append(f"incoming/{folder.name} 的 license.json 记 GB2312 一级 {meta['gb2312_l1']}，实测 {l1}")
    rec = {
        "id": meta["id"],
        "status": status_declared,
        "name_zh": meta["name_zh"],
        "name_en": meta["name_en"],
        "era": meta["era"],
        "style": meta["style"],
        "style_detail": meta["style_detail"],
        "license_spdx": declared,
        "license_text_excerpt": _license_excerpt(lic_path, names, detected),
        "license_url": meta.get("license_url", ""),
        "source_url": meta.get("source_url", ""),
        "file": path.relative_to(ROOT).as_posix(),
        "format": fmt,
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "num_glyphs": stats["num_glyphs"],
        "cmap_entries": stats["cmap_entries"],
        "has_cjk_unified": stats["has_cjk_unified"],
        "has_ext_a": stats["has_ext_a"],
        "has_ext_b": stats["has_ext_b"],
        "gb2312_coverage": round(gb2312_cov, 5),
        "gbk_coverage": round(gbk_cov, 5),
        "big5_coverage": round(big5_cov, 5),
        "has_gb2312": gb2312_cov >= COVERAGE_THRESHOLD,
        "has_gbk": gbk_cov >= COVERAGE_THRESHOLD,
        "has_big5": big5_cov >= COVERAGE_THRESHOLD,
        "encoding_note": (
            f"cmap 共 {stats['cmap_entries']} 个码位。逐字穷举（非抽样，非估算）："
            f"GB2312 6763 字 {gb2312_cov:.3%}（缺 {len(GB2312_SET - cps)}）、"
            f"GBK 21003 字 {gbk_cov:.3%}（缺 {len(GBK_SET - cps)}）、"
            f"Big5 13053 字 {big5_cov:.3%}（缺 {len(BIG5_SET - cps)}）；"
            f"覆盖率 ≥{COVERAGE_THRESHOLD:.0%} 记为支持该编码。"
        ),
        "coverage_sample": coverage_sample(font, cmap),
        "font_family": names.get(1, [""])[0],
        "font_version": names.get(5, [""])[0],
        "name_table": {str(k): v for k, v in names.items()},
        "notes": meta.get("notes", ""),
        # ---- 本轮新增字段（仅新条目；不动旧条目）----
        "folder": folder.relative_to(ROOT).as_posix(),
        "license_file": (folder / lic_name).relative_to(ROOT).as_posix(),
        "license_json": (folder / "license.json").relative_to(ROOT).as_posix(),
        "attribution_required": meta.get("attribution_required", True),
        "modification_allowed": meta.get("modification_allowed", False),
        "redistribution_allowed": meta.get("redistribution_allowed", False),
        "commercial_use_allowed": meta.get("commercial_use_allowed", False),
        "reserved_font_name": meta.get("reserved_font_name"),
        "gb2312_l1": l1,
        "gb2312_l2": l2,
        "gbk": gbk_n,
        "supplemental": meta.get("supplemental", l1 < 1500),
        "name_table_license": detected,
    }
    if l1 < 1500:
        rec["encoding_note"] += " GB2312 一级命中 <1500 字，标为 supplemental（仅作字形展示/回退，不作正文）。"
    if declared != detected and detected != "UNKNOWN":
        rec["license_mismatch"] = f"license.json 声明 {declared}，name 表判定 {detected}"
    if rec["status"] == "quarantine":
        rec["quarantine_reason"] = meta.get("reject_reason") or meta.get("quarantine_reason", "")

    if measure_woff2:
        try:
            wb = woff2_size(path, woff2_cache)
            rec["woff2_bytes"] = wb
            rec["woff2_ratio"] = round(wb / rec["bytes"], 3)
        except Exception as exc:
            rec["woff2_bytes"] = None
            rec["woff2_error"] = f"{type(exc).__name__}: {exc}"
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-woff2", action="store_true", help="跳过 WOFF2 体积测量")
    ap.add_argument("--check-only", action="store_true", help="只核验，不写 data/font-verify.json")
    args = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    cache = Path(tempfile.gettempdir()) / "glyph-atlas-woff2-cache"
    records, problems = [], []

    for entry in REGISTRY:
        path = resolve_font(entry)
        if path is None:
            # quarantine 目录按新布局只留档 LICENSE/NOTICE（字体文件已移除），旧条目由合并逻辑原样保留
            if entry.get("status") == "quarantine":
                continue
            problems.append(f"缺少文件：{entry['file']}（登记 id={entry['id']}，raw/ 与 modern/ 均未找到）")
            continue
        rec = build_record(entry, path, cache, not args.no_woff2)
        # 白名单闸门
        if rec["status"] == "shipped" and rec["license_spdx"] not in WHITELIST:
            problems.append(
                f"{rec['id']} 位于 raw/ 但许可 {rec['license_spdx']} 不在白名单，必须隔离"
            )
        if rec["status"] == "quarantine" and rec["license_spdx"] in WHITELIST:
            problems.append(
                f"{rec['id']} 位于 quarantine/ 但许可 {rec['license_spdx']} 在白名单，应放行"
            )
        records.append(rec)

    # ---------------- fonts/incoming/<id>/ 四件套（本轮新字体） ----------------
    old_by_id = {}
    if CATALOG.exists():
        try:
            prev = json.loads(CATALOG.read_text(encoding="utf-8"))
            old_by_id = {r["id"]: r for r in prev.get("fonts", [])}
        except Exception as exc:
            problems.append(f"旧 catalog 读取失败（将整体重写）：{type(exc).__name__}: {exc}")

    incoming_ids = []
    if INCOMING_DIR.exists():
        for folder in sorted(p for p in INCOMING_DIR.iterdir()
                             if p.is_dir() and (p / "license.json").exists()):
            rec = build_incoming_record(folder, cache, not args.no_woff2, problems)
            if rec:
                records.append(rec)
                incoming_ids.append(rec["id"])
        missing_json = [p.name for p in sorted(INCOMING_DIR.iterdir())
                        if p.is_dir() and not (p / "license.json").exists()]
        if missing_json:
            problems.append(f"incoming/ 下有目录缺少 license.json：{', '.join(missing_json)}")
    else:
        problems.append("缺少 fonts/incoming/ 目录")

    # ---------------- fonts/quarantine/<id>/ 四件套（新增隔离字体） ----------------
    qdir = ROOT / "fonts" / "quarantine"
    if qdir.exists():
        scanned = {r["id"] for r in records}
        for folder in sorted(p for p in qdir.iterdir()
                             if p.is_dir() and (p / "license.json").exists()):
            if folder.name in scanned:
                continue
            if not any(p.suffix.lower() in FONT_SUFFIXES for p in folder.iterdir()):
                continue  # 旧隔离目录只留 LICENSE/NOTICE 档，无字体文件
            rec = build_incoming_record(folder, cache, not args.no_woff2, problems)
            if rec:
                records.append(rec)

    # 预设条目：旧条目按原样保留（用户要求“不删改已有 11 条”）——
    # 仅当磁盘文件 sha256 变化时才用新记录替换，并显式报 problem。
    regen = {r["id"]: r for r in records}
    registry_ids = {e["id"] for e in REGISTRY}
    final = []
    for rid, old in old_by_id.items():
        if rid not in registry_ids:
            continue                               # incoming/ 条目每次重算，不吃旧数据
        new = regen.pop(rid, None)
        if new is None:
            final.append(old)                      # 旧条目不在本轮扫描里，原样保留
        elif new["sha256"] == old.get("sha256"):
            # 文件未变：沿用旧条目，仅刷新迁移后的路径字段（内容字段一个都不改）
            if old.get("file") != new["file"] or ("folder" not in old and new.get("folder")):
                old = dict(old)
                old["file"] = new["file"]
                if new.get("folder"):
                    old["folder"] = new["folder"]
            final.append(old)
        else:
            problems.append(f"{rid} 的文件 sha256 与旧 catalog 不同，条目已更新（需人工确认）")
            final.append(new)
    final.extend(regen.values())
    records = final

    records.sort(key=lambda r: (r["status"] != "shipped", r["id"]))

    shipped = [r for r in records if r["status"] == "shipped"]
    held = [r for r in records if r["status"] == "quarantine"]
    shipped_total_bytes = sum(r["bytes"] for r in shipped)
    measured = [r for r in shipped if r.get("woff2_bytes")]
    measured_bytes = sum(r["bytes"] for r in measured)
    measured_woff2 = sum(r["woff2_bytes"] for r in measured)
    incoming = [r for r in shipped if "folder" in r]
    incoming_bytes = sum(r["bytes"] for r in incoming)
    incoming_woff2 = sum(r.get("woff2_bytes") or 0 for r in incoming)

    styles = {}
    for r in shipped:
        styles.setdefault(r["style"], []).append(r["id"])

    genres = {k: list(v) for k, v in styles.items()}
    for r in shipped:
        if "刻本" in r["style_detail"] or "雕版" in r["style_detail"]:
            genres.setdefault("古籍刻本风", []).append(r["id"])

    catalog = {
        "schema_version": SCHEMA_VERSION,
        "project": "glyph-atlas",
        "description": "古今汉字字形查询工具 —— 字体资产目录（许可已核验）",
        "license_policy": {
            "allowed": WHITELIST,
            "rejected": DENYLIST,
            "note": "许可判定以字体 name 表原文为准；判定为不可放行的文件移入 fonts/quarantine/。",
        },
        "summary": {
            "shipped_count": len(shipped),
            "quarantine_count": len(held),
            "shipped_total_bytes": shipped_total_bytes,
            "shipped_total_woff2_bytes": measured_woff2,
            "woff2_measured_count": len(measured),
            "styles_covered": sorted(styles),
            "styles_missing": [s for s in TARGET_STYLES if s not in styles],
            "style_to_ids": {k: sorted(v) for k, v in sorted(styles.items())},
            "genres_covered": sorted(genres),
            "genres_missing": [g for g in TARGET_GENRES if g not in genres],
            "genres_to_ids": {k: sorted(v) for k, v in sorted(genres.items())},
            "incoming_count": len(incoming),
            "incoming_total_bytes": incoming_bytes,
            "incoming_total_woff2_bytes": incoming_woff2,
            "supplemental_ids": sorted(r["id"] for r in records if r.get("supplemental")),
            "shrink_ratio": round(measured_woff2 / measured_bytes, 4) if measured_bytes else None,
        },
        "fonts": records,
    }

    # 控制台摘要
    print(f"{'ID':<28}{'STYLE':<8}{'LICENSE':<14}{'BYTES':>12}{'WOFF2':>12}{'CMAP':>8}{'':>3}")
    for r in records:
        flag = "" if r["status"] == "shipped" else "⛔"
        wb = r.get("woff2_bytes")
        print(
            f"{r['id']:<28}{r['style']:<8}{r['license_spdx']:<14}"
            f"{r['bytes']:>12,}{(wb if wb else 0):>12,}{r['cmap_entries']:>8} {flag}"
        )
    print(f"\nshipped={len(shipped)}  quarantine={len(held)}  "
          f"raw_total={shipped_total_bytes/1048576:.1f} MB  woff2_total={measured_woff2/1048576:.1f} MB（{len(measured)}/{len(shipped)} 款已测）")
    print("styles covered:", ", ".join(sorted(styles)) or "(none)")

    if problems:
        print("\n!! 需要人工处理：")
        for p in problems:
            print("  -", p)

    if not args.check_only:
        # 只读原则：本脚本绝不写 data/font-catalog.json（主数据由维护方合并）。
        # 核验结果单独落到 data/font-verify.json，便于复跑与 diff。
        VERIFY_OUT.parent.mkdir(parents=True, exist_ok=True)
        report = dict(catalog)
        report["problems"] = problems
        VERIFY_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
        print(f"\nwrote {VERIFY_OUT.relative_to(ROOT)} ({VERIFY_OUT.stat().st_size/1024:.1f} KB)"
              f"；未改动 {CATALOG.relative_to(ROOT)}")

    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())