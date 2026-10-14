# Task 39-2 插值修复训练采集执行手册（runbook interp-training v1）

> 本手册是 corpus runbook v1 的 **interp-training 适配版**：执行套件（launcher / 采集流程 / 处置树 /
> 禁令）与 corpus 主体逐条沿用，不改任何采集脚本；差异为采集矩阵（插值修复的新训练锚点候选
> 26/52/57 × 41/70/98 × 44.1/48 kHz × repeats 2 = 36 单元 / 12 会话）、stimulus 来源、
> **每会话 prefs-seed 机制**（移植 midfill 已验证做法）与数据角色声明。
> 修订详情见 §8。
>
> 配套冻结资产：`interp-training-blind-audit.json`（盲性审计）、`stimulus-interp/`（刺激与 receipt）、
> `calibration/interpolation-capture-proposal-20261014.json`（用户批准的执行依据）、
> `calibration/interpolation-research-20261014.md`（预研结论）。
> 读者：主会话执行者。GUI 操作全部经主会话 windows-mcp 逐次核验与审批；非 GUI 步骤按下述命令执行。
> 纪律：不自动 commit；不静默重试；异常即记录并按下述处置树处理。
>
> **数据角色（本批核心约束）**：本批全部 36 单元为**训练数据**（供后续训练准入分析）。
> 验证候选音高 25/27/53/59 **不在本批刺激中、不采集、不渲染**；验证集在本批全程保持未打开。
> B 表与生产代码在本批不改（新锚点接纳是独立后续步骤）。

---

## 0. 路径约定（每批次开始时确定一次）

| 变量（bash） | 值 |
|---|---|
| `PILOT` | `/root/repos/pianoteq9/acoustic_lab/results/task39-2-official-reference-v2/pilot` |
| `PWSH` | `/mnt/c/Program Files/PowerShell/7/pwsh.exe` |
| `BATCH_ID` | `interp-training-<YYYYMMDD-HHMMSS>`（批次开始时确定） |
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

---

## 1. 批次前置（一次，全部通过才进入会话）

```bash
# 0) 环境确认：无残留 Pianoteq（preflight 会再查一次）
# 1) 创建批次根并复制执行资产
rm -rf "$BATCH_WSL"; mkdir -p "$BATCH_WSL/launcher" "$BATCH_WSL/sessions" "$BATCH_WSL/tools"
cp "$PILOT"/launcher/*.ps1 "$BATCH_WSL/launcher/"
cp -r "$BATCH_PREFS_FROM/prefs-template" "$BATCH_WSL/prefs-template"   # 44100/48000 两套（register 归档）
cp "$PILOT/tools/make-stimulus-corpus.py" "$BATCH_WSL/tools/"          # 工具副本（版本记录）
# 2) 刺激（本批新生成 26/52/57 三音；工作区预生成副本在 PILOT/stimulus-interp/）
python3 "$PILOT/tools/make-stimulus-corpus.py" --out-dir "$BATCH_WSL/stimulus" \
  --reference "/mnt/g/source/projects/devpiano-evidence/phase39/task39-2/gui-export-20261012-092853/stimulus/A4-v70.mid" \
  --notes 26,52,57
# 3) 复制核验（launcher 与 PILOT 侧逐字节一致；stimulus 的 9 个 MIDI 与工作区副本散列一致）
sha256sum "$PILOT"/launcher/*.ps1 "$BATCH_WSL"/launcher/*.ps1
( cd "$BATCH_WSL/stimulus" && sha256sum *.mid ) > "$BATCH_WSL/stimulus-mid-sha256.txt"
( cd "$PILOT/stimulus-interp" && sha256sum *.mid ) > "$BATCH_WSL/stimulus-workcopy-sha256.txt"
diff "$BATCH_WSL/stimulus-mid-sha256.txt" "$BATCH_WSL/stimulus-workcopy-sha256.txt" && echo stimulus-identical
# 4) 基线文件自检（应与 provenance.json 一致）
sha256sum "$PILOT/baseline/"*
# 5) 受保护快照 before
python3 "$PILOT/tools/protected-snapshot.py" generate --out "$BATCH_WSL/protected-before.json"
# 6) 官方侧 preflight（用户 Modartt 目录备份 + 核验 + 无既有进程）
"$PWSH" -NoLogo -NoProfile -NonInteractive -File "$BATCH_WIN\launcher\preflight-protection.ps1" -Evidence "$BATCH_WIN" -Exe "$EXE_WIN"
```
写入 `$BATCH_WSL/scope.json`（授权文本、矩阵、盲性审计引用、合约散列、数据角色；格式参考 midfill 归档 `scope.json`）。

