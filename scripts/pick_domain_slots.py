#!/usr/bin/env python3
"""Randomly sample WildIdea domain slots without loading the full pool into model context.

Usage:
  python scripts/pick_domain_slots.py --type algorithm
  python scripts/pick_domain_slots.py --type product
  python scripts/pick_domain_slots.py --type algorithm --seed 42

The domain anchor pool is embedded here intentionally: SKILL.md should call this
script and only read the returned JSON, not the full pool.
"""
import argparse
import json
import pathlib
import random
import sys

POOLS = {
  "D1": [
    {
      "domain": "序列建模",
      "anchor": "CTC 允许 blank：不是每一帧都必须贴标签，最后再把重复和 blank 折叠成序列",
      "kind": "经典",
      "source": "[Graves et al., 2006](https://www.cs.toronto.edu/~graves/icml_2006.pdf)"
    },
    {
      "domain": "鲁棒估计",
      "anchor": "RANSAC 随机抽最小样本拟合模型，只有内点比例超过阈值才接受",
      "kind": "经典",
      "source": "[Fischler & Bolles, 1981](https://dl.acm.org/doi/10.1145/358669.358692)"
    },
    {
      "domain": "不确定性",
      "anchor": "Conformal prediction 不硬给一个类，而是输出满足覆盖率的候选集合",
      "kind": "经典/通用",
      "source": "[Vovk et al., 2005](https://link.springer.com/book/10.1007/b106715)"
    },
    {
      "domain": "生成模型",
      "anchor": "DDPM 先逐步加噪，再训练模型一步步反向去噪",
      "kind": "近年经典",
      "source": "[Ho et al., 2020](https://proceedings.neurips.cc/paper/2020/hash/4c5bcfec8584af0d967f1ab10179ca4b-Abstract.html)"
    },
    {
      "domain": "条件生成",
      "anchor": "Classifier-free guidance 同一扩散模型同时学有条件和无条件分数，采样时用 guidance scale 拉开方向",
      "kind": "近年经典",
      "source": "[Ho & Salimans, 2022](https://arxiv.org/abs/2207.12598)"
    },
    {
      "domain": "参数高效微调",
      "anchor": "LoRA 冻结原模型权重，只训练低秩增量矩阵",
      "kind": "近年经典",
      "source": "[Hu et al., 2021](https://arxiv.org/abs/2106.09685)"
    },
    {
      "domain": "知识增强",
      "anchor": "RAG 先检索外部文档，再让生成模型基于检索内容回答",
      "kind": "近年经典",
      "source": "[Lewis et al., 2020](https://r.jordan.im/download/language-models/lewis2020.pdf)"
    },
    {
      "domain": "偏好优化",
      "anchor": "DPO 直接用 chosen/rejected 偏好对优化策略，不先训练独立 reward model",
      "kind": "近年经典",
      "source": "[Rafailov et al., 2023](https://arxiv.org/abs/2305.18290)"
    },
    {
      "domain": "推理采样",
      "anchor": "Self-consistency 同一题采样多条推理路径，用最终答案的一致性投票",
      "kind": "近年经典",
      "source": "[Wang et al., 2022](https://arxiv.org/abs/2203.11171)"
    },
    {
      "domain": "多任务优化",
      "anchor": "PCGrad 发现两个任务梯度冲突时，把冲突方向投影掉",
      "kind": "近年经典",
      "source": "[Yu et al., 2020](https://arxiv.org/abs/2001.06782)"
    },
    {
      "domain": "强化学习",
      "anchor": "Prioritized replay 按 TD-error 给经验排序，错误大的经验更常回放",
      "kind": "经典",
      "source": "[Schaul et al., 2015](https://arxiv.org/abs/1511.05952)"
    },
    {
      "domain": "快速适应",
      "anchor": "MAML 学一个初始参数，让模型用少量样本、少数梯度步就能适应新任务",
      "kind": "经典",
      "source": "[Finn et al., 2017](https://proceedings.mlr.press/v70/finn17a)"
    },
    {
      "domain": "超参搜索",
      "anchor": "Hyperband/Successive Halving 先给所有方案小预算，再淘汰低分者，把预算给幸存者",
      "kind": "经典",
      "source": "[Li et al., 2017](https://jmlr.org/papers/v18/16-558.html)"
    },
    {
      "domain": "多臂老虎机",
      "anchor": "UCB 选择“当前均值 + 探索奖励”最大的臂；样本少的臂自动得到更高探索项",
      "kind": "经典",
      "source": "[Auer et al., 2002](https://homes.di.unimi.it/~cesabian/Pubblicazioni/ml-02.pdf)"
    },
    {
      "domain": "贝叶斯决策",
      "anchor": "Thompson sampling 从每个动作的后验里抽一次样，选抽样收益最高者",
      "kind": "经典/通用",
      "source": "[Agrawal & Goyal, 2012](https://proceedings.mlr.press/v23/agrawal12.html)"
    },
    {
      "domain": "状态估计",
      "anchor": "Kalman filter 用预测值和观测值的残差更新状态，残差协方差决定信任程度",
      "kind": "经典",
      "source": "[Kalman, 1960](https://asmedigitalcollection.asme.org/fluidsengineering/article/82/1/35/397706/A-New-Approach-to-Linear-Filtering-and-Prediction)"
    },
    {
      "domain": "异常门控",
      "anchor": "NIS gate 用 innovation 的二次型与卡方阈值比较，超阈值观测不直接更新",
      "kind": "工程经典",
      "source": "[Bar-Shalom tracking text](https://onlinelibrary.wiley.com/doi/book/10.1002/0471221279)"
    },
    {
      "domain": "隐变量估计",
      "anchor": "EM 算法在 E 步估计隐变量责任分配，在 M 步更新参数，反复提高似然",
      "kind": "经典",
      "source": "[Dempster et al., 1977](https://www.jstor.org/stable/2984875)"
    },
    {
      "domain": "动态规划",
      "anchor": "Viterbi 每个时刻只保存到达各状态的最佳前驱，最后一次性回溯路径",
      "kind": "经典",
      "source": "[Viterbi, 1967](https://ieeexplore.ieee.org/document/1054010)"
    },
    {
      "domain": "目标检测",
      "anchor": "NMS 按置信度排序，保留高分框并抑制 IoU 超阈值的重叠框",
      "kind": "工程经典",
      "source": "[Torchvision NMS](https://pytorch.org/vision/main/generated/torchvision.ops.nms.html)"
    },
    {
      "domain": "数据结构",
      "anchor": "Bloom filter 允许误报命中，但不允许漏掉已加入元素，用空间换速度",
      "kind": "经典",
      "source": "[Bloom, 1970](https://dl.acm.org/doi/10.1145/362686.362692)"
    },
    {
      "domain": "漂移检测",
      "anchor": "CUSUM 不因单点异常报警，而是累积偏差越过阈值才触发",
      "kind": "经典",
      "source": "[Page, 1954](https://www.jstor.org/stable/2333009)"
    },
    {
      "domain": "特征选择",
      "anchor": "Knockoff 造同分布假变量，用真/假变量重要性差控制误发现率",
      "kind": "近年经典",
      "source": "[Barber & Candès, 2015](https://arxiv.org/abs/1404.5609)"
    },
    {
      "domain": "多重检验",
      "anchor": "Benjamini-Hochberg 把 p 值排序，找最大 k 使 p(k) <= kq/m 来控 FDR",
      "kind": "经典",
      "source": "[Benjamini & Hochberg, 1995](https://www.jstor.org/stable/2346101)"
    },
    {
      "domain": "近邻检索",
      "anchor": "HNSW 用上层稀疏远链路和底层密集邻接图，从高层贪心下沉到近邻",
      "kind": "近年经典",
      "source": "[Malkov & Yashunin, 2016](https://arxiv.org/abs/1603.09320)"
    },
    {
      "domain": "异常检测",
      "anchor": "Isolation Forest 用随机切分隔离样本；越少切分就被隔离的点越异常",
      "kind": "经典",
      "source": "[Liu et al., 2008](https://cs.nju.edu.cn/zhouzh/zhouzh.files/publication/icdm08b.pdf)"
    },
    {
      "domain": "网页排序",
      "anchor": "PageRank 用阻尼随机游走计算稳定分布，既沿链接走也随机跳转",
      "kind": "经典",
      "source": "[Page et al., 1999](http://ilpubs.stanford.edu:8090/422/1/1999-66.pdf)"
    },
    {
      "domain": "黑盒优化",
      "anchor": "Expected Improvement 选择“相对当前最好值的期望改进”最大的下一个实验点",
      "kind": "经典",
      "source": "[Jones et al., 1998](https://link.springer.com/article/10.1023/A:1008306431147)"
    },
    {
      "domain": "隐私训练",
      "anchor": "Differential privacy 先裁剪单个样本贡献，再加噪声，用 epsilon 记录隐私预算",
      "kind": "经典",
      "source": "[Dwork et al., 2006](https://www.microsoft.com/en-us/research/publication/calibrating-noise-to-sensitivity-in-private-data-analysis/)"
    },
    {
      "domain": "专家路由",
      "anchor": "Switch Transformer 每个 token 只路由到少数专家，并加入负载均衡损失",
      "kind": "近年经典",
      "source": "[Fedus et al., 2021](https://arxiv.org/abs/2101.03961)"
    },
    {
      "domain": "长序列建模",
      "anchor": "Mamba 用输入依赖的选择机制决定状态空间模型保留/丢弃哪些信息",
      "kind": "近年新机制",
      "source": "[Gu & Dao, 2023](https://arxiv.org/abs/2312.00752)"
    },
    {
      "domain": "可提示模型",
      "anchor": "SAM 用点、框、mask 等 prompt 触发分割，并对不确定 prompt 输出多个候选 mask",
      "kind": "近年新机制",
      "source": "[Kirillov et al., 2023](https://arxiv.org/abs/2304.02643)"
    },
    {
      "domain": "安全控制",
      "anchor": "Safety shield 在动作真正执行前检查约束，危险动作被替换或拦截",
      "kind": "经典/工程",
      "source": "[Control barrier functions survey](https://arxiv.org/abs/1903.11199)"
    },
    {
      "domain": "LLM 推理",
      "anchor": "DeepSeek-R1-Zero 用纯强化学习在可验证任务上激发自反思、验证和动态策略调整，不依赖大量人工推理轨迹",
      "kind": "2025 代表机制",
      "source": "[DeepSeek-R1](https://arxiv.org/abs/2501.12948)"
    },
    {
      "domain": "推理预算",
      "anchor": "s1 通过 budget forcing 控制 test-time 思维长度，推理时多算可以换更高结果质量",
      "kind": "2025 代表机制",
      "source": "[s1](https://arxiv.org/abs/2501.19393)"
    },
    {
      "domain": "自动算法发现",
      "anchor": "AlphaEvolve 让 LLM 生成代码变体，用自动评测器打分，再保留优胜变体进入下一轮进化",
      "kind": "2025 官方系统",
      "source": "[Google DeepMind AlphaEvolve](https://deepmind.google/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/)"
    },
    {
      "domain": "Agentic RAG",
      "anchor": "Agentic RAG 把检索放进智能体规划环，让模型决定何时检索、检索什么、如何使用证据",
      "kind": "2025 综述",
      "source": "[Agentic RAG survey](https://arxiv.org/abs/2501.09136)"
    },
    {
      "domain": "评审器扩展",
      "anchor": "Generalist reward model 在推理时也增加计算、生成 critique 并聚合判断，让评审器本身做 test-time scaling",
      "kind": "2025 代表机制",
      "source": "[Inference-Time Scaling for Generalist Reward Modeling](https://arxiv.org/abs/2504.02495)"
    },
    {
      "domain": "向量检索",
      "anchor": "Filtered vector search 要求返回与查询相似且满足结构化过滤条件的向量，检索与筛选不能互相破坏召回",
      "kind": "2025 VLDB 方向",
      "source": "[Filtered Vector Search tutorial](https://doi.org/10.14778/3750601.3750700)"
    },
    {
      "domain": "向量数据库",
      "anchor": "GaussDB-Vector 把实时插入删除、持久化、分布式搜索和 scalar-vector hybrid filtering 放进同一个向量数据库系统",
      "kind": "2025 VLDB 系统",
      "source": "[GaussDB-Vector](https://www.vldb.org/pvldb/vol18/p4951-sun.pdf)"
    },
    {
      "domain": "结构化检索",
      "anchor": "GraphRAG 先从文档构建实体知识图和社区摘要，再把局部回答汇总成全局回答",
      "kind": "2024/2025 代表机制",
      "source": "[GraphRAG](https://arxiv.org/abs/2404.16130)"
    },
    {
      "domain": "尾部风险",
      "anchor": "Conformal tail risk control 不只校准平均表现，而是用轻量校准控制黑盒模型的极端坏结果风险",
      "kind": "2025 代表机制",
      "source": "[Conformal Tail Risk Control](https://arxiv.org/abs/2502.20285)"
    },
    {
      "domain": "深度特征选择",
      "anchor": "DiffKnock 用扩散模型生成 knockoff 假特征，再用真/假特征重要性差控制高维选择的 FDR",
      "kind": "2025 代表机制",
      "source": "[DiffKnock](https://arxiv.org/abs/2510.01418)"
    },
    {
      "domain": "深度特征选择",
      "anchor": "深度网络内部做特征选择时也要给出错误发现率控制，不允许只凭梯度重要性直接选特征",
      "kind": "2025/2026 理论机制",
      "source": "[Deep FDR feature selection](https://arxiv.org/abs/2512.04696)"
    },
    {
      "domain": "因果基础模型",
      "anchor": "CausalFM 用结构因果模型生成先验数据预训练 PFN，让因果推断任务通过 in-context learning 完成",
      "kind": "2025/2026 代表机制",
      "source": "[CausalFM](https://arxiv.org/abs/2506.10914)"
    },
    {
      "domain": "在线推断",
      "anchor": "Always-valid inference/e-values 允许实验过程中随时看数据、随时停，同时仍控制错误率",
      "kind": "近年统计机制",
      "source": "[E-values overview](https://arxiv.org/abs/1906.07801)"
    },
    {
      "domain": "无 oracle 测试",
      "anchor": "Metamorphic testing 不需要标准答案，而是检查输入变换前后输出是否满足必要关系",
      "kind": "2025/2026 测试机制",
      "source": "[Metamorphic testing for LLMs](https://arxiv.org/abs/2511.02108)"
    },
    {
      "domain": "智能体安全",
      "anchor": "AI agent 的风险不只是不良回答，还包括工具调用、权限、数据泄露和越权动作，需要运行时边界",
      "kind": "2025/2026 安全机制",
      "source": "[IBM AI agent security](https://www.ibm.com/think/topics/ai-agent-security)"
    },
    {
      "domain": "人机模糊测试",
      "anchor": "Human-in-the-loop fuzzing 把专家放在种子选择、引导和可视化环节，而不是只让人做结果标注",
      "kind": "2026 测试机制",
      "source": "[HITL fuzzing review](https://arxiv.org/abs/2603.13411)"
    },
    {
      "domain": "可微状态估计",
      "anchor": "Autodifferentiable Ensemble Kalman Filter 保留预测-校正结构，同时让动态模型和滤波过程可被学习",
      "kind": "经典延展",
      "source": "[Autodifferentiable EnKF](https://epubs.siam.org/doi/10.1137/21M1434477)"
    },
    {
      "domain": "机器人基础模型",
      "anchor": "GR00T N1 用慢思考系统做规划、快动作系统做连续运动，把机器人控制拆成快慢双系统",
      "kind": "2025 官方系统",
      "source": "[NVIDIA GR00T N1](https://developer.nvidia.com/blog/nvidia-isaac-gr00t-n1-open-foundation-model-for-generalist-humanoid-robots/)"
    }
  ],
  "D2": [
    {
      "domain": "免疫学",
      "anchor": "T 细胞激活需要抗原信号 + 共刺激信号；缺第二信号会变成不响应",
      "kind": "经典",
      "source": "[Molecular mechanisms of co-stimulation](https://pmc.ncbi.nlm.nih.gov/articles/PMC3786574/)"
    },
    {
      "domain": "免疫学",
      "anchor": "胸腺选择同时淘汰反应太弱和太强的 T 细胞，只留下中间可用者",
      "kind": "经典/综述",
      "source": "[Nature Reviews Immunology, 2023](https://www.nature.com/articles/s41577-023-00911-8)"
    },
    {
      "domain": "免疫学",
      "anchor": "免疫检查点如 CTLA-4/PD-1 不是增强攻击，而是在特定阶段刹车",
      "kind": "经典/综述",
      "source": "[Immune checkpoint review](https://jeccr.biomedcentral.com/articles/10.1186/s13046-021-01987-7)"
    },
    {
      "domain": "分子生物",
      "anchor": "CRISPR-Cas9 用 guide RNA 定位目标 DNA，再由 Cas9 切割",
      "kind": "经典",
      "source": "[Jinek et al., 2012](https://pubmed.ncbi.nlm.nih.gov/22745249/)"
    },
    {
      "domain": "分子生物",
      "anchor": "PCR 每轮用变性、退火、延伸三步复制目标片段，循环数带来指数放大",
      "kind": "经典",
      "source": "[Mullis Nobel lecture](https://www.nobelprize.org/prizes/chemistry/1993/mullis/lecture/)"
    },
    {
      "domain": "流行病学",
      "anchor": "Rt 大于 1 时传播扩张，小于 1 时传播收缩；干预目标是把 Rt 压到阈值以下",
      "kind": "经典/公共卫生",
      "source": "[CDC Emerging Infectious Diseases](https://wwwnc.cdc.gov/eid/article/25/1/17-1901_article)"
    },
    {
      "domain": "诊断医学",
      "anchor": "贝叶斯诊断先有 pre-test probability，再用似然比更新成 post-test probability",
      "kind": "经典",
      "source": "[NCBI diagnostic testing](https://www.ncbi.nlm.nih.gov/books/NBK98237/)"
    },
    {
      "domain": "灾难医学",
      "anchor": "START triage 先问能否行走，再看呼吸、灌注、意识，按颜色分诊",
      "kind": "工程经典",
      "source": "[HHS CHEMM START](https://chemm.hhs.gov/startadult.htm)"
    },
    {
      "domain": "神经科学",
      "anchor": "STDP 由突触前后放电的先后毫秒差决定增强还是削弱连接",
      "kind": "经典",
      "source": "[Markram et al., 1997](https://www.nature.com/articles/385807a0)"
    },
    {
      "domain": "交通工程",
      "anchor": "匝道控制不让车随便进主路，而是按主路状态限制流入",
      "kind": "经典/工程",
      "source": "[ALINEA ramp metering](https://trid.trb.org/View/365587)"
    },
    {
      "domain": "交通网络",
      "anchor": "Braess 悖论：加一条路在某些需求区间反而让整体通行成本上升",
      "kind": "经典",
      "source": "[Roughgarden, 2005](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=758059)"
    },
    {
      "domain": "交通流",
      "anchor": "LWR 模型把车流当作波，拥堵会像冲击波一样向后传播",
      "kind": "经典",
      "source": "[Lighthill & Whitham](https://onlinepubs.trb.org/Onlinepubs/sr/sr79/79-002.pdf)"
    },
    {
      "domain": "交通信号",
      "anchor": "双环相位控制中，冲突相位不能同时放行，必须跨 barrier 切换",
      "kind": "工程经典",
      "source": "[Traffic Signal Timing Manual](https://www.govinfo.gov/content/pkg/GOVPUB-TD2-PURL-gpo9122/pdf/GOVPUB-TD2-PURL-gpo9122.pdf)"
    },
    {
      "domain": "建筑安全",
      "anchor": "防火/防烟分区通过隔断、门和压差限制烟火蔓延，局部失火不应全楼扩散",
      "kind": "工程经典",
      "source": "[ASHRAE smoke control](https://handbook.ashrae.org/Handbooks/A19/IP/a19_ch54/a19_ch54_ip.aspx)"
    },
    {
      "domain": "结构工程",
      "anchor": "抗震耗能构件允许指定部位先屈服，把破坏集中到可替换部件",
      "kind": "工程经典",
      "source": "[FEMA earthquake engineering](https://www.fema.gov/emergency-managers/risk-management/earthquake/training)"
    },
    {
      "domain": "断裂力学",
      "anchor": "应力强度因子超过材料断裂韧度时，裂纹会继续扩展",
      "kind": "工程经典",
      "source": "[NASA fracture control](https://standards.nasa.gov/standard/nasa/nasa-std-5019)"
    },
    {
      "domain": "水文工程",
      "anchor": "调蓄池先截留峰值径流，再通过受限出口慢慢释放，削平下游洪峰",
      "kind": "工程经典",
      "source": "[EPA stormwater BMPs](https://www.epa.gov/npdes/national-menu-best-management-practices-bmps-stormwater-post-construction)"
    },
    {
      "domain": "建筑理论",
      "anchor": "空间句法把空间连通关系变成图，研究可达性如何影响行为",
      "kind": "经典",
      "source": "[Hillier & Hanson, 1984](https://www.cambridge.org/core/books/social-logic-of-space/introduction/96F4F7333982C7693C7808827ADEC2EB)"
    },
    {
      "domain": "城市行为",
      "anchor": "欲望路径记录真实行走路线；正式道路若不贴合，会被脚印纠正",
      "kind": "近年研究",
      "source": "[Desire path study, 2025](https://www.sciencedirect.com/science/article/pii/S026427512501008X)"
    },
    {
      "domain": "生态学",
      "anchor": "岛屿物种数由迁入率和灭绝率共同决定，面积和隔离度改变平衡点",
      "kind": "经典",
      "source": "[MacArthur & Wilson](https://link.springer.com/article/10.1023/A%3A1016393430551)"
    },
    {
      "domain": "生态学",
      "anchor": "适度扰动可以提高多样性；太少或太多扰动都会降低多样性",
      "kind": "经典/争议",
      "source": "[Pulse dynamics review](https://pmc.ncbi.nlm.nih.gov/articles/PMC6851700/)"
    },
    {
      "domain": "生态学",
      "anchor": "关键种移除会触发级联改变，小角色可能控制大结构",
      "kind": "经典",
      "source": "[Britannica Keystone species](https://www.britannica.com/science/keystone-species)"
    },
    {
      "domain": "系统韧性",
      "anchor": "Adaptive cycle 有增长、保守、释放、重组四阶段；崩塌后可能重组",
      "kind": "经典/综述",
      "source": "[Adaptive cycle / panarchy](https://www.mdpi.com/2073-445X/10/9/980)"
    },
    {
      "domain": "供应链",
      "anchor": "牛鞭效应：需求信息向上游传递时波动被放大",
      "kind": "经典",
      "source": "[Lee et al., 1997](https://pubsonline.informs.org/doi/10.1287/mnsc.43.4.546)"
    },
    {
      "domain": "库存理论",
      "anchor": "Newsvendor 用缺货成本和滞销成本的比值决定一次性订货分位数",
      "kind": "经典",
      "source": "[Newsvendor model](https://metricgate.com/docs/inventory-newsvendor/)"
    },
    {
      "domain": "排队论",
      "anchor": "Little's Law：系统平均在制数量 = 到达率 x 平均停留时间",
      "kind": "经典",
      "source": "[Little, 1961](https://pubsonline.informs.org/doi/10.1287/opre.9.3.383)"
    },
    {
      "domain": "控制工程",
      "anchor": "PID 的积分项会累积历史误差；anti-windup 在执行器饱和时限制积分继续膨胀",
      "kind": "工程经典",
      "source": "[MathWorks anti-windup](https://www.mathworks.com/help/simulink/slref/anti-windup-control-using-a-pid-controller.html)"
    },
    {
      "domain": "社会学",
      "anchor": "阈值模型里，每个人在看到足够比例他人行动后才加入集体行动",
      "kind": "经典",
      "source": "[Granovetter, 1978](https://www.jstor.org/stable/2778111)"
    },
    {
      "domain": "拍卖理论",
      "anchor": "二价拍卖让最高出价者获胜但只付第二高价，降低虚报价格的动机",
      "kind": "经典",
      "source": "[Vickrey, 1961](https://www.jstor.org/stable/2627882)"
    },
    {
      "domain": "实验设计",
      "anchor": "随机对照试验先预定义分组和终点，再用随机化隔离干预效果",
      "kind": "经典/规范",
      "source": "[CONSORT statement](https://www.consort-statement.org/)"
    },
    {
      "domain": "可靠性工程",
      "anchor": "FMEA 逐项列失效模式、影响、原因和检测方式，再按风险优先级处理",
      "kind": "工程经典",
      "source": "[ASQ FMEA](https://asq.org/quality-resources/fmea)"
    },
    {
      "domain": "空间组学",
      "anchor": "CRISPR 扰动和空间转录组同时读出，让“做了什么干预”和“组织邻域里发生什么后果”在同一实验里连接",
      "kind": "2025 生命科学机制",
      "source": "[Cell, 2025](https://www.nature.com/nature-index/article/10.1016/j.cell.2025.02.012)"
    },
    {
      "domain": "单细胞组学",
      "anchor": "单细胞和空间组学把细胞身份、状态和空间邻域一起建模，样本不是孤立点而是带邻居的状态点",
      "kind": "2025 生命科学机制",
      "source": "[Nature Reviews Methods Primers](https://www.nature.com/articles/s43586-025-00392-y)"
    },
    {
      "domain": "非侵入监测",
      "anchor": "eDNA 从水、土壤、空气等环境痕迹识别物种存在，减少直接捕捉或打扰",
      "kind": "生态监测机制",
      "source": "[Nature eDNA review](https://www.nature.com/articles/s41576-023-00600-1)"
    },
    {
      "domain": "交通能源",
      "anchor": "VGI/V2G 把电动车同时当作交通工具、可调度负载和移动储能，调度时要兼顾用户出行与电网需求",
      "kind": "2025 政策/工程机制",
      "source": "[DOE VGI report](https://www.energy.gov/sites/default/files/2025-01/Vehicle_Grid_Integration_Asseessment_Report_01162025.pdf)"
    },
    {
      "domain": "3D 打印建筑",
      "anchor": "建筑结构由打印路径、材料配方和层间连接共同生成，不再只由统一模具决定",
      "kind": "2025 建筑机制",
      "source": "[3D printed construction review](https://www.sciencedirect.com/science/article/pii/S235271022500283X)"
    },
    {
      "domain": "循环建筑",
      "anchor": "循环建材把一处系统的废料重新变成另一处系统的输入，生命周期从“使用后丢弃”改为“再进入系统”",
      "kind": "2025 建筑机制",
      "source": "[Circular construction review](https://www.sciencedirect.com/science/article/pii/S0959652625009268)"
    },
    {
      "domain": "AI 教育",
      "anchor": "研究设计过的 AI tutor 在 RCT 中用即时反馈和个性化脚手架提升学习效果，而不是只提供内容库",
      "kind": "2025 RCT",
      "source": "[Scientific Reports AI tutor RCT](https://www.nature.com/articles/s41598-025-97652-6)"
    },
    {
      "domain": "教育增强",
      "anchor": "Tutor CoPilot 不替代人类导师，而是在实时辅导中给导师专家策略提示",
      "kind": "2024/2025 RCT",
      "source": "[Tutor CoPilot](https://arxiv.org/abs/2410.03017)"
    },
    {
      "domain": "法律科技",
      "anchor": "高风险法律 AI 需要引用验证、责任链和人工复核嵌入工作流，不能只给生成文本",
      "kind": "2025 行业机制",
      "source": "[Stanford HAI legal AI risks](https://hai.stanford.edu/news/ai-trial-legal-models-hallucinate-1-out-6-or-more-benchmarking-queries)"
    },
    {
      "domain": "市场设计",
      "anchor": "多智能体市场要设计资源分配、偏好协调和系统性风险规则，而不是只优化单个 agent",
      "kind": "2025/2026 经济机制",
      "source": "[AI agent market design](https://arxiv.org/abs/2506.16080)"
    }
  ],
  "D3": [
    {
      "domain": "音乐",
      "anchor": "五类对位从一音对一音逐步加复杂度；平行五度/八度被禁止",
      "kind": "经典",
      "source": "[Fux species counterpoint](https://www.ars-nova.com/cpmanual/gradus.htm)"
    },
    {
      "domain": "音乐",
      "anchor": "赋格先让主题在一个声部出现，再让其他声部依次以答题进入",
      "kind": "经典",
      "source": "[Britannica Fugue](https://www.britannica.com/art/fugue)"
    },
    {
      "domain": "音乐分析",
      "anchor": "Schenker 分析把前景音符逐层还原到中景和背景结构",
      "kind": "经典",
      "source": "[Schenkerian analysis](https://en.wikipedia.org/wiki/Schenkerian_analysis)"
    },
    {
      "domain": "音乐作曲",
      "anchor": "十二音技法先定一条音列，再用原形、逆行、倒影、逆行倒影变换，避免某音过早占主导",
      "kind": "经典",
      "source": "[Britannica twelve-tone music](https://www.britannica.com/art/12-tone-music)"
    },
    {
      "domain": "电影",
      "anchor": "蒙太奇通过镜头碰撞产生单个镜头没有的意义",
      "kind": "经典",
      "source": "[Soviet montage theory](https://www.britannica.com/art/montage-filmmaking)"
    },
    {
      "domain": "电影",
      "anchor": "交叉剪辑把不同地点动作并置，制造“同时发生”的紧张关系",
      "kind": "经典",
      "source": "[Film editing](https://www.britannica.com/art/motion-picture/Expressive-elements-of-motion-pictures)"
    },
    {
      "domain": "电影",
      "anchor": "Kuleshov effect 中，同一张脸接不同镜头会被观众读成不同情绪",
      "kind": "经典",
      "source": "[Britannica Kuleshov effect](https://www.britannica.com/art/Kuleshov-effect)"
    },
    {
      "domain": "绘画",
      "anchor": "线性透视把平行线汇聚到消失点，地平线固定观看者眼高",
      "kind": "经典",
      "source": "[Britannica perspective](https://www.britannica.com/art/perspective-art)"
    },
    {
      "domain": "绘画",
      "anchor": "明暗法用强光暗对比塑造体积，边界不是线条而是光影过渡",
      "kind": "经典",
      "source": "[Britannica chiaroscuro](https://www.britannica.com/art/chiaroscuro)"
    },
    {
      "domain": "绘画修复",
      "anchor": "修复遵守最小干预和可逆性，后来的介入应能被识别或撤回",
      "kind": "经典保守原则",
      "source": "[AIC Code of Ethics](https://www.culturalheritage.org/about-conservation/code-of-ethics)"
    },
    {
      "domain": "手工艺",
      "anchor": "金缮不隐藏裂缝，而是用漆和金粉把裂缝变成新信息层",
      "kind": "经典工艺",
      "source": "[Britannica Kintsugi](https://www.britannica.com/art/kintsugi-ceramics)"
    },
    {
      "domain": "档案制度",
      "anchor": "Provenance 要求材料按来源主体保留，不把不同来源混成一个主题堆",
      "kind": "经典原则",
      "source": "[SAA Dictionary provenance](https://dictionary.archivists.org/entry/provenance.html)"
    },
    {
      "domain": "档案制度",
      "anchor": "Original order 要尽量保留原始排列，因为排列本身携带使用语境",
      "kind": "经典原则",
      "source": "[SAA Dictionary original order](https://dictionary.archivists.org/entry/original-order.html)"
    },
    {
      "domain": "文献形态",
      "anchor": "Palimpsest 会刮掉旧文字再写新文字，但旧痕迹仍可能被读出",
      "kind": "经典机制",
      "source": "[Britannica palimpsest](https://www.britannica.com/topic/palimpsest)"
    },
    {
      "domain": "建筑/设计",
      "anchor": "Pattern language 把反复有效的空间问题写成可复用模式",
      "kind": "经典",
      "source": "[PatternLanguage.com](https://www.patternlanguage.com/)"
    },
    {
      "domain": "叙事",
      "anchor": "框架叙事让一个故事包含另一个故事，内外层相互改变解释",
      "kind": "经典机制",
      "source": "[Britannica frame story](https://www.britannica.com/art/frame-story)"
    },
    {
      "domain": "戏剧",
      "anchor": "角色行动可拆成 objective、obstacle、action；每一场戏由目标和阻碍推动",
      "kind": "经典机制",
      "source": "[Stanislavsky system](https://www.britannica.com/art/Stanislavsky-system)"
    },
    {
      "domain": "舞蹈",
      "anchor": "Laban effort 用重量、时间、空间、流动四维描述动作质感",
      "kind": "经典机制",
      "source": "[Laban movement analysis](https://www.britannica.com/art/Labanotation)"
    },
    {
      "domain": "纺织",
      "anchor": "织物由经线和纬线交错形成；经线张力先设定结构边界，纬线再填充图案",
      "kind": "经典工艺",
      "source": "[Britannica weaving](https://www.britannica.com/technology/weaving)"
    },
    {
      "domain": "陶瓷",
      "anchor": "烧制按升温、保温、降温曲线改变釉面和坯体；温度窗口错了会变形或开裂",
      "kind": "经典工艺",
      "source": "[Britannica pottery](https://www.britannica.com/art/pottery)"
    },
    {
      "domain": "书法",
      "anchor": "笔画顺序、提按和转折决定字形骨架；同一轮廓不能替代真实书写过程",
      "kind": "经典机制",
      "source": "[Britannica calligraphy](https://www.britannica.com/art/calligraphy)"
    },
    {
      "domain": "仪式",
      "anchor": "固定动作、顺序和参与资格让群体状态可重复切换",
      "kind": "经典机制",
      "source": "[Ritual studies overview](https://www.britannica.com/topic/ritual)"
    },
    {
      "domain": "历史方法",
      "anchor": "史料批判先问来源、作者、时间和传抄链，再决定材料能证明什么",
      "kind": "经典机制",
      "source": "[Historical method](https://www.britannica.com/topic/historiography)"
    },
    {
      "domain": "博物馆",
      "anchor": "入藏需要编号、来源、保存条件和位置记录；没有 provenance 的材料可信度下降",
      "kind": "经典机制",
      "source": "[Collections Trust accessioning](https://collectionstrust.org.uk/resource/accessioning/)"
    },
    {
      "domain": "AI 创作",
      "anchor": "文生图 AI 提高单个创作者产量和受欢迎度，但平均内容新颖性下降，工具会提升局部效率也压缩群体多样性",
      "kind": "2024 研究机制",
      "source": "[PNAS Nexus](https://academic.oup.com/pnasnexus/article/3/3/pgae052/7618478)"
    },
    {
      "domain": "交互创作",
      "anchor": "交互式 GenAI 创作系统把创作做成多轮协商、局部编辑和选择保留，而不是一次性生成",
      "kind": "2025 HCI 机制",
      "source": "[Interactive GenAI creativity survey](https://arxiv.org/abs/2503.13517)"
    },
    {
      "domain": "创意产业",
      "anchor": "生成式 AI 进入音乐、影视、设计和游戏流程后，创意链条从“单点生成”变成灵感、草稿、编辑、协作、分发的重组",
      "kind": "2025 综述机制",
      "source": "[AI creative industries review](https://www.sciencedirect.com/science/article/pii/S0268401225000217)"
    },
    {
      "domain": "文化遗产",
      "anchor": "AI 文化遗产保护先做损伤识别、环境预测和风险评估，再决定修复或展示策略",
      "kind": "2025 综述机制",
      "source": "[AI heritage conservation review](https://www.sciencedirect.com/science/article/pii/S2352710225030992)"
    },
    {
      "domain": "数字博物馆",
      "anchor": "数字博物馆用文本到图像、3D 建模和大规模场景生成做可探索展陈，但需要长期保存和真实性约束",
      "kind": "2025 综述机制",
      "source": "[npj Heritage Science](https://www.nature.com/articles/s40494-025-02164-1)"
    },
    {
      "domain": "文化遗产",
      "anchor": "AI + IoT + 物理知识先建立可监测的文物数字副本，在副本里预测损伤与试错保护策略",
      "kind": "2026 机制",
      "source": "[AI-IoT heritage framework](https://arxiv.org/abs/2604.03233)"
    },
    {
      "domain": "创意研究",
      "anchor": "NeurIPS Creative AI track 把 AI 艺术、设计和创造实践作为正式研究输出，成果不只论文，也可以是可体验系统",
      "kind": "2025 会议机制",
      "source": "[NeurIPS Creative AI](https://nips.cc/Conferences/2025/CallForCreativeAI)"
    }
  ],
  "D4": [
    {
      "domain": "邮件",
      "anchor": "Gmail Undo Send 在发送后保留短暂取消窗口，用户可撤回误发邮件",
      "kind": "官方/补救机制",
      "source": "[Gmail Undo Send](https://support.google.com/mail/answer/2819488)"
    },
    {
      "domain": "相册/隐私",
      "anchor": "Google Photos Locked Folder 把敏感照片从照片流、搜索、相册、回忆里隐藏，并用锁屏或账号密码保护",
      "kind": "官方/隐私机制",
      "source": "[Google Photos Locked Folder](https://support.google.com/photos/answer/10694388)"
    },
    {
      "domain": "相册/分享",
      "anchor": "Google Photos 可把照片、视频、相册或 highlight video 分享给联系人，也可创建 direct link",
      "kind": "官方/分享机制",
      "source": "[Google Photos about](https://www.google.com/photos/about)"
    },
    {
      "domain": "视频流媒体",
      "anchor": "Netflix Skip Intro 在片头出现时给跳过按钮，减少连续观看里重复片头的等待",
      "kind": "官方/省时机制",
      "source": "[About Netflix Skip Intro](https://about.netflix.com/news/looking-back-on-the-origin-of-skip-intro-five-years-later)"
    },
    {
      "domain": "音乐",
      "anchor": "Spotify Discover Weekly 每周自动生成个性化发现歌单，把找新歌的主动搜索变成定期投递",
      "kind": "官方/发现机制",
      "source": "[Spotify Newsroom](https://newsroom.spotify.com/2025-06-30/discover-weekly-turns-10-celebrating-100-billion-tracks-streamed-and-a-decade-of-personalized-discovery/)"
    },
    {
      "domain": "学习",
      "anchor": "Duolingo Streak Freeze 允许用户请假一天仍保住连续学习记录，降低一次中断带来的放弃感",
      "kind": "官方/容错机制",
      "source": "[Duolingo streak](https://blog.duolingo.com/how-duolingo-streak-builds-habit/)"
    },
    {
      "domain": "求职",
      "anchor": "LinkedIn Open to Work 让用户声明职位、地点等求职意向，使招聘方搜索时更容易匹配到",
      "kind": "官方/信号机制",
      "source": "[LinkedIn Help](https://www.linkedin.com/help/linkedin/answer/a507508/let-recruiters-know-you-re-open-to-opportunities)"
    },
    {
      "domain": "账号隐私",
      "anchor": "Apple Hide My Email 为每个网站生成唯一随机邮箱并转发到真实邮箱，用户不必暴露主邮箱",
      "kind": "官方/隐私机制",
      "source": "[Apple Support](https://support.apple.com/en-gb/guide/icloud/-mme38e1602db/icloud)"
    },
    {
      "domain": "聊天隐私",
      "anchor": "WhatsApp disappearing messages 可为新聊天默认设置消息消失时间，并在聊天中提示对方该默认设置",
      "kind": "官方/隐私机制",
      "source": "[Meta WhatsApp update](https://about.fb.com/news/2021/12/whatsapp-default-disappearing-messages-multiple-durations/)"
    },
    {
      "domain": "地图/出行",
      "anchor": "Google Maps Popular Times 显示热门时段、实时繁忙度、等待时间和典型停留时长，帮助用户避开拥挤",
      "kind": "官方/决策机制",
      "source": "[Google Business Profile Help](https://support.google.com/business/answer/6263531)"
    },
    {
      "domain": "地图/无障碍",
      "anchor": "Google Maps Accessible Places 打开后用轮椅图标和入口、座位、洗手间、停车等属性提示可达性",
      "kind": "官方/无障碍机制",
      "source": "[Google Maps accessibility](https://blog.google/products-and-platforms/products/maps/wheelchair-accessible-places-google-maps/)"
    },
    {
      "domain": "打车",
      "anchor": "Uber upfront pricing 在用户叫车前显示本次行程价格，减少到达后价格不确定",
      "kind": "官方/确定性机制",
      "source": "[Uber upfront pricing](https://www.uber.com/us/en/ride/how-it-works/upfront-pricing/)"
    },
    {
      "domain": "打车",
      "anchor": "Lyft Scheduled Rides 让用户提前预约用车，并可在取车前一定时间内编辑或取消",
      "kind": "官方/提前锁定机制",
      "source": "[Lyft Scheduled Rides](https://www.lyft.com/ride-with-lyft/scheduledrides)"
    },
    {
      "domain": "生鲜配送",
      "anchor": "Instacart replacement instructions 让用户为缺货商品预设替换、不要替换或具体说明，购物员可在拣货时看到",
      "kind": "官方/替代机制",
      "source": "[Instacart Help](https://www.instacart.com/help/section/3600079028331/360039162252)"
    },
    {
      "domain": "订阅购物",
      "anchor": "Amazon Subscribe & Save 允许用户随时跳过、取消、改频率、改数量或改配送日，避免自动补货失控",
      "kind": "官方/订阅弹性机制",
      "source": "[About Amazon](https://www.aboutamazon.com/news/retail/how-you-can-save-time-and-money-with-amazon-subscribe-save//)"
    },
    {
      "domain": "电商配送",
      "anchor": "Amazon Add to Delivery 让会员把符合条件的小件一键加入即将到来的包裹，减少重复下单和多包裹等待",
      "kind": "官方/合单机制",
      "source": "[About Amazon](https://www.aboutamazon.com/news/retail/amazon-shopping-prime-members-add-to-delivery/)"
    },
    {
      "domain": "住宿搜索",
      "anchor": "Airbnb Flexible Dates 允许用户在日期或目的地不固定时先探索可住选项，而不是先被迫填死日期",
      "kind": "官方/模糊搜索机制",
      "source": "[Airbnb Flexible Search](https://news.airbnb.com/new-flexible-search/)"
    },
    {
      "domain": "住宿搜索",
      "anchor": "Airbnb Split Stays 在长住或热门目的地里把一次旅行智能拆成两个房源，解决单个房源无法覆盖全程的问题",
      "kind": "官方/拆分补全机制",
      "source": "[Airbnb 2022 Summer Release](https://news.airbnb.com/product-releases/airbnb-2022-summer-release/)"
    },
    {
      "domain": "住宿比价",
      "anchor": "Airbnb total price display 把清洁费等费用纳入搜索展示价格，减少结账前才发现总价上涨",
      "kind": "官方/价格透明机制",
      "source": "[Airbnb total price](https://www.airbnb.com/help/article/3610)"
    },
    {
      "domain": "文件收集",
      "anchor": "Dropbox File Requests 让任何人通过链接上传文件到指定文件夹，即使对方没有 Dropbox 账号；关闭请求后链接不能再上传",
      "kind": "官方/低门槛收集机制",
      "source": "[Dropbox Help](https://help.dropbox.com/share/create-file-request)"
    },
    {
      "domain": "数据迁移",
      "anchor": "Google Takeout 让用户选择产品数据并导出下载，降低离开或备份服务时的锁定感",
      "kind": "官方/可携带机制",
      "source": "[Google Account Help](https://support.google.com/accounts/answer/3024190)"
    },
    {
      "domain": "密码安全",
      "anchor": "Google Password Checkup 自动识别已泄露、重复或弱密码，并引导用户修复高风险账号",
      "kind": "官方/风险提示机制",
      "source": "[Google Password Manager](https://passwords.google/)"
    },
    {
      "domain": "预约",
      "anchor": "Calendly buffer time 自动在会议前后留空，避免用户被连续预约挤压",
      "kind": "官方/缓冲机制",
      "source": "[Calendly buffers](https://help.calendly.com/hc/en-us/articles/223145627-Add-buffer-time-before-or-after-events)"
    },
    {
      "domain": "协作编辑",
      "anchor": "Google Docs suggesting mode 把直接修改变成可接受或拒绝的建议，降低多人改稿时的破坏感",
      "kind": "官方/可逆协作机制",
      "source": "[Google Docs suggest edits](https://support.google.com/docs/answer/6033474)"
    },
    {
      "domain": "购物车",
      "anchor": "Shopify abandoned checkout 记录已填联系方式但未完成付款的 checkout，商家可用恢复流程帮用户回到未完成订单",
      "kind": "官方/中断恢复机制",
      "source": "[Shopify abandoned checkouts](https://help.shopify.com/en/manual/orders/abandoned-checkouts)"
    },
    {
      "domain": "通用消费",
      "anchor": "购物车/订单锁库存设定时间窗口，用户在窗口内可安心付款，过期自动释放库存",
      "kind": "产品通用机制",
      "source": "电商/票务通用机制"
    },
    {
      "domain": "游戏/竞技",
      "anchor": "Ban/Pick 先让用户或队伍排除不想遇到的选项，再选择目标对象，缓解选择空间过大和不公平匹配",
      "kind": "产品通用机制",
      "source": "游戏竞技通用机制"
    },
    {
      "domain": "教育产品",
      "anchor": "间隔重复按遗忘风险安排复习，错题或低熟练项更早回到用户面前",
      "kind": "产品通用机制",
      "source": "学习产品通用机制"
    },
    {
      "domain": "AI 购物",
      "anchor": "Amazon Rufus 让用户用对话完成商品研究、比较和推荐，购物入口从关键词搜索变成任务问答",
      "kind": "官方/代理购物机制",
      "source": "[Amazon Rufus](https://www.aboutamazon.com/news/retail/amazon-rufus-ai-assistant-personalized-shopping-features)"
    },
    {
      "domain": "AI 购物",
      "anchor": "Walmart Sparky 综合评论、场景需求和多模态输入，帮助用户计划、比较和购买",
      "kind": "官方/代理购物机制",
      "source": "[Walmart Sparky](https://corporate.walmart.com/news/2025/06/06/walmart-the-future-of-shopping-is-agentic-meet-sparky)"
    },
    {
      "domain": "礼物购买",
      "anchor": "Target Gift Finder 让用户用对话描述对象和场景，再由系统缩小礼物候选",
      "kind": "官方/场景搜索机制",
      "source": "[Target AI shopping features](https://corporate.target.com/press/release/2025/11/target-launches-new-ai-powered-features-to-make-holiday-shopping-easier%2C-smarter-and-more-fun)"
    },
    {
      "domain": "Agentic commerce",
      "anchor": "AI shopping agents 从推荐商品升级为比较、研究、下单和订单管理，用户委托任务而不是浏览货架",
      "kind": "2025/2026 产品趋势",
      "source": "[Morgan Stanley agentic commerce](https://www.morganstanley.com/insights/articles/agentic-commerce-market-impact-outlook)"
    },
    {
      "domain": "AI 眼镜",
      "anchor": "Android XR 眼镜把 Gemini 放进视野、语音和环境理解里，帮助发生在当下而不是把用户拉回手机屏幕",
      "kind": "2026 官方产品机制",
      "source": "[Google Android XR eyewear](https://blog.google/products-and-platforms/platforms/android/android-xr-io-2026/)"
    },
    {
      "domain": "AI 眼镜",
      "anchor": "Google I/O 2025 的 Android XR 眼镜演示把实时翻译、拍照、日程和视觉理解放到可穿戴交互里",
      "kind": "2025 官方产品机制",
      "source": "[Google Android XR demo](https://blog.google/products/android/android-xr-gemini-glasses-headsets/)"
    },
    {
      "domain": "法律工作流",
      "anchor": "法律 AI 产品把案情评估、文件整理、时间线、证据和 discovery 放到同一责任链里，而不是只生成法律文本",
      "kind": "高风险工作流机制",
      "source": "[Thomson Reuters GenAI report](https://www.thomsonreuters.com/en/reports/2025-generative-ai-in-professional-services-report)"
    }
  ]
}

