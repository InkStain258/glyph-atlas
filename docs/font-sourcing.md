# 字体资产采集与核验说明（glyph-atlas）

> 本文记录「古今汉字字形查询工具」所用字体资产的**获取来源、许可判定依据、覆盖能力与体积**，
> 以及**没有获取的商业字体清单**（只列名与链接，仓库内不落地任何商业字库文件）。
>
> 配套产物：
> - `data/font-catalog.json` —— 机器可读目录（逐字体含 name 表原文、sha256、cmap 覆盖）
> - `scripts/verify_fonts.py` —— 核验脚本，可复跑，输出与上方 catalog 一致
> - `fonts/modern/<id>/` —— 第一轮 11 款可发布字体（迁移后布局：`original.ttf` + `subset.ttf` + 四件套）
> - `fonts/incoming/<id>/` —— 第二轮 16 款新字体（四件套：原文件 + `LICENSE.txt` + `NOTICE.md` + `license.json`）
> - `fonts/ancient/<layer>/` —— 由 CC0 字形 SVG 编译的古文字字体（甲骨/金文/楚简/秦简/传抄古文/小篆/隶书）
> - `fonts/quarantine/<id>/` —— 许可不可放行的字库（6 款，仅存档取证，不得用于产品）

最后更新：2026-11-03

---

## 1. 结论速览

| 指标 | 数值 |
|---|---|
| 可发布字体数 | **36 款现代字库**（第一轮 11 + 第二轮 16 + 第四轮 8，含 1 款仅归档；另有 8 类古文字形字体在 `fonts/ancient/`） |
| 原始文件总体积 | **483,552,640 B（461.1 MiB）**（36 款现代字库，不含古文字形字体） |
| 覆盖的目标书体 | **9 / 10 类**（宋体、古籍刻本风、楷书、行书、草书、仿宋、黑体、篆书、**魏碑**） |
| 古文字形字体（编译） | **8 类**：甲骨、金文、楚文字、秦系简牍、传抄古文、小篆、隶书、說文小篆 |
| 缺失书体 | **隶书**（唯一缺口：候选 wt021 因文鼎争议隔离，见 §16.3；另有 CC0 编译层 `fonts/ancient/clerical` 可作字形数据） |
| 隔离（不可发布） | **14 款**，见 §12、§16.3 |
| 拒绝下载 / 未落地 | I.Ming（IPA）、开元小篆（无编译产物）、GenRyuMin（无 LICENSE）等，见 §12.3 |
| 商业字库 | **0 个文件落地**，仅名录，见 §7 |

判定口径不是"看官网宣传"，而是**逐个文件读 OpenType `name` 表**（nameID 0/1/2/4/13/14），
把版权声明与许可声明原文抓出来写进 catalog，再与登记预期交叉校验，不一致即报错。

---

## 2. 许可政策（硬约束）

### 2.1 白名单

| SPDX 标识 | 含义 |
|---|---|
| `OFL-1.1` | SIL Open Font License 1.1（允许嵌入、修改、再分发；禁止单独售卖字体文件本身） |
| `CC0-1.0` | CC0 1.0 / Public Domain Dedication |
| `CC-BY-4.0` / `CC-BY-3.0` | 知识共享 署名（可商用、可改，需署名） |
| `GOV-ODL-1.0` | 政府资料开放授权条款（预留） |
| `FREE-COMMERCIAL-WRITTEN` | 明确书面「免费可商用」（预留，需附原始声明链接） |

### 2.2 黑名单（已出现或预判）

| 标识 | 为什么不行 |
|---|---|
| `CC-BY-ND-3.0` | 允许商用但**禁止改作**：与转 WOFF2、子集化、字形抽取直接冲突 |
| `IPA-1.0` | IPA Font License 1.0，不是 OFL，不在本项目策略内 |
| `PROPRIETARY` | All Rights Reserved / 非开源、禁止修改 |
| `UNKNOWN` | name 表无版权或许可信息，无法核验 |

### 2.3 判定流程（脚本内实现）

1. 用 `fontTools.ttLib.TTFont(lazy=True)` 打开文件，读 `name` 表全部记录；
2. 解码 `nameID 0`（版权）、`1`（家族）、`2`（子族）、`4`（全名）、`13`（许可）、`14`（许可 URL），
   兼容 UTF-16BE 与 Mac Roman 两种编码；
3. 按关键词分类（OFL / CC0 / CC BY-ND / IPA / Proprietary / CC BY），并抽取**许可原文片段**（≤240 字符）；
4. 与 `REGISTRY` 中人工登记的 `expected_spdx` 比对，不一致则在 catalog 里留 `license_mismatch` 字段；
5. 闸门：`raw/` 里出现非白名单许可 → 脚本报 `problems` 并拒绝写 catalog；`quarantine/` 里出现白名单许可 → 同样报错（防止错杀）。

### 2.4 逐案判例（容易误判的三例）

| 字体 | name 表实际情况 | 判定 | 理由 |
|---|---|---|---|
| 得意黑 Smiley Sans | nameID0 = `Copyright © 2022–2024 atelierAnchor. All rights reserved.`，nameID13 = OFL 1.1 全文 | **OFL-1.1** | 版权行写 All rights reserved 是 OFL 项目的常见写法；许可由 nameID13 明确声明，且上游仓库附 OFL.txt |
| 汇文明朝体 | nameID0 = `Public Domain`，**无 nameID13/14** | **CC0-1.0** | 字体自身声明公有领域；作者发布页另有中文授权声明（免费印刷/显示/嵌入、可转发、可随软件套装销售但不可单独转卖字体文件） |
| 霞鹜篆书 LXGW Seal | nameID13 = OFL 1.1 **+ ADDITIONAL PERMISSION** | **OFL-1.1** | 附加许可只放宽"未改源码的 WOFF/WOFF2 转换用于 web"，不限制本项目 |

---

## 3. 可发布字体清单（11 款）

体积单位：字节；WOFF2 列为 `fontTools.ttLib.woff2 compress` 实测（默认 brotli 参数，未子集化）。

| id | 字体 | 书体 | 年代 | 许可 | 字节 | WOFF2 | 占比 | cmap |
|---|---|---|---|---:|---:|---:|---:|---:|
| `notoserifsc` | 思源宋体 SC（可变） | 宋体 | 现代 | OFL-1.1 | 25,125,512 | 11,032,420 | 43.9% | 30,928 |
| `huiwenmincho` | 汇文明朝体 | 宋体（古籍刻本风） | 明（刻本复刻） | CC0-1.0 | 24,444,088 | 8,031,352 | 32.9% | 14,052 |
| `notosanssc` | 思源黑体 SC（可变） | 黑体 | 现代 | OFL-1.1 | 17,772,300 | 7,782,072 | 43.8% | 30,890 |
| `lxgwwenkai` | 霞鹜文楷 | 楷书 | 现代 | OFL-1.1 | 25,928,940 | 8,099,268 | 31.2% | 46,926 |
| `mashanzheng` | 马善政毛笔楷书 | 楷书 | 现代 | OFL-1.1 | 5,857,936 | 3,250,464 | 55.5% | 7,015 |
| `longcang` | 龙藏体 | 楷书 | 现代 | OFL-1.1 | 5,162,508 | 2,945,128 | 57.0% | 7,015 |
| `zhimangxing` | 志莽行书 | 行书 | 现代 | OFL-1.1 | 4,063,532 | 2,300,368 | 56.6% | 7,015 |
| `liujianmaocao` | 刘建毛草 | 草书 | 现代 | OFL-1.1 | 4,951,804 | 2,340,288 | 47.3% | 7,015 |
| `zhuque` | 朱雀仿宋 | 仿宋 | 现代（民国铅字风） | OFL-1.1 | 8,824,084 | 4,805,504 | 54.5% | 12,882 |
| `smileysans` | 得意黑 | 黑体（标题） | 现代 | OFL-1.1 | 2,629,764 | 1,151,368 | 43.8% | 9,440 |
| `lxgwseal` | 霞鹜篆书 | 篆书 | 秦（小篆） | OFL-1.1 | 227,780 | 68,744 | 30.2% | 512 |

