---
name: wildidea
version: "1.3"
description: "WildIdea v1.3：按网页 v1.4 的 9 槽位、预设卡池、逐卡独立评分、最多重抽 2 次和未达标保底逻辑执行；标准 Skill 额外强制真实联网审查、独立判官与 HTML 校验。"
---

# WildIdea Skill v1.3 Full Spec

这是 Agent Skill 的完整执行规范。脚本只用于内部抽卡、搜索记录与产物校验，不要把 CLI 当成用户体验。

## Standard Pipeline

固定执行：

`输入问题与常见解法 -> 类型判断 -> 结构化为 problem_card（五键） -> 按模式抽 9 个槽位 -> 隔离常规答案 -> 逐槽冻结他山之石 -> 抽象无目标域词的方法 -> 映射为落地方案（对照 problem_card） -> 基础校验 -> 独立判官（同时核对 problem_card 对应关系） -> 未达标则重抽（最多 2 次） -> 真实联网审查 -> 形成通过/未达标保底/失败结果 -> 生成并校验 HTML -> problem_card 五键覆盖盘点 -> 返回路径`

五条纪律：

1. 必须先抽来源，再写方案；不能先写常规答案，再给它套一个外域名字。
2. 9 个槽位彼此独立。某张卡完成后可以立即报告，不必等待其余卡；最终 HTML 在全部槽位结束后生成。
3. 每个槽位最多 3 次生成，即初次生成加最多 2 次重抽。不得无限重抽直至凑齐 9 张通过卡。
4. 高亮卡或全局排序只能在全部槽位结束后计算。
5. `problem_card` 只结构化问题本身，不产出解法；每张卡的映射与独立判官都要对照它，`desc` 须声明本卡主攻 `problem_card` 的哪一键；9 张卡全部完成后按五键盘点覆盖面，没有任何卡命中的键必须在最终交付中披露。

## Mode Gate

默认进入标准模式。用户说“用 WildIdea”“帮我想方向”“给我方案”等仍是标准模式。

只有用户明确要求 `快速`、`速览`、`草稿`、`只要文本`、`不要 HTML`、`不要联网`、`别生成文件`、`先别查重` 时，才可进入非标准模式。非标准输出必须声明实际跳过了哪些步骤。

标准模式完成条件：

- 每个最终可见候选都有真实搜索证据，且没有 `needs_manual_check` 冒充通过；
- 每个候选都由独立子智能体或独立评价器完成评分：结构映射卡 6 维，`RANDOM_WORD` 卡改用独立的 4 维评分（见 Random Word 一节）；
- 已生成 HTML 与搜索 sidecar；
- 已使用 `validate_poster.py` 带禁词、sidecar 和实际卡片数校验通过；
- 最终回复给出本地路径和 `file:///` 地址。

任何要求不可用时，不得静默降级。

## Problem Card

在抽槽位之前，先把用户问题重述为 `problem_card`：五个字符串键 `actor`（受困的行动者）、`constraint`（当前限制其行动的约束）、`bottleneck_relation`（卡住的关键关系）、`desired_change`（期望达成的改变）、`trade_off`（必须在其间取舍的两难）。

- `problem_card` 只结构化问题本身，不写任何机制名、目标域常规解法或方案；这一步与 `mechanism-transfer.md` 里“源域锁定阶段禁止看目标域”并不冲突——详见该文件“目标域侧的对称要求”一节。
- 每张卡的映射步骤与独立判官都要对照 `problem_card`，而不是只对照原始问题文本。
- 每张卡的 `desc` 开头须声明本卡主攻 `problem_card` 的哪一键。
- 9 个槽位全部完成后，按五键盘点覆盖面：统计哪些键至少被一张卡命中，哪些键没有任何卡命中；未覆盖的键必须写进最终交付，不能略过不提。

## Web v1.4 Parity

以下生成逻辑必须与网页保持一致：

- 默认 9 个槽位；用户没有指定时不要生成 10 张。
- 一张卡独立经历 `生成 -> 基础校验 -> 独立评分 -> 完成/重抽`。
- 质量门槛分两档，由 `risk_profile` 选择，默认 `pragmatic`：
  - `pragmatic`（默认）：`Structural Depth >= 判官模型校准线`、`Novelty >= 7`、`Applicability >= 9`。
  - `explore`（用户要求“更野”“探索模式”时切换）：`Structural Depth >= 判官模型校准线`、`Novelty >= 7`、`Applicability >= 7`，且 `Domain Distance >= 7` 或 `Unexpectedness >= 8` 至少满足一项。
  - 最终交付必须披露实际使用的档位（`pragmatic` 或 `explore`）。
