# Task 39-2 全语料执行手册（runbook corpus v1）

> 本手册是 pilot runbook v2.2 的 training-corpus 适配版：执行套件（launcher / 采集流程 / 处置树）
> 与本手册主体逐条沿用 v2.2，不改任何采集脚本；差异仅为采集矩阵（预登记 training 12 音中尚未
> 采集的 6 音：21/24/43/44/69/108）与批次命名。本批为训练语料单次采集（无 repeats；
> 单元名沿用 rep0 编号仅为既有验收/分析结构兼容）。修订详情见 §8。

> 配套：`plan-v2.md`（方案与决策项）、`task39-2-preregistration-v2.json`（协议）。
> 读者：主会话执行者。GUI 操作全部经主会话 windows-mcp 逐次人工审批；非 GUI 步骤按下述命令执行。
> 纪律：不自动 commit；不静默重试；异常即记录并按下述处置树处理。
> v2.1 要点：RPC 步骤全部内置「稳定等待 + 硬断言」（FXP/MIDI 加载存在异步应用窗口，不得立即读参数）；
> prepare 含 restore counterexample；命令均需 `-BaselineJson`。
> v2.2 要点：模板播种会话的导出目标目录归一（D1，见 §2.8.1）——首个导出单元必须核对 Target file
> 目录并在不符时最小干预修正。修订详情见 §8。

---

## 0. 路径约定（每批次开始时确定一次）

| 变量（bash） | 值 |
|---|---|
| `PILOT` | `/root/repos/pianoteq9/acoustic_lab/results/task39-2-official-reference-v2/pilot` |
| `PWSH` | `/mnt/c/Program Files/PowerShell/7/pwsh.exe` |
| `BATCH_ID` | `corpus-<YYYYMMDD-HHMMSS>`（批次开始时确定） |
| `BATCH_PREFS_FROM` | `/mnt/g/source/projects/devpiano-evidence/phase39/task39-2/register-pilot-20261012-162401`（prefs 模板来源批次，归档副本） |
| `BATCH_WSL` | `/mnt/g/tmp/devpiano-task39-2-$BATCH_ID`（批次根，WSL 视图） |
| `BATCH_WIN` | `G:\tmp\devpiano-task39-2-$BATCH_ID`（同根，Windows 视图） |
| `EXE_WIN` | `\\wsl.localhost\Ubuntu\root\repos\pianoteq9\binaries\Pianoteq_9.2.5_Windows\Pianoteq 9.exe` |
| `FXP_WIN` | `G:\source\projects\devpiano-evidence\phase39\task39-2\official925-standard-state-20261012-060228\session-2\private-home\AppData\Roaming\Modartt\Pianoteq\Presets\Task39-2 Controlled Validation\Task39-2 Flat Full State 20261012-060228.fxp` |

硬性事实（来源：已认证证据）：
- EXE SHA-256 `7fcb5b2385a753e2f7d0a9ed068692abe877ab65b438e70a3fe2b44879b278bd`（9.2.5.20260909，签名 Valid）。
- FXP SHA-256 `9f749ca99143c4b1e0760099b2d6aad83cc3e9a745aa57a0a535a481342cddc9`。
- 基线 `baseline/certified-export-state-215.json`（215 项；unison / sympathetic_resonance / duplex_scale_resonance / quadratic_effect 均应为 `0`）。
- 期望音频：DirectSound / 主声音驱动程序 / 44100.0 / buffer 2560。

---

## 1. 批次前置（一次，全部通过才进入会话）

