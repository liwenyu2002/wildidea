---
name: wildidea
version: "1.3"
description: "WildIdea V5：用于产品、策略、研究和算法创新发散。按问题类型抽取算法技术、学术机制、人文艺术、产品机制、毛选和随机组词槽位；标准模式默认强制联网搜索和查重，算法/科研类默认强制在线论文粗查，循环到10条通过候选并生成白底米黄的横版自由窗口HTML。算法/科研类使用源域优先、原型编号、去锚点退化、最近邻差异、最强反驳和人工 novelty 标记。"
---

# WildIdea Skill v1.3

This is the active agent skill spec v1.3. Treat the listed Python commands as internal helper scripts that the agent may call for slot sampling, search, and validation; they are not the user-facing product experience.

## Pipeline

固定执行这条流水线：

`输入 -> 类型判断 -> 抽槽位 -> 隔离常规答案 -> 源域/外域机制冻结 -> 映射到用户领域 -> 联网查重过滤 -> 淘汰则重抽 -> 得到10条 -> 启动独立子智能体评映射质量(6维度0-10分，Structural Depth<5淘汰) -> 生成HTML -> 校验HTML -> 返回路径`

标准模式不得只给文字；除非用户明确说“不要 HTML/只要文本”，最终都生成 `outputs/<topic>.html`。
标准模式默认强制联网搜索和查重；算法/科研类默认强制在线论文粗查。

## Core Rules

- 只做三件事：收集陌生来源、找外域锚点、并放用户领域对应物。
- 不提炼用户问题的“本质”；不写“因为/所以/体现了”；不把远域写成比喻或启发。
- 允许写具体操作说明，禁止写推理过程、价值解释和空泛类比说明。
- 最终必须有 10 条通过项。被淘汰或搜索不可判定的候选不得进入最终 10 条。
- 每次淘汰都记录到“本轮淘汰/重抽记录”；超过 8 条只展示关键 8 条和总数。

## Type And Slots

先判断问题类型，再运行脚本。只读取脚本返回的 JSON，不要读取完整领域库。

| 用户问题 | 脚本命令 | 配额 |
|---|---|---|
| 算法/科研/模型/识别/预测/优化/信号/控制 | `python scripts/pick_domain_slots.py --type algorithm` 或 `--type research` | D1算法技术5 + D2学术机制2 + D3人文艺术1 + 毛选1 + 随机组词1 |
| 产品/策略/增长/商业/功能/体验/运营 | `python scripts/pick_domain_slots.py --type product` 或 `--type strategy` | D1算法技术1 + D2学术机制3 + D3人文艺术2 + D4产品机制2 + 毛选1 + 随机组词1 |

重抽命令（统一走主脚本，单一入口）：
- 毛选：`python scripts/pick_domain_slots.py --reroll mao`
- 随机组词：`python scripts/pick_domain_slots.py --reroll random_word`
- 单个远域槽位：`python scripts/pick_domain_slots.py --reroll D1`（或 D2/D3/D4）

防重抽：重抽远域槽位时带 `--exclude <锚点id>`，跳过本轮已用或已淘汰的锚点。锚点 id 是输出 JSON 里每条的 `id` 字段（如 `D3-07`，稳定不变）。
例：`python scripts/pick_domain_slots.py --reroll D1 --exclude D1-03 D1-11`
整轮抽取也支持 `--exclude`，把上一轮来源的 id 排除掉。

随机组词的设计目的是**最大化随机**，不要求组合有意义。流程：从 `references/common-chinese-chars.txt` 随机抽两个字 → 联网搜索该词（按 `references/search-integration.md` 的搜索工具兜底链：`scripts/search_helper.py` → 询问用户可用搜索工具 → 兜底直接联想） → 拿搜索结果的第一条 → 从中提取一种方法论、机制、规则或边界 → 映射到用户领域。词越无意义，搜索结果越不可预期，这正是随机组词的价值。不要因为组合"看起来没意义"就重抽。

## Candidate Contract

每条候选必须同时满足：

