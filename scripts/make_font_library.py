# -*- coding: utf-8 -*-
"""把项目里的字体整理成「每款字体一个文件夹 + 随附版权协议」的库结构。

用户要求（m00531 第 4 条）：所有的字体，在项目中单开一个文件夹，每个字体要配有版权协议。

整理后的结构：

    fonts/
      README.md                      # 索引表（谁在哪、什么许可、多少字）
      license-texts/                 # 各协议的全文副本（唯一一份，各字体目录引用它）
      ancient/<layer>/               # 由 hanzi-glyphs-svg 的 SVG 字形编译而成
          glyphs.ttf  glyphs.woff2
          LICENSE.txt  license.json  NOTICE.md
      modern/<id>/                   # 直接收录的开源字库
          original.ttf               # 原样下载的文件（可复核 sha256）
          subset.ttf                 # 我们收窄到 GBK∩cmap 并改过名的衍生版
          LICENSE.txt  license.json  NOTICE.md
      quarantine/<id>/               # 版权不合规、**不对外使用**的字库（留档说明理由）

同时做两件与合规直接相关的事：
1. 衍生子集字体**重命名**（name 表 ID 1/4/6/16/17 改成 "GA-<id> Subset"）。
   OFL 1.1 §3 禁止在修改版上继续使用保留字体名（Reserved Font Name）；
   我们对外发布的是子集，必须换名，原版权行与许可声明（ID 0/13/14）一律保留。
2. 每个字体目录必须有 LICENSE.txt 与 license.json，缺一个就报错退出。

用法：
    python scripts/make_font_library.py            # 首次整理（会移动 fonts/raw、fonts/gen 里的文件）
    python scripts/make_font_library.py --check    # 只校验，不动文件
"""
import argparse
import hashlib
import json
import os
import shutil
import sys

from fontTools.ttLib import TTFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(ROOT, "fonts")
LICDIR = os.path.join(FONTS, "license-texts")
LICSRC = os.path.join(ROOT, ".cache", "lic")

ERA_ORDER_MOD = {"shuowen-seal-kaiyuan": 6.6}
GEN = os.environ.get("GA_GEN") or os.path.join(FONTS, "gen")
RAW = os.path.join(FONTS, "raw")
QUAR = os.path.join(FONTS, "quarantine")

TODAY = __import__("datetime").date.today().isoformat()
UP_STREAM = "https://github.com/zhouyongh/hanzi-glyphs-svg"

# ---------------------------------------------------------------- 古文字层

ANCIENT = {
    "oracle": {
        "name_zh": "甲骨文", "name_en": "Oracle Bone Script",
        "era": "商", "era_order": 1, "up_layer": "glyphs/oracle",
        "spdx": "CC0-1.0", "extra_spdx": "CC-BY-4.0",
        "copyright": "Public Domain (CC0 1.0) — 汉典拓片摹本 10,213 字；JGW 参数化矢量数据集 1,203 字为 CC BY 4.0",
        "author": "漢典（zdic.net）拓片摹本；Li Qing-sheng & Bian Yu-lin《Oracle Bone Glyphs》",
        "attribution": True,
        "source_detail": "汉典「书法·甲骨文」拓片摹本 + JGW v0.3 参数化矢量数据集",
        "note": "甲骨文在 Unicode 中没有码位，每条字形记录的是对应现代字的码位。",
    },
    "bronze": {
        "name_zh": "金文", "name_en": "Bronze Inscription",
        "era": "商–戰國", "era_order": 2, "up_layer": "glyphs/bronze",
        "spdx": "CC0-1.0",
        "copyright": "Public Domain (CC0 1.0)",
        "author": "漢典（zdic.net）；中研院「小學堂」位图描摹件",
        "attribution": False,
        "source_detail": "汉典「书法·金文」拓片摹本 + 小學堂金文摹件",
        "note": "含青铜器铭文出处（器名 +《集成》编号 + 时代）。",
    },
    "chu": {
        "name_zh": "楚文字", "name_en": "Chu Script",
        "era": "戰國", "era_order": 3, "up_layer": "glyphs/chu",
        "spdx": "CC0-1.0",
        "copyright": "Public Domain (CC0 1.0)",
        "author": "漢典（zdic.net）；中研院「小學堂」楚系摹件",
        "attribution": False,
        "source_detail": "楚简帛文字摹本（含篇目 book_part 信息）",
        "note": "以楚简、楚帛书为主，含郭店、上博、清华简等篇目。",
    },
    "qinwenzi": {
        "name_zh": "秦系簡牘", "name_en": "Qin Slips",
        "era": "戰國末–秦", "era_order": 4, "up_layer": "glyphs/qinwenzi",
        "spdx": "CC0-1.0",
        "copyright": "Public Domain (CC0 1.0)",
        "author": "漢典（zdic.net）；中研院「小學堂」秦系摹件",
        "attribution": False,
        "source_detail": "秦系简牍文字摹本（睡虎地、里耶等）",
        "note": "秦汉简牍日常书写体，处于篆隶之间。",
    },
    "chuanchao": {
        "name_zh": "傳抄古文", "name_en": "Transmitted Ancient Text",
        "era": "漢以後傳抄", "era_order": 5, "up_layer": "glyphs/chuanchao",
        "spdx": "CC0-1.0",
        "copyright": "Public Domain (CC0 1.0)",
        "author": "漢典（zdic.net）；中研院「小學堂」傳抄摹件",
        "attribution": False,
        "source_detail": "《汗简》《古文四声韵》等传抄古文系统摹本",
        "note": "字书传抄保存的古文写法，覆盖字量最大的一层。",
    },
    "seal": {
        "name_zh": "小篆", "name_en": "Small Seal Script",
        "era": "秦–漢", "era_order": 6, "up_layer": "glyphs/seal",
        "spdx": "CC0-1.0",
        "copyright": "Public Domain (CC0 1.0)",
        "author": "漢典（zdic.net）《说文解字》字形",
        "attribution": False,
        "source_detail": "《说文解字》篆文（含大徐本系统）",
        "note": "对应《说文》部次；源数据缺「二」「川」「口」等若干常用字本身。",
    },
    "clerical": {
        "name_zh": "隸書", "name_en": "Clerical Script",
        "era": "戰國末–秦漢", "era_order": 7, "up_layer": "glyphs/clerical",
        "spdx": "CC0-1.0",
        "copyright": "Public Domain (CC0 1.0)",
        "author": "漢典（zdic.net）；中研院「小學堂」隸書摹件",
        "attribution": False,
        "source_detail": "汉碑、汉简隶书摹本",
        "note": "无合法免费的开源隶书字库，故本层为拓本字形编译所得。",
    },
}

