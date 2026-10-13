# Task 39-2 v2 Pilot 会话 RPC 序列脚本（固化 constraints v2）。
#
# 分工：GUI 操作由主会话（windows-mcp，逐次人工审批）执行；
#       本脚本只负责非 GUI 的官方 JSON-RPC 调用与证据落盘，不接触任何 GUI。
#
# v2 修订（FXP 异步应用门禁，依据 2026-10-12 s01 会话实测）：
#   1) loadFile(FXP) 返回 result:null 不等于状态应用完成。实测：返回后 5 ms 采样到
#      中间态（unison=1.00 / equalizer_switch=On 未恢复），消融实验显示 500 ms
#      采样已完全恢复。因此所有 loadFile/loadMidiFile 之后一律「稳定等待」：
#      按 PollIntervalMs 轮询，直到连续两次快照完全一致且满足期望（全量 digest
#      或反例偏离判据），再落盘权威快照与断言结论。
#   2) prepare 增加 state_binding 要求的 restore counterexample：向固定 4 项参数
#      （unison / equalizer_switch / condition / reverb_switch）写入「与写入前读数不同」
#      的反例值（候选按 before 读数自动选择，避开引擎格式化显示差异），核验偏离生效后
#      加载 FXP，断言全量 215 项恢复为认证基线（证明 FXP 覆盖非默认值，不是空操作）。
#   3) 每个单元 pre/post 快照都做稳定性与一致性断言（post 必须逐项等于 pre）；
#      断言失败即记录证据并报错中止，不自动改写参数。
#
# v2.1 修订（依据 2026-10-12 s01 正式会话首单元实测），两处：
#   4) Load-BaselineItems 统一读取契约：既接受认证基线的 items 数组，也接受本脚本
#      落盘的 RPC receipt（含 response_raw）。修复前 unit-after 读取 unit-before 写入的
#      receipt 结构 pre-parameters.json 时只解析出 1 项并立即断言失败。
#   5) Wait-ParameterSettle 对「项数不等于 215」的采样不再立即报错，而是落盘
#      *-incomplete-NNN.json 证据并继续轮询；只有「连续两次完整且一致的快照」
#      才判 settled，超限仍未恢复时按 unstable 报错中止。
#
# Step 语义：
#   prepare       GUI 准备（Welcome/音频/Standard）完成后调用：
#                 getInfo -> FXP 身份(SHA-256) -> 反例写入+核验 -> loadFile(FXP)
#                 -> getInfo(preset 核验) -> getAudioDeviceInfo
#                 -> 稳定等待 -> 215 项基线断言 -> 权威快照
#   unit-before   导出前调用：loadMidiFile -> getSequencerInfo(核验) -> 稳定等待
#                 -> pre 快照 == 基线
#   unit-after    导出后调用：等待 WAV 完整 -> SHA-256 -> 复制 -> 复核
#                 -> 稳定等待 -> post 快照 == pre 快照
#   close         会话收尾：getInfo -> quit（quit 挂起时记录并报错，不自动强杀）
#
# 证据格式与既有批次一致（utc/pid/port/request/response_raw 或 error），
# 供 pilot-verify.py 直接解析比对。已有证据文件默认拒绝覆盖；重试须显式 -ForceRewrite。
param(
    [Parameter(Mandatory)][int]$Port,
    [Parameter(Mandatory)][int]$TargetPid,
    [Parameter(Mandatory)][string]$Evidence,
    [Parameter(Mandatory)][ValidateSet('prepare', 'unit-before', 'unit-after', 'close')][string]$Step,
    [string]$Fxp = '',
    [string]$Midi = '',
    [string]$Unit = '',
    [string]$BaselineJson = '',
    [int]$PollIntervalMs = 500,
    [int]$MaxPolls = 40,
    [int]$PlateauLimit = 8,
    [switch]$ForceRewrite,
    [int]$WaitSeconds = 180
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$script:rpcSeq = 1000
$expectedPreset = 'Task39-2 Flat Full State 20261012-060228'
$script:parameterCount = 215
# 反例参数集与候选值（不可随意变更；变更须走脚本修订并重新出证据）。
# 语义：写入「与写入前读数不同」的值；工具按 before 读数自动选择候选（见 prepare 分支）。
# 选择依据：前两项是实测最难恢复的参数（s01 实测中间态即此两项），后两项为普通控制参数。
# 候选顺序即优先级：选择第一个 text 与 before 读数不同的候选。
# 说明：Pianoteq 的 text 是格式化显示值（例如写入 '1' 读回为 '1.00'），
# 因此生效判据是「偏离 before 读数」，而不是「等于写入值」。
$script:counterexampleCandidates = @(
    [ordered]@{id = 'unison'; options = @('1.00', '0.50')},
    [ordered]@{id = 'equalizer_switch'; options = @('On', 'Off')},
    [ordered]@{id = 'condition'; options = @('1.00', '0.50')},
    [ordered]@{id = 'reverb_switch'; options = @('On', 'Off')}
)

function Save-Json([string]$Path, $Value) {
    if ((Test-Path -LiteralPath $Path) -and -not $ForceRewrite) {
        throw "evidence file already exists (use -ForceRewrite to overwrite): $Path"
    }
    [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($Path))
    $Value | ConvertTo-Json -Depth 14 | Set-Content -LiteralPath $Path -Encoding utf8
}

function Invoke-RpcRaw([string]$Method, [hashtable]$Params) {
    # 不落盘的 RPC 调用：返回 @{receipt=...; result=...} 或 @{receipt=...; error=...}。
    $script:rpcSeq += 1
    $request = [ordered]@{jsonrpc = '2.0'; id = $script:rpcSeq; method = $Method; params = $Params}
    $body = $request | ConvertTo-Json -Compress -Depth 8
    $receipt = [ordered]@{
        utc = (Get-Date).ToUniversalTime().ToString('o')
        pid = $TargetPid
        port = $Port
        request = ($body | ConvertFrom-Json)
    }
    try {
        $response = (Invoke-WebRequest -Uri "http://127.0.0.1:$Port/jsonrpc" -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 20).Content
        $receipt['response_raw'] = $response
        $parsed = $response | ConvertFrom-Json -Depth 14
        if ($parsed.PSObject.Properties.Name -contains 'error') {
            $receipt['error'] = "RPC error from ${Method}: $response"
            return [ordered]@{receipt = $receipt; error = $receipt['error']}
        }
        return [ordered]@{receipt = $receipt; result = $parsed.result}
    } catch {
        $receipt['error'] = $_.ToString()
        return [ordered]@{receipt = $receipt; error = $receipt['error']}
    }
}

function Invoke-Rpc([string]$Method, [hashtable]$Params, [string]$Name) {
    # 落盘 RPC 调用（既有行为）：失败时落 -error.json 并抛错。
    $captured = Invoke-RpcRaw -Method $Method -Params $Params
    if ($captured.Contains('error')) {
        Save-Json -Path (Join-Path $Evidence "rpc\$Name-error.json") -Value $captured.receipt
        throw $captured.error
    }
    Save-Json -Path (Join-Path $Evidence "rpc\$Name.json") -Value $captured.receipt
    return $captured.result
}

function Get-LiveStatus {
    # 供 quit 分支判断进程是否仍存活（不修改任何进程状态）。
    $process = Get-Process -Id $TargetPid -ErrorAction SilentlyContinue
    if ($null -eq $process) { return 'exited' }
    return 'alive'
}

function Read-WavInfo([string]$Path) {
    $bytes = [IO.File]::ReadAllBytes($Path)
    if ($bytes.Length -lt 44) { return $null }
    if ([Text.Encoding]::ASCII.GetString($bytes, 0, 4) -ne 'RIFF') { return $null }
    if ([Text.Encoding]::ASCII.GetString($bytes, 8, 4) -ne 'WAVE') { return $null }
    $pos = 12
    $format = $null
    $data = $null
    while ($pos + 8 -le $bytes.Length) {
        $chunkId = [Text.Encoding]::ASCII.GetString($bytes, $pos, 4)
        $chunkSize = [BitConverter]::ToUInt32($bytes, $pos + 4)
        if ($chunkId -eq 'fmt ' -and ($pos + 8 + 16) -le $bytes.Length) {
            $format = [ordered]@{
                channels = [BitConverter]::ToUInt16($bytes, $pos + 10)
                sample_rate = [BitConverter]::ToUInt32($bytes, $pos + 12)
                bit_depth = [BitConverter]::ToUInt16($bytes, $pos + 22)
            }
        }
        if ($chunkId -eq 'data') {
            $data = [ordered]@{offset = $pos + 8; size = $chunkSize}
        }
        $pos += 8 + $chunkSize + ($chunkSize % 2)
    }
    if ($null -eq $format -or $null -eq $data) { return $null }
    $blockAlign = [int]$format.channels * [int]$format.bit_depth / 8
    $frames = 0
    if ($blockAlign -gt 0) { $frames = [math]::Floor([double]$data.size / $blockAlign) }
    $duration = 0.0
    if ($format.sample_rate -gt 0) { $duration = [double]$frames / [double]$format.sample_rate }
    return [ordered]@{
        channels = $format.channels
        sample_rate = $format.sample_rate
        bit_depth = $format.bit_depth
        frames = $frames
        duration_seconds = $duration
        data_size = $data.size
        file_bytes = $bytes.Length
        complete = (($data.offset + $data.size) -le $bytes.Length)
    }
}

function Assert-Preset([string]$InfoName, $result) {
    $preset = $result[0].current_preset.name
    if ($preset -ne $expectedPreset) {
        throw "preset verification failed after ${InfoName}: got '$preset', expected '$expectedPreset'"
    }
}

function Get-FileIdentity([string]$Path) {
    $file = Get-Item -LiteralPath $Path
    return [ordered]@{
        path = $file.FullName
        bytes = $file.Length
        sha256 = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
        last_write_utc = $file.LastWriteTimeUtc.ToString('o')
    }
}

function Get-CanonicalParameterRows($items) {
    # 规范化行（id 排序）：id|text|normalized(R, invariant)，用于快照 digest。
    $rows = @()
    foreach ($it in ($items | Sort-Object { $_.id })) {
        $norm = [double]$it.normalized_value
        $normText = $norm.ToString('R', [Globalization.CultureInfo]::InvariantCulture)
        $rows += ("$($it.id)|$($it.text)|$normText")
    }
    return , $rows
}

function Get-RowsDigest($rows) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes(($rows -join "`n"))
        return (($sha.ComputeHash($bytes) | ForEach-Object { $_.ToString('x2') }) -join '')
    } finally { $sha.Dispose() }
}

