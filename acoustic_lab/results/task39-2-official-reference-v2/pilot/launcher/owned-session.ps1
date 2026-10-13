# Task 39-2 v2 Pilot 受控启动器（owned-session v2，固化 constraints v2）。
#
# 相对 b0 版（pilot-b0-20261012-193620/launcher/owned-session.ps1）的修订：
#   1. 新增单元计时器：进程创建起 DeadlineSeconds 秒硬窗口；
#      到期时仅写 deadline-exceeded.json 并在标准输出打点，
#      不改动 GUI、不终止进程（强杀须外部人工授权）。
#   2. lifecycle-created.json 记录 registered_deadline_utc 与终止策略。
#   3. 等待循环改为轮询 WaitForExit(5000)，替代无限 WaitForExit()。
#
# stdio 纪律（runbook 固定调用模板，勿省略）：
#   调用方必须把本脚本的输出重定向到 <session-dir>/launcher-stdio.log；
#   Pianoteq 自身 stdio 继承该重定向，fatal 行与 Ctx 行因此在挂起时也不丢。
#   示例：pwsh -NoLogo -NoProfile -NonInteractive -File owned-session.ps1
#           -Exe "<EXE>" -Evidence "<session-dir>" > "<session-dir>/launcher-stdio.log" 2>&1
#
# 本脚本不执行任何 GUI 操作，不修改任何既有用户文件。
param(
    [Parameter(Mandatory)][string]$Exe,
    [Parameter(Mandatory)][string]$Evidence,
    [int]$DeadlineSeconds = 900,
    [string]$Reason = 'Task 39-2 v2 Pilot controlled session',
    [string]$PrefsTemplate = ''
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$runId = [Guid]::NewGuid().ToString()
$expectedHash = '7fcb5b2385a753e2f7d0a9ed068692abe877ab65b438e70a3fe2b44879b278bd'
$child = $null
try {
    # 1) 进程表快照 + 既有实例互斥
    $before = @(Get-CimInstance Win32_Process)
    $before | Select-Object ProcessId, ParentProcessId, Name, ExecutablePath, CreationDate, CommandLine, SessionId | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath "$Evidence/processes-immediately-before-launch.json" -Encoding utf8
    if (@($before | Where-Object { $_.Name -match '(?i)pianoteq' -or $_.ExecutablePath -match '(?i)pianoteq' }).Count -ne 0) { throw 'Existing Pianoteq process found; refusing ownership or launch' }

    # 2) 生产者身份核验（散列/版本/签名）
    $file = Get-Item -LiteralPath $Exe
    $hash = (Get-FileHash -LiteralPath $Exe -Algorithm SHA256).Hash.ToLowerInvariant()
    $signature = Get-AuthenticodeSignature -LiteralPath $Exe
    if ($hash -ne $expectedHash -or $file.VersionInfo.ProductVersion -ne '9.2.5' -or $signature.Status -ne 'Valid') { throw 'Source identity verification failed' }

    # 3) 私有 home / prefs 拒绝复用；可选从模板播种（P1，2026-10-12 用户批准）
    $privateHome = Join-Path $Evidence 'private-home'
    $prefs = Join-Path $Evidence 'private-session.prefs'
    if ((Test-Path -LiteralPath $privateHome) -or (Test-Path -LiteralPath $prefs)) { throw 'Private state already exists; refusing reuse' }
    foreach ($relative in @('AppData/Roaming', 'AppData/Local', 'Temp', 'Documents')) { [void][IO.Directory]::CreateDirectory((Join-Path $privateHome $relative)) }
    # 模板播种：-PrefsTemplate 目录须含 session-prefs.xml（会话级 --prefs 内容，含 audio-setup）
    # 与 user-prefs.xml（用户级 Pianoteq92.prefs 内容，含 welcome-done-demo）。播种后移除
    # --no-audio-prefs，让模板中的音频设备配置生效；随后以 RPC getAudioDeviceInfo 校验。
    $useAudioPrefs = $false
    if (-not [string]::IsNullOrWhiteSpace($PrefsTemplate)) {
        $tplSession = Join-Path $PrefsTemplate 'session-prefs.xml'
        $tplUser = Join-Path $PrefsTemplate 'user-prefs.xml'
        if (-not (Test-Path -LiteralPath $tplSession) -or -not (Test-Path -LiteralPath $tplUser)) { throw "PrefsTemplate must contain session-prefs.xml and user-prefs.xml: $PrefsTemplate" }
        Copy-Item -LiteralPath $tplSession -Destination $prefs
        $userPrefsDir = Join-Path $privateHome 'AppData/Roaming/Modartt'
        [void][IO.Directory]::CreateDirectory($userPrefsDir)
        Copy-Item -LiteralPath $tplUser -Destination (Join-Path $userPrefsDir 'Pianoteq92.prefs')
        $useAudioPrefs = $true
    }

    # 4) 回环端口分配（--serve）
    $socket = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
    $socket.Start()
    $port = $socket.LocalEndpoint.Port
    $socket.Stop()

    # 5) 启动参数与环境隔离
    $start = [Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $file.FullName
    $start.UseShellExecute = $false
    $start.WorkingDirectory = $privateHome
    $launchArgs = @('--prefs', $prefs)
    if (-not $useAudioPrefs) { $launchArgs += '--no-audio-prefs' }
    $launchArgs += @('--serve', "127.0.0.1:$port")
    foreach ($argument in $launchArgs) { $start.ArgumentList.Add($argument) }
    $start.Environment['APPDATA'] = Join-Path $privateHome 'AppData/Roaming'
    $start.Environment['LOCALAPPDATA'] = Join-Path $privateHome 'AppData/Local'
    $start.Environment['USERPROFILE'] = $privateHome
    $start.Environment['TEMP'] = Join-Path $privateHome 'Temp'
    $start.Environment['TMP'] = Join-Path $privateHome 'Temp'
    $start.Environment['PATH'] = (($start.Environment['PATH'] -split ';' | Where-Object { $_ -notmatch '(?i)pianoteq|vst3' }) -join ';')

    # 6) 启动 + 子进程身份验证
    $requestedAt = (Get-Date).ToUniversalTime().ToString('o')
    $child = [Diagnostics.Process]::Start($start)
    $live = Get-CimInstance Win32_Process -Filter "ProcessId = $($child.Id)"
    if (-not $live -or -not $live.ExecutablePath.Equals($file.FullName, [StringComparison]::OrdinalIgnoreCase)) { throw 'Created process identity cannot be proved; stopping observation' }
    $createdUtc = $live.CreationDate.ToUniversalTime()
    $deadlineUtc = $createdUtc.AddSeconds($DeadlineSeconds)

    # 7) 生命周期凭据（含计时窗口登记）
    $receipt = [ordered]@{
        run_id = $runId
        reason = $Reason
        requested_at = $requestedAt
        controller_pid = $PID
        pid = $child.Id
        parent_pid = $live.ParentProcessId
        created_utc = $createdUtc.ToString('o')
        session_id = $live.SessionId
        exe = $live.ExecutablePath
        sha256 = $hash
        command_line = $live.CommandLine
        arguments = @($start.ArgumentList)
        private_home = $privateHome
        prefs = $prefs
        prefs_template = $PrefsTemplate
        prefs_template_seeded = $useAudioPrefs
        rpc_port = $port
        deadline_seconds = $DeadlineSeconds
        registered_deadline_utc = $deadlineUtc.ToString('o')
        termination_policy = 'external manual authorization only; timer never mutates GUI or terminates the process'
        copied_application = $false
        gui_ready_verified = $false
        force_termination_allowed = $false
    }
    $receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath "$Evidence/lifecycle-created.json" -Encoding utf8
    [Console]::WriteLine('OWNED_OFFICIAL_STARTED ' + ($receipt | ConvertTo-Json -Depth 8 -Compress))

    # 8) 等待循环：轮询退出 + 单次 deadline 超窗记录（不改变任何进程状态）
    $deadlineExceeded = $false
    while (-not $child.HasExited) {
        [void]$child.WaitForExit(5000)
        if (-not $deadlineExceeded -and [DateTime]::UtcNow -ge $deadlineUtc) {
            $deadlineExceeded = $true
            [ordered]@{
                run_id = $runId
                pid = $child.Id
                created_utc = $createdUtc.ToString('o')
                registered_deadline_utc = $deadlineUtc.ToString('o')
                observed_at_utc = (Get-Date).ToUniversalTime().ToString('o')
                elapsed_seconds = ([DateTime]::UtcNow - $createdUtc).TotalSeconds
                action = 'none: notice only; no GUI mutation, no restart, no termination'
                qualification = 'constraints v2 hard unit window exceeded; abandon remaining work in this unit after manual wrap-up'
            } | ConvertTo-Json | Set-Content -LiteralPath "$Evidence/deadline-exceeded.json" -Encoding utf8
            [Console]::WriteLine('OWNED_OFFICIAL_DEADLINE_EXCEEDED ' + $DeadlineSeconds)
        }
    }
    [ordered]@{run_id=$runId;pid=$child.Id;created_utc=$createdUtc.ToString('o');observed_exit_at=(Get-Date).ToUniversalTime().ToString('o');exit_code=$child.ExitCode;forced=$false;deadline_exceeded=$deadlineExceeded} | ConvertTo-Json | Set-Content -LiteralPath "$Evidence/lifecycle-exited.json" -Encoding utf8
    [Console]::WriteLine('OWNED_OFFICIAL_EXITED ' + $child.ExitCode)
} catch {
    [ordered]@{run_id=$runId;observed_at=(Get-Date).ToUniversalTime().ToString('o');error=$_.ToString();child_pid=if ($child) {$child.Id} else {$null};child_still_alive=if ($child) {-not $child.HasExited} else {$false};automatic_recovery=$false;forced=$false} | ConvertTo-Json | Set-Content -LiteralPath "$Evidence/lifecycle-failure.json" -Encoding utf8
    throw
}
