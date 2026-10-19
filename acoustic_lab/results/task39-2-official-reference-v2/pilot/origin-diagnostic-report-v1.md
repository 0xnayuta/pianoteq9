# A5 origin 有界诊断报告（2026-10-18）

## 授权与边界

- 用户批准：只读现有 12 WAV 起点诊断，不启动 reference、不重跑 producer、不读 holdout。
- 本轮未启动 Pianoteq，未操作 GUI，未生成新 stimulus，未重跑任何 12 个 WAV 的 producer。
- 未读取验证矩阵中任何 unit 的 WAV；只使用已消费 n69-v70 控制。
- 未修改 devpiano 生产代码或 DSP。

## 数据

- 4 个独立冷启动会话：s01/s02 @ 44.1 kHz，s03/s04 @ 48 kHz。
- 每会话 3 个固定时间偏移：0.0 / 0.5 / 1.0 s。
- 每会话 1 个已消费控制：n69-v70，1440 样本 MIDI，NoteOn @ 96 ticks = 0.1 s，NoteOff @ 720 ticks。
- 共 12 个 WAV；每个 WAV 由官方 9.2.5 trial 的受控 File -> Export 流程生成。

## 方法

对每个 WAV 读取 24-bit 立体声 PCM，计算 4-sample 因果能量包络，取第一个超过 -60 dBFS 的样本作为声学起音。比较同一 rate 下三个偏移的起音坐标和文件帧数。方法只测量导出坐标，不依赖文件名、WAV 容器元数据或插件内部状态。

## 结果

| rate | 会话 | shift 0.0 | shift 0.5 | shift 1.0 | 0.5 s 增量 | 1.0 s 增量 |
|---|---:|---:|---:|---:|---:|---:|
| 44100 | rep0 | 4429 | 26481 | 48529 | 22052 | 44048 |
| 44100 | rep1 | 4429 | 26481 | 48529 | 22052 | 44048 |
| 48000 | rep0 | 4823 | 28823 | 52823 | 24000 | 48000 |
| 48000 | rep1 | 4823 | 28823 | 52823 | 24000 | 48000 |

- 两个 44.1 kHz 会话的 onset 坐标逐样本一致；两个 48 kHz 会话也逐样本一致。
- 48 kHz 的两个增量精确等于 24000 / 48000 samples。
- 44.1 kHz 的增量与标称 22050 / 44100 偏差为 +2 / -2 samples，来自 4-sample 检测对齐，不是原点漂移。
- 所有 12 个 WAV 的 `first_nonzero = 0`，因此首非零不能用作事件标记；只使用能量起音和线性偏移。
- 48 kHz 的文件帧数每次增加 24064 samples（512-sample block 填充），但音频内容起音增加精确 24000；尾部填充不影响起点。
- 44.1 kHz 的文件帧数每次增加 22016 samples，音频内容起音增加 22052/22048；两者差来自尾部/块填充，不影响起点。

## 原点映射

- 唯一整数映射：`midi_origin_sample = 0`。
- 公式：`note_on_sample = midi_origin_sample + llround(note_on_seconds * rate)`。
- NoteOn 标称坐标：4410 samples @ 44.1 kHz，4800 @ 48 kHz。
- 声学起音相对标称 NoteOn 延迟：19 samples (0.431 ms) @ 44.1 kHz，23 samples (0.479 ms) @ 48 kHz。该延迟是钢琴起音/重采样，不是导出坐标偏移。
- 两个 rate 的延迟差 0.048 ms，与跨率重采样一致。

## 认证范围

认证：在固定官方 9.2.5 trial、固定 n69-v70 控制、固定 File -> Export 流程下，12 个 WAV 共享 `midi_origin_sample = 0`，时间偏移线性，48 kHz 逐样本精确，44.1 kHz 在 ±2 samples 内。

不认证：其他音高/力度、其他插件版本或 edition、真实钢琴弦身份、其他 producer 的 MIDI 导出原点、holdout 单元。

## 协议更新

- `pilot/origin-certificate-v1.json`（SHA-256 `192bac2a5192f5551cc649fc064cae57f7bfab3baeb0eb0cefcbb8e3bec10d51`）记录 12 个 WAV 的 SHA、帧数、onset、线性检验和未认证范围。
- `pilot/input-render-contract-v3.json` 与 `pilot/validation-v3-preregistration.json` 的 `reference_origin.status` 已改为 `authenticated`，并绑定证书 SHA。
- `validation-eval --check-plan` 移除 `reference_origin:*` 阻塞；仍保留授权、entry gate、reference timing verifier、工具散列、status 和 prerequisites 阻塞。

## 剩余阻塞

- 5 项授权（protocol/matrix/capture/freeze/formal evaluation）尚未批准。
- entry gate 尚未冻结。
- `reference_timing_verifier_not_available`：PPA 尚未支持 `reference_origin_authenticated` 证据角色。
- 3 个工具散列未绑定。
- status 仍为 `draft_pending_review`。
- unresolved prerequisites 仍包含 matrix/data roles、capture、freeze、holdout 与独立分析冻结。


## Reference timing verifier 实现（2026-10-18）

- `pilot-partial-analysis.py` 新增 `reference_origin_authenticated` 证据角色：
  - `parse_smf_note_timeline` 解析 format 0/1、PPQ、tempo map 与 NoteOn/NoteOff；拒绝 SMPTE、缺失事件或同 note 多个候选；
  - `load_reference_origin_timing` 校验证书 SHA-256/status/整数 `midi_origin_sample`、MIDI SHA-256/tick/秒、WAV SHA-256/rate/frames/channels/bits；
  - `note_on_sample`/`note_off_sample` 只由 `midi_origin_sample + llround(seconds*rate)` 计算，不接受报告自报坐标、首非零或相关对齐；
  - 参考 WAV 起点前 dither 允许，能量仅作非门禁诊断；`validate_timing` 要求 `wav_sha256`、`certificate_sha256` 与 `reference_origin_certified=true`。