function Assert-ParameterSet($items) {
    $count = @($items).Count
    if ($null -eq $items -or $count -ne $script:parameterCount) {
        throw "parameter snapshot must contain $script:parameterCount items, got $count"
    }
}

function Get-ParameterMap($items) {
    $map = @{}
    foreach ($it in $items) { $map[$it.id] = $it }
    return $map
}

function Get-ParameterDrift($currentItems, $expectedItems) {
    # 逐项比较 text 与 normalized_value；返回 drift 列表。
    $cur = Get-ParameterMap $currentItems
    $exp = Get-ParameterMap $expectedItems
    $drift = @()
    foreach ($id in ($exp.Keys | Sort-Object)) {
        $e = $exp[$id]
        $c = $cur[$id]
        if ($null -eq $c) {
            $drift += [ordered]@{id = $id; expected = $e.text; actual = '(missing)'}
            continue
        }
        $sameText = ([string]$c.text -eq [string]$e.text)
        $sameNorm = ([double]$c.normalized_value -eq [double]$e.normalized_value)
        if (-not $sameText -or -not $sameNorm) {
            $drift += [ordered]@{id = $id; expected = $e.text; actual = $c.text}
        }
    }
    return , $drift
}

function Test-CounterexampleActive($items, $beforeItems, $ids) {
    # 反例生效判据：每个目标参数的 (text, normalized_value) 至少一项偏离写入前读数。
    $cur = Get-ParameterMap $items
    $bef = Get-ParameterMap $beforeItems
    foreach ($id in $ids) {
        $c = $cur[$id]
        $b = $bef[$id]
        if ($null -eq $c -or $null -eq $b) { return $false }
        $sameText = ([string]$c.text -eq [string]$b.text)
        $sameNorm = ([double]$c.normalized_value -eq [double]$b.normalized_value)
        if ($sameText -and $sameNorm) { return $false }
    }
    return $true
}

