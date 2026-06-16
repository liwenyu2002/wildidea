<div align="center">

# WildIdea Skill

[![Skill](https://img.shields.io/badge/Codex%20Skill-v1.3-6f42c1)](./skill/wildidea/SKILL.md)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)

[简体中文](./README.md) | [English](./README_EN.md)

**把“他山之石”强行引入问题现场，生成更远、更具体的创新思路。**

WildIdea 是一个独立的 Codex Skill，用于产品、策略、研究、算法和设计问题的跨领域创新发散。

</div>

## 项目简介

人类看到问题的第一个想法，往往是最不具有创造力的。

WildIdea 不围绕问题原地发散，而是先从远领域卡池中抽取一个源现象，将其冻结为“他山之石”，再抽象出可迁移的方法论，最后映射回用户的问题。这种流程可以打断熟悉领域里的惯性答案，减少“把老解法换个包装当新东西”的情况。

## 核心能力

| 能力 | 说明 |
|---|---|
| 远领域抽卡 | 从算法技术、学术机制、人文艺术、产品机制、毛选、随机组词等卡池抽取源机制 |
| 他山之石 | 先展示真实源现象，再抽象出方法论，帮助用户理解创意从哪里来 |
| 联网搜索 | 内置免 API key 搜索 helper，用于随机组词和基础新颖性检查 |
| 质量过滤 | 对结构深度、领域距离、新颖度和可用性进行约束，弱候选可重抽 |
| 独立使用 | 直接下载 `skill/wildidea/` 即可使用，不需要额外服务 |

## 快速开始

下载或克隆本仓库，然后把独立 Skill 文件夹复制到 Codex skills 目录：

```bash
mkdir -p ~/.codex/skills
cp -R skill/wildidea ~/.codex/skills/wildidea
```

重新打开一个 Codex 对话，然后这样使用：

```text
Use $wildidea to generate cross-domain ideas for 如何做一个新鲜的相册 APP
```

## 工作流

1. 输入问题，并写下需要避开的常见解法。
2. 从远领域卡池中抽取源机制。
3. 识别具体源现象。
4. 抽象出不含目标领域术语的可迁移方法。
5. 将方法映射回用户问题。
6. 过滤或重抽弱候选。
7. 返回具体的灵感卡片。

## 包含内容

| 路径 | 作用 |
|---|---|
| `skill/wildidea/SKILL.md` | Skill 入口 |
| `skill/wildidea/references/wildidea-skill.md` | 完整工作流规则 |
| `skill/wildidea/references/domains.json` | 卡池数据 |
| `skill/wildidea/scripts/search_helper.py` | 免 API key 联网搜索 helper |
| `skill/wildidea/scripts/pick_domain_slots.py` | 卡池抽取脚本 |
| `skill/wildidea/templates/poster.html` | 可选海报模板 |

## 本地校验

```bash
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py skill/wildidea
```

## 许可

MIT
