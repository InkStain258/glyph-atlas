# 歷代字形查詢 · Glyph Atlas

给古籍标注用的**离线字形查询工具**：一个汉字，一次看到它在甲骨、金文、楚簡、秦簡、傳抄古文、小篆、隸書，以及历代刻本、活字、现代字库里的样子。

在线站点：**<https://inkstain258.github.io/glyph-atlas/>**（纯静态，无后端）

---

## 能做什么

| 场景 | 能力 |
| --- | --- |
| 认一个生僻字 | 输入单字，横向列出各时代字形；某层没有就明确显示「未收錄」，**不回退系统字体**骗人 |
| 认印章 | 墨／朱文（白字红底）／白文（红字白底）三种印面预览 |
| 读整段古籍 | 粘贴一段原文，自动切成字表，每字标「有／无字形」 |
| 简繁／异体混用 | 输入「說」也会命中「説」「说」的字形，命中时标出实际用的是哪个字 |
| 一个字多种写法 | 同一书体下的异写挂在 `ss01…ss08`，点角标数字切换 |
| 只认得一半 | 「部件檢索」：选方位（左／右／上／下／中／外／内／任意）＋部件，反查结构相符的字 |
| 核对版权 | 「字體與版權」页按卡片列出每款的许可、条款标记与协议全文 |

## 收了多少

35 个图层、1,188 个按 `unicode-range` 切好的 WOFF2 分片（共 166 MB，浏览器按需加载，首屏约 19 MB）：

- **古文字 9 层**：甲骨 2,103 字、金文 3,459、楚文字 4,173、秦系簡牘 2,153、傳抄古文 13,000、小篆 10,591、說文小篆 10,879、開元小篆 9,713、隸書 5,679
- **历代书体 26 层**：思源宋/黑、霞鹜文楷、汇文明朝、昭源宋、花园明朝A、巴别石汉字、朱雀仿宋、Fandol 四款、禅老明朝、古书籍明朝、新テゴミン、悠司肅、芫荽、Klee One、草篆、马善政、龙藏、志莽、刘建毛草、站酷小薇、得意黑、霞鹜篆书

小篆三层并存是刻意的：`seal`（42.2%）+ 說文（55.2%）+ 開元（73.2%），并集 GB2312 一级 **76.7%**。

## 用法

直接用浏览器打开 `index.html` 即可，不需要服务器。也可以整个目录拷到 U 盘离线用。

## 数据来源与许可

- 字形：**hanzi-glyphs-svg**（逐层 CC0 / CC BY 4.0）、开源说文体、以及各类 OFL / GPL+FE / Arphic PL 字库
- 部件结构：**BabelStone IDS**（作者声明可自由使用，无需署名）
- 简繁异体：Unicode Unihan + OpenCC 映射，构建期使用

逐款条款见 [`LICENSES/THIRD-PARTY.md`](LICENSES/THIRD-PARTY.md)，协议全文在 [`LICENSES/`](LICENSES/)。
本项目截图与文档见 [`docs/`](docs/)。

## 不含什么

- **不做以形查字**：不能从拓片/印章图片自动识别文字。公开数据训练的印章识别准确率远达不到可用，实测字形比对在印章上的 IoU 仅 0.13–0.35。正确用法是：人工看笔势猜候选字 → 拉出所有写法并排比对。
- **没有魏碑**：至今没有合法免费字库，也没有 CC0 字形源，不硬凑。
- 字体二进制只在 Web 需要的那部分（分片 WOFF2）；原始 TTF 与完整字体库不在此仓库。

## 仓库与源码

本仓库即发布根（`index.html` / `css/` / `fonts/` / `data/` 直接由 GitHub Pages 提供）。
工程源码（`web/` `fonts/` 字库原件 `data/` 中间产物 `scripts/`）保存在作者本地的 `src/` 目录，
其中字库与 SVG 字形源约 2 GB，不适合进 Git。仓库里的 `scripts/` 是构建脚本的发布副本。

## 构建

```bash
python -X utf8 scripts/build_glyph_fonts.py --src <hanzi-glyphs-svg> \
    --layers oracle bronze chu qinwenzi chuanchao seal clerical --out .tmp_fonts --data .tmp_data
python -X utf8 scripts/make_layers_index.py
python -X utf8 scripts/build_modern_fonts.py
python -X utf8 scripts/make_web.py            # 切片 + unicode-range CSS
python -X utf8 scripts/build_ids.py           # 部件索引
python -X utf8 scripts/make_license_data.py   # 版权页数据
python -X utf8 scripts/make_public_site.py    # 打包成本站点
```

脚本需要 `fonttools[brotli]`、Python 3.12。`scripts/` 下每个脚本都有 docstring 说明输入输出。

## 目录

```
index.html / licenses.html      两页
app.js / parts.js / licenses.js 查询、部件检索、版权页
css/<layer>.css                 每层一个 @font-face + unicode-range 分片表
fonts/<layer>-n.woff2           1,188 个分片
data/                           layers / variants / ids / licenses / meta
docs/                           可行性报告、字体来源调研、截图
scripts/                        构建脚本
LICENSES/                       协议全文 + 第三方清单
```