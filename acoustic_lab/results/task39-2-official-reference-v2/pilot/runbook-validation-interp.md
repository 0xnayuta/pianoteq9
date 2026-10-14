# Task 39-2 interp 验证集采集执行手册（runbook validation-interp v1）

> 本手册是 interp-training runbook 的**验证集适配版**：执行套件（launcher / 采集流程 / 处置树 / 禁令）
> 与 interp-training 主体逐条沿用，不改任何采集脚本；差异为采集矩阵（验证音高 25/27/53/59 ×
> 力度 47/79/107 × 44.1/48 kHz × repeats 2 = 48 单元 / 16 冷会话）、**一次性（one-shot）评估纪律**与
> 预登记冻结（`validation-interp-preregistration.json`）。修订详情见 §7。
>
> 配套冻结资产：`validation-interp-preregistration.json`（entry gate：锚点/候选表/评估器/数据角色）、
> `validation-interp-candidate-table.json`（88 键候选表）、`stimulus-interpval/`（刺激与 receipt）、
> 实施与更正证据（`interp-anchor-correction-20261014-105438`）。
> 读者：主会话执行者。GUI 操作全部经主会话 windows-mcp 逐次核验与审批；非 GUI 步骤按下述命令执行。
> 纪律：不自动 commit；不静默重试；异常即记录并按下述处置树处理。
>
> **One-shot 纪律（本批核心约束）**：两侧渲染完成后仅执行**一次**最终评估；评估前不得窥视谱指标、
> 不选峰、不选种子、不在本集上调参；失败即消耗本集（下一迭代重新登记验证数据）。
> 数据角色：25/27 = 条件级留出（音高已消耗，用户 2026-10-14 确认）；53/59 = 未消耗音高
> （blind audit `94de2702…` 已核对）。B 表在本批不改。

---

## 0. 路径约定（每批次开始时确定一次）

| 变量（bash） | 值 |
|---|---|
| `PILOT` | `/root/repos/pianoteq9/acoustic_lab/results/task39-2-official-reference-v2/pilot` |
| `PWSH` | `/mnt/c/Program Files/PowerShell/7/pwsh.exe` |
| `BATCH_ID` | `validation-interp-<YYYYMMDD-HHMMSS>`（批次开始时确定） |
| `BATCH_PREFS_FROM` | `/mnt/g/source/projects/devpiano-evidence/phase39/task39-2/register-pilot-20261012-162401`（prefs 模板来源批次，归档副本，含 44100/48000 两套模板） |
| `BATCH_WSL` | `/mnt/g/tmp/devpiano-task39-2-$BATCH_ID`（批次根，WSL 视图） |
| `BATCH_WIN` | `G:\tmp\devpiano-task39-2-$BATCH_ID`（同根，Windows 视图） |
| `EXE_WIN` | `\\wsl.localhost\Ubuntu\root\repos\pianoteq9\binaries\Pianoteq_9.2.5_Windows\Pianoteq 9.exe` |
| `FXP_WIN` | `G:\source\projects\devpiano-evidence\phase39\task39-2\official925-standard-state-20261012-060228\session-2\private-home\AppData\Roaming\Modartt\Pianoteq\Presets\Task39-2 Controlled Validation\Task39-2 Flat Full State 20261012-060228.fxp` |

硬性事实（来源：已认证证据）：
- EXE SHA-256 `7fcb5b2385a753e2f7d0a9ed068692abe877ab65b438e70a3fe2b44879b278bd`（9.2.5.20260909，签名 Valid）。
- FXP SHA-256 `9f749ca99143c4b1e0760099b2d6aad83cc3e9a745aa57a0a535a481342cddc9`。
- 基线 `baseline/certified-export-state-215.json`（215 项；unison / sympathetic_resonance / duplex_scale_resonance / quadratic_effect 均应为 `0`）。
- 期望音频：DirectSound / 主声音驱动程序 / `<本会话 rate>.0` / buffer 2560。
- A4 = 440（与 interp-training 相同条件组）；trial 静音音高不含 25/27/53/59，逐单元以族质量门核实信号证据。

---