**批次门禁（interp-training v1 决定，2026-10-14）——独立 dry-run 免于执行，理由登记：**

1. 本批次执行套件与 corpus/midfill 逐字节相同（launcher 三脚本 SHA-256 与 PILOT 侧一致，见 §1 步骤 3），
   采集流程已在 pilot / register / corpus / anchors2 / bridge / midfill 共 60+ 正式会话中连续验证；
   唯一新变量是 stimulus 文件集与音频 rate 组合；
2. 刺激生成器自检 `build_mid(69,70)` 与认证参考 A4-v70.mid 逐位一致（SHA-256 `9e4827ed…`），
   本批 9 个刺激与该结构同构（receipt 逐文件散列）；
3. 因此首个正式会话（s01）的首个单元即为完整集成验证：`unit-before` 硬断言、GUI 导出、
   `unit-after` 硬断言、`pilot-verify` 独立审计全部照常执行，任何失败按 §5 处置树停止并记录，
   不静默重试。

## 2. 会话流程（每会话重复 §2.1–§2.7）

### 2.1 会话开始

```bash
SESS="s01-n26-44100-rep0"                 # 会话编号与语义名（见 §2.1.1 会话表）
SESS_WSL="$BATCH_WSL/sessions/$SESS"; SESS_WIN="$BATCH_WIN\sessions\$SESS"
mkdir -p "$SESS_WSL"
```

写 `$SESS_WSL/context.json`（授权、note/rate/rep、3 个单元名、FXP、基线路径、`prefs_seed`、`started_utc`）。

**每会话 prefs-seed 生成（本批固化；midfill 已验证机制）**：导出对话框的 Target file 目录继承
`RecentWav` 记录路径；把 seed 的 `RecentWav` 预置为本会话三条导出路径，Target 目录即自动归一到
本会话 `private-home/Documents`（免除运行时 D1 修正；D1 复读检查仍保留）：

```bash
python3 "$BATCH_WSL/tools/seed-prefs.py" \
  --template "$BATCH_WSL/prefs-template/<rate>/session-prefs.xml" \
  --user-prefs "$BATCH_WSL/prefs-template/<rate>/user-prefs.xml" \
  --out-dir "$SESS_WSL/prefs-seed" --note <note> \
  --wav-dir-win "$SESS_WIN\\private-home\\Documents"
# 核验：seed 与模板 diff 仅 RecentWav 一行；RecentWav = <本会话 Documents>\n26-v98.wav&#10;…v70&#10;…v41
```

启动（后台 + stdio 重定向；勿省略重定向——挂起时 fatal 行靠它保留）：

```bash
nohup "$PWSH" -NoLogo -NoProfile -NonInteractive -File "$BATCH_WIN\launcher\owned-session.ps1" \
  -Exe "$EXE_WIN" -Evidence "$SESS_WIN" -DeadlineSeconds 900 -Reason 'P3 interp-training controlled capture' \
  -PrefsTemplate "$SESS_WIN\prefs-seed" \
  > "$SESS_WSL/launcher-stdio.log" 2>&1 &
```

等待 `$SESS_WSL/lifecycle-created.json` 出现（≤30 s）；从其中读取 `pid` 与 `rpc_port`（记入会话变量 `PID` / `PORT`）。

### 2.2 GUI 准备（windows-mcp，主会话逐动作）

**动作前核验窗口身份**（EXE 路径 / PID / HWND / 创建时间）；**每个动作后 `ui_snapshot` 复读**。

**seed 播种后的预期**：无 Welcome 面板（用户级 `welcome-done-demo` 生效），音频设备已就绪 →
**跳过 G1、G3–G5**（以 §2.1 的 RPC 音频校验为准）。Demo 提示（G2 及 G6c 后）与
Standard 模式切换（G6）均无持久配置项，仍按下表执行；G6 只需 2 次点击。