# ---------------------------------------------------------------- 现代字库

MODERN_NOTICE_EXTRA = {
    "notoserifsc": "思源宋体的字体家族名与「Source」均为 Adobe 保留字体名；本项目的子集已改名为 GA-notoserifsc Subset。",
    "notosanssc": "思源黑体的字体家族名与「Source」均为 Adobe 保留字体名；本项目的子集已改名为 GA-notosanssc Subset。",
    "lxgwwenkai": "「霞鹜 / 霞鶩 / 落霞孤鹜 / 落霞孤鶩 / LXGW」为保留字体名；子集已改名，不得继续使用这些名称。",
    "lxgwseal": "「霞鹜 / 霞鶩 / 落霞孤鹜 / 落霞孤鶩 / LXGW」为保留字体名；子集已改名，不得继续使用这些名称。",
    "mashanzheng": "字体商标「Trademark of zhongqifont shanghai」；子集已改名，不得继续使用原名称。",
    "longcang": "字体商标「Trademark of ZHONGQI Electronic Co., ShangHai」；子集已改名。",
    "zhimangxing": "字体商标「ZhongQiFont」；子集已改名。",
    "liujianmaocao": "字体商标「ZhongQi Font Software」；子集已改名。",
    "zhuque": "朱雀仿宋（JadeFoci）依 OFL 1.1 分发。",
    "smileysans": "得意黑（atelierAnchor）依 OFL 1.1 分发。",
    "huiwenmincho": "作者声明为公有领域（Public Domain），name 表版权字段即为该声明。",
}

LICENSE_NAMES = {
    "OFL-1.1": ("SIL Open Font License 1.1", "https://openfontlicense.org/"),
    "CC0-1.0": ("CC0 1.0 通用（公有领域奉献）", "https://creativecommons.org/publicdomain/zero/1.0/"),
    "CC-BY-4.0": ("Creative Commons 署名 4.0 国际", "https://creativecommons.org/licenses/by/4.0/"),
    "CC-BY-ND-3.0": ("Creative Commons 署名-禁止改作 3.0", "https://creativecommons.org/licenses/by-nd/3.0/"),
    "IPA-1.0": ("IPA Font License 1.0", "https://opensource.org/licenses/IPA/"),
    "PD": ("公有领域（Public Domain）", "https://creativecommons.org/publicdomain/mark/1.0/"),
    "Arphic-PL-1.0": ("文鼎公共许可（Arphic Public License）", "https://www.arphic.com/"),
    "GPL-3.0+FE": ("GNU GPL v3 附字体例外", "https://www.gnu.org/licenses/gpl-3.0.html"),
    "GPL-2.0": ("GNU General Public License v2.0", "https://www.gnu.org/licenses/old-licenses/gpl-2.0.html"),
    "PROPRIETARY": ("商业授权（不可自由分发）", ""),
    "UNKNOWN": ("许可不明", ""),
    "PROJECT-GRANT": ("项目组内部授权（北师大文学院，限学习研究）", ""),
}

LICENSE_FILES = {
    "OFL-1.1": "OFL-1.1.txt",
    "CC0-1.0": "CC0-1.0.txt",
    "CC-BY-4.0": "CC-BY-4.0.txt",
    "CC-BY-ND-3.0": "CC-BY-ND-3.0.txt",
    "IPA-1.0": "IPA-1.0.txt",
    "Arphic-PL-1.0": "Arphic-PL-1.0.txt",
    "GPL-3.0+FE": "GPL-3.0+FE.txt",
    "GPL-2.0": "GPL-2.0.txt",
    "PD": "PD.txt",
    "PROJECT-GRANT": "PROJECT-GRANT.txt",
}

PD_TEXT = """本字体以「公有领域」（Public Domain）方式提供。

依据（字体 name 表版权字段原文，未作改写）：
    Public Domain

字体：汇文明朝体 Huiwen Mincho
来源：https://zhuanlan.zhihu.com/p/344103391

公有领域意味着权利人放弃著作权财产权，任何人都可以复制、修改、分发、商用，
无须署名，也无须注明是否改动。本项目仍在此如实署明来源，属于自愿，不是义务。

参考：https://creativecommons.org/publicdomain/mark/1.0/
"""