- 当前模型校准基线：Claude Sonnet 系列 SD 至少 6；DeepSeek v4 系列 SD 至少 8；DeepSeek R1 系列 SD 至少 9（已知评分偏高，不建议作为判官模型，如用户坚持使用须先提醒）；其他模型优先使用已有校准值，没有校准记录时按网页代码默认线 `SD >= 6` 执行并披露。
- 某次候选未过门槛时，记录 6 维评分与四项均分，然后重抽同一槽位，排除本轮已用来源。
- 三次都未过分数门槛时，从有效候选中选择 `(SD + DD + NV + AP) / 4` 最高者，标记为 `未达标保底`，不得写成“通过”。
- 直接重复已有实现、来源不真实、字段损坏或无法判断的候选不能作为保底。
- 若一个槽位三次都没有可用候选，保留该槽位的失败状态，不得用无关内容补位。
- 网页对未达标保底/失败卡退款；本地 Skill 没有积分账本，只保留状态语义，不声称已退款。

## Type And Slots

先判断问题类型，再运行抽卡脚本。只读取抽样 JSON。

| 类型 | 命令 | 默认 9 卡配额 |
|---|---|---|
| algorithm | `python3 scripts/pick_domain_slots.py --type algorithm` | D1 x4, D2 x2, D3 x1, D6/毛选 x1, D7/随机组词 x1 |
| research | `python3 scripts/pick_domain_slots.py --type research` | D1 x3, D2 x2, D3 x1, D5 x1, D6 x1, D7 x1 |
| product | `python3 scripts/pick_domain_slots.py --type product` | D1 x1, D2 x2, D3 x1, D4 x2, D5 x1, D6 x1, D7 x1 |
| strategy | `python3 scripts/pick_domain_slots.py --type strategy` | D1 x1, D2 x2, D3 x1, D4 x1, D5 x2, D6 x1, D7 x1 |

槽位含义：

- `D1` 算法技术
- `D2` 学术机制
- `D3` 人文艺术
- `D4` 产品机制
- `D5` 社会政策
- `MAO`，卡面显示 `D6 毛选`
- `RANDOM_WORD`，卡面显示 `D7 随机组词`

D 数字表示顶层卡池，旁边的领域文字表示该来源的具体学科。相同 D 数字不得被解释成不同顶层卡池。

### Pool Modes

使用网站同款预设：

| 模式 | 命令 | 分布 |
|---|---|---|
| 默认分布 | 不传或 `--pool-mode default` | 按上表的问题类型配额 |
| 纯社会政策 | `--pool-mode social_policy` | D5 x9 |
| 纯算法 | `--pool-mode algorithm` | D1 x9 |
| 纯产品 | `--pool-mode product` | D4 x9 |

默认排除已标记为“已完成一次跨域映射的成品案例”的锚点条目：这类条目已经是别人包装好的现成类比，直接复用会形成双跳类比。仅当用户明确要求更野时，加 `--include-completed-analogies` 纳入，并在交付中披露已启用。

重抽统一调用：

```bash
python3 scripts/pick_domain_slots.py --reroll D1 --exclude D1-03 D1-11
python3 scripts/pick_domain_slots.py --reroll D5 --exclude D5-02
python3 scripts/pick_domain_slots.py --reroll mao --exclude MAO-07
python3 scripts/pick_domain_slots.py --reroll random_word --exclude 已用词
```

重抽必须尽量排除本轮已用或已淘汰的锚点。

## Source-First Contract

每张卡先形成这条链：

`具体源现象 -> 抽象方法 -> 目标域对象映射 -> 落地动作链`

字段要求：

- `source_phenomenon`：他山之石。写“谁/什么在什么情境下做了什么，产生什么结果或约束”，以中文为主，不得只是论文标题或术语名。
- `source`：机制中文名；必要时写中文名加英文缩写，如 `随机采样一致性（RANSAC）`。
- `proto`：抽象方法。不得出现用户问题、目标产品、目标数据或目标领域词。
- `desc`：落地方案。开头先声明本卡主攻 `problem_card` 五键中的哪一键，再用 2-4 个短句写清输入/材料、动作顺序、触发条件、改变结果以及可观察输出。
- `advantage`：以 `这种方案的优势在于，` 开头，尽量不超过 50 个中文字符，用人话说明价值。
- `fail`：具体失败前提，作为详情或内部元数据保留；紧凑卡面可隐藏。

如果锚点有 `source_scene`，优先把它作为他山之石。若有 `methods`，用 `input/process/output/key_insight` 理解结构，但不要照搬 `transfer_examples`。

算法/学术卡的主要卡面仍显示源现象；环境支持悬停详情时，同时补充通俗实际场景。

## Candidate Validation

基础校验必须在判官前完成：

- 标题短且可复述；
- 他山之石是具体事实，不是抽象品质；
- 抽象方法没有目标域词；
- 落地方案至少有两句和明确动作链；
- 产品题包含可见用户流程；
- 算法题包含输入数据、模型/特征步骤、输出和验证信号；
- 研究题包含变量、测量、对照或验证条件；
- 策略题包含行动者、激励/约束变化和可观察指标；
- 去掉外域机制后若只剩行业常识，淘汰；
- 不依赖品牌专名来制造具体感，除非用户明确要求竞品方案。

## Independent Judge And Retry

标准模式中，生成者不能自评。独立判官只接收用户问题、`problem_card`、源域、目标域、对象映射、共享关系与候选文本，不接收生成过程；除了给 6 维打分，还要核对候选是否真的命中它 `desc` 声明主攻的那个 `problem_card` 键。