### 3.1 逐款来源与说明

- **notoserifsc / notosanssc** — `github.com/google/fonts/tree/main/ofl/notoserifsc`、`.../ofl/notosanssc`。
  可变字体（`NotoSerifSC[wght].ttf` 等），nameID0 = `(c) 2017-2024 Adobe`，OFL 1.1。
  覆盖最全：GB2312 100%、GBK 100%、Big5 100%（逐字穷举），含扩展 A/B。
- **huiwenmincho** — 汇文明朝体 v1.0，经公共存档 `github.com/cntrump/imitation_typeface_fonts` 取得原始 TTF；
  作者发布页 `zhuanlan.zhihu.com/p/344103391`（特里王）。nameID0 = `Public Domain`。
  繁体为主（Big5 覆盖 61.3%），简体字亦有收录，**古籍刻本/明朝体风格**，是"古籍刻本风"的唯一落地款。
- **lxgwwenkai** — `github.com/lxgw/LxgwWenKai/releases/tag/v1.530`。OFL 1.1，含保留字体名
  `霞鹜 / 霞鶩 / 落霞孤鹜 / LXGW`（**再分发修改版时必须改名**，UI 展示不受影响）。
  覆盖 GB2312/GBK/Big5 各 100%，扩展 A 6,592 字、扩展 B 1,970 字 —— 是简繁与生僻字查询的主力。
- **mashanzheng / longcang / zhimangxing / liujianmaocao** — Google Fonts CJK 手写四款
  （`github.com/google/fonts/tree/main/ofl/<id>`）。四款 cmap 都是 7,015（= GB2312 6763 字 + 符号），
  **只覆盖 GB2312，无扩展区**；nameID13 均为 OFL 1.1 全文。适合书法风格展示，不适合生僻字查询。
- **zhuque** — 朱雀仿宋 v0.212，`github.com/TrionesType/Zhuque/releases/tag/v0.212`（zip 内为
  `ZhuqueFangsong-Regular.ttf`）。nameID0 = `Copyright 2023 JadeFoci`，OFL 1.1，cmap 12,882。
- **smileysans** — 得意黑 v2.0.1，`github.com/atelier-anchor/smiley-sans/releases/tag/v2.0.1`。
  注意发布的是 `SmileySans-Oblique.ttf`（唯一的倾斜字重），cmap 9,440。
- **lxgwseal** — 霞鹜篆书 v0.001-alpha.10.8，`github.com/lxgw/LxgwSeal/releases/tag/v0.001-alpha.10.8`。
  **只有 75 个篆字**（今字↔小篆映射），按 Unicode 18.0 小篆区块编码，字形借 Klee One / Gungsuh（均 OFL）。
  只能当"篆书示例"，不能当篆书字库用 —— 篆书全量请见 §6.2。

### 3.2 编码覆盖（逐字穷举，非抽样）

判定方法：用 Python 内置 codec 反解出**完整**字符集（`gb2312` 6,763 字、`gbk` 21,003 字、
`big5` 13,053 字），与 cmap 求交，覆盖率 ≥99% 记为"支持"。

| id | GB2312 | GBK | Big5 | 扩展 A | 扩展 B |
|---|---|---|---|---|---|
| notoserifsc | 100% | 99.995% | 99.971% | ✅ | ✅ |
| notosanssc | 100% | 99.995% | 99.971% | ✅ | ✅ |
| lxgwwenkai | 100% | 100% | 100% | ✅ | ✅ |
| huiwenmincho | 99.985% | 56.1% | 61.3% | ✅ | ✅ |
| zhuque | 100% | 52.5% | 59.1% | ✅ | ✅ |
| smileysans | 100% | 39.8% | 42.0% | ✅ | ✅ |
| mashanzheng / longcang / zhimangxing / liujianmaocao | 100% | 31.7% | 32.9% | ❌ | ❌ |
| lxgwseal | 2.4% | — | — | ✅（小篆区块） | ❌ |

> 说明：GBK/Big5 百分比低不等于"缺字"，而是这些字体本就不打算覆盖对应字符集
> （如手写四款只做 GB2312）；反过来 `notoserifsc` 的 99.995% 是**缺 1 个 GBK 码位**，catalog 的
> `encoding_note` 里写明了缺口个数，`gbk_coverage` 等字段保留小数供调用方自行设阈值。

---

## 4. 覆盖矩阵（书体 × 可用字体）

| 目标书体 | 落地字体 | 状态 |
|---|---|---|
| 隶书 | — | ❌ 无合法免费字库（§6.1 有 CC0 字形替代） |
| 楷书（含碑楷/写经楷） | `lxgwwenkai`、`mashanzheng`、`longcang` | ✅ 3 款 |
| 行书 | `zhimangxing` | ✅ |
| 草书 | `liujianmaocao` | ✅ |
| 魏碑 | — | ❌ 无合法免费字库（§6.3） |
| 宋体/明体 | `notoserifsc`、`huiwenmincho` | ✅ 2 款 |
| 仿宋 | `zhuque` | ✅ |
| 黑体 | `notosanssc`、`smileysans` | ✅ 2 款 |
| 篆书 | `lxgwseal`（仅 75 字）；**全量见 §6.2 CC0 SVG** | ⚠️ 部分 |
| 古籍刻本风 | `huiwenmincho` | ✅ |

---

## 5. 隔离区（已下载，但**不可用于产品**）

文件在 `fonts/quarantine/`，catalog 中 `status: "quarantine"`，保留是为了留证与后续申诉，不得进构建。

| id | 字体 | 判定许可 | 证据（name 表原文） | 隔离原因 |
|---|---|---|---|---|
| `tw-sung` | 全字庫正宋體（教育部標準宋體） | CC-BY-ND-3.0 | `(c) 本字形檔採創用CC姓名標示-禁止改作3.0臺灣版授權` | 禁止改作 → 不能转 WOFF2、不能子集化；且不允许做字形衍生 |
| `tw-kai` | 全字庫正楷體（教育部標準楷書） | CC-BY-ND-3.0 | 同上（`-ND-` 明确） | 同上 |
| `lxgwneoxihei` | 霞鹜新晰黑 v1.308 | IPA-1.0 | nameID13 = `https://opensource.org/licenses/IPA/`，`You must accept ... to use this product` | IPA 字体许可不在白名单 |
| `jinghua-laosong` | 京華老宋体 v2.002 | PROPRIETARY | nameID0 = `Font © Copyright 2022 TerryWang.All rights reserved.` | 作者页声明"非开源、勿修改、勿传播修改版" → 与 WOFF2 流程冲突 |
| `yishan-beizhuan` | 峄山碑篆体 | UNKNOWN | name 表**完全没有** nameID 0/13/14 | 无任何版权/许可信息，无法核验 |
| `beishida-shuowen-xiaozhuan` | 北师大说文小篆 | UNKNOWN / 专有 | nameID0 = `Proprietary for Sinica, all right reserved.` | 专有；且 `getBestCmap()` 为空（cmap 表无可用的 Unicode 子表），字形不可检索 |

