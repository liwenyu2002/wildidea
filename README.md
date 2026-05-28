# WildIdea V5

WildIdea 是一个用于产品、策略、研究和算法创新发散的 Codex skill。

它的核心目标不是让模型先理解问题、再找跨域类比，而是先抽取外部领域里的具体机制，再把这些机制并放到用户领域里的具体对象上。这样可以减少“大路货答案”和“先想好答案再包装”的问题。

## 核心机制

运行路径：

```text
输入 -> 判断问题类型 -> 按槽位抽远域钉子 -> 找用户领域对应物 -> 过滤 -> 重抽 -> 输出10条通过项 -> 生成16:9横版HTML
```

WildIdea 只做三件事：

- 收集陌生来源。
- 找外域锚点。
- 并放用户领域对应物。

它明确禁止：

- 先提炼用户问题的“本质”。
- 把远域降级成比喻或启发。
- 在外域锚点和用户领域对应物之间写空泛推导。

## 问题类型与配额

标准模式输出 10 条候选，并默认生成一个 16:9 横版 HTML 海报。

| 问题类型 | 槽位配额 |
|----------|----------|
| 算法/科研类 | D1 算法技术 5 条 + D2 学术机制 2 条 + D3 人文艺术 1 条 + 毛选 1 条 + 随机组词 1 条 |
| 产品/策略类 | D1 算法技术 1 条 + D2 学术机制 3 条 + D3 人文艺术 2 条 + D4 产品机制 2 条 + 毛选 1 条 + 随机组词 1 条 |

## 目录结构

```text
wildidea/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── references/
│   ├── common-chinese-chars.txt
│   ├── mechanism-transfer.md
│   ├── output-innovation-recipes.md
│   ├── poster-guide.md
│   ├── poster-palettes.md
│   └── search-integration.md
├── scripts/
│   ├── pick_domain_slots.py
│   ├── pick_seed.py
│   └── search_char.py
└── templates/
    ├── output-example.md
    └── poster.html
```

说明：

- `SKILL.md` 是主流程。
- `scripts/pick_domain_slots.py` 内置领域库，按问题类型随机抽取 10 个槽位，避免每次调用把完整领域库塞进上下文。
- `references/mechanism-transfer.md` 用于算法/科研类问题，包含源域优先、去锚点退化、最近邻审查、最强反驳等规则。
- `references/poster-guide.md` 和 `templates/poster.html` 用于生成 16:9 白底米黄 HTML 海报。
- `outputs/` 是本地生成物目录，已在 `.gitignore` 中忽略，不作为 skill 内容提交。

## 脚本用法

抽取算法/科研类槽位：

```bash
python scripts/pick_domain_slots.py --type algorithm
```

抽取产品/策略类槽位：

```bash
python scripts/pick_domain_slots.py --type product
```

单独重抽毛选种子：

```bash
python scripts/pick_seed.py
```

单独重抽随机组词：

```bash
python scripts/search_char.py
```

## 默认 HTML 输出

每次标准模式都会生成横版 HTML，用户不需要额外说“生成 HTML”。只有用户明确说“不要 HTML/只要文本”时才跳过。生成时使用：

- `templates/poster.html`
- `references/poster-guide.md`
- `references/poster-palettes.md`

默认风格是 16:9 横版、白底米黄、Claude 式低对比卡片，写入 `outputs/<topic>-16x9.html`。卡片结构固定包含：

- 远域类别
- 具体来源机制
- 候选机制名
- 用户领域怎么干（通俗展开）
- 失败条件

## 验证

提交前可运行：

```bash
python -X utf8 C:\Users\admin\.codex\skills\.system\skill-creator\scripts\quick_validate.py C:\ALL\wildidea
```

期望输出：

```text
Skill is valid!
```

## License

MIT
