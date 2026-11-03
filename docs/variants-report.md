# 简繁 / 异体字符等价类数据（variants.json）构建报告

构建日期：2026-11-03（Asia/Shanghai）　生成器：`scripts/build_variants.py`（Python 3 标准库，零第三方依赖）

| 交付物 | 路径 | 体积 |
| --- | --- | --- |
| 构建脚本 | `scripts/build_variants.py` | 34,390 B（888 行） |
| 前端数据 | `data/variants.json` | 870,440 B；**gzip -9: 186,001 B**（压缩率 −78.6%，远低于 1.5 MB 预算） |
| 本报告 | `docs/variants-report.md` | — |
| 上游缓存 | `.cache/`（Unihan.zip、OpenCC 4 个词典，未污染 `data/`） | 9.5 MB |

产物是**纯静态 JSON**，前端运行时零依赖、零网络请求：直接 `fetch('data/variants.json')` 即可。

---

## 1. 数据来源与许可

| 来源 | 文件 / 字段 | 许可 | 缓存体积 | sha256（前 16 位） |
| --- | --- | --- | --- | --- |
| Unicode Unihan（UCD latest，**Unicode 18.0.0**，文件日期 2026-07-31） | `Unihan.zip` → `Unihan_Variants.txt`（kSimplifiedVariant / kTraditionalVariant / kSemanticVariant / kZVariant / kSpecializedSemanticVariant）、`Unihan_IRGSources.txt`（kTotalStrokes，按需读 zip，不落盘） | [Unicode Terms of Use](https://www.unicode.org/terms_of_use.html) | 8,340,649 B（`Unihan_Variants.txt` 726,700 B） | `4c93ea9c1f636451…` |
| OpenCC `STCharacters.txt`（简→繁） | 4,012 条，276 条为多候选 | Apache-2.0 | 36,026 B | `a0ca1601c70648cf…` |
| OpenCC `TSCharacters.txt`（繁→简） | 4,148 条，997 条为多候选 | Apache-2.0 | 104,520 B | `9ff46a7d30e57653…` |
| OpenCC `STPhrases.txt` | 49,309 行，**仅缓存/统计，未入图** | Apache-2.0 | 1,008,747 B | `24d23700f4f3d186…` |
| OpenCC `TSPhrases.txt` | 505 行，**仅缓存/统计，未入图** | Apache-2.0 | 9,177 B | `1b1e60a3d50492bc…` |

- 全部缓存于 `glyph-atlas/.cache/`，脚本按 sha256 校验存在性；`--refresh` 才重新下载。
- 只使用 **Unicode 官方数据 + OpenCC**，未引入任何商业字库数据。分发时建议在工具“关于”页保留一行署名：
  「字形归一化数据派生自 Unicode Unihan Database（Unicode ToU）与 OpenCC（Apache-2.0）」。
- **台湾教育部《异体字字典》未纳入**：官网 <https://dict.variants.moe.edu.tw/> 是 JSP 查询界面，未找到稳定的机器可读批量直链；网上流传的“原盘/转储”来源与许可不明，按任务约定跳过。若后续拿到官方授权数据，只需在 `SOURCES` 增加一项并在 `build_relations()` 里接一条新边类型。

## 2. 方法

### 2.1 两类边

| 类型 | 来源 | 处理 |
| --- | --- | --- |
| **强边** | Unihan `kSimplifiedVariant`（简化形 → 本体）、`kTraditionalVariant`（本体 → 繁体，取 S=本体）、OpenCC `STCharacters`、`TSCharacters` | 经守护判定后**并入并查集**，形成等价类 |
| **弱边** | Unihan `kSemanticVariant`（`sem`）、`kZVariant`（`z`）、`kSpecializedSemanticVariant`（`ssem`） | **不合并**，只写进 `related` 作为“候选相关字” |

Unihan 值形如 `U+8AAA<kMatthews`，解析时剥掉 `<` 之后的注记只留码位；码位再转字符。
`src` 字段把每个字符命中的来源串成有序逗号列表（`st,ts,unihan_simp,unihan_trad,z,sem,ssem`）。

### 2.2 防过度合并：逐“简体侧”节点守护

对每个简体侧字符 S 及其伙伴集合 P，按下列顺序判定（命中即阻断，**该节点所有强边整体转入 related**）：

- **A. 多语素判据**：把 P 投到“变体证据图”（仅 kZVariant / kSemanticVariant / kSpecializedSemanticVariant，节点限于 P）上，若连通分量 > 1，说明若干繁体形彼此并无变体关系，S 是“一简对多繁”枢纽 → 阻断。
- **B. 同字例外**：若 {S}∪P 在该图上全连通（Unihan 明确记载它们是同一字的字形变体）→ 放行（宝/寶、为/為/爲、说/說/説、峰/峯、真/眞、万/萬 都靠这条通过）。
- **C. 传世字自指**：S 出现在 `STCharacters` 且候选里包含 S 自己（说明 S 本身是传世正字，如 后、里、云、余、台、干、面、制、折、卷、松、斗、叶…）→ 阻断。
- **D. 兜底**：S 不在 ST、但在 Big5 编码范围内、且 `kTraditionalVariant` 自指 → 阻断。

被阻断的强边不丢弃：**以最高优先级写入 `related`（双向）**，因此“一简对多繁”的字仍然能被前端找到，只是分层展示、不共用一个规范键。`related` 每字上限 16 条（本次实际最大 7 条，无截断）。

> 刻意**不使用** `kJapaneseOldVariant` / `kJapaneseNewVariant` 作“同字证据”：Unihan 记载 `余 kJapaneseOldVariant 餘`，若采信会让 余/餘 被错误合并（首版实测即因此 FAIL）。这两个字段只保留在脚本里做诊断参考。

### 2.3 规范代表字（canonical key）

排序键 `(GB2312 层级, 是否简体, 笔画数, 码位)`：GB2312 一级字（3,755 个）> 二级字 > 仅 GBK > 其他；同级优先“简体证据”字（作为他人 `kSimplifiedVariant` 目标或在 ST 词典里），再取笔画少（Unihan `kTotalStrokes` 首值），最后按码位稳定排序。

### 2.4 输出结构

```jsonc
{
  "meta": { "built": "...", "schema": "glyph-atlas/variants@1", "unihan_version": "Unicode Version 18.0.0",
            "sources": [ { "name": ..., "url": ..., "license": ..., "sha256": ..., "bytes": ... } ],
            "count": { ... }, "policy": { ... }, "stats": { ... } },
  "canon":   { "說": "说", "説": "说", "寶": "宝" },     // 任意成员 → 规范键
  "same":    { "说": ["說", "説"], "宝": ["寶"] },        // 规范键 → 同类的其他成员
  "related": { "干": ["乾", "幹", "榦", "𬺭"], "后": ["後"] }, // 弱关联（双向）
  "src":     { "說": "st,unihan_trad", ... }             // 溯源标记
}
```

- 键与值**一律用字符本身**，不用 `U+XXXX`；需要码位时 JS 侧用 `ch.codePointAt(0)`（注意 5,855 个非 BMP 字符是代理对）。
- 规范键自己不出现在 `same` 的值里；`same` 只列其他成员。
- 未出现在 `canon` 里的字（无变体记录，或所有边都被阻断）按 `canon.get(ch) ?? ch` 回落为自身。
- 没有 `same`/`related` 记录的字即“无变体”，前端无需特殊处理。

前端取用建议：

```js
const c = data.canon[ch] ?? ch;              // 规范键
const glyphs = [c, ...(data.same[c] ?? [])]; // 同类：同一字的不同字形
const hints  = data.related[ch] ?? [];       // 相关：一简对多繁 / 语义近邻，二级展示
```

## 3. 统计（本次构建实测）

| 指标 | 数值 |
| --- | --- |
| 等价类总数 | **6,760**（全部为 ≥2 成员的多字类） |
| 进入等价类的字符 | **13,644** |
| `canon` / `same` 条目 | 13,644 / 6,760 |
| 强边候选 / 实际合并 / 被阻断 | 7,234 / 6,885 / **349** |
| 弱边（相关对） | 2,450 |
| `related` 字符数 / 对数 | 3,812 / 4,824（双向计） |
| `src` 覆盖字符 | 16,492（= 数据中出现的全部不同字符） |
| 等价类规模分布 | 2 人：6,657；3 人：82；4 人：21（最大类 4 个成员） |
| 守护阻断理由 | `self-ref-st` 116、`multi-morpheme` 105（合计 221 个简体节点，涉 349 条边） |
| GB2312（6,763 字）覆盖率 | 有等价类 2,290（33.9%）；在数据中任意出现（含 related）**3,414（50.5%）**；related-only 1,124 |
| 非 BMP 字符 | 5,855（Ext-B 及以后，前端字体需覆盖） |
| 数据体积 | 870,440 B；**gzip 186,001 B** |

来源标记分布（按字符计）：`unihan_simp` 13,699、`unihan_trad` 13,699、`ts` 8,164、`st` 8,066、`sem` 3,563、`ssem` 525、`z` 159。

最大的几个等价类（人工目检过全部 103 个 ≥3 成员类）：

`历/厤/曆/歷`、`仑/侖/崙/𪨧`、`奖/奨/奬/獎`、`岁/嵗/歲/𡻕`、`线/綫/線/缐`、`鉴/鑑/鑒/𰾫`、`针/針/鍼/𰾗`、`钩/鈎/鉤/𰽭`、`说/說/説`、`为/為/爲`、`启/啓/啟`、`叹/嘆/歎`、`鸡/雞/鷄`、`钻/鉆/鑽/𰿆`。

## 4. 自检（18/18 PASS）

测试逻辑内置在 `scripts/build_variants.py` 里（因交付路径只允许三个文件，不另建测试脚本），命令：

```bash
python3 scripts/build_variants.py --selftest --selftest-md .cache/selftest.md
```

验收口径：
- **“同类”用例**：所有字落在同一等价类，且类成员数 ≥ 用例字数。
- **“不合并”用例**（一简对多繁）：① 组内任意两字**不在同一等价类**；② 首选字的 `related` **列出该组全部伙伴**；③ 双向可发现（每个伙伴的 `related` 也回指首选字）。

| 用例 | 期望 | 实际 | 结果 |
| --- | --- | --- | --- |
| 说/說/説 同类 | 同类（说 → 說/説（繁简+异体）） | `same=說説说` | **PASS** |
| 宝/寶 同类 | 同类（宝 → 寶） | `same=宝寶` | **PASS** |
| 为/為/爲 同类 | 同类（为 → 為/爲（爲 为 Unihan 正体）） | `same=为為爲` | **PASS** |
| 峰/峯 同类 | 同类（异体字同键） | `same=峯峰` | **PASS** |
| 真/眞 同类 | 同类（异体字同键） | `same=眞真` | **PASS** |
| 万/萬 同类 | 同类（常规简化回归） | `same=万萬` | **PASS** |
| 东/東 同类 | 同类（常规简化回归） | `same=东東` | **PASS** |
| 头/頭 同类 | 同类（常规简化回归） | `same=头頭` | **PASS** |
| 无/無 同类 | 同类（常规简化回归） | `same=无無` | **PASS** |
| 后/後 不合并 | 不合并（一简对多繁：后(皇后) ≠ 後） | `related=后->後; 後->后` | **PASS** |
| 余/餘 不合并 | 不合并（余(我) ≠ 餘(剩余)） | `related=余->餘予; 餘->余` | **PASS** |
| 云/雲 不合并 | 不合并（云(说) ≠ 雲(云彩)） | `related=云->雲; 雲->云` | **PASS** |
| 里/裡/裏 不合并 | 不合并（里(乡里) ≠ 裡/裏(里面)） | `related=里->哩裏裡; 裡->里裏; 裏->里裡` | **PASS** |
| 干/乾/幹/榦 不合并 | 不合并（干(干戈) ≠ 乾/幹/榦） | `related=干->乾幹榦𬺭; 乾->干乹亁; 幹->干𬺭; 榦->干` | **PASS** |
| 发/發/髮 不合并 | 不合并（发(发生) ≠ 髮(头发)） | `related=发->發髮; 發->发; 髮->发` | **PASS** |
| 台/臺/檯/颱 不合并 | 不合并（台(台子) ≠ 臺/檯/颱） | `related=台->檯臺颱; 臺->台; 檯->台儓枱; 颱->台` | **PASS** |
| 只/隻 不合并 | 不合并（只(只有) ≠ 隻(一只)） | `related=只->戠祇衹隻子; 隻->只` | **PASS** |
| 系/係/繫 不合并 | 不合并（系(系统) ≠ 係/繫） | `related=系->係繫; 係->系; 繫->系` | **PASS** |

任务里点名的 8 个关键 case 全部得到正确结果：`说→說/説`、`宝→寶`、`为→為/爲`、`里`/`裡`/`裏` 不合并、`云`/`雲` 不合并、`余`/`餘` 不合并、`后`/`後` 不合并、`干`/`乾`/`幹` 不合并（均进 `related`）。

另有 6 项结构性自检（脚本 `--selftest` 之外的一次性校验，均 0 错误）：`canon` 幂等且闭合于 `same` 键、`same` 无自指/重复、`related` 不含同类成员且无重复、`src` 标记只含白名单、键均为单字符。

## 5. 已知缺口与已知问题

1. **一简对异体但未合并（`伪` 类）**：`伪 / 偽 / 僞` 三字各占一个键，只在 `related` 里互通。原因是 Unihan 没有记录 偽–僞 之间的变体关系，守护判据 A 把它们当成两个不同语素而阻断。同类还有 `缊/緼/縕`、`蕴/藴/蘊`、`辒/輼/轀`、`酝/醖/醞`。对查询功能无损（related 仍能命中），但规范键不统一；若拿到台湾教育部数据可解。
2. **传世字被保守阻断**：`叶/葉`（OpenCC ST 记录 叶 为叶韵 xié 的自指）、`广/廣`、`云/雲` 等落 `related` 而非 `same`。对古籍标注是有意为之（叶韵 ≠ 树叶），但普通用户搜“叶”时繁体字形只出现在二级列表。若产品希望“常用简化优先”，可把判据 C 的 ST 自指改成“ST 自指且该字在 GB2312 中另有独立字义”再人工白名单。
3. **Unihan 语义链接造成的合并（与“严格 related-only”口径有出入）**：`历/厤/曆/歷`、`饥/飢/饑`、`于/於`、`仇/讎/雠`、`坏/坯/壞` 被合成一个类。原因是 Unihan `kSemanticVariant` 把几个繁体形互相链成一个连通块（历/饥 属真正的一简对多繁）。这对“字形查询”通常更友好（搜“历”一次看到 歷+曆），但若下游需要严格区分语素，应在展示层把 `same` 再按 `src` 是否含 `z` 拆分。
4. **`related` 含语义噪声**：如 `只→戠/子`、`里→哩`（OpenCC ST 里→哩）、`面→麪/麫/麵`、`干→𬺭`。这些是 SEM 字段与 OpenCC 多候选的原生噪声，只作“候选相关字”，不应被当作等价。
5. **未做词组级消歧**：`STPhrases/TSPhrases`（49,309 + 505 行）已缓存但未入图。若要处理“干（干戈）/ 幹（干部）”这类词内消歧，需要词语级索引，属下一步工作。
6. **非 BMP 字符占 35%**（5,855 字）：多为 Ext-B～H 的异体字。前端做 `String` 索引时必须用 `codePointAt`/`Array.from`；字体子集需确认覆盖，否则这些字的字形查询会落到缺字。
7. **覆盖率口径**：GB2312 只有 33.9% 的字有等价类，其余 4,473 字在 Unihan/OpenCC 里没有变体记录（多为独体、专名、近代化学用字），属数据面天然稀疏，不是 bug。
8. **守护是启发式**：A/B/C/D 四条判据基于 Unihan/OpenCC 自身关系，个别字仍可能误判；`--diagnostics .cache/guard.tsv` 会导出 7,038 行 MERGE/BLOCK 明细（含理由、码位、ST 自指标记），便于人工复核和后续加白/黑名单。

## 6. 复跑

```bash
cd glyph-atlas
python3 scripts/build_variants.py                      # 用 .cache 缓存重建 data/variants.json
python3 scripts/build_variants.py --refresh            # 强制重新下载上游
python3 scripts/build_variants.py --selftest --selftest-md .cache/selftest.md
python3 scripts/build_variants.py --diagnostics .cache/guard.tsv
python3 scripts/build_variants.py --pretty --out .cache/variants.pretty.json   # 调试用缩进版
```

脚本无第三方依赖、幂等（除 `meta.built` 时间戳外同一上游输入产出相同内容），下载失败会重试 3 次并落 sha256；上游更新后重跑即可，无需改代码（Unihan 版本号会自动写进 `meta.unihan_version`）。