SLOT_NAMES = {
  "D1": "算法技术",
  "D2": "学术机制",
  "D3": "人文艺术",
  "D4": "产品机制"
}

QUOTAS = {
    "algorithm": {"D1": 5, "D2": 2, "D3": 1, "MAO": 1, "RANDOM_WORD": 1},
    "research": {"D1": 5, "D2": 2, "D3": 1, "MAO": 1, "RANDOM_WORD": 1},
    "product": {"D1": 1, "D2": 3, "D3": 2, "D4": 2, "MAO": 1, "RANDOM_WORD": 1},
    "strategy": {"D1": 1, "D2": 3, "D3": 2, "D4": 2, "MAO": 1, "RANDOM_WORD": 1},
}


def _import_sibling(name):
    script_dir = pathlib.Path(__file__).resolve().parent
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))
    return __import__(name)


def sample_pool(slot, n):
    pool = POOLS.get(slot, [])
    if n > len(pool):
        raise ValueError(f"not enough anchors in {slot}: need {n}, have {len(pool)}")
    picks = random.sample(pool, n)
    return [{"slot": slot, "slot_name": SLOT_NAMES[slot], **row} for row in picks]


def pick_mao():
    pick_seed = _import_sibling("pick_seed")
    seed_id, text, hint = pick_seed.pick(1)[0]
    return {
        "slot": "MAO",
        "slot_name": "毛选",
        "seed_id": seed_id,
        "anchor": text,
        "mechanism_hint": hint,
        "status": "picked",
    }