```bash
# 0) 环境确认：无残留 Pianoteq（preflight 会再查一次）
# 1) 创建批次根并复制执行资产（launcher 沿用 pilot 套件；刺激为缺量音符新生成）
rm -rf "$BATCH_WSL"; mkdir -p "$BATCH_WSL/launcher" "$BATCH_WSL/sessions"
cp "$PILOT"/launcher/*.ps1 "$BATCH_WSL/launcher/"
cp -r "$BATCH_PREFS_FROM/prefs-template" "$BATCH_WSL/prefs-template"   # 复用 register 批次模板（播种会话按 D1 归一目录）
python3 "$PILOT/tools/make-stimulus-corpus.py" --out-dir "$BATCH_WSL/stimulus" \
  --reference "/mnt/g/source/projects/devpiano-evidence/phase39/task39-2/gui-export-20261012-092853/stimulus/A4-v70.mid"
# 2) 复制核验（launcher 与 PILOT 侧逐字节一致；stimulus 对照本次 receipt.json）
sha256sum "$PILOT"/launcher/*.ps1 "$BATCH_WSL"/launcher/*.ps1
( cd "$BATCH_WSL/stimulus" && sha256sum *.mid )   # 对照本次 receipt.json 与 PILOT/stimulus-corpus/receipt.json（期望 18 文件零差异；生成时自检 (69,70) 逐位复刻认证参考）
# 3) 基线文件自检（应与 provenance.json 一致）
sha256sum "$PILOT/baseline/"*
# 4) 受保护快照 before
python3 "$PILOT/tools/protected-snapshot.py" generate --out "$BATCH_WSL/protected-before.json"
# 5) 官方侧 preflight（用户 Modartt 目录备份 + 核验 + 无既有进程）
"$PWSH" -NoLogo -NoProfile -NonInteractive -File "$BATCH_WIN\launcher\preflight-protection.ps1" -Evidence "$BATCH_WIN" -Exe "$EXE_WIN"
```
写入 `$BATCH_WSL/scope.json`（授权文本、范围表、约束引用；格式参考 092853 `scope.json`）。

**批次门禁（corpus v1 决定，2026-10-13）——独立 dry-run 免于执行，理由登记：**

1. 本批次执行套件与 pilot v2.2 逐字节相同（launcher 三脚本 SHA-256 与 PILOT 侧一致，见 §1 步骤 2），
   采集流程已在 pilot 与 register 共 24 个正式会话中连续验证；唯一新变量是 stimulus 文件集；
2. 刺激生成器自检 `build_mid(69,70)` 与认证参考 A4-v70.mid 逐位一致（SHA-256 `9e4827ed…`；
   本批 n69-v70 单元本身即与该参考逐位一致），且文件结构（55 字节 format-0 SMF、PPQ 480、
   tick 结构）与 pilot 刺激完全同构；
3. 因此首个正式会话（s01）的首个单元即为完整集成验证：`unit-before` 硬断言（P8）、
   GUI 导出、`unit-after` 硬断言（P9）、`pilot-verify` 独立审计全部照常执行，
   任何失败按 §5 处置树停止并记录，不静默重试。

## 2. 会话流程（每会话重复 §2.1–§2.7）

### 2.1 会话开始

```bash
SESS="s01-n44-44100-rep0"                 # 会话编号与语义名（见 §2.1.1 会话表）
SESS_WSL="$BATCH_WSL/sessions/$SESS"; SESS_WIN="$BATCH_WIN\sessions\$SESS"
mkdir -p "$SESS_WSL"
```

写 `$SESS_WSL/context.json`（授权、note/rate/rep、3 个单元名、FXP、基线路径、`started_utc`）。

**prefs 模板播种（P1，推荐）**：`$BATCH_WIN\prefs-template\<rate>\` 含 `session-prefs.xml` 与
`user-prefs.xml`（生成与维护见 §2.8）。加 `-PrefsTemplate` 后启动器播种两份 prefs 并**移除**
`--no-audio-prefs`（让模板里的 audio-setup 生效）；不给模板时保持原行为（空 prefs + `--no-audio-prefs`）。
无论是否播种，启动后**第一步**都做音频校验：RPC `getAudioDeviceInfo`，期望
`device_type=DirectSound`、`sample_rate=<本会话 rate>.0`、`buffer_size=2560`；不符 → 回退手动 G3–G5 并在
`gui-actions.json` 记录偏差。

启动（后台 + stdio 重定向；勿省略重定向——挂起时 fatal 行靠它保留；模板可用时加 `-PrefsTemplate`）：

```bash
nohup "$PWSH" -NoLogo -NoProfile -NonInteractive -File "$BATCH_WIN\launcher\owned-session.ps1" \
  -Exe "$EXE_WIN" -Evidence "$SESS_WIN" -DeadlineSeconds 900 \
  -PrefsTemplate "$BATCH_WIN\prefs-template\<rate>" \
  > "$SESS_WSL/launcher-stdio.log" 2>&1 &
