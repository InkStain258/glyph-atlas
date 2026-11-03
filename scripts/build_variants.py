#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_variants.py -- 为「古今汉字字形查询工具」构建简繁/异体字符等价类数据。

产物
----
data/variants.json  前端直接加载的静态数据（纯 JSON，运行时零依赖）
  {
    "meta":    {...},                       # 构建信息 / 统计 / 策略
    "canon":   {"說":"说", "寶":"宝"},       # 任意字符 -> 规范代表字
    "same":    {"说":["說","説"]},           # 强等价类（确定性合并）
    "related": {"干":["乾","幹","榦"]},      # 弱关联（候选相关字，不合并）
    "src":     {"說":"st,ts,unihan_simp,z"} # 该字参与的关系来自哪些字段
  }

设计要点
--------
* 强边（可合并）：Unihan kSimplifiedVariant / kTraditionalVariant，
  OpenCC STCharacters / TSCharacters 的映射。二者合进并查集。
  -> 但「一简对多繁」必须防止过度合并（后/後、干/乾/幹、发/發/髮 ……），
     详见 should_block() 的四条判据（多语素 / 同字例外 / ST 自指 / Big5 兜底）。
* 弱边（只记录不合并）：kSemanticVariant / kZVariant / kSpecializedSemanticVariant。
  -> 单独输出到 related，前端可分层展示。
* 每条关系都保留来源标记：st / ts / unihan_simp / unihan_trad / z / sem / ssem。
* 规范代表字：GB2312 一级字 > GB2312 二级字 > GBK > 其他；
  同级优先「简体形」，再优先笔画少，最后按码位。

许可
----
Unihan  : Unicode Terms of Use        https://www.unicode.org/terms_of_use.html
OpenCC  : Apache-2.0                   https://github.com/BYVoid/OpenCC

用法
----
    python3 scripts/build_variants.py                  # 构建（缓存缺失时才下载）
    python3 scripts/build_variants.py --refresh        # 强制重新下载后再构建
    python3 scripts/build_variants.py --selftest       # 已知用例自检（读取已构建 JSON）
    python3 scripts/build_variants.py --diagnostics .cache/guard.tsv  # 导出守护判据表
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

# --------------------------------------------------------------------------- #
# 路径与数据源
# --------------------------------------------------------------------------- #

PROJECT_ROOT = Path(__file__).resolve().parent.parent          # .../glyph-atlas
CACHE_DIR = PROJECT_ROOT / ".cache"
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_OUT = DATA_DIR / "variants.json"

OPENCC_BASE = "https://raw.githubusercontent.com/BYVoid/OpenCC/master/data/dictionary/"

SOURCES = [
    {
        "key": "unihan",
        "name": "Unicode Unihan Database (UCD latest)",
        "url": "https://www.unicode.org/Public/UCD/latest/ucd/Unihan.zip",
        "filename": "Unihan.zip",
        "license": "Unicode Terms of Use (https://www.unicode.org/terms_of_use.html)",
        "members": ["Unihan_Variants.txt", "Unihan_IRGSources.txt"],
    },
    {
        "key": "st",
        "name": "OpenCC STCharacters.txt (简体→繁体)",
        "url": OPENCC_BASE + "STCharacters.txt",
        "filename": "STCharacters.txt",
        "license": "Apache-2.0",
    },
    {
        "key": "ts",
        "name": "OpenCC TSCharacters.txt (繁体→简体)",
        "url": OPENCC_BASE + "TSCharacters.txt",
        "filename": "TSCharacters.txt",
        "license": "Apache-2.0",
    },
    {
        "key": "st_phrases",
        "name": "OpenCC STPhrases.txt (词语级，仅作缓存/统计)",
        "url": OPENCC_BASE + "STPhrases.txt",
        "filename": "STPhrases.txt",
        "license": "Apache-2.0",
    },
    {
        "key": "ts_phrases",
        "name": "OpenCC TSPhrases.txt (词语级，仅作缓存/统计)",
        "url": OPENCC_BASE + "TSPhrases.txt",
        "filename": "TSPhrases.txt",
        "license": "Apache-2.0",
    },
]

