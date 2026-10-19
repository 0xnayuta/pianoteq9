# Task 39-2 validation-interp2 采集与评估执行手册（runbook v1.1）

> 本手册沿用 `runbook-validation-interp.md` 的执行套件与已登记误差门槛，增加用户批准的 B 表冻结与单次验收上限。
> **执行状态（2026-10-14）：本手册已按授权完整执行并消耗**——48/48 单元采集，唯一一次 guarded 判决为**证据不足**（32 个可评估单元全部达标；12 个 n88 单元参考侧无法收敛、4 个 n67-v47 单元可比分音不足）。本批不重开、不扩采、不补开替代批次；历史手册中的续采建议不构成本批授权。
> **工具修订边界**：下方采集与正式评估命令是已执行的历史流程，不授权重新运行。工作区评估器现已修复数值准入/分类并增加冻结散列门禁；原冻结协议不改散列来追认新工具。旧判决复现须用对应不可变工具快照，新工具仅按 §8 显式诊断，不覆盖旧输出。

## 0. 差异总表（相对 runbook-validation-interp）

| 项目 | validation-interp | validation-interp2（本批） |
|---|---|---|
| 音高 | 25/27/53/59 | **29/55/67/88**（F1/G3/G4/E6；全部为首次使用音高） |
| 力度 | 47/79/107 | 47/79/107（同） |
| 采样率 / 重复 | 44100/48000 × 2 | 同 |
| 单元 / 会话 | 48 / 16 | 48 / 16 |
| 会话命名 | s01-n25-44100-rep0 … s16-n59-48000-rep1 | **s01-n29-44100-rep0 … s16-n88-48000-rep1**（顺序：音高 29→55→67→88，组内 44100 rep0→rep1、48000 rep0→rep1） |
| stimulus | `stimulus-interpval/` | `stimulus-interpval2/`（`make-stimulus-corpus.py --notes 29,55,67,88 --velocities 47,79,107`） |
| 预登记 | `validation-interp-preregistration.json` | `validation-interp2-preregistration.json` |
| 评估器 | `interp-validation-eval.py`（矩阵硬编码） | **`validation-eval.py`**（矩阵与工具散列从预登记 JSON 读取） |
| 方法修订 | amendment-3/4 | **amendment-1/2/3/4/5**（新增候选强度守卫，G=20 dB） |
| 敏感性并列 | — | 评估产物必须并列 guarded 与 legacy（`--refinement-guard-db off`）关键统计（amendment-5 §4.6） |
| 依赖链 | 仅钉评估器散列 | **同时钉评估器与其 import 的分析工具散列**（amendment-5 §6） |

### 0.1 冻结范围与停止条件（优先于继承手册）

- 生产表冻结为 `Piano88KeyTable.h` SHA-256 `c1997c904115ca23bdb1c9bbeb1d41542b25d8f7ed1dce0234109649da91a5b1`，19 表节点 = 17 实测锚点 + 2 文献外推节点；停止追加训练音高、锚点与插值/外推修订。
- 本批只验证该表：最多 48 单元 / 16 冷会话、一个正式批次和一次 guarded 最终评估；不更换 29/55/67/88、力度、rate 或重复矩阵，不新增会话或补开替代批次。legacy 仅作原登记的敏感性旁证，不是第二次判决。
- 可比较分音机械遵守 amendment-3：MIDI <72 用 n≥7，72–95 用 n≥5，≥96 不排除；基准 m 为最小共同可比分音，不计入 RMS/max，非基准样本 ≥2，RMS ≤1 / max ≤3 cents 不变。
- 进入门禁失败记未执行/阻塞；采集中出现不可恢复的身份、受保护状态或参数状态错误即停止，按既有受控流程安全收尾，不自动强杀。
- 固定矩阵全部输入/状态/内容/参考族质量合格，且 `units_total = units_evaluable = units_passing = 48` 才可记所选条件通过。不能仅凭命令 exit 0、形式 accepted 或排除失败行后的子集计数声明通过。
- 任一可评估单元超界记不通过；缺单元、族质量不合格、可比分音不足或分析错误记证据不足；两类缺口并列记录，不以不充分掩盖已确认失败。通过、不通过或证据不足均结束本 Task 39-2 采集计划。
- 保持 B 表、判据、历史判决与归档原件不变；不在本集拟合、不自动修工具后重判、不追加训练或注册下一验证集。原手册有界 GUI 动作重试只服务本批既定单元，不增加正式批次或评估次数。
- n88 尚无本次参考声学证据，分音是否充分须如实观察；不足不允许删除或换成有利音高。通过只支持登记的抽样条件，不认证 85–108 全域或真实琴型。