> 后两款来自 `.dsh/skills/chinese-seal-research/assets/fonts/`，按 lead 要求**核验后**才决定是否复制：
> 核验结果均为不可放行，已只复制到 `quarantine/` 而未进 `raw/`。

### 5.1 拒绝下载（未落地任何文件）

- **I.Ming 一点明体**（`github.com/ichitenfont/I.Ming`，release 8.10，共 6 个文件、单文件约 25 MB）：
  仓库 README 与 `8.10/IPA_Font_License_Agreement_v1.0.md` 明确为 **IPA Font License 1.0**，
  非 OFL，不在白名单 → 未下载。
  （网上大量文章把它写成"开源可商用"，但许可文本是 IPA，与 OFL 的权利义务不同，不能当作 OFL 用。）

---

## 6. 书体缺口与替代方案

### 6.1 隶书 —— 没有合法的免费隶书字库（TTF/OTF）

排查过程：
- Google Fonts 的 CJK 字体全集只有 4 款手写 + Noto 系列 + 少量其他，**无隶书**；
- GitHub 检索 `lishu` / `隶书` / `clerical script chinese font` 的仓库，**无可用字库仓库**
  （唯一命中 `taekchef/weibei-english-font` 是英文字体）；
- 商业字库（汉仪、方正、文鼎、华康、阿里妈妈刀隶体、临海隶书等）**均为自定义授权**，
  官网/发布页措辞多为"免费商用"但**条款可随时变更、无 SPDX、无可核验的文件内许可**，
  不满足本项目"文件内许可可核验"的硬要求 → **不落地**（仅名录，见 §7）。

**替代方案（推荐）**：`github.com/zhouyongh/hanzi-glyphs-svg`
—— 汉字字形 **SVG** 库，逐层许可不同，其中：

| 层 | 目录 | 数量 | 许可 |
|---|---|---|---|
| **隶书** | `glyphs/clerical/` | **12,597 个 SVG** | **CC0 1.0** |
| 篆书 | `glyphs/seal/` | 10,591 个 SVG | CC0 1.0 |
| 金文 | `glyphs/bronze/` | 11,691 个 SVG | CC0 1.0 |
| 甲骨文 | `glyphs/oracle/` | 11,416 个 SVG | CC0（其中 1,203 条 CC BY 4.0） |
| 楷/行/草/宋/黑（现代六层） | `glyphs/{kaishu,xingshu,caoshu,songti,songti-tc,heiti-hk}/` | 各 6,763 | OFL 1.1（从 OFL 字体抽轮廓） |

- 隶书层来源：汉典（zdic.net）书法隶书实例 + 中研院「小學堂」隸變庫的位图描摹件；
  每条在 `glyphs/provenance/clerical.jsonl` 有 `source_book`（如「老子乙前93下」「漢印徵」）、
  `period`（西漢/東漢/唐…）、`sha256` 与 `source_url` —— **可溯源，正合"字形查询"场景**。
- CC0 是公有领域奉献，**不要求署名、允许修改与商用**，可放心入库；
  但注意它是 SVG 轮廓，不是字体文件：**要在产品里用，得走 SVG 渲染或自行编译成自有字体**。
- 本仓库未把该目录批量下载进 `fonts/raw/`（交付路径只允许字体文件 + catalog + 说明 + 脚本），
  已在此记录决策依据与坐标，供后续 pipeline 直接取用。

### 6.2 篆书 —— 覆盖严重不足，同样建议用 CC0 SVG

已落地的 `lxgwseal` 只有 **75 个篆字**，作为篆书查询工具几乎不可用；
`yishan-beizhuan`（3,849 字形）与 `beishida-shuowen-xiaozhuan`（19,879 字形但 cmap 为空）都因许可问题进隔离区。
**可用方案仍是 `hanzi-glyphs-svg` 的 `glyphs/seal/`：10,591 个篆书 SVG，CC0 1.0，逐字有出处**
（汉典《服务条款》第四条以 CC0 释出，见该仓库 `LICENSE-DATA`）。
若产品必须用字体文件渲染篆书，则需自行从这些 CC0 轮廓编译字体，或采购商业篆书字体授权。

### 6.3 魏碑 —— 没有合法的免费魏碑字库

- 市面魏碑字体（汉仪敦煌当代魏楷、方正魏碑系列、华康/文鼎魏碑等）**全部为商业字库**；
- GitHub 只有英文魏碑风字体（`taekchef/weibei-english-font`），不含汉字；
- `hanzi-glyphs-svg` 的 13 个书体层里**没有**魏碑层。
- 结论：**魏碑是本项目唯一连"替代数据源"都没有的书体**。可行路径只有三条：
  ① 采购商业授权（汉仪/方正）；② 自建（专家摹写 + 授权清晰）；③ 产品里暂时不提供魏碑筛选。

> 没有为了凑满 10 类而放宽许可：把 CC BY-ND 的 TW-Sung/TW-Kai、IPA 的霞鹜新晰黑、
> 或自定义条款的商业隶书/魏碑塞进 `raw/` 会让整个项目承担版权风险 —— 这正是用户明确要规避的。

---

## 7. 未获取的商业字体清单（仅名录，仓库内**无任何文件**）

> 以下字体**没有下载、没有解包、没有入库**，仅作为"若将来采购/对照"的线索。
> 报价一律以厂商当期页面为准（多数厂商不公开报价，需在线询价/按用途购买）。

