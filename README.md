# Pianoteq 9 逆向工程与物理建模声学实验室

本仓库是针对 **Modartt Pianoteq 9.1.2** 商业物理建模钢琴软件的逆向工程、参数体系提取与黑盒声学测量实验室。

### 核心定位与目标

本研究专门服务于自有开源 C++20 / JUCE 钢琴合成器项目 [devpiano](../devpiano/) 的高保真声学建模引擎开发。通过 **REA + Ghidra 静态定向反编译证据** 与 **无头自动化黑盒声学实测数据** 的双向验证，提炼出商业级物理建模钢琴的核心声学参数体系、毛毡击弦非线性动力学、琴弦非谐性方程以及同音双阶段衰减机制，为 `devpiano` 提供直接落地的数学物理公式与工程调校基准。

---

## 一、目录结构架构

```
pianoteq9/
├── SUMMARY.md                 # 实验室总决算报告：五大战役收获全景与 devpiano 落地蓝图
├── README.md                  # 本文档：项目架构、工具链与研究成果说明
├── AGENTS.md                  # Agent 协同守则、合规红线与提交规范
├── .omp/                      # OMP Agent 本地配置
│   └── mcp.json               # REA (Reverse Engineer Anything) MCP 服务注册配置
├── binaries/                  # Pianoteq 9 上游原始模块与资源归档
│   ├── Pianoteq 9.exe         # 独立 GUI 应用程序 (59.8 MiB, PE32+ x86-64)
│   ├── Pianoteq 9.vst3plugin  # 核心声学物理建模引擎 (58.0 MiB, pre-Pianoteq-vst3.dll)
│   ├── VST3/                  # VST3 引导加载模块 (Pianoteq 9.vst3, 2.0 MiB)
│   ├── AppData/               # 官方预设 (.fxp)、模型扩展包 (.ptq) 与配置
│   ├── Documentation/         # 官方四语言 HTML 用户手册与声学原理说明
│   └── extra/                 # 辅助工具 (lame.exe MP3 编码器)
├── docs/                      # 核心研究文档、反编译证据与 Clean-Room 技术规格书
│   ├── roadmap.md                                           # 深度逆向与物理建模算法研究路线图 (Phase 1~5 规划全景)
│   ├── pianoteq9_parameter_dictionary_and_acoustic_spec.md  # 物理建模参数字典与声学特性清单
│   ├── acoustic_benchmark_report.md                         # 黑盒声学实测基准报告 (Steinway D 物理常数)
│   ├── phase1/                                              # Phase 1: 琴槌击弦非线性动力学 (已完成)
│   │   ├── phase1-1-rva-xrefs-evidence.md                   # 锚点取证、9处指令级XRefs与.pdata函数边界
│   │   ├── phase1-2-hammer-mapping-decompilation.md          # 96字节红黑树结构、别名网络与三锚点刚度方程
│   │   └── phase1-3-hammer-dynamics-spec.md                  # 逐采样点Verlet力求解器、回弹状态机与C++20规约
│   ├── phase2/                                              # Phase 2: 音板力学阻抗与模态网络 (已完成)
│   │   ├── phase2-1-soundboard-anchors-evidence.md          # 阻抗RVA锚点、25处XRefs与43KB核心求解器
│   │   ├── phase2-2-filter-coefficient-decompilation.md     # 阻抗延音线性缩放律与双线性变换损耗滤波方程
│   │   └── phase2-3-soundboard-acoustic-spec.md             # 长短琴桥断裂补偿、16模态参数表与空间辐射规约
│   ├── phase3/                                              # Phase 3: 同音微失谐与双阶段拍频 (已完成)
│   │   ├── phase3-1-unison-control-chain.md                 # 同音RVA锚点、22处XRefs与槽位33/34控制链
│   │   ├── phase3-2-beating-matrix-decompilation.md          # 1/sqrt(2)投影常数、正交模态矩阵与反投影算子
│   │   └── phase3-3-unison-beating-spec.md                  # 三弦非对称失谐方程、立体声微相展开与C++20规约
│   ├── phase4/                                              # Phase 4: 全局开放弦交感共鸣与双音阶 (已完成)
│   │   ├── phase4-1-sympathetic-anchors-evidence.md          # 交感/双音阶RVA锚点、24处XRefs与制音器3通路模型
│   │   ├── phase4-2-resonance-pool-decompilation.md          # 1104字节12色度控制器、星型总线与反向广播模型
│   │   └── phase4-3-sympathetic-system-spec.md              # 12色度共鸣腔网络、制音器门控与Aliquot扩展规约
│   └── phase5/                                              # Phase 5: 二次方张力非线性与泛音绽放 (已完成)
│       ├── phase5-1-quadratic-blooming-anchors-evidence.md  # 二次方/绽放RVA锚点与核心函数取证
│       ├── phase5-2-nonlinear-mechanics-decompilation.md     # 几何张力调制与惯性膨胀例程反编译
│       └── phase5-3-quadratic-blooming-spec.md              # 纯数学Clean-Room规约与C++20参考实现
├── acoustic_lab/              # 黑盒声学实测实验室
│   ├── midi/                  # 自动生成的标准 SMF 0 格式测试序列 (C1~C7, 三力度, 长延音)
│   ├── audio/                 # 无头批处理渲染导出的 48 kHz / 24-bit 纯物理干音 WAV 采样
│   └── results/               # 信号分析输出产物与拟合数据
└── scripts/                   # 自动化可复现工程脚本
    ├── extract_parameters.py  # 二进制明文字典与文档提取脚本
    └── run_acoustic_experiments.py  # MIDI生成、无头渲染与科学信号分析套件
```