评分维度为 0-10（`RANDOM_WORD` 卡不适用本节六维评分，改用 Random Word 一节的 4 维评分）：

- Structural Depth
- Domain Distance
- Applicability
- Novelty
- Unexpectedness
- Non-Obviousness

每槽执行：

1. 生成并做基础校验；失败则消耗本次尝试。
2. 独立判官评分，同时核对 `problem_card` 对应关系。
3. 达到质量门槛（见 Web v1.4 Parity 的 `pragmatic`/`explore` 两档）后，再做联网审查。
4. 联网确认直接同机制实现时，本次淘汰；搜索无法判断时，标准模式不得将其标为通过。
5. 未过分数门槛的有效候选保留在该槽位的保底候选集中。
6. 最多三次；三次结束后按四项均分选择可搜索确认的最高保底，否则该槽位失败。

## Random Word

随机组词的目标是引入不可预测来源，但不得让模型随意换源：

1. 保留脚本抽到的原词。
2. 用 Agent 真实联网搜索该词。
3. 从真实结果中提取操作、规则、事件或边界。
4. 再抽象和映射。

没有可靠搜索落点时重抽或失败，不能凭空改成河流侵蚀、免疫系统等无关机制。

随机组词卡不适用六维结构映射评分（Structural Depth/Domain Distance/Applicability/Novelty/Unexpectedness/Non-Obviousness）。改用独立判官模板 `src/wildidea/prompts/judge_random_word.txt`，评 4 维（0-10）：

- `chain_clarity`：链路清晰度
- `actionability`：可执行性
- `novelty`：新颖度
- `unexpectedness`：意外度

通过线：`chain_clarity >= 6` 且 `actionability >= 6` 且 `novelty >= 7`（初始未校准值，待实际打分分布出来后再调整，此处先如实注明）。

## Search Audit

Skill 标准模式保留网页之外的增强审查：

- 产品/策略：查产品功能、竞品、专利和公开案例。
- 算法/研究：查论文、代码、基准、数据集和专利。
- 每个最终候选至少一条真实搜索记录。
- “未发现同名”只能写成粗查结论，不能宣称绝对原创。
- 产品、论文、代码或专利出现同机制实现时淘汰。
- 搜索失败或无法判断时，不得作为标准通过卡。

按 `references/search-integration.md` 写 `outputs/<topic>.search.json`。

## Output Contract

最终保留 9 个槽位结果及其状态：

```text
01 通过
02 重抽 1 次后通过
03 未达标保底
04 失败
...
```

主卡面优先显示：问题、标题、D 槽位与具体领域、他山之石、抽象方法、落地方案、优势。6 维评分、失败边界、搜索证据和重抽详情可放详情区或 sidecar，不要挤占主卡面的可读性。

结果统计至少报告：通过数、未达标保底数、失败数、累计重抽数、搜索状态、通过卡的 SD/DD/NV/AP 均值、本轮使用的质量门槛档位（`pragmatic`/`explore`），以及 `problem_card` 五键覆盖盘点（哪些键无任何卡命中）。

## HTML Pipeline

1. 读取 `references/poster-guide.md` 和 `templates/poster.html`。
2. 写入 `outputs/<topic>.html`。
3. 写入 `outputs/<topic>.search.json`。
4. 从用户输入和常见解法中提取中英文禁词。
5. 9 张可渲染卡时运行：

```bash
python3 scripts/validate_poster.py outputs/<topic>.html \
  --cards 9 \
  --forbid-proto-term <目标域禁词...> \
  --search-sidecar outputs/<topic>.search.json
```

6. 若有完全失败槽位导致可渲染卡少于 9 张，`--cards` 传实际渲染数，并在最终回复明确缺失槽位，不能伪造补齐。
7. 最终回复给出本地绝对路径和 `file:///` 地址。

## Algorithm And Research Additions

算法/科研题还要读 `references/mechanism-transfer.md`，内部保留源域原型、对象映射、共享关系、去锚点退化物、最近邻差异、最强反驳、最小可证伪实验与验证状态。

主卡面的落地方案仍然必须通俗：写拿什么数据，先后做什么，何时触发，最后用什么指标验证，不要只列变量名。

## Iteration

用户要求“迭代”“再野一点”或把上一轮产出也排除时：

- 将上一轮对应物加入禁用区；
- 不复用上一轮来源 ID 和主对应物；
- 仍按 9 个原始槽位、每槽最多 3 次执行；
- Soft-ban 可作为组件，但不能再次成为主创新。

## Optional Modes

| 触发词 | 行为 |
|---|---|
| 快速/速览/草稿 | 输出 1-2 条或用户指定数量，并声明未完成的标准步骤 |
| 精简/宁少勿多 | 正常抽样后只展示最强不超过 3 条，内部仍保留筛选事实 |
| 极端/一条/一杀 | 只展示 1 条，附最小启动成本和止损线 |
| 画像/角色 | 按工程师、设计、管理或研究者调整表达 |

## References

- `references/mechanism-transfer.md`
- `references/search-integration.md`
- `references/poster-guide.md`
- `references/poster-palettes.md`
- `references/output-innovation-recipes.md`