# Unihan 字段 -> 来源标记
STRONG_FIELDS = {
    "kSimplifiedVariant": "unihan_simp",     # 该字(繁体)的简化形式
    "kTraditionalVariant": "unihan_trad",    # 该字(简体)的繁体形式
}
WEAK_FIELDS = {
    "kSemanticVariant": "sem",
    "kZVariant": "z",
    "kSpecializedSemanticVariant": "ssem",
}
# 仅用于「是否同一字」的判据（不产生合并边，也不进 related）。
# 注意：这里刻意不收 kJapaneseOldVariant / kJapaneseNewVariant ——
# 它们会把「余/餘」「后/後」这类不同语素判成同一字（日本新字体习惯用法），
# 正是需要防止的过度合并来源。
GUARD_FIELDS = (
    "kSemanticVariant",
    "kZVariant",
    "kSpecializedSemanticVariant",
)

SRC_ORDER = {"st": 0, "ts": 1, "unihan_simp": 2, "unihan_trad": 3, "z": 4, "sem": 5, "ssem": 6}


# --------------------------------------------------------------------------- #
# 基础工具
# --------------------------------------------------------------------------- #

def log(msg: str) -> None:
    print(msg, flush=True)


def reconfigure_stdout() -> None:
    """Windows 控制台默认 cp936，打印汉字会崩；统一切到 utf-8。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path, timeout: int = 180, retries: int = 3) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "glyph-atlas-variants/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp, open(tmp, "wb") as out:
                shutil.copyfileobj(resp, out)
            if tmp.stat().st_size == 0:
                raise IOError("empty response")
            os.replace(tmp, dest)
            return
        except Exception as exc:                       # noqa: BLE001 - 网络错误统一重试
            last_err = exc
            log(f"  ! 下载失败（第 {attempt}/{retries} 次）: {url} -> {exc}")
            time.sleep(1.5 * attempt)
    if tmp.exists():
        tmp.unlink()
    raise SystemExit(f"无法下载 {url}: {last_err}")


def ensure_sources(refresh: bool) -> dict:
    """把上游数据缓存到 .cache/，返回 source key -> 本地路径。"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    paths = {}
    for src in SOURCES:
        dest = CACHE_DIR / src["filename"]
        if refresh or not dest.exists() or dest.stat().st_size == 0:
            log(f"[download] {src['filename']} <- {src['url']}")
            download(src["url"], dest)
        else:
            log(f"[cache]    {src['filename']} ({dest.stat().st_size:,} bytes)")
        paths[src["key"]] = dest
    return paths


def read_zip_member(zip_path: Path, member: str) -> str:
    with zipfile.ZipFile(zip_path) as zf:
        return zf.read(member).decode("utf-8")


# --------------------------------------------------------------------------- #
# 解析
# --------------------------------------------------------------------------- #

def strip_note(token: str) -> str:
    """'U+8AAA<kMatthews' -> 'U+8AAA'"""
    return token.split("<", 1)[0].strip()


def parse_unihan_variants(text: str) -> dict:
    """char -> field -> [char, ...]（已去重、去掉注记、去掉自指）。"""
    data = defaultdict(lambda: defaultdict(list))
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        cp, field, values = parts[0], parts[1], parts[2]
        if field not in STRONG_FIELDS and field not in WEAK_FIELDS and field not in GUARD_FIELDS:
            continue
        if not cp.startswith("U+"):
            continue
        ch = chr(int(cp[2:], 16))
        seen = set()
        for token in values.split():
            token = strip_note(token)
            if not token.startswith("U+"):
                continue
            try:
                other = chr(int(token[2:], 16))
            except ValueError:
                continue
            if other == ch or other in seen:
                continue
            seen.add(other)
            data[ch][field].append(other)
    return {ch: dict(fields) for ch, fields in data.items()}


def parse_unihan_strokes(text: str) -> dict:
    """kTotalStrokes：取第一个数值（Unicode 会列 G/T 等多个区域值）。"""
    strokes = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 3 or parts[1] != "kTotalStrokes":
            continue
        try:
            strokes[chr(int(parts[0][2:], 16))] = int(parts[2].split()[0])
        except (ValueError, IndexError):
            continue
    return strokes


