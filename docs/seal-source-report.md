# 說文小篆字形源调研报告（第三轮，2026-11-03）

> 目标：为 `fonts/ancient/seal/`（CC0 描摹层，GB2312 一级仅 **1,583/3,755 = 42.1%**，缺 `二`/`川`/`口` 等基本字）寻找**许可可再分发、且覆盖率明显更高**的第二个《說文解字》小篆字形源。
> 口径：只接受 CC0 / 公有领域 / CC BY / 政府开放数据 / 明确可再分发；禁再分发、禁改作、仅限学习、保留所有权利、需注册付费的一律排除。
> 结果：**2 个可用源（1 个已落地、1 个按决策不落地）+ 1 个「许可可用但未能取得」**；其余全部有明确排除理由。

---

## 1. 结论摘要

| # | 源 | 许可 | GB2312 一级 | 可再分发 | 本轮结论 |
|---|---|---|---|---|---|
| 1 | **开元小篆 Kaiyuan Small Seal Font** | **OFL-1.1** | **2,748（73.2%）** | ✅ | ✅ **已落地** `fonts/incoming/shuowen-seal-kaiyuan/` |
| 2 | **yigezi 合并字体**（开元 + 全字库） | OFL-1.1 + OGDL-Taiwan-1.0 | **3,046（81.1%）** | ✅（须显名全字库） | ⚪ **可用，但按 lead 决策本轮不落地、不下载**（见 §5） |
| 3 | **全字库《說文解字》** | **OGDL-Taiwan-1.0**（政府开放数据） | 6,721 字形（未实测） | ✅（须显名） | ⚪ **许可可用，但未取得原文件**（官网不可达、镜像需登录） |
| — | 北师大说文（已在 `fonts/ancient/beishida/`） | PROJECT-GRANT（项目组授权） | 2,783（74.1%） | ❌ 禁商用/禁再分发 | 仅内部使用，不进开源层 |

**一句话**：开源可再分发口径下，小篆一级覆盖可从 **42.1% 提到 73.2%（单源）**；若接受全字库 OGDL 显名义务可到 **81.1%**；内部口径叠加北师大可到 **91.2%**。

---

## 2. 源 1：开元小篆（已落地）

### 2.1 基本信息

| 项 | 值 |
|---|---|
| 仓库 | https://github.com/frankslin/kaiyuan-small-seal-font |
| 许可原文 | 仓库根目录 `OFL.txt`，全文复制到 `fonts/incoming/shuowen-seal-kaiyuan/LICENSE.txt`（5,312 B） |
| 版权行 | `Copyright (c) 2026 Kaiyuan Small Seal Font Contributors` |
| 保留字体名 | 未声明 Reserved Font Name（`OFL.txt` 中无 RFN 字段） |
| 字形来源 | 公版《說文解字》清刻十五卷（Wikimedia Commons `NLC892` 扫描件）逐字切字描摹；上游对每字形记录页/栏/坐标（`data/provenance/`） |
| 上游状态 | 仓库 README 明确「尚未发行字型」；无 release 二进制，只有 SVG 轮廓与脚本 |
| 覆盖范围 | Unicode 18.0 小篆区块 U+3D000–U+3FC3F，共 11,328 码位；仓库内实际有 **10,980 个** `glyphs/u3Dxxx.svg` |
| 第三方数据 | `third_party/unicode/ucd/SealSources.txt` 采用 **Unicode License v3**（`THIRD_PARTY_UNICODE_LICENSE.txt` 已复制进交付目录） |

### 2.2 本项目做了什么（属 OFL 允许的修改版/衍生版）

1. 读取 10,980 个 `glyphs/u3Dxxx.svg`（统一 `viewBox="0 -880 1000 1000"`，单 `<path d=...>`；`data-source` 属性带刻本出处）。
2. `fontTools.svgLib.path.parse_path` → 三次曲线，`cu2qu` 转二次曲线，生成 `glyf` 表（TTF）。
3. 用 UCD `SealSources.txt` 的 `kSEAL_MCJK` 建「篆书码位 → 今字」；再以 OpenCC `SealCharacters.txt`（篆→今）、`SealVariants.txt`（今→隸定字）、`STCharacters.txt`（简→繁）补桥接；`data/compat_prefer.txt` 指定优先写法。
4. 每个篆形只建 1 个字形（**10,934** 个，46 个 SVG 未映射到今字），cmap 让 **13,709** 个今字共享同一篆形。
5. family 改为 `Glyph Atlas Shuowen Seal`，PS 名 `GlyphAtlasShuowenSeal-Regular`（上游未声明保留名，改名目的为不冒充原作者发布物）；nameID 13 保留 OFL 声明。

### 2.3 交付物与数字