## 1. 批次前置（一次）

与 validation-interp 相同（批次根、launcher/prefs 复制、stimulus 逐文件散列核验、基线自检、受保护快照 before、preflight-protection），差异为：

```bash
python3 "$PILOT/tools/make-stimulus-corpus.py" --out-dir "$BATCH_WSL/stimulus" \
  --reference <A4-v70.mid> --notes 29,55,67,88 --velocities 47,79,107
```

进入门禁（全部满足才进入会话）：
1. 完整工作区预登记已获执行批准并在任何本批渲染前置为 frozen，另有明确采集启动授权；`closure_policy.capture_authorized` 与授权记录一致；
2. 生产表、候选表、评估器及 import 分析工具实际散列与预登记逐一一致（production table `c1997c90…`、analysis tool `0255ae71…`、evaluator `a4b9c9bc…`、candidate table `300b0680…`），不把评估器“仅记录散列”当作门禁已经强制校验；
3. stimulus 与登记清单逐文件散列一致，矩阵与 reference/native trial 禁键映射无冲突；
4. 受保护快照 before 生成成功，沿用官方 EXE、认证 FXP 与 215 项基线；本次没有已有正式批次或已执行的 guarded 判决。

## 2. 会话流程

与 `runbook-validation-interp.md` §2.1–§2.7 逐条相同（会话目录/context.json；prefs-seed；后台启动 + stdio 重定向；
lifecycle-created 等待；GUI 准备（G1/G3–G5 跳过、G2/G6 执行）；RPC prepare + 215 项基线断言；
单元循环 ×3（v47→v79→v107：unit-before → GUI 导出 E1–E4 → unit-after → pilot-verify）；close + lifecycle-exited；
受保护比对；session-receipt）。单元命名 `n<note>-v<vel>-<rate>-rep<n>`；stimulus `n<note>-v<vel>.mid`。

## 3. 批次收尾（一次性评估）

先完成固定矩阵的身份/状态/内容与参考族质量检查；任何不可恢复缺口按 §0.1 停止，不以新会话替换失败单元。完整输入具备后才运行 guarded 最终评估；从其完整输出逐单元判定，通过/不通过/证据不足均保留且不重判。

```bash
PILOT=/root/repos/pianoteq9/acoustic_lab/results/task39-2-official-reference-v2/pilot
# 1) 48 单元状态汇总（同 validation-interp）
# 2) 最终受保护比对
# 3) 参考侧族质量（interpval2 preset；不构成判决）
#    —— interpval2 输入网格已完成；工具与 import 散列按当前预登记硬核对，
#       无需再新增网格或变更分析算法
python3 "$PILOT/tools/pilot-partial-analysis.py" --batch "$BATCH_WSL" --out "$BATCH_WSL/analysis" --preset interpval2
# 4) devpiano 侧渲染（临时渲染测试：29/55/67/88 × 47/79/107 × 双率、A4=440、5.2 s、24-bit、
#    velocity/127；与 validation-interp 渲染逐参数同构）
# 5) 唯一一次最终评估（amendment-3/4 判据 + amendment-5 守卫；失败即消耗本集）
python3 "$PILOT/tools/validation-eval.py" \
  --preregistration "$PILOT/validation-interp2-preregistration.json" \
  --reference-batch "$BATCH_WSL" --dev-render <devpiano 渲染根> \
  --out "$BATCH_WSL/analysis/validation-eval.json" \
  --candidate-table "$PILOT/validation-interp2-candidate-table.json"
# 6) 敏感性并列（amendment-5 §4.6；仅记录，不参与判据）
python3 "$PILOT/tools/validation-eval.py" \
  --preregistration "$PILOT/validation-interp2-preregistration.json" \
  --reference-batch "$BATCH_WSL" --dev-render <devpiano 渲染根> \
  --out "$BATCH_WSL/analysis/validation-eval-legacy.json" \
  --candidate-table "$PILOT/validation-interp2-candidate-table.json" \
  --refinement-guard-db off
# 7) 归档（先写 meta.json，再执行；原件保留）
python3 "$PILOT/tools/archive_pilot_batch.py" --meta "$BATCH_WSL/meta.json"
# 8) 文档追加：_index/evidence-catalog.md 新节 + devpiano current-iteration 实施记录
```