def parse_opencc(path: Path) -> dict:
    """OpenCC *.txt: 第一列 key，制表符后空格分隔候选。"""
    table = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip() or line.startswith("#"):
                continue
            key, _, rest = line.rstrip("\n").partition("\t")
            if not key:
                continue
            table[key] = rest.split()
    return table


# --------------------------------------------------------------------------- #
# 并查集
# --------------------------------------------------------------------------- #

class DSU:
    __slots__ = ("parent",)

    def __init__(self):
        self.parent = {}

    def add(self, x):
        if x not in self.parent:
            self.parent[x] = x

    def find(self, x):
        parent = self.parent
        if x not in parent:
            parent[x] = x
            return x
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:          # 路径压缩
            parent[x], x = root, parent[x]
        return root

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb

    def groups(self):
        out = defaultdict(list)
        for node in self.parent:
            out[self.find(node)].append(node)
        return out


# --------------------------------------------------------------------------- #
# 常用字分级 / 笔画 / 繁简判定
# --------------------------------------------------------------------------- #

def gb_tier(ch: str) -> int:
    """0=GB2312 一级字(3755) 1=GB2312 二级字 2=GBK 3=其他。

    GB2312 一级字区：首字节 0xB0-0xD7；二级字区：0xD8-0xF7。
    """
    try:
        raw = ch.encode("gb2312")
    except UnicodeEncodeError:
        try:
            ch.encode("gbk")
            return 2
        except UnicodeEncodeError:
            return 3
    if len(raw) == 2 and 0xB0 <= raw[0] <= 0xD7:
        return 0
    return 1


def in_big5(ch: str) -> bool:
    """Big5 是繁体字集：能编码说明该字在繁体系统里有独立码位。"""
    for codec in ("big5", "big5hkscs"):
        try:
            ch.encode(codec)
            return True
        except UnicodeEncodeError:
            continue
    return False


def canonical_order(ch: str, strokes: dict, simp_evidence: set) -> tuple:
    """规范代表字排序键：常用度 > 简体 > 笔画少 > 码位。"""
    return (
        gb_tier(ch),
        0 if ch in simp_evidence else 1,
        strokes.get(ch, 99),
        ord(ch),
    )


# --------------------------------------------------------------------------- #
# 关系图构建
# --------------------------------------------------------------------------- #

def build_relations(unihan: dict, st: dict, ts: dict):
    """收集候选关系。

    返回
    ----
    edges     : {(simp_side, trad_side): set(src_tags)}   # 强边候选
    weak      : {frozenset({a, b}): set(src_tags)}        # 弱关联
    guard_adj : {char: set(char)}                          # 同一字证据图
    src_tags  : {char: set(src_tags)}                      # 每个字的来源标记
    """
    edges = defaultdict(set)
    weak = defaultdict(set)
    guard_adj = defaultdict(set)
    src_tags = defaultdict(set)

    def add_strong(simplified: str, traditional: str, tag: str) -> None:
        if not simplified or not traditional or simplified == traditional:
            return
        edges[(simplified, traditional)].add(tag)
        src_tags[simplified].add(tag)
        src_tags[traditional].add(tag)

    def add_weak(a: str, b: str, tag: str) -> None:
        if not a or not b or a == b:
            return
        weak[frozenset((a, b))].add(tag)
        src_tags[a].add(tag)
        src_tags[b].add(tag)

    # --- Unihan 变体字段 ------------------------------------------------- #
    for ch, fields in unihan.items():
        for field, tag in STRONG_FIELDS.items():
            for other in fields.get(field, ()):
                if field == "kSimplifiedVariant":
                    # ch 是繁体侧，other 是它的简化形式
                    add_strong(other, ch, tag)
                else:  # kTraditionalVariant：ch 是简体侧，other 是繁体形式
                    add_strong(ch, other, tag)
        for field, tag in WEAK_FIELDS.items():
            for other in fields.get(field, ()):
                add_weak(ch, other, tag)
        for field in GUARD_FIELDS:
            for other in fields.get(field, ()):
                guard_adj[ch].add(other)
                guard_adj[other].add(ch)

    # --- OpenCC 字符词典 -------------------------------------------------- #
    for simp, candidates in st.items():
        for trad in candidates:
            add_strong(simp, trad, "st")
    for trad, candidates in ts.items():
        for simp in candidates:
            add_strong(simp, trad, "ts")

    return edges, weak, guard_adj, src_tags


