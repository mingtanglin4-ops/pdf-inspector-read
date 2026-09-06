# PDF Ingestion Behaviour Audit — 设计文档

被测对象是**解析器**，不是模型。它回答一个现有工作都没回答的问题：
一个 agent 把 PDF 喂给模型之前，中间那一层到底做了什么，以及它有没有告诉你。

---

## 1. 定位与边界

| 工作 | 测什么 | 被测对象 | 与本项目的关系 |
|---|---|---|---|
| OmniDocBench (CVPR 2025) | 抽得准不准 | 解析器 | 同被测对象，不同维度。它测保真度，不测沉默 |
| CrackedPDFs (2026-08) | 注入能不能藏住 | 攻击手法 | 上游。它造样本，明说不覆盖 markitdown / docling / marker / LLM vision |
| PhantomLint (2025-08) | 藏了能不能查出来 | 检测器 | 下游。OCR 一致性比对，ICML 3257 篇 FP 0.092% |
| **本项目** | **解析器做了什么，有没有说** | **解析器 + 它的调用契约** | 中间那一层，空的 |

一句话 gap：**攻击有人研究，检测有人研究，"你的流水线实际交给模型的是什么"没人系统量过。**

出发点不是安全，是工程：写 agent 的 PDF 路由时，你必须知道每条路由的沉默行为，否则路由决策没有依据。安全只是这个视角下最有传播力的一个切片。

### 范围

**测**：文字层解析器（含 LLM-oriented 的 markdown 转换器）在边界输入上的三个可观测量。

**不测**（写进文档，避免被问"为什么不做 X"）：

- 攻击手法的新颖性 → CrackedPDFs 已覆盖，直接引用它的手法分类
- 检测器的 SOTA 性能 → PhantomLint 已覆盖，本项目的检测代码只作为矩阵的取证工具
- 抽取准确率 / 版面还原质量 → OmniDocBench 已覆盖
- 端到端 RAG 的下游影响 → 需要另一套实验设计，列为 future work

---

## 2. 五支柱审计

| 支柱 | 状态 | 内容 |
|---|---|---|
| Research Gap | ✅ | 第三观测量"是否告知调用方"，无人测过 |
| Construction Pipeline | ⚠️ 待建 | 双语料：真实语料为主证据 + 控制 fixture 为判别性对照。**这是本项目风险最高的一环，见 §5** |
| Evaluation Framework | ✅ | 三观测量 + 信号通道分类学 + 判别性门槛 |
| Empirical Findings | 🟡 已有雏形 | 预实验 4 类 × 7 解析器已跑通，见 §6 |
| Companion Method | ✅ | **skill 本身就是 companion method**：矩阵产出路由规则，skill 消费它。用 `plugin eval` 的 with/without 双臂检验"照矩阵行事是否有增量" |

把 skill 重新定位成 companion method 是这个项目最重要的一次框架转换。它从"我写了个工具，顺手做了点测量"变成"我做了个测量，并证明照它行事有/没有用"——后者即使结论是负的也成立。

---

## 3. 设计目标

模型基准的难度校准（顶模型 0.1–9%）在这里不适用，被测对象是确定性软件。取而代之的是**判别性**：

| 目标 | 策略 | 硬指标 |
|---|---|---|
| G1 覆盖 | 7+ 解析器 × 7 行为类别，含 LLM-oriented 转换器和视觉路径 | 每个类别至少 5 个解析器 |
| G2 判别性 | 每个行为类别必须**分开**解析器 | `0 < n_occurred < n_parsers`，否则删掉这一类 |
| G3 可复现 | 版本锁定 + 每格一行命令 + fixture hash | 别人 clone 后一条命令重跑出同一张表 |
| G4 时效 | CI 定期重跑，解析器出新版自动比对 | 矩阵带 `generated_at` 和版本快照，diff 可见 |

**G2 是这个项目的保命条款。** 上一次"解析失败模式基准"死在核心假设一次都没触发——那就是判别性为零。这次把它做成代码里的一个 gate（`discriminability()`），不通过的类别在预实验阶段就被打上 `DROP`，不进正式矩阵。

---

## 4. 分类学

