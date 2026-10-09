# Pianoteq 9 深度逆向与物理建模算法研究路线图 (Roadmap)

> **文档定位**：本路线图定义了在 WSL2 环境下利用 REA 6.1.0 与 Ghidra 12.1.4 对 `binaries/Pianoteq 9.vst3plugin` (58.0 MiB) 开展代码级深度逆向工程的分阶段规划。
> **严格边界**：本项目只负责产出客观的逆向证据、离散数学方程与声学参数规格报告，**严禁向 `devpiano` 复制专有二进制代码**；所有针对 `devpiano` 的吸收、重构与工程落地必须在 `devpiano` 自身的开发迭代中独立进行。

---

## 阶段演进概览

```mermaid
flowchart TD
    subgraph Phase 1: 琴槌击弦动力学
        P1_1[Phase 1-1: RVA锚点与XRefs取证] --> P1_2[Phase 1-2: 参数映射与结构体反编译]
        P1_2 --> P1_3[Phase 1-3: 离散接触力方程重构]
    end

    subgraph Phase 2: 音板阻抗与截止
        P2_1[Phase 2-1: 阻抗参数锚点检索] --> P2_2[Phase 2-2: 滤波器系数生成例程反编译]
        P2_2 --> P2_3[Phase 2-3: 音板网络拓扑与衰减规约]
    end

    subgraph Phase 3: 同音微调与拍频
        P3_1[Phase 3-1: 同音失谐控制链定位] --> P3_2[Phase 3-2: 偏振耦合与相位反相算子反编译]
        P3_3[Phase 3-3: 双阶段衰减生成算法规格]
        P3_1 --> P3_2 --> P3_3
    end

    subgraph Phase 4: 交感共鸣与双音阶
        P4_1[Phase 4-1: 开放弦共鸣触发链路定位] --> P4_2[Phase 4-2: 共鸣池总线分配例程反编译]
        P4_2 --> P4_3[Phase 4-3: 交感共鸣耦合网络规格]
    end

    Phase 1 --> Phase 2 --> Phase 3 --> Phase 4
```

---

## Phase 1: 琴槌非线性击弦动力学定向逆向 (Hammer-String Dynamics)

### 1.1 阶段目标
逆向提取 Pianoteq 9 琴槌毛毡在不同力度下的非线性接触刚度模型、三速度阶梯（Piano 41 / Mezzo 70 / Forte 98）映射逻辑、接触时间 $T_c$ 动态变化机制，以及击弦瞬态打击噪声与木质感平衡滤波器的算法实现。

### 1.2 研究边界与前置条件
- **边界约束**：聚焦于琴槌激励核（Exciter Kernel）本身，不扩散至琴弦全局波动方程求解器；不反编译无关的 GUI 控件与视图组件代码。
- **前置条件**：`binaries/Pianoteq 9.vst3plugin` 完整就绪，REA + Ghidra 12.1.4 冒烟测试正常。

### 1.3 子阶段任务与验收标准

| 子阶段编号 | 任务名称 | 具体任务内容 | 交付产物与验收标准 |
| :--- | :--- | :--- | :--- |
| **Phase 1-1** | 击弦参数 RVA 锚点与 XRefs 交叉引用取证 | 编写提取脚本扫描 `.rdata` 节，精确定位 `hammer_hardness_*`、`hammer_noise_*`、`hammer_tone_*` 字符串的虚拟内存地址（RVA）；调用 REA/Ghidra 提取所有引用该地址的代码指令（XRefs）。 | **验收报告**：`docs/phase1/phase1-1-rva-xrefs-evidence.md`<br>**标准**：记录各字符串的物理偏移、RVA 地址、所有调用方指令地址与调用函数上下文。 |
| **Phase 1-2** | 琴槌参数注册与映射函数定向反编译 | 针对 Phase 1-1 锁定的函数入口，调用 `rea decompile` 提取 C/C++ 伪代码；逆向分析琴槌参数结构体（struct）、MIDI Velocity 到刚度系数 $K(v)$ 的映射逻辑与三速度插值算法。 | **验收报告**：`docs/phase1/phase1-2-hammer-mapping-decompilation.md`<br>**标准**：提供 Ghidra 伪代码原件、字段标注的 C++ 结构体草案、三点拟合数学公式。 |
| **Phase 1-3** | 离散接触力计算核心算法与激振核数学重构 | 追踪参数进入实时音频渲染循环（Process Loop）的关键调用，提取琴槌-琴弦接触受力计算的逐采样点离散方程、毛毡压缩回弹状态判定逻辑与打击噪声带通滤波器拓扑。 | **验收报告**：`docs/phase1/phase1-3-hammer-dynamics-spec.md`<br>**标准**：输出完全脱离专有汇编的纯离散数学方程、状态机定义及技术规约文档。 |