```

等待 `$SESS_WSL/lifecycle-created.json` 出现（≤30 s）；从其中读取 `pid` 与 `rpc_port`（记入会话变量 `PID` / `PORT`）。

### 2.2 GUI 准备（windows-mcp，主会话逐动作）

**动作前核验窗口身份**（EXE 路径 / PID / HWND / 创建时间）；**每个动作后 `ui_snapshot` 复读**。

**模板播种后的预期**（用 `-PrefsTemplate` 启动）：无 Welcome 面板（用户级 `welcome-done-demo` 生效），
音频设备已就绪 → **跳过 G1、G3–G5**（以 §2.1 的 RPC 音频校验为准）。Demo 提示（G2 及 G6c 后）与
Standard 模式切换（G6）均无持久配置项，仍按下表执行；G6 只需 2 次点击。

| 序 | 动作 | 观察点（复读确认） |
|---|---|---|
| G1 | 关闭 Welcome 面板（面板内按钮，元素现场发现）**（模板播种时预期不出现；若出现仍执行）** | Welcome 面板消失；主界面出现 |
| G1' | **（仅模板生成会话）**在 Welcome 面板取消勾选 "Always show the welcome screen on startup"，再关闭面板 | 勾选框变为未勾选；退出后用户级 prefs 出现 `welcome-done-demo` |
| G2 | Demo 确认对话框点 OK（若出现） | Demo 提示消失 |
| G3 | 打开设备选择对话（"Open the device selection dialogue"）**（模板播种时预期跳过）** | Options 窗口出现（新 HWND，记录） |
| G4 | 音频设备类型选择 → DirectSound（对 selector 用方向键 + 复读）**（模板播种时预期跳过）** | readback = `DirectSound` |
| G5 | 关闭 Options 窗口**（模板播种时预期跳过）** | Options 窗口消失 |
| G6 | `Try Pianoteq Standard` → `Switch to Pianoteq STANDARD` | 切换后菜单出现 `Try Pianoteq STAGE` |

记录全部动作到 `$SESS_WSL/mcp/gui-actions.json`（字段：seq / name / tool / elementId 或坐标 / post snapshot token / readback；
模式参照 official925 `mcp/main-session-requests-and-results.json`，附 `qualification` 声明为工具响应摘要）。

### 2.3 RPC prepare + 基线断言

```bash
"$PWSH" -NoLogo -NoProfile -NonInteractive -File "$BATCH_WIN\launcher\pilot-rpc.ps1" \
  -Port $PORT -TargetPid $PID -Evidence "$SESS_WIN" -Step prepare -Fxp "$FXP_WIN" \
  -BaselineJson "\\wsl.localhost\Ubuntu\root\repos\pianoteq9\acoustic_lab\results\task39-2-official-reference-v2\pilot\baseline\certified-export-state-215.json"
```
期望输出 `PILOT_STEP_PREPARE_OK ... settled_ms=... polls=... drift=0`。

prepare 内部流程（v2.1，全部落盘 `rpc/`）：
1. `prepare-ready.json`（GUI 就绪时的 preset/plugin_type/version）；
2. `prepare-fxp-identity.json`（FXP 路径/SHA-256/字节数，必须 = `9f749ca9…`）；
3. restore counterexample：`prepare-counterexample-before.json`（写入前读数）→ `prepare-counterexample-plan.json`
   （按 before 读数选定的反例值）→ `prepare-counterexample-write.json`（setParameters）→ 稳定等待反例生效
   → `prepare-counterexample-pre.json` + `prepare-counterexample-delta.json`（4 项 `deviated=true`）；
4. `loadFile(FXP)` → `prepare-after-fxp-info.json`（preset 名必须 = `Task39-2 Flat Full State 20261012-060228`）
   → `prepare-audio-device.json`；
5. **稳定等待 + 全量基线硬断言**：`prepare-poll-000.json`（首读）+ `prepare-settle.json`（采样序列摘要）
   → `prepare-parameters.json`（权威 215 快照）+ `prepare-baseline-assertion.json`（`ok=true`）；
   未稳定（outcome=unstable/plateau）或存在漂移 → 落盘 `prepare-settle-failure.json` 并报错，按 P2 处置。

随后必须：

```bash
# 音频记录核验：rpc/prepare-audio-device.json 中 device_type=DirectSound、sample_rate=44100.0、buffer_size=2560
python3 "$PILOT/tools/pilot-verify.py" compare \
  --a "$SESS_WSL/rpc/prepare-parameters.json" \
  --b "$PILOT/baseline/certified-export-state-215.json" \
  --out "$SESS_WSL/session-baseline-drift.json" --label "$SESS-baseline"
