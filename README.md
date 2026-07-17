<div align="center">

# WildIdea Skill

[![Skill](https://img.shields.io/badge/Skill-v1.4-6f42c1)](./skill/wildidea/SKILL.md)
[![Web](https://img.shields.io/badge/Web-v1.4-f6d365)](https://wildidea.wenyuli.site)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)

[简体中文](./README.md) | [English](./README_EN.md)

**把“他山之石”强行引入问题现场，生成更远、更具体的创新思路。**

WildIdea 是一个独立的灵感生成 Skill，用于产品、策略、研究、算法和设计问题的跨领域创新发散。

</div>

## 项目简介

人类看到问题的第一个想法，往往是最不具有创造力的。

WildIdea 不围绕问题原地发散，而是先从远领域卡池中抽取一个源现象，将其冻结为“他山之石”，再抽象出可迁移的方法论，最后映射回用户的问题。这种流程可以打断熟悉领域里的惯性答案，减少“把老解法换个包装当新东西”的情况。

## 网页版本

WildIdea 现已推出网页版本：[wildidea.wenyuli.site](https://wildidea.wenyuli.site)。无需安装本地 Skill，注册后即可在浏览器中抽取、保存和分享跨域灵感卡。新用户注册赠送 30 张灵感卡。

<p align="center">
  <a href="https://wildidea.wenyuli.site">
    <img src="./docs/assets/wildidea-web-preview.png" alt="WildIdea 网页版本预览" width="900">
  </a>
</p>

## 核心能力

| 能力 | 说明 |
|---|---|
| 远领域抽卡 | 从算法技术、学术机制、人文艺术、产品机制、毛选、随机组词等卡池抽取源机制 |
| 他山之石 | 先展示真实源现象，再抽象出方法论，帮助用户理解创意从哪里来 |
| 隔离结构映射 | 源机制和目标问题由互相隔离的角色分别建图，再按因果/功能关系对齐 |
| 红蓝对抗 | 每张卡都经过证据红队攻击，并记录存活理由、残余弱点或致命反例 |
| 联网搜索 | 使用 OpenAlex、arXiv 或公开网页检查目标领域撞车，并保留证据记录 |
| 质量与多样性 | 独立判官、定向修复、Vendi 多样性和解法形式检查共同约束输出 |
| 可对接 auto-research | `research` 质量档在生成阶段就抬高新颖度与跨域门槛、放宽即时可行性，筛出又新又可实现的跨域 idea，供 idea→实现→benchmark 全流程复用 |
| 独立使用 | 直接下载 `skill/wildidea/` 即可使用，不需要额外服务 |

## 快速开始

将下方指令粘贴并发送给你的 Agent，Agent 将自动安装本 Skill：

```bash
curl -fsSL https://raw.githubusercontent.com/liwenyu2002/wildidea/main/scripts/install.sh | bash
```

安装完成后，你就可以和你的 Agent 说：

```text
用 wildidea，帮我回答一下如何设计相册 APP
```

## 工作流

1. 将问题结构化并建立目标关系图。
2. 从远领域卡池抽取源机制，在隔离上下文中建立源关系图。
3. 对齐两张图，从共享因果结构生成方案。
4. 由独立判官评分，再由红队尝试用证据杀死方案。
5. 蓝队记录存活理由，或把反例送回定向修复。
6. 做目标领域查重、可证伪推论和整批多样性检查。
7. 返回带红蓝档案的灵感卡片与校验后的 HTML。

## 包含内容

| 路径 | 作用 |
|---|---|
| `skill/wildidea/SKILL.md` | Skill 入口 |
| `skill/wildidea/references/wildidea-skill.md` | 完整工作流规则 |
| `skill/wildidea/references/red-blue-workflow.md` | 红蓝角色、证据门槛与审计档案 |
| `skill/wildidea/references/domains.json` | 卡池数据 |
| `skill/wildidea/scripts/search_helper.py` | 免 API key 联网搜索 helper |
| `skill/wildidea/scripts/pick_domain_slots.py` | 卡池抽取脚本 |
| `skill/wildidea/templates/poster.html` | 可选海报模板 |
| `scripts/install.sh` | 一句话安装脚本 |

## 本地校验

```bash
python3 /path/to/skill-creator/scripts/quick_validate.py skill/wildidea
```

## 许可

MIT