```
被测对象           行为类别                        观测量
─────────────      ────────────────────────       ──────────────────────
pdftotext          hidden_text.white_on_white     occurred    发生了吗
pdftotext-layout   hidden_text.render_mode_3      signalled   告诉调用方了吗（+通道）
pdfplumber         hidden_text.off_page           cost        代价变了吗
pypdf              hidden_text.microtext
pymupdf            silent_ocr_escalation
pymupdf4llm        dropped_rotated_content
markitdown         table_column_bleed
docling            multicolumn_interleave
marker             formula_flattening
MinerU
LLM-vision
```

11 × 9 = 99 格，每格三个观测量。

### 信号通道分类学（第二观测量的关键）

"有没有告诉你"必须可操作化，否则是主观判断。定义为：一次正常调用中，调用方能看到的任何东西。

| 等级 | 通道 | 结构化程度 |
|---|---|---|
| S4 | 抛异常 / 返回值带显式字段 | 程序可分支 |
| S3 | `warnings.warn` | 程序可捕获 |
| S2 | `logging` ≥ WARNING | 需配置才可见 |
| S1 | 写 stderr / stdout（含 native 层直写 fd） | 只有人眼可见 |
| S0 | 什么都没有 | 静默 |

**测量必须在 fd 层做，不能只用 `contextlib.redirect_stdout`。** MuPDF 和 Tesseract 都直接写 fd 1，Python 层重定向抓不到——预实验里就漏过一次，见 `bench/_capture.py`。

### 缺失解析器不等于安全

调用失败的格必须从统计里**排除**，绝不能记成 `occurred=False`。否则"这台机器没装 poppler"会变成"pdftotext 不泄漏"——一个把环境缺陷伪装成安全结论的假阴性。`discriminability()` 里已实现这条，并单列 `n_error` 与 `errored_parsers`。也是因此，**发表用的矩阵只认 CI 里那套固定环境产出的那一份**，见 `.github/workflows/matrix.yml`。

---

## 5. 构建流水线

范式取 **Controlled Injection**（CrackedPDFs 那一路）做对照臂，**真实语料**做主臂。两臂分工必须写死，否则会重蹈"自造 fixture 造错还当成发现"的覆辙。

| 阶段 | 输入 | 操作 | 输出 | 质量闸门 |
|---|---|---|---|---|
| 1 主语料采集 | arXiv 已知注入样本、OmniDocBench 公开集、年报/政府扫描件 | 按许可筛选、去重、记录来源 URL 与 hash | 真实文档池 | 许可可商用；每类 ≥30 篇；来源可追溯 |
| 2 对照 fixture | `bench/fixtures.py` | 每技法生成 payload / clean 配对 | 控制集 | payload 与 clean 只差一处；clean 上任何"发生"都是误报 |
| 3 判别性预实验 | 控制集 | 跑 `discriminability()` | keep / DROP 清单 | **不判别的类别当场删掉，不进正式矩阵** |
| 4 正式矩阵 | 主语料 ∩ keep 类别 | 跑全部解析器 × 全部类别 | `results/matrix.json` | 版本锁定；每格附复现命令 |
| 5 人工抽检 | 矩阵随机 10% | 人眼开 PDF 核对 occurred 判定 | 抽检报告 | 判定与人眼一致率 ≥95% |
| 6 CI 固化 | matrix.json | 定期重跑 + diff | 回归报告 | 版本变动导致的行为翻转必须显式记录 |

### 主臂为什么必须是真实语料

自造 fixture 只能证明"这个技法在这个解析器上会发生"，证不了"这事在真实世界里有多普遍"。上一次的教训是：自造样本既可能造不出触发（假阴性），也可能造出人工产物（假阳性，那次"全员失败"的那类就是 fixture 本身写错了）。

规则写死：**自造样本只能出现在对照臂，且必须配 clean twin；任何进正文表格的数字都来自真实语料。**

### 成本测量的方法学（预实验已暴露的坑）

预实验里 pdfplumber 出现 5.46× 的 payload/clean 时间比，这是首次调用的 import 与缓存预热，不是真实开销。正式测量必须：预热一次 → 重复 ≥5 次 → 取中位数 → 报告四分位距。单次计时的比值一律不进表。

