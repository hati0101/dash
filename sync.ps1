# 자동 동기화 한 번: GitHub에서 대시보드 요청·주제 가져오기 → 처리·알림 → 바뀐 내용만 암호화 → 검증 → push
# 작업 스케줄러가 주기적으로 실행한다(setup-auto.ps1). 비밀번호는 Windows DPAPI로 보호된 .local/pw.dpapi에서 읽는다.
$ErrorActionPreference = 'Continue'
Set-Location $PSScriptRoot
$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
New-Item -ItemType Directory -Force (Join-Path $PSScriptRoot '.local') | Out-Null
$log = Join-Path $PSScriptRoot '.local/sync.log'
function Log([string]$m) { ((Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + ' ' + $m) | Out-File $log -Append -Encoding utf8 }

# 겹쳐 실행 방지 (20분 넘은 잠금은 비정상 종료로 보고 무시)
$lock = Join-Path $PSScriptRoot '.local/sync.lock'
if ((Test-Path $lock) -and ((Get-Date) - (Get-Item $lock).LastWriteTime).TotalMinutes -lt 20) { Log '이전 동기화 실행 중 — 건너뜀'; return }
Set-Content $lock $PID

try {
  if (-not (Test-Path '.local/pw.dpapi')) { Log '저장된 비밀번호 없음 — setup-auto.ps1을 먼저 실행하세요'; return }
  $sec = Get-Content '.local/pw.dpapi' | ConvertTo-SecureString
  $b = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
  try { $env:REAL_OPS_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b) }

  $out = (python topics.py pull --close 2>&1 | Out-String).Trim()
  if ($LASTEXITCODE) { Log "가져오기 실패: $out" } elseif ($out -notmatch '^새 주제·요청 없음') { Log "가져오기: $out" }
  $out = (python topics.py announce 2>&1 | Out-String).Trim()
  if ($out -notmatch '새 알림 0건') { Log "알림: $out" }

  $out = (python build.py --skip-unchanged 2>&1 | Out-String).Trim()
  if ($LASTEXITCODE -eq 10) { return }
  if ($LASTEXITCODE) { Log "생성 실패: $out"; return }
  $out = (python tests/verify.py 2>&1 | Out-String).Trim()
  if ($LASTEXITCODE) { Log "검증 실패 — 게시하지 않음: $out"; return }

  git add -A
  $staged = @(git diff --cached --name-only)
  $bad = $staged | Where-Object { $_ -match '^(data/(?!example\.json)|topics/|out/|\.local/|config\.local\.json|GUIDE-LOCAL)' }
  if ($bad) { git reset -q; Log "평문 파일이 스테이징됨 — 중단: $($bad -join ', ')"; return }
  if ($staged.Count) { git commit -q -m ('sync ' + (Get-Date -Format 'yyyy-MM-dd HH:mm')) | Out-Null }
  $out = (git push -q origin HEAD 2>&1 | Out-String).Trim()
  if ($LASTEXITCODE) { Log "push 실패: $out"; return }
  if ($staged.Count) { Log ('게시: ' + ($staged -join ', ')) }
} catch {
  Log ('오류: ' + $_.Exception.Message)
} finally {
  Remove-Item Env:REAL_OPS_PASSWORD -ErrorAction SilentlyContinue
  Remove-Item $lock -ErrorAction SilentlyContinue
}
