# Pianoteq 9 物理建模参数字典与声学特性清单

> **文档定位**：本清单基于 WSL2 环境下从真实 `Pianoteq 9.vst3plugin` (58.0 MiB) 二进制中提取的明文参数字典、导出符号与官方用户手册声学定义，结合 `devpiano` 当前的物理建模引擎架构（`PianoSynthVoice.h`, `AcousticSnapshot.h` 等）整理而成。旨在为 `devpiano` 高保真物理建模钢琴音源提供可直接对齐的物理参数体系、声学公式与架构升级参考。

## 一、Pianoteq 9 二进制声学参数架构全景

在 `Pianoteq 9.vst3plugin` 中，Modartt 采用了**结构化、三层递进**的物理建模参数体系：
1. **全局乐器架构层 (Design Level)**：宏观物理尺寸与材质特性（音板阻抗、截止频率、弦长/非谐性、双音阶弦区）。
2. **整音与发声动力学层 (Voicing Level)**：琴槌冲击与相互作用（三速度阶梯琴槌硬度、击弦点频谱轮廓、击弦瞬态噪声与木质平衡）。
3. **微观调律与耦合共振层 (Tuning & Resonance Level)**：同音三弦独立失谐、交感共振矩阵、八度拉伸、微调律与踏板机构。

### 1. 琴槌击弦与动力学 (Hammer & Strike Dynamics)

| 参数标识符 (Parameter Identifier) | 中文名称与物理概念 | 典型调节范围 | 物理声学作用与听感影响 |
| :--- | :--- | :--- | :--- |
| `hammer_hardness_piano` | Piano 力度下琴槌硬度 (MIDI Vel ≈ 41) | 0.10 ~ 2.50 | 控制轻弹时的接触时间与高频注入，毛毡较软，音色温和 |
| `hammer_hardness_mezzo` | Mezzo 力度下琴槌硬度 (MIDI Vel ≈ 70) | 0.10 ~ 2.50 | 中等力度下毛毡刚度，标准音色基准 |
| `hammer_hardness_forte` | Forte 力度下琴槌硬度 (MIDI Vel ≈ 98) | 0.10 ~ 2.50 | 强奏时毛毡极度压实，非线性接触时间极短，激发大量高阶金属分音 |
| `hammer_noise_slider` | 击弦打击噪声 (Hammer Noise) | -40 dB ~ +12 dB | 琴槌木核撞击琴弦的初始宽带打击冲量，赋予近场敲击感 |
| `hammer_tone_slider` | 击弦音色平衡 (Hammer Tone) | -2.0 ~ +2.0 | 调节初始撞击瞬态的频谱倾角（暗沉木质感 vs 明亮金属冲击） |
| `hammer_tine_noise` | 电钢/簧片琴槌噪点 (Tine/Reed Noise) | 0% ~ 100% | 用于 Rhodes/Wurlitzer 等电声模型的簧片初始撞击噪波 |
| `Hammer Stickiness` | 毛毡表面回击粘滞阻尼 | 0% ~ 100% | 琴槌与弦脱离时的微阻尼摩擦，影响起振极初期的瞬态衰减 |

### 1. 音板与声学辐射 (Soundboard & Acoustic Radiation)

| 参数标识符 (Parameter Identifier) | 中文名称与物理概念 | 典型调节范围 | 物理声学作用与听感影响 |
| :--- | :--- | :--- | :--- |
| `Soundboard Impedance` | 音板机械力学阻抗 (Impedance) | 0.20 ~ 3.00 | 音板对琴弦振动的反作用阻力。阻抗越大，能量泄漏越慢，衰减越长；阻抗越小，起始响度大但衰减极速 |
| `impedance_cutoff` | 音板阻抗高频截止频率 (Cutoff) | 500 Hz ~ 10 kHz | 音板内部粘滞耗散的高频截止点。高于该频率的分音被音板吸收极快 |
| `impedance_section` | 低音/高音音板分区特性 | Curve / Multi-break | 区分长琴桥（中高音）与短琴桥（低音）向音板传导的阻抗差异 |
| `Lid Position` | 琴盖开合度 (Full / Half / Closed) | 0° ~ 45° | 影响直达声与早期反射声的辐射方向、高频空气吸收与箱体共鸣 |