- 目录：`fonts/incoming/shuowen-seal-kaiyuan/`
  - `shuowen-seal-kaiyuan.ttf` — **23,193,832 B**，sha256 `201d213ab0c5e3c2b0a14d4502c4c8b47b488bb0ca92906d66d39f57240c7c28`
  - `LICENSE.txt`（上游 OFL 原文，未截断）
  - `NOTICE.md`（来源、改动、许可、覆盖率、质量提示）
  - `license.json`（结构化条款 + 哈希 + 覆盖统计）
  - `THIRD_PARTY_UNICODE_LICENSE.txt`（Unicode-3.0 原文）
- 团队已把它迁到 `fonts/modern/shuowen-seal-kaiyuan/{original.ttf, subset.ttf, ...}` 接成独立图层（subset 16,566,528 B）。
- 覆盖率（逐字穷举）：**GB2312 一级 2,748/3,755（73.2%）**、二级 1,697/3,008、GBK 9,713/21,003。
- 体积：TTF 23,193,832 B → WOFF2 **9,936,956 B（42.8%）**；CFF/OTF 版 WOFF2 要 11,840,132 B，故交付 glyf/TTF。
- 与现有层的关系：`fonts/ancient/seal` 是它的**子集之外**还有 151 个独有字（其中一级字 17 个，如 圖/亖/堇/境）；并集一级 **2,765**。

### 2.4 质量提示（必须如实标注）

- 上游字形为**扫描描摹**，项目自述「尚未完成逐字人工审核」，部分字可能存在笔画粘连/比例偏差。
- 本项目仅做格式转换与映射，**未做任何字形修正**。
- 若用于正式出版级排版，建议先做一次逐字抽检（按 `data/provenance/` 回查原刻本页）。

---

## 3. 源 2：yigezi 合并字体（可用，本轮不落地）

| 项 | 值 |
|---|---|
| 文件 | `seal.woff2`，8,711,700 B；cmap 10,249；字形名表仅 `Shuowen Seal`（无许可字段） |
| 许可构成 | 上游 `THIRD_PARTY_NOTICES`：**开元小篆（OFL-1.1，主体）+ 全字库《說文解字》（OGDL-Taiwan-1.0，补充）**；并明确声明**不使用**汉典（授权口径不一）、小學堂（数据许可待定） |
| 覆盖 | 一级 **3,046/3,755（81.1%）**、二级 1,837、GBK 10,249 |
| OFL 义务 | 可再分发/可修改/可商用；须附 OFL 全文，字体名不得单独用 `Kaiyuan` |
| OGDL 义务 | 须显名：**「數位發展部，CNS11643 中文標準交換碼全字庫網站，https://www.cns11643.gov.tw」**；衍生字体同样要保留该声明 |
| 本轮决策 | **不落地、不下载**（lead 2026-11-03 决定）：收益是 73.2%→81.1%（一级 +298 字），代价是额外一份 OGDL 协议全文 + 每个分发物件都要带台湾政府机关显名，属于锦上添花，不解决缺口主因 |

**如果后续要做**：需在 `fonts/incoming/<id>/` 同时放 OFL 全文 + OGDL 全文 + 两段显名，并在产品版权页同时展示；字体 family 不能用 `Kaiyuan` 单独命名。

---

## 4. 源 3：全字库《說文解字》（许可可用，未取得）

| 项 | 值 |
|---|---|
| 官方站 | https://www.cns11643.gov.tw （全字庫） |
| 许可 | **OGDL-Taiwan-1.0（政府資料開放授權條款－第1版）**：允许商用、修改、再分发，须显名「數位發展部，CNS11643 中文標準交換碼全字庫網站」 |
| 规模 | 6,721 字形（据公开资料；未实测） |
| 取得情况 | 官网在本机网络**不可达**（curl schannel TLS 失败、Python `UNEXPECTED_EOF`、HTTP 502 均复现）；猫啃镜像 `www.maoken.com/freefonts/881` 页面标注 OGDL 但下载需登录 → **未取得原文件** |
| 结论 | **许可可用，证据仅到授权页，未能取得 → 记为「可用但未取得」**，不列为已落地源 |

> 备注：yigezi 的 81.1% 正是「开元 + 全字库」合并的结果；若将来能拿到全字库原始文件，可以自己做同样的合并，而不依赖第三方合并包。

---

## 5. 排除清单（每款一句理由 + 许可出处）