```
期望 `identical=True`（exit 0）。不等 → 停止该会话（处置树 P2）。

#### 2.1.1 会话表（training corpus 缺量：12 会话 = 6 note × 2 rate，单次）

| 会话 | note | rate | rep | 单元（v41/v70/v98） |
|---|---|---|---|---|
| s01-n44-44100-rep0 | 44 | 44100 | 0 | n44-v41 / n44-v70 / n44-v98 |
| s02-n44-48000-rep0 | 44 | 48000 | 0 | 同上 |
| s03-n43-44100-rep0 | 43 | 44100 | 0 | n43-v41 / n43-v70 / n43-v98 |
| s04-n43-48000-rep0 | 43 | 48000 | 0 | 同上 |
| s05-n69-44100-rep0 | 69 | 44100 | 0 | n69-v41 / n69-v70 / n69-v98 |
| s06-n69-48000-rep0 | 69 | 48000 | 0 | 同上 |
| s07-n24-44100-rep0 | 24 | 44100 | 0 | n24-v41 / n24-v70 / n24-v98 |
| s08-n24-48000-rep0 | 24 | 48000 | 0 | 同上 |
| s09-n21-44100-rep0 | 21 | 44100 | 0 | n21-v41 / n21-v70 / n21-v98 |
| s10-n21-48000-rep0 | 21 | 48000 | 0 | 同上 |
| s11-n108-44100-rep0 | 108 | 44100 | 0 | n108-v41 / n108-v70 / n108-v98 |
| s12-n108-48000-rep0 | 108 | 48000 | 0 | 同上 |

组织顺序（风险递增，2026-10-13 评估决定）：先做成熟细分交界与锚点（n44/n43 G2/G#2 段、n69 A4）——
它们与已通过的 n36/48 邻近；再做需分析端复检的极低音（n24/n21，见 §7.1）；最后做结构上分音数
不可能达 ≥5 的 n108（20 kHz 内仅 4 个分音，预期不产出锚点）。每音 44100 先行、48000 次之。

与复用单元（pilot-v2 的 n36/48/60、register 的 n72/84/96 的 rep0）合并即为预登记 training
12 音 × 3 力度 × 2 rate = 72 单元；合并分析由分析工具 `corpus` preset（多 `--batch`）承担。

### 2.4 单元循环（×3：v41 → v70 → v98）

对 `U=<note>-v<vel>-<rate>-rep<n>` 与 `MIDI=n<note>-v<vel>.mid`（`$BASE_JSON` 同 §2.3 的基线路径参数）：

```bash
# a) 导出前（loadMidiFile -> sequencer 核验 -> 稳定等待 -> pre 快照 == 基线硬断言）
"$PWSH" ... -Step unit-before -Unit $U -Midi "$BATCH_WIN\stimulus\$MIDI" -BaselineJson "$BASE_JSON"
#    期望 PILOT_STEP_UNIT_BEFORE_OK；落盘 units/$U/：pre-settle.json、pre-parameters.json、
#    unit-$U-pre-baseline-assertion.json（ok=true）；rpc/unit-$U-pre-poll-000.json 为首读快照
#    （断言失败 = pre != 基线）→ 全局暂停（处置树 P8）
```
```
# b) GUI 导出（主会话）：
#    E1 主窗口 File 菜单（鼠标坐标点击）→ 菜单项 "Export to audio file"
#    E2 等待对话框出现（有渲染延迟；>30 s 未见才可判失败，重试 1 次）
#    E3 对话框验证：Format=WAV、Rate=<本会话 rate>、Bit depth=24 bits、
#       Normalize 未勾选、High quality 未选（use current settings）、
#       Target file 文件名 == n<note>-v<vel>.wav
#       —— 首次导出设置不正确时先改正并复读；之后每单元只读验证
#       —— 播种会话首个导出单元另须核对 Target file 目录 == 本会话
#          $SESS_WIN\private-home\Documents；不符先按 §2.8.1 D1 修正（v2.2）
#    E4 点 Export；若出现 "File already exists / Overwrite" → 点 Overwrite 并记录偏差
#    E5 对话框关闭即进入渲染；不做其它 GUI 操作
#    实测事实（2026-10-12 s01 正式会话，主屏 2560x1440 scale 1）：
#      - File 菜单：ui_click 菜单栏项可打开；但菜单项自身 ui_click 会被判 disabled
#        （自绘菜单），须用坐标点击芯片 (912,602) = "Export to audio file"。
#        打开后须立即点击；中间插入慢调用（list / snapshot）会让菜单先关闭，
#        此时坐标会落到主窗口内容区（无副作用，重新打开重试即可）。
#      - 导出对话框：自绘模态层，UIA 无任何控件元素（主窗口树只剩标题栏按钮）；
#        全部用坐标：Export=(1188,1033)，Bit depth 芯片=(1380,787)（点开后列表
#        中 24 bits=(1220,878)）。对话框自身不显示标题，用主窗口标题栏的 MIDI
#        文件名（如 n60-v41.mid）确认当前单元。
#      - 设置记忆：首次改好的 WAV / 本会话 rate / 24 bits / Use current settings /
#        Normalize 未勾选，在会话内保持；后续单元只需只读截图验证。
#      - 渲染速度：约 5.4 s 音频实测 <5 s 渲染完成，WAV ~1,430,120 字节
#        （2ch / 24-bit / rate × 5.4 s）。
#      - 对话框存在性检测：不要用窗口列表（自绘模态层常不可见，遗留 "menu" 类窗口会误导）；
#        可靠信号 = 主窗口 UIA 树坍缩为仅标题栏（元素数 <10），或以一次全屏截图确认。
```
```bash
# c) 导出后（等待 WAV 完成 ≤180 s、复制、散列、稳定等待、post 快照 == pre 硬断言）
"$PWSH" ... -Step unit-after -Unit $U -Midi "$BATCH_WIN\stimulus\$MIDI" -BaselineJson "$BASE_JSON"
#    期望 PILOT_STEP_UNIT_AFTER_OK；落盘 units/$U/：post-parameters.json、post-consistency.json（ok=true）
#    （post != pre 或未稳定）→ 全局暂停（处置树 P9）
# d) 单元核验（pilot-verify 独立审计：双层断言 + WAV 断言）
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

