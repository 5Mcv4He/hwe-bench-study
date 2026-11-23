# 数据与复现

| 来源 | 本仓库使用方式 |
|---|---|
| [HWE-bench 论文](https://arxiv.org/abs/2604.14709v3) · [基准源码](https://github.com/pku-liang/hwe-bench/tree/7bab86a1018c202395a957f68e918bee4e68f073) | 选材方法、环境适配、补丁提取与离线评分 |
| [v1.0 任务](https://huggingface.co/datasets/henryen/hwe-bench/tree/v1.0) · [v1.1 任务](https://huggingface.co/datasets/henryen/hwe-bench/tree/ef3f000af6abdb4a8b4ba6292069694f4d17f14d) | 两版按 org、repo、PR 号逐一对齐，比较全部顶层字段 |
| [v1.1 发布说明](https://pku-liang.github.io/hwe-bench/v1.1.html) · [成绩原表](https://github.com/pku-liang/hwe-bench/blob/7bab86a/website/scores-v1.1.json) | 作者给出的修订理由、通过数与费用 |
| [实验材料冻结版本](https://github.com/pku-liang/hwe-bench-artifacts/tree/a3682069411b5698f456affb17436da1b821ec76) | 历史模型的真实候选补丁、工具记录和最终评分材料 |

[输入指纹](inputs.json)包含两份 JSONL 的 SHA-256 和所用 Git 文件的 blob 指纹。以下命令在仓库根目录运行。默认把原始材料放到单独的本地目录；原始日志、候选补丁及隐藏脚本由上游提供。研究缓存只供分析与评分使用，未来独立求解时应使用隔离环境。

```bash
python3 analysis/materials.py /tmp/hwe-study-input
python3 analysis/summarize.py /tmp/hwe-study-input
python3 analysis/replay.py /tmp/hwe-study-input
python3 analysis/owned.py /tmp/hwe-study-input
```

统计需要 Python 3.9+。后两条需要 Bash、Git，功能与宏重放另需能从 PATH 调用的 Icarus Verilog 及 vvp（本次为 13.0）。按官方任务脚本约定在临时目录运行 Ibex，用临时工作路径替换固定的 /home/ibex。无需 GPU、模型 API 或整套 Docker 镜像。离线环境可直接读下列结果。

| 文件 | 含义 |
|---|---|
| [projects.csv](projects.csv) · [systems.csv](systems.csv) | 六个工程、七套系统。总成本包括成功与未解任务的支出 |
| [task_labels.csv](task_labels.csv) · [revisions.csv](revisions.csv) | 官方构造标签频数；按实际发生变化的字段组合互斥计数 |
| [replay.json](replay.json) | Ibex #54 的 18 次官方脚本运行、9 组低半字枚举，以及 OpenTitan #12505 的 6 次宏编译；分歧输入为十六进制 |
| [owned.json](owned.json) | UART #21632 的两个上游文件在应用参考修复前、应用后、执行恢复阶段后的 SHA-256 |

图表从 projects.csv 生成。需要 Pillow 和支持中文的字体，可运行 `python3 analysis/figure.py --font /path/to/cjk-font.ttc`。Ibex #2232 正文引用的是数据记录及脚本静态核查。不同案例的证据层级在正文分别标明。