function Load-BaselineItems([string]$Path) {
    # v2.1：既接受「认证基线的 items 数组」，也接受本脚本落盘的 RPC receipt
    # （对象含 response_raw）。unit-before 的 pre-parameters.json 是 receipt 结构。
    $obj = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    if ($obj.PSObject.Properties.Name -contains 'response_raw') {
        $items = @(($obj.response_raw | ConvertFrom-Json -Depth 14).result)
    } else {
        $items = @($obj)
    }
    Assert-ParameterSet $items
    return , $items
}

function Wait-ParameterSettle {
    # 轮询 getParameters，直到「连续两次快照 digest 完全一致」且满足期望：
    #   -ExpectItems          全量期望（digest 相等）
    #   -DeviationIds         需偏离 -DeviationBaseItems 的参数 id 列表（反例生效判据）
    # 满足期望前若在「稳定但不满足期望」的平台上停留 PlateauAllowance 次采样，判 plateau 失败。
    # 返回 outcome = settled | plateau | unstable。
    param(
        [Parameter(Mandatory)][string]$Prefix,
        [Parameter(Mandatory)][string]$PollDir,
        [int]$IntervalMs = 500,
        [int]$Limit = 40,
        [int]$PlateauAllowance = 8,
        $ExpectItems = $null,
        $DeviationIds = $null,
        $DeviationBaseItems = $null
    )
    if ($null -eq $ExpectItems -and $null -eq $DeviationIds) {
        throw 'Wait-ParameterSettle requires -ExpectItems or -DeviationIds'
    }
    if ($null -ne $DeviationIds -and $null -eq $DeviationBaseItems) {
        throw 'Wait-ParameterSettle requires -DeviationBaseItems together with -DeviationIds'
    }
    $expectDigest = $null
    if ($null -ne $ExpectItems) {
        $expectDigest = Get-RowsDigest (Get-CanonicalParameterRows $ExpectItems)
    }
    $t0 = Get-Date
    $lastDigest = $null
    $sameCount = 0
    $nonMatchStable = 0
    $sequence = @()
    $items = $null
    $digest = $null
    $receipt = $null
    $elapsed = 0
    for ($i = 0; $i -lt $Limit; $i++) {
        Start-Sleep -Milliseconds $IntervalMs
        $captured = Invoke-RpcRaw -Method 'getParameters' -Params @{}
        if ($captured.Contains('error')) {
            Save-Json -Path (Join-Path $PollDir ("{0}-poll-error.json" -f $Prefix)) -Value $captured.receipt
            throw ("parameter poll failed during {0}: {1}" -f $Prefix, $captured.error)
        }
        $items = @($captured.result)
        $receipt = $captured.receipt
        if ($null -eq $captured.result -or $items.Count -ne $script:parameterCount) {
            # v2.1：未就绪容忍（例如导出后引擎短时只暴露部分参数）。记录证据并继续轮询，
            # 该采样不参与 digest 稳定计数；只有「连续两次完整且一致的快照」才可能判 settled。
            $elapsedInc = [math]::Round(((Get-Date) - $t0).TotalMilliseconds)
            Save-Json -Path (Join-Path $PollDir ("{0}-incomplete-{1:d3}.json" -f $Prefix, ($i + 1))) -Value ([ordered]@{
                utc = $receipt.utc; poll_index = $i + 1; elapsed_ms = $elapsedInc; item_count = $items.Count
            })
            $sequence += [ordered]@{utc = $receipt.utc; elapsed_ms = $elapsedInc; digest = '(incomplete)'; same_count = 0; item_count = $items.Count}
            $lastDigest = $null
            $sameCount = 0
            $nonMatchStable = 0
            continue
        }
        $digest = Get-RowsDigest (Get-CanonicalParameterRows $items)
        $elapsed = [math]::Round(((Get-Date) - $t0).TotalMilliseconds)
        if ($digest -eq $lastDigest) {
            $sameCount += 1
        } else {
            $sameCount = 1
            $nonMatchStable = 0
        }
        $lastDigest = $digest
        $sequence += [ordered]@{utc = $receipt.utc; elapsed_ms = $elapsed; digest = $digest; same_count = $sameCount}
        if ($i -eq 0) {
            Save-Json -Path (Join-Path $PollDir ("{0}-poll-000.json" -f $Prefix)) -Value $receipt
        }
        if ($sameCount -ge 2) {
            $matched = $false
            if ($null -ne $ExpectItems) {
                $matched = ($digest -eq $expectDigest)
            } else {
                $matched = (Test-CounterexampleActive $items $DeviationBaseItems $DeviationIds)
            }
            if ($matched) {
                return [ordered]@{
                    outcome = 'settled'; items = $items; receipt = $receipt; digest = $digest
                    expect_digest = $expectDigest; polls_used = $i + 1; settled_after_ms = $elapsed
                    sequence = $sequence
                }
            }
            $nonMatchStable += 1
            if ($nonMatchStable -ge $PlateauAllowance) {
                return [ordered]@{
                    outcome = 'plateau'; items = $items; receipt = $receipt; digest = $digest
                    expect_digest = $expectDigest; polls_used = $i + 1; settled_after_ms = $elapsed
                    sequence = $sequence
                }
            }
        }
    }
    return [ordered]@{
        outcome = 'unstable'; items = $items; receipt = $receipt; digest = $digest
        expect_digest = $expectDigest; polls_used = $Limit; settled_after_ms = $elapsed
        sequence = $sequence
    }
}