---

### 2.8 prefs 模板生成与维护（P1；按 rate 各一份）

首次生成（在任意一次受控会话内完成，每 rate 仅需一次）：

1. 正常启动（该会话不播种模板），完成 G1'（**取消勾选 "Always show the welcome screen on startup"**）、G3–G5（音频到目标 rate，含 buffer 2560）、G6；其余流程照常；
2. 会话正常退出（quit）后写盘情况（2026-10-12 s02 实测勘误）：
   - `$SESS_WSL/private-session.prefs`：会话级，**实际承载全部所需字段**（`welcome-done-demo`、audio-setup、wav_export_* 等）；
   - `$SESS_WSL/private-home/AppData/Roaming/Modartt/Pianoteq92.prefs`：**不会生成**。`--prefs` 模式下
     Pianoteq 不读写 %APPDATA% 用户级文件（b0 / gui-export / s01 / s02 批的 private-home 中均无此文件；
     证据：s02 rpc/ 与 private-home 树、b0 归档树）。原「退出后两份 prefs 已写盘」仅对会话级成立。
3. 提取（只读复制，不修改会话证据；模板含 RecentWav 等会话历史字段，无害）：

```bash
mkdir -p "$BATCH_WSL/prefs-template/<rate>"
cp "$SESS_WSL/private-session.prefs" "$BATCH_WSL/prefs-template/<rate>/session-prefs.xml"
# user-prefs.xml：播种机制要求该文件存在；会话内若恰好生成过用户级文件则复制，否则构造最小内容
# （只含 welcome-done-demo=1，与 --prefs 模式外无此文件的默认状态等价）：
if [ -f "$SESS_WSL/private-home/AppData/Roaming/Modartt/Pianoteq92.prefs" ]; then
  cp "$SESS_WSL/private-home/AppData/Roaming/Modartt/Pianoteq92.prefs" "$BATCH_WSL/prefs-template/<rate>/user-prefs.xml"
else
  printf '<?xml version="1.0" encoding="UTF-8"?>\n\n<PROPERTIES>\n  <VALUE name="welcome-done-demo" val="1"/>\n</PROPERTIES>\n' \
    > "$BATCH_WSL/prefs-template/<rate>/user-prefs.xml"
fi
sha256sum "$BATCH_WSL/prefs-template/<rate>"/*.xml
```