def guard_components(nodes: set, guard_adj: dict) -> list:
    """在 nodes 子图里求连通分量（只看节点集内部的边）。"""
    seen, comps = set(), []
    for start in nodes:
        if start in seen:
            continue
        stack, comp = [start], []
        seen.add(start)
        while stack:
            cur = stack.pop()
            comp.append(cur)
            for nxt in guard_adj.get(cur, ()):
                if nxt in nodes and nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        comps.append(comp)
    return comps


def should_block(simplified: str, partners: list, guard_adj: dict,
                 st: dict, tv_self: set, big5_cache: dict) -> tuple:
    """判断「简体侧字符 S」与它的繁体候选们能否安全合并。

    返回 (blocked: bool, reason: str)

    判据
    ----
    A. 多繁且互不同源：S 的繁体候选中存在若干互不构成「同一字变体关系」的分组
       （如 发 -> 發 | 髮，干 -> 乾 | 幹），合并会把两个不同语素并成一类 -> 阻断。
    B. S 本身是传世汉字：OpenCC STCharacters 把 S 自己列为候选（self-reference）
       说明 S 在繁体语境中独立使用（后/後、里/裡、云/雲、余/餘……）-> 阻断。
    C. S 不在 OpenCC 词表里，但既在 Big5（繁体字集）里有码位、又自列为繁体变体
       -> 视为传世字 -> 阻断。

    例外：若 S 与其繁体候选在 Unihan 变体字段里被明确认定为「同一字的不同写法」
    （kZVariant / kSemanticVariant / kSpecializedSemanticVariant / kJapanese*），
    即使 S 在 Big5 中有码位也允许合并（宝/寶、峰/峯、真/眞、万/萬）。
    """
    nodes = set(partners) | {simplified}

    partner_nodes = set(partners)
    clusters = guard_components(partner_nodes, guard_adj) if partner_nodes else []
    all_comps = guard_components(nodes, guard_adj)
    same_morpheme = len(all_comps) == 1

    if same_morpheme:
        return False, "variant-linked"

    if len(clusters) > 1:
        return True, "multi-morpheme"

    if simplified in st and simplified in st[simplified]:
        return True, "self-ref-st"

    if simplified not in st:
        cached = big5_cache.get(simplified)
        if cached is None:
            cached = in_big5(simplified)
            big5_cache[simplified] = cached
        if cached and simplified in tv_self:
            return True, "big5-independent"

    return False, "simplified-only"


# --------------------------------------------------------------------------- #
# 主构建流程
# --------------------------------------------------------------------------- #

