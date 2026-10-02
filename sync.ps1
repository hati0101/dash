# 자동 동기화 한 번. 작업 스케줄러가 주기적으로 실행한다(setup-auto.ps1).
#   허브(개발컴, role=hub): 받기 → 대시보드 요청·주제 가져오기 → 자동 배분 → 알림 → 바뀐 내용만 암호화 → 검증 → 올리기
#   노드(서버컴 등, role=node): 받기 → 배정·답을 이 PC 작업자 수신 폴더로 → 이 PC 기록을 암호화 → 자기 파일만 올리기
# 비밀번호는 Windows DPAPI로 보호된 .local/pw.dpapi에서 읽는다. 각 PC는 자기 파일만 올리므로 서로 덮어쓰지 않는다.
$ErrorActionPreference = 'Continue'
Set-Location $PSScriptRoot
$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
New-Item -ItemType Directory -Force (Join-Path $PSScriptRoot '.local') | Out-Null
$log = Join-Path $PSScriptRoot '.local/sync.log'
function Log([string]$m) { ((Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + ' ' + $m) | Out-File $log -Append -Encoding utf8 }

$lock = Join-Path $PSScriptRoot '.local/sync.lock'
if ((Test-Path $lock) -and ((Get-Date) - (Get-Item $lock).LastWriteTime).TotalMinutes -lt 20) { Log '이전 동기화 실행 중 — 건너뜀'; return }
Set-Content $lock $PID

function Push-Safely([string[]]$paths) {
  # 자기 파일만 올린다. 다른 PC가 먼저 올렸으면 받아서 다시 시도한다(한 번).
  foreach ($try in 1..2) {
    $out = (git push -q origin HEAD 2>&1 | Out-String).Trim()
    if (-not $LASTEXITCODE) { return $true }
    Log "올리기 거절 — 받아서 다시 시도: $out"
    git pull -q --rebase --autostash origin main 2>&1 | Out-Null
  }
  return $false
}

try {
  if (-not (Test-Path '.local/pw.dpapi')) { Log '저장된 비밀번호 없음 — setup-auto.ps1을 먼저 실행하세요'; return }
  $sec = Get-Content '.local/pw.dpapi' | ConvertTo-SecureString
  $b = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
  try { $env:REAL_OPS_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b) }
  $cfg = Get-Content 'config.local.json' -Raw -Encoding UTF8 | ConvertFrom-Json
  $role = if ($cfg.pc -and $cfg.pc.role) { $cfg.pc.role } else { 'hub' }

  $out = (git pull -q --rebase --autostash origin main 2>&1 | Out-String).Trim()
  if ($LASTEXITCODE) { Log "받기 실패: $out" }

  if ($role -eq 'node') {
    $pcid = $cfg.pc.id
    $out = (python node.py inbox 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE) { Log "수신 전달 실패: $out" } elseif ($out -notmatch '새 전달 0건') { Log "수신 전달: $out" }
    $out = (python node.py pack --if-changed 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -eq 10) { return }
    if ($LASTEXITCODE) { Log "기록 암호화 실패: $out"; return }
    $file = "docs/nodes/$pcid.enc.json"
    git add -- $file
    $staged = @(git diff --cached --name-only)
    $bad = $staged | Where-Object { $_ -ne $file }
    if ($bad) { git reset -q; Log "노드는 자기 파일만 올립니다 — 다른 파일 감지로 중단: $($bad -join ', ')"; return }
    if ($staged.Count) { git commit -q -m ("node $pcid " + (Get-Date -Format 'yyyy-MM-dd HH:mm')) | Out-Null }
    if (Push-Safely @($file)) { if ($staged.Count) { Log "올림: $file" } } else { Log '올리기 실패' }
    return
  }

  # ---- 허브
  $out = (python topics.py pull --close 2>&1 | Out-String).Trim()
  if ($LASTEXITCODE) { Log "가져오기 실패: $out" } elseif ($out -notmatch '^새 주제·요청 없음') { Log "가져오기: $out" }
  $out = (python topics.py dispatch 2>&1 | Out-String).Trim()
  if ($LASTEXITCODE) { Log "자동 배분 실패: $out" } elseif ($out -notmatch '자동 배분 0건') { Log "자동 배분: $out" }
  $out = (python topics.py announce 2>&1 | Out-String).Trim()
  if ($out -notmatch '새 알림 0건') { Log "알림: $out" }

  $out = (python build.py --skip-unchanged 2>&1 | Out-String).Trim()
  if ($LASTEXITCODE -eq 10) { return }
  if ($LASTEXITCODE) { Log "생성 실패: $out"; return }
  $out = (python tests/verify.py 2>&1 | Out-String).Trim()
  if ($LASTEXITCODE) { Log "검증 실패 — 게시하지 않음: $out"; return }

  git add -A
  $staged = @(git diff --cached --name-only)
  $bad = $staged | Where-Object { $_ -match '^(data/(?!example\.json)|topics/|out/|\.local/|node-data/|config\.local\.json|routing\.json|GUIDE-LOCAL)' }
  if ($bad) { git reset -q; Log "평문 파일이 스테이징됨 — 중단: $($bad -join ', ')"; return }
  if ($staged.Count) { git commit -q -m ('sync ' + (Get-Date -Format 'yyyy-MM-dd HH:mm')) | Out-Null }
  if (Push-Safely $staged) { if ($staged.Count) { Log ('게시: ' + ($staged -join ', ')) } } else { Log '올리기 실패' }
} catch {
  Log ('오류: ' + $_.Exception.Message)
} finally {
  Remove-Item Env:REAL_OPS_PASSWORD -ErrorAction SilentlyContinue
  Remove-Item $lock -ErrorAction SilentlyContinue
}