4. 校验：`session-prefs.xml` 应含 `welcome-done-demo`、`audio-setup` 与 `wav_export_*`（G1'/G3–G5 生效的直接证据；缺少 → 回到步骤 1）；`user-prefs.xml` 应含 `welcome-done-demo`。模板两份文件的 SHA-256 记入批次说明；模板播种效果（无 Welcome、音频就绪 → 跳过 G1/G3–G5）在下一播种会话内以观察与 §2.1 的 RPC 音频校验确认。

注意：换 rate 的会话如需独立模板按同法生成（首跑时只改 Sample rate 一项）；模板始终只写入批次私有目录，不触碰用户真实配置。

### 2.8.1 D1（v2.2）：播种会话的导出目标归一

模板 `session-prefs.xml` 会携带「上次导出目录」，表现为导出对话框 Target file 的初始目录。播种会话的
**首个导出单元**中，Target file 可能指向模板生成会话的私有目录（如 `sessions/s02-…/private-home/Documents`）；
若直接导出，WAV 会写入或覆盖旧会话的证据目录。

规则（2026-10-12 s04 首个播种会话实测固化，用户批准）：

1. 播种会话首个导出单元在 E3 检查时，除文件名与格式外，必须核对 Target file **目录** == 本会话
   `$SESS_WIN\private-home\Documents`；
2. 不符时以最小干预在对话框内修正：点击 Target file 输入框 → 全选重输本会话完整目标路径
   （windows-mcp `keyboard_control` type + `clearFirst`）→ 点击对话框空白处失焦提交 → 截图复核路径
   开头与结尾，随后点 Export；
3. 修正后同会话后续单元自动沿用修正目录，只做只读验证；
4. 修正动作记入 `gui-actions.json`（name 形如 `E3-<unit>-targetfix`，含截图证据）；会话记录
   `session-summary.json` 增加 `deviation_D1` 字段（what/risk/fix/verification）；
5. 导出落点以文件系统核验：本会话 Documents 出现 WAV；被继承目录的文件 mtime 不变（未被触碰）。

## 3. 批次收尾