## 4. 禁令清单

与 `runbook-validation-interp.md` §4 逐条相同（GUI 白名单、禁止反复切换、禁止 Freeze/面板修改、
禁止会话中改设备、禁止未验证快捷键、失败重试 ≤1 且显式记录、禁止自动强杀、one-shot 纪律）。

## 5. 失败/挂起处置树

沿用 `runbook-validation-interp.md` §5 的 P1–P11 安全处置，续采或新批次建议受本手册 §0.1 覆盖；任何分支均不授权新增会话、替换矩阵、重新判决或解除生产 B 冻结。

## 6. 会话检查单

与 `runbook-validation-interp.md` §6 逐条相同。

## 7. 执行授权与冻结复核

1. `interpval2` 网格已完成，分析工具散列为 `0255ae71…`；通用评估器已按既有 amendment-3 修正音区分音边界，散列为 `a4b9c9bc…`。原归档草稿的 `80fa2c9f…` / `2358d5bf…` 不作为本工作区版本的执行身份。
2. 执行前草稿曾保持 `draft_pending_user_approval`；随后用户批准完整工作区协议与启动，执行快照冻结为 `frozen_before_validation_rendering_or_inspection` 并完成一次验收（现已消耗）。原冻结协议的采集授权字段记录当时授权，不构成新采集或重判授权。
3. 执行批准时核对固定矩阵、状态/文件保护、进入门禁及 §0.1 停止条件；不将待批准草稿直接当 frozen 运行，不提前打开本次新参考留出声音。

## 8. 有界量测资格与诊断入口（2026-10-14）

用户批准 A1 匹配初始化/逐窗失败报告与 A2–A3 最小共享观察器/独立资格设计；保留静态 B 的独立验证目标。未批准新参考采集、B 调参或替换验证条件。所有执行在 Windows 原生 Python、隔离 NumPy/SciPy 环境运行，WSL 仅编辑脚本。

- `tools/validation-eval.py --diagnostic-only`：矩阵仍读原预登记；参考族必须满足两个窗口的独立预测、充分性和窗间/重复稳定性，才进入对照统计。六个互斥状态为 `missing_input`、`analysis_error`、`reference_rejected`、`insufficient_comparable`、`comparison_failed`、`comparison_passed`；零可比分音、只有基准或一个非基准样本均计不足，不漏行。散列不匹配时禁止登记评估；无论模式均拒绝覆盖已存在的输出。`units_evaluable`/`units_passing` 是数值门禁后的对照统计，不是弦身份或完整物理准入证书。
- `tools/validation-eval-tests.py`：纯内存回归覆盖数值超界但 status=ok、缺/重复留出、窗口/重复发散、可比较音区边界、零样本/基准排除及完整分类；不是文案或结构快照测试。
- `tools/meter-qualification.py --check-registration` 仅作登记元数据校验，不授予或恢复角色执行权。`method-qualification-window-refusal-v1.json` 已按单独授权完整执行一次，原始qualified仅限其预登记有限合成域；seal已消费，批准后的登记和源码保持字节不可变，保留的approval=true不是下一轮许可。实际执行、原始PCM／逐窗输出、只读完整性审阅和单批授权关闭入口为 [`window-refusal-qualification-verification.json`](window-refusal-qualification-verification.json)；前瞻和准备快照分别保留在 [`window-refusal-qualification-review.json`](window-refusal-qualification-review.json)、[`window-refusal-preparation-verification.json`](window-refusal-preparation-verification.json)。不得重跑、补批、改预期、另造seal或换目录恢复／扩大资格；旧A5、完整84例、NoteOn及更早v3的原判决与消费证据保持。后续已单独批准对齐活动completed_method_evidence、对应登记及当前方法状态；真实Windows原生 `python -B pilot/tools/validation-eval.py --check-plan --preregistration pilot/validation-v3-preregistration.json` 已核验新证据和当前六输入匹配，退出3且仍不可执行，见 [`v3-method-binding-verification.json`](v3-method-binding-verification.json)。该准备复核不重跑资格、不读生产者PCM、不创建seal，也不认证参考原点、真实弦身份或完整v3验收；其他未决项、正式授权／冻结与参考时序角色阻断保持，不放行A6/A7。
- **runner 窗级输入契约**：`frames_boundary` 必须保留 W1/W2，W1 正常，且只有预登记为 `rejected`、对应窗口明确为 `not_ok` 并实际超出一致的注册/PCM帧数时，才在候选提取前记录 `observer_lane.windows[window].status=input_refused`。这不是共享观察器返回的状态、声学弃权或分音认证；该窗不提候选、不调用观察器、不裁剪或补零。合法窗的 `input_accepted` 只表示输入界合法，后续仍须满足原观察/区域/家族义务；任何真实异常仍失败。窗口记录缺失、界被截短、伪造拒绝或拒绝窗带探针均为评分违例；`samples` 是原请求长度，`frames` 是实际可用总帧数。旧资格原判与封印输入不改，本修订和自有开发数据不构成新独立资格。
- `tools/family-hypothesis-diagnostic.py --batch <已消耗批次> --out <新目录>`：固定 n29 既有三力度/双率/两重复与预声明子集/窗口，逐线自检约束时域结论；留出从原谱重新识别，选峰敏感性并列，不选最有利参数、物理机制或正式结论。