function Get-SettleSummary([string]$Prefix, $Wait) {
    return [ordered]@{
        utc = (Get-Date).ToUniversalTime().ToString('o')
        prefix = $Prefix
        poll_interval_ms = $PollIntervalMs
        max_polls = $MaxPolls
        plateau_limit = $PlateauLimit
        outcome = $Wait.outcome
        polls_used = $Wait.polls_used
        settled_after_ms = $Wait.settled_after_ms
        final_digest = $Wait.digest
        expected_digest = $Wait.expect_digest
        sequence = $Wait.sequence
    }
}

function Assert-BaselineOrThrow([string]$Prefix, [string]$EvidenceDir, $Wait, $BaselineItems) {
    # 双实现断言：digest 已在 settle 中匹配；这里再做逐项比较（独立第二判据）。
    $summary = Get-SettleSummary $Prefix $Wait
    if ($Wait.outcome -ne 'settled') {
        Save-Json -Path (Join-Path $EvidenceDir ("{0}-settle-failure.json" -f $Prefix)) -Value $summary
        throw ("{0}: parameter state did not settle to baseline (outcome={1}, polls={2}, digest={3}, expected={4})" -f $Prefix, $Wait.outcome, $Wait.polls_used, $Wait.digest, $Wait.expect_digest)
    }
    $drift = Get-ParameterDrift $Wait.items $BaselineItems
    $assertion = [ordered]@{
        utc = (Get-Date).ToUniversalTime().ToString('o')
        prefix = $Prefix
        snapshot_digest = $Wait.digest
        expected_digest = $Wait.expect_digest
        drift_count = $drift.Count
        drift = $drift
        ok = ($drift.Count -eq 0)
    }
    Save-Json -Path (Join-Path $EvidenceDir ("{0}-baseline-assertion.json" -f $Prefix)) -Value $assertion
    if ($drift.Count -ne 0) {
        Save-Json -Path (Join-Path $EvidenceDir ("{0}-settle-failure.json" -f $Prefix)) -Value $summary
        throw ("{0}: parameter drift against baseline detected (count={1})" -f $Prefix, $drift.Count)
    }
    return $assertion
}