- **如果锚点有 `methods` 字段（本地方法库）**：优先参考 `methods[].input` / `methods[].process` / `methods[].output` 来理解源域机制的结构，参考 `methods[].key_insight` 来抓住核心洞察，参考 `transfer_examples` 来理解该机制已经被成功迁移到哪些领域。但不要照搬迁移案例——你的任务是迁移到用户领域，不是重复已有迁移。`methods[].paper` / `methods[].code` 可用于联网查重时的搜索关键词。
- 外域锚点有数字、时间、事件、物理量、阈值或明确边界。
- 外域锚点是一条操作、规则、约束或真实事件，不是抽象品质判断。
- 用户领域对应物是具体产品、技术、功能、流程、组织机制或实验设置。
- 对应物至少包含一个可指认专有名词，例如具体分子、技术、框架、设备、算法、产品或公司名。
- 去掉远域机制后，如果只剩行业常识、普通组合或命名差异，则淘汰。
- **可执行性门槛**：候选描述必须让读者能在脑中形成实施画面。写清楚：用什么数据/材料、按什么顺序做什么、什么条件触发、触发后改变什么。禁止只写"可以用来做X"而不说明怎么做。如果一个候选去掉专有名词后只剩"做X来解决Y"的句式，说明描述不够具体，需要补充机制细节。
- **映射结构深度**：全部 10 条候选生成完毕后，由**独立子智能体**逐条评分（0-10 分），不得由生成者自评，不得在生成流程中顺带评分。独立子智能体有独立的上下文窗口，看不到生成过程、源域锚点列表和 SKILL.md 规则，只收到以下输入：
  - 用户问题
  - 源域名称
  - 目标域名称
  - 对象映射（源域中的 X → 目标域中的 Y）
  - 共享关系（源域中 X 和 Y 的关系 → 目标域中对应物的关系）
  - 评分维度（0-10）：
    - **Structural Depth**：对象映射是否定义清晰且有洞察力。0=模糊浅层映射；10=深刻结构性对应
    - **Domain Distance**：源域和目标域的距离。0=同领域；10=完全不同领域
    - **Applicability**：映射是否能有效转移知识解决问题。0=无帮助或误导；10=变革性洞察
    - **Novelty**：映射的原创性。0=常见映射；10=开创性洞察
    - **Unexpectedness**：映射的反直觉程度。0=显而易见的连接；10=需要重大概念跳跃
    - **Non-Obviousness**：领域专家做出此连接的可能性。0=领域内标准类比；10=需要跨领域知识综合
  - 判官 prompt：`You are an expert judge evaluating the quality of an analogy proposed to solve a scientific problem. Problem Statement: {problem} Problem Domain: {source_domain} Analogous Domain: {target_domain} Object Mappings: {object_mappings} Shared Relations: {shared_relations} Score this analogy on 6 dimensions using a 0-10 scale. Structural Depth (0-10): How well-defined and meaningful are the object mappings? 0=Vague or superficial mappings with little explanatory power; 10=Exceptional mappings with deep insight into structural correspondence. Domain Distance (0-10): How far apart are the problem domain and analogous domain? 0=Same or closely related domains; 10=Highly disparate domains with no obvious overlap. Applicability (0-10): How well does this analogy enable knowledge transfer to solve the problem? 0=Analogy doesn't help or is misleading; 10=Transformative insight that directly enables solution. Novelty (0-10): How original and insightful is this analogy? 0=Very common or obvious analogy; 10=Groundbreaking insight, highly innovative. Unexpectedness (0-10): How counter-intuitive or surprising is this analogy? 0=Obvious connection; 10=Highly surprising connection requiring significant conceptual leap. Non-Obviousness (0-10): How unlikely is it that a domain expert would make this connection? 0=Standard analogy in the field; 10=Requires knowledge synthesis across disparate fields. Return ONLY valid JSON.`
  - Structural Depth 低于阈值的候选必须重做映射或淘汰。最终 10 条的平均 Structural Depth 应达到平均阈值。
  - **判官模型选择**（按优先级）：
    1. `anthropic/claude-sonnet-4.5`（论文原版，temp=0）— 首选，max_tokens=800。淘汰阈值 SD<6，平均阈值 SD≥6
    2. `deepseek/deepseek-v4-pro`（免费/低成本）— 降级方案，max_tokens 必须设为 2000。评分比 Claude 宽松约 0.5-1.0 分（实测 SD 平均 8.22 vs Claude 7.8），淘汰阈值 SD<7，平均阈值 SD≥7
    3. 任意其他推理模型 — max_tokens ≥ 2000，淘汰阈值和平均阈值需比 Claude 上调 1 分
    4. 当前正在运行 WildIdea 的同一个模型 — 最后手段，必须注明"判官=生成模型，评分可能 inflation"
  - **JSON 解析容错**：推理模型输出的 JSON 可能被 reasoning token 截断或嵌套过深。解析时：先尝试提取 markdown 代码块内的 JSON；失败则用括号计数法提取第一个完整 JSON 对象；再失败则重试一次（max_tokens 再加 500）。

算法/科研类还必须读 `references/mechanism-transfer.md`，并保留这些字段：源域机制原文、源域原型/外域抽象结果、用户领域怎么干、改变环节、去锚点退化物、最近邻同/异/风险、最强反驳、最小可证伪实验、三项评分、验证状态。

“用户领域怎么干”必须通俗具体：写拿什么数据、按什么顺序做什么、什么条件触发、触发后改变什么。不要写变量名清单。

## Verification States

标准模式查重状态只允许前两档；第三档只用于用户明确要求“快速/草稿/不要联网”的非标准模式。

| 状态 | 使用条件 | 写法 |
|---|---|---|
| 联网粗查已启用 | 标准模式默认；产品/策略查产品、功能、专利、竞品；算法/科研查论文、代码、benchmark、专利 | `联网粗查已启用；文献级 novelty audit 待人工验证` |
| 文献集严格查重已启用 | 用户提供 BibTeX、DOI、Zotero、标题摘要 CSV、PDF 文件夹或明确本地文献集 | `文献集严格查重已启用；记录最近邻命中依据` |
| 用户要求跳过查重 | 仅限快速/草稿/不要联网，不得标为标准模式 | `快速草稿；联网查重未启用` |