def build(paths: dict) -> dict:
    t0 = time.time()
    log("[parse] Unihan_Variants.txt")
    unihan_text = read_zip_member(paths["unihan"], "Unihan_Variants.txt")
    unihan = parse_unihan_variants(unihan_text)

    log("[parse] Unihan_IRGSources.txt (kTotalStrokes)")
    strokes = parse_unihan_strokes(read_zip_member(paths["unihan"], "Unihan_IRGSources.txt"))

    log("[parse] OpenCC STCharacters / TSCharacters")
    st = parse_opencc(paths["st"])
    ts = parse_opencc(paths["ts"])

    log("[graph] 合并强边 + 收集弱边")
    edges, weak, guard_adj, src_tags = build_relations(unihan, st, ts)

    # 每个字符自指的繁体变体集合（判据 C 用）：kTraditionalVariant 里包含自己
    tv_self = set()
    for ch, fields in unihan.items():
        if ch in fields.get("kTraditionalVariant", ()):
            tv_self.add(ch)

    log(f"[graph] 强边候选项 {len(edges):,}，弱关联 {len(weak):,}")

    # 简化判定证据（规范字优先序里的「简体」）：作为某字的 kSimplifiedVariant 目标，或在 ST 词表里
    simp_evidence = set()
    for ch, fields in unihan.items():
        for other in fields.get("kSimplifiedVariant", ()):
            simp_evidence.add(other)
    simp_evidence.update(st.keys())

    # --- 逐「简体侧」节点做守护判定 ------------------------------------ #
    partners_by_simp = defaultdict(set)
    for (simp, trad) in edges:
        partners_by_simp[simp].add(trad)

    big5_cache = {}
    decisions = {}
    for simp, partners in partners_by_simp.items():
        blocked, reason = should_block(simp, sorted(partners), guard_adj, st, tv_self, big5_cache)
        decisions[simp] = (blocked, reason)

    # --- 并查集合并允许的强边 ------------------------------------------- #
    dsu = DSU()
    blocked_edges = []
    for (simp, trad) in edges:
        blocked, _ = decisions[simp]
        if blocked:
            blocked_edges.append((simp, trad))
            continue
        dsu.add(simp)
        dsu.add(trad)
        dsu.union(simp, trad)

    groups = dsu.groups()
    multi = [sorted(members, key=lambda c: ord(c)) for members in groups.values() if len(members) > 1]
    multi.sort(key=lambda members: ord(members[0]))
    log(f"[graph] 等价类 {len(groups):,} 个，其中多字类 {len(multi):,} 个，"
        f"覆盖字符 {sum(len(g) for g in groups.values()):,}")

    # --- 规范代表字 ------------------------------------------------------ #
    canon = {}
    same = {}
    for members in multi:
        best = min(members, key=lambda c: canonical_order(c, strokes, simp_evidence))
        same[best] = sorted((c for c in members if c != best), key=lambda c: ord(c))
        for c in members:
            canon[c] = best

    # --- related（弱关联 + 被阻断的强边） -------------------------------- #
    related_priority = defaultdict(dict)      # char -> {other: 优先级}
    PRIORITY = {"blocked": 0, "sem": 1, "ssem": 2, "z": 3}

    def push(a: str, b: str, prio: str) -> None:
        if a == b:
            return
        if canon.get(a, a) == canon.get(b, b):
            return                              # 已经同类，不必再列
        cur = related_priority[a].get(b)
        p = PRIORITY.get(prio, 9)
        if cur is None or p < cur:
            related_priority[a][b] = p

    for (simp, trad) in blocked_edges:
        push(simp, trad, "blocked")
        push(trad, simp, "blocked")
    for pair, tags in weak.items():
        if len(pair) != 2:
            continue
        a, b = tuple(pair)
        for tag in tags:
            push(a, b, tag)
            push(b, a, tag)

    max_related = 16
    related = {}
    truncated = 0
    for ch, cand in related_priority.items():
        ordered = sorted(cand.items(), key=lambda kv: (kv[1], ord(kv[0])))
        if len(ordered) > max_related:
            truncated += 1
            ordered = ordered[:max_related]
        related[ch] = [x for x, _ in ordered]

    # --- src -------------------------------------------------------------- #
    src = {}
    for ch, tags in src_tags.items():
        ordered = sorted(tags, key=lambda t: (SRC_ORDER.get(t, 99), t))
        src[ch] = ",".join(ordered)

    # --- 统计 ------------------------------------------------------------- #
    stats = compute_stats(canon, same, related, strokes, unihan, blocked_edges,
                          decisions, src, groups)

    built_at = time.strftime("%Y-%m-%dT%H:%M:%S%z") or time.strftime("%Y-%m-%dT%H:%M:%S")
    unihan_version = parse_unihan_version(unihan_text)

    meta = {
        "built": built_at,
        "schema": "glyph-atlas/variants@1",
        "sources": [
            {
                "name": s["name"],
                "url": s["url"],
                "license": s["license"],
                "sha256": sha256_of(paths[s["key"]]),
                "bytes": paths[s["key"]].stat().st_size,
            }
            for s in SOURCES
        ],
        "unihan_version": unihan_version,
        "count": {
            "classes": len(groups),
            "multi_char_classes": len(multi),
            "chars_in_classes": sum(len(g) for g in groups.values()),
            "canon_entries": len(canon),
            "same_entries": len(same),
            "related_chars": len(related),
            "related_pairs": sum(len(v) for v in related.values()),
            "src_chars": len(src),
            "strong_edges": len(edges),
            "blocked_edges": len(blocked_edges),
            "weak_pairs": len(weak),
            "related_truncated_chars": truncated,
        },
        "policy": {
            "strong": ["unihan:kSimplifiedVariant", "unihan:kTraditionalVariant",
                       "opencc:STCharacters", "opencc:TSCharacters"],
            "weak": ["unihan:kSemanticVariant", "unihan:kZVariant",
                     "unihan:kSpecializedSemanticVariant"],
            "guard": "一简对多繁 / 传世字自指阻断，转 related 不合并",
            "canonical": "GB2312 一级 > 二级 > GBK > 其他；同级简体优先、笔画少优先",
            "related_cap": max_related,
            "keys": "字符本身（非 U+XXXX）；码位可由 ch.codePointAt(0) 取得",
        },
        "stats": stats,
    }

    log(f"[done] {time.time() - t0:.1f}s")
    return {"meta": meta, "canon": canon, "same": same, "related": related, "src": src}