| 厂商 | 代表字体（与本项目书体的关系） | 官网 | 授权 / 报价入口 |
|---|---|---|---|
| 汉仪字库 | 汉仪敦煌当代魏楷（魏碑）、汉仪秦川飞影篆书（篆书） | https://www.hanyi.com.cn/ | 授权说明 http://www.hanyi.com.cn/law.php/license ；个人非商用须知 https://www.hanyi.com.cn/custom-font-case-7/faq-doc-1 |
| 方正字库 | 方正魏碑、方正清刻本悦宋 / 宋刻本秀楷（古籍刻本风）、方正隶书 | https://shop.foundertype.com/ | 企业官网授权（含报价入口） https://shop.foundertype.com/index.php/BuyAuth/empowerFonts/bid/58.html ；网络广告授权 https://shop.foundertype.com/index.php/BuyAuth/empowerFonts/bid/53.html |
| 文鼎 Arphic | 文鼎隶书、文鼎魏碑系列 | https://ifontcloud.com.cn/ | 文鼎云字库订阅与授权 FAQ https://ifontcloud.com.cn/index/qa.jsp |
| 华康 DynaComware | 华康隶书、华康魏碑、华康古籍系列 | https://www.dynacw.com.cn/ | 华康典藏（字库商品页） https://www.dynacw.com.cn/netshop/netshop_dynalibrary.aspx |
| 华文 SinoType | 华文隶书、华文行楷、华文魏碑 | （厂商页，字客网收录） https://m.fontke.com/foundry/6328/introduction/ | 需向厂商询价 |
| 字魂 | 字魂隶书类、字魂魏碑类 | https://izihun.com/ | 站内授权/会员页 |
| 锐字家族 Reeji | 锐字真言体等（艺术黑体；隶书/魏碑需另购） | http://www.reeji.com/ | 免费商用页（仅限指定字体） http://www.reeji.com/font/ruizizhenyantimianfeishangyong.html |
| 叶根友 | 叶根友毛笔隶书、叶根友魏碑 | http://www.yegenyou.com/ | 站内授权说明 http://www.yegenyou.com/faq-1.htm |
| 阿里巴巴 / 阿里妈妈 | 阿里妈妈刀隶体（自称免费商用，平台自定义条款、无 SPDX） | 官方渠道为阿里巴巴设计/iconfont | 第三方介绍（仅供线索） https://www.uisdc.com/alimama-daoliti |
| 独立作者 | 临海隶书（隶书） | — | 字体站预览 https://www.hellofont.cn/font-detail?fontid=54586 、 https://51font.17font.com/detail/df9bff90d45711eeb6f015b9d0db302f |

**为什么连"免费商用"的也不收？**
阿里妈妈刀隶体、临海隶书这类字体确实宣称免费商用，但：①条款挂在厂商页面而非文件内，
可单方面变更，无法随文件一起归档举证；②无 SPDX 标识，法务无法机械核验；
③文件名/版本频繁变动，难以固定 sha256。本项目采用"**文件内许可 + 原文摘录 + sha256 固定**"的
可审计模型，这类字体不满足，因此只列入名录、不落地。

### 7.1 未获取但可能合规的候选（**尚未核验**，不建议直接使用）

| 候选 | 已知情况 | 未采纳原因 |
|---|---|---|
| GenRyuMin 源流明体 / GenSekiGothic（ButTaiwan） | 基于思源系列，通常为 OFL | 与 Noto Serif / 汇文明朝体功能重复，未下载 |
| BabelStone Han | 作者页面称免费，覆盖极广 | 单文件约 50 MB；许可声明为作者自定义措辞，需逐字核验后才能用 |
| 花园明朝 HanaMin A/B | 老牌宽覆盖字体 | 许可为作者自定义（非 OFL），未核验 → 不落地 |
| 台湾教育部全字库（TW-Sung/TW-Kai 官方原始下载） | 政府开放数据 | 已下载的镜像文件 name 表明确为 **CC BY-ND 3.0**；若官方另有更宽松条款，需以官方文件为准重新核验 |

---

## 8. 复跑与目录结构

### 8.1 复跑

```bash
cd glyph-atlas
python scripts/verify_fonts.py            # 全量：读 name 表 + 覆盖统计 + WOFF2 实测 → 写 catalog
python scripts/verify_fonts.py --no-woff2 # 跳过 WOFF2 压缩（快，适合只查许可）
python scripts/verify_fonts.py --check-only  # 只跑闸门，不写文件（CI 用）
```

- 依赖：`fontTools >= 4.40`、`brotli`（WOFF2 用）。Windows / Linux / macOS 均可。
- WOFF2 结果按 `sha256[:16]` 缓存在 `%TEMP%/glyph-atlas-woff2-cache/`，重复跑不重算。
- 脚本不修改任何原字体文件，转换只在临时目录进行。
- 退出码：闸门 `problems` 非空时返回 1。

### 8.2 目录

```
glyph-atlas/
├─ fonts/
│  ├─ raw/          # 11 款，许可已核验，可进构建
│  └─ quarantine/   # 6 款，仅存档取证，禁止进构建
├─ data/font-catalog.json
├─ docs/font-sourcing.md
└─ scripts/verify_fonts.py
```

### 8.3 catalog 字段

| 字段 | 含义 |
|---|---|
| `id` | 稳定标识（= 文件名主干） |
| `status` | `shipped` / `quarantine` |
| `name_zh` / `name_en` / `era` / `style` / `style_detail` | 中文名 / 英文名 / 年代 / 书体（9 类枚举）/ 细分风格 |
| `license_spdx` | 由 name 表判定的 SPDX 标识 |
| `license_text_excerpt` | name 表许可原文片段（≤240 字符，未改写） |
| `license_url` | 许可全文或作者授权声明所在页 |
| `source_url` | 文件下载来源（release 页 / 仓库 / 作者页） |
| `file` / `format` / `bytes` / `sha256` | 相对路径、容器格式、字节数、整文件校验和 |
| `woff2_bytes` | 转 WOFF2 后的字节数（`--woff2` 时才有；`--no-woff2` 时该键不存在） |
| `num_glyphs` / `cmap_entries` | `maxp.numGlyphs` / `getBestCmap()` 码位数 |
| `has_cjk_unified` / `has_ext_a` / `has_ext_b` | 是否含 U+4E00–9FFF / U+3400–4DBF / U+20000–2A6DF |
| `gb2312_coverage` / `gbk_coverage` / `big5_coverage` | 完整字符集覆盖率（0–1，逐字穷举） |
| `has_gb2312` / `has_gbk` / `has_big5` | 覆盖率 ≥99% 的布尔化结果 |
| `encoding_note` | 覆盖率与缺口个数的自然语言说明（含逐款补充提示） |
| `coverage_sample` | 固定种子随机抽 10 个常用字，逐个记录 `in_cmap` 与 `has_outline`（轮廓非空） |
| `font_family` / `font_version` | name 表 nameID 1 / 5 |
| `name_table` | name 表全量记录（含 nameID 0/13/14 原文） |
| `notes` / `license_mismatch` | 人工备注 / 登记与实测不一致时的提示 |

`summary` 块给出：`shipped_count`、`quarantine_count`、总体积、WOFF2 总体积、压缩比、
`styles_covered` / `styles_missing` / `style_to_ids`、`genres_covered` / `genres_missing` / `genres_to_ids`。

---

## 9. 体积与可行性

| 维度 | 数字 |
|---|---|
| 全量 raw | 119.2 MiB（11 款，124,988,248 B） |
| 全量 WOFF2 | 49.4 MiB（51,806,976 B，41.4%） |
| 最大单文件 | `lxgwwenkai` 24.7 MiB（WOFF2 7.7 MiB）、`notoserifsc` 24.0 MiB（10.5 MiB）、`huiwenmincho` 23.3 MiB（7.7 MiB） |
| 最小可用组合 | `notosanssc` + `notoserifsc` + `lxgwwenkai` → 65.6 MiB raw / 25.7 MiB WOFF2，覆盖 GB2312/GBK/Big5 与扩展 A/B |

结论：**不做子集化也能上 web**（49 MiB 是首屏可分批懒加载的量级）；
若按字表子集化（如只留 GB2312 + 常用扩展 A），单款可再降到 2–4 MB，
但**注意保留字体名规则**（`lxgwwenkai` 有 RFN 保留名，子集化属修改，发布时分发名需去掉保留名）。
所有可发布字体均为 OFL/CC0，**允许子集化与 WOFF2 转换**；CC BY-ND 的两款已隔离，不参与任何转换。