## 1. 批次前置（一次，全部通过才进入会话）

与 interp-training §1 相同（创建批次根 + 复制 launcher / prefs 模板 / tools 副本；生成 stimulus 并与
`PILOT/stimulus-interpval` 逐文件散列核验；基线自检；受保护快照 before；preflight-protection）。
差异：stimulus 生成命令为

```bash
python3 "$PILOT/tools/make-stimulus-corpus.py" --out-dir "$BATCH_WSL/stimulus" \
  --reference "/mnt/g/source/projects/devpiano-evidence/phase39/task39-2/gui-export-20261012-092853/stimulus/A4-v70.mid" \
  --notes 25,27,53,59 --velocities 47,79,107
```

并写入 `$BATCH_WSL/scope.json`（授权文本、矩阵、预登记引用与散列、数据角色）。

**批次门禁**：本批执行套件与 interp-training 逐字节相同（launcher 三脚本散列一致）；首个正式会话（s01）
的首个单元即为完整集成验证：`unit-before` 硬断言、GUI 导出、`unit-after` 硬断言、`pilot-verify` 独立审计
全部照常执行；任何失败按 §5 处置树停止并记录，不静默重试。

## 2. 会话流程（每会话重复 §2.1–§2.7）

流程与 interp-training §2.1–§2.7 逐条相同（会话目录/context.json；每会话 prefs-seed；后台启动 +
stdio 重定向；等待 lifecycle-created；GUI 准备（seed 播种下 G1/G3–G5 预期跳过、G2/G6 执行）；
RPC prepare + 基线断言；单元循环 ×3（v47 → v79 → v107：unit-before → GUI 导出（E1–E4）→ unit-after → pilot-verify）；
会话收尾 close + lifecycle-exited 核验；受保护比对；session-receipt.json）。
单元命名：`n<note>-v<vel>-<rate>-rep<n>`（如 `n25-v47-44100-rep0`）；stimulus `n<note>-v<vel>.mid`。

### 2.1.1 会话表（validation-interp：16 会话 = 4 note × 2 rate × 2 repeats）

| 会话 | note | rate | rep | 单元（v47/v79/v107） |
|---|---|---|---|---|
| s01-n25-44100-rep0 | 25 | 44100 | 0 | n25-v47 / n25-v79 / n25-v107（-44100-rep0） |
| s02-n25-44100-rep1 | 25 | 44100 | 1 | 同上（-44100-rep1） |
| s03-n25-48000-rep0 | 25 | 48000 | 0 | 同上（-48000-rep0） |
| s04-n25-48000-rep1 | 25 | 48000 | 1 | 同上（-48000-rep1） |
| s05-n27-44100-rep0 | 27 | 44100 | 0 | n27-v47 / n27-v79 / n27-v107（-44100-rep0） |
| s06-n27-44100-rep1 | 27 | 44100 | 1 | 同上（-44100-rep1） |
| s07-n27-48000-rep0 | 27 | 48000 | 0 | 同上（-48000-rep0） |
| s08-n27-48000-rep1 | 27 | 48000 | 1 | 同上（-48000-rep1） |
| s09-n53-44100-rep0 | 53 | 44100 | 0 | n53-v47 / n53-v79 / n53-v107（-44100-rep0） |
| s10-n53-44100-rep1 | 53 | 44100 | 1 | 同上（-44100-rep1） |
| s11-n53-48000-rep0 | 53 | 48000 | 0 | 同上（-48000-rep0） |
| s12-n53-48000-rep1 | 53 | 48000 | 1 | 同上（-48000-rep1） |
| s13-n59-44100-rep0 | 59 | 44100 | 0 | n59-v47 / n59-v79 / n59-v107（-44100-rep0） |
| s14-n59-44100-rep1 | 59 | 44100 | 1 | 同上（-44100-rep1） |
| s15-n59-48000-rep0 | 59 | 48000 | 0 | 同上（-48000-rep0） |
| s16-n59-48000-rep1 | 59 | 48000 | 1 | 同上（-48000-rep1） |

