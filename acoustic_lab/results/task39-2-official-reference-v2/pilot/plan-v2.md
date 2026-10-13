# Task 39-2 v2 Pilot 执行方案 v2（固化 constraints v2，待确认）

> 状态：**修订版（替代 `pilot-execution-plan-draft.md` 草案），未执行**。
> 依据：`task39-2-preregistration-v2.json`（协议与范围）；`pilot-b0-20261012-193620` 批次（导出流程事实与偏差）；
> `gui-export-20261012-092853` 批次（认证执行链与确定性证据）；constraints v2（b0 崩溃调查与参数漂移观察的固化结论）。
> 编制日期：2026-10-12。脚本套件见本目录 `pilot/`（工具已验证，见 §10）。

---

## 1. 范围（严格取自 v2 预登记，执行中不得增删）

| 项 | 值 |
|---|---|
| 音符 | 36 (C2)、48 (C3)、60 (C4) |
| 力度 | 41、70、98 |
| 采样率 | 44100、48000 |
| 重复 | 2（rep0 / rep1，跨独立冷启动） |
| 导出总数 | 3 × 3 × 2 × 2 = **36 个 WAV** |
| 采集格式 | WAV **24-bit、无 dither、无 normalize、current settings**；设备保持 44100/DirectSound/缓冲 2560 |
| 状态绑定 | FXP `9f749ca9…`（Flat、440 Hz）；每会话 FXP 加载后 215 参数必须逐项等于认证基线 |
| 激励 | 9 个受控 MIDI（`n<note>-v<vel>.mid`，与认证 A4-v70 逐位同构，散列见 `stimulus/receipt.json`） |
| 不做 | 不改 `B`/拉伸；不生成完整训练库；不打开封闭验证集；不改旧 GUI 脚本 |

## 2. 组织结构（12 会话 × 3 导出）

- **单元** = 1 个导出 WAV，命名 `<note>-<vel>-<rate>-rep<n>`（如 `n60-v41-44100-rep0`）。
- **会话** = 1 次独立冷启动（= 1 个计时单元，进程创建起 ≤900 s 硬窗口），产出同一 (note, rate, rep) 的 3 个力度导出。
- rep0 与 rep1 为**相邻的两次独立冷启动**（与 092853 的确定性证明同级口径）。

| # | 会话 | note | rate | rep | 导出单元（3 个） |
|---|---|---|---|---|---|
| s01 | n60-44100-rep0 | 60 | 44100 | 0 | n60-v41/v70/v98-44100-rep0 |
| s02 | n60-44100-rep1 | 60 | 44100 | 1 | 同上去 rep1 |
| s03 | n48-44100-rep0 | 48 | 44100 | 0 | … |
| s04 | n48-44100-rep1 | 48 | 44100 | 1 | … |
| s05 | n36-44100-rep0 | 36 | 44100 | 0 | … |
| s06 | n36-44100-rep1 | 36 | 44100 | 1 | … |
| s07 | n60-48000-rep0 | 60 | 48000 | 0 | … |
| s08 | n60-48000-rep1 | 60 | 48000 | 1 | … |
| s09 | n48-48000-rep0 | 48 | 48000 | 0 | … |
| s10 | n48-48000-rep1 | 48 | 48000 | 1 | … |
| s11 | n36-48000-rep0 | 36 | 48000 | 0 | … |
| s12 | n36-48000-rep1 | 36 | 48000 | 1 | … |

顺序理由：s01 与已认证流程（note 60 邻近、44.1 kHz）最接近；44.1 kHz 六会话先行（18 WAV，风险最低）；
48 kHz 六会话集中后置，其中 **s07 为 48 kHz 首会话，完成后强制复核**（b0 的 4 参数漂移疑似与 48 kHz 导出相关，未决）。

> **已消耗会话说明（2026-10-12）**：原 s01（n60-44100-rep0）已用于「FXP 异步应用窗口」缺陷发现与脚本 v2.1 修订验证
> （V1 正向：反例写入→加载→全量恢复 1024 ms 稳定；V2 负向：错误基线必报错），**未产出正式单元**，会话已正常 quit 关闭，
> 证据保留在批次根 `sessions/s01-n60-44100-rep0/`（含 diag/ 与 verify/）。**正式 Pilot 从新的 s01 重新开始**。

每个会话固定流程（详见 runbook）：受控启动 → GUI 准备（Welcome / 音频 / Standard）→ RPC prepare + 基线断言
→ 3 ×（unit-before → GUI 导出 → unit-after → 单元核验）→ RPC close → 退出与核验。

## 3. constraints v2 固化映射