| 序 | 动作 | 观察点（复读确认） |
|---|---|---|
| G1 | 关闭 Welcome 面板（面板内按钮，元素现场发现）**（seed 播种时预期不出现；若出现仍执行）** | Welcome 面板消失；主界面出现 |
| G2 | Demo 确认对话框点 OK（若出现） | Demo 提示消失 |
| G3 | 打开设备选择对话（"Open the device selection dialogue"）**（seed 播种时预期跳过；出现则执行并记录偏差）** | Options 窗口出现（新 HWND，记录） |
| G4 | 音频设备类型选择 → DirectSound（对 selector 用方向键 + 复读）**（同上）** | readback = `DirectSound` |
| G5 | 关闭 Options 窗口**（同上）** | Options 窗口消失 |
| G6 | `Try Pianoteq Standard` → `Switch to Pianoteq STANDARD` | 切换后菜单出现 `Try Pianoteq STAGE` |

记录全部动作到 `$SESS_WSL/mcp/gui-actions.json`（字段：seq / name / tool / elementId 或坐标 / post snapshot token / readback；
模式参照 midfill `mcp/gui-actions.json`，附 `qualification` 声明为工具响应摘要）。

### 2.3 RPC prepare + 基线断言

```bash
"$PWSH" -NoLogo -NoProfile -NonInteractive -File "$BATCH_WIN\launcher\pilot-rpc.ps1" \
  -Port $PORT -TargetPid $PID -Evidence "$SESS_WIN" -Step prepare -Fxp "$FXP_WIN" \
  -BaselineJson "\\wsl.localhost\Ubuntu\root\repos\pianoteq9\acoustic_lab\results\task39-2-official-reference-v2\pilot\baseline\certified-export-state-215.json"
```
期望输出 `PILOT_STEP_PREPARE_OK ... settled_ms=... polls=... drift=0`（流程与落盘文件同 corpus §2.3）。

随后必须：

```bash
# 音频记录核验：rpc/prepare-audio-device.json 中 device_type=DirectSound、sample_rate=<本会话 rate>.0、buffer_size=2560
python3 "$PILOT/tools/pilot-verify.py" compare \
  --a "$SESS_WSL/rpc/prepare-parameters.json" \
  --b "$PILOT/baseline/certified-export-state-215.json" \
  --out "$SESS_WSL/session-baseline-drift.json" --label "$SESS-baseline"
```
期望 `identical=True`（exit 0）。不等 → 停止该会话（处置树 P2）。

#### 2.1.1 会话表（interp-training：12 会话 = 3 note × 2 rate × 2 repeats）

| 会话 | note | rate | rep | 单元（v41/v70/v98） |
|---|---|---|---|---|
| s01-n26-44100-rep0 | 26 | 44100 | 0 | n26-v41 / n26-v70 / n26-v98（-44100-rep0） |
| s02-n26-44100-rep1 | 26 | 44100 | 1 | 同上（-44100-rep1） |
| s03-n26-48000-rep0 | 26 | 48000 | 0 | 同上（-48000-rep0） |
| s04-n26-48000-rep1 | 26 | 48000 | 1 | 同上（-48000-rep1） |
| s05-n52-44100-rep0 | 52 | 44100 | 0 | n52-v41 / n52-v70 / n52-v98（-44100-rep0） |
| s06-n52-44100-rep1 | 52 | 44100 | 1 | 同上（-44100-rep1） |
| s07-n52-48000-rep0 | 52 | 48000 | 0 | 同上（-48000-rep0） |
| s08-n52-48000-rep1 | 52 | 48000 | 1 | 同上（-48000-rep1） |
| s09-n57-44100-rep0 | 57 | 44100 | 0 | n57-v41 / n57-v70 / n57-v98（-44100-rep0） |
| s10-n57-44100-rep1 | 57 | 44100 | 1 | 同上（-44100-rep1） |
| s11-n57-48000-rep0 | 57 | 48000 | 0 | 同上（-48000-rep0） |
| s12-n57-48000-rep1 | 57 | 48000 | 1 | 同上（-48000-rep1） |

组织顺序：按音高分组（26 → 52 → 57），组内 44100 先行（rep0 → rep1）、48000 次之（rep0 → rep1），
同 rate 连续减少设备切换。每会话 3 单元、单次采集；rep0/rep1 为独立冷会话重复（稳定性/一致性由分析端比较）。

### 2.4 单元循环（×3：v41 → v70 → v98）

对 `U=<note>-v<vel>-<rate>-rep<n>`（如 `n26-v41-44100-rep0`）与 `MIDI=n<note>-v<vel>.mid`：