def parse_unihan_version(text: str) -> str:
    for line in text.splitlines()[:12]:
        if line.startswith("# Date:"):
            continue
        if "Unicode Version" in line:
            return line.lstrip("# ").strip()
    return "unknown"


def compute_stats(canon, same, related, strokes, unihan, blocked_edges, decisions,
                  src, groups) -> dict:
    """报告需要的数字：覆盖率、分布、守护判据分布、极端类样本。"""
    gb2312_chars = []
    for cp in range(0x4E00, 0xA000):
        ch = chr(cp)
        try:
            ch.encode("gb2312")
            gb2312_chars.append(ch)
        except UnicodeEncodeError:
            continue

    covered = sum(1 for ch in gb2312_chars if ch in canon)
    reasons = defaultdict(int)
    for simp, (blocked, reason) in decisions.items():
        if blocked:
            reasons[reason] += 1

    # 等价类规模分布
    sizes = defaultdict(int)
    for members in groups.values():
        n = len(members)
        if n > 1:
            sizes["5+" if n >= 5 else str(n)] += 1
    merged_chars = sum(len(v) + 1 for v in same.values())
    largest = sorted(same.items(), key=lambda kv: (-len(kv[1]), ord(kv[0])))[:10]

    # 来源标记分布（按字符计）
    tag_counts = defaultdict(int)
    for tags in src.values():
        for t in tags.split(","):
            if t:
                tag_counts[t] += 1

    # 阻断样本：按字符序整理，便于人工复核误杀
    blocked_samples = sorted({(a, b) for a, b in blocked_edges}, key=lambda p: (ord(p[0]), ord(p[1])))

    related_max = max((len(v) for v in related.values()), default=0)

    return {
        "gb2312_chars": len(gb2312_chars),
        "gb2312_with_class": covered,
        "gb2312_coverage": round(covered / max(1, len(gb2312_chars)), 4),
        "class_size_histogram": dict(sorted(sizes.items())),
        "merged_chars": merged_chars,
        "guard_blocks": dict(sorted(reasons.items())),
        "guard_block_multi_morpheme": reasons.get("multi-morpheme", 0),
        "blocked_pairs": len(set(blocked_edges)),
        "blocked_edge_samples": [f"{a}→{b}" for a, b in blocked_samples[:24]],
        "src_tag_counts": dict(sorted(tag_counts.items(), key=lambda kv: -kv[1])),
        "related_max_fanout": related_max,
        "largest_classes": [
            {"canon": k, "n": len(v) + 1, "members": (k + "".join(v))[:24]}
            for k, v in largest
        ],
    }


# --------------------------------------------------------------------------- #
# 自检
# --------------------------------------------------------------------------- #

