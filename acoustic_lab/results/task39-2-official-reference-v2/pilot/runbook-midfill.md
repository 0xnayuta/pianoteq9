# Task 39-2 P3 采集 runbook：48 kHz midfill

- 修订：2026-10-13。用户已授权先修订文档，再执行 midfill；GUI 变更仅主会话逐次审批，工作区修改不自动提交。
- 本轮及后续可提供的参考仅为官方 Pianoteq 9.2.5 Standard Trial。**treble96（87/93/99/105/108）关闭为“缺少合格高采样率参考环境、无法实施”**，不是等待设备排查或后续采集的待办。
- 依据：[官方手册 §1.3 / §15](https://www.modartt.com/user_manual?product=pianoteq&lang=en)规定 Stage/Standard 内部采样率上限 48 kHz，PRO 上限 192 kHz；[官方 FAQ](https://www.modartt.com/faq?product=pianoteq)明确无 PRO 试用版。9.2.5 随附手册 SHA-256 `601473ece9de67913718973e121dc4d158ad1340e94ad70be9e81868ddf5fe29` 与既有登记一致。
- 不采购或假定 PRO、不改设备或宿主采样率冒充原生高率计算、不升采样、不修改 WAV 头。原 treble96 刺激仅保留为未执行准备记录，不采集、不分析、不作为实测。
- 85–108 段继续是自 C6 实测锚点按公开文献外推，**无独立高采样率实测验收**；不能因关闭该路线或 midfill 通过而宣称全域验收通过。

## 1. 冻结范围与矩阵

midfill 为新登记的未看音高验证集，仅检验 24→28、48→60 插值曲率及中区覆盖，不新增或修改生产 B 锚点。

| 会话 | MIDI 音 | 力度 | 采样率 | 单元 |
|---|---|---|---|---|
| s01-n25-48000-rep0 | 25 | 41/70/98 | 48 kHz | 3 |
| s02-n27-48000-rep0 | 27 | 41/70/98 | 48 kHz | 3 |
| s03-n49-48000-rep0 | 49 | 41/70/98 | 48 kHz | 3 |
| s04-n51-48000-rep0 | 51 | 41/70/98 | 48 kHz | 3 |
| s05-n64-48000-rep0 | 64 | 41/70/98 | 48 kHz | 3 |
| s06-n74-48000-rep0 | 74 | 41/70/98 | 48 kHz | 3 |

- 合计 6 个独立冷启动会话、18 个单元；每个单元只采集一次，rep0 是既有目录约定，不宣称重复稳定性或双率一致性。
- 排除已消耗 holdout 26/39/50/63/77/86/98/104 与旧锚点。不得先看新 WAV 再改网格、配对、判据或参数。
- 刺激使用 `pilot/stimulus-midfill/` 的 18 个 MIDI 与 `receipt.json`，复制到新批次的 `stimulus/` 并逐文件核验；生成器 `make-stimulus-corpus.py` 的认证 A4-v70 自检沿用。
- 单元命名 `n<note>-v<velocity>-48000-rep0`；批次命名 `midfill-<YYYYMMDD-HHMMSS>`。

## 2. 采集身份与状态门禁

复用 [runbook-corpus](runbook-corpus.md) 的 §0、§1、§2 和异常处置树，仅以本手册矩阵替代 corpus 的音符/会话表；不使用其中旧批次删除命令或 training 汇总命令。

- EXE：官方 9.2.5，SHA-256 `7fcb5b2385a753e2f7d0a9ed068692abe877ab65b438e70a3fe2b44879b278bd`，签名 Valid；仅在全新私有 home/prefs 中启动。
- FXP：`Task39-2 Flat Full State 20261012-060228`，SHA-256 `9f749ca99143c4b1e0760099b2d6aad83cc3e9a745aa57a0a535a481342cddc9`。
- 播种归档 register 批次的 `prefs-template/48000/`；音频设备须实读为 DirectSound / 48000.0 / buffer 2560。
- 每会话仅切一次 Standard，再执行 RPC prepare、恢复反例与完整 215 项认证基线断言。A4=440、拾音/增益/效果等沿用完整认证状态，不重新调参。
- 每单元 `unit-before` 加载 MIDI 并断言 pre == 基线；GUI 导出 WAV / 48000 Hz / 24-bit / 双声道、Use current settings、Normalize 关闭。
- 首单元按 D1 核对并修正目标目录为**本会话** `private-home/Documents`；不得写回模板来源或旧证据目录。
- `unit-after` 核验实际 WAV 头/散列与 post == pre；独立 `pilot-verify.py unit --rate 48000` 接受后才进入下一单元。
- 每个 GUI 动作前核验 EXE/PID/创建时间/HWND，动作后以 `ui_snapshot(mode=auto)` 或截图复读，并保存原始请求、响应及审批证据；历史坐标不直接复用。
- 每会话自创建起 ≤900 s；保持官方 20 分钟试用边界。计时器仅通知、不强杀；异常不静默重试，按既有处置树正常收尾。
- 会话退出须 exit 0；每会话及批次结束核验受保护源/脚本和用户配置，无缺失/变更；原件保留不删除。

## 3. 采集后的分析与结论边界

```bash
python3 tools/pilot-partial-analysis.py --preset midfill \
    --batch <midfill 批次根> --out <分析输出>
```

- 参考侧族质量保持 amendment-1/2：W1=0.08–3.8 s、W2=0.5–4.1 s、立体声功率和、40–20000 Hz；至少 5 个已识别分音，至少 3 个训练分音和 2 个未触碰预测分音；RMS ≤1 / max ≤3 cents，窗口散布 ≤1 cent。
- n25/n27 基频低于 40 Hz，保留既有检测下限；不得降低下限凑基准，归一化使用双方共同可识别分音。
- 跨生产者评估使用 amendment-3/4：可比较分音集排除冻结的 `beatingPartials` 设计区，基准 m 取可比较集最小共同分音；全口径和设计区指标并列保存。
- 参考侧拟合的 `B_eff` 只标记为有效输出参数；参考族质量通过不等于 devpiano 对照误差通过，也不证明中心弦身份。
- 结果不预设通过或曲率方向。失败、不可分析和缺少比较分音均照实登记；采集后不以该验证集回调 B 表、不放宽判据。
- 85–108 高音区缺少合格参考的边界保持；不恢复 treble96，不把 midfill 结论外推为全 88 键实测认证。

## 4. 证据与交付

- 开始前冻结本手册、方法修订、分析/采集脚本、MIDI receipt、215 项基线与生产 B 表散列到 `scope.json`。
- 采集后保存 18 个单元状态、会话生命周期、完整 GUI 通信/截图、参数快照、WAV、分析配方及结果。
- 归档沿用 `archive_pilot_batch.py`：逐文件源/目标 SHA-256、manifest、四个机器索引与 evidence-catalog；不改写既有已消耗 holdout 的归档判决。
- 采集/分析的实际结果只在本批次回执和 devpiano 当前迭代追加，不把“已授权”写成“已采集通过”。