```bash
# 1) 36 单元状态汇总 -> $BATCH_WSL/batch-summary.json（一单元一行：accepted / drift / sha256 / 原因）
# 2) 最终受保护比对（before vs 批次结束时快照）
python3 "$PILOT/tools/protected-snapshot.py" generate --out "$BATCH_WSL/protected-after-final.json"
python3 "$PILOT/tools/protected-snapshot.py" compare --before "$BATCH_WSL/protected-before.json" \
  --after "$BATCH_WSL/protected-after-final.json" --out "$BATCH_WSL/protected-comparison.json"
# 3) 本批无 repeats（单次训练语料）：跨率/跨批次一致性由分析工具（corpus preset）承担，不在此重复
#    批次归档后的合并分析命令（另行授权；含复用单元的三个批次根）：
#    python3 "$PILOT/tools/pilot-partial-analysis.py" --preset corpus \
#      --batch "$BATCH_WSL" \
#      --batch /mnt/g/source/projects/devpiano-evidence/phase39/task39-2/pilot-v2-20261012-211747 \
#      --batch /mnt/g/source/projects/devpiano-evidence/phase39/task39-2/register-pilot-20261012-162401 \
#      --out <analysis-out>
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

## 5. 失败/挂起处置树

| # | 情形 | 处置 |
|---|---|---|
| P1 | 单元 `accepted=false`（drift ≠ 0 或 WAV 断言失败） | 立即**全局暂停**：记录 `acceptance.json`，不改任何状态，向用户报告（含 drift 明细）并请求决策；**不**继续后续单元/会话 |
| P2 | 会话 prepare 失败：`prepare-counterexample-failure.json`（反例写入未生效）、`prepare-settle-failure.json`（outcome=unstable/plateau，状态未稳定或未恢复基线）、`prepare-baseline-assertion.json` `ok=false` | 停止该会话（不导出）；按 P3 收尾；归档证据；报告。**不**自动重试加载、**不**自动改参数 |
| P3 | `close` 挂起 / RPC 超时（getInfo/getParameters/quit 连续 2 次超时） | 1) 确认 `launcher-stdio.log` 已含 fatal/Ctx 行（已有则原样保留）；2) 记录 `rpc/close-quit-error.json`（或对应 `-error.json`）；3) 不尝试 WM_CLOSE；4) 请求用户授权外部强杀；5) 强杀后记录 `hanging-termination.json`（授权文本、时刻、方式） |
| P4 | 导出对话框 >30 s 未出现 / 导出无 WAV（unit-after 180 s 超时） | 允许 1 次重试（对话框点击或重导出；覆盖确认按 Overwrite 并记录）；再失败 → 中止该会话（按 P3 收尾），单元作废 |
| P5 | 受保护文件 compare `ok=False` | 立即停止全部工作；列出 changed/missing 清单报告；不自行恢复或修改 |
| P6 | `deadline-exceeded.json` 出现（会话超 900 s） | 不再开始新单元；进行中单元等其完成后收尾；未完成单元作废（重跑归下一会话） |
| P7 | 累计试用限制迹象（R6，如播放被截断/静音提示） | 全局暂停；报告；不绕过 |
| P8 | `unit-before` 断言失败：`pre-baseline-assertion.json` `ok=false`（pre ≠ 基线） | 全局暂停：该单元不导出；记录证据并报告（含 drift 明细）；**不**继续后续单元/会话；诊断根因（含 launcher-stdio.log 与 prepoll 序列） |
| P9 | `unit-after` 断言失败：`post-consistency.json` `ok=false`（post ≠ pre）或 `outcome≠settled` | 全局暂停：WAV 已产出但状态可疑，不得作为 accepted 证据；记录证据并报告；检查导出流程是否意外改变参数 |
| P10 | 断言类失败（`got N` / 形状不符 / ok=false） | **第一动作检查被断言的输入数据本身**（如读 `pre-parameters.json` 的顶层结构与项数），再考虑运行时瞬态假设；瞬态结论须有时间序列证据（多次采样），不得由单次采样得出 |
| P11 | 模板播种后音频校验不符（`getAudioDeviceInfo` ≠ DirectSound / 本会话 rate / 2560） | 回退手动 G3–G5；在 `gui-actions.json` 记录偏差与实测值；该 rate 模板视为待更新（不删除、不借用其它 rate 的模板） |

## 6. 会话检查单（执行时逐项勾）

- [ ] 无残留 Pianoteq/受控进程；preflight 通过（每会话前重跑 preflight-protection.ps1）
- [ ] owned-session 启动成功，`pid`/`rpc_port` 记录
- [ ] GUI 准备按表复读确认：模板播种时 G1/G3–G5 预期跳过且 RPC 音频校验通过（DirectSound / 本会话 rate / 2560）；G2 与 G6（含 G6 后 Demo OK）仍需执行；G1' 仅模板生成会话
- [ ] prepare 通过（`PILOT_STEP_PREPARE_OK`，drift=0）+ 音频记录 = DirectSound/44100.0/2560
      + FXP 身份 SHA-256 匹配 + 反例 delta 4/4 `deviated=true` + `prepare-baseline-assertion.json` `ok=true`
- [ ] 3 × (unit-before ✓ + `unit-<U>-pre-baseline-assertion.json` ok → 对话框验证快照 ✓ → unit-after ✓
      + `post-consistency.json` ok → acceptance accepted)
- [ ] close 正常；exit_code=0；无 deadline-exceeded
- [ ] 受保护 compare ok
- [ ] gui-actions.json、session-receipt.json、context.json 齐套

## 7. 附：证据字段速查

- 单元证据目录：`sessions/<sess>/units/<unit>/`：`pre-parameters.json`、`pre-settle.json`、
  `unit-<unit>-pre-baseline-assertion.json`、`post-parameters.json`、`post-consistency.json`、
  `export.wav`、`wav-receipt.json`、`acceptance.json`。
- 会话证据：`lifecycle-created.json`、`lifecycle-exited.json`、`launcher-stdio.log`、`context.json`、`session-receipt.json`、
  `private-home/`、`private-session.prefs`、`mcp/gui-actions.json`，以及 `rpc/` 下：
  `prepare-ready.json`、`prepare-fxp-identity.json`、`prepare-counterexample-before/plan/write/pre/delta.json`、
  `prepare-fxp-load.json`、`prepare-after-fxp-info.json`、`prepare-audio-device.json`、`prepare-poll-000.json`、
  `prepare-settle.json`、`prepare-parameters.json`、`prepare-baseline-assertion.json`、`close-info.json`、`close-quit.json`；
  失败时另有 `*-settle-failure.json` / `*-error.json`。
- 批次证据：`scope.json`、`preflight-*`、`protected-*`、`stimulus/`、`batch-summary.json`、`evidence-manifest.json`（归档时生成）。

### 7.1 极低音分析检查项（n21/n24，2026-10-13 探针结论）

- 分析端已通过合成验证：40 Hz 峰搜索低限下 n21/n24 从 n≥2 拟合；在真实化幅度模型
  （最强分音 n≈4、之后约 -1.9 dB/分音）下 f1/B 恢复精确（≤0.03 cents）、分音数约 35。
  「窗口重叠错位」仅在分音数 ≥67 且高次分音过强时出现（合成 1/n 幅度才会触发）；
  真实钢琴数据分音数 ≤65（C2 实测），且即便发生也由 holdout 判据拒绝（安全失败，非错误准入）。
  真实录音在 15–64 Hz 存在 -55…-80 dB 杂散峰（40 Hz 低限的设置依据），真低次分音强 15+ dB。
- 采集完成后对首个 n21 与 n24 单元（corpus 分析时）逐项检查：识别分音数 ≥5、max/rms holdout
  达判据、W1/W2 的 f1 窗口散布 ≤1 cent；若失败 → 记录并做专项诊断（**不放宽判据**、
  不强行产出锚点；必要时按预登记「unavailable_controlled_reference」条款处置）。

## 8. 修订记录

- **v2.2（2026-10-12）**：新增 §2.8.1 D1（播种会话的导出目标归一），§2.4 E3 检查清单补充播种首单元的
  Target file 目录核对。起因：s04（首个播种会话）首个导出发现 Target file 继承模板中的 s02 私有目录
  （写入/覆盖风险），已最小干预修正且被继承目录未被触碰。证据：s04 `session-summary.json`
  `template_seeding.deviation_D1`、`mcp/gui-actions.json`（E3-n60v41-targetfix 条目与截图）。
- **v2.1（2026-10-12）**：`pilot-rpc.ps1` 修复 FXP 异步应用窗口缺陷（详见 `plan-v2.md` §11）：
  prepare/unit-before/unit-after 全部改为「稳定等待 + 硬断言」；prepare 增加 restore counterexample 与
  FXP 身份落盘；新增 `-BaselineJson` 参数（§2.3/§2.4 命令已含）；处置树新增 P8/P9，P2 细化。
  实测验证见 `plan-v2.md` §10 自检记录（正/负例与 close 全部通过）。

- **register v1（2026-10-12）**：pilot runbook v2.2 的高音区先导适配版。采集矩阵改为 notes 72/84/96
  （C5/C6/C7）× velocities 41/70/98 × rates 44100/48000 × repeats 2 = 36 单元 / 12 会话；launcher 与
  工具套件不改动（与 pilot 侧逐字节一致）；stimulus 由 `make-stimulus-register.py` 生成（自检
  (69,70) 逐位复刻认证参考）；prefs 模板复用 pilot 批次（播种会话按 §2.8.1 D1 归一导出目录）；
  独立 dry-run 免于执行，理由登记于 §1 批次门禁。授权：用户 2026-10-12 选择「高音区先导采集
  （36 单元，pilot 同流程）」，pilot 分析 18/18 族通过后放行。
- **corpus v1（2026-10-13）**：pilot runbook v2.2 的 training-corpus 适配版。采集矩阵为预登记
  training 12 音中尚未采集的 6 音（21/24/43/44/69/108）× velocities 41/70/98 × rates
  44100/48000 × 单次 = 36 单元 / 12 会话；launcher 与采集工具套件不改动（与 pilot 侧逐字节一致）；
  stimulus 由 `make-stimulus-corpus.py` 生成（自检 (69,70) 逐位复刻认证参考；其中 n69-v70 单元
  本身即与参考逐位一致；工作区预生成副本在 `stimulus-corpus/`，执行时逐文件散列对照）；
  prefs 模板复用 register 批次（播种会话按 §2.8.1 D1 归一导出目录）；独立 dry-run 免于执行，
  理由登记于 §1 批次门禁。新增 §7.1 极低音分析检查项。分析端（`corpus` preset 与多批次
  `--batch` 合并）在 `pilot-partial-analysis.py` 内实现，并经回归验证（v2/register 单批
  与归档零差异；corpus 干跑 28 复用单元零差异、8 个既有边界失败、36 个待采）。授权：
  用户 2026-10-13 选择「放行：先准备、后采集」（评估：全语料仅需新采 6 音 36 单元，
  已有 6 音 36 单元同条件复用）。
