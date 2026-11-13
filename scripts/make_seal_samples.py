# -*- coding: utf-8 -*-
"""生成「印章考據」頁的示範樣本（合成印面）。

為什麼要合成：真實書影有版權與體積問題；而本頁要演示的恰恰是
「朱印定位 → 拆字 → 查形」這條鏈，用合成印面能同時控制字數、排版、
朱白文與磨損，回歸測試也可重現。

輸出：web/data/seal-samples.js  →  window.GA_SEAL_SAMPLES = [{label, png}]
"""
import base64
import io
import json
import os
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT = os.path.join(ROOT, "fonts", "ancient", "beishida", "glyphs.ttf")
OUT = os.path.join(ROOT, "web", "data", "seal-samples.js")

SS = 4                     # 超採樣倍率
PX = 216                   # 成品邊長
PAPER = (243, 237, 226)
RED = (158, 43, 30)

# (名稱, 字串, 排列 cols×rows, 朱/白, 加框, 磨損)
SAMPLES = [
    ("永受 · 朱文加框", "永受", (1, 2), "zhu", True, 0.0),
    ("長樂未央 · 白文", "長樂未央", (2, 2), "bai", False, 0.05),
    ("右司馬 · 朱文", "右司馬", (1, 3), "zhu", True, 0.05),
    ("福 · 圓框磨損", "福", (1, 1), "zhu", True, 0.35),
]


def cell_size(w, h, pad=0.08, gap=0.03):
    """回傳 (cell_w, cell_h, gap_px, pad_px)"""
    pad_px = int(PX * SS * pad)
    gap_px = int(PX * SS * gap) if (w > 1 or h > 1) else 0
    cw = (PX * SS - pad_px * 2 - gap_px * (w - 1)) // w
    ch = (PX * SS - pad_px * 2 - gap_px * (h - 1)) // h
    return cw, ch, gap_px, pad_px


def fit_font(path, ch, box):
    best = None
    for s in range(box, 8, -1):
        f = ImageFont.truetype(path, s)
        try:
            x0, y0, x1, y1 = f.getbbox(ch)
        except Exception:
            continue
        if x1 - x0 <= box and y1 - y0 <= box:
            best = f
            break
    if best is None:
        best = ImageFont.truetype(path, 8)
    return best


def draw_char(layer, path, ch, cx, cy, box):
    """把字畫在 layer 的 (cx,cy) 中心，尺寸自適應 box；回傳墨跡遮罩。"""
    f = fit_font(path, ch, box)
    m = Image.new("L", layer.size, 0)
    d = ImageDraw.Draw(m)
    x0, y0, x1, y1 = f.getbbox(ch)
    d.text((cx - (x1 - x0) / 2 - x0, cy - (y1 - y0) / 2 - y0), ch, font=f, fill=255)
    return m


def make(name, text, grid, kind, framed, wear):
    W, H = grid
    S = PX * SS
    paper = Image.new("RGB", (S, S), PAPER)
    # 紙紋：細微噪點
    rnd = random.Random(hash(text) & 0xFFFF)
    noise = Image.effect_noise((S, S), 9).convert("L")
    paper = Image.composite(Image.new("RGB", (S, S), (238, 231, 217)), paper, noise.point(lambda v: 22))

    if kind == "bai":
        ground = Image.new("L", (S, S), 0)
        gd = ImageDraw.Draw(ground)
        pad = int(S * 0.055)
        gd.rectangle([pad, pad, S - pad, S - pad], fill=255)
        img = Image.composite(Image.new("RGB", (S, S), RED), paper, ground)
        ink_on_white = True
    else:
        img = paper.copy()
        ink_on_white = False

    cw, ch_, gap, pad = cell_size(W, H)
    chars = list(text)
    for i, c in enumerate(chars):
        # 直行右至左：第 i 字落在第 (i // H) 欄（由右往左數）、第 (i % H) 列
        cx_i, cy_i = W - 1 - (i // H), i % H
        x = pad + cx_i * (cw + gap) + cw // 2
        y = pad + cy_i * (ch_ + gap) + ch_ // 2
        m = draw_char(img, FONT, c, x, y, int(min(cw, ch_) * 0.94))
        if kind == "bai":
            # 白文：字是紙色（挖掉紅底）
            img = Image.composite(Image.new("RGB", (S, S), PAPER), img, m)
        else:
            img = Image.composite(Image.new("RGB", (S, S), RED), img, m)

    if framed:
        d = ImageDraw.Draw(img)
        w = max(2, int(S * 0.035))
        if text == "福":
            d.ellipse([w, w, S - w - 1, S - w - 1], outline=RED, width=w)
        else:
            d.rectangle([w // 2, w // 2, S - w // 2 - 1, S - w // 2 - 1], outline=RED, width=w)

    if wear > 0:
        # 磨損：局部擦除 + 邊緣模糊，模擬古印鈐蓋
        mask = Image.effect_noise((S, S), 120).convert("L")
        mask = mask.filter(ImageFilter.GaussianBlur(3))
        keep = mask.point(lambda v: 255 if v > int(255 * wear * 0.55) else 0)
        img = Image.composite(img, paper, keep)
        img = img.filter(ImageFilter.GaussianBlur(0.6 * SS))

    img = img.resize((PX, PX), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return {"label": name, "png": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()}


def main():
    out = [make(*s) for s in SAMPLES]
    js = "window.GA_SEAL_SAMPLES = " + json.dumps(out, ensure_ascii=False) + ";\n"
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(js)
    print("wrote", OUT, os.path.getsize(OUT), "bytes,", len(out), "samples")


if __name__ == "__main__":
    main()