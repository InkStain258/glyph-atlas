# -*- coding: utf-8 -*-
"""把工程源码（src/web 等）同步成仓库根目录下的可部署站点。

布局约定：
    E:/Github/glyph-atlas/         <- git 仓库根 = GitHub Pages 发布根
    E:/Github/glyph-atlas/src/     <- 本项目工程源码（本脚本所在处）

只同步站点运行所需的文件 + 许可文档 + 构建脚本；不搬 719 MB 的原始/子集字体库（在 src/fonts/）。
删除时只清 `PUBLISHED` 名单里的条目，绝不碰 `.git/` 与 `src/`。
"""
import io, json, os, shutil, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .../glyph-atlas/src
OUT = os.path.dirname(ROOT)                                          # .../glyph-atlas

PUBLISHED = [
    "index.html", "licenses.html", "app.js", "parts.js", "licenses.js", "style.css",
    "css", "fonts", "data", "docs", "scripts", "LICENSES", ".nojekyll", "README.md",
]

def copytree(src, dst):
    if not os.path.exists(src):
        print("!! 缺", src)
        return
    shutil.copytree(src, dst, dirs_exist_ok=True)

def copyfile(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)

def clean():
    for name in PUBLISHED:
        p = os.path.join(OUT, name)
        if os.path.isdir(p) and not os.path.islink(p):
            shutil.rmtree(p)
        elif os.path.exists(p):
            os.remove(p)


def main():
    if not os.path.isdir(os.path.join(OUT, ".git")):
        sys.exit("目标不是 git 仓库，拒绝覆盖: " + OUT)
    if os.path.abspath(ROOT) == os.path.abspath(OUT):
        sys.exit("ROOT 与 OUT 相同，布局异常")

    print("清空发布物...", flush=True)
    clean()

    web = os.path.join(ROOT, "web")
    for f in ("index.html", "licenses.html", "app.js", "parts.js", "licenses.js", "style.css"):
        copyfile(os.path.join(web, f), os.path.join(OUT, f))
    for d in ("css", "fonts", "data"):
        copytree(os.path.join(web, d), os.path.join(OUT, d))

    # 文档：报告 + 截图
    os.makedirs(os.path.join(OUT, "docs"))
    for f in sorted(os.listdir(os.path.join(ROOT, "docs"))):
        if f.endswith((".md", ".png")):
            copyfile(os.path.join(ROOT, "docs", f), os.path.join(OUT, "docs", f))

    # 构建脚本（可复现）
    copytree(os.path.join(ROOT, "scripts"), os.path.join(OUT, "scripts"))

    # 许可全文
    licdir = os.path.join(ROOT, "fonts", "license-texts")
    os.makedirs(os.path.join(OUT, "LICENSES"))
    for f in sorted(os.listdir(licdir)):
        copyfile(os.path.join(licdir, f), os.path.join(OUT, "LICENSES", f))

    # 第三方清单
    lib = json.load(io.open(os.path.join(ROOT, "data", "font-library.json"), encoding="utf-8"))
    fonts = [f for f in lib["fonts"] if f.get("shipped")]
    fonts.sort(key=lambda f: (f.get("era_order") or 0, f.get("name_zh") or ""))
    lines = [
        "# 第三方素材清单 · Third-party notices",
        "",
        "本工具的字形来自 36 款字库（9 个古文字字形源 + 27 款历史/现代字库）。逐款许可如下，",
        "协议全文见 `LICENSES/`。每款在原始仓库里都有独立目录，内含 `LICENSE.txt`、`license.json`、`NOTICE.md`。",
        "",
        "| 字体 | 时代/书体 | 许可 | 字数 | 需署名 | 可商用 |",
        "| --- | --- | --- | ---: | --- | --- |",
    ]
    for f in fonts:
        lines.append("| %s | %s / %s | %s | %s | %s | %s |" % (
            f.get("name_zh") or f["id"],
            f.get("era") or "—",
            f.get("style") or "—",
            f.get("license_spdx") or "—",
            f.get("chars") or "—",
            "是" if f.get("attribution_required") else "否",
            "是" if f.get("commercial_use_allowed") else "否",
        ))
    lines += [
        "",
        "## 字形数据",
        "",
        "- **hanzi-glyphs-svg**（[zhouyongh/hanzi-glyphs-svg](https://github.com/zhouyongh/hanzi-glyphs-svg)）：甲骨/金文/楚文字/秦简/传抄古文/小篆/隶书 七层 SVG 字形。逐层授权不同——甲骨层 JGW 参数化 1,203 条为 CC BY 4.0（署名 + 注明修改），其余为 CC0 1.0。",
        "- **BabelStone IDS**（[babelstone.co.uk/CJK/IDS.TXT](https://babelstone.co.uk/CJK/IDS.TXT)）：部件结构数据，97,680 条。作者声明任何人可为个人或商业目的自由使用，无需许可或署名。",
        "- **OpenCC / Unicode Unihan**：简繁异体映射，仅在构建期使用，最终产物是等价类表，不随仓库分发原始映射文件。",
        "",
        "## 已排除",
        "",
        "商业字库（汉仪、方正、文鼎、华康、华文、字魂、锐字、叶根友等）一律未下载、未打包；",
        "另有 5 款经核验不能落地的字库（CC BY-ND、IPA 许可、保留所有权利等）只保留许可留档，二进制未分发。",
    ]
    io.open(os.path.join(OUT, "LICENSES", "THIRD-PARTY.md"), "w", encoding="utf-8", newline="\n").write(
        "\n".join(lines) + "\n")

    # .nojekyll + 公开 README
    io.open(os.path.join(OUT, ".nojekyll"), "w", encoding="utf-8").write("")
    readme = io.open(os.path.join(ROOT, "docs", "readme-public.md"), encoding="utf-8").read()
    io.open(os.path.join(OUT, "README.md"), "w", encoding="utf-8", newline="\n").write(readme)

    total = 0
    n = 0
    for r, d, fs in os.walk(OUT):
        parts = r.split(os.sep)
        if ".git" in parts or "src" in parts:
            continue
        for x in fs:
            total += os.path.getsize(os.path.join(r, x))
            n += 1
    print("站点已同步到 %s：%.1f MB / %d 个文件（不含 .git）" % (OUT, total / 1048576, n))

if __name__ == "__main__":
    main()