组织顺序：按音高分组（25 → 27 → 53 → 59），组内 44100 先行（rep0 → rep1）、48000 次之（rep0 → rep1）。
每会话 3 单元、单次采集；rep0/rep1 为独立冷会话重复。

## 3. 批次收尾（验证 one-shot）

```bash
# 1) 48 单元状态汇总 -> $BATCH_WSL/batch-summary.json（同 interp-training）
# 2) 最终受保护比对（before vs 批次结束快照）
# 3) 参考侧族质量（interpval preset；不构成判决）
python3 "$PILOT/tools/pilot-partial-analysis.py" --batch "$BATCH_WSL" --out "$BATCH_WSL/analysis" --preset interpval
# 4) devpiano 侧渲染（临时渲染测试，48 WAV；A4=440、velocity 47/79/107、5.2 s、24-bit，双率）
#    仅在两侧全部渲染完成后执行一次对照评估；评估前不窥视指标
# 5) 唯一一次最终评估（amendment-3/4 口径；失败即消耗本集）
python3 "$PILOT/tools/interp-validation-eval.py" \
  --reference-batch "$BATCH_WSL" --dev-render <devpiano 渲染根> \
  --out "$BATCH_WSL/analysis/interp-validation-eval.json" \
  --candidate-table "$PILOT/validation-interp-candidate-table.json"
# 6) 归档（先按实际结果编写 meta.json，再执行；原件保留不删）
python3 "$PILOT/tools/archive_pilot_batch.py" --meta "$BATCH_WSL/meta.json"
# 7) 文档追加：_index/evidence-catalog.md 新节 + devpiano current-iteration 实施记录
```

## 4. 禁令清单（constraints v2 §3 固化 + 本批 one-shot 增补）

1. GUI 白名单仅 §2.2 与 §2.4 列出的动作；**禁止**任何其它菜单探索。
2. **禁止** Standard/Stage 反复切换；`Try Pianoteq Standard → Switch to STANDARD` 仅允许在 §2.2（G6）执行一次。
3. **禁止** Freeze 面板交互；**禁止**打开 Presets/Parameters 面板做任何修改。
4. **禁止**在会话中修改音频设备、音量、采样率。
5. **禁止** Ctrl+E 之类未验证快捷键（导出只用 File 菜单鼠标点击）。
6. **禁止**静默重试：任何失败重试须在证据中显式记录（次数 ≤1）。
7. **禁止**对 Pianoteq 进程执行自动强杀；强杀须用户显式授权并记录。
8. **one-shot 纪律**：两侧渲染完成前不计算/不查看任何谱指标；评估只执行一次；不在本集上调参；
   失败即消耗本集。**禁止**以本批数据回调 B 表或判据。

## 5. 失败/挂起处置树

与 interp-training §5 逐条相同（P1 单元断言失败→全局暂停；P2 prepare 失败→停止会话；P3 close 挂起；
P4 导出缺失→1 次重试；P5 受保护文件变更→立即停止；P6 超 900 s→收尾；P7 试用限制迹象→暂停；
P8 unit-before 断言失败→全局暂停；P9 unit-after 断言失败→全局暂停；P10 断言失败先查输入数据本身；
P11 seed 播种后音频校验不符→回退手动 G3–G5 并记录）。

## 6. 会话检查单（执行时逐项勾）

与 interp-training §6 相同（preflight、启动/seed、GUI 准备、prepare+基线、单元循环四项、收尾、受保护比对、
receipt、mcp/gui-actions.json）。

## 7. 与 interp-training runbook 的差异

1. 矩阵：25/27/53/59 × 47/79/107 × 双率 × 2 reps = 48 单元 / 16 会话（训练为 26/52/57 × 41/70/98 = 36/12）。
2. stimulus：`stimulus-interpval/`（12 MIDI；receipt 逐文件散列）。
3. 预登记：`validation-interp-preregistration.json`（entry gate 冻结：锚点/候选表/评估器散列/数据角色）。
4. 评估：`interp-validation-eval.py`（amendment-3/4 口径）+ interpval preset；**one-shot**。
5. 其余（执行套件、prefs-seed、处置树、禁令主体）与 interp-training 逐条相同。
