# Pianoteq 9 参数语义与声学研究字典

> 用途：组织公开参数语义、历史字符串线索和候选理论；不是商业内部类、滑块范围或方程的完整还原。
> 当前量测、旧主张处理与身份见 [声学基准报告](acoustic_benchmark_report.md) / [manifest](../acoustic_lab/results/task39-1-reference-revalidation/manifest.json)。

## 来源等级与单位

官方定义、历史字符串/注册观察、经典理论、候选设计和工程验证分别管理。参数存在不证明DSP拓扑；网页语义不证明指数、质量或微观离散方程。以下按使用域组织，不声称 Modartt 内部使用同一三层类结构。

原稿缺少可复核来源的硬度、噪声、阻抗、弦长及共鸣增益范围不再列为厂家真实范围；相关取值统一为“未复核”，开发者自己的合法范围必须另行设计和验证。音量百分比、线性增益、Hz、cents、秒、MIDI值不可混用。

## 参数字典

| 名称 / 历史标识线索 | 当前语义 | 单位 / 范围与来源边界 |
|---|---|---|
| `hammer_hardness_piano` | Piano力度整音硬度；公开锚点约MIDI41 | 公开Voicing定义；真实滑块范围未复核 |
| `hammer_hardness_mezzo` | Mezzo forte力度整音硬度；公开锚点约MIDI70 | 不与Mezzo piano混称；标识为历史字符串线索 |
| `hammer_hardness_forte` | Forte力度整音硬度；公开锚点约MIDI98 | 公开语义不能独自反推出接触指数 |
| `hammer_noise_slider`、`hammer_tone_slider` | 打击噪声与音色方向的历史研究线索 | dB/归一化映射、增益与滤波拓扑未复核 |
| `Hammer Stickiness`、`hammer_tine_noise` | 毛毡/电声模型相关控制线索 | 范围、单位与实现未复核，不扩展 devpiano 产品定位 |
| `Soundboard Impedance`、`impedance_cutoff`、`impedance_section` | 阻抗、频率与分区的研究维度 | 原始槽位记录在Phase2；具体映射、频率/Q表未认证 |
| `String Length`、`String Tension` | 有效长度、张力与几何的研究维度 | 物理单位应分别为m、N；不是只改弦长就能复刻琴型 |
| `Spectrum Profile` | 公开的前八项强度控制，第1项称fundamental | 对应分音编号从1开始，不直接等同某个击弦点或固定陷波 |
| `unison_width` | 同一音三弦最高与最低频率之差 | 公开Advanced Tuning语义；显示单位/映射应单独确认，不混Hz和cents |
| `Unison Balance` | 中弦频率由最低位置(-1)到最高位置(+1)，0为公开出厂描述 | 不是机械能量、垂直/水平偏振或初始相位权重 |
| `Direct sound duration` | 公开可独立调节直达声时长 | 不是固定的全琴双指数衰减常数 |
| `sympathetic_resonance`、`resonance_duration_view` | 开放弦交感强度/时长线索 | 增益、秒与耗散定义未复核；输出拟合权重不是机械能量 |
| `duplex_scale_resonance` | 非发音段共鸣研究线索 | Duplex不是独立Aliquot第四弦；高通不能证明被动受迫模型 |
| `last_damper_slider` / Last damper | 公开定义为MIDI编号严格大于该值时无制音器 | MIDI21–108，pianoKey=midi-20；MIDI66=F#4，F#6=MIDI90，key66=MIDI86(D6)。具体默认值未复核 |
| `damper_position_slider`、`damper_duration_slider`、`damper_noise_slider` | 制音位置、下落耗散和机械声研究线索 | 不将MIDI离键速度与秒/增益等量；原范围缺来源则未复核 |
| `damper_vel_threshold`、`pedal_noise_slider` | 制音门槛与踏板声线索 | 门控、来源通道、Panic和连续值行为需实际验证 |
| `Quadratic Effect`、`Blooming Energy`、`Blooming Inertia` | 张力与泛音时间轨迹的研究维度 | 历史槽位版本不一致不自动统一；候选方程不证明二阶状态求解器 |
| `Lid Position` | 琴盖与辐射控制研究维度 | 角度、离散模式与传递函数未复核 |

公开依据来自本机 `binaries/Documentation/pianoteq-english.html` 的 Advanced Tuning、Voicing/Spectrum profile和Action章节；该完整手册不提交Git，其SHA已写入manifest。历史字符串、汇编和作者注释见 `docs/phase1/`–`docs/phase5/`，本轮不重新认证它们。

## 理论模型与本次量测

### 刚度与第一分音

本次拟合使用统一的刚性弦近似：

$$f_1=f_{soft}\sqrt{1+B},\qquad f_n=n f_1\sqrt{\frac{1+B n^2}{1+B}}$$

其中柔弦频率、拉伸后第一分音基准、三弦各自频率和输出最大峰不同。均匀圆截面弦的经典近似可写为 $B=\pi^3 E d^4/(64TL^2)$；该式须明确弯曲刚度、张力与长度假设，不直接适用于所有缠弦或成为商业内部方程证明。保持名义音高时改变弦长还需考虑张力/线密度，不能仅凭 $L^{-2}$ 推断整个琴型。

### 琴槌与包络

非线性接触力 $F=K\max(\eta,0)^p$ 及迟滞修正可作为经典理论线索，但 $K$、质量、压缩位移、接触时间、MIDI→机械速度映射及 $p$ 在本仓库未被完整证实。参数硬度不是物理速度；三个输出力度点不能唯一确定这些值。输出RMS rise也不能代替接触测量。

单指数振幅平方的功率时间常数为一半，复合包络还含交叉项。输出声压/功率、存储弦能量和模态系数不等量；同音平衡不能从一组输出比例反推。当前实际结果与候选族只引用基准报告，不再复制旧常数或指数曲线。

## devpiano 消费边界

这些是研究输入，不是必须新增的API或琴型工厂。devpiano 已有增强模态琴槌、分音归一化/拉伸、共鸣、微失谐、双振幅包络与经验动力学；状态、实时、文件格式及产品路线只看其 [roadmap](https://github.com/0xnayuta/devpiano/blob/main/docs/roadmap/roadmap.md)。本字典不要求保留旧字段兼容，不承诺所有旋钮可直接生产落地或具体CPU成本。
