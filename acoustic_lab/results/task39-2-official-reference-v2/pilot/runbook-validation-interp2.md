# Task 39-2 validation-interp2 采集与评估执行手册（runbook v1.1）

> 本手册沿用 `runbook-validation-interp.md` 的执行套件与已登记误差门槛，增加用户批准的 B 表冻结与单次验收上限。
> **执行状态（2026-10-14）：本手册已按授权完整执行并消耗**——48/48 单元采集，唯一一次 guarded 判决为**证据不足**（32 个可评估单元全部达标；12 个 n88 单元参考侧无法收敛、4 个 n67-v47 单元可比分音不足）。本批不重开、不扩采、不补开替代批次；历史手册中的续采建议不构成本批授权。

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
2. 生产冻结与一次验收上限已获批准，不等于本批采集授权；预登记当前保持 `draft_pending_user_approval`，待用户批准完整工作区协议与启动后才冻结执行快照。
3. 执行批准时核对固定矩阵、状态/文件保护、进入门禁及 §0.1 停止条件；不将待批准草稿直接当 frozen 运行，不提前打开本次新参考留出声音。
