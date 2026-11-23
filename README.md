# 基于 HWE-bench v1.1 的学习、研究与诊断

**一项芯片工程故障，怎样从开发者合并的代码改动，变成 Agent 能独立求解、第三方能自动判分的一道题？**

## 一、真实硬件工程里，开发者究竟修了什么？

HWE-bench 从六个开源工程超过 30,000 个合并请求（Pull Request，PR）出发，最终得到 417 道可执行的修复任务。PR 留下了代码从哪个版本改到哪个版本，相关 Issue 有时记录现象，有时只列后续工作。要把这段历史交给一个能读写仓库、运行工具的模型 Agent，需要还原修复前的工程，写出它应该满足的行为，再做出能判断补丁对错的测试。[论文](https://arxiv.org/html/2604.14709v3) · [v1.1 数据集](https://huggingface.co/datasets/henryen/hwe-bench/tree/ef3f000af6abdb4a8b4ba6292069694f4d17f14d)

v1.1 榜单上的七套模型与工具组合，通过率都超过 90%。这个分数的分母究竟包括什么？要解释它，得先沿着一道题往回追：开发者遇到了什么故障，制题者保留了哪些线索，裁判又能观察到哪些行为。

### 先认识这六个工程：一条指令经过哪些模块？

HWE-bench 包含三套相连的东西。**制题程序**从历史 PR 找到一个可重现的故障；**求解环境**让 Agent 进入修复前的仓库、使用终端并修改文件；**评分程序**接收补丁，在自己的环境里验证结果。理解第一步要先看工程本身。六个工程中有三个 CPU 核、一个片上系统生成器、一个硬件信任根子系统和一个安全片上系统。下面从容易跟踪的一条指令讲起。

**Ibex｜顺序执行的小型 32 位核。** 取指单元按程序计数器（PC）读取指令，译码器辨认操作，寄存器堆提供操作数，加减和比较送到算术逻辑单元，乘除法由相应执行单元完成。读写内存则走访存单元（LSU）。基本配置把取指和译码执行分成两级，也可配置独立写回级。控制状态寄存器（CSR）记录处理器状态；物理内存保护单元（PMP）按地址、操作和权限决定一次访问能否发生。这个小核已经足以提出两类不同的题：当前这笔访问是否应当获准，以及权限改变之后，已经取入流水线的指令怎么办。[Ibex 流水线文档](https://ibex-core.readthedocs.io/en/latest/03_reference/pipeline_details.html)

**CVA6｜面向操作系统的可配置处理器核。** 在典型六级流水线中，前端预测跳转并取指，译码后由发射级检查依赖，记分牌记录哪些在途指令还没返回结果。不同执行单元可以在不同周期完成，提交级按程序顺序使结果生效，这样软件才能看到确定的异常位置。应用级配置还要处理虚拟地址：内存管理单元（MMU）负责地址翻译，指令缓存和数据缓存减少等待。同一份核可以有不同指令扩展和保护配置，规范中的一条规则有时必须按当前配置解释。[CVA6 设计说明](https://docs.openhwgroup.org/projects/cva6-user-manual/03_cva6_design/intro.html) · [项目与配置](https://github.com/openhwfoundation/cva6)

**Caliptra｜主芯片里的硬件信任根。** 内部 VeeR EL2 处理器运行安全固件，ROM 提供启动代码，指令和数据存储器供运行时使用。SHA、HMAC 和椭圆曲线密码单元承担哈希、带密钥的认证和签名相关运算；Key Vault 管理密钥材料，PCR 保存启动度量，Mailbox 负责与主系统交换命令和结果。跟踪一次密钥读取，既要看数据是否到达运算单元，也要看传输中途出错后对外报告什么，以及中间寄存器何时清理。[Caliptra 硬件与设计资料](https://github.com/chipsalliance/caliptra-rtl)

**Rocket Chip｜从核到片上系统的生成器。** Rocket Core 是顺序执行的处理器核。RocketTile 把核、一级缓存及相关地址翻译部件封装起来，生成器再按配置接入其他 Tile、内存、中断控制器、外设或 RoCC 加速器。TileLink 规定模块怎样请求、应答和交换一致性信息，Diplomacy 在生成硬件时协商连接参数。于是同一个工程里既有“一个缓存寄存器复位后取什么值”，也有“如何把两种总线的事务完成语义接起来”。[Rocket 与 RocketTile](https://chipyard.readthedocs.io/en/stable/generators/rocket/) · [Rocket Chip 仓库](https://github.com/chipsalliance/rocket-chip)

**OpenTitan｜多个 IP 共同组成的安全片上系统。** 以 Earl Grey 为例，Ibex 执行固件，ROM、SRAM 和非易失存储器保存代码与数据，密码模块处理加密、认证与密钥操作。生命周期控制器管理设备状态，告警处理器汇集异常，时钟、电源和复位管理器维持各模块的运行条件。SPI、UART、I²C 等外设把芯片接到外部。验证复位管理器时，即使模块在正常时钟下工作正确，还要追问电源异常、某个时钟已经停止时，下游能否进入复位。这说明为什么读整芯片连接图有时比只看出错寄存器更有用。[Earl Grey 顶层设计与模块](https://opentitan.org/book/hw/top_earlgrey/)

**香山｜允许指令乱序执行的高性能核。** 前端预测下一段取指地址，把预测与取指信息记入取指目标队列（FTQ）。后端进行寄存器重命名，消除重复使用同一架构寄存器名造成的假依赖；随后分派到队列，待操作数就绪再送入整数、浮点或访存单元。重排序缓冲区（ROB）记录在途指令，并按程序顺序提交。如果预测落空，部分推测指令要冲刷，前端队列也得根据后端反馈决定哪些条目可回收。具体队列和发射宽度随架构代际变化，解释历史 PR 时要回到当时的版本。[香山设计文档](https://docs.xiangshan.cc/projects/design/en/latest/)

### 每个工程取一道入选题：从现象读到修复

六个工程覆盖处理器核、生成器、片上系统和硬件信任根。下面各取一个入选 PR，从现象对照修复动作。这样才能看清同一个“修 Bug”标签底下，工程师做的是哪些不同的判断。

**Ibex（35 题）｜CPU 进入调试状态后，谁还能拒绝它的内存访问？** Ibex 是一个小型 RISC-V 处理器核。PMP（物理内存保护）通常按地址和权限决定能否取指、读写。在 Debug Mode 下，处理器必须能够访问调试模块所在的地址范围，原检查却可能将合法访问挡住。上游把调试状态和调试地址范围接入 PMP 判断，使范围内的访问获得放行，范围外仍走原有规则。工程师需要先确定例外成立的两个条件，再决定在哪条权限路径上实现它。这也是后文贯穿制题和评分的例子。[PR #2232](https://github.com/lowRISC/ibex/pull/2232)

**Rocket Chip（32 题）｜刚退出复位，指令缓存为什么会报告命中？** 这个片上系统生成器用 Chisel 描述硬件。指令缓存用寄存器 `s2_hit` 保存前一流水级的命中结果。第一次真正的查询还没建立结果时，缺少复位初值就可能让它报出有效响应。参考补丁只改一行，把 `RegEnable(s1_hit, !stall)` 改成 `RegEnable(s1_hit, Bool(false), !stall)`。增加的参数规定了复位后的值；稳态运行时的命中计算可以原样保留。[PR #404](https://github.com/chipsalliance/rocket-chip/pull/404)

**香山（54 题）｜一个队列条目里，部分指令提交、部分被冲刷，这一项算完成了吗？** 香山是高性能乱序 RISC-V 处理器。前端的 FTQ（取指目标队列）按条目记录取指与预测信息，但后端反馈的是指令的提交或冲刷。遇到两种状态混合，按原条件推进指针，可能连带影响预测器更新。补丁重新判断条目中最后一条有效指令是否已经提交，并区分条目提交与指针前移的条件。它和 Rocket #404 都只动一个文件，读懂这个改动却需要跟踪多个周期的状态。[PR #3307](https://github.com/OpenXiangShan/XiangShan/pull/3307)

**Caliptra RTL（16 题）｜最后一个数据拍正常，整次密钥读取就成功了吗？** 在这个硬件信任根子系统中，一次密钥传输要经历多个时钟周期。原逻辑可能让末拍的正常状态覆盖前面出现的错误。上游让错误一旦发生便保留到这次访问结束。同一个 PR 还修正 AES 读取新密钥时对中间暂存寄存器的清零。一个 PR 编号下有两项验收条件；只测错误锁存，无法说明清零也正确。[PR #963](https://github.com/chipsalliance/caliptra-rtl/pull/963)

**OpenTitan（245 题）｜时钟已经停了，复位还能传到下游吗？** 在这个安全片上系统里，故障落在复位管理器的连接关系上。外部上电复位信号有效时，部分时钟可能已经停止，原有复位路径无法可靠覆盖有关内部节点。上游调整复位树，让相关节点从适当的上电复位源获得复位。与 Rocket #404 相比，这里需要验证的是信号能否到达目标模块，检查一个寄存器的复位值还不够。[PR #10732](https://github.com/lowRISC/opentitan/pull/10732)

**CVA6（35 题）｜为什么一项“硬件评测”会要求改 C++？** CVA6 工程包含配套的 Spike 指令集模拟器。模拟器匹配一类扩展指令时，对 `funct7` 字段使用的掩码是 `0xe`，漏查若干编码位，可能把不支持的编码判成匹配。补丁将掩码改为 `0x7e`。修复发生在软件译码逻辑里，正确与否取决于硬件指令编码契约。这道题在数据中归为 `SW_BUG_FIX / SW_FW_LOGIC`。[PR #1482](https://github.com/openhwgroup/cva6/pull/1482)

六个工程的样本权重相差很大。OpenTitan 独占 245/417，约 58.75%。后面读总榜时，这个分母决定了哪些工程的表现对总成绩影响最大。[逐项目统计](https://github.com/5Mcv4He/hwe-bench-study/blob/main/evidence/projects.csv)

### 从原始 Issue 读到 PR：补丁改在哪里，故障又是在哪一层发生的？

上面六道题说明了最终数据里有什么。换一个问法：如果先给工程师看原始现象，**他需要知道什么，才能判断该往哪里改？** 下表按解释故障所需的知识组织。L1–L7 是本文阅读工程案例时使用的七个观察角度，允许一题横跨几层。官方分类器使用的标签和 417 题的频数见下一节。这里同时使用了历史 PR 和已收录任务，因此不能从案例数估计整个题库的类别比例。

| 观察角度 | 原始现象、修复动作，以及两者之间的因果关系 |
|---|---|
| L1 局部表达、掩码与初值 | Rocket 缓存还没有做过一次有效查询，退出复位后却可能送出有效响应。补丁为保存命中的寄存器显式添加假初值。CVA6 的另一个例子也是局部修改，但依据来自指令编码规范：部分位操作指令只检查了位 22–20，使一些保留编码也能匹配。补丁把检查扩大到位 24–20，并处理非法编码。[Rocket Issue #401](https://github.com/chipsalliance/rocket-chip/issues/401) · [PR #404](https://github.com/chipsalliance/rocket-chip/pull/404) · [CVA6 Issue #2276](https://github.com/openhwfoundation/cva6/issues/2276) · [PR #2282](https://github.com/openhwfoundation/cva6/pull/2282) |
| L2 单模块功能 | 检查一个计数器、队列或状态机时，要先说清状态保存到什么时候。Caliptra #963 的一次密钥读取跨越多个数据拍。若寄存器只记最近一拍的状态，后来的成功就会抹去先前的错误；锁存整次传输期间出现的错误，才能正确完成本次事务。[PR #963](https://github.com/chipsalliance/caliptra-rtl/pull/963) |
| L3 跨周期状态 | Ibex 软件已经改写 PMP 权限，取指级却可能保留按旧权限取入的指令。PR 让译码和流水线控制取得所需的 CSR 信息，并在有关写入后冲刷流水线。香山 #3307 同样要处理前后状态不一致，但对象变成了一批已有部分指令提交、部分指令被冲刷的 FTQ 条目。[Ibex Issue #2193](https://github.com/lowRISC/ibex/issues/2193) · [PR #2214](https://github.com/lowRISC/ibex/pull/2214) · [香山 PR #3307](https://github.com/OpenXiangShan/XiangShan/pull/3307) |
| L4 指令集和接口协议 | CVA6 已采取的跳转，目标地址需要两字节还是四字节对齐，取决于是否启用压缩指令扩展 RVC。PR 在禁用 RVC 时额外检查地址位 1。Rocket 的 AHB 问题则要求读懂一次总线传输何时完成：Issue 讨论从设备的完成信号，上游通过引入适配器改动了 11 个文件，留下“修复既有行为”和“补足接口功能”的分类边界。[CVA6 Issue #1300](https://github.com/openhwfoundation/cva6/issues/1300) · [PR #1719](https://github.com/openhwfoundation/cva6/pull/1719) · [Rocket Issue #383](https://github.com/chipsalliance/rocket-chip/issues/383) · [PR #485](https://github.com/chipsalliance/rocket-chip/pull/485) |
| L5 模块协作与软硬件契约 | OpenTitan 的 OTP 控制器分别控制“能否写检查配置”和“能否触发检查”。固件如果用同一个寄存器判断两项操作，就会在其中一项上读错锁定状态。PR 按操作选择对应寄存器，并更新锁定位的写入语义。故障发生在 C 驱动与硬件寄存器契约的交界处。[Issue #4056](https://github.com/lowRISC/opentitan/issues/4056) · [PR #14681](https://github.com/lowRISC/opentitan/pull/14681) |
| L6 芯片系统约束 | OpenTitan 的两个案例分别涉及停钟后的复位传播，以及 SPI 直通模式下发往片外的时钟应何时门控。后者在输出路径引入时钟门控单元。另一例由 OpenTitan 报告、在 Ibex 修复，研究对象是冗余核与寄存器堆的故障检测覆盖。三例分别需要观察复位树、片外接口和系统的故障模型。[复位 Issue #10682](https://github.com/lowRISC/opentitan/issues/10682) · [PR #10732](https://github.com/lowRISC/opentitan/pull/10732) · [SPI Issue #12502](https://github.com/lowRISC/opentitan/issues/12502) · [PR #12505](https://github.com/lowRISC/opentitan/pull/12505) · [Ibex 修订 #2117](https://github.com/lowRISC/ibex/pull/2117) |
| L7 配置与实现能力 | CVA6 的一个 MMU 配置声明了 64 个 PMP 条目，当时的 RTL 最多支持 16 个。工程在配置检查时就可能失败；上游把该配置调为 16。只看报错位置容易误以为要重写保护逻辑，核对参数声明和实现上限即可解释这一行修复。[Issue #2244](https://github.com/openhwfoundation/cva6/issues/2244) · [PR #2248](https://github.com/openhwfoundation/cva6/pull/2248) |

读这些案例可以单独记录三个量。**知识范围**看需要查哪些契约，例如 RVC 配置和指令对齐规范。**时间跨度**看错误至少要经过哪些周期或事件才能显现，例如先改 CSR，再执行已经取入的指令。**定位跨度**看症状与修复位置相隔多远，例如权限表现异常，修复却涉及译码和冲刷控制。三者各自提供信息。另要记录验收目标：Rocket 的一个上游 PR 把重放队列深度从 2 调到 3，希望改善连续访存吞吐。评价这种修改需要测量持续负载下的性能，只核对单次运算结果很难分出差别。[Rocket Issue #3653](https://github.com/chipsalliance/rocket-chip/issues/3653) · [PR #3678](https://github.com/chipsalliance/rocket-chip/pull/3678)

<a id="engineering"></a>

## 二、超过 30,000 个 PR，怎样筛成能制题的候选？

上面六例来自最终数据。回到制题起点，开发者合并 PR 时并没有替评测者准备好题目。HWE-bench 的前八步先处理三件事：取得上下文、识别修复、估计能否复现。上游用 s01–s11 标识各阶段，前一阶段输出的 JSONL（每行一条 JSON 记录）供下一阶段读取。[采集流程源码与逐阶段说明](https://github.com/pku-liang/hwe-bench/tree/7bab86a/hwe_bench/collect)

| 源码阶段 | 谁做、具体做什么 | 这一阶段结束时得到了什么 |
|---|---|---|
| s01 收集 PR | 用 GitHub API 分页读取仓库 PR，给已合并的 PR 补取提交记录 | 包含开发描述、合并状态和提交消息的原始记录 |
| s02 关联 Issue | 检查已关闭、已合并，从标题、正文和提交消息提取 Issue 引用。实现默认调用 DeepSeek，也可以切换为正则匹配 | 一份 PR 对应哪些 Issue 编号。引用能找回上下文，不能单独证明因果 |
| s03 获取 Issue | 对编号去重，用 API 取标题、正文和状态 | 单独的 Issue 记录 |
| s04 合并上下文 | 按编号将 Issue 内容并回对应 PR | 后续分类器能一起读到问题描述和开发者的改动说明 |
| s05 拆补丁 | 取代码差异，按文件路径中的测试标记拆为修复补丁 `fix_patch` 和测试补丁 `test_patch`，丢弃修复部分为空的记录 | 已知修法、随 PR 提交的测试改动，以及变更规模 |
| s06 限制规模 | Python 规则按文件数和增删行数过滤，默认上限分别为 50 和 2,000 | 规模适合继续处理的候选，这一步尚未判断技术难度 |
| s07 判断修了什么 | 分类 Agent 读 PR、Issue 和补丁，输出一级类别、二级类别、置信度和理由 | RTL 修复、软件修复、其他。纯测试、文档、重构、功能新增等按规则归入其他 |
| s08 判断是否适合制题 | Agent 分别评估工程价值、软件问题所需硬件知识、复现线索及仿真成本 | 四个分项和优先级，供制题阶段择取候选 |

**s02 的一个具体陷阱。** Ibex #2232 关联的 #2233 是为这次修改另开的验证待办。读它可以知道工程师想覆盖哪些情况，却不能把它写成最初发现故障的记录。采集器检索引用时承担的是找线索的工作。最终数据还有两条关联 Issue 列表为空；公开实现的筛选规则和发布数据的实测属性，应分别描述。[Issue #2233](https://github.com/lowRISC/ibex/issues/2233) · [关联逻辑](https://github.com/pku-liang/hwe-bench/blob/7bab86a/hwe_bench/collect/s2_filter_by_issues.py)

还可能取到另一份 PR。s03 按编号读取 GitHub 的 Issue 记录，这个接口也能返回 PR。CVA6 #1482 的正文指向前一份 PR #1481；香山 #3307 讨论了 #3303 和 #3086；Caliptra #963 中，明确用来关闭 #977 的改动是补头文件，同一个 PR 还修改了错误锁存和密钥清零。故而读取 `resolved_issues` 后要分别标出原始故障报告、前序 PR、验证待办和只解释部分改动的引用。直接拿这个字段给样本打根因标签，会混合四种关系。[CVA6 #1482](https://github.com/openhwfoundation/cva6/pull/1482) · [香山 #3307](https://github.com/OpenXiangShan/XiangShan/pull/3307) · [Caliptra #963](https://github.com/chipsalliance/caliptra-rtl/pull/963)

**s07 怎样区分 Bug？** 一级标签回答根因落在 RTL 设计、软件还是其他改动。二级标签才回答具体违反了哪种约束。下面是 v1.1 对 417 条任务的实际计数；分类提示中列出了兜底标签，最终数据恰好没有题使用它们。[分类提示](https://github.com/pku-liang/hwe-bench/blob/7bab86a/hwe_bench/collect/s7_instruction.py) · [计数表](https://github.com/5Mcv4He/hwe-bench-study/blob/main/evidence/task_labels.csv)

| 根因类别 | 二级标签与实际题数 | 分类时看的证据 |
|---|---|---|
| RTL 设计，407 题 | 功能逻辑 136、接口协议 100、规格实现 85、配置集成 46、时序同步 40 | 是状态转移算错、握手顺序有误、违反架构规范、接线参数不对，还是时钟复位关系有问题？ |
| 软件，10 题 | 硬件配置 7、软件自身逻辑 2、软硬件交互 1 | 是写错寄存器配置、软件计算本身出错，还是错误处理了中断、状态或握手？ |

分类规则本身也值得核查。Rocket Chip #485 的上游改动引入 AHB 适配器，而纯功能新增按分类规则应属于其他。它的入选提出了一个具体的审查问题：题面把哪种原有行为界定为缺陷？要判定是否误分类，还需对照基线行为、题面与测试，单看 PR 标题无法定论。[PR #485](https://github.com/chipsalliance/rocket-chip/pull/485)

**s08 的高分代表什么？** 四项各取 0–2 分，优先级等于工程价值 × 4，加跨层深度 × 2，加复现线索 × 6，再减仿真成本 × 3。CVA6 #1482 的四项为 1、1、1、0，所以得到 12 分。这里最重的是复现线索：已有明确触发输入和预期行为，会使制题更可行。对于 RTL 类，提示要求跨层深度一项填零，因此不能拿这个零评价香山前后端推理是否复杂。进入 s09 时还可分别设置最低工程价值、最低复现线索等条件；12 分这个例子说明算法如何排序，不能推出一条统一录取线。[打分规则](https://github.com/pku-liang/hwe-bench/blob/7bab86a/hwe_bench/collect/s8_instruction.py) · [下游筛选参数](https://github.com/pku-liang/hwe-bench/blob/7bab86a/hwe_bench/harness/tbgen/prepare_input.py)

### 用什么分母看“落选”？

按论文披露的起点计算，417 个成题样本占最初超过 30,000 个 PR 的比例低于 1.39%。起点里还有文档、功能开发和重构，因而这个比例只能描述**从全部 PR 到可执行任务的压缩程度**。原研究讨论还保留了一组历史查询，以 2026 年 4 月 16 日为截止日，分别按 PR 创建日期与合并日期计数。下表前两列转录该次查询，末列为发布的任务数；本次修订未重新取得带时间戳的搜索快照。读者可用同一条件重查，仓库历史与搜索索引的变动可能使结果不同。[GitHub 查询示例：Ibex 已创建 PR](https://github.com/lowRISC/ibex/pulls?q=is%3Apr+created%3A%3C%3D2026-04-16) · [已合并 PR](https://github.com/lowRISC/ibex/pulls?q=is%3Apr+merged%3A%3C%3D2026-04-16) · [v1.1 发布数据](https://huggingface.co/datasets/henryen/hwe-bench/tree/ef3f000af6abdb4a8b4ba6292069694f4d17f14d)

| 工程 | 截止日以前及当天创建的 PR | 截止日以前及当天合并的 PR | v1.1 任务 |
|---|---:|---:|---:|
| OpenTitan | 22,203 | 19,818 | 245 |
| Ibex | 1,494 | 1,338 | 35 |
| CVA6 | 1,953 | 1,566 | 35 |
| Caliptra | 685 | 555 | 16 |
| 香山 | 5,090 | 4,240 | 54 |
| Rocket Chip | 2,695 | 2,140 | 32 |
| 合计 | 34,120 | 29,657 | 417 |

这两个日期查询描述了仓库的历史规模。要还原作者筛选当时的漏斗，还需取得同一次采集运行的候选 ID，分别计算 s02 后还有多少、s07 标成 OTHER 的有多少、s09 产出测试后在 s10 复验失败的有多少。把 29,657 减去 417，无法算出任何一个阶段淘汰了多少真实 Bug。

### 四个 Ibex 未入选 PR 与一个入选对照

| PR | 上游改动规模（文件 / 增删行合计） | 对照工程记录和最终名单后能作出的判断 |
|---|---:|---|
| [#2216](https://github.com/lowRISC/ibex/pull/2216) | 1 / 2 | 未入选。寄存器堆 A 读端口错接 B 的地址。原讨论在标题、正文、提交说明中均未找到 Issue 编号；按公开 s02 规则，缺少引用就足以阻断这条候选。历史实跑是否停在这里仍待日志确认。 |
| [#2214](https://github.com/lowRISC/ibex/pull/2214) | 3 / 57 | 未入选。PR 明确修复 [#2193](https://github.com/lowRISC/ibex/issues/2193) 描述的 PMP 更新与流水线冲刷问题。已有关联、规模也合格，最终名单无法说明它在哪一步停止。 |
| [#2166](https://github.com/lowRISC/ibex/pull/2166) | 6 / 117 | 未入选。上游修正安全配置中对非预期内存响应的处理，[Issue #2144](https://github.com/lowRISC/ibex/issues/2144) 还提供了复现材料。这是调查后续筛选记录的好样本：已知的工程价值、线索与适中规模都没有自动带来收录。 |
| [#2117](https://github.com/lowRISC/ibex/pull/2117) | 9 / 410 | 未入选。问题在 OpenTitan 提出、在 Ibex 修订。若要检验引用规则能否正确处理跨仓库编号，需要查看该 PR 在 s02 与 s03 的落盘记录。 |
| [#2232](https://github.com/lowRISC/ibex/pull/2232) | 12 / 71 | 入选。上游提交时仍待补验证，最终数据里却有一份能区分错误基线和参考修复的测试。它和 #2166 并列时，最值得追问的是制题阶段对原始验证材料做了什么。 |

因此，“没有成为题”的记录至少要按三种情况取证。纯文档或新功能属于任务范围之外；需硅片测量、长时间性能统计等工作可能超出当前环境能承担的范围；另有候选满足任务定义，但制题或复验没能产出稳定的判据。后两类对应不同的改进办法：一种需要扩展工具环境，另一种值得改进生成与复验流程。要把具体 PR 放入其中一类，应留存它的首个停止阶段、输入记录和日志。

## 三、筛完 PR 以后，怎样把已知修复变成一道题？

走完 s08，制题者知道哪份代码有问题，也知道上游怎样修。还缺两样东西：一个能自动判断修复是否生效的测试，一份让另一位工程师或 Agent 能独立开工的题面。s09–s11 依次交付它们。[上游验证与制题流程](https://github.com/pku-liang/hwe-bench/tree/7bab86a/hwe_bench/harness)

1. **s09 写复现测试。** 制题端按项目、仓库和 PR 号，把 s08 评分与 s05 保存的代码差异合并。制题 Agent 可以看参考补丁，使用该工程的工具链，写出 `tb_script.sh`，需要时补写环境准备脚本。候选测试要在修复前的代码上测出失败，应用参考补丁后用同一测试测出通过。s05 拆出的 `test_patch` 记录上游提交过什么；这里生成的 `tb_script` 才承担评测复现工作，所以没有随 PR 提交测试的 #2232 仍有机会成为题。[测试生成](https://github.com/pku-liang/hwe-bench/tree/7bab86a/hwe_bench/harness/tbgen)
2. **s10 在标准环境复验。** 把候选测试交给统一验证程序，在按项目准备的 Docker 容器内重新执行两种代码状态，解析带名称的测试结果。若脚本有问题，制题方可修正脚本后再验证。s09 是把一个能触发故障的实验做出来，s10 要确认它换到正式评分流程还能重复。交付物包括通过复验的脚本和两侧运行记录。[标准复验](https://github.com/pku-liang/hwe-bench/tree/7bab86a/hwe_bench/harness/verify)
3. **s11 根据已验证的行为写题面。** 题面说明触发条件、观察到的错误、预期行为及受影响功能。复核时既要核对描述是否和测试一致，也要检查有没有泄漏上游补丁或隐藏用例。最后将审核后的 `problem_statement` 连同验证字段写回数据集。这解释了为什么题面放在制题末尾生成：到此时，制题者才知道裁判在环境里实际观察到了什么。[题面生成与复核](https://github.com/pku-liang/hwe-bench/tree/7bab86a/hwe_bench/harness/psgen)

**具体怎样写测试？** Ibex 的 s09 提示给制题者三个按成本递增的选择。先试仓库已有的测试命令，看它能否直接暴露故障；已有框架可用时，在 `simple_system` 等环境中增加一段最小激励程序；两条路都覆盖不到目标行为，才自行搭建测试平台、驱动输入并观察输出。提示要求实际构建或运行被测设计，优先取仿真程序的退出码；若需解析文本，应读取运行日志。读取源码搜索某个信号名无法验证功能。Ibex 提示还把单次编译加仿真的上限定在 20 分钟，最多迭代三轮。这两个限制约束的是这个项目的**测试生成**，不宜套用为榜单上求解 Agent 的统一时间预算。[Ibex 制题提示与三种策略](https://github.com/pku-liang/hwe-bench/blob/7bab86a/hwe_bench/harness/tbgen/prompts/lowRISC__ibex.md)

<a id="environment"></a>

### 跟踪 Ibex #2232：需求、参考解和测试分别给了什么

上游 PR 要求，在处理器已经进入调试模式时，物理内存保护（PMP）应允许对调试模块地址范围的取指、读取与写入。范围外仍遵循原有权限规则。值得注意的是，数据集关联的 Issue #2233 正是为这次改动另开的**验证待办**。它列出了基本读写取指、范围外保护、以及地址与访问类型等组合覆盖三个层次。PR 指出本次提交不含相应验证。因而，仅仅拿到原始补丁，还缺一套可执行的检验手段。[上游 PR #2232](https://github.com/lowRISC/ibex/pull/2232) · [验证 Issue #2233](https://github.com/lowRISC/ibex/issues/2233)

在数据记录里，这道题的标签是 RTL_SPEC，优先级为 17。面向求解者的题面已经交代了触发状态、地址范围、三种访问类型，也指明 PMP 权限检查路径。Agent 的工作仍包括在实际工程里接通信号、实现正确条件并交付可应用的补丁。因为题面已经提供了定位线索，通过这道题能为“按明确契约完成工程修改”提供证据；对“从模糊外部症状独立定位根因”的支持弱一些。[冻结版任务数据](https://huggingface.co/datasets/henryen/hwe-bench/blob/ef3f000af6abdb4a8b4ba6292069694f4d17f14d/hwe_bench_full.jsonl)

**打开隐藏测试，看裁判在什么时刻判错。** 这道题的具名检查叫 `pmp_debug_dm_access`。制题端生成的 shell 脚本组织仿真材料，其中 `tb_pmp_debug_dm.sv` 搭建测试平台，`prim_stubs.sv` 提供仿真所需的原语替身，`sim_main.cpp` 驱动 Verilator 仿真。被测对象仍是实际 Ibex RTL。只看文件名很难理解它到底测了什么，可以按一次执行的顺序读：

1. **进入调试态。** 测试先配置允许启动区访问，让处理器退出复位并在启动区运行；约第 20 个周期，平台发出 `debug_req` 请求，让处理器转去执行调试程序。这一步建立了 PMP 调试例外生效的前提。
2. **检查范围内读写。** 调试程序从调试模块范围内读出事先写入的 `0xCAFEBEEF`，再将读到的值写到范围内另一个位置。结束时检查实际写回值，可以区分“程序走到这里了”和“数据确实经过了受测读写路径”。
3. **检查范围外仍会触发异常。** 程序再访问一个范围外、受保护的地址，预期由异常处理路径报告结果。如果候选补丁简单地在调试态放行一切，前半段读写会成功，却会在这里暴露错误。
4. **收集判据。** 测试平台同时检查结束标志 `result == 1` 和写回值 `stored_value == 32'hCAFE_BEEF`。若范围外访问意外成功，程序给出错误结束标志；周期计数超过 500 仍未完成也会失败。编译和运行输出分别进入 `build.log`、`sim.log`，脚本对外报告具名检查结果。记录里错误基线为 FAIL、参考修复为 PASS；这是上游执行结果，此处按脚本解释其含义。[冻结版任务记录](https://huggingface.co/datasets/henryen/hwe-bench/blob/ef3f000af6abdb4a8b4ba6292069694f4d17f14d/hwe_bench_full.jsonl)

任务的 `f2p_tests` 为这个具名用例保存了三个值：`run = NONE`、`test = FAIL`、`fix = PASS`。因此可以核对作者记录了哪一项先失败、后通过，而不是由一个总退出码猜测。测试台直接实例化了 `ibex_core`；若另一份实现改动了这个边界，还需要区分编译接口不兼容和功能断言失败。

这个测试同时问了两个方向的问题：应当放行的访问是否成功，应当拦截的访问是否仍被拦截。它覆盖了一次具体配置与执行路径；Issue 中希望覆盖的所有地址边界和权限组合，仍需逐一检查。

| 从材料里可以确认 | 证据的边界 |
|---|---|
| 上游提出了完整验证愿望，包括组合覆盖 | Issue 中的计划不能充当实际覆盖率报告 |
| 任务记录保存同名检查在测试侧 FAIL、参考修复侧 PASS | 这是作者保存的运行结果。本项目核对了脚本及记录，本轮未重跑 #2232 的完整核级仿真 |
| 实际脚本检查具体配置、地址、访问与终止条件 | 其他地址边界、权限组合、不同实现接口的兼容性需要另外验证 |

### 谁拿到题面，谁拿到答案，模型最后交付什么？

JSONL 的一行把材料装在一起，执行时再分给不同的角色。工程身份与基线提交确定“在哪份代码上做”；`problem_statement` 告诉 Agent “应出现什么行为”；`fix_patch` 给制题者一份已知修复；`tb_script` 给裁判可执行的判据；`f2p_tests` 记录哪些具名检查在错误版本失败、在参考修复上通过（Fail-to-Pass）。Docker 镜像固定仓库和工具链，某些题还有准备脚本。不同工程的仿真器与验证依赖不同，题号相同也必须核对快照与测试版本。[测试生成](https://github.com/pku-liang/hwe-bench/tree/7bab86a/hwe_bench/harness/tbgen) · [构造验证](https://github.com/pku-liang/hwe-bench/tree/7bab86a/hwe_bench/harness/verify) · [题面生成](https://github.com/pku-liang/hwe-bench/tree/7bab86a/hwe_bench/harness/psgen)

从发布数据到一次试次，适配器会把同一条记录拆成不同用途的文件：

| 文件或位置 | 在哪一步使用 | 对求解、评分有什么作用 |
|---|---|---|
| `instruction.md` | Agent 开工时 | 展示经复核的行为要求。求解者从这里理解要改什么 |
| `task.toml`、`environment/` | Harbor 启动试次时 | 描述任务与环境，使求解者在指定的工程快照和工具链中工作 |
| `solution/solve.sh` | 参考解路径 | 供框架运行已知解时使用。独立求解时应隔离参考解 |
| `tests/test.sh` | Harbor 收尾时 | 在这个适配器里负责从工作树提取候选补丁。名字里虽有 test，这一步产生的占位分数还不是功能判定 |
| `tb_script` 与评分日志 | 独立 evaluator 收到补丁后 | 将候选改动应用到干净工程，运行隐藏测试，从具名结果判断是否通过 |

以 #2232 为例，适配器把题面写入 `instruction.md`。求解 Agent 面对的是修复前的工程与可用工具。它查找 PMP 模块、追踪调试状态和地址判断、编辑代码，可以执行自己的检查。这里描述的是任务允许的求解路径；某个模型在某次试验中实际查了什么，需要看那次的工具记录。交付物是工作树相对基线的差异，独立评分器才有隐藏用例来检验它。

```mermaid
flowchart TD
    P["上游 PR、关联 Issue、工程快照"] --> B["构造方生成题面与测试"]
    B --> I["题面与待修工程"]
    B --> H["隐藏测试"]
    P --> R["上游参考修复"]
    H --> V["基线失败、参考修复通过"]
    R --> V
    I --> A["Agent 查代码、调用工具、编辑文件"]
    A --> D["Harbor 提取候选补丁"]
    D --> E["独立评分环境重新应用补丁"]
    V --> E
    E --> S["具名测试结果与任务分数"]
```

这里最容易读错的是两个 `test` 的含义。Harbor 是调度 Agent 和管理试次的运行框架。它的适配模板在任务结束时相对镜像基线提取 Git 差异；这个模板写入的 `reward.txt` 为占位值。随后桥接程序收集非空补丁，外部 evaluator 在干净评分环境运行真正的隐藏测试，解析具名结果。Agent 在自己的终端看到“编译成功”、Harbor 拿到了补丁、外部评测判定通过，是三个不同事件。只有区分它们，才能解释一份空提交、一条工具错误和一个功能断言各自说明什么。[Harbor 收补丁模板](https://github.com/pku-liang/hwe-bench/blob/7bab86a/hwe_bench/harness/harbor/templates/test.sh.j2) · [桥接程序](https://github.com/pku-liang/hwe-bench/blob/7bab86a/hwe_bench/harness/harbor/verify_bridge.py) · [评分入口](https://github.com/pku-liang/hwe-bench/blob/7bab86a/hwe_bench/harness/evaluator.py)

具体到文件，Harbor 收尾时暂存工作树相对基线的改动，将差异写入 `model_patch.diff`，同时记录空补丁或补丁行数。模板退出时给 `reward.txt` 写入固定值 0。桥接程序把收集到的补丁整理为 `patches.jsonl`，再由 evaluator 应用各题补丁、运行隐藏脚本并生成报告。这个分工解释了为何不能直接用 Harbor 的 0 训练模型：它在这里表示收集流程的约定，真实的功能反馈来自后续离线评分。还有一项独立的实验条件：固定版本的任务模板把网络模式设为 `public`。隐藏解的分发方式和求解时能访问哪些外部资料需要分别审计；这个配置本身不能证明某次求解查阅过上游答案。[收集模板](https://github.com/pku-liang/hwe-bench/blob/7bab86a/hwe_bench/harness/harbor/templates/test.sh.j2) · [任务配置](https://github.com/pku-liang/hwe-bench/blob/7bab86a/hwe_bench/harness/harbor/templates/task.toml.j2) · [桥接程序](https://github.com/pku-liang/hwe-bench/blob/7bab86a/hwe_bench/harness/harbor/verify_bridge.py)

<a id="revision"></a>

## 四、v1.1 改动了哪些判断条件

逐字段对齐两份完整数据后，417 个任务标识一一对应。209 题所有顶层字段相同；158 题仅改测试，20 题仅改题面，29 题同时改测试和题面，1 题连参考修复一起改。按字段统计即 **188 份测试、50 份题面、1 份参考修复**。测试的文本发生变化，数据里保存的基线和参考验证结果字段却相同。作者在发布说明中报告重新验证了修订后的测试；确认这一声明的逐题执行证据，还需要新脚本对应的运行日志。[互斥计数表](https://github.com/5Mcv4He/hwe-bench-study/blob/main/evidence/revisions.csv) · [作者发布说明](https://pku-liang.github.io/hwe-bench/v1.1.html)

| 修订解决什么问题 | 用什么区分“读到修改”和“验证了效果” |
|---|---|
| OpenTitan #12505：测试提供的断言宏只接受某些调用形式，合理的工程写法可能在预处理就失败 | 固定调用，分别用两版测试宏编译。两参调用均通过，三参、四参旧版失败新版通过。这个局部实验验证了签名兼容性，完整 SPI 功能仍需芯片级环境验证。[编译结果](https://github.com/5Mcv4He/hwe-bench-study/blob/main/evidence/replay.json) |
| Ibex #332：只观察挂起请求的地址，还会漏掉分支后交给处理器的指令流错误 | 新测试增加返回数据与请求地址的对应检查，并检查重定向后的下游交付。这里确定的是脚本覆盖范围的改变。固定候选补丁在两版上的成对判定仍待实跑。[上游说明](https://pku-liang.github.io/hwe-bench/v1.1.html) |
| OpenTitan #21632：评分前恢复受保护的验证文件，可以清除求解者留下的测试改动 | 对真实 UART 核与验证记分板应用参考修复，再执行恢复阶段。新版保留了核的改动，却把记分板恢复为基线。若想评价设计与配套验证的共同交付，需要给后者单设验收。[文件指纹实验](https://github.com/5Mcv4He/hwe-bench-study/blob/main/evidence/owned.json) |

## 五、七组系统的高分测出了什么

![六个工程的任务数与 Claude 和 DeepSeek 两套系统各自的未解数](https://raw.githubusercontent.com/5Mcv4He/hwe-bench-study/main/figures/project-results.png)

图左解释总体成功率的权重，图右解释差距集中在哪里。OpenTitan 占了过半题目，另外五个工程的模型表现容易被总分稀释。例如在 Ibex 上，Claude 与 DeepSeek 相差 5 题，但分母只有 35，换成通过率便相差 14.29 个百分点。[作图数据](https://github.com/5Mcv4He/hwe-bench-study/blob/main/evidence/projects.csv)

| 模型与工具系统 | 通过 / 417 | 通过率 | 官方总成本（美元） |
|---|---:|---:|---:|
| Claude Opus 5.5 · Claude Code | 413 | 99.04% | 5,110.22 |
| GPT-6.1 Sol · Codex CLI | 405 | 97.12% | 197.27 |
| GPT-6 Astra · Codex CLI | 405 | 97.12% | 1,094.72 |
| GPT-6 Sol · Codex CLI | 390 | 93.53% | 304.23 |
| Kimi K3.1 Pro · Kimi Code | 386 | 92.57% | 483.17 |
| DeepSeek V4.1 Flash 1017 · DeepSeek Harness | 386 | 92.57% | 112.53 |
| GLM 5.3 · OpenCode | 377 | 90.41% | 1,465.25 |

前六组公布的推理档位均为各厂商的 max，GLM 一行未列。DeepSeek 和 Claude 同时更换了基础模型和 Harness（提供工具、上下文管理和执行循环的软件）。在 Caliptra 的 16 题上七组全过，此时最终通过率已无法给这些系统排序；而在 OpenTitan，成绩仍有差异。Claude 的四个未解都在 OpenTitan，两系统共同未解的题数只能从分项成绩约束到 **0 至 4**。截至本次检查，官方材料没有这两个最新组合的完整逐题轨迹。报告不能把 27 题净差解释为某个模型不懂协议，也不能把价格差换算成验证能力差。[官方分数原表](https://github.com/pku-liang/hwe-bench/blob/7bab86a/website/scores-v1.1.json) · [公开实验材料](https://github.com/pku-liang/hwe-bench-artifacts/tree/a3682069411b5698f456affb17436da1b821ec76)

各系统在六个工程上通过的题数如下。列标题给出各自分母。同为 405 题，GPT-6 Astra 在 OpenTitan 多通过 1 题，GPT-6.1 Sol 在 Rocket Chip 多通过 1 题；相同总分可以来自不同的项目表现。[官方逐项目成绩](https://github.com/pku-liang/hwe-bench/blob/7bab86a/website/scores-v1.1.json)

| 系统 | OpenTitan / 245 | Ibex / 35 | CVA6 / 35 | Caliptra / 16 | 香山 / 54 | Rocket Chip / 32 |
|---|---:|---:|---:|---:|---:|---:|
| Claude Opus 5.5 | 241 | 35 | 35 | 16 | 54 | 32 |
| GPT-6.1 Sol | 241 | 34 | 34 | 16 | 52 | 28 |
| GPT-6 Astra | 242 | 34 | 34 | 16 | 52 | 27 |
| GPT-6 Sol | 229 | 34 | 34 | 16 | 50 | 27 |
| Kimi K3.1 Pro | 231 | 31 | 33 | 16 | 47 | 28 |
| DeepSeek V4.1 Flash 1017 | 231 | 30 | 34 | 16 | 47 | 28 |
| GLM 5.3 | 227 | 27 | 33 | 16 | 45 | 29 |

### 一个实际反例：Ibex #54 的七份 PASS

#54 修正 RISC-V 压缩指令译码。部分编码是合法的 HINT，即允许硬件忽略其操作效果的提示指令；将其标记为非法会引起不同的架构行为。这道题的官方脚本用五个输入验证相关指令。问题在于，其中的移位例子覆盖了移位量为零，却没有同时覆盖目的寄存器为 x0 的那个交点。[上游 PR](https://github.com/lowRISC/ibex/pull/54) · [RISC-V 压缩指令规范](https://docs.riscv.org/reference/isa/v20260120/unpriv/c-st-ext.html)

**本项目实际执行**：取错误基线、参考修复和七份公开历史候选，对每份设计分别运行 v1.0 与 v1.1 的官方脚本。这道题两版脚本相同。再固定输入高 16 位为零，枚举低 16 位的 65,536 种取值，比较是否为压缩指令、非法标志以及展开后的指令三个输出。错误基线在两版均失败，参考及七份候选均通过。扩大输入后出现以下区别。

| 历史候选 | 与参考输出不同的输入数 | 如何解释 |
|---|---:|---|
| GPT-5.4、DeepSeek V3.2 | 各 0 | 本轮限定输入域和三个观测量上全部一致 |
| GPT-5.6 Sol、Claude Opus 4.6、Claude Sonnet 4.6、Qwen3.6 Plus | 各 32 | 都把一组合法提示编码判为非法，其中 0x0002 同时满足零移位量与目的寄存器 x0 |
| Kimi K2.5 | 1 | 改变了保留编码 0x6101 的既有行为。此项是与项目基线及参考实现的差异，规范对保留编码的要求应单独解释 |

历史 GPT-5.6 Sol 的自建测试把目的寄存器从 1 开始遍历，跳过了 x0。因而这里能指出一个实际遗漏的输入，以及一条解释它为何未在自测中暴露的工具记录。这能诊断这一次提交的自测范围，也给出改题的具体办法。七份候选来自历史实验，不能充当上表最新七套系统在 #54 上的表现。穷举也限于这个小译码模块和所声明的输入域。[七份候选的输入定位](https://github.com/5Mcv4He/hwe-bench-study/blob/main/evidence/inputs.json) · [运行结果及反例](https://github.com/5Mcv4He/hwe-bench-study/blob/main/evidence/replay.json) · [GPT 历史试次](https://github.com/pku-liang/hwe-bench-artifacts/tree/a368206/jobs/ibex/gpt5.6-sol/pr-54)

<a id="limits"></a>

## 六、从分数回到能力与训练数据

| 想评价的能力 | 现有证据能支持到哪里 | 后续怎样增强判别力 |
|---|---|---|
| 理解规格与边界 | #2232 检查范围内和范围外的行为，#54 证明故障可藏在两个条件的交点 | 对明示的条件做交叉覆盖，加入只修对一半的候选，确认测试能拒绝它们 |
| 定位根因、利用反馈 | 题面能提示故障子系统。最终通过的一行分数无法说明 Agent 怎样找到文件或如何使用仿真反馈 | 保存每次运行可见的题面、工具退出码、所跑用例、补丁与终止原因，再按相同配置对照 |
| 修复正确性与回归 | 411 题只登记一个具名 Fail-to-Pass 检查，其内部仍可能包含许多输入。全库登记的 Pass-to-Pass 名单为空 | 区分“修复目标行为”和“保留既有行为”，各自记录输入族、结果和失效信号 |
| 工程交付与验证策略 | #21632 显示合法的验证改动可能在评分前被恢复。二元分数难以衡量候选自建测试的质量 | 独立验收设计；另用正确设计与已知错误设计检验候选测试能否分别接受和拒绝 |

如果把这些题用于后训练，首先要知道哪一种反馈值得模型学习。#54 中，遗漏 x0 的候选和考虑了 x0 的候选得到同样的官方通过信号。沿用这一个信号，训练过程就无法从这道题区分两种行为。加入合法边界输入和应保持原状的邻近编码后，才有可执行的判据。**这提供了任务设计的依据；至于训练之后能否迁移到其他译码器、寄存器属性或有状态协议，需要留出新任务验证。**

## 七、初步结论与下一步实验

读完这条链，我对构建专业 Agent 测试有了一个可以实际执行的判断顺序。先从真实工程记录中写清楚预期行为，再保存可复现的错误基线，以参考修复校准验证器。随后给求解者独立环境，从最终工程状态提取补丁，在干净环境里判分。最后再用另外的正确解、部分修复和反例审查验证器本身。HWE-bench 的价值在于把这些层接到了真实硬件工程上；v1.1 的修订和 #54 的局部验证说明，校准之后仍然有检查覆盖的工作可做。

下一项最有信息量的实验是 **Ibex #332 的八格固定补丁重放**。固定错误基线、上游参考修复、两份已有历史候选，分别送入旧版和新版测试，在首次分歧的时钟周期对齐请求地址、授权、返回与实际交付的指令。这样只改变测试版本，就能检验新检查究竟多识别出了哪一种故障。这个实验尚待执行，当前初稿的独立执行范围是 #54 的功能枚举、#12505 的宏编译和 #21632 的文件恢复。[复现说明与已有结果](#reproduction)

### 哪些研究问题已有材料，哪些还需要实验？

| 研究问题 | 目前可以核对的结果 | 进一步下结论需要的材料 |
|---|---|---|
| 七组系统在哪些题上分出高低？ | v1.1 总分、成本和逐项目计数；历史 #54 候选有可重放的补丁 | 同一版题面、隐藏测试、工具配置下的逐题结果与轨迹。成功和失败各取实例如实记录第一次有效定位、修改、自测与退出原因 |
| 哪些修订真正改变了裁判的判断？ | 208 道题发生字段变化；修订说明、宏编译及文件恢复各自提供了不同层级的证据 | 用固定候选在两版测试上成对重放，保存首个分歧和可观察信号。#332 是前述待做实验 |
| 哪种真实故障在入选过程中消失？ | 六仓历史规模与四个 Ibex 缺席案例，部分上游已有明确问题与复现线索 | 同一次采集的逐阶段记录及失败日志，区分范围外、环境受限与制题失败 |
| 题目是否覆盖工程所需的理解深度？ | 已统计官方标签并建立从代码、周期到系统配置的案例对照 | 给每题另标知识范围、时间跨度、定位跨度；保留标注所据 Issue、Diff 和分歧意见，再按工程与模型结果交叉分析 |

<a id="reproduction"></a>

## 八、数据与复现

| 来源 | 本仓库使用方式 |
|---|---|
| [HWE-bench 论文](https://arxiv.org/abs/2604.14709v3) · [基准源码](https://github.com/pku-liang/hwe-bench/tree/7bab86a1018c202395a957f68e918bee4e68f073) | 选材方法、环境适配、补丁提取与离线评分 |
| [v1.0 任务](https://huggingface.co/datasets/henryen/hwe-bench/tree/v1.0) · [v1.1 任务](https://huggingface.co/datasets/henryen/hwe-bench/tree/ef3f000af6abdb4a8b4ba6292069694f4d17f14d) | 两版按 org、repo、PR 号逐一对齐，比较全部顶层字段 |
| [v1.1 发布说明](https://pku-liang.github.io/hwe-bench/v1.1.html) · [成绩原表](https://github.com/pku-liang/hwe-bench/blob/7bab86a/website/scores-v1.1.json) | 作者给出的修订理由、通过数与费用 |
| [实验材料冻结版本](https://github.com/pku-liang/hwe-bench-artifacts/tree/a3682069411b5698f456affb17436da1b821ec76) | 历史模型的真实候选补丁、工具记录和最终评分材料 |

[输入指纹](https://github.com/5Mcv4He/hwe-bench-study/blob/main/evidence/inputs.json)包含两份 JSONL 的 SHA-256 和所用 Git 文件的 blob 指纹。以下命令在仓库根目录运行。默认把原始材料放到单独的本地目录；原始日志、候选补丁及隐藏脚本由上游提供。研究缓存只供分析与评分使用，未来独立求解时应使用隔离环境。

```bash
python3 analysis/materials.py /tmp/hwe-study-input
python3 analysis/summarize.py /tmp/hwe-study-input
python3 analysis/replay.py /tmp/hwe-study-input
python3 analysis/owned.py /tmp/hwe-study-input
```

统计需要 Python 3.9+。后两条需要 Bash、Git，功能与宏重放另需能从 PATH 调用的 Icarus Verilog 及 vvp（本次为 13.0）。按官方任务脚本约定在临时目录运行 Ibex，用临时工作路径替换固定的 /home/ibex。无需 GPU、模型 API 或整套 Docker 镜像。离线环境可直接读下列结果。

| 文件 | 含义 |
|---|---|
| [projects.csv](https://github.com/5Mcv4He/hwe-bench-study/blob/main/evidence/projects.csv) · [systems.csv](https://github.com/5Mcv4He/hwe-bench-study/blob/main/evidence/systems.csv) | 六个工程、七套系统。总成本包括成功与未解任务的支出 |
| [task_labels.csv](https://github.com/5Mcv4He/hwe-bench-study/blob/main/evidence/task_labels.csv) · [revisions.csv](https://github.com/5Mcv4He/hwe-bench-study/blob/main/evidence/revisions.csv) | 官方构造标签频数；按实际发生变化的字段组合互斥计数 |
| [replay.json](https://github.com/5Mcv4He/hwe-bench-study/blob/main/evidence/replay.json) | Ibex #54 的 18 次官方脚本运行、9 组低半字枚举，以及 OpenTitan #12505 的 6 次宏编译；分歧输入为十六进制 |
| [owned.json](https://github.com/5Mcv4He/hwe-bench-study/blob/main/evidence/owned.json) | UART #21632 的两个上游文件在应用参考修复前、应用后、执行恢复阶段后的 SHA-256 |

图表从 projects.csv 生成。需要 Pillow 和支持中文的字体，可运行 `python3 analysis/figure.py --font /path/to/cjk-font.ttc`。Ibex #2232 正文引用的是数据记录及脚本静态核查。不同案例的证据层级在正文分别标明。