```bash
# a) 导出前（loadMidiFile -> sequencer 核验 -> 稳定等待 -> pre 快照 == 基线硬断言）
"$PWSH" ... -Step unit-before -Unit $U -Midi "$BATCH_WIN\stimulus\$MIDI" -BaselineJson "$BASE_JSON"
#    期望 PILOT_STEP_UNIT_BEFORE_OK；落盘 units/$U/：pre-settle.json、pre-parameters.json、
#    unit-$U-pre-baseline-assertion.json（ok=true）→ 失败 = 全局暂停（处置树 P8）
```
```
# b) GUI 导出（主会话）：
#    E1 主窗口 File 菜单（UIA 打开菜单栏项）→ 菜单项 "Export to audio file" 屏幕坐标点击 (912,602)（2560x1440 主屏）
#    E2 等待对话框出现（有渲染延迟；>30 s 未见才可判失败，重试 1 次）
#    E3 对话框验证：Format=WAV、Rate=<本会话 rate>、Bit depth=24 bits、
#       Normalize 未勾选、High quality 未选（use current settings）、
#       Target file 文件名 == n<note>-v<vel>.wav
#       —— 首次导出设置不正确时先改正并复读；之后每单元只读验证
#       —— seed 播种会话首个导出单元另须核对 Target file 目录 == 本会话
#          $SESS_WIN\private-home\Documents（预期直接满足；不符按 §2.8.1 最小干预）
#    E4 点 Export；若出现 "File already exists / Overwrite" → 点 Overwrite 并记录偏差
#    E5 对话框关闭即进入渲染；不做其它 GUI 操作
#    实测事实（沿用 midfill 2026-10-13/14 固化）：
#      - 自绘菜单项 ui_click 被判 disabled，须坐标点击；打开菜单后立即点击，
#        中间慢调用会让菜单关闭（重新打开重试即可）；每单元至多 1 次记录重试。
#      - 导出对话框为自绘模态层：Export=(1188,1033)，Bit depth 芯片=(1380,787)、列表 24 bits=(1220,878)。
#        对话框自身无标题，用主窗口标题栏 MIDI 文件名确认当前单元。
#      - 设置记忆：首次改好的 WAV / 本会话 rate / 24 bits / Use current settings /
#        Normalize 未勾选，在会话内保持；后续单元只需只读截图验证。
#      - 对话框存在性检测：主窗口 UIA 树坍缩为仅标题栏（元素数 <10），或以一次全屏截图确认。
```
```bash
# c) 导出后（等待 WAV 完成 ≤180 s、复制、散列、稳定等待、post 快照 == pre 硬断言）
"$PWSH" ... -Step unit-after -Unit $U -Midi "$BATCH_WIN\stimulus\$MIDI" -BaselineJson "$BASE_JSON"
#    期望 PILOT_STEP_UNIT_AFTER_OK；落盘 units/$U/：post-parameters.json、post-consistency.json（ok=true）
# d) 单元核验（pilot-verify 独立审计）
python3 "$PILOT/tools/pilot-verify.py" unit --unit-dir "$SESS_WSL/units/$U" \
  --rate <44100|48000> --baseline "$PILOT/baseline/certified-export-state-215.json"
```
`accepted=true` 才进入下一单元；`accepted=false` → 处置树 P1。

### 2.5 会话收尾

```bash
"$PWSH" ... -Step close        # 期望 PILOT_STEP_CLOSE_OK
```
等待 `$SESS_WSL/lifecycle-exited.json` 出现（≤60 s）；核验 `exit_code == 0`。
`close` 报错或进程未退出 → 处置树 P3。

### 2.6 会话核验

```bash
# 1) 单元验收汇总：3 个 acceptance.json 均 accepted
# 2) 计时核验：deadline-exceeded.json 不存在；created→exited 时长记录
# 3) 受保护核验
python3 "$PILOT/tools/protected-snapshot.py" generate --out "$BATCH_WSL/protected-after-$SESS.json"
python3 "$PILOT/tools/protected-snapshot.py" compare --before "$BATCH_WSL/protected-before.json" \
  --after "$BATCH_WSL/protected-after-$SESS.json" --out "$BATCH_WSL/protected-compare-$SESS.json"
```
期望 `ok=True`。否则处置树 P5。

### 2.7 会话记录