def pick_random_word():
    search_char = _import_sibling("search_char")
    chars = search_char.load_chars()
    a, b = search_char.pick_chars(chars)
    query = search_char.make_query(a, b)
    return {
        "slot": "RANDOM_WORD",
        "slot_name": "随机组词",
        "chars": {"a": a, "b": b},
        "query": query,
        "status": "needs_search",
        "note": "Use current environment search, keep only real rules/events/boundaries.",
    }


def build_slots(problem_type):
    quota = QUOTAS[problem_type]
    slots = []
    for slot in ("D1", "D2", "D3", "D4"):
        n = quota.get(slot, 0)
        if n:
            slots.extend(sample_pool(slot, n))
    if quota.get("MAO"):
        slots.append(pick_mao())
    if quota.get("RANDOM_WORD"):
        slots.append(pick_random_word())
    random.shuffle(slots)
    return slots


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", choices=sorted(QUOTAS), required=True, help="algorithm/research/product/strategy")
    parser.add_argument("--seed", type=int, help="Optional deterministic seed")
    parser.add_argument("--stats", action="store_true", help="Only print pool counts")
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    if args.stats:
        print(json.dumps({k: len(v) for k, v in POOLS.items()}, ensure_ascii=False, indent=2))
        return

    output = {
        "problem_type": args.type,
        "quota": QUOTAS[args.type],
        "slots": build_slots(args.type),
        "instruction": "Use only these sampled anchors for this run. Do not load the full domain pool.",
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