### 1. 琴弦特性与非谐性 (String & Inharmonicity)

| 参数标识符 (Parameter Identifier) | 中文名称与物理概念 | 典型调节范围 | 物理声学作用与听感影响 |
| :--- | :--- | :--- | :--- |
| `String Length` | 有效琴弦长度 (String Length) | 0.80 m ~ 3.50 m | 物理弦长直接决定非谐性系数 B：短琴弦 B 值极大（音色如钟声），长琴弦 B 极小（泛音规整和谐） |
| `String Tension` | 琴弦张力 (String Tension) | N / kg | 结合弦长与线密度决定基频与高动态强击下的张力调制音高微漂移 (Pitch Glide) |
| `Spectrum Profile (Partials 1~8)` | 分音频谱轮廓 (8 阶分音增益) | -24 dB ~ +12 dB | 独立微调前 8 阶分音幅度，模拟击弦点几何位置 (1/7~1/8) 引起的梳状滤波陷波特性 |

### 1. 同音多弦与非对称拍频 (Unison Tuning & Beating)

| 参数标识符 (Parameter Identifier) | 中文名称与物理概念 | 典型调节范围 | 物理声学作用与听感影响 |
| :--- | :--- | :--- | :--- |
| `unison_width` | 同音弦失谐宽度 (Unison Width) | 0.0 ~ 10.0 Cent / Hz | 三根同音弦之间的频率微差，决定同音衰减过程中的非对称拍频周期 |
| `Unison Balance` | 同音弦能量与相位平衡 | 0.0 ~ 1.0 |  Weinreich 模型中垂直偏振与水平偏振、同相模态与反相模态的能量分配，产生双阶段衰减 (Two-stage Decay) |

### 1. 交感共振与双音阶 (Sympathetic & Duplex Resonances)

| 参数标识符 (Parameter Identifier) | 中文名称与物理概念 | 典型调节范围 | 物理声学作用与听感影响 |
| :--- | :--- | :--- | :--- |
| `sympathetic_resonance` | 弦间交感共鸣强度 (Sympathetic Resonance) | 0.0 ~ 2.0 | 开放弦（未被制音）在琴桥振动激励下的全局耦合振荡（Bartók 效果） |
| `duplex_scale_resonance` | 双音阶共鸣强度 (Duplex Scale) | 0.0 ~ 2.0 | 琴桥后无制音弦段 (Aliquot/Duplex) 的高频共振，提供明亮通透的空气感高频 |
| `resonance_duration_view` | 共振衰减持续时间 | 0.2 s ~ 10.0 s | 交感共鸣在共振池内的能量耗散时间 |

### 1. 制音器与踏板机械机构 (Dampers & Pedals)

| 参数标识符 (Parameter Identifier) | 中文名称与物理概念 | 典型调节范围 | 物理声学作用与听感影响 |
| :--- | :--- | :--- | :--- |
| `damper_duration_slider` | 制音器下落阻尼时间 (Damper Duration) | 10 ms ~ 500 ms | 松开琴键后，毛毡制音器压在振动琴弦上的能量吸收速度 |
| `damper_position_slider` | 制音器触弦物理位置 | 0.0 ~ 1.0 | 毛毡接触琴弦的相对节点位置，决定高阶分音与低阶分音的先后熄灭次序 |
| `damper_noise_slider` | 制音器释放与回落机械声 | -40 dB ~ 0 dB | 制音器离开与撞击琴弦时的轻微毛毡杂音 (Felt Thump) |
| `damper_vel_threshold` | 弱击不离弦速度阈值 | MIDI 1 ~ 30 | 极轻触键时制音器不完全抬起的物理判定 |
| `last_damper_slider` | 最高音无制音区界限 (Last Damper) | Key #65 ~ #73 (F6~C7) | 三角钢琴最高音区天然无制音器，始终处于自由振动与交感共振状态 |
| `pedal_noise_slider` | 踏板踏下与回弹机械杂音 | -40 dB ~ 0 dB | 踏板杠杆驱动全体制音器横梁升降时的机械轰鸣声 |

## 二、官方文档声学原语深度梳理 (Acoustic Specifications)

根据 `Documentation/pianoteq-english.html` 的详细记载，以下为物理建模各维度的声学定义与数学物理公式：