---

## 6. 预实验结果（已跑通，真实数据）

环境：Python 3.11.15 / Linux；pdftotext(poppler) 24.02.0、pdfplumber 0.11.9、pypdf 3.17.4、pymupdf 1.28.2、pymupdf4llm 1.28.2、markitdown 0.1.5。控制集 4 技法 × payload/clean 配对，28 格。

| 行为类别 | occurred | signalled | 干净孪生上的误报 | 判别性 |
|---|---|---|---|---|
| `hidden_text.white_on_white` | 6/7 | 1/7 | 0 | keep |
| `hidden_text.render_mode_3` | 6/7 | 1/7 | 0 | keep |
| `hidden_text.microtext_1pt` | 6/7 | 1/7 | 0 | keep |
| `hidden_text.off_page` | 3/7 | 1/7 | 0 | keep |

四类全部判别，零误报。三条可以直接进文章的观察：

1. **唯一不漏的是 pymupdf4llm**，四类全挡。代价见下一条。
2. **唯一"发出信号"的也是 pymupdf4llm，而且信号是错的**：在纯文字层 PDF 上向 fd 1 打印 `=== Document parser messages === / Using Tesseract for OCR processing.`。它宣告了一次并不需要的 OCR，走的是 S1 通道（native 层直写 fd，程序捕获不到）。其余 6 个解析器全程 S0。
3. **`off_page` 把解析器劈成两半**：pdftotext 与 pymupdf 按 MediaBox 裁剪（不漏），pdfplumber / pypdf / markitdown 不裁剪（漏）。这是"完整性 vs 保真度"这对矛盾第一次以可测量的形式出现，且与 PhantomLint 顺带提到的 clipping path 差异是同一族现象。

---

## 7. 四周排期

**第 1 周｜把 7 类行为都做到判别**
现有 4 类隐藏文本已通过。补 `silent_ocr_escalation`（栅格化一份扫描件）、`dropped_rotated_content`（旋转页边戳记）、`table_column_bleed`（右对齐表格）。每类先跑控制集过 G2 门槛，不过就删。产出：keep 清单。

**第 2 周｜主语料**
按 §5 阶段 1 采集，每类 ≥30 篇。这一周只做采集和许可核查，不出结论。产出：`corpus/manifest.json`（来源 URL + hash + 许可 + 分类标签）。

**第 3 周｜正式矩阵 + 补解析器**
接上 docling、marker、MinerU、一条 LLM-vision 路径。跑全矩阵，做 10% 人工抽检，成本测量按 §5 的预热-重复-中位数流程重跑。产出：`results/matrix.json` + 抽检报告。

**第 4 周｜companion 实验与发布**
只在矩阵判定"解析器分歧大"的文档子集上跑 `claude plugin eval --ablation with-without --runs 5`，测 skill 的增量。同时修表格串列 bug，记录修前/修后在真实表格上的赢平输分布。产出：文章 + README 重排 + 一条发布。

排期的硬约束：**第 1 周结束时如果 keep 类别少于 4 个，砍掉这个项目。** 判别性不够就没有矩阵，只有一堆轶事，那时候止损比第 3 周止损便宜得多。

---

## 8. 发布

- 仓库首屏是矩阵和那句 trade-off；skill 降为"矩阵的一个应用"
- 文章标题打"没有一个库告诉你它选了哪一边"，不打隐藏文本
- Related work 一节主动摆清 CrackedPDFs / PhantomLint / OmniDocBench 的分工，明说本项目在 ingestion layer
- `detect_hidden.py` 降级为矩阵的取证工具，并注明 PhantomLint 更严谨
- 保留"这个项目三次推翻了自己"那一节

## 9. 预先写下的失败条件

1. 第 1 周 keep 类别 < 4 → 停
2. 人工抽检一致率 < 95% → occurred 的判定标准有问题，回到 §4 重定义，不带着错的判定往下跑
3. 主语料某类凑不到 30 篇 → 该类降级为"控制集观察"，不进正文表格，且在文章里注明
4. companion 实验 delta 落在 5 次运行的方差以内 → 如实写"skill 在该子集上无增量"，不换指标重跑
