# WildIdea 统一红蓝工作流

本文件是唯一 `wildidea` Skill 的深度执行规范。红蓝对抗不是可选扩展，也不是另一个 Skill；标准运行中，每张最终可见卡都必须留下可审计的红蓝档案。

## 目标

把跨域类比从“生成者自由联想并自报结构”改成一组相互隔离、可计算、可攻击的中间产物：

`问题图 + 源机制图 -> 结构对齐 -> 候选卡 -> 独立评分 -> 证据红队 -> 蓝队存活/修复 -> 可证伪推论 -> 查重 -> 批次多样性`

重点不是增加代理数量，而是让每一步都能被后续角色检查和推翻。

## 角色与隔离

### 1. Problem Structurer

只读用户问题，输出：

```json
{
  "actor": "",
  "constraint": "",
  "bottleneck_relation": "",
  "desired_change": "",
  "trade_off": ""
}
```

五项只描述问题，不得出现方案、机制名或常规解法。

### 2. Target Structurer

只读问题与 `problem_card`，输出目标关系图：

```json
{
  "domain": "target",
  "nodes": [{"id": "t1", "label": "", "type": "state|threshold|process|resource|actor|outcome"}],
  "edges": [{"id": "f1", "from": "t1", "to": "t2", "relation": "", "condition": ""}],
  "higher_order": [{"id": "h1", "edges": ["f1", "f2"], "shared_relation": ""}]
}
```

只描述问题结构，不提出解法。

### 3. Base Structurer

只读抽中的源锚点。物理隔离目标问题、`problem_card`、目标图和常规答案，输出同结构的 `base` 图。

源图不得包含目标领域词。若角色拿到了目标问题，视为隔离失败，必须重跑。

### 4. Aligner

读取两张图，按关系类型、拓扑位置和高阶关系进行 SME 风格对齐。输出：

```json
{
  "node_pairs": [{"base": "n1", "target": "t3", "why": ""}],
  "edge_pairs": [{"base": "e2", "target": "f2", "covered_by": "h1"}],
  "notes": ""
}
```

对齐质量由图计算或独立审查，不接受模型自报：

- `coverage`：被有效映射的目标节点/边比例。
- `systematicity_score`：映射边中，被源图高阶关系共同覆盖的比例。
- `structural_consistency`：一个节点不能同时映射到多个互相冲突的角色。

对齐不足时，可再运行一轮 aligner 补缺口；不要让卡片写作者自由补关系。

### 5. Card Writer

只从已接受的结构对齐写卡。`relation_pairs` 必须直接对应映射边；`proto` 必须来自源图关系且不含目标词；`desc` 必须落到 `problem_card` 的一个主攻键。

### 6. Independent Judge

使用与生成者隔离的上下文，评分：

- Structural Depth
- Domain Distance
- Applicability
- Novelty
- Unexpectedness
- Non-Obviousness

Structural Depth 必须显式检查系统性。边界卡可进行三次同判官采样取中位数，或启用结构、可行性和目标领域审稿人组成的视角委员会。

## 红队

### Structural Killer

用同一组映射推出一个与 `desc` 矛盾的目标结论，或指出映射必然预测但现实不成立的关系。

只有给出具体反向映射或反例，才可 `killed=true`。

### Naked Test

删除卡片标题、源领域名、隐喻和类比措辞，再看剩余方案：

- 若只剩目标行业常识、普通平台/推荐/加权/阈值方案，判为致命退化。
- 若仍保留由源机制带来的特定动作链、约束和失败边界，记录为存活证据。

### Staleness Detective

联网寻找目标领域内已经存在的同机制实现。必须提供可访问的论文、代码、专利、产品或公开案例证据。只命中源方法本身，不算目标领域撞车。

### Kill 纪律

- `kill = kill`，不得用平均分覆盖致命证据。
- Kill 必须携带 `counter_mapping`、`stripped_text`、`citations` 或 `direct_implementation` 至少一项。
- 没有证据的强烈怀疑记为 `major weakness`，不能直接淘汰。

## 蓝队

蓝队不负责无条件辩护，而是记录卡片为什么仍成立，或把红队证据转成修复输入。

```json
{
  "survived": [
    {"attack": "", "reason": "为什么没有被该攻击杀死", "evidence": ""}
  ],
  "weaknesses": [
    {"objection": "", "severity": "minor|major|fatal", "mitigation": ""}
  ],
  "fatal": null,
  "judge_dims": {
    "strongest": {"dimension": "", "score": 0, "explanation": ""},
    "weakest": {"dimension": "", "score": 0, "explanation": ""}
  }
}
```

若卡片在生成循环中未触发红队，最终定稿前仍要补做一次红队，以形成完整档案。

## 修复闭环

三次尝试固定为：

1. `fresh`：从当前对齐写卡。
2. `repair`：注入具体质量规则、判官维度或红队证据，只重写被点名字段。
3. `reangle`：若同类失败重复，保持源锚点，重新选择源图中的另一段因果链并重跑对齐。

红队证据不得压缩成“提高可行性”之类空话。应原样保留关键反例、撞车文献或裸测退化文本。

## 候选推论与验证

对通过卡，寻找源图中“与已映射边相连但尚未迁移”的边，生成最多两个目标领域预测。预测必须可验证，随后归类：

- `confirmed`
- `contradicted`
- `untested_falsifiable`
- `untestable`

`untested_falsifiable` 是优先交给 auto-research 的状态。`untestable` 不得包装成研究假设。

## 多样性

使用卡片核心机制文本构造相似度矩阵并计算 Vendi Score。通过 leave-one-out 变化定位最冗余卡。若无法计算真实 Vendi Score，使用语义等价类聚类并明确标记为降级。

还要单独检查输出形式坍缩：机制不同但全部变成 App、平台、仪表盘或推送，也属于同质化。

本质方向不足约 6 个时，从新源领域重抽最冗余卡；替代卡仍需完整走对齐、判官和红蓝流程。

## 可审计状态

仓库 Harness 可将中间状态写入：

```text
outputs/harness/<run_id>/state/
  problem_card.json
  target_field_brief.json
  target_graph.json
  run_manifest.json
  slot_NN/
    anchor.json
    base_graph.json
    mapping.json
    card.json
    attempts.json
    judge.json
    grounding.json
    novelty.json
    redteam.json
    adversarial.json
  batch/
    vendi.json
    diversity.json
```

在纯 Agent Skill 环境中，不强制完全相同的目录，但必须保留等价的信息，不能只交付最终卡而丢失红蓝结论。

## 预算与降级

代理调用预算是软上限。预算不足时，优先保留：源/目标隔离建图、对齐、卡片写作、独立判官和每卡红蓝档案。目标领域简报、候选推论等附加阶段可以降级，但必须披露。

任何下列缺失都不能静默称为标准结果：

- 无法隔离子代理上下文；
- 无法真实联网搜索；
- 无法运行独立判官；
- 无法为每张最终卡形成红蓝档案；
- 无法校验 HTML/search sidecar。