### 1. 击弦动力学与三力度硬度 (Hammer Hardness at Piano, Mezzo, Forte)
- **声学原理**：琴槌由毛毡层紧密包裹木核制成。毛毡具有强烈的**非线性刚度**行为，其恢复力遵循 Hunt-Crossley 或 Chaigne-Askenfelt 幂函数模型：
  $$F(t) = K(v) \cdot [y_h(t) - y_s(t)]^p$$
  其中刚度指数 $p \approx 2.2 \sim 3.0$。
- **三点拟合机制**：
  - **Piano (MIDI ≈ 41)**：接触时间 $T_c \approx 4 \sim 5\text{ ms}$，高频截止点较低，声音圆润柔美；
  - **Mezzo (MIDI ≈ 70)**：接触时间 $T_c \approx 2.5 \sim 3.5\text{ ms}$，动态平衡点；
  - **Forte (MIDI ≈ 98)**：接触时间 $T_c \le 1.5\text{ ms}$，刚度极大，高频分音大量激起，产生典型的钢琴开裂声 (Crack)。
- **在 devpiano 中的落地参考**：目前 `devpiano` 的 `PianoSynthVoice.h` 仅有单一标量 `pianoHammerHardness`。建议重构为三段样条插值（Spline）或基于输入的 MIDI Velocity 映射：根据三点 $(41, H_p), (70, H_m), (98, H_f)$ 动态计算当前触键刚度。

### 2. 琴弦非谐性与有效弦长 (String Inharmonicity & Length)
- **声学原理**：钢质琴弦存在弯曲刚度（Bending Stiffness），使得振动恢复力除了张力还包含刚度项，导致第 $n$ 阶分音频率偏离谐波系列：
  $$f_n = n \cdot f_0 \cdot \sqrt{1 + B \cdot n^2}$$
- **非谐性系数公式**：
  $$B = \frac{\pi^3 E d^4}{64 T L^2}$$
  其中 $L$ 为有效弦长，$d$ 为弦径，$E$ 为杨氏模量，$T$ 为弦张力。
- **声学规律**：弦长 $L$ 越短，分母 $L^2$ 剧烈缩小，$B$ 值急剧放大。立式钢琴由于低音弦短，非谐性高，音色接近金属敲击；2.74 米三角琴（如 Steinway D）弦长极大，$B$ 值微小，低音纯正深厚。
- **在 devpiano 中的落地参考**：`devpiano` 当前的 `PianoTuning.h` 已经具备基频拉伸表，但各分音合成阶段可直接引入动态弦长参数，通过 $B(L)$ 动态调制各 Partial 的偏振频率。

### 3. 音板力学阻抗与衰减控制 (Soundboard Impedance & Cutoff)
- **声学原理**：音板是一块被肋木（Ribs）加固的大型云杉木共振板。琴弦振动通过琴桥（Bridge）将交变力传导给音板：
  - **力学阻抗 $Z = F / v$**：如果音板阻抗过小，琴弦能量在几个周期内迅速排空（响度极大但无延音，似班卓琴）；阻抗过大，琴弦能量无法向外辐射（声音干瘪微弱但延音极长）。
  - **阻抗高频截止 (Impedance Cutoff)**：木质纤维与清漆具有高频粘滞内耗。高频振动在音板上的阻尼速度远大于低频，形成天然的低通截止衰减曲线。
- **在 devpiano 中的落地参考**：`devpiano` 现有的 16 峰正交模态音板网络 (`bodyResonators`) 非常适合接入一个 `Z_soundboard` 阻抗增益因子（控制各模态的 Q 值与带宽）以及一个一阶/二阶的高频阻尼滚降极点。

### 4. 同音三弦非对称微失谐与双阶段衰减 (Unison Detuning & Two-stage Decay)
- **声学原理 (Weinreich 1977)**：钢琴中高音由三根弦组成。琴槌击弦后，三根弦并非同步衰减：
  - **初始强阶段 (Prompt Decay)**：三根弦同相振动，对琴桥产生同向驱动，能量快速辐射到音板，响度大但耗散快；
  - **后期长衰减 (Aftersound)**：微小的失谐（Unison Width）导致相位反转，琴桥受力互相抵消，能量被锁在琴弦内部缓慢泄漏，产生持续数秒的柔和长延音并伴随缓慢微澜拍频。