---

## 10. 参考链接

- SIL OFL 1.1：https://openfontlicense.org
- Google Fonts 字体仓库：https://github.com/google/fonts
- 霞鹜文楷：https://github.com/lxgw/LxgwWenKai
- 霞鹜篆书：https://github.com/lxgw/LxgwSeal
- 霞鹜新晰黑（IPA，已隔离）：https://github.com/lxgw/LxgwNeoXiHei
- 朱雀仿宋：https://github.com/TrionesType/Zhuque
- 得意黑：https://github.com/atelier-anchor/smiley-sans
- 汇文明朝体作者页：https://zhuanlan.zhihu.com/p/344103391
- 京華老宋体作者页（专有，已隔离）：https://zhuanlan.zhihu.com/p/677725322
- 仿制字体公共存档：https://github.com/cntrump/imitation_typeface_fonts
- 台湾教育部语言司（全字库）：https://language.moe.gov.tw/
- 汉字字形 SVG 库（隶书/篆书/金文 CC0 层）：https://github.com/zhouyongh/hanzi-glyphs-svg
- IPA Font License 1.0：https://opensource.org/licenses/IPA/

---

## 11. 第二轮新增：16 款（古代/历史书体优先）

第二轮目标：补齐古代/历史书体。做法是**先搜古代书体字库，再搜历史谱系字面，最后才是现代字体**。
本轮 16 款全部通过「name 表原文 + 上游 LICENSE/NOTICE 全文」双重核验，四件套落在
`fonts/incoming/<id>/`（原文件 + `LICENSE.txt` + `NOTICE.md` + `license.json`）。

### 11.1 新增清单与覆盖

（GB2312 一级 = 3755 常用字、二级 = 3008 次常用字；逐字穷举求交，非抽样。）

| id | 字体 | era | style | 一级 | 二级 | GBK | 许可 | 体积（MiB） |
|---|---|---|---|---|---|---|---|---|
| `babelstone-han` | BabelStone Han | 现代（1994–2025） | 宋体 | 3755 | 3008 | 21636 | Arphic-PL-1.0 | 49.56 |
| `hanamin-a` | 花园明朝A | 现代（2008–2017） | 宋体 | 3755 | 3008 | 21791 | OFL-1.1 / HFL | 21.71 |
| `hanamin-b` | 花园明朝B | 现代（2008–2017） | 宋体 | 4 | 0 | 6 | OFL-1.1 / HFL | 29.32 |
| `fandol-song` | Fandol 宋（开元宋） | 现代（2012–2013） | 宋体 | 3755 | 3008 | 8735 | GPL-3.0+FE | 4.72 |
| `fandol-kai` | Fandol 楷（开元楷） | 现代（2012–2013） | 楷书 | 3755 | 3008 | 8717 | GPL-3.0+FE | 7.43 |
| `fandol-hei` | Fandol 黑（开元黑） | 现代（2012–2013） | 黑体 | 3755 | 3008 | 8660 | GPL-3.0+FE | 5.54 |
| `fandol-fang` | Fandol 仿宋 | 现代（2012–2013） | 仿宋 | 3755 | 3008 | 8721 | GPL-3.0+FE | 6.64 |
| `iansui` | 芫荽 | 现代（2025） | 楷书 | 2722 | 1744 | 10814 | OFL-1.1 | 9.01 |
| `chiron-sung-hk` | 昭源宋体（香港） | 现代（2020–2024） | 宋体 | 3755 | 3008 | 21791 | OFL-1.1 | 23.69 |
| `zcoolxiaowei` | 站酷小薇体 | 现代（2018） | 宋体 | 3755 | 3008 | 6903 | OFL-1.1 | 6.02 |
| `kleeone` | Klee One（教科书楷） | 现代（2020） | 楷书 | 2501 | 1279 | 8647 | OFL-1.1 | 8.32 |
| `zenoldmincho` | 禅老明朝 | 现代复刻（江户—明治） | 宋体 | 2384 | 994 | 7306 | OFL-1.1 | 5.19 |
| `kaiseitokumin` | Kaisei Tokumin | 现代复刻（明治活字） | 宋体 | 2389 | 996 | 7391 | OFL-1.1 | 4.37 |
| `newtegomin` | 新テゴミン | 现代复刻（明治木活字） | 宋体 | 2370 | 961 | 6757 | OFL-1.1 | 7.11 |
| `grassseal` | 草篆（GrassSeal 汉字面） | 现代复刻（小篆） | 篆书 | **1345** | 48 | — | OFL-1.1 | 4.08 |
| `yujisyuku` | Yuji Syuku | 现代（毛笔楷/写经风） | 楷书 | 2399 | 997 | 8013 | OFL-1.1 | 8.04 |

补充说明：

- **`hanamin-b`、`grassseal` 标 `supplemental`**：一级命中 <1500（4 / 1345 字），只能作生僻字/篆书回退，不能作正文用字。catalog 里 `supplemental: true`。
- **日文字面（`kleeone` / `zenoldmincho` / `kaiseitokumin` / `newtegomin` / `yujisyuku`）**：虽能命中 2370–2501 个 GB2312 一级码位，但字形是日文汉字写法，简体正文排版会露出日式笔画差异，定位为「历史谱系/风格展示」，不作简体正文首选。
- **真正补齐古代书体的是 `fonts/ancient/`**（甲骨/金文/楚简/秦简/传抄古文/小篆/隶书，由 CC0 字形 SVG 编译），见 §13；本轮 16 款补的是「历史谱系字面」与「宽覆盖生僻字」。

### 11.2 许可放行依据（原文，非印象）

**BabelStone Han → `Arphic-PL-1.0`（放行）**

- 作者页（https://www.babelstone.co.uk/Fonts/Han.html）原文：字体 "released under the original Arphic Public License, and may be used and distributed freely for personal or commercial purposes"，且明确允许任意修改，前提是修改版**保留 Arphic Public License** 并**在字体名中不得使用 BabelStone**。
- 字体 `nameID 13` 内嵌整段 ARPHIC PUBLIC LICENSE，`nameID 14` 指向 GNU 镜像全文：
  http://ftp.gnu.org/non-gnu/chinese-fonts-truetype/LICENSE（`ARPHICPL.TXT`，6,959 B，1999 原始版）。
- 关键区别：**1999 原始版**允许 verbatim 复制分发、任意修改、修改版按同许可再分发，并允许收费服务；
  2010 新版 Arphic PL 反而限制非营利使用 —— BabelStone 用的是旧版，所以放行。四件套里的 `LICENSE.txt` 就是这份 1999 原文。

**花园明朝 HanaMinA/B → `OFL-1.1`（放行）**

- 字体 name 表只有 `nameID 0 = "Created by GlyphWiki."`，没有 license 字段 —— 单看 name 表会误判 `UNKNOWN`。
- 判定依据是上游发行包内的 `LICENSE.txt`（Debian `fonts-hanazono_20170904.orig.tar.bz2`），明示**双许可**：
  ① Hanazono Font License："Unlimited permission is granted to use, copy, and distribute it, with or without modification, either commercially and noncommercially"；
  ② SIL OFL 1.1，保留名为 `Hanazono Font`、`HanaMinA`、`HanaMinB`、`花園フォント`、`花園明朝A`、`花園明朝B`。