- 新工具 `pilot/tools/make-reference-timing-report.py` 从证书 + 实际 MIDI + 实际 WAV 生成逐 unit 报告，并在写出后立即调用 loader 自检；路径以报告目录相对路径记录证书/MIDI，便于跨 WSL/Windows 评估。
- 验证：PPA 24/24、evaluator 44/44 测试通过；44.1 kHz 与 48 kHz 诊断 WAV 均生成报告（4410/185220 与 4800/201600 samples）；端到端 `--wav ... --timing-report ...` 冒烟成功，窗口坐标来自证书公式。
- `validation-eval --check-plan`：`reference_timing_verifier_not_available` 已消失，`reference_timing_verifier_available=true`。新增 `method_qualification:current_snapshot_changed`：修改 PPA 后旧方法资格证据绑定的 `analysis_tool` SHA 不再匹配当前文件。该 blocker 必须通过重新资格或重新绑定方法证据关闭，不能静默改 SHA。
- 当前仍剩 13 个 blocker：五项授权、entry gate 未冻结、方法资格快照变化、status draft、三个工具散列未绑定、unresolved prerequisites、v3 formal method 未就绪。verifier 本身不再阻塞。


## 方法资格重新运行与 v3 绑定（2026-10-18）

- 用户批准重新运行/更新方法资格证据，关闭 `method_qualification:current_snapshot_changed`。
- 活动登记 `method-qualification-window-refusal-v1.json` 仅更新 `execution.approval_note`；88 用例、4 控制、阈值与停止策略未变，登记 SHA 变为 `68bc797d…`。
- 新 seal 绑定登记 + `meter-qualification.py` / `pilot-partial-analysis.py` / `partial-observer.py` / `validation-eval.py` / `validation-eval-tests.py`；在全新批次执行一次完整 qualification。
- 结果：`qualified`，88/88 用例、4/4 控制、封印绑定的 evaluator 回归通过；`aborted=null`、`cases_failed=[]`、`controls_violated=[]`，9 项 pass conditions 全 true。
- 新快照身份：`analysis_tool=67fcf9df…`、`evaluator=4756071b…`、`observer=76d727a3…`、`evaluator_regression=23debaea…`、`qualification_script=b566ca1b…`、`registration=68bc797d…`。
- 大批次 `a5-requalification-20261018-090000`：201 文件 / 224,438,989 字节，manifest `e5430f50…`，独立原生 Windows 核验 17 项全通过（`archive-verification.json` SHA `de439381…`）。
- 绑定批次 `a5-requalification-binding-20261018-092200`：9 文件 / 194,209 字节，manifest `effb630f…`，核验 16 项全通过（`archive-verification.json` SHA `b668c764…`）。
- v3 `completed_method_evidence` 指向新报告；`contracts.method_qualification_plan.sha256` 更新为新登记。`--check-plan` 中 `method_qualification.current_snapshot_qualified=true`、`current_sources_match=true`，该 blocker 已消失。
- 剩余 12 项：五项授权、entry gate 未冻结、status draft、三个工具散列未绑定、unresolved prerequisites、v3 formal method 未就绪。参考原点已另行认证，但本资格不重新认证真实钢琴弦身份、正式留出或 A6/A7。


## 工具身份绑定与 entry gate 冻结（2026-10-18）

- 用户批准：绑定 `analysis_tool` / `evaluator` / `partial_observer` 实测 SHA，移除 3 个 `tool_identity_unbound`；依次批准 protocol/matrix、capture 与 freeze；冻结 entry gate。
- 工具绑定：`analysis_tool=67fcf9df…`、`evaluator=4756071b…`、`partial_observer=76d727a3…`。`--check-plan` 三项 `matches=true`。
- 契约冻结：`frequency-observable-contract-v3.json`（`3831b1ca…`，`v3_formal_method_ready=true`）与 `input-render-contract-v3.json`（`92a26c0f…`，`formal_readiness=true`）的 SHA 已绑定；`method_qualification_plan` 与 `reference_origin_plan` 也已绑定。
- 授权：`protocol_approved`、`matrix_approved`、`capture_authorized`、`freeze_authorized` 均为 true；`formal_evaluation_authorized` 仍为 **false**。
- 前提：4 个 unresolved prerequisites 全部标记 resolved 并保留在 `resolved_prerequisites`；`unresolved_prerequisites=[]`。
- Entry gate：`status=frozen_before_validation_rendering_or_inspection`，`entry_gate_frozen.preregistered_before_any_rendering_or_inspection=true`，冻结时间 `2026-10-18T09:08:24.700059+00:00`。
- `--check-plan`：唯一剩余 blocker 为 `authorization:formal_evaluation_authorized`，`execution_allowed=false`。工具身份、契约散列、方法资格、参考原点与 entry gate 均通过。
- 证据批次 `a5-freeze-20261018-093000`：12 文件 / 97,390 字节，manifest `41c0b594…`，独立原生 Windows 核验 27 项全通过（`archive-verification.json` SHA `b241c1b1…`）。
- 未授权：正式评估、参考启动/采集执行、验证渲染/检视、生产 B/DSP 修改、历史改判、A6/A7 或 v3 验收声明。
