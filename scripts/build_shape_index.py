# -*- coding: utf-8 -*-
"""以形查字：把古文字层的每个字形栅格化成「形状指纹」，供纯前端反查。

指纹（每字形 146 字节，与 web/shape.js 的解码逐位对应）：
    [0:128]   16x16 密度网格，每格 4 bit（0..15），两格一字节，高位在前
    [128:144] 16 条水平投影 + 16 条垂直投影，各 4 bit，两值一字节
    [144]     长宽比 w/h，clamp 到 [0.25,4] 后映射到 0..255
    [145]     墨量（64x64 框内着墨比例）0..255

归一化管线（Python 与 JS 必须一致）：
    二值掩膜 -> 紧包围盒裁切 -> 等比缩放使长边 = 56 -> 居中放进 64x64
    -> 4x4 盒式降采样成 16x16 -> 量化到 0..15

用法：
    python -X utf8 scripts/build_shape_index.py [--layers seal oracle] [--samples]
"""
import argparse
import base64
import io
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                      # .../glyph-atlas/src
WEB = os.path.join(ROOT, "web")
OUT = os.path.join(WEB, "data", "shape")

N = 64          # 归一化画布
INNER = 56      # 长边目标
G = 16          # 网格边长
DESC = 146      # 每字形字节数

ANCIENT = [
    ("oracle",   "甲骨文",   1, "甲"),
    ("bronze",   "金文",     2, "金"),
    ("chu",      "楚文字",   3, "楚"),
    ("qinwenzi", "秦系簡牘", 4, "秦"),
    ("chuanchao","傳抄古文", 5, "傳"),
    ("seal",     "小篆",     6, "篆"),
    ("beishida", "說文小篆", 6.5, "說"),
    ("shuowen-seal-kaiyuan", "開元小篆", 6.6, "開"),
    ("clerical", "隸書",     7, "隸"),
]


def font_path(lid):
    p = os.path.join(ROOT, "fonts", "ancient", lid, "glyphs.ttf")
    if os.path.exists(p):
        return p
    p = os.path.join(ROOT, "fonts", "modern", lid, "subset.ttf")
    return p if os.path.exists(p) else None


def chars_of(lid):
    """从 data/meta/<lid>.json 取字表；没有 meta 的层从字体 cmap 取。"""
    mp = os.path.join(ROOT, "data", "meta", lid + ".json")
    if os.path.exists(mp):
        d = json.load(io.open(mp, encoding="utf-8"))
        return sorted(d.keys(), key=lambda c: ord(c[0]) if len(c) == 1 else 0x10FFFF)
    from fontTools.ttLib import TTFont
    f = TTFont(font_path(lid), fontNumber=0, lazy=True)
    cm = f.getBestCmap() or {}
    f.close()
    return [chr(u) for u in sorted(cm) if 0x3400 <= u <= 0x2FA1F]


def render_mask(pil_font, ch, px=160):
    """渲染单字为二值掩膜（numpy uint8, 0/255）。空字形返回 None。"""
    pad = px // 2
    img = Image.new("L", (px + pad * 2, px + pad * 2), 0)
    d = ImageDraw.Draw(img)
    try:
        d.text((pad, pad), ch, font=pil_font, fill=255)
    except Exception:
        return None
    a = np.asarray(img)
    ys, xs = np.nonzero(a > 127)
    if len(xs) < 4:
        return None
    return (a[ys.min():ys.max() + 1, xs.min():xs.max() + 1] > 127).astype(np.uint8) * 255


