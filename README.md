# WildIdea Skill

<a href="./README_EN.md"><kbd>English Version</kbd></a>

WildIdea 是一个独立的 Codex Skill，用于生成跨领域创新思路。

它不会从用户问题本身的惯性框架出发，而是先抽取一个距离很远的源领域机制，将其作为“他山之石”冻结下来，再抽象出可迁移的方法论，最后映射回用户的产品、策略、研究、算法或设计问题。

## 版本

- Skill: 1.3

## 安装

下载或克隆本仓库，然后把独立 Skill 文件夹复制到你的 Codex skills 目录：

```bash
mkdir -p ~/.codex/skills
cp -R skill/wildidea ~/.codex/skills/wildidea
```

重新打开一个 Codex 对话，然后这样使用：

```text
Use $wildidea to generate cross-domain ideas for ...
```

## 包含内容

- `skill/wildidea/SKILL.md`: Skill 入口
- `skill/wildidea/references/wildidea-skill.md`: 完整工作流规则
- `skill/wildidea/references/domains.json`: 卡池数据
- `skill/wildidea/scripts/search_helper.py`: 免 API key 联网搜索 helper
- `skill/wildidea/scripts/pick_domain_slots.py`: 卡池抽取脚本
- `skill/wildidea/templates/poster.html`: 可选海报模板

如果你想使用带联网搜索能力的版本，直接下载 `skill/wildidea/` 即可，不需要部署其他服务。

## 核心流程

1. 输入问题，并写下需要避开的常见解法。
2. 从卡池中抽取远领域源机制。
3. 识别具体源现象。
4. 抽象出不含目标领域术语的可迁移方法。
5. 将方法映射回用户问题。
6. 过滤或重抽弱候选。
7. 返回具体的灵感卡片。

## 项目结构

```text
skill/wildidea/           独立可下载 Codex Skill
SKILL.md                  根目录 Skill 入口镜像
docs/wildidea-skill.md    完整 Skill 规则镜像
```

## 本地校验

```bash
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py skill/wildidea
```

## 许可

MIT
