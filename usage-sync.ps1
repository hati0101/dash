# 작업실 사용량 갱신(개발컴 전용). 예약 작업 'REAL-작업실-사용량'이 15분마다 실행한다.
# 비밀번호는 setup-auto.ps1이 저장한 .local/pw.dpapi(이 PC·이 사용자만 풀 수 있음)에서 읽는다.
Set-Location $PSScriptRoot
$log = Join-Path $PSScriptRoot '.local/usage.log'
try {
  $sec = Get-Content '.local/pw.dpapi' | ConvertTo-SecureString
  $b = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
  try { $env:REAL_OPS_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b) }
  $out = (python usage_probe.py 2>&1 | Out-String).Trim()
  Add-Content -Path $log -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $out" -Encoding utf8
} catch {
  Add-Content -Path $log -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') 실패: $($_.Exception.Message)" -Encoding utf8
} finally { Remove-Item Env:REAL_OPS_PASSWORD -ErrorAction SilentlyContinue }