---

## Phase 2: 音板力学阻抗与频带截止滤波器定向逆向 (Soundboard Impedance & Cutoff)

### 2.1 阶段目标
逆向提取 Pianoteq 9 音板机械力学阻抗、截止频率与高低音板分区的离散 DSP 滤波器拓扑结构、极零点系数计算公式以及琴弦振动能量向音板耗散的衰减控制机制。

### 2.2 研究边界与前置条件
- **边界约束**：聚焦于琴桥-音板界面的能量吸收网络与阻抗滤波，不涉及空间房间冲激响应（Reverb Space）与多麦克风拾音延迟阵列。
- **前置条件**：Phase 1 逆向完成，熟悉核心声音引擎的 C++ 类继承体系。

### 2.3 子阶段任务与验收标准

| 子阶段编号 | 任务名称 | 具体任务内容 | 交付产物与验收标准 |
| :--- | :--- | :--- | :--- |
| **Phase 2-1** | 音板阻抗与截止参数锚点检索 | 在 `.rdata` 节定位 `Impedance`、`impedance_cutoff`、`impedance_section`、`impedance_slope` 字符串的 RVA 地址，通过 REA 追踪读取该参数的初始化函数。 | **验收报告**：`docs/phase2/phase2-1-soundboard-anchors-evidence.md`<br>**标准**：锁定负责计算音板阻抗响应的核心类及其虚函数表 (vtable)。 |
| **Phase 2-2** | 阻抗到 DSP 滤波器系数生成例程反编译 | 定向反编译将力学阻抗标量转化为实际 IIR/Biquad/SVF 极零点系数的例程，分析其截止频率与斜率（Slope）的数学映射公式。 | **验收报告**：`docs/phase2/phase2-2-filter-coefficient-decompilation.md`<br>**标准**：完整提取双二次滤波器或状态变量滤波器的连续到离散双线性变换公式。 |
| **Phase 2-3** | 音板能量衰减网络拓扑规约提炼 | 判定其音板网络是 16 模态并联二阶谐振器、级联损耗端还是状态变量波导终止端，提取各频段能量耗散率常数。 | **验收报告**：`docs/phase2/phase2-3-soundboard-acoustic-spec.md`<br>**标准**：生成完整的音板阻抗与高频耗散离散网络结构图与参数计算清单。 |

---

## Phase 3: 同音三弦微失谐与琴桥耦合矩阵定向逆向 (Unison Detuning & Beating)

### 3.1 阶段目标
逆向提取 `unison_width` 与 `Unison Balance` 在同音多弦之间分配失谐量（微音分偏差）的数值规律，以及琴桥端三弦耦合在离散时域产生 Weinreich 双阶段衰减（Prompt Decay 与 Aftersound）的矩阵算子结构。

### 3.2 研究边界与前置条件
- **边界约束**：聚焦单键同音弦（Unison Triplet）内部的力学耦合与非对称拍频，不扩展到跨琴键的全局交感共鸣池。
- **前置条件**：已掌握音板琴桥阻抗边界条件。

### 3.3 子阶段任务与验收标准

