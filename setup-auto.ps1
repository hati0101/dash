# 자동 동기화 켜기/끄기 (한 번만 실행)
#   켜기: powershell -ExecutionPolicy Bypass -File setup-auto.ps1
#   끄기: powershell -ExecutionPolicy Bypass -File setup-auto.ps1 -Remove
# 비밀번호는 Windows DPAPI로 암호화해 .local/pw.dpapi에 둔다. 이 PC의 이 Windows 계정만 풀 수 있다.
param([switch]$Remove, [int]$Minutes = 10)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$name = 'REAL-ops-dashboard-sync'

if ($Remove) {
  Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
  Remove-Item '.local/pw.dpapi' -ErrorAction SilentlyContinue
  Write-Host '자동 동기화를 끄고 저장된 비밀번호를 지웠습니다.'
  return
}

$sec = Read-Host -AsSecureString '대시보드 비밀번호 (게시할 때 쓴 것)'
$b = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
try { $env:REAL_OPS_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b) }
try {
  node encrypt.mjs decrypt docs/data.enc.json | Out-Null
  if ($LASTEXITCODE) { throw '비밀번호가 현재 게시본과 맞지 않습니다. 다시 실행해주세요.' }
} finally { Remove-Item Env:REAL_OPS_PASSWORD -ErrorAction SilentlyContinue }

New-Item -ItemType Directory -Force '.local' | Out-Null
$sec | ConvertFrom-SecureString | Set-Content '.local/pw.dpapi'

# 창이 깜빡이지 않도록 wscript로 숨겨서 실행
$vbs = Join-Path $PSScriptRoot '.local/sync-hidden.vbs'
$cmd = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $PSScriptRoot 'sync.ps1') + '"'
Set-Content $vbs ('CreateObject("WScript.Shell").Run "' + $cmd.Replace('"', '""') + '", 0, False') -Encoding ASCII

$action = New-ScheduledTaskAction -Execute 'wscript.exe' -Argument ('"' + $vbs + '"')
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes $Minutes)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 15)
Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Force `
  -Description 'REAL 운영 대시보드: 대시보드 요청 가져오기·처리, 바뀐 내용만 암호화 게시' | Out-Null
Write-Host "자동 동기화를 켰습니다. ${Minutes}분마다 실행되고, 기록은 .local\sync.log에 남습니다."