| 源 | 号称许可 | 排除理由 | 许可/证据出处 |
|---|---|---|---|
| 北师大说文小篆（11,101 字）/ `BeiShiDaShuoWenXiaoZhuan-1.ttf` | 未声明（name 表无 0/13/14） | 原版授权不明；项目组仅给「本项目使用」的书面授权，**禁商用、禁再分发**，不能进开源层 | name 表无字段；`fonts/license-texts/PROJECT-GRANT.txt` |
| 統一碼說文小篆（librarhyme, 2025） | 未声明 | 是北师大字形的派生，**未获北师大授权** | 维基百科「已知的小篆字体」页 + 项目页自述 |
| 華瑞小篆體（Freemdict, 2026, 24,000 字） | 未声明 | 同上，改自北师大、未获授权 | 同上 |
| 說文標篆體（宋建華, 2008） | 未声明 | 改自段注本，未说明许可 → 默认著作权所有 | 同上 |
| Seal Hanzi（Richard S. Cook, 11,246 字） | 专有 | 专有字体，内嵌 Wenlin 数据 | 项目页授权说明 |
| 崇羲篆體（小學堂, 11,596 字） | **CC BY-ND 3.0 TW** | **禁改作**：与子集化、WOFF2 转换、字体编译全部冲突 | 授权页明示「姓名標示-禁止改作」 |
| 峄山碑篆体（3,754 字） | 猫啃「作者声明」 | 自定义条款、无 SPDX、不可随文件举证；项目已隔离 | 猫啃字体页作者声明；`fonts/quarantine/yishan-beizhuan/` |
| Seal Sans（Ghimist, 11,328 字） | **AGPL-3.0** | 可再分发，但 copyleft + 网络条款，产品侧合规成本高 | 仓库 LICENSE |
| 霞鹜篆书 LxgwSeal | OFL-1.1 | 许可干净但**仅 75 字**，量不足 | `fonts/modern/lxgwseal/` |
| 汉典（zdic.net）各层 | 官网称 CC0 | **授权口径不一**（维基百科称字典部分 CC BY-NC-ND 2.5），不能作干净上游；现有 `fonts/ancient/seal` 即来源此，属历史遗留风险 | 汉典站内声明 + 维基百科许可说明 |
| 方正/汉仪/文鼎等商业篆书 | 商业授权 | 不在白名单，只列名录不落地 | 见 `docs/font-sourcing.md` §8 |
| 全字库说文（§4） | OGDL-1.0 | 许可可用，但**未取得文件**（非排除，单列） | 见 §4 |

---

## 6. 覆盖率对照（逐字穷举，GB2312 一级 3,755 字）

| 组合 | 一级覆盖 | 备注 |
|---|---|---|
| 现有 `fonts/ancient/seal` | 1,583（42.1%） | CC0 描摹层，缺基本字 |
| **开元小篆（新）** | **2,748（73.2%）** | OFL，单源，可再分发 |
| 现有 + 开元（并集） | 2,765 | 旧层独有 151 字（含 17 个一级字） |
| 北师大（PROJECT-GRANT） | 2,783（74.1%） | 仅内部使用 |
| 北师大 + 开元 | **3,426（91.2%）** | 内部口径；开元补 643 个北师大没有的一级字 |
| yigezi 合并（OFL+OGDL） | 3,046（81.1%） | 开源口径的天花板 |
| yigezi + 北师大 | 3,556 | 内部口径上限 |
| 四层全并（含旧层） | 3,558（94.8%） | 剩余 197 个一级字无篆形数据 |

---

## 7. 复现方法

1. 取上游：`https://codeload.github.com/frankslin/kaiyuan-small-seal-font/zip/refs/heads/main`（42,306,715 B）。
2. 解包后确认 `glyphs/u*.svg` 10,980 个、`viewBox` 全为 `0 -880 1000 1000`。
3. 映射：`third_party/unicode/ucd/SealSources.txt`（`kSEAL_MCJK`）+ OpenCC 三表（`SealCharacters.txt` / `SealVariants.txt` / `STCharacters.txt`）+ `data/compat_prefer.txt`。
4. 轮廓：`parse_path` → `T2CharStringPen(1000)` + `TransformPen((1,0,0,-1,0,120))`（viewBox 的 y 轴翻转 + 基线下移 120）→ CFF；再 `Cu2QuPen(1.0, reverse_direction=True)` → `TTGlyphPen` → `glyf`。
5. FontBuilder：`unitsPerEm=1000`、`ascent=880`、`descent=120`、宽 1000；name 表写 OFL 声明，family 用新名。
6. 校验：`python scripts/verify_fonts.py --check-only`（**只读**，不写 `data/font-catalog.json`；如需落盘只写 `data/font-verify.json`）。

> 编译脚本未随仓库分发（体积与一次性原因）；按上面 4–5 步可在 10 分钟内重建同款字体。

---

## 8. 建议

1. **开源/可再分发口径**：以 `shuowen-seal-kaiyuan` 作为小篆主层或与现有 CC0 层并集（一级 73.2% / 并集 73.6%），无额外署名义务（OFL + Unicode 数据许可）。
2. **内部口径**：开元 + 北师大并集 91.2%，但北师大层不得随开源产物分发，页面需单独标「項目組授權」。
3. **若将来接受 OGDL 显名**：再评估 yigezi 合并（81.1%）或自取全字库原文自行合并。
4. 无论采用哪种组合，**都不要**再把汉典原始件当作 CC0 证据；现有 CC0 层的许可依据应标注为「上游宣称 CC0、实际存疑」。