- 本项目按 OFL 1.1 使用，`LICENSE.txt` 保留上游双许可全文。

**Fandol 四款 → `GPL-3.0+FE`（放行）**

- CTAN `fandol` 包 README 原文："These fonts's licensing is GPL + GPL font exception."
- 上游 `COPYING` 是 **GPL v3 全文**，第 676–683 行为字体嵌入例外条款（把字体嵌入文档不使文档传染 GPL）。
- 字体 `nameID 13` 为空、`nameID 14 = http://www.gnu.org/licenses/licenses.html`、`nameID 0 = "Copyright © 2012-2013, the Fandol team."`。
- 满足「允许修改 + 允许再分发 + 允许商用」，但**衍生/转换版本须继续按 GPL+FE 分发**（与 OFL 不同的义务，产品分发时要在关于页注明）。

**Google Fonts 六款（zcoolxiaowei / kleeone / zenoldmincho / kaiseitokumin / newtegomin / yujisyuku）+ Chiron Sung HK + Iansui + GrassSeal → `OFL-1.1`**

- Google Fonts 各款 `nameID 13` 均为标准 OFL 1.1 原文、`nameID 14` 指向 https://openfontlicense.org，仓库路径 `ofl/<slug>/` 亦为佐证；四件套 `LICENSE.txt` 为上游 `OFL.txt` 原文。
- Chiron Sung HK 的 `LICENSE.md` 只在 release 分支（main 分支 404），内容为 "Copyright 2021-2026 Tamcy … SIL Open Font License 1.1"；`nameID 0` 保留 Adobe 版权行（源自思源宋体），已一并保留。
- GrassSeal（`dmitryalexander/tenshogi`）`OFL.txt` 署名 "GrassSeal contributors; Kaiyuan Small Seal Font Contributors"；上游 README 自述"未经全面人工复核"、215 字为艺术补形 —— 已如实标注。

### 11.3 体积与 WOFF2（本轮 16 款）

| 项 | 数值 |
|---|---|
| 16 款原始合计 | **210,491,124 B（200.7 MiB）** |
| 16 款 WOFF2 合计 | **82,674,872 B（78.8 MiB）**，为原始的 **39.3%** |
| 全库（36 款现代字库）原始合计 | **483,552,640 B（461.1 MiB）** |
| 全库 WOFF2 合计 | **134,481,848 B（128.3 MiB）**，为原始的 **40.1%** |
| 最大三款（原始 → WOFF2） | BabelStone Han 49.56 → 8.95 MiB、HanaMinB 29.32 → 11.47 MiB、Chiron Sung HK 23.69 → 14.59 MiB |
| 最省的三款 | Iansui 9.01 → 2.85 MiB、Klee One 8.32 → 2.73 MiB、Zen Old Mincho 5.19 → 1.91 MiB |

逐款 WOFF2（字节）：

| id | 原始 | WOFF2 | 比率 |
|---|---:|---:|---:|
| `babelstone-han` | 51,971,284 | 9,383,116 | 18.1% |
| `hanamin-b` | 30,739,236 | 12,027,336 | 39.1% |
| `chiron-sung-hk` | 24,838,976 | 15,294,020 | 61.6% |
| `hanamin-a` | 22,761,228 | 7,704,020 | 33.8% |
| `iansui` | 9,447,424 | 2,983,096 | 31.6% |
| `kleeone` | 8,724,204 | 2,864,632 | 32.8% |
| `yujisyuku` | 8,430,348 | 4,067,668 | 48.2% |
| `fandol-kai` | 7,790,552 | 4,442,532 | 57.0% |
| `newtegomin` | 7,450,688 | 3,777,352 | 50.7% |
| `fandol-fang` | 6,961,384 | 4,521,224 | 64.9% |
| `zcoolxiaowei` | 6,313,808 | 2,633,132 | 41.7% |
| `fandol-hei` | 5,808,908 | 3,746,664 | 64.5% |
| `zenoldmincho` | 5,442,512 | 2,007,296 | 36.9% |
| `fandol-song` | 4,947,904 | 3,332,888 | 67.4% |
| `kaiseitokumin` | 4,581,732 | 2,129,168 | 46.5% |
| `grassseal` | 4,280,936 | 1,760,728 | 41.1% |

> 说明：Fandol 四款是 OpenType/CFF，WOFF2 压缩率明显差于 TrueType（67% vs 30% 量级）——
> 若要压体积，优先选 glyf 轮廓的字体；CFF 字体可考虑先转 TrueType 再压缩（属修改，需遵守 GPL+FE/OFL）。
> HanaMinB 30 MB、6 万复杂字形，brotli 单文件约 7 分钟，已单独后台测量完成。

---

## 12. 隔离区与本轮复核结论

### 12.1 本轮复核的三款：全部放行（附条件）

| 字体 | 结论 | 依据 | 我们承担的义务 |
|---|---|---|---|
| BabelStone Han | ✅ 放行 | Arphic PL 1999（见 §11.2） | 保留许可全文；修改版改名（不得用 BabelStone 名义） |
| HanaMinA / HanaMinB | ✅ 放行 | 上游双许可含 OFL 1.1（见 §11.2） | 保留双许可全文；分发修改版不得用 6 个保留名 |
| Fandol 四款 | ✅ 放行 | GPL v3 + 字体例外（见 §11.2） | 衍生/转换版本按 GPL+FE 分发，附源码/许可 |

### 12.2 仍在隔离区（6 款，本轮无新增）

第一轮已隔离的 6 款维持原判，本轮**没有新增隔离**：

| id | 许可判定 | 原因 |
|---|---|---|
| `tw-sung` / `tw-kai` | CC-BY-ND-3.0 | 允许商用但**禁止改作**，与子集化/转 WOFF2 冲突 |
| `lxgwneoxihei` | IPA-1.0 | IPA 字体许可，不在白名单 |
| `jinghua-laosong` | PROPRIETARY | 作者声明"非开源、勿修改、勿传播修改版" |
| `beishida-shuowen-xiaozhuan` | PROPRIETARY | "Proprietary for Sinica" 且 cmap 无可检索子表 |
| `yishan-beizhuan` | UNKNOWN | name 表无 0/13/14 字段，无法核验 |

### 12.3 调研后未落地

| 候选 | 为什么不下 |
|---|---|
| I.Ming 一点明体 | 官方 README 与 `IPA_Font_License_Agreement_v1.0.md` 证实 IPA 1.0，不在白名单 |
| 开元小篆（kaiyuan-small-seal-font） | 仓库只有字形 SVG 与脚本，**无编译产物**，不能作为字库落地 |
| GenRyuMin 源流明体 | v2.100 release 资产为 71–74 MB zip，仓库根目录无 LICENSE 文件，许可无法随文件举证 |
| 阿里妈妈刀隶体 / 临海隶书 / 汉仪敦煌当代魏楷 | 商业平台的"免费商用"自定义条款（可单方变更、无 SPDX、无法随文件取证），只列名录 |
| 汉仪 / 方正(非 Fandol) / 文鼎 / 华康 / 华文 / 字魂 / 锐字 / 叶根友 | **硬规则禁止下载**，仅名录与官网链接（见 §7） |