写 `$SESS_WSL/session-receipt.json`：run_id / pid / 起止时刻 / 时长 / 3 单元状态（accepted + WAV 散列）/
音频记录摘要 / 偏差列表（如有）。GUI 动作记录已在 §2.2 落盘。

### 2.8 prefs 模板与 seed

- 批次模板：从 `$BATCH_PREFS_FROM/prefs-template/`（register 归档）复制 `44100/` 与 `48000/` 两套，
  内容与 register 批次一致（含 `session-prefs.xml` 与 `user-prefs.xml`）；散列记入批次说明。
- 每会话 seed：§2.1 用 `tools/seed-prefs.py` 生成（只改写 `RecentWav`），启动器 `-PrefsTemplate` 指向
  该 seed 目录。seed 与批次模板的 diff 作为证据保留（`$SESS_WSL/prefs-seed/`）。

### 2.8.1 D1（保留兜底）：播种会话的导出目标归一

seed 机制预期已使 Target file 目录直接归一到本会话；D1 规则保留为兜底：

1. 播种会话首个导出单元在 E3 检查时，核对 Target file **目录** == 本会话 `$SESS_WIN\private-home\Documents`；
2. 不符时以最小干预在对话框内修正：点击 Target file 输入框 → 全选重输本会话完整目标路径
   （windows-mcp `keyboard_control` type + `clearFirst`）→ 点击对话框空白处失焦提交 → 截图复核
   路径开头与结尾，随后点 Export；
3. 修正后同会话后续单元自动沿用修正目录，只做只读验证；
4. 修正动作记入 `gui-actions.json`（name 形如 `E3-<unit>-targetfix`，含截图证据）；会话记录
   `session-receipt.json` 增加 `deviation_D1` 字段（what/risk/fix/verification）；
5. 导出落点以文件系统核验：本会话 Documents 出现 WAV；被继承目录的文件 mtime 不变（未被触碰）。

## 3. 批次收尾

```bash
# 1) 36 单元状态汇总 -> $BATCH_WSL/batch-summary.json（一单元一行：accepted / drift / sha256 / 原因）
# 2) 最终受保护比对（before vs 批次结束时快照）
python3 "$PILOT/tools/protected-snapshot.py" generate --out "$BATCH_WSL/protected-after-final.json"
python3 "$PILOT/tools/protected-snapshot.py" compare --before "$BATCH_WSL/protected-before.json" \
  --after "$BATCH_WSL/protected-after-final.json" --out "$BATCH_WSL/protected-comparison.json"
# 3) 本批为训练数据：训练准入分析（pilot-partial-analysis 的 interp-training 扩展）在批次完成后
#    另行执行与登记；本批不打开验证集、不做跨生产者判决
# 4) 归档（先按实际结果编写 meta.json，再执行；原件保留不删）
python3 "$PILOT/tools/archive_pilot_batch.py" --meta "$BATCH_WSL/meta.json"
# 5) 文档追加：_index/evidence-catalog.md 新节 + devpiano current-iteration 实施记录
```

## 4. 禁令清单（constraints v2 §3 固化）

1. GUI 白名单仅 §2.2 与 §2.4 列出的动作；**禁止**任何其它菜单探索。
2. **禁止** Standard/Stage 反复切换；`Try Pianoteq Standard → Switch to STANDARD` 仅允许在 §2.2（G6）执行一次。
3. **禁止** Freeze 面板交互；**禁止**打开 Presets/Parameters 面板做任何修改。
4. **禁止**在会话中修改音频设备、音量、采样率（§2.2 之外的调整一律禁止）。
5. **禁止** Ctrl+E 之类未验证快捷键（导出只用 File 菜单鼠标点击）。
6. **禁止**静默重试：任何失败重试须在证据中显式记录（次数 ≤1）。
7. **禁止**对 Pianoteq 进程执行自动强杀；强杀须用户显式授权并记录。
8. **禁止**渲染、打开或查询验证候选音高（25/27/53/59）的任何新数据；**禁止**以本批数据回调 B 表或判据。

## 5. 失败/挂起处置树

