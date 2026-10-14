# Task 39-2 validation-interp2 采集与评估执行手册（runbook v1）

> 本手册是 `runbook-validation-interp.md` 的后继版本：执行套件（launcher / 采集流程 / 处置树 / 禁令）
> 与 validation-interp 逐条沿用，仅矩阵、评估器与判定产物不同。**draft：待用户批准预登记后生效。**

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

## 1. 批次前置（一次）

与 validation-interp 相同（批次根、launcher/prefs 复制、stimulus 逐文件散列核验、基线自检、受保护快照 before、preflight-protection），差异为：

```bash
python3 "$PILOT/tools/make-stimulus-corpus.py" --out-dir "$BATCH_WSL/stimulus" \
  --reference <A4-v70.mid> --notes 29,55,67,88 --velocities 47,79,107
```

进入门禁（全部满足才进入会话）：
1. 预登记 `validation-interp2-preregistration.json` 已获用户批准并置为 frozen；
2. 工具散列与时点校验通过（analysis tool `80fa2c9f…`、evaluator `2358d5bf…`、candidate table `300b0680…`）；
3. stimulus 与登记清单逐文件散列一致；
4. 受保护快照 before 生成成功。

## 2. 会话流程

与 `runbook-validation-interp.md` §2.1–§2.7 逐条相同（会话目录/context.json；prefs-seed；后台启动 + stdio 重定向；
lifecycle-created 等待；GUI 准备（G1/G3–G5 跳过、G2/G6 执行）；RPC prepare + 215 项基线断言；
单元循环 ×3（v47→v79→v107：unit-before → GUI 导出 E1–E4 → unit-after → pilot-verify）；close + lifecycle-exited；
受保护比对；session-receipt）。单元命名 `n<note>-v<vel>-<rate>-rep<n>`；stimulus `n<note>-v<vel>.mid`。

## 3. 批次收尾（一次性评估）

```bash
PILOT=/root/repos/pianoteq9/acoustic_lab/results/task39-2-official-reference-v2/pilot
# 1) 48 单元状态汇总（同 validation-interp）
# 2) 最终受保护比对
# 3) 参考侧族质量（interpval2 preset；不构成判决）
#    —— 说明：pilot-partial-analysis.py 需新增 interpval2 输入网格（登记为批次前工具扩展，
#       算法/判据/窗口不变；扩展后的工具散列在预登记 entry gate 中登记）
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

与 `runbook-validation-interp.md` §5 逐条相同（P1–P11）。

## 6. 会话检查单

与 `runbook-validation-interp.md` §6 逐条相同。

## 7. 待决事项（批准前）

1. 工具扩展：`pilot-partial-analysis.py` 需新增 `interpval2` 输入网格（`NOTES` 29/55/67/88 + `PRESETS['interpval2']`
   + `velocities` 47/79/107 + help 文本）。该扩展改变工具散列，必须在本预登记置为 frozen **之前**完成并更新
   `entry_gate_frozen.analysis_tool.sha256`。
2. 音高选择复核：29（28-33 段）/ 55（52-57 段内）/ 67（60-69 长段）/ 88（84-96 段）——如需调整音高，
   在批准前修改矩阵与数据角色声明。