# 基线注入（prepare/unit-before/unit-after 必需）。
$baselineItems = $null
if ($Step -ne 'close') {
    if ([string]::IsNullOrWhiteSpace($BaselineJson)) { throw '-BaselineJson is required for this step' }
    if (-not (Test-Path -LiteralPath $BaselineJson)) { throw "baseline not found: $BaselineJson" }
    $baselineItems = Load-BaselineItems $BaselineJson
}

switch ($Step) {
    'prepare' {
        if ([string]::IsNullOrWhiteSpace($Fxp)) { throw '-Fxp is required for prepare' }
        if (-not (Test-Path -LiteralPath $Fxp)) { throw "FXP not found: $Fxp" }
        $rpcDir = Join-Path $Evidence 'rpc'
        [void][IO.Directory]::CreateDirectory($rpcDir)
        $info = Invoke-Rpc -Method 'getInfo' -Params @{} -Name 'prepare-info'
        Save-Json -Path (Join-Path $Evidence 'rpc\prepare-ready.json') -Value ([ordered]@{
            utc = (Get-Date).ToUniversalTime().ToString('o')
            preset_at_gui_ready = $info[0].current_preset.name
            plugin_type = $info[0].plugin_type
            version = $info[0].version
        })
        # 1) FXP 身份（协议要求：exact producer version/preset/bank/FXP hash）。
        $fxpIdentity = Get-FileIdentity $Fxp
        Save-Json -Path (Join-Path $Evidence 'rpc\prepare-fxp-identity.json') -Value $fxpIdentity
        # 2) restore counterexample：写入「偏离写入前读数」的反例值并核验生效。
        $beforeItems = @(Invoke-Rpc -Method 'getParameters' -Params @{} -Name 'prepare-counterexample-before')
        Assert-ParameterSet $beforeItems
        $beforeMap = Get-ParameterMap $beforeItems
        $cxPlan = @()
        foreach ($entry in $script:counterexampleCandidates) {
            $beforeText = [string]$beforeMap[$entry.id].text
            $chosen = $null
            foreach ($option in $entry.options) {
                if ($option -ne $beforeText) { $chosen = $option; break }
            }
            if ($null -eq $chosen) { throw ("counterexample candidate exhausted for $($entry.id): all options equal before text '$beforeText'") }
            $cxPlan += [ordered]@{id = $entry.id; before_text = $beforeText; chosen_text = $chosen}
        }
        Save-Json -Path (Join-Path $Evidence 'rpc\prepare-counterexample-plan.json') -Value ([ordered]@{
            utc = (Get-Date).ToUniversalTime().ToString('o')
            plan = $cxPlan
        })
        $cxWriteList = @($cxPlan | ForEach-Object { [ordered]@{id = $_.id; text = $_.chosen_text} })
        [void](Invoke-Rpc -Method 'setParameters' -Params @{list = $cxWriteList} -Name 'prepare-counterexample-write')
        $deviationIds = @($cxPlan | ForEach-Object { $_.id })
        $cxWait = Wait-ParameterSettle -Prefix 'prepare-counterexample' -PollDir $rpcDir `
            -IntervalMs $PollIntervalMs -Limit $MaxPolls -PlateauAllowance $PlateauLimit `
            -DeviationIds $deviationIds -DeviationBaseItems $beforeItems
        if ($cxWait.outcome -ne 'settled') {
            Save-Json -Path (Join-Path $Evidence 'rpc\prepare-counterexample-failure.json') -Value (Get-SettleSummary 'prepare-counterexample' $cxWait)
            throw ("prepare: counterexample write did not take effect (outcome={0}, polls={1})" -f $cxWait.outcome, $cxWait.polls_used)
        }
        Save-Json -Path (Join-Path $Evidence 'rpc\prepare-counterexample-pre.json') -Value $cxWait.receipt
        # 偏离明细（restore counterexample 的写入侧证据）。
        $cxMap = Get-ParameterMap $cxWait.items
        $delta = @()
        foreach ($entry in $cxPlan) {
            $b = $beforeMap[$entry.id]
            $a = $cxMap[$entry.id]
            $delta += [ordered]@{
                id = $entry.id
                before_text = $b.text
                before_normalized = $b.normalized_value
                after_text = $a.text
                after_normalized = $a.normalized_value
                chosen_text = $entry.chosen_text
                deviated = (([string]$a.text -ne [string]$b.text) -or ([double]$a.normalized_value -ne [double]$b.normalized_value))
            }
        }
        Save-Json -Path (Join-Path $Evidence 'rpc\prepare-counterexample-delta.json') -Value ([ordered]@{
            utc = (Get-Date).ToUniversalTime().ToString('o')
            items = $delta
        })
        # 3) 加载 FXP，核验 preset 与音频设备。
        [void](Invoke-Rpc -Method 'loadFile' -Params @{path = $Fxp} -Name 'prepare-fxp-load')
        $after = Invoke-Rpc -Method 'getInfo' -Params @{} -Name 'prepare-after-fxp-info'
        Assert-Preset 'fxp-load' $after
        $audio = Invoke-Rpc -Method 'getAudioDeviceInfo' -Params @{} -Name 'prepare-audio-device'
        # 4) 稳定等待 + 全量基线断言（FXP 覆盖含反例项在内的全部 215 项）。
        $wait = Wait-ParameterSettle -Prefix 'prepare' -PollDir $rpcDir `
            -IntervalMs $PollIntervalMs -Limit $MaxPolls -PlateauAllowance $PlateauLimit `
            -ExpectItems $baselineItems
        $assertion = Assert-BaselineOrThrow 'prepare' $rpcDir $wait $baselineItems
        Save-Json -Path (Join-Path $Evidence 'rpc\prepare-settle.json') -Value (Get-SettleSummary 'prepare' $wait)
        Save-Json -Path (Join-Path $Evidence 'rpc\prepare-parameters.json') -Value $wait.receipt
        [Console]::WriteLine('PILOT_STEP_PREPARE_OK preset=' + $after[0].current_preset.name +
            ' audio=' + $audio.device_type + '/' + $audio.sample_rate +
            ' fxp_sha256=' + $fxpIdentity.sha256 +
            ' settled_ms=' + $wait.settled_after_ms + ' polls=' + $wait.polls_used +
            ' drift=0')
    }
    'unit-before' {
        if ([string]::IsNullOrWhiteSpace($Midi) -or [string]::IsNullOrWhiteSpace($Unit)) { throw '-Midi and -Unit are required for unit-before' }
        if (-not (Test-Path -LiteralPath $Midi)) { throw "MIDI not found: $Midi" }
        $unitDir = Join-Path $Evidence "units\$Unit"
        if (Test-Path -LiteralPath (Join-Path $unitDir 'pre-parameters.json')) {
            throw "unit already has pre-parameters.json; refusing duplicate unit-before (use -ForceRewrite and manual cleanup)"
        }
        [void][IO.Directory]::CreateDirectory($unitDir)
        [void](Invoke-Rpc -Method 'loadMidiFile' -Params @{path = $Midi} -Name "unit-before-midi-load-$Unit")
        $info = Invoke-Rpc -Method 'getSequencerInfo' -Params @{} -Name "unit-before-sequencer-info-$Unit"
        $expectedName = [IO.Path]::GetFileName($Midi)
        if ($info[0].name -ne $expectedName) {
            throw "sequencer verification failed: got '$($info[0].name)', expected '$expectedName'"
        }
        $wait = Wait-ParameterSettle -Prefix ("unit-{0}-pre" -f $Unit) -PollDir (Join-Path $Evidence 'rpc') `
            -IntervalMs $PollIntervalMs -Limit $MaxPolls -PlateauAllowance $PlateauLimit `
            -ExpectItems $baselineItems
        $assertion = Assert-BaselineOrThrow ("unit-{0}-pre" -f $Unit) $unitDir $wait $baselineItems
        Save-Json -Path (Join-Path $unitDir 'pre-settle.json') -Value (Get-SettleSummary ("unit-{0}-pre" -f $Unit) $wait)
        Save-Json -Path (Join-Path $unitDir 'pre-parameters.json') -Value $wait.receipt
        [Console]::WriteLine('PILOT_STEP_UNIT_BEFORE_OK unit=' + $Unit + ' midi=' + $info[0].name +
            ' duration=' + $info[0].duration + ' settled_ms=' + $wait.settled_after_ms + ' polls=' + $wait.polls_used)
    }
    'unit-after' {
        if ([string]::IsNullOrWhiteSpace($Midi) -or [string]::IsNullOrWhiteSpace($Unit)) { throw '-Midi and -Unit are required for unit-after' }
        $unitDir = Join-Path $Evidence "units\$Unit"
        $stem = [IO.Path]::GetFileNameWithoutExtension($Midi)
        $wavPath = Join-Path $Evidence "private-home\Documents\$stem.wav"
        # 等待渲染完成：大小稳定 + RIFF/WAVE 头 + data chunk 完整落盘
        $deadline = (Get-Date).AddSeconds($WaitSeconds)
        $lastSize = -1
        $stable = 0
        $wavInfo = $null
        while ((Get-Date) -lt $deadline) {
            if (Test-Path -LiteralPath $wavPath) {
                $size = (Get-Item -LiteralPath $wavPath).Length
                if ($size -eq $lastSize -and $size -gt 0) { $stable += 1 } else { $stable = 0 }
                $lastSize = $size
                if ($stable -ge 2) {
                    $candidate = Read-WavInfo -Path $wavPath
                    if ($null -ne $candidate -and $candidate.complete) { $wavInfo = $candidate; break }
                }
            }
            Start-Sleep -Seconds 2
        }
        if ($null -eq $wavInfo) { throw "export WAV did not complete within $WaitSeconds seconds: $wavPath" }
        $sha = (Get-FileHash -LiteralPath $wavPath -Algorithm SHA256).Hash.ToLowerInvariant()
        $exportPath = Join-Path $unitDir 'export.wav'
        [void][IO.Directory]::CreateDirectory($unitDir)
        if ((Test-Path -LiteralPath $exportPath) -and -not $ForceRewrite) {
            throw "export.wav already exists (use -ForceRewrite to overwrite): $exportPath"
        }
        Copy-Item -LiteralPath $wavPath -Destination $exportPath -Force:$ForceRewrite
        $shaCopy = (Get-FileHash -LiteralPath $exportPath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($sha -ne $shaCopy) { throw 'export copy verification failed: SHA-256 mismatch' }
        Save-Json -Path (Join-Path $unitDir 'wav-receipt.json') -Value ([ordered]@{
            unit = $Unit
            source_path = $wavPath
            export_path = $exportPath
            sha256 = $sha
            bytes = (Get-Item -LiteralPath $exportPath).Length
            channels = $wavInfo.channels
            sample_rate = $wavInfo.sample_rate
            bit_depth = $wavInfo.bit_depth
            frames = $wavInfo.frames
            duration_seconds = $wavInfo.duration_seconds
            captured_utc = (Get-Date).ToUniversalTime().ToString('o')
        })
        # post 快照必须逐项等于 pre 快照（导出不得改变参数状态）。
        $prePath = Join-Path $unitDir 'pre-parameters.json'
        if (-not (Test-Path -LiteralPath $prePath)) { throw "unit-before pre-parameters.json missing; cannot assert post consistency: $prePath" }
        $preItems = Load-BaselineItems $prePath
        $wait = Wait-ParameterSettle -Prefix ("unit-{0}-post" -f $Unit) -PollDir (Join-Path $Evidence 'rpc') `
            -IntervalMs $PollIntervalMs -Limit $MaxPolls -PlateauAllowance $PlateauLimit `
            -ExpectItems $preItems
        $drift = @()
        $summary = Get-SettleSummary ("unit-{0}-post" -f $Unit) $wait
        if ($wait.outcome -eq 'settled') {
            $drift = Get-ParameterDrift $wait.items $preItems
        }
        Save-Json -Path (Join-Path $unitDir 'post-consistency.json') -Value ([ordered]@{
            utc = (Get-Date).ToUniversalTime().ToString('o')
            unit = $Unit
            outcome = $wait.outcome
            polls_used = $wait.polls_used
            settled_after_ms = $wait.settled_after_ms
            snapshot_digest = $wait.digest
            expected_digest = $wait.expect_digest
            drift_count = $drift.Count
            drift = $drift
            ok = (($wait.outcome -eq 'settled') -and ($drift.Count -eq 0))
        })
        if ($wait.outcome -ne 'settled') {
            Save-Json -Path (Join-Path $unitDir 'post-settle-failure.json') -Value $summary
            throw ("unit-after: post-export parameter state did not settle back to pre state (outcome={0}, polls={1})" -f $wait.outcome, $wait.polls_used)
        }
        if ($drift.Count -ne 0) {
            throw ("unit-after: post-export parameter drift against pre state detected (count={0})" -f $drift.Count)
        }
        Save-Json -Path (Join-Path $unitDir 'post-parameters.json') -Value $wait.receipt
        [Console]::WriteLine('PILOT_STEP_UNIT_AFTER_OK unit=' + $Unit + ' sha256=' + $sha + ' bytes=' + $wavInfo.file_bytes +
            ' post_settled_ms=' + $wait.settled_after_ms + ' post_polls=' + $wait.polls_used)
    }
    'close' {
        [void](Invoke-Rpc -Method 'getInfo' -Params @{} -Name 'close-info')
        $script:rpcSeq += 1
        $request = [ordered]@{jsonrpc = '2.0'; id = $script:rpcSeq; method = 'quit'; params = @{}}
        $body = $request | ConvertTo-Json -Compress -Depth 8
        $receipt = [ordered]@{
            utc = (Get-Date).ToUniversalTime().ToString('o')
            pid = $TargetPid
            port = $Port
            request = ($body | ConvertFrom-Json)
        }
        try {
            $response = (Invoke-WebRequest -Uri "http://127.0.0.1:$Port/jsonrpc" -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 20).Content
            $receipt['response_raw'] = $response
            Save-Json -Path (Join-Path $Evidence 'rpc\close-quit.json') -Value $receipt
            [Console]::WriteLine('PILOT_STEP_CLOSE_OK quit_accepted')
        } catch {
            $receipt['error'] = $_.ToString()
            $receipt['process_alive_after'] = (Get-LiveStatus)
            Save-Json -Path (Join-Path $Evidence 'rpc\close-quit-error.json') -Value $receipt
            if ($receipt['process_alive_after'] -eq 'alive') {
                throw 'quit did not terminate the process; hanging-state handling required (record stdio, request external kill authorization)'
            }
            [Console]::WriteLine('PILOT_STEP_CLOSE_OK connection_closed_but_process_exited')
        }
    }
}
