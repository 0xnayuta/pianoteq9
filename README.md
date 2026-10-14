# Pianoteq 9 逆向研究与保留音频实验室

本仓库整理 Pianoteq 的公开参数语义、历史样本静态记录与软件输出声学观察，服务于 [devpiano](https://github.com/0xnayuta/devpiano) 的自研钢琴开发。旧 9.1.2 已确认来自第三方破解/补丁发布，停止执行并撤销官方参考资格；新研究仅在核验后的官方 9.2.5 试用版上按独立协议开展。

## 当前证据边界

- 官方参数定义、历史地址/XRefs、经典理论、候选模型和生产工程验证分别管理；有报告、字符串、常量或分配大小不等于完整商业算法已被还原。
- devpiano Task 39-1 的参考侧复算与纠错已回流。本仓库当前量测与旧主张处理的唯一入口为 [声学基准报告](docs/acoustic_benchmark_report.md)，轻量结果和方法见 [manifest](acoustic_lab/results/task39-1-reference-revalidation/manifest.json)。
- **Task 39-2（官方 9.2.5 受控参考）**：受控采集、插值修复与生产回归已完成，devpiano 现行 `B` 表为 17 实测锚点 + 2 文献外推节点；用户批准冻结该表、停止追加训练锚点。既有未全通过判决与已消耗验证集保持原样，工具修复后的诊断复算不替代正式验收；后续 [validation-interp2 预登记](acoustic_lab/results/task39-2-official-reference-v2/pilot/validation-interp2-preregistration.json) 与 [runbook](acoustic_lab/results/task39-2-official-reference-v2/pilot/runbook-validation-interp2.md) 所述一次有界独立验收已完整执行并消耗（48/48 单元；判决：32/32 可评估单元达标，12 个 n88 分析失败 + 4 个 n67-v47 可比分音不足 → **证据不足**，未记通过），不因判决自动调参、扩采或补开批次。
- **参考资源边界**：用户仅提供当前 Standard Trial，96 kHz treble96 因缺少合格参考环境保持关闭，不保留此轮或后续采集承诺。[48 kHz midfill](acoustic_lab/results/task39-2-official-reference-v2/pilot/runbook-midfill.md) 已完成，不再是待采集任务；85–108 仍为文献外推，不由本次抽样验收认证全域或真实琴型。
- 当前来源资格由 [provenance.json](acoustic_lab/results/task39-2-official-reference-v2/provenance.json) 追加说明：旧二进制、Phase 1–5 地址记录与旧 WAV 为 `untrusted-binary-provenance`，数值复算不能恢复其官方资格。原 manifest、数据和方法不覆盖，公开手册/理论、自有量测器与 devpiano 生产基线分别保留。
- 候选分音族及 `B_eff` 只描述指定 WAV/方法/固定配对。历史预设参数、EQ/Reverb、拾音、增益及种子未知，不称为真实 Steinway 逐键常数，也不直接注入 devpiano 参数表。
- **放弃“逆向完整物理建模引擎”的幻想**：商业编译器激进优化抹去了物理意图，浮点指令无法反演物理量纲；彻底撤回存在致命缺陷的旧 C++ 求解器示例（如 Phase 3 单声道抵消与能量 1.105、Phase 5 余弦平方均值 1/2 滑音不衰减、音频内循环逐采样超越函数调用等）。
- 旧指数刚度曲线、C7错误频率锚点、恒定接触时间、固定机械能量权重和完整算法等价主张已按证据限制或撤回；不是把旧常数替换成另一套权威常数。
- 商业二进制、模型包、预设、完整官方手册、专有配置与大体积音频不进入 Git。只吸收可解释的参数语义、独立量测与数学候选，Clean-Room 声明不代替来源和许可核对。

## 阅读入口与职责

| 入口 | 职责 |
|---|---|
| [SUMMARY.md](SUMMARY.md) | 研究价值、已撤回外推及 devpiano 消费边界，不复制量测表 |
| [声学基准报告](docs/acoustic_benchmark_report.md) | 固定口径、候选结果、残差、不确定性、准入/撤回与复算命令 |
| [参数字典](docs/pianoteq9_parameter_dictionary_and_acoustic_spec.md) | 参数名与语义来源，单位及未复核范围 |
| [研究路线](docs/roadmap.md) | 原研究产物与当前证据状态，不维护 devpiano 产品进度 |
| `docs/phase1/`–`docs/phase5/` | 原静态记录与候选假说；每份文件的复核说明决定当前可用范围 |
| [参考结果 manifest](acoustic_lab/results/task39-1-reference-revalidation/manifest.json) | 原始数据散列、版本、方法、证据包来源及已知/未知条件 |

## 保留数据与本机封存

```text
acoustic_lab/
  midi/                                  保留 SMF 输入
  audio/                                 保留参考 WAV，本机忽略，不保证可重新生成
  results/task39-1-reference-revalidation/ 轻量结果、方法、claims 和 manifest
  results/task39-2-official-reference-v2/  Task 39-2 官方 9.2.5 协议、pilot 套件、逐键锚点与封闭验证闭环；不覆盖 v1
  backups/task39-1-20261010/               本机只读封存包，不随 Git 分发
scripts/
  extract_parameters.py                   只读已登记官方样本的字符串并核对散列
  run_acoustic_experiments.py              只读分析现有参考文件并检查冻结证据
```

本机封存包含原始参考 MIDI/WAV、完整 devpiano Task 39-1 证据包以及双方原文快照和重建文本，不含商业二进制或模型资产。`seal.json` 保存 archive/member SHA256；只读权限不等于不可篡改存储。Windows 构建目录不再是原始证据的唯一保留位置。

Git clone 不带被忽略资产。缺数据时，从本机封存恢复到新的独立目录后显式指定路径；不要覆盖历史文件，不使用当前 prefs 补证历史渲染条件，不承诺未知种子的商业渲染逐字节重现。

## 实际复算入口

环境：Python 3，NumPy 和 SciPy；冻结基线版本及容差见 [methods.json](acoustic_lab/results/task39-1-reference-revalidation/methods.json)。

```bash
python3 scripts/run_acoustic_experiments.py
python3 scripts/run_acoustic_experiments.py --json
```

可用 `--audio-dir`、`--midi-dir`、`--evidence-dir` 指向等价保留目录。入口先检查输入/结果散列，再由 WAV/MIDI 独立计算并核对冻结数值；缺失、损坏或数值不符返回非零。JSON 与文本输出均明确旧数据不具官方参考资格；复算通过不是校准准入。入口没有调用商业程序、重渲染或覆盖输出的代码路径，也不执行 JSON 重建文本。

REA 6.3.0 / Ghidra 12.1.4 是 Task 39-1 记录的可用研究工具环境，具体过程应保留对应版本和真实工具证据；不能用当前环境版本改写过去 session。该任务没有新开展完整 Ghidra 商业 DSP 重构。

## 对 devpiano 的边界

研究结果可以反馈纠错，实现代码与产品排期仍在 [devpiano roadmap](https://github.com/0xnayuta/devpiano/blob/main/docs/roadmap/roadmap.md) 维护。本仓库不修改其 DSP、默认参数、预设格式，不提供历史字段兼容方案或工业级实时性能承诺。