def normalize(mask):
    """紧包围盒掩膜 -> 64x64 归一化灰度（长边 56、居中）。"""
    h, w = mask.shape
    s = INNER / float(max(h, w))
    tw, th = max(1, int(round(w * s))), max(1, int(round(h * s)))
    im = Image.fromarray(mask).resize((tw, th), Image.BOX)
    canvas = Image.new("L", (N, N), 0)
    canvas.paste(im, ((N - tw) // 2, (N - th) // 2))
    return np.asarray(canvas, dtype=np.float32), (w, h)


def descriptor(mask):
    """返回 146 字节指纹；与 shape.js 的 encode 完全同构。"""
    norm, (w, h) = normalize(mask)
    cell = norm.reshape(G, N // G, G, N // G).mean(axis=(1, 3))   # 16x16, 0..255
    q = np.clip(np.rint(cell / 255.0 * 15.0), 0, 15).astype(np.uint8)

    buf = bytearray(DESC)
    flat = q.reshape(-1)
    for i in range(0, 256, 2):
        buf[i // 2] = (int(flat[i]) << 4) | int(flat[i + 1])

    rows = q.sum(axis=1).astype(np.float32)
    cols = q.sum(axis=0).astype(np.float32)
    rows = rows / rows.max() if rows.max() > 0 else rows
    cols = cols / cols.max() if cols.max() > 0 else cols
    pr = np.clip(np.rint(rows * 15), 0, 15).astype(np.uint8)
    pc = np.clip(np.rint(cols * 15), 0, 15).astype(np.uint8)
    for i in range(0, 16, 2):
        buf[128 + i // 2] = (int(pr[i]) << 4) | int(pr[i + 1])
        buf[136 + i // 2] = (int(pc[i]) << 4) | int(pc[i + 1])

    ar = max(0.25, min(4.0, w / float(h)))
    buf[144] = int(round((ar - 0.25) / 3.75 * 255))
    buf[145] = int(round(float((norm > 127).mean()) * 255))
    return bytes(buf)


def build_layer(lid, name, era, mono, limit=None):
    fp = font_path(lid)
    if not fp:
        print("  !! 缺字体", lid, flush=True)
        return None
    cs = chars_of(lid)
    if limit:
        cs = cs[:limit]
    pf = ImageFont.truetype(fp, 160)
    blobs = []
    kept = []
    empty = 0
    for i, ch in enumerate(cs):
        m = render_mask(pf, ch)
        if m is None:
            empty += 1
            continue
        blobs.append(descriptor(m))
        kept.append(ch)
        if (i + 1) % 2000 == 0:
            print("  %s %d/%d" % (lid, i + 1, len(cs)), flush=True)
    raw = b"".join(blobs)
    b64 = base64.b64encode(raw).decode("ascii")
    payload = {
        "id": lid, "name": name, "era": era, "mono": mono,
        "n": len(kept), "stride": DESC, "chars": "".join(kept), "b64": b64,
    }
    os.makedirs(OUT, exist_ok=True)
    js = "window.GA_SHAPE=window.GA_SHAPE||{};window.GA_SHAPE[%s]=%s;" % (
        json.dumps(lid), json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    io.open(os.path.join(OUT, lid + ".js"), "w", encoding="utf-8", newline="\n").write(js)
    print("  %-22s %6d 字  %5d 空  %7.2f MB" % (lid, len(kept), empty, len(js) / 1048576.0), flush=True)
    return {"id": lid, "name": name, "era": era, "mono": mono,
            "n": len(kept), "bytes": len(js)}


def make_samples():
    """从真实字形造 8 张「拓片风格」查询样本，页面开箱即有结果。"""
    specs = [
        ("seal", "永", "小篆·永", 0, 0.0),
        ("seal", "福", "小篆·福（磨蝕）", -4, 0.05),
        ("oracle", "王", "甲骨·王", 0, 0.02),
        ("bronze", "受", "金文·受（旋轉）", 7, 0.03),
        ("clerical", "長", "隸書·長", 0, 0.04),
        ("seal", "樂", "小篆·樂（朱文）", 0, 0.0, "zhu"),
        ("oracle", "日", "甲骨·日（斷裂）", -6, 0.09),
        ("bronze", "央", "金文·央", 3, 0.02),
    ]
    rng = np.random.default_rng(20261109)
    out = []
    for spec in specs:
        lid, ch, label, rot, noise = spec[:5]
        mode = spec[5] if len(spec) > 5 else None
        fp = font_path(lid)
        pf = ImageFont.truetype(fp, 200)
        m = render_mask(pf, ch, px=200)
        if m is None:
            continue
        im = Image.fromarray(m)
        # 放进 256 画布，模拟拓片留白
        s = 190.0 / max(im.size)
        im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.BOX)
        canvas = Image.new("L", (256, 256), 0)
        canvas.paste(im, ((256 - im.width) // 2, (256 - im.height) // 2))
        if rot:
            canvas = canvas.rotate(rot, resample=Image.BICUBIC, expand=False, fillcolor=0)
        a = np.asarray(canvas, dtype=np.float32)
        if noise:
            a = a + rng.normal(0, noise * 255, a.shape)
            a = np.clip(a, 0, 255)
            # 随机斑点，模拟石花
            spots = rng.random(a.shape) < (noise * 0.10)
            a[spots] = 255 - a[spots]
        a = np.clip(a, 0, 255).astype(np.uint8)
        q = Image.fromarray(a).filter(ImageFilter.GaussianBlur(0.6))
        if mode == "zhu":
            # 真朱文：宣纸底 + 朱砂字。亮度上字比底暗，必须反相才提得出笔画。
            g = np.asarray(q, dtype=np.float32)[..., None] / 255.0
            paper = np.array([245., 240., 228.], dtype=np.float32)
            verm = np.array([198., 50., 43.], dtype=np.float32)
            rgb = paper * (1.0 - g) + verm * g
            q = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB")
        bio = io.BytesIO()
        q.convert("RGB").save(bio, "PNG", optimize=True)
        out.append({"id": "%s-%s" % (lid, ch), "char": ch, "layer": lid,
                    "label": label, "invert": mode == "zhu",
                    "png": base64.b64encode(bio.getvalue()).decode("ascii")})
        print("  sample", label, len(bio.getvalue()), "B", flush=True)
    js = "window.GA_SHAPE_SAMPLES=%s;" % json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    os.makedirs(OUT, exist_ok=True)
    io.open(os.path.join(OUT, "samples.js"), "w", encoding="utf-8", newline="\n").write(js)
    print("  samples.js %.2f MB" % (len(js) / 1048576.0), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--layers", nargs="*", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--samples", action="store_true")
    ap.add_argument("--samples-only", action="store_true")
    a = ap.parse_args()

    if a.samples_only:
        make_samples()
        return

    want = set(a.layers) if a.layers else None
    index = []
    for lid, name, era, mono in ANCIENT:
        if want and lid not in want:
            continue
        print("[build]", lid, flush=True)
        r = build_layer(lid, name, era, mono, a.limit)
        if r:
            index.append(r)

    if index:
        prev = []
        ip = os.path.join(OUT, "index.js")
        if os.path.exists(ip) and want:
            txt = io.open(ip, encoding="utf-8").read()
            try:
                prev = json.loads(txt[txt.index("=") + 1:].rstrip(";"))
            except Exception:
                prev = []
        merged = {x["id"]: x for x in prev}
        for x in index:
            merged[x["id"]] = x
        order = {lid: i for i, (lid, _, _, _) in enumerate(ANCIENT)}
        arr = sorted(merged.values(), key=lambda x: order.get(x["id"], 99))
        io.open(ip, "w", encoding="utf-8", newline="\n").write(
            "window.GA_SHAPE_INDEX=%s;" % json.dumps(arr, ensure_ascii=False, separators=(",", ":")))
        print("index.js", len(arr), "layers", flush=True)

    if a.samples:
        print("[samples]", flush=True)
        make_samples()


if __name__ == "__main__":
    main()