| # | constraints v2 条款 | 固化机制 |
|---|---|---|
| 1 | 每计时单元 ≤900 s（自进程创建起）；不做 1200 s 余量假设 | `launcher/owned-session.ps1`：登记 `registered_deadline_utc`，到点写 `deadline-exceeded.json` 并打点（不改 GUI、不杀进程）；runbook 收尾纪律 |
| 2 | 每单元 pre/post 参数快照；drift ≠ 0 拒收 | `launcher/pilot-rpc.ps1` v2.1：每次 loadFile/loadMidiFile 后「稳定等待」（连续两次快照 digest 一致）再落盘权威快照；prepare 内置 215 项基线硬断言 + restore counterexample（反例写入→加载→全量恢复）；unit-before/after 内置 pre==基线、post==pre 断言；`tools/pilot-verify.py` 再作独立审计比对；`acceptance.json` 受/拒收 |
| 3 | 批次内禁用 Standard 切换（除冷启动准备的一次性切换）、Freeze 面板、非必需探索 | runbook 禁令清单 + GUI 白名单（仅列出的动作允许） |
| 4 | 导出经 File 菜单鼠标坐标点击；覆盖确认按 Overwrite；注意渲染延迟 | runbook 动作表（含等待与复读） |
| 5 | 挂起处置：记录 stdio → 不强期待 WM_CLOSE → 强杀须外部授权 | stdio 重定向模板（launcher-stdio.log）+ runbook 处置树 |

## 4. b0 遗留问题的处置

| b0 遗留 | v2 处置 |
|---|---|
| 4 高级参数在会话后段变为默认 1.00（归因未决） | **2026-10-12 s01 验证会话新发现**：`loadFile(FXP)` 返回 `result:null` 不等于状态应用完成——返回后 5 ms 采样到中间态（unison=1.00 / equalizer_switch=On 未恢复），消融实验显示 500 ms 采样已完全恢复（恢复窗口在数十~数百 ms 量级）。此前 prepare 立即读数即捕捉到该窗口。**b0 的「后段漂移」是否同源仍未定论**（b0 现象出现在会话后段，与加载后瞬间不同）；v2.1 以「稳定等待 + 全量基线硬断言 + 反例验证」防护：任何未恢复/漂移状态都会被拦截并记录，**首次 drift 出现即全局暂停**并报告 |
| 探索性 Standard 切换触发 Internal Error + 挂起 | 禁令清单 + 处置树；Standard 仅在冷启动 GUI 准备阶段一次性切换 |
| b0 会话超 900 s（注册边界）才收尾 | 硬窗口 + 会话时间预算（§7），超窗即收尾并作废未完成部分（2026-10-12 验证会话已实际触发一次，按 notice-only 处置正常结束） |
| 单导出耗时未分解（R4） | s01 即基准会话：从证据 utc 推导耗时表；超预算触发降级条款（§8） |
| 文件名/覆盖策略未固化（R5） | 每会话全新 private-home + 每单元独立 MIDI 名；正常无覆盖；重试遇覆盖确认按 Overwrite 并记录偏差 |
| R1/R2/R3（24-bit、48 kHz、连续多导出） | 已由 b0 关闭；v2 沿用其对话框事实 |
| R6 累计试用限制（未知） | 每会话监控；触发迹象即全局暂停 |

## 5. 验收标准

- **单元**：`acceptance.json` `accepted=true` —— pre/post drift = 0、pre == 认证基线（215 项逐项）、WAV 为 24-bit、采样率相符、双声道、时长 ∈ [5.2, 5.6] s、SHA-256 登记。另有脚本内置门禁：`units/<unit>/unit-<unit>-pre-baseline-assertion.json`、`post-consistency.json` 的 `ok=true`（pre==基线、post==pre）。
- **会话**：exit 0（正常 quit）、无 deadline 超窗、3 单元全部 accepted、受保护文件比对 0 变化、无残留进程；`rpc/prepare-baseline-assertion.json` `ok=true`、`rpc/prepare-counterexample-delta.json` 四项全部 `deviated=true`。
- **批次**：36 单元状态表完整（含任何拒收的原因与证据）；rep0/rep1 同组合交叉对比（逐位一致 = 确定性再证；不一致 → 记录差异幅度移交分析）；全量证据归档 + 四索引追加 + `evidence-catalog.md` 追加。

## 6. 决策项（待用户确认）

| # | 决策 | 推荐 |
|---|---|---|
| E1 | 组织：12 会话 × 3 导出 | 推荐（会话数=草案口径；单会话预算充裕） |
| E2 | 顺序：44.1 kHz 全组先行，rep0/rep1 相邻冷启动 | 推荐 |
| E3 | 暂停条款：首次 drift / s07 复核失败 / 挂起 / 超窗 / 受保护变化 → 全局暂停报告 | 推荐 |
| E4 | 对话框 HQ 选项：`use current settings`（不启 high quality、不 normalize） | 推荐（b0 已验证同口径导出链） |
| E5 | 授权节奏：脚本确认 → s01 执行并复核（含耗时分解）→ 通过后连续 s02–s12 | 推荐 |