---

## 二、已部署的逆向与分析工具链

本工作区在 WSL2 Ubuntu 环境下完成了完整分析工具链的深度部署与验证：

| 组件 / 工具 | 版本 | 配置与说明 |
| :--- | :--- | :--- |
| **基础操作系统** | Ubuntu 26.04.1 LTS | 内核 `6.18.40.1-microsoft-standard-WSL2`，内存 15 GiB，磁盘空间充足 |
| **Java 运行环境** | OpenJDK 21.0.12.1 | 路径 `/usr/lib/jvm/java-21-openjdk-amd64`，满足 Ghidra 12.1.x 严格要求 |
| **反编译分析引擎** | Ghidra 12.1.4_PUBLIC | 路径 `/opt/ghidra/ghidra_12.1.4_PUBLIC`，Headless 与原生反编译器就绪 |
| **AI 逆向框架** | REA 6.1.0 (`rea-agents`) | 全局安装并注入固定环境变量，`rea doctor` 9 项健康指标全部通过 |
| **科学计算库** | NumPy 2.5.3 / SciPy 1.18.1 | 用于高精度加窗 FFT、分音自动拾取、非线性最小二乘曲线拟合与包络分析 |
| **OMP 协同** | `.omp/mcp.json` | 注册 `rea` 为本地 stdio MCP 服务，支持 Agent 交互式执行反编译与 XRefs 查询 |

---

## 三、核心研究成果摘要

### 1. 物理建模参数体系（详见 `docs/pianoteq9_parameter_dictionary_and_acoustic_spec.md`）

在核心模块 `Pianoteq 9.vst3plugin` 中提炼出未混淆的物理建模参数字典：
- **琴槌击弦层**：三力度阶梯硬度（`hammer_hardness_piano`、`hammer_hardness_mezzo`、`hammer_hardness_forte`）、打击冲量噪声（`hammer_noise_slider`）、瞬态频谱倾角（`hammer_tone_slider`）。
- **音板结构层**：机械阻抗（`Impedance`）、高频粘滞截止频率（`impedance_cutoff`）、低音/高音音板分区（`impedance_section`）。
- **琴弦几何层**：有效弦长（`String Length`，映射非谐性 $B$）、分音频谱轮廓（`Spectrum Profile 1~8`，模拟 1/7 击弦点陷波）。
- **微观调律与共振**：同音微失谐宽度（`unison_width`）、交感共鸣池（`sympathetic_resonance`）、双音阶弦区（`duplex_scale_resonance`）、最高音无制音区界限（`last_damper_slider`）。

