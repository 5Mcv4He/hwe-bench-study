# HWE-bench v1.1：硬件 Agent 评测机制与验证可靠性研究

> **Independent Benchmark Study · RTL Bug Repair · Agent Evaluation · Verifier Quality**

本仓库是一项基于 [HWE-bench](https://github.com/pku-liang/hwe-bench) v1.1 的**独立源码研究、数据分析与局部复现实验**，不是 HWE-bench 的官方仓库，也不是对整套基准的重新评测。

核心问题：**真实硬件 Bug 怎样被转化成可执行的 Agent 任务？一次 PASS 具体证明了什么？验证器会遗漏哪些行为差异？**

**研究入口：** [研究底稿](report/research-notes.md) · [研究报告](report/hwe-bench-v1.1.md) · [复现说明与证据](evidence/README.md) · [分析与重放脚本](analysis/) · [图表](figures/project-results.png)

## 研究背景与对象

HWE-bench 从 Ibex、CVA6、Caliptra、Rocket Chip、OpenTitan 和 XiangShan 六个真实开源硬件工程中构造 **417 个修复任务**。每项任务涉及问题描述、待修代码、Agent 操作过程和仿真验证。v1.1 官方榜单上七组模型与执行系统均超过 90% 通过率，因此需要进一步研究分数背后的**任务构成、验证强度、实际硬件知识需求和失败模式**。

## 研究方法与已形成的工作

| 环节 | 工作内容 | 证据与产物 |
| --- | --- | --- |
| 任务来源与筛选 | 追踪上游 PR/Issue、补丁拆分、规则筛选、LLM 分类与可复现测试生成，分析任务入库条件 | [完整报告](report/hwe-bench-v1.1.md) |
| Dataset 结构 | 梳理题面、基线、参考补丁、隐藏测试、Fail-to-Pass 判据、测试和评分之间的关系 | [完整报告](report/hwe-bench-v1.1.md) · [源码分析](analysis/) |
| v1.0 / v1.1 修订 | 按任务 ID 对齐 417 条记录，比较题面、测试、参考修复及标签 | [修订统计](evidence/revisions.csv) · [标签统计](evidence/task_labels.csv) |
| Agent / Harness / Verifier | 分析 Harbor 运行、补丁提取、独立评分和开发反馈的边界 | [完整报告](report/hwe-bench-v1.1.md) |
| 局部执行与验证器诊断 | 复核特定 Bug、不同测试版本和真实历史候选的行为差异 | [重放脚本](analysis/replay.py) · [结果数据](evidence/replay.json) |

## 主要发现

**① 不能只根据总体通过率断言硬件工程能力已被充分覆盖。** OpenTitan 占 245/417 道题，任务来源高度不均衡；不同模型往往使用不同 Harness，分数也混合了模型与工具环境的影响。完整分析见[研究报告](report/hwe-bench-v1.1.md)。

**② v1.1 的主要变化集中在验证材料。** 逐字段对齐的统计结果为：**188 份测试、50 份题面和 1 份参考修复**发生变化，部分任务同时修改多个字段。这个结果是静态数据分析，不等于已经重跑全部修订任务。[统计](evidence/revisions.csv)

**③ 局部可执行反例：Ibex #54。** 使用错误基线、参考修复及 7 份公开历史候选，对每个版本运行 v1.0 与 v1.1 官方测试，再枚举限定输入域中的 **65,536 种 16 位指令编码**，比较译码模块输出。七份历史候选均通过官方测试，但扩展检查后，其中 **4 份候选各有 32 个输入与参考不同**，具体涉及合法 HINT 编码的非法标志误判；另有 1 份在保留编码上不同，不能不加说明地直接判作违反规范。这说明**官方测试 PASS 与更充分的行为一致性不是同一个概念**。[数据](evidence/replay.json) · [脚本](analysis/replay.py) · [分析](report/hwe-bench-v1.1.md)

**④ 验证基础设施自身也会影响判分。** 对 OpenTitan #12505 的断言宏执行两版局部编译对照；对 #21632 的 UART 核和 Scoreboard 运行文件恢复阶段的哈希对照，分析验收中对测试文件的保护与副作用。[局部编译数据](evidence/replay.json) · [文件指纹](evidence/owned.json)

![六个硬件工程的任务组成及模型未解题数](figures/project-results.png)

## 仓库内容

| 路径 | 内容 |
| --- | --- |
| [研究底稿](report/research-notes.md) | 研究思路、任务机制梳理、案例分析与技术讨论 |
| [研究报告](report/hwe-bench-v1.1.md) | HWE-bench v1.1 的数据分析、评测机制与实验诊断 |
| [analysis/](analysis/) | 数据整理、局部复现、比较分析与作图程序 |
| [evidence/README.md](evidence/README.md) | 数据出处、固定版本、复现条件与证据边界 |
| [evidence/replay.json](evidence/replay.json) | Ibex #54 实验、OpenTitan #12505 宏编译结果 |
| [evidence/owned.json](evidence/owned.json) | OpenTitan #21632 评分文件恢复行为的哈希证据 |
| [figures/project-results.png](figures/project-results.png) | 任务分布与两组模型系统的未解任务比较 |

## 对硬件 Agent 数据与评测的启示

将专业工程任务转换为模型训练或评测数据，需要区分**任务有效性、环境可重复性、验证器的正确拒绝/正确接受能力，以及模型具体依赖了哪些工具反馈**。本项目通过原始构造代码研究、任务级复现和验证边界反例，为后续可验证奖励与硬件 Agent 任务质量控制提供依据。

## 证据边界与引用

本研究**没有**声称全量重跑 417 道题、获得最新七套 Agent 的逐题轨迹，或已完成新的 RL 训练环境。Ibex #54 的枚举结果只覆盖所声明的单模块输入域；Ibex #2232 等案例的脚本静态阅读不等于完整核级仿真。对应的证据等级、上游材料和复现条件都在[报告](report/hwe-bench-v1.1.md)与[复现说明](evidence/README.md)中列明。