SELFTESTS = [
    # (说明, 期望类型, 涉及字符, 备注)
    ("说/說/説 同类", "same", ["说", "說", "説"], "说 → 說/説（繁简+异体）"),
    ("宝/寶 同类", "same", ["宝", "寶"], "宝 → 寶"),
    ("为/為/爲 同类", "same", ["为", "為", "爲"], "为 → 為/爲（爲 为 Unihan 正体）"),
    ("峰/峯 同类", "same", ["峰", "峯"], "异体字同键"),
    ("真/眞 同类", "same", ["真", "眞"], "异体字同键"),
    ("万/萬 同类", "same", ["万", "萬"], "常规简化回归"),
    ("东/東 同类", "same", ["东", "東"], "常规简化回归"),
    ("头/頭 同类", "same", ["头", "頭"], "常规简化回归"),
    ("无/無 同类", "same", ["无", "無"], "常规简化回归"),
    ("后/後 不合并", "related", ["后", "後"], "一简对多繁：后(皇后) ≠ 後"),
    ("余/餘 不合并", "related", ["余", "餘"], "余(我) ≠ 餘(剩余)"),
    ("云/雲 不合并", "related", ["云", "雲"], "云(说) ≠ 雲(云彩)"),
    ("里/裡/裏 不合并", "related", ["里", "裡", "裏"], "里(乡里) ≠ 裡/裏(里面)"),
    ("干/乾/幹/榦 不合并", "related", ["干", "乾", "幹", "榦"], "干(干戈) ≠ 乾/幹/榦"),
    ("发/發/髮 不合并", "related", ["发", "發", "髮"], "发(发生) ≠ 髮(头发)"),
    ("台/臺/檯/颱 不合并", "related", ["台", "臺", "檯", "颱"], "台(台子) ≠ 臺/檯/颱"),
    ("只/隻 不合并", "related", ["只", "隻"], "只(只有) ≠ 隻(一只)"),
    ("系/係/繫 不合并", "related", ["系", "係", "繫"], "系(系统) ≠ 係/繫"),
]


def run_selftest(data_path: Path, md_path: Path | None = None, verbose: bool = True) -> int:
    with open(data_path, encoding="utf-8") as fh:
        data = json.load(fh)
    canon = data["canon"]
    same = data["same"]
    related = data["related"]

    def cls(ch):
        return canon.get(ch, ch)

    def same_group(ch):
        c = cls(ch)
        return {c} | set(same.get(c, []))

    rows, failures = [], 0
    for label, kind, chars, note in SELFTESTS:
        if kind == "same":
            groups = {frozenset(same_group(ch)) for ch in chars}
            ok = len(groups) == 1 and len(next(iter(groups))) >= len(chars)
            got = f"same={''.join(sorted(next(iter(groups))))}" if ok else \
                  f"same={{{' | '.join(''.join(sorted(g)) for g in groups)}}}"
        else:
            # 「不合并」用例的验收口径：
            # 1) 组内任意两字不在同一等价类（没有被错误合并）；
            # 2) 首选字（组内第一个）的 related 列出该组全部伙伴；
            # 3) 双向可发现：每个伙伴的 related 也含首选字。
            hub = chars[0]
            distinct = all(
                cls(chars[i]) != cls(chars[j])
                for i in range(len(chars))
                for j in range(i + 1, len(chars))
            )
            hub_lists_all = all(c in related.get(hub, []) for c in chars[1:])
            partners_link_hub = all(hub in related.get(c, []) for c in chars[1:])
            ok = distinct and hub_lists_all and partners_link_hub
            flags = []
            if not distinct:
                flags.append("误合并")
            if not hub_lists_all:
                flags.append(f"{hub} 未列全")
            if not partners_link_hub:
                flags.append(f"伙伴未反链 {hub}")
            got = "related=" + "; ".join(
                f"{c}->{''.join(related.get(c, [])) or '-'}" for c in chars
            )
            if flags:
                got += " [" + ", ".join(flags) + "]"
        status = "PASS" if ok else "FAIL"
        if not ok:
            failures += 1
        rows.append((label, note, "同类" if kind == "same" else "不合并", got, status))

    lines = []
    if md_path:
        lines.append("| 用例 | 期望 | 实际 | 结果 |")
        lines.append("| --- | --- | --- | --- |")
        for label, note, expect, got, status in rows:
            lines.append(f"| {label} | {expect}（{note}） | `{got}` | **{status}** |")
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        if verbose:
            log(f"[selftest] 明细已写入 {md_path}")

    width = max(len(r[0]) for r in rows)
    for label, note, expect, got, status in rows:
        log(f"  {status}  {label:<{width}}  期望={expect}  {got}")

    total = len(rows)
    log(f"[selftest] {total - failures}/{total} 通过")
    return 1 if failures else 0