---

## 13. 古代字形数据源候选（只调研，编译由构建管线完成）

古代书体（先秦甲骨/金文/简牍、小篆、隶书）在字体市场**没有合法开放字库**。
可用的替代路径是「CC0/CC BY 字形 SVG → 编译成字体」，本轮已据此落地 `fonts/ancient/`：

| 数据源 | 层 | 字形数量 | 许可 | 获取方式 | 状态 |
|---|---|---|---|---|---|
| `github.com/zhouyongh/hanzi-glyphs-svg` | `glyphs/oracle/` 甲骨 | 11,416 SVG（去重后字头 2,114） | CC0 1.0（其中 1,203 条 JGW 层为 CC BY 4.0） | git clone / raw | ✅ 已编译为 `fonts/ancient/oracle/` |
| 同上 | `glyphs/bronze/` 金文 | 11,691 SVG（字头 3,459） | CC0 1.0 | 同上 | ✅ `fonts/ancient/bronze/` |
| 同上 | `glyphs/chu/` 楚文字 | 字头 4,173 | CC0 1.0 | 同上 | ✅ `fonts/ancient/chu/` |
| 同上 | `glyphs/qinwenzi/` 秦系简牍 | 字头 2,153 | CC0 1.0 | 同上 | ✅ `fonts/ancient/qinwenzi/` |
| 同上 | `glyphs/chuanchao/` 传抄古文 | 字头 13,000 | CC0 1.0 | 同上 | ✅ `fonts/ancient/chuanchao/` |
| 同上 | `glyphs/seal/` 小篆 | 10,591 SVG | CC0 1.0 | 同上 | ✅ `fonts/ancient/seal/` |
| 同上 | `glyphs/clerical/` 隶书 | 12,597 SVG（字头 5,679） | CC0 1.0 | 同上 | ✅ `fonts/ancient/clerical/`（**补上第一轮隶书缺口**） |
| 同上 | `glyphs/{kaishu,xingshu,caoshu,songti,songti-tc,heiti-hk}/` | 各 6,763 SVG | OFL 1.1 | 同上 | 备用（已有等价字体，不重复编译） |
| NDL（日本国立国会图书馆）《新撰篆書字典》1924 | 篆书扫描 | — | 公有领域（PDM） | NDL Digital Collections | 已被 GrassSeal 用作字形来源，间接使用 |
| 敦煌遗书 IDP | 写经字形 | — | **逐件不同，多为非商业** | idp.bl.uk | ❌ 不可整批商用，需逐件核 rights |
| 中央研究院「小學堂」隸變庫 | 隶变字形 | — | 学术使用条款 | 站点检索 | ❌ 许可不明，不落地 |
| 汉典书法（zdic.net） | 隶书实例 | — | 版权不明 | 网页 | ⚠️ hanzi-glyphs-svg 的隶书层用它作**参考**，落地的是 CC0 描摹件 |

**结论（必须如实说明）**：

1. **先秦甲骨、金文、楚简、秦简、传抄古文、小篆、隶书**：**没有任何一款合法开放「字体」**，但都有 CC0/CC BY 字形数据源，已编译成字体（`fonts/ancient/`），并在 `license.json` 中逐层标注许可。
2. **魏碑**：唯一连替代数据源都没有的书体 —— 商业字库全收费，开放 SVG 库无魏碑层，GitHub 仅 `taekchef/weibei-english-font`（英文字体，非汉字）。**本项目不提供魏碑，不是为了凑数而放宽许可。**
3. 字头数（去重后的 `modern_char`）远小于 SVG 文件数，原因是同一字有多个异体/拓片来源；编译时按字头去重，保留每字一个代表字形。
4. 数据源根目录 `LICENSE`（CC BY 4.0）只覆盖甲骨 JGW 层；其余层以仓库 `LICENSE-DATA` 为准（逐层 CC0）。**不能用一个根许可推断全仓库。**
---

## 14. 后记：北师大说文小篆的解禁（唯一一笔专有许可）

`beishida-shuowen-xiaozhuan`（`BeiShiDaShuoWenXiaoZhuan-1.ttf`）最初因 name 表 `Proprietary for Sinica, all right reserved.` 且 cmap 只有 Big5 码位，被移入隔离区（见 §12.2、§13）。

**2026-11-03 使用方确认**：「北师大说文小篆可以用，我们就是北师大文学院的项目组，这个工具本身也仅用于学习。」

据此解禁，但**没有把它当成开源字库**：

| 项 | 处理 |
| --- | --- |
| 版权原文 | 上游 nameID 0 原样保留在 `fonts/ancient/beishida/glyphs.ttf`，不被覆盖 |
| 授权说明 | `fonts/license-texts/PROJECT-GRANT.txt`（上游原文 + 项目组授权 + 本项目所做改动 + 用途限制） |
| 本项目改动 | **cmap 码位转换**（Big5 → Unicode，含 format 4 / format 12 / platformID 0 子表）、**剔除指向空轮廓的码位**（19,877 个码位里 7,559 条为空）、**刚性归一化**（等比缩放 + 平移，对齐各层设计框）；字形轮廓未改一笔 |
| 条款标记 | `license_spdx: PROJECT-GRANT`、`attribution_required: true`、`commercial_use_allowed: false`、`redistribution_allowed: false` |
| 页面呈现 | 版权页单独徽章「項目組授權」，标签为「需署名 / 可修改 / 禁商用」 |

**它解决了什么**：hanzi-glyphs-svg 的 `seal` 层缺 `二`、`川`、`口` 这类基本字（上游 CSV 没这几行，见 §5.1）；说文小篆把它们补齐。该层实收 **10,879 字**，GB2312 一级 **2,073（55.2%）**，与 `seal` 层并集 2,089（55.6%）——**远低于早期按码位存在性估的 74%，那是没剔除空轮廓的错误数字**。真正把一级推到 73% 的是第三轮的开元小篆（见 §15）。

**没有波及的部分**：其余 6 款隔离字库（TW-Sung / TW-Kai / 霞鹜新晰黑 / I.Ming / 京华老宋体 / 峄山碑篆体）照旧不进仓库，只留许可留档。

> **隔离区当前的二进制策略（第四轮起统一）**：`fonts/quarantine/<id>/original.ttf` 仅在**本机**留档，不随 Git 仓库分发、不进入发布物（`src/` 整体被 `.gitignore` 排除，`make_public_site.py` 只同步 `web/`、`LICENSES/` 与 `fonts/license-texts/`）。保留二进制是为了将来拿到授权或争议澄清时**可直接复核、无需重新下载**；`license.json` 里 `quarantine_basis` 区分「条款本身不允许（license）」与「条款干净但来源存疑（provenance）」——后者如实写 `modification_allowed/redistribution_allowed/commercial_use_allowed = true`，不能因为隔离就把条款说反。

---

## 15. 第三轮：小篆第二个字形源的调研与落地（2026-11-03）