## 7. 会话时间预算（软约束，硬窗口 900 s）

| 阶段 | 预算 |
|---|---|
| 启动 → GUI 准备完成 | 90–180 s |
| RPC prepare + 基线断言（含反例写入与稳定等待） | 20–35 s（v2.1 实测 ≈3 s） |
| 每单元（RPC + GUI 导出 + RPC + 核验） | 50–95 s × 3（v2.1 脚本侧每次约 +1–2 s 稳定等待） |
| close + 退出 | 20–40 s |
| **合计** | **约 290–490 s**（含缓冲 < 900 s） |

## 8. 降级与中断条款

- 若 s01 实测单单元 > 120 s 或全会话 > 750 s：后续会话降为 **2 导出/会话**（v98 单元另起会话，总会话数 12 → 18）。
  降级在 s01 复核时向用户报告并确认后执行。
- 任一暂停条款触发：停止启动新会话；已完成的证据保持原样；不自动重试、不静默重启（090315 先例）。

## 9. 规模与产出

- 约 12 个受控会话（每会话 5–8 分钟操作 + 4–5 分钟核验/记录），跨多个工作日；
- 产出：36 个 WAV + 每单元 4 件证据 + 每会话生命周期/GUI/快照凭证 + 批次 manifest；
- 数据分析（分音识别、拟合、准入门槛核对）不在本方案内，Pilot 完成后按预登记口径另行推进。

## 10. 脚本套件（本目录 `pilot/`，已自检）

```
pilot/
  plan-v2.md                    本方案
  runbook-v2.md                 执行手册（命令级）
  launcher/
    owned-session.ps1           受控启动 + deadline 计时（v2 修订）
    pilot-rpc.ps1               prepare / unit-before / unit-after / close
                                （v2.1：稳定等待 + 反例验证 + 基线/一致性硬断言 + 证据落盘）
    preflight-protection.ps1    批次/会话前置核验（与 b0 版逐字节一致）
  tools/
    make-stimulus.py            9 个 MIDI 生成 + 与认证 A4-v70 逐位自检
    pilot-verify.py             compare / unit（双层 drift 断言 + WAV 断言）
    protected-snapshot.py       受保护快照生成/比对（规则化清单，当前 337 文件）
    archive_pilot_batch.py      批次归档（复制→核验→manifest→四索引）
  stimulus/                     9 个 MIDI + receipt.json（含散列）
  baseline/                     certified-export-state-215.json + provenance.json
```

脚本自检记录：pilot-verify.py 正/负例（含 b0 四参数漂移、采样率不符、基线隐藏漂移）全部预期；
protected-snapshot.py 同源比对与变更检出正确；archive_pilot_batch.py 复制/核验/索引/重复拒绝正确；
两个 ps1 在 Windows PowerShell 7 语法通过且 G:\ 路径错误分支 dry-run 正确；
**pilot-rpc.ps1 v2.1 于 2026-10-12 s01 验证会话实测**：prepare 正向（反例写入→加载→215 项全量恢复，
settled 1024 ms / 2 polls / drift 0，全程 2.7 s）与负向（故意篡改 unison 期望值的基线必触发 plateau 报错并落盘
`prepare-settle-failure.json`）均符合预期；close 分支实测 quit 正常、进程退出（exit 0）。

## 11. 修订记录

- **v2.1（2026-10-12，s01 验证会话后）**：修复 `pilot-rpc.ps1` 的 FXP 异步应用窗口缺陷——
  `loadFile(FXP)` 的 `result:null` 仅表示请求被接受，参数应用存在短暂窗口（实测 5 ms 采样到中间态、
  500 ms 已恢复）。此前 prepare 在 loadFile 后立即读参数，捕获到 `unison` / `equalizer_switch` 未恢复的中间态。
  修订项：① 所有 loadFile/loadMidiFile 后引入「稳定等待」（连续两次快照 digest 一致）；② prepare 增加
  restore counterexample（4 项反例按写入前读数自动选择候选值，核验偏离后加载并断言全量恢复）；
  ③ prepare/unit-before/unit-after 全部改用内置硬断言（基线 digest + 逐项双重判据），失败即中止并落盘证据；
  ④ FXP 身份（SHA-256/字节数）随 prepare 落盘。反例候选自动选择的原因：Pianoteq text 为格式化显示值
  （写入 `1` 读回 `1.00`），固定期望文本会产生假失败；判据改为「偏离写入前读数」。