def write_diagnostics(out: Path, edges, decisions, st) -> None:
    """把守护判定落成 TSV，便于人工复核误杀/漏杀。"""
    rows = []
    partners_by_simp = defaultdict(set)
    for (simp, trad) in edges:
        partners_by_simp[simp].add(trad)
    for simp, partners in sorted(partners_by_simp.items(), key=lambda kv: ord(kv[0])):
        blocked, reason = decisions[simp]
        rows.append("\t".join([
            "BLOCK" if blocked else "MERGE",
            reason,
            simp,
            "".join(sorted(partners, key=ord)),
            f"U+{ord(simp):04X}",
            "ST-self" if (simp in st and simp in st[simp]) else "",
        ]))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(rows) + "\n", encoding="utf-8")
    log(f"[diagnostics] {len(rows):,} 行 -> {out}")


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #

def main(argv=None) -> int:
    reconfigure_stdout()
    parser = argparse.ArgumentParser(description="构建简繁/异体字符等价类数据 variants.json")
    parser.add_argument("--refresh", action="store_true", help="强制重新下载上游数据")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="输出 JSON 路径")
    parser.add_argument("--selftest", action="store_true", help="只跑已知用例自检")
    parser.add_argument("--selftest-md", type=Path, default=None, help="自检结果写入 Markdown")
    parser.add_argument("--diagnostics", type=Path, default=None, help="导出守护判据诊断表")
    parser.add_argument("--pretty", action="store_true", help="输出缩进 JSON（调试用，体积会变大）")
    args = parser.parse_args(argv)

    if args.selftest:
        md = args.selftest_md or (CACHE_DIR / "selftest.md")
        return run_selftest(args.out, md)

    paths = ensure_sources(args.refresh)
    payload = build(paths)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.pretty:
        text = json.dumps(payload, ensure_ascii=False, indent=1)
    else:
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    args.out.write_text(text, encoding="utf-8")

    raw = args.out.stat().st_size
    gz = len(gzip.compress(text.encode("utf-8"), 9))
    meta = payload["meta"]
    log("")
    log(f"[output] {args.out}")
    log(f"         raw {raw:,} bytes / gzip {gz:,} bytes")
    log(f"         等价类 {meta['count']['classes']:,}（多字类 {meta['count']['multi_char_classes']:,}）"
        f"  canon {meta['count']['canon_entries']:,}"
        f"  same {meta['count']['same_entries']:,}"
        f"  related {meta['count']['related_pairs']:,} 对")
    log(f"         GB2312 覆盖率 {meta['stats']['gb2312_coverage']:.1%} "
        f"({meta['stats']['gb2312_with_class']}/{meta['stats']['gb2312_chars']})")

    if args.diagnostics:
        # 重建一次轻量关系图只为了导出决策表
        unihan = parse_unihan_variants(read_zip_member(paths["unihan"], "Unihan_Variants.txt"))
        st = parse_opencc(paths["st"])
        ts = parse_opencc(paths["ts"])
        edges, _weak, guard_adj, _src = build_relations(unihan, st, ts)
        tv_self = {ch for ch, f in unihan.items() if ch in f.get("kTraditionalVariant", ())}
        partners_by_simp = defaultdict(set)
        for (simp, trad) in edges:
            partners_by_simp[simp].add(trad)
        cache = {}
        decisions = {simp: should_block(simp, sorted(p), guard_adj, st, tv_self, cache)
                     for simp, p in partners_by_simp.items()}
        write_diagnostics(args.diagnostics, edges, decisions, st)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())