| 子阶段编号 | 任务名称 | 具体任务内容 | 交付产物与验收标准 |
| :--- | :--- | :--- | :--- |
| **Phase 3-1** | 同音失谐参数控制链定位 | 检索 `Unison Width`、`Unison Balance`、`unison_width` 字符锚点，定位控制三根弦独立音高偏置与初始相位的代码路径。 | **验收报告**：`docs/phase3/phase3-1-unison-control-chain.md`<br>**标准**：列出三根琴弦失谐因子 $\Delta f_1, \Delta f_2, \Delta f_3$ 的符号引用。 |
| **Phase 3-2** | 偏振耦合与相位反相算子反编译 | 定向反编译同相模态（Prompt 衰减）与反相模态（Aftersound 延音）的能量传递计算代码，逆向三弦振动合成时的振幅加权矩阵。 | **验收报告**：`docs/phase3/phase3-2-beating-matrix-decompilation.md`<br>**标准**：提取 Weinreich 经典偏振耦合在离散采样回路中的矩阵更新算法。 |
| **Phase 3-3** | 同音双阶段衰减生成算法规格提炼 | 结合实验测得的 $\tau_1=0.865\text{s}, \tau_2=5.322\text{s}$ 与 $f_{beat}=3.56\text{Hz}$ 数据，重构出可复现的同音三振荡器衰减规范。 | **验收报告**：`docs/phase3/phase3-3-unison-beating-spec.md`<br>**标准**：输出包含能量权重比、失谐公式与相位初值的独立算法规格书。 |

---

## Phase 4: 全局开放弦交感共鸣与延音共鸣池定向逆向 (Sympathetic & Duplex Resonances)

### 4.1 阶段目标
逆向分析延音踏板踩下（CC64=127）或单键和弦长音时，未制音琴弦与琴桥振动的全局双向耦合能量注入模型，揭示交感共鸣池与双音阶弦区（Duplex Scale）的计算复杂度、共鸣池分配拓扑与能量衰减方程。

### 4.2 研究边界与前置条件
- **边界约束**：聚焦琴弦间的被动激励与阻尼时间，不包含机械踏板踩踏物理杂音模型。
- **前置条件**：完成 Phase 1~3，已建立对单音发声物理全链路的认知。

### 4.3 子阶段任务与验收标准

| 子阶段编号 | 任务名称 | 具体任务内容 | 交付产物与验收标准 |
| :--- | :--- | :--- | :--- |
| **Phase 4-1** | 开放弦共鸣参数锚点与触发链路定位 | 定位 `sympathetic_resonance`、`duplex_scale_resonance`、`resonance_duration_view` 的 RVA 地址，追踪制音器抬起状态下的交感共鸣激活代码。 | **验收报告**：`docs/phase4/phase4-1-sympathetic-anchors-evidence.md`<br>**标准**：确认未击打弦作为被动振荡器加入计算的数据结构定义。 |
| **Phase 4-2** | 共鸣池总线分配例程定向反编译 | 反编译琴桥共振总线（Resonance Bus）与 88 键未制音弦之间能量双向交换的混音与滤波例程。 | **验收报告**：`docs/phase4/phase4-2-resonance-pool-decompilation.md`<br>**标准**：解析共鸣池矩阵维度（是 12 半音腔还是 88 键双向网络）及计算复杂度控制。 |
| **Phase 4-3** | 交感共鸣耦合网络算法规格提炼 | 提取阻尼耗散时间与共鸣强度增益方程，生成规范的交感共鸣与双音阶系统架构规格书。 | **验收报告**：`docs/phase4/phase4-3-sympathetic-system-spec.md`<br>**标准**：输出完整的全局交感共振池物理数学模型与离散实现设计规约。 |

---

## 阶段验收与文档归档准则

1. **严格的子目录归档**：
   各阶段产生的证据日志、反编译伪代码与数学技术报告，必须统一落盘至对应的 `docs/phaseX/` 子目录下，严禁散落在 `docs/` 根目录。
2. **证据链铁律 (Evidence-First)**：
   每份验收报告必须明确包含：
   - **已观测事实 (Observations)**：物理文件偏移、RVA 地址、REA 生成的 Evidence ID、Ghidra 反编译原始行；
   - **推断结论 (Inferences)**：数据结构推导、数学物理公式重构；
   - **待验证未知项 (Unknowns)**：由于内联或反编译缺陷尚未完全证实的细节。
3. **单向赋能边界**：
   本路线图执行过程中，**任何阶段均不得自动修改 `devpiano` 仓库中的代码**。所有验收产物以离散数学方程、结构体伪代码与技术报告的形式提交至本仓库版本控制。