- **在 devpiano 中的落地参考**：`devpiano` 在 `PianoSynthVoice.h` 中已经设计了三弦非对称失谐。可以进一步参考 Pianoteq 的 `unison_width`（调节失谐频率）和 `Unison Balance`（调节初始相位与三弦能量差）暴露成用户控制项。

## 三、devpiano 物理建模引擎对照与落地建议

对比 `devpiano` 当前的源码实现（特别是 `source/Audio/PianoSynthVoice.h` 和 `AcousticSnapshot.h`），我们可以明确当前已具备的能力与值得吸收的成熟方案：

| 声学模块 | devpiano 当前实现现状 | Pianoteq 9 对标参考点 | 落地建议与演进路线 |
| :--- | :--- | :--- | :--- |
| **琴槌硬度模型** | 单一标量 `pianoHammerHardness` 控制瞬态衰减与刚度 | 三力度阶梯 (`hammer_hardness_piano/mezzo/forte`) | 在 `AcousticSnapshot` 中增加三速度硬度，并在击弦时根据 Velocity 进行非线性插值 |
| **击弦打击噪波** | 机械击弦微扰 (Bank & Chabassier 2019) 随机抖动 | 显式分离打击声 (`hammer_noise_slider`, `hammer_tone_slider`) | 引入独立带通滤波的冲击瞬态核（Impact Excitation Kernel），允许调节敲击感与音色倾角 |
| **分音频谱调节** | `pianoBrightness` 总体倾斜控制 | 8 阶分音微调 (`Spectrum Profile Partials 1~8`) | 允许在整音层对特定分音（如 1/7 击弦点造成的第 7、8 分音）施加精确陷波增益 |
| **音板阻抗与截止** | 16 峰正交云杉模态滤波器固定 Q 值 | 阻抗连续滑块与高频截止 (`Impedance`, `impedance_cutoff`) | 在 16 峰模态滤波器前增加一个动态截止低通滤波器，并根据阻抗缩放模态阻尼时间 |
| **弦长与非谐性** | 预计算静态基频拉伸表 (`PianoTuning.h`) | 动态弦长连续调整 (`String Length`, 0.8m~3.5m) | 将基频拉伸与各 Partial 的 $B$ 系数关联，支持通过有效弦长实时改变非谐性泛音结构 |
| **同音三弦拍频** | 3 弦独立三振荡器非对称拍频 (Phase 19-C) | `unison_width` 与 `unison_balance` 连续微调 | 将目前的硬编码失谐常数提升为由 `unison_width` 驱动的动态参数 |
| **交感共鸣池** | 12 半音基底共鸣池与 Duplex 共鸣池 | 全局交感共鸣与共鸣衰减时长 (`sympathetic_resonance`, `resonance_duration`) | 增加共鸣池能量反馈阻尼控制，允许调节共振尾音的持续时间 |
| **无制音高音区** | 全音域制音策略统一处理 | 显式高音截断分界线 (`last_damper_slider`，约 F6~C7) | 88 键中高于该键位的音符制音器永不落下，松键后保持自由衰减与交感振动 |

## 四、总结与后续步骤建议

1. **参数字典成果**：Pianoteq 9 二进制的参数字典证实其核心物理建模聚焦于“击弦非线性硬度分级”、“有效弦长/非谐性”、“音板力学阻抗衰减”、“同音三弦拍频”和“交感共振衰减”。
2. **代码设计契合度**：`devpiano` 的 `PianoSynthVoice` 已经拥有极高的物理声学设计水准（涵盖 Bilbao、Bank、Chabassier 等顶尖论文模型），其架构天然兼容 Pianoteq 的参数控制范式。
3. **下一步执行动作**：
   - **动作一（参数对齐）**：可在 `devpiano` 的 `AcousticSnapshot.h` 和 `SettingsModel.h` 中逐步引入三力度琴槌硬度和音板截止参数。
   - **动作二（黑盒声学验证）**：在 Windows 平台上使用 Pianoteq 9 渲染 C1~C7 在 Velocity 41, 70, 98 时的纯干音 WAV，用 Python 测量其实际非谐性与衰减常数，用真实数据校准 `devpiano` 的物理模态常数。