（与 corpus v1 §5 逐条相同：P1 单元断言失败→全局暂停；P2 prepare 失败→停止会话；P3 close 挂起→按授权流程；
P4 导出缺失→1 次重试；P5 受保护文件变更→立即停止；P6 超 900 s→收尾；P7 试用限制迹象→暂停；
P8 unit-before 断言失败→全局暂停；P9 unit-after 断言失败→全局暂停；P10 断言失败先查输入数据本身；
P11 seed 播种后音频校验不符→回退手动 G3–G5 并记录，该 rate seed 视为待更新。）

## 6. 会话检查单（执行时逐项勾）

- [ ] 无残留 Pianoteq/受控进程；preflight 通过（批次一次；owned-session 内建既有进程互斥每会话再查）
- [ ] owned-session 启动成功，`pid`/`rpc_port` 记录；prefs-seed 生成并核验（仅 RecentWav 差异）
- [ ] GUI 准备按表复读确认：seed 播种时 G1/G3–G5 预期跳过且 RPC 音频校验通过（DirectSound / 本会话 rate / 2560）；G2 与 G6 仍需执行
- [ ] prepare 通过（`PILOT_STEP_PREPARE_OK`，drift=0）+ 音频记录匹配 + FXP 身份 SHA-256 匹配
      + 反例 delta 4/4 `deviated=true` + `prepare-baseline-assertion.json` `ok=true`
- [ ] 3 × (unit-before ✓ + pre-baseline-assertion ok → 对话框验证快照 ✓ → unit-after ✓
      + post-consistency ok → acceptance accepted)
- [ ] close 正常；exit_code=0；无 deadline-exceeded
- [ ] 受保护 compare ok
- [ ] gui-actions.json、session-receipt.json、context.json 齐套

## 7. 附：证据字段速查

- 单元证据目录：`sessions/<sess>/units/<unit>/`：`pre-parameters.json`、`pre-settle.json`、
  `unit-<unit>-pre-baseline-assertion.json`、`post-parameters.json`、`post-consistency.json`、
  `export.wav`、`wav-receipt.json`、`acceptance.json`。
- 会话证据：`lifecycle-created.json`、`lifecycle-exited.json`、`launcher-stdio.log`、`context.json`、`session-receipt.json`、
  `private-home/`、`private-session.prefs`、`prefs-seed/`、`mcp/gui-actions.json`，以及 `rpc/` 下
  `prepare-*.json`、`unit-*-pre-poll-000.json`、`unit-*-post-poll-000.json`、`close-info.json`、`close-quit.json`；
  失败时另有 `*-settle-failure.json` / `*-error.json`。
- 批次证据：`scope.json`、`preflight-*`、`protected-*`、`stimulus/`、`prefs-template/`、`tools/seed-prefs.py`、
  `batch-summary.json`、`evidence-manifest.json`（归档时生成）。

### 7.1 低音训练键（n26）分析检查项

- n26 与 n21/n24 同类：f1 ≈ 36.7 Hz 低于分析工具 40 Hz 下限，n=1 不可识别，拟合自 n≥2 起
  （§corpus §7.1 的合成分析已证明该路径精确）；锚点准入预期口径为**弱力度 v41**
  （与 21/24/28 相同政策），v70/v98 记录为强力度观察，不外推锚点。
- 训练准入分析（批次后执行）沿用 amendment-1/2 独立留出判据；失败照实登记、不放宽、不强制产出锚点。

## 8. 修订记录

- **interp-training v1（2026-10-14）**：corpus runbook v1 的插值修复训练适配版。采集矩阵为
  26/52/57 × 41/70/98 × 44.1/48 kHz × repeats 2 = 36 单元 / 12 会话；stimulus 由
  `make-stimulus-corpus.py --notes 26,52,57` 生成（自检 (69,70) 逐位复刻认证参考；
  工作区预生成副本在 `stimulus-interp/`）；launcher 与采集工具套件不改动（与 PILOT 侧逐字节一致）；
  prefs 采用 register 归档双 rate 模板 + **每会话 seed 机制**（改写 `RecentWav` 预置本会话
  导出目录；midfill 已验证，免除 D1 运行时修正，D1 保留兜底）；新增 §2.1 seed 生成步骤与
  §7.1 低音训练键分析检查项。独立 dry-run 免于执行，理由登记于 §1 批次门禁。
  授权：用户 2026-10-14 确认「少量新训练锚点 + 保持 log 线性」路线与低区新条件留出资格，
  批准本清单并指示「先采训练，不直接打开验证集」。执行依据：
  `calibration/interpolation-capture-proposal-20261014.json`（训练部分）。