**问题**：`fonts/ancient/seal/` 的一级字覆盖只有 **1,583/3,755（42.1%）**，`二`/`川`/`口` 这类基本字都缺；北师大说文（PROJECT-GRANT）虽把一级提到 74%，但它**不可再分发、不可商用**，不能作为开源层交付。本轮要找「许可干净、覆盖率明显高于 42%」的第二条小篆数据源。

**结论速览**：

| 方案 | 许可 | GB2312 一级 | 可再分发 | 结论 |
| --- | --- | --- | --- | --- |
| 现有 `fonts/ancient/seal` | CC0 1.0（汉典描摹） | 1,583（42.1%） | ✅（但上游口径存疑） | 基线 |
| **开元小篆（本项目自行编译）** | **OFL-1.1** | **2,748（73.2%）** | ✅ | ✅ **已落地** `fonts/incoming/shuowen-seal-kaiyuan/` |
| yigezi 合并字体（开元 + 全字库） | OFL-1.1 + OGDL-Taiwan-1.0 | 3,046（81.1%） | ✅（须显名全字库） | ⚪ 可选，未落地 |
| 全字库说文解字 | OGDL-Taiwan-1.0 | 6,721 字形（未实测） | ✅（须显名） | ⚪ 官网不可达、镜像需登录，**未取得** |
| 北师大说文（PROJECT-GRANT） | 项目组书面授权 | 2,073（55.2%） | ❌ 禁商用/禁再分发 | 仅内部使用 |
| 崇羲篆体 | CC BY-ND 3.0 TW | — | ❌ 禁改作（与子集化/WOFF2 冲突） | 排除 |
| 汉典源（zdic） | 口径不一（CC0 vs CC BY-NC-ND 2.5） | — | ⚠️ | 不作干净上游 |

### 15.1 落地产物：`shuowen-seal-kaiyuan`

- **上游**：[frankslin/kaiyuan-small-seal-font](https://github.com/frankslin/kaiyuan-small-seal-font)（OFL-1.1，`Copyright (c) 2026 Kaiyuan Small Seal Font Contributors`；仓库自述**尚未发行字体**）。
- **字形来源**：公版《說文解字》清刻十五卷（Wikimedia Commons `NLC892` 扫描件）逐字切字描摹，上游为每个字形记录页/栏/坐标出处。
- **本项目所做改动**：读取 10,980 个 `glyphs/u3Dxxx.svg`（统一 viewBox `0 -880 1000 1000`，单 `<path>`），`fontTools.svgLib.path.parse_path` → 三次曲线 CFF → cu2qu 转二次曲线 `glyf`；每个篆形只建 1 个字形（10,934 个），其余今字共享；family 改为 `Glyph Atlas Shuowen Seal`（上游未声明保留字体名），nameID 13 保留 OFL 声明。
- **映射链**：UCD `SealSources.txt` 的 `kSEAL_MCJK`（篆码位→今字，Unicode-3.0） + OpenCC `SealCharacters.txt`（篆→今，Apache-2.0） + `SealVariants.txt`（今→隸定字） + `STCharacters.txt`（简→繁） + 上游 `data/compat_prefer.txt`（优先写法）。
- **规模**：TTF **23,193,832 B**，字形 **10,934**，cmap **13,709** 个今字；转 WOFF2 **9,936,956 B（42.8%）**。
- **覆盖（逐字穷举）**：GB2312 一级 **2,748/3,755（73.2%）**、二级 1,697/3,008、GBK 9,713/21,003。
- **补缺效果**：与现有 seal 层并集，一级 **2,765** 字（旧层独有 151 字，其中 17 个一级字；新层补约 1,182 个一级字）。
- **与北师大层并集**：一级 **2,879（76.7%）** —— 开元补 806 个北师大没有的一级字，北师大只补 131 个开元没有的。**注意这仍受 PROJECT-GRANT 限制，不能作为开源交付口径。**
- **三层并集（seal + 说文 + 开元）**：一级 **2,880（76.7%）**、二级 1,852（61.6%）、GBK 16,300。
- **质量提示**：上游为扫描描摹、自述尚未逐字人工审核；本项目未做字形修正，只做格式转换与映射。见目录内 `NOTICE.md`。

### 15.2 未落地的可选项（留给决策）

- **yigezi 合并字体**：`seal.woff2` 8,711,700 B，cmap 10,249，一级 **3,046（81.1%）**，`THIRD_PARTY_NOTICES` 明确「开元（OFL）为主体 + 全字库（OGDL）补充」。若采用须同时满足 OFL 与 OGDL：显名「數位發展部，CNS11643 中文標準交換碼全字庫網站，https://www.cns11643.gov.tw」，且字体名不得单独使用 Kaiyuan。**本项目当前选择不背 OGDL 义务，故未落地。**
- **全字库说文解字**：OGDL-Taiwan-1.0，官网 `cns11643.gov.tw` 在本机网络不可达（TLS/502），猫啃镜像 `freefonts/881` 页面标注 OGDL 但下载需登录 → 证据只到授权页，**未取得原文件**，结论「可用但未取得」。

### 15.3 排除清单（含理由）

| 源 | 理由 |
| --- | --- |
| 北师大说文小篆 11,101 / 統一碼說文（librarhyme 2025）/ 華瑞小篆（24,000） | 后两者是北师大字形的派生，**未获北师大授权**；原版授权仅限项目内部 |
| 說文標篆體（宋建華 2008） | 改自段注本，未声明许可 → 默认著作权所有 |
| Seal Hanzi（Richard S. Cook，11,246） | 专有，内嵌 Wenlin |
| 崇羲篆體（11,596） | CC BY-ND 3.0 TW，**禁改作**，与子集化/WOFF2/字体编译冲突 |
| 峄山碑篆体（3,754） | 猫啃「作者声明」自定义授权，已隔离 |
| 汉典（zdic.net）各层 | 官网称 CC0、维基百科称字典部分 CC BY-NC-ND 2.5，**口径不一，不能作干净上游**（现有 seal 层即来源于此，属历史遗留风险） |
| Seal Sans（Ghimist, 11,328） | AGPL-3.0，可再分发但 copyleft + 网络条款，产品侧风险高 → 仅备选 |
| 霞鹜篆书 LxgwSeal | OFL 但仅 75 字，量不足 |
| 方正/汉仪等商业篆书 | 商业授权，不碰 |

### 15.4 建议

1. 开源/可再分发口径：**用 `shuowen-seal-kaiyuan` 替换或并列现有 seal 层**，一级从 42% → 73%，无额外署名义务（仅 OFL + Unicode 数据许可）。
2. 若接受 OGDL 显名义务：换用 yigezi 合并字体可到 81.1%，比自编译多 298 个一级字。
3. 内部使用口径：开元 + 北师大并集一级 76.7%（分层都开就能查全），但**不能**随开源产物分发北师大层。
4. 任何情况下都不要把汉典原始件当 CC0 证据；现有 `fonts/ancient/seal` 的许可依据应标注为「上游宣称 CC0、实际存疑」，或改用开元层作为唯一来源。

### 15.5 复现

`fonts/incoming/shuowen-seal-kaiyuan/` 内四件套即成品；编译脚本与上游 zip 未随仓库分发（体积原因），算法与参数见 `docs/seal-source-report.md`。核验可用 `scripts/verify_fonts.py --check-only`（只读，不写 catalog）。