旧合并矩阵的结论保留：原分析器与局部 SNR 候选未排除未分辨混合族假阳性。现行 `partial-observer.py` 使用实际离散 Hann 复数响应，比较单频/同频双衰减/两频/三频解释；输出 `single_component_adequate` / `resolved_components` / `ambiguous`，条件区间不认证物理弦身份。PPA 从第 1–6 分音起步，逐窗保留阶段/种子失败、原 FFT 候选与观察证据；失败或弃权窗口不被另一窗口替代。参考门禁同轮消费观察区间与独立留出，原 >=5 分音、>=3 训练、>=2 留出及 RMS/max 标准保持。

方法资格登记不是 v3 最终验收协议。新的 NoteOn 方案见 §11；旧 `method-qualification-v3.json` 及已消费结果不改写。完整资格不足时不冻结 v3、不启动新采集；双分音区间或动态包络不替代静态 B 验收。历史复现使用批次内归档工具；现行工具禁止对旧散列重新正式判决。实际执行及证据入口只维护在 [devpiano 当前迭代](https://github.com/0xnayuta/devpiano/blob/main/docs/roadmap/current-iteration.md#task-39-2受证据约束的逐键非谐性校准)。

## 9. AM/包络独立研究（不开放采集）

- `tools/am-envelope-study.py --registration pilot/am-envelope-preregistration.json --role development --out <新目录>`：仅合成研究，包络解释与既有静态单分量结果分列；不读取旧参考、不改原门禁或 B 表。只拟合前段，对独立后段原始采样做预测，真值只在观察后用于误差核验。
- `--role qualification` 还必须提供执行前源码封印 `--seal <JSON>`，其中 `role=am_envelope_method_qualification`、`files` 精确绑定研究脚本、AM 模型、原观察器和预登记的绝对路径/SHA-256；依赖不符或输出已存在即拒绝。完整一次执行并保留结果；改动后不得把已观察的资格配方重新称为未触碰。
- AM 与相干三音可具有相同 PCM，包络及条件载频成功不证明唯一来源。极慢 AM 在有限精度下也可能被现有单分量模型接受，不能解释为“无 AM”。研究资格不替代原 A1–A3 完整量测资格，不开启新参考采集或 v3 冻结。


## 10. 可比量与 A4/A5 准备契约（不开放采集）

- [`frequency-observable-contract-v3.json`](frequency-observable-contract-v3.json) 区分合格静态线、多分量、条件 AM 载频和原始峰。同一比较器先要求两侧完整族、两窗、观察区间/留出/重复均合格；单弦 MIDI21..35 可从第1分音起比较候选，多弦36..71仍第7起、72..95第5起、>=96第1起。所有混合证据保留并整族拒绝；候选不能替代准入，AM 不覆盖弃权或证明唯一来源，原数值/充分性与时序预算保持。
- [`input-render-contract-v3.json`](input-render-contract-v3.json) 规定双方 MIDI 事件与采样坐标：保留认证的 0.1 s NoteOn、4.2 s NoteOff、5.2 s EOT；dev 端不裁去前静音、不归一化，以相同 MIDI 事件的块内采样偏移驱动实际合成器。W1/W2 以 NoteOn 为原点，W2 半开区间恰好结束于离键，不把旧 PPA 的绝对窗口追认为新坐标。
- A4 准备只使用已消费的 n69-v70 认证刺激及内部控制；Windows Debug 实际 PCM、独立 SMF 解析与运行事件记录用于检查输入/渲染，而不是新参考或 B 通过证据。生成器要求全新目录，拒绝覆盖已有 MIDI/receipt。
- **参考端限制**：实际首个非零采样不等于已认证的 MIDI 导出原点；文件时长和最有利的 dev/ref 相关性对齐也不能替代原点证据。没有绑定参考端事件与导出坐标前，不冻结 v3、不扩大对照声明。
- A5 仍为 [`validation-v3-preregistration.json`](validation-v3-preregistration.json) 草案。同一评估器实际核验 `qualification.completed_method_evidence` 的报告/manifest/封印/消费标记、原源码快照、角色完整性与日志；`method_qualification.completed_evidence.verified` 表示原快照实证有效，`current_snapshot_qualified` 还要求当前依赖匹配。原有限方法 qualified 不与 v3 就绪混用；当前评估器/回归已变，新独立覆盖尚未执行。原点、矩阵、工具冻结和授权独立阻断，不改标签放行，不重放已消费资格。
- **实际入口**：`tools/verify-input-render.py --contract <input-render-contract-v3.json> --midi <SMF> --wav <render.wav> --receipt <render-receipt.json> --out <全新 JSON>` 从真实 SMF/PCM/运行事件独立验证；只报告输入与 dev 渲染契约，不估计 B、不认证参考 origin。消费者的完整源码与 Debug 编译配方保留在 A5 草案所指归档，需要时临时恢复到 `source/tests/Task392V3RenderConsumer.cpp`，不接入永久 CMake/单元测试。
- 在 Windows 原生 Python 执行 `tools/validation-eval.py --check-plan --preregistration <validation-v3-preregistration.json>` 可取得当前阻塞报告；退出码 3 表示仍不可执行，不是声学失败或通过。`--diagnostic-only` 不绕过草案和契约门禁，已有输出拒绝覆盖。

## 11. NoteOn 坐标接入与后续资格/取证方案

- `pilot-partial-analysis.py --wav <已消费 dev WAV> --note 69 --timing-report <A4 independent-verification.json> --out <新目录>` 读取同一 WAV 的散列绑定报告，输出 `partial-analysis.json`，保留 NoteOn 相对窗、实际整数 `[start_sample, stop_sample)` 及分析结果。缺失/错配/篡改报告不回退到文件绝对窗，dev 证据不能升级为 reference 原点。
- 现行 `analyze_samples` / `analyze_unit` 必须显式关键字 `timing`。v3 `note_on_relative` 使用 `note_on_sample + llround(relative_seconds*rate)`，频谱和受保护观察器最终取相同整数样本；释放边界按半开区间处理。消费数据诊断明确使用 `file_absolute` 并保留原截断口径，不追认历史绝对分析为相对坐标证据。
- [`method-qualification-noteon-v3.json`](method-qualification-noteon-v3.json) 保留原已消费有限合成域的快照实证，不转记为变更后方法的新资格。正例必须有实际准入能力，混合/时变/编号错误不能冒充静态族；AM 边界即使获得静态近似准入，仍须满足原独立频率、编号、B、留出与稳定性预算。全部义务与停止规则事先登记，不按通过率豁免。
- 独立资格须显式批准、绑定登记与五个源码的外部封印、完整未触碰角色；封印开始执行即独占消费，异常/遗漏/失败/中断全部保留后停止，不换目录、改标签、换封印或补批恢复资格。执行状态和一次性结果以批次原始回执及 devpiano 当前迭代为准，本段不授予新的执行权限。封印绑定的六态评估器回归是方法门禁，参考原点认证及真实采集/正式评估是后续独立放行条件，不反过来成为方法资格前提。
- [`reference-origin-evidence-plan-v3.json`](reference-origin-evidence-plan-v3.json) 仅制定取证方案：先取得独立的事件—导出帧映射依据，再审阅有界诊断。若无法取得依据，就停止，不以时长、首个非零采样、重复一致或最有利相关性代替认证。提议的诊断上限不等于采集授权；当前不启动 Pianoteq/GUI、不生成新参考。
- 有界只读能力核验已完成，处置 `origin_not_authenticated`；停止参考诊断采集，其他只读契约工作继续。精确手册及官方版本绑定回执未建立所选离线导出路径的事件—整数帧映射；旧 9.1.2 帮助/41 方法清单/serve 页面不得作为官方 9.2.5 依据，七个特定候选方法失败也不是接口不存在的普遍证明。
- [`a5-implementation-verification.json`](a5-implementation-verification.json) 是获批两项实现的事先验证登记，只授权相关回归、自有合成 development 与准备级入口。原提案已在 `a5-contract-review-20261015-115821/metadata-after/research/pilot/` 完整归档并从活动路径退役；当前只保留一个评估器/比较实现。多弦分化区仍排除，整族拒绝及原预算/时间不变；新独立资格、替代时序、实际参考诊断和正式评估仍须分别批准。
- [`method-qualification-a5-v1.json`](method-qualification-a5-v1.json) 是变更方法的前瞻有限覆盖；已按另行明确授权在 `a5-qualification-20261016-040725` 完整执行一次，原始结果not_qualified，seal已消费，development未执行。历史种子、有效声学核心及note/B/offset排重边界保持；配对/重复/双率是设计簇，不冒称独立重复样本。新鲜正向矩阵与已消费控制分开记账，不以部分通过扩大真实物理或参考来源声明。
- **runner契约已闭合，不替代资格判决**：`check_execution` 接受严格布尔false；`comparison_expectations` 与 `check_cross_case_groups` 要求完整唯一的role/pair、a/b成员、键号/采样率及正整数基准/候选/非基准预期。`evaluate_group_gates` 保留唯一比较器的真实结果，再逐项核对；即使comparison_passed，任何身份/数量违例仍记comparison_pair_not_passed并阻断资格。未复制比较或单弦策略、增加负向/不对称pair或放宽预算；实现验证见 [`a5-runner-closure-verification.json`](a5-runner-closure-verification.json)。准备/回归/完整性通过均不能豁免本次低音正向准入遗漏与额外模态假阳性。
- **已消费后停止**：原批次先记录授权后登记SHA-256，再绑定五个定稿源码生成精确seal，并仅运行一次完整qualification、四个旧控制及同封印回归。当前A5登记是执行前冻结快照，不在消费后回写其前瞻状态字段而破坏已有散列；实际结论以 `G:/source/projects/devpiano-evidence/phase39/task39-2/a5-qualification-20261016-040725/verification-summary.json`、原始报告及消费标记为准。不换目录、seed、配方、源码或seal重跑，不以已消费数据补批；后续另批的修订/开发验证见下条，不恢复旧角色。旧completed_method_evidence与v3正式授权/origin门禁保持，参考/GUI/RPC/采集和生产改动仍未放行。
- [`a5-candidate-structure-development-verification.json`](a5-candidate-structure-development-verification.json) 事先登记了用户另批的两项最小修订与开发验证：PPA候选下界 `min(40 Hz,theory/2)`，较高音区保持原范围；PPA与评估器共用明确结构性异常的整族拒绝判据，普通低信息ambiguous不冒称混合，不改观察器拟合或探针宽度。Windows相关回归和自有低音/带外伴线双率开发冒烟通过，原充分性、数值与时间/比较契约保持。入口 `G:/source/projects/devpiano-evidence/phase39/task39-2/a5-candidate-structure-development-20261016-051007/verification-summary.json`；不是新独立资格，不能从开发结果或已消费控制恢复原not_qualified，后继覆盖须前瞻登记审阅并另批执行。