联网/论文/市场验证规则：
- 产品发布、功能公布、专利、论文、品牌案例直接同名或同机制命中 -> 淘汰。
- 论坛讨论、理论文章、无关结果、不构成实现 -> 可保留。
- 搜索失败或无法判断 -> 不进入最终 10 条，除非用户切换到快速/速览模式。
- 不得把“未检索到同名方法”写成“查重通过”；最多写“未发现同名，机制级仍待人工审查”。

## Output Contract

标准文字输出：

```markdown
## 隔离区
V0: ...
V1: ...

## 外域锚点 -> 对应物
| 来源 | 外域锚点 | 源域原型/外域抽象结果 | 对应物 | 验证 | 映射质量评分(6维度) | 维度 |
|---|---|---|---|---|---|
| ...共10条 | ... | ... | ... | ... | ... |

淘汰/重抽记录：...
统计：最终通过10条；累计重抽淘汰N条；搜索不可判定0条；查重状态：联网粗查已启用/文献集严格查重已启用；槽位配额已满足；平均映射质量：Structural Depth X.X/10, Domain Distance X.X/10, Novelty X.X/10。
```

算法/科研类可使用机制候选表，但表里仍然优先保证“用户领域怎么干”可读，不为整齐压缩成黑话。

## HTML Pipeline

生成 HTML 时：

1. 读取 `references/poster-guide.md` 和 `templates/poster.html`。
2. 写入 `outputs/<topic>.html`；无法命名时用 `wildidea-YYYYMMDD-HHMM.html`。
3. 卡片只放：远域类别、具体来源机制、源域原型/外域抽象结果、候选名、用户领域怎么干、失败条件、映射质量评分（Structural Depth / Domain Distance / Novelty）。
4. 隔离区后必须放“本轮淘汰/重抽”。
5. 运行校验：`python scripts/validate_poster.py outputs/<topic>.html --forbid-proto-term <用户领域术语...>`。
   - **`--forbid-proto-term` 是必填项**：不传直接 FAIL。从用户输入里抽取任务名、数据类型、对象、指标、常规方法名作为禁词。禁词尽量覆盖中英文双语（例如 EEG 任务传 `EEG 脑电 被试 域适应 准确率`），脚本会自动做 NFKC + 大小写归一，并展开中英文同义词（如 `agent` ↔ `智能体`、`drift` ↔ `漂移`），堵住跨语言/大小写绕过。
   - 校验脚本还会检查：`.proto` 与 `.desc` 的相似度——若 `.proto` 大体上是 `.desc` 删掉禁词后的洗白版，标记为"疑似马后炮"（先写领域方案再删词填入 proto），这是去锚点纪律的结构性检测。
   - 校验脚本除此之外还查：占位符、卡片数、`.source` 不能是槽位名、`.slot` 必须带 D1–D6、卡片不得残留模板样例文字、文字溢出防护。
   - 精简/极端/一杀模式卡片不足 10 张时加 `--cards N`。
6. **（标准模式必须）生成搜索证据 sidecar**：按 `references/search-integration.md` 的格式，为每条最终候选写搜索记录，输出为 `outputs/<topic>.search.json`。然后运行：`python scripts/validate_poster.py outputs/<topic>.html --forbid-proto-term <禁词> --search-sidecar outputs/<topic>.search.json`。校验脚本会检查：每条候选至少有一条搜索记录、status 合法、decision 与 status 自洽、标准模式不允许 `needs_manual_check` 候选进入最终列表。
7. 最终答复给出本地路径和 `file:///` 地址。

## Iteration

用户说“迭代/重跑/再野一点/把产出一起 ban 掉”时：

- 把上一轮对应物加入 V1，并标为 Concept-ban、Mechanism-ban、Module-ban 或 Soft-ban。
- 重跑槽位注入，不复用上一轮来源、种子和主对应物。
- Soft-ban 可作为组件复用，但不得作为主创新再次输出。

## Optional Modes

| 触发词 | 模式 |
|---|---|
| 快速/速览 | 只出 1-2 条，不做完整验证 |
| 压缩/锚点格式 | 见 `references/output-innovation-recipes.md` |
| 画像/角色 | 按工程师、设计、管理、研究者改口径 |
| 精简/宁少勿多 | 正常抽样后只保留最强 <=3 条 |
| 极端/一条/一杀 | 只输出 1 条，带最小启动成本和止损线 |
| 重新生成 HTML/竖版/截图 | 见 `references/poster-guide.md` |

## References

- `references/mechanism-transfer.md`：算法/科研类源域优先和退化审查。
- `references/search-integration.md`：联网搜索口径。
- `references/poster-guide.md`：横版自由窗口 HTML 生成和校验标准。
- `references/poster-palettes.md`：白底米黄配色约束。
- `references/output-innovation-recipes.md`：可选压缩输出。