### 2. 黑盒声学实测数据（详见 `docs/acoustic_benchmark_report.md`）

以 `NY Steinway D Classical` 模型为基准，实测提取出真实的声学常数：
- **琴弦非谐性**：
  - 低音 $C_1$ 实测 $B \approx 8.52 \times 10^{-4}$（追踪 20 阶分音，模型拟合度 $R^2 = 0.987$）；
  - 高音 $C_6$ 实测 $B \approx 3.22 \times 10^{-3}$（琴弦短硬导致泛音急剧偏离整数倍）。
- **琴槌强非线性刚度**：
  - 击弦起振时间常数高度恒定在 **$32.2\text{ ms}$**；
  - 演奏力度由 Mezzo (70) 跃升至 Forte (98) 时，$>2.5\text{ kHz}$ 高频分音能量激增 **$+12.12\text{ dB}$**，验证毛毡具有高次非线性刚度指数（$p \approx 2.4 \sim 2.8$）。
- **同音三弦双阶段衰减**：
  - 初始同相快衰减时间常数 $\tau_1 = 0.865\text{ s}$（占初始能量 $89.5\%$）；
  - 后期反相慢衰减时间常数 $\tau_2 = 5.322\text{ s}$（占长延音能量 $10.5\%$）；
  - 同音微失谐调制拍频频率为 **$3.56\text{ Hz}$**（周期约 $0.28\text{ s}$）。

---

## 四、对 devpiano 项目的落地指引

根据上述实测成果，对 `devpiano/source/Audio/` 提出以下核心实现方案：

1. **升级琴弦非谐性模型 (`PianoTuning.h`)**：
   在模态合成中将各 Partial 频率绑定到实测曲线：
   $$f_n(k) = n \cdot f_0(k) \cdot \sqrt{1 + B(k) \cdot n^2}$$
   低音区采用 $B(k) \approx 0.0012 \cdot e^{-0.065 \cdot k}$，高音区采用 $B(k) \approx 0.0002 \cdot e^{0.085 \cdot (k - 72)}$。
2. **重构击弦力度高频爆发 (`PianoSynthVoice.h`)**：
   对高阶分音采用超线性力度指数增益：
   $$G_n(v) = G_{n,0} \cdot \left(\frac{v}{70}\right)^{\alpha_n}, \quad \alpha_n = 1.0 + 0.12 \cdot n$$
   当 $v = 98, n > 8$ 时 $\alpha_n > 2.0$，复现强击时的明亮开裂声 (Crack)。
3. **同音三振荡器配平 (`PianoSynthVoice.h`)**：
   将 3 振荡器的能量与衰减常数设置为：
   - 振荡器 1 & 2（同相）：能量权重共 $90\%$，$\tau_1 = 0.865\text{ s}$；
   - 振荡器 3（反相）：能量权重 $10\%$，$\tau_2 = 5.322\text{ s}$，失谐量 $\Delta f = 1.78\text{ Hz}$（激发 $3.56\text{ Hz}$ 呼吸拍频）。

---

## 五、常用操作指南

### 1. 运行 REA 诊断与反编译

```bash
# 验证环境健康状态
rea doctor --provider ghidra

# 对小型目标或函数执行反编译
rea decompile "/root/repos/pianoteq9/binaries/VST3/Pianoteq 9.vst3" GetPluginFactory

# 检索目标中的符号或交叉引用
rea search "/root/repos/pianoteq9/binaries/Pianoteq 9.vst3plugin" hammer_hardness
```

### 2. 重新执行声学实验与数据更新
```bash
# 执行完整实验套件 (生成MIDI -> 无头渲染干音 -> SciPy信号分析)
python3 scripts/run_acoustic_experiments.py
```
