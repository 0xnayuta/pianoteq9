# Pianoteq 9 保留音频量测与证据复核

> 用途：本仓库唯一的当前量测口径、参考结果与旧主张处理入口；不是实琴标定或商业内部算法等价证明。
> 原研究日期：2026-10-09；Task 39-1 复核及证据回流：2026-10-10。原稿已随原始数据封存，不静默改写历史观测。
> 来源：devpiano Task 39-1，渲染源码输入 `76ebdca`；结果记录来自当时工作树快照，不声称该提交包含本次全部复核记录。
> 数据与责任：[参考 manifest](../acoustic_lab/results/task39-1-reference-revalidation/manifest.json)；devpiano 实现状态只在其 [roadmap](https://github.com/0xnayuta/devpiano/blob/main/docs/roadmap/roadmap.md) 维护。

## 数据身份与历史条件

- 候选独立程序与核心 PE 的 FileVersion/ProductVersion 均为 9.1.2。独立程序 SHA256：`620ba6d53808994e0a9fa999a7e060780e36daeb27693d5f249d0ad6df3f1eda`；核心：`218ba590b07877d5a80d1e48f2d61f90ceda7971a02e5d34ddbc8ecb0d5678a5`；英文手册：`601473ece9de67913718973e121dc4d158ad1340e94ad70be9e81868ddf5fe29`。身份不证明旧 WAV 由该散列及某组参数生成。
- 保留参考为 48 kHz、24-bit、双声道 WAV；SMF 0、单轨、480 PPQ、500000 µs/quarter、Ch1。C1–C7 为力度70、0秒起音、4秒离键；三力度 C4 为41/70/98、3秒离键；C3衰减样本实际力度80、6秒离键。末尾 NoteOn(0,0) 使用 NoteOff 语义，不是新的低音。
- 预设名 NY Steinway D Classical 仅来自旧报告/命令模板。历史渲染 receipt、预设参数散列、EQ/Reverb、麦克风、Master/限制器、随机种子均未知；当前 prefs 与脚本模板不能补造过去的生效条件。官方手册还说明 Classical/Prelude 可只在拾音位置上不同。
- 本次是保留输出的复算，不是重做实琴测量或新的完整 Ghidra 取证。旧地址、切片和 XRefs 的历史记录不因文档纠错自动得到验证或全部被推翻。

## 统一量测定义

`midiNote` 为 MIDI 编号21–108，`pianoKey=midiNote-20` 为1–88琴键序号；分音号从1开始。柔弦基频与实际第一分音分开：

$$f_1=f_{soft}\sqrt{1+B},\qquad f_n=n f_1\sqrt{\frac{1+B n^2}{1+B}}$$

这是本次统一的刚性弦候选拟合模型，不是对商业内部实现的认证。名义12-TET、拉伸后的第一分音基准、同音弦各自频率与最强混合峰不得互换。

- 低/中音频率窗0.08–3.8秒；C7用0.08–0.8秒。Hann、至少8倍补零、log-power抛物线峰插值；真实`1/T`尺度约0.269/1.389Hz，主瓣约`4/T`宽。补零提高插值密度，不提高双弦分辨能力。
- 分音族使用立体声功率峰、不减均值（原候选搜索口径），阈值为全窗最强功率的-80dB，最近峰容差1%；固定峰配对后独立复拟并留一复拟。原候选种子只是量测输入，不是目标答案或生产参数。
- C4谱窗0.05–0.80秒，每声道去段均值，`P=(|FFT(L)|²+|FFT(R)|²)/2`，在20Hz以上归一化。谱重心为`ΣfP/ΣP`；HF为>2.5kHz功率占比，以`10log10`表示。单声道均值的相干抵消与立体声功率求和必须区分。
- 原始最大峰以`20log10 max|x|`记录，单声道均值和双声道最大峰分别列出。不能用增益差证明音色或品质差。
- 起音量为前0.15秒内局部峰的10%–90%因果moving-RMS上升时间，比较10/20/40ms窗，窗口终点记时。参考开头补40ms零只定义仪表初始化，不证明渲染前史、接触时间或硬件延迟。
- C3用100ms RMS窗、20ms hop，在离键前多窗分别拟合RMS幅度和功率；每窗按其最大值归一，时间原点为首窗中心。正系数双指数仅为输出包络现象模型，边界/种子/容差见 [methods.json](../acoustic_lab/results/task39-1-reference-revalidation/methods.json)。

## 条件性参考分音族

`f1_fit` 是固定配对族的拟合量，不等于最强峰或经认证的中心弦。输入、编号、观测Hz、Hz/cents残差见 [reference-family-checks.json](../acoustic_lab/results/task39-1-reference-revalidation/reference-family-checks.json)。

| 音符 | `f1_fit` Hz | `B_eff` | 固定分音号 | 最大拟合残差 cents | 留一复拟最大残差 cents |
|---|---:|---:|---|---:|---:|
| C1 | 32.4907 | 8.9757e-05 | 1–25 | 2.597 | 2.865 |
| C2 | 65.2969 | 5.0277e-05 | 1–25 | 1.204 | 1.328 |
| C3 | 130.7003 | 0.00011635 | 1–25 | 0.378 | 0.415 |
| C4 | 261.5106 | 0.0003587 | 1–15 | 0.606 | 0.720 |
| C5 | 523.3005 | 0.0011064 | 1–8 | 0.255 | 0.532 |
| C6 | 1049.6386 | 0.0031428 | 1–5 | 0.208 | 0.534 |
| C7 | 2109.5746 | 0.0090015 | 1–3 | 0.194 | 0.755 |

C3–C5的候选族与旧稿`B<1e-5`不相容；C6量级与旧报告接近，仍不认证内部或实琴参数。留一复拟保留全数据所选峰配对，因此只是自洽检验，不是无泄漏的峰识别外推；C7仅三个可用分音，可靠性尤其有限。未知历史控制和同音身份阻止将这些值直接注入 devpiano。

C7在父方单声道、去均值、0.08–0.8秒窗的最强混合峰约2107.37Hz，直接DFT约2107.365Hz，和上表族拟合值属于不同量。旧稿柔弦频率2276.84Hz配合其`B`应对应约2277.77Hz第一分音，不符合该观察；不作调律锚点，也不在原拟合流程缺失时擅定故障原因。

## C4 力度与输出包络

| Velocity | 单声道均值最大峰 dBFS | 双声道最大峰 dBFS | 功率重心 Hz | HF功率占比 dB |
|---|---:|---:|---:|---:|
| 41 | -28.381 | -25.527 | 299.229 | -60.042 |
| 70 | -19.310 | -17.188 | 387.337 | -40.728 |
| 98 | -12.086 | -10.611 | 477.905 | -28.239 |

70→98在本口径下HF占比增加约12.49dB。单声道峰复现旧报告的峰值口径；旧HF绝对值和谱重心不因此自动认证，幅度谱范数与功率谱范数不能混用。数据支持力度相关频谱变化，不唯一反演毛毡指数或分音增益幂律。

| Velocity | 10ms RMS窗 rise ms | 20ms RMS窗 rise ms | 40ms RMS窗 rise ms |
|---|---:|---:|---:|
| 41 | 32.583 | 34.208 | 39.750 |
| 70 | 31.479 | 33.083 | 41.188 |
| 98 | 31.583 | 31.042 | 39.833 |

旧稿32.2ms不准入为恒定琴槌接触/起振常数，也不直接写入ADSR或延迟目标。

## C3 衰减的可识别性

| 观测窗 s | 输出域 | 快项τ s | 慢项τ s | 归一化RMSE | 拟合触界 |
|---|---|---:|---:|---:|---|
| 0.08–5.8 | RMS amplitude | 0.902 | 25.267 | 0.00319 | 否 |
| 0.08–5.8 | power | 0.489 | 2.812 | 0.00340 | 否 |
| 0.3–5.8 | RMS amplitude | 0.877 | 15.385 | 0.00317 | 否 |
| 0.3–5.8 | power | 0.495 | 3.688 | 0.00284 | 否 |
| 0.5–4.5 | RMS amplitude | 0.868 | 30.868 | 0.00226 | 是 |
| 0.5–4.5 | power | 0.465 | 2.022 | 0.00166 | 否 |

低残差仍不能唯一识别慢项；此表不替换成新的全琴衰减常数。单指数幅度平方的功率时间常数为一半；双指数幅度平方还含交叉项，不能逐项简单换算。输出声压/RMS系数不是机械能量，89.5/10.5%的旧归因撤回。残差存在多个低频峰，3.56Hz不作为全琴唯一同音宽度；频率与周期必须互为倒数，0.366Hz的周期约2.73秒而不是0.28秒。6秒之后为离键场景，不混入自由持音拟合。

## 证据等级与旧主张处理

| ID | 旧主张 | 当前状态 | 当前结论与边界 |
|---|---|---|---|
| `historical-render-conditions` | 纯干音且关闭 Reverb/EQ | `unknown` | 旧渲染 receipt、预设参数、Reverb/EQ、麦克风、增益和种子未知；命令模板与当前prefs不能补证 |
| `C7-frequency` | 柔弦基频 2276.84 Hz 可作锚点 | `withdrawn` | 固定窗最强混合峰约2107.37 Hz；候选族拟合f1约2109.57 Hz，不能互称中心弦或复现旧f0 |
| `legacy-B-curve` | 指数B(k)与报告散点可直接注入生产 | `withdrawn` | 键号语义和锚点不一致；候选B_eff只描述给定WAV和固定配对，不是商业内部或实琴参数 |
| `contact-time` | 32.2 ms 为恒定琴槌接触/起振常数 | `withdrawn-attribution` | 输出因果RMS上升时间随10/20/40ms窗口变化，不能直接设定接触时间、ADSR或硬件延迟 |
| `hammer-exponent` | +12.12dB 唯一证明 p=2.4..2.8 | `withdrawn-attribution` | 同口径HF功率占比70→98增加约12.49dB；不能由三个输出点唯一反演毛毡接触指数 |
| `decay-energy-beat` | 0.865/5.322s、89.5/10.5%和3.56Hz为全琴常数 | `withdrawn-attribution` | 拟合依赖窗口和幅度/功率域，慢项不可唯一识别，输出系数不是机械能量或唯一同音宽度 |
| `commercial-algorithm-equivalence` | 常量/分配大小/注册链证明完整商业DSP算法，示例工业级已验证 | `not-established` | 原始静态记录保留但本轮未重做Ghidra；理论/候选方程不等于专有实现或工程实时验收 |
| `public-parameter-semantics` | 三力度/Unison/Last damper语义 | `admitted-semantics` | Piano/Mezzo forte/Forte约41/70/98；Balance是中弦频率位置；Last damper用MIDI严格大于界限；未认证其它滑块范围 |
| `reference-candidate-families` | 新B_eff表可作为新权威物理常数 | `conditional-observation-only` | 只准入给定文件和固定配对下的自洽结果；LOO保留全数据选峰，非无泄漏外推 |

机器可读状态由 [claims.json](../acoustic_lab/results/task39-1-reference-revalidation/claims.json) 保存。公开定义、历史静态观察、经典理论、候选模型和工程验证分别管理；任务产物完成不等于内部机制或生产实时契约已认证。参考逆投影的两反对称列在单声道/琴桥平均力求和中抵消；若两份after能量均取0.105，总量为1.105，不是1。这些数学复核不认证专有代码。

## 复算与原始数据保留

- 轻量结果、methods、claims及manifest在 `acoustic_lab/results/task39-1-reference-revalidation/`，可随Git保存；商业资产和WAV仍排除。
- 本机只读封存目录 `acoustic_lab/backups/task39-1-20261010/` 包含 `devpiano-evidence.tar`、`pianoteq-reference-inputs.tar`、`devpiano-document-snapshot.tar` 和 `seal.json`。54组生产及12组参考MIDI/WAV已逐项核对原散列；不含商业程序、模型包、官方手册或用户配置。只读标记与SHA不等于WORM存储，备份不随Git分发。
- 原稿/脚本可在输入修订 `3f710ec` 或封存包中追溯；旧模板的空入口没有执行完整实验。当前入口只分析现有数据，先检查输入/结果散列，缺失或不匹配时非零失败，不自动渲染、恢复或覆盖文件。

```bash
python3 scripts/run_acoustic_experiments.py
python3 scripts/run_acoustic_experiments.py --json
```

可显式提供 `--audio-dir`、`--midi-dir`、`--evidence-dir` 的等价保留目录；不依赖G盘、devpiano构建缓存或商业二进制。原始音频缺失时应从本机封存包恢复到新的独立目录，再显式指向它；不能将重新生成和重算相混，也不能用新渲染覆盖历史素材。

`reference-candidate-recipe.json` 保留旧候选搜索和固定配对复拟文本作为来源输入，当前入口不执行JSON中的代码。`reference-parent-checks.json` 包含C4/C3和矩阵/指数语义检查。devpiano的生产对象、参数、波形基线与排期仍归其自身记录，本仓库只保留冻结对照来源，不维护第二份产品状态。清理或重新构建Windows镜像树不会删除这里的封存包。
