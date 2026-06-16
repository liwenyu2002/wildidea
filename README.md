# WildIdea Skill

WildIdea 是一个独立的 Codex Skill，用于生成跨领域创新思路。

WildIdea is a standalone Codex skill for generating cross-domain innovation ideas.

它不会从用户问题本身的惯性框架出发，而是先抽取一个距离很远的源领域机制，将其作为“他山之石”冻结下来，再抽象出可迁移的方法论，最后映射回用户的产品、策略、研究、算法或设计问题。

It does not start from the user's existing problem frame. It first draws a distant-domain source mechanism, freezes it as "他山之石", abstracts the transferable method, then maps that method back to the user's product, strategy, research, algorithm, or design problem.

## 版本 / Version

- Skill: 1.3

## 安装 / Install

下载或克隆本仓库，然后把独立 Skill 文件夹复制到你的 Codex skills 目录：

Download or clone this repository, then copy the standalone skill folder into your Codex skills directory:

```bash
mkdir -p ~/.codex/skills
cp -R skill/wildidea ~/.codex/skills/wildidea
```

重新打开一个 Codex 对话，然后这样使用：

Start a new Codex chat and ask:

```text
Use $wildidea to generate cross-domain ideas for ...
```

## 包含内容 / What Is Included

- `skill/wildidea/SKILL.md`: Skill 入口 / skill entrypoint
- `skill/wildidea/references/wildidea-skill.md`: 完整工作流规则 / full workflow spec
- `skill/wildidea/references/domains.json`: 卡池数据 / card pool
- `skill/wildidea/scripts/search_helper.py`: 免 API key 联网搜索 helper / zero-key web search helper
- `skill/wildidea/scripts/pick_domain_slots.py`: 卡池抽取脚本 / slot sampler
- `skill/wildidea/templates/poster.html`: 可选海报模板 / optional poster template

如果你想使用带联网搜索能力的版本，直接下载 `skill/wildidea/` 即可，不需要部署其他服务。

Users who want the networking/search version can download `skill/wildidea/` directly and use it without deploying anything else.

## 核心流程 / Core Flow

1. 输入问题，并写下需要避开的常见解法。<br>
   Input the problem and common solutions to avoid.
2. 从卡池中抽取远领域源机制。<br>
   Draw distant source mechanisms from the card pool.
3. 识别具体源现象。<br>
   Identify the source phenomenon.
4. 抽象出不含目标领域术语的可迁移方法。<br>
   Abstract a transferable method without target-domain terms.
5. 将方法映射回用户问题。<br>
   Map the method back to the user's problem.
6. 过滤或重抽弱候选。<br>
   Filter or reroll weak ideas.
7. 返回具体的灵感卡片。<br>
   Return concrete idea cards.

## 项目结构 / Project Layout

```text
skill/wildidea/           独立可下载 Codex Skill / standalone downloadable Codex skill
SKILL.md                  根目录 Skill 入口镜像 / root mirror of the skill entrypoint
docs/wildidea-skill.md    完整 Skill 规则镜像 / root copy of the full skill workflow spec
```

## 本地校验 / Local Validation

```bash
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py skill/wildidea
```

## 许可 / License

MIT