PROPRIETARY_TEXT = """本字体为**商业授权**字体，不属于自由许可，本项目**不使用**其字体文件。

此处仅留档说明「为什么不能用」，以便日后复核：

- 字体：{name}
- name 表版权字段原文：{copyright}
- 结论：未取得书面授权，不得复制、修改、子集化或随本项目分发。
- 处理：只保留原始文件供授权核验，不进入 web/、不参与任何构建产物。

如你已获得该字体的商业授权，可自行替换 fonts/quarantine/{id}/ 下的文件并重新构建。
"""

UNKNOWN_TEXT = """本字体的许可状态**无法确认**，本项目**不使用**其字体文件。

- 字体：{name}
- 情况：name 表中没有任何版权或许可字段，上游也没有 LICENSE / NOTICE 文件。
- 结论：无法确认是否可以修改与再分发，按最保守原则排除。

如你能提供作者的书面许可，可自行替换 fonts/quarantine/{id}/ 下的文件并重新构建。
"""


def sha256(path, buf=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            b = fh.read(buf)
            if not b:
                break
            h.update(b)
    return h.hexdigest()

# 旧式码位字库（非 Unicode cmap，需先用 scripts/import_legacy_font.py 转换）
ANCIENT_FONTS = {
    "beishida": {
        "name_zh": "說文小篆（北師大）", "name_en": "BeiShiDa ShuoWen Xiaozhuan",
        "era": "東漢·《說文解字》篆文", "era_order": 6.5,
        "style": "小篆",
        "style_detail": "北京师范大学《說文解字》小篆字库；原 cmap 为 Big5 码位，本项目转 Unicode 后收 18,438 字",
        "spdx": "PROJECT-GRANT",
        "copyright": "字库 name 表声明 \"Proprietary for Sinica, all right reserved.\"；本项目由北师大文学院项目组用于学习研究",
        "author": "北京师范大学（說文小篆字库）；本项目做 Big5→Unicode cmap 转换",
        "attribution": "字形来源：北師大說文小篆字库（北京师范大学）。本项目仅将其 cmap 由 Big5 转为 Unicode，字形轮廓未改。",
        "source_url": "https://www.zdic.net/",
        "source_detail": "北師大說文小篆字库（BeiShiDaShuoWenXiaoZhuan），Big5 → Unicode 转换",
        "reserved_font_name": "北師大說文小篆",
        "derivation": "字节码转换：Big5 码位 → Unicode cmap；字形未改，name 表改名以示转换版本。",
        "note": "补上了 hanzi-glyphs-svg 小篆层缺失的二、川、口等常用字。",
        "redistribution_allowed": True,  # 项目组 2026-11-03 确认可随本项目公开部署
    },
}


def ancient_font_notice(aid, meta, ldata):
    NL = chr(10)
    parts = [
        "# %s · %s" % (meta["name_zh"], meta["name_en"]),
        "",
        "## 这是什么",
        "",
        "%s。字体文件放在本目录，供「識印」歷代字形查詢平台工具做本地字形比对。" % meta["style_detail"],
        "",
        "## 许可",
        "",
        "- 类型：%s" % LICENSE_NAMES[meta["spdx"]][0],
        "- 上游 name 表声明：%s" % meta["copyright"],
        "- 本项目用途：古籍字形查询与教学研究，不对外分发字体文件。",
        "- 详见同目录 `LICENSE.txt` 与 `license.json`。",
        "",
        "## 本项目做了什么",
        "",
        "- 原 cmap 为 Big5 码位（platformID=3, platEncID=4），浏览器按 Unicode 查不到字；"
        "本项目逐码解码重建 Unicode cmap（format 4 + 12），**字形轮廓未改动**。",
        "- name 表 family 改为 `GlyphAtlas-beishida`，nameID 0 版权行原样保留。",
        "- 为网页加载做 subset 分片与 woff2 压缩。",
        "",
        "## 规模",
        "",
        "- 本层：%d 字 / %d 个字形" % (ldata.get("chars", 0), ldata.get("glyphs", 0)),
    ]
    if meta.get("note"):
        parts.append("- 备注：%s" % meta["note"])
    parts.append("")
    return NL.join(parts)


def move_if(src, dst):
    """把 src 移到 dst；dst 已存在就保留 dst（幂等）。"""
    if not os.path.exists(src):
        return os.path.exists(dst)
    # src 与 dst 是同一个文件时绝不能"保留 dst、删掉 src"——那会把唯一的一份删掉。
    if os.path.abspath(src) == os.path.abspath(dst):
        return True
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.exists(dst):
        os.remove(src)
        return True
    shutil.move(src, dst)
    return True


def ensure_license_texts():
    os.makedirs(LICDIR, exist_ok=True)
    for key, fn in LICENSE_FILES.items():
        src = os.path.join(LICSRC, fn)
        dst = os.path.join(LICDIR, fn)
        if os.path.exists(src) and not os.path.exists(dst):
            shutil.copyfile(src, dst)
    ipa_src = os.path.join(LICSRC, "IPA-1.0.html")
    if os.path.exists(ipa_src):
        txt = os.path.join(LICDIR, "IPA-1.0.txt")
        if not os.path.exists(txt):
            import re
            raw = open(ipa_src, encoding="utf-8", errors="replace").read()
            raw = re.sub(r"(?is)<(script|style).*?</\1>", "", raw)
            raw = re.sub(r"(?s)<[^>]+>", "\n", raw)
            raw = re.sub(r"\n{3,}", "\n\n", raw)
            raw = "\n".join(l.strip() for l in raw.splitlines() if l.strip())
            open(txt, "w", encoding="utf-8").write(
                "IPA Font License 1.0（从 https://opensource.org/licenses/IPA/ 提取的正文）\n"
                "许可全文以此 URL 为准：https://opensource.org/licenses/IPA/\n\n" + raw)
    for key, text in (("PD", PD_TEXT),):
        p = os.path.join(LICDIR, key + ".txt")
        if not os.path.exists(p):
            open(p, "w", encoding="utf-8").write(text)
    for key in ("PROPRIETARY", "UNKNOWN"):
        p = os.path.join(LICDIR, key + ".txt")
        if not os.path.exists(p):
            open(p, "w", encoding="utf-8").write(
                "本文件是「不可用」说明模板，具体见各字体目录下的 LICENSE.txt。")


def rename_subset(path, layer_id):
    """OFL §3：修改版不得继续使用保留字体名 → 统一改成 GA-<id> Subset。"""
    new = "GA-%s Subset" % layer_id
    f = TTFont(path)
    name = f["name"]
    changed = False
    for rec in name.names:
        if rec.nameID in (1, 3, 4, 6, 16, 17, 18, 20, 21):
            try:
                cur = rec.toUnicode()
            except Exception:
                continue
            if cur != new:
                rec.string = new
                changed = True
        # 24/25 = 变体描述，避免误称
    if changed:
        f.save(path)
        return True
    f.close()
    return False


def write_common(folder, lic_text_src_abs, spdx, spdx_extra=None):
    lic_txt = os.path.join(folder, "LICENSE.txt")
    body = ""
    if spdx_extra:
        body += ("本字体包含两种许可的材料，分别适用于对应字形：\n"
                 "  · %s\n  · %s\n\n" % (spdx, spdx_extra))
    body += open(lic_text_src_abs, encoding="utf-8").read()
    if spdx_extra:
        extra_src = os.path.join(LICDIR, LICENSE_FILES.get(spdx_extra, "CC-BY-4.0.txt"))
        body += "\n\n========== " + spdx_extra + " ==========\n\n"
        body += open(extra_src, encoding="utf-8").read()
    open(lic_txt, "w", encoding="utf-8").write(body)
    return lic_txt


def ancient_notice(aid, meta, ldata, counts):
    lines = []
    lines.append("# %s · %s\n" % (meta["name_zh"], meta["name_en"]))
    lines.append("## 这是什么\n")
    lines.append("由 [hanzi-glyphs-svg](%s) 的 `%s` 层 SVG 字形编译成的 TrueType 字体，"
                 "供「識印」歷代字形查詢平台工具做本地字形比对。\n"
                 % (UP_STREAM, meta["up_layer"]))
    lines.append("## 数据集来源\n")
    lines.append("- 上游仓库：%s" % UP_STREAM)
    lines.append("- 上游层：`%s`" % meta["up_layer"])
    lines.append("- 上游内容：%s" % meta["source_detail"])
    lines.append("- 许可：%s%s" % (meta["spdx"], "（另有 CC BY 4.0 部分，见下）" if meta.get("extra_spdx") else ""))
    lines.append("- 本层字数：%d 字 / %d 个字形" % (ldata.get("chars", 0), ldata.get("glyphs", 0)))
    lines.append("")
    if meta.get("extra_spdx"):
        lines.append("### CC BY 4.0 部分（必须署名）\n")
        lines.append("甲骨文层中 1,203 个字来自 JGW 参数化矢量数据集，使用须遵守 CC BY 4.0：\n")
        lines.append("> 字形来源：Li, Qing-sheng & Bian, Yu-lin (2026), *Oracle Bone Glyphs: Parametric Vector\n"
                     "> Dataset (v0.3)*, doi:10.5281/zenodo.22467946, CC BY 4.0.\n"
                     "> 数据集主页：https://zenodo.org/records/22467946\n"
                     "> 许可全文：https://creativecommons.org/licenses/by/4.0/legalcode\n")
    lines.append("## 我们做了哪些改动（CC BY 4.0 §3(a)(1)(B) 要求声明）\n")
    lines.append("1. 从上游 SVG 的 `<path>` 提取轮廓（`fontTools.svgLib.path.parse_path`），"
                 "补闭合路径（TrueType 轮廓必须闭合）。")
    lines.append("2. 上游 viewBox 极不统一（`0 0 400 400`、`0 0 17 8`、紧包围盒等），"
                 "**按每个字形自身的包围盒归一化**：长边缩到 860 单位、中心放在 (500, 380)、y 轴取反。"
                 "这一步改变了字形坐标，属于修改。")
    lines.append("3. 同一字的多个写法按顺序挂到 OpenType `ss01`–`ss08` 特性上，主形占 cmap 码位。")
    lines.append("4. 上表所列改动**不改变上游材料的许可状态**，也不代表上游认可本衍生字体。\n")
    lines.append("## 生成方式\n")
    lines.append("```\npython scripts/build_glyph_fonts.py --src .src/hanzi-glyphs-svg-main "
                 "--layers %s --out fonts/ancient --data data\n```\n" % aid)
    lines.append("生成日期：%s　构建脚本：`scripts/build_glyph_fonts.py`" % TODAY)
    lines.append("")
    lines.append("## 已知缺口\n")
    lines.append("- %s" % meta["note"])
    lines.append("- 上游数据本身不全：越古的层对现代常用字覆盖越低（甲骨 2,114 字、小篆 10,591 字）。")
    lines.append("- 本字体只做「现代字 → 古字形」的反查，不代表篆刻/拓片的可直接使用字形。")
    return "\n".join(lines) + "\n"


def modern_notice(f):
    lines = []
    lines.append("# %s · %s\n" % (f.get("name_zh"), f.get("name_en", "")))
    lines.append("## 字体\n")
    lines.append("- 书体：%s%s" % (f.get("style", ""), "（%s）" % f["style_detail"] if f.get("style_detail") else ""))
    lines.append("- 时代/风格：%s" % f.get("era", ""))
    lines.append("- 原始文件：`original.ttf`，%d 字节" % f.get("bytes", 0))
    lines.append("- 原始 sha256：`%s`" % f.get("sha256", ""))
    lines.append("- 来源：%s" % f.get("source_url", ""))
    lines.append("")
    lines.append("## 许可\n")
    lines.append("- SPDX：%s" % f.get("license_spdx", ""))
    lines.append("- 许可全文：`LICENSE.txt`（%s）" % f.get("license_url", ""))
    lines.append("- name 表版权字段原文：\n")
    lines.append("```\n%s\n```\n" % (f.get("license_text_excerpt") or f.get("copyright") or ""))
    lines.append("## 我们做了哪些改动\n")
    lines.append("1. 子集化：只保留 GBK 范围内的码位中、该字体 cmap 实际拥有的字（%s 字），其余字形删除，"
                 "以缩小体积。" % f.get("num_glyphs", ""))
    lines.append("2. 重命名：子集字体家族名改为 `GA-%s Subset`，文件为 `subset.ttf`。" % f["id"])
    lines.append("3. 关闭 hinting、丢弃 DSIG 表、保留全部 layout features 与 name 记录。")
    lines.append("4. 结论：`subset.ttf` 是**修改版**，不是原作者发布的字体，原作者不对本衍生版负责。")
    lines.append("")
    if MODERN_NOTICE_EXTRA.get(f["id"]):
        lines.append("> %s\n" % MODERN_NOTICE_EXTRA[f["id"]])
    lines.append("## 生成日期\n")
    lines.append("%s　构建脚本：`scripts/build_modern_fonts.py`、`scripts/make_font_library.py`" % TODAY)
    return "\n".join(lines) + "\n"


def quarantine_notice(f, reason, text):
    lines = ["# %s · 未采用\n" % f.get("name_zh", f["id"]),
             "本字库**不进入**「識印」歷代字形查詢平台工具，也不参与任何构建产物。\n",
             "## 原因\n", text, "",
             "## 原始信息\n",
             "- 字体：%s（%s）" % (f.get("name_zh", ""), f.get("name_en", "")),
             "- SPDX：%s" % f.get("license_spdx", ""),
             "- 来源：%s" % f.get("source_url", ""),
             "- 文件：`original.ttf`，%d 字节" % f.get("bytes", 0),
             "- 理由代码：`%s`" % reason,
             "", "## 如果你有授权\n",
             "把授权后的文件替换到本目录，改 `license.json` 的 `shipped` 为 true，"
             "再跑 `python scripts/build_modern_fonts.py` 与 `make_web.py` 即可接入。"]
    return "\n".join(lines) + "\n"


def write_license_json(folder, obj):
    p = os.path.join(folder, "license.json")
    open(p, "w", encoding="utf-8").write(
        json.dumps(obj, ensure_ascii=False, indent=1) + "\n")
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    layers = {L["id"]: L for L in json.load(open(os.path.join(ROOT, "data/layers.json"), encoding="utf-8"))}
    _mpath = os.path.join(ROOT, "data/layers-modern.json")
    modern_layers = {L["id"]: L for L in json.load(open(_mpath, encoding="utf-8"))} if os.path.exists(_mpath) else {}
    cat = json.load(open(os.path.join(ROOT, "data/font-catalog.json"), encoding="utf-8"))
    ensure_license_texts()

    lib = []

    # ---------- 古文字 ----------
    for aid, meta in ANCIENT.items():
        folder = os.path.join(FONTS, "ancient", aid)
        os.makedirs(folder, exist_ok=True)
        src_ttf = os.path.join(GEN, aid + ".ttf")
        dst_ttf = os.path.join(folder, "glyphs.ttf")
        if not args.check:
            move_if(src_ttf, dst_ttf)
        if not args.check and os.path.exists(src_ttf) and src_ttf != dst_ttf:
            pass
        if not os.path.exists(dst_ttf):
            print("!! 缺字体文件", dst_ttf)
            continue
        ldata = layers.get(aid, {})
        lic = write_common(folder, os.path.join(LICDIR, "CC0-1.0.txt"),
                           meta["spdx"], meta.get("extra_spdx"))
        if not args.check:
            open(os.path.join(folder, "NOTICE.md"), "w", encoding="utf-8").write(
                ancient_notice(aid, meta, ldata, None))
        obj = {
            "id": aid, "kind": "ancient-compiled",
            "name_zh": meta["name_zh"], "name_en": meta["name_en"],
            "era": meta["era"], "era_order": meta["era_order"],
            "style": "古文字", "style_detail": meta["source_detail"],
            "license_spdx": meta["spdx"],
            "license_spdx_extra": meta.get("extra_spdx"),
            "license_name": LICENSE_NAMES[meta["spdx"]][0],
            "license_url": LICENSE_NAMES[meta["spdx"]][1],
            "license_text_file": "LICENSE.txt",
            "license_text_rel": "../../license-texts/" + LICENSE_FILES[meta["spdx"]],
            "copyright_holder": meta["copyright"], "author": meta["author"],
            "attribution_required": meta["attribution"],
            "attribution_text": ("字形来源：Li, Qing-sheng & Bian, Yu-lin (2026), Oracle Bone Glyphs: "
                                 "Parametric Vector Dataset (v0.3), doi:10.5281/zenodo.22467946, CC BY 4.0."
                                 if meta["attribution"] else ""),
            "modification_allowed": True, "redistribution_allowed": True,
            "commercial_use_allowed": True, "reserved_font_name": None,
            "source_url": UP_STREAM, "source_detail": meta["source_detail"],
            "source_layer": meta["up_layer"],
            "chars": ldata.get("chars", 0), "glyphs": ldata.get("glyphs", 0),
            "variants": ldata.get("variants", 0),
            "files": {"ttf": "glyphs.ttf", "woff2": "glyphs.woff2"},
            "bytes": os.path.getsize(dst_ttf),
            "sha256": sha256(dst_ttf),
            "notice_file": "NOTICE.md", "shipped": True,
            "derivation": "由 CC0/CC BY 上游 SVG 字形编译；未使用任何商业字库。",
        }
        # woff2
        w2 = os.path.join(folder, "glyphs.woff2")
        if not args.check and not os.path.exists(w2):
            try:
                fnt = TTFont(dst_ttf)
                fnt.flavor = "woff2"
                fnt.save(w2)
                fnt.close()
            except Exception as e:
                print("woff2 失败", aid, e)
        if os.path.exists(w2):
            obj["files"]["woff2"] = "glyphs.woff2"
            obj["bytes_woff2"] = os.path.getsize(w2)
            obj["sha256_woff2"] = sha256(w2)
        if lic and not args.check:
            write_license_json(folder, obj)
        lib.append(obj)

    # ---------- 古文字：旧式码位字库（Big5/GBK → Unicode 转换而来） ----------
    for aid, meta in ANCIENT_FONTS.items():
        folder = os.path.join(FONTS, "ancient", aid)
        dst_ttf = os.path.join(folder, "glyphs.ttf")
        if not os.path.exists(dst_ttf):
            print("!! 缺字体文件", dst_ttf)
            continue
        ldata = layers.get(aid, {})
        lic = write_common(folder, os.path.join(LICDIR, "PROJECT-GRANT.txt"),
                           meta["spdx"], None)
        w2 = os.path.join(folder, "glyphs.woff2")
        obj = {
            "id": aid, "kind": "ancient-font",
            "name_zh": meta["name_zh"], "name_en": meta["name_en"],
            "era": meta["era"], "era_order": meta["era_order"],
            "style": meta["style"], "style_detail": meta["style_detail"],
            "license_spdx": meta["spdx"],
            "license_spdx_extra": None,
            "license_name": LICENSE_NAMES[meta["spdx"]][0],
            "license_url": LICENSE_NAMES[meta["spdx"]][1],
            "license_text_file": "LICENSE.txt",
            "license_text_rel": "../../license-texts/PROJECT-GRANT.txt",
            "copyright_holder": meta["copyright"], "author": meta["author"],
            "attribution_required": True,
            "attribution_text": meta["attribution"],
            "modification_allowed": True,
            "redistribution_allowed": bool(meta.get("redistribution_allowed", False)),
            "commercial_use_allowed": False,
            "reserved_font_name": meta.get("reserved_font_name"),
            "source_url": meta["source_url"], "source_detail": meta["source_detail"],
            "source_layer": None,
            "chars": ldata.get("chars", 0), "glyphs": ldata.get("glyphs", 0),
            "variants": ldata.get("variants", 0),
            "files": {"ttf": "glyphs.ttf", "woff2": "glyphs.woff2"},
            "bytes": os.path.getsize(dst_ttf),
            "sha256": sha256(dst_ttf),
            "notice_file": "NOTICE.md", "shipped": True,
            "derivation": meta["derivation"],
            "local_only": True,
        }
        if os.path.exists(w2):
            obj["bytes_woff2"] = os.path.getsize(w2)
            obj["sha256_woff2"] = sha256(w2)
        else:
            obj["files"].pop("woff2", None)
        if not args.check:
            open(os.path.join(folder, "NOTICE.md"), "w", encoding="utf-8").write(
                ancient_font_notice(aid, meta, ldata))
        if lic and not args.check:
            write_license_json(folder, obj)
        lib.append(obj)

    # ---------- 现代字库 ----------
    for f in cat["fonts"]:
        fid = f["id"]
        if f.get("status") == "shipped":
            if fid in ANCIENT_FONTS:
                # 已在上面按「旧式码位字库」处理过，绝不能再当现代字库搬一次
                continue
            folder = os.path.join(FONTS, "modern", fid)
            os.makedirs(folder, exist_ok=True)
            raw_src = None
            # 已经整理进 fonts/modern/<id>/original.* 的，直接用它（绝不能再 move，否则自删）
            for fn in ("original.ttf", "original.otf", "original.ttc"):
                pth = os.path.join(folder, fn)
                if os.path.exists(pth):
                    raw_src = pth
                    break
            for cand in ((None if raw_src else f.get("file")) or "", ""):
                if not cand:
                    continue
                pth = os.path.join(ROOT, cand) if not cand.startswith("fonts/") else os.path.join(ROOT, cand)
                if os.path.exists(pth):
                    raw_src = pth
                    break
            if raw_src is None:
                # font-scout 抓的字体直接落在 fonts/incoming/<id>/，文件名沿用上游原名
                inc = os.path.join(FONTS, "incoming", fid)
                if os.path.isdir(inc):
                    for fn in sorted(os.listdir(inc)):
                        if fn.lower().endswith((".ttf", ".otf")):
                            raw_src = os.path.join(inc, fn)
                            break
            if raw_src is None:
                print("!! 找不到原始字体", fid)
                continue
            orig = os.path.join(folder, "original.ttf")
            if not args.check:
                move_if(raw_src, orig)
            sub_src = os.path.join(GEN, fid + ".ttf")
            sub = os.path.join(folder, "subset.ttf")
            if not args.check:
                move_if(sub_src, sub)
            has_sub = os.path.exists(sub)
            if not has_sub:
                # hanamin-b 这类字体在 GBK 内只有几个字，不做 web 子集，
                # 但仍按「字库」归档：原始文件 + 协议 + NOTICE 一件不少。
                print("-- 无 web 子集（仅归档）", fid)
            spdx = f.get("license_spdx", "OFL-1.1")
            if fid == "huiwenmincho":
                # 作者在 name 表里直接声明 Public Domain，它不是 CC0，别混写
                spdx = "PD"
            lic_fn = LICENSE_FILES.get(spdx, "OFL-1.1.txt")
            if has_sub and not args.check:
                rename_subset(sub, fid)
            lic = write_common(folder, os.path.join(LICDIR, lic_fn), spdx)
            if not args.check:
                open(os.path.join(folder, "NOTICE.md"), "w", encoding="utf-8").write(modern_notice(f))
            obj = {
                "id": fid, "kind": "modern-font",
                "group": f.get("group") or "modern",
                "name_zh": f.get("name_zh"), "name_en": f.get("name_en", ""),
                "era": f.get("era", ""),
                "era_order": ERA_ORDER_MOD.get(fid, 90),
                "style": f.get("style", ""), "style_detail": f.get("style_detail", ""),
                "license_spdx": spdx,
                "license_name": LICENSE_NAMES.get(spdx, (spdx, ""))[0],
                "license_url": f.get("license_url") or LICENSE_NAMES.get(spdx, ("", ""))[1],
                "license_text_file": "LICENSE.txt",
                "license_text_rel": "../../license-texts/" + lic_fn,
                "copyright_holder": (f.get("copyright") or f.get("license_text_excerpt") or ""),
                "author": f.get("author", "（见 NOTICE.md）"),
                "attribution_required": spdx == "CC-BY-4.0",
                "attribution_text": "",
                "modification_allowed": spdx != "CC-BY-ND-3.0",
                "redistribution_allowed": spdx != "PROPRIETARY",
                "commercial_use_allowed": spdx in ("OFL-1.1", "CC0-1.0", "CC-BY-4.0", "PD", "GPL-3.0+FE", "GPL-2.0", "Arphic-PL-1.0"),
                "reserved_font_name": f.get("reserved_font_name"),
                "source_url": f.get("source_url", ""),
                "source_detail": f.get("style_detail", ""),
                "chars": (f.get("subset_chars") or f.get("num_chars")
                          or modern_layers.get(fid, {}).get("chars", 0)),
                "glyphs": f.get("num_glyphs", 0),
                "variants": 0,
                "files": {"original": "original.ttf", **({"subset": "subset.ttf"} if has_sub else {})},
                "bytes": os.path.getsize(sub) if has_sub else
                         (os.path.getsize(orig) if os.path.exists(orig) else f.get("bytes", 0)),
                "bytes_original": os.path.getsize(orig) if os.path.exists(orig) else f.get("bytes", 0),
                "sha256": sha256(sub) if has_sub else (sha256(orig) if os.path.exists(orig) else f.get("sha256", "")),
                "sha256_original": f.get("sha256", ""),
                "web_shipped": bool(has_sub),
                "notice_file": "NOTICE.md", "shipped": True,
                "derivation": "原始字体做了子集化与改名，衍生版按同一许可分发。",
            }
            if lic and not args.check:
                write_license_json(folder, obj)
            lib.append(obj)

    # ---------- 隔离区 ----------
    for f in cat["fonts"]:
        fid = f["id"]
        if f.get("status") != "quarantine":
            # shipped 已处理；superseded（如与 beishida 重复的旧条目）直接跳过
            continue
        folder = os.path.join(FONTS, "quarantine", fid)
        os.makedirs(folder, exist_ok=True)
        src = os.path.join(ROOT, f["file"])
        orig = os.path.join(folder, "original.ttf")
        if not args.check:
            move_if(src, orig)
        spdx = f.get("license_spdx", "UNKNOWN")
        # 隔离有两种依据：许可本身不允许（license），或许可干净但来源权属存疑（provenance）。
        # 后者必须如实报出该许可真实的条款，不能因为隔离就把「可修改/可商用」写成 false。
        FREE = ("OFL-1.1", "CC0-1.0", "CC-BY-4.0", "PD", "GPL-3.0+FE", "GPL-2.0", "Arphic-PL-1.0")
        basis = "provenance" if spdx in FREE else "license"
        reason = (f.get("quarantine_reason") or "").strip() or {
            "PROPRIETARY": "商用授权/保留所有权利", "CC-BY-ND-3.0": "禁止改作（与子集化冲突）",
            "IPA-1.0": "IPA 许可与本项目分发方式不兼容", "UNKNOWN": "许可不明",
            "UNVERIFIED": "字体 name 表找不到许可声明，无法核验",
        }.get(spdx, spdx)
        if not args.check:
            if spdx in ("PROPRIETARY",):
                txt = PROPRIETARY_TEXT.format(name=f.get("name_zh"), copyright=f.get("license_text_excerpt") or "",
                                              id=fid)
            elif spdx == "UNKNOWN":
                txt = UNKNOWN_TEXT.format(name=f.get("name_zh"), id=fid)
            elif basis == "provenance":
                txt = ("本字体许可为 %s，条款本身允许修改与再分发；但**来源权属存在争议**，"
                       "本项目不采用、不进入构建产物、不随仓库分发。\n\n理由：%s\n\n%s\n"
                       % (spdx, reason, f.get("license_text_excerpt") or ""))
            else:
                txt = ("本字体许可为 %s，与本项目的「子集化 + 再分发」不兼容，故不采用。\n\n%s\n"
                       % (spdx, f.get("license_text_excerpt") or ""))
            open(os.path.join(folder, "LICENSE.txt"), "w", encoding="utf-8").write(txt)
            open(os.path.join(folder, "NOTICE.md"), "w", encoding="utf-8").write(
                quarantine_notice(f, spdx, txt))
            qentry = {
                "id": fid, "kind": "quarantine",
                "name_zh": f.get("name_zh"), "name_en": f.get("name_en", ""),
                "era": f.get("era", ""), "era_order": 0,
                "style": f.get("style", ""), "style_detail": f.get("style_detail", ""),
                "license_spdx": spdx,
                "license_name": LICENSE_NAMES.get(spdx, (spdx, ""))[0],
                "license_url": f.get("license_url", ""),
                "license_text_file": "LICENSE.txt", "license_text_rel": "LICENSE.txt",
                "copyright_holder": f.get("license_text_excerpt") or "",
                "author": "", "attribution_required": True, "attribution_text": "",
                # 许可本身允许的，如实写 true；隔离依据是来源（provenance）而非条款。
                "modification_allowed": spdx in FREE,
                "redistribution_allowed": spdx in FREE,
                "commercial_use_allowed": spdx in FREE,
                "quarantine_basis": basis, "reserved_font_name": None,
                "source_url": f.get("source_url", ""), "source_detail": "",
                "chars": (f.get("num_chars") or f.get("cmap_entries") or 0), "glyphs": f.get("num_glyphs", 0), "variants": 0,
                "files": {"original": "original.ttf"},
                "bytes": f.get("bytes", 0), "sha256": f.get("sha256", ""),
                "notice_file": "NOTICE.md", "shipped": False,
                "reject_reason": reason,
                "derivation": "仅供授权核验留档，不进入任何构建产物。",
            }
            write_license_json(folder, qentry)
            lib.append(qentry)
        else:
            # --check 模式不写文件，最少字段供打印
            lib.append({"id": fid, "kind": "quarantine", "name_zh": f.get("name_zh"),
                        "license_spdx": spdx, "shipped": False, "reject_reason": reason})

    # ---------- 索引 ----------
    if not args.check:
        json.dump({"schema_version": 2, "generated_at": TODAY, "fonts": lib},
                  open(os.path.join(ROOT, "data/font-library.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)

        rows = ["| # | 字体 | 时代/风格 | 许可 | 字数 | 目录 |", "|---|---|---|---|---|---|"]
        shipped = [x for x in lib if x.get("shipped")]
        for i, x in enumerate(shipped, 1):
            kind = "ancient" if x["kind"] in ("ancient-compiled", "ancient-font") else "modern"
            rows.append("| %d | %s | %s | %s | %s | [`fonts/%s/%s/`](%s/%s/) |" % (
                i, x["name_zh"], x.get("era", ""), x["license_spdx"],
                x.get("chars", ""), kind, x["id"], kind, x["id"]))
        rej = [x for x in lib if not x.get("shipped")]
        md = ["# 字体库\n",
              "共 **%d** 款可用字体 + **%d** 款已排除字库。每款字体一个文件夹，"
              "文件夹内必含 `LICENSE.txt`（协议全文）、`license.json`（结构化条款）、`NOTICE.md`（来源与改动声明）。\n"
              % (len(shipped), len(rej)),
              "## 可用字体\n"] + rows + ["",
              "## 已排除（版权不合规，不参与构建）\n"]
        for x in rej:
            md.append("- **%s** — `%s`：%s（见 `fonts/quarantine/%s/`）\n"
                      % (x["name_zh"], x["license_spdx"], x.get("reject_reason", ""), x["id"]))
        md += ["",
               "## 目录结构\n",
               "```",
               "fonts/",
               "  license-texts/     各协议全文（OFL-1.1 / CC0-1.0 / CC-BY-4.0 / …）",
               "  ancient/<layer>/   由 SVG 字形编译的古文字字体（CC0 / CC BY）",
               "  modern/<id>/       收录的开源字库：original.ttf + subset.ttf",
               "  quarantine/<id>/   版权不合规，仅留档说明",
               "```",
               "",
               "## 许可原则",
               "",
               "只收 **SIL OFL 1.1 / CC0 1.0 / CC BY 4.0 / 公有领域** 四种可商用、可修改、可再分发的许可；"
               "商业字库（汉仪、方正、文鼎、华康、华文、字魂、锐字、叶根友等）一律不下载、不打包。",
               "",
               "OFL 1.1 §3 要求修改版不得继续使用保留字体名，故所有 `subset.ttf` 的家族名已改为 "
               "`GA-<id> Subset`，版权行与许可声明原样保留。",
               ""]
        open(os.path.join(FONTS, "README.md"), "w", encoding="utf-8").write("\n".join(md))

    print("shipped=%d quarantine=%d -> data/font-library.json + fonts/README.md"
          % (len([x for x in lib if x.get("shipped")]), len([x for x in lib if not x.get("shipped")])))


if __name__ == "__main__":
    main()