param([Parameter(Mandatory)][string]$Evidence,[Parameter(Mandatory)][string]$Exe)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$procs=@(Get-CimInstance Win32_Process)
$procs | Select-Object ProcessId,ParentProcessId,Name,ExecutablePath,CreationDate,CommandLine,SessionId | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $Evidence 'preflight-processes.json') -Encoding utf8
if (@($procs | Where-Object { $_.Name -match '(?i)pianoteq' -or $_.ExecutablePath -match '(?i)pianoteq' }).Count) { throw 'Existing Pianoteq; not owning or starting anything' }
$file=Get-Item -LiteralPath $Exe
$hash=(Get-FileHash -LiteralPath $Exe -Algorithm SHA256).Hash.ToLowerInvariant()
$sig=Get-AuthenticodeSignature -LiteralPath $Exe
if ($hash -ne '7fcb5b2385a753e2f7d0a9ed068692abe877ab65b438e70a3fe2b44879b278bd' -or $sig.Status -ne 'Valid' -or $file.VersionInfo.ProductVersion -ne '9.2.5') {throw 'Official executable identity mismatch'}
$roots=@('C:\Users\Admin\AppData\Roaming\Modartt','C:\Users\Admin\AppData\Local\Modartt','C:\ProgramData\Modartt')
$records=@()
$backupRoot=Join-Path $Evidence 'protected-user-backup'
[void][IO.Directory]::CreateDirectory($backupRoot)
for ($idx=0;$idx -lt $roots.Count;$idx++) {
  $root=$roots[$idx]
  $entries=@()
  if(Test-Path -LiteralPath $root) {
    foreach($f in @(Get-ChildItem -LiteralPath $root -File -Recurse -Force)) {
      $relative=[IO.Path]::GetRelativePath($root,$f.FullName)
      $backup=Join-Path (Join-Path $backupRoot ([string]$idx)) $relative
      [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($backup))
      Copy-Item -LiteralPath $f.FullName -Destination $backup
      $sha=(Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
      $backupSha=(Get-FileHash -LiteralPath $backup -Algorithm SHA256).Hash.ToLowerInvariant()
      if($sha -ne $backupSha){throw 'User state backup mismatch'}
      $entries+=@{path=$f.FullName;relative=$relative;size=$f.Length;mtime_utc=$f.LastWriteTimeUtc.ToString('o');sha256=$sha;backup=$backup}
    }
  }
  $records+=@{root=$root;exists=(Test-Path -LiteralPath $root);files=$entries}
}
$receipt=@{created_utc=(Get-Date).ToUniversalTime().ToString('o');exe=$file.FullName;exe_sha256=$hash;version=$file.VersionInfo.ProductVersion;signature=[string]$sig.Status;signer=$sig.SignerCertificate.Subject;protected_user_roots=$records;no_existing_pianoteq=$true;backup_is_not_runtime_input=$true;no_gui_calls=$true}
$receipt | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $Evidence 'preflight-protection.json') -Encoding utf8
$receipt | ConvertTo-Json -Depth 10 -Compress
