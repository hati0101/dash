# 자동 동기화 한 번. 작업 스케줄러가 주기적으로 실행한다(setup-auto.ps1).
#   허브(개발컴, role=hub): 받기 → 대시보드 요청·주제 가져오기 → 자동 배분 → 알림 → 바뀐 내용만 암호화 → 검증 → 올리기
#   노드(서버컴 등, role=node): 받기 → 배정·답을 이 PC 작업자 수신 폴더로 → 이 PC 기록을 암호화 → 자기 파일만 올리기
# 비밀번호는 Windows DPAPI로 보호된 .local/pw.dpapi에서 읽는다. 각 PC는 자기 파일만 올리므로 서로 덮어쓰지 않는다.
# -FromRunner: 자동 실행기가 결과를 바로 올릴 때 부른다(실행기를 다시 띄우지 않는다).
param([switch]$FromRunner)
$ErrorActionPreference = 'Continue'
Set-Location $PSScriptRoot
$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
# 예약 작업 환경의 기본 문자표(cp949) 때문에 python 출력이 깨지거나 예외가 나지 않게 UTF-8로 고정
$env:PYTHONUTF8 = '1'; $env:PYTHONIOENCODING = 'utf-8'
# python이 UTF-8로 내보내므로 PowerShell도 UTF-8로 읽어야 기록(sync.log)의 한글이 깨지지 않는다
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }
New-Item -ItemType Directory -Force (Join-Path $PSScriptRoot '.local') | Out-Null
$log = Join-Path $PSScriptRoot '.local/sync.log'
function Log([string]$m) { ((Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + ' ' + $m) | Out-File $log -Append -Encoding utf8 }
# python 출력과 오류를 cmd에서 합쳐 받는다(PowerShell 5의 오류 레코드 장식이 기록에 섞이지 않게). 종료 코드는 $LASTEXITCODE로 남는다.
function Py([string]$a) { (cmd /c "python $a 2>&1" | Out-String).Trim() }

# 도구를 고치는 동안 잠시 멈춤: .local/pause 파일이 있으면 아무것도 하지 않는다(반쯤 고친 상태가 게시·실행되지 않게)
if (Test-Path (Join-Path $PSScriptRoot '.local/pause')) { Log '일시 정지(.local/pause) — 건너뜀'; return }
$lock = Join-Path $PSScriptRoot '.local/sync.lock'
if ((Test-Path $lock) -and ((Get-Date) - (Get-Item $lock).LastWriteTime).TotalMinutes -lt 20) { Log '이전 동기화 실행 중 — 건너뜀'; return }
Set-Content $lock $PID

# 자동 실행기: 이 PC 작업자 차례인 일이 있으면 그 AI를 화면 없이 깨운다. 따로 돌게 띄워 동기화는 바로 끝난다.
# (비밀번호 환경 변수는 실행기에만 이어지고, 실행기는 AI 프로세스에 넘기지 않는다)
function Start-Runner {
  if ($FromRunner -or -not (Test-Path (Join-Path $PSScriptRoot 'runner.py'))) { return }
  try {
    Start-Process -FilePath 'python' -ArgumentList 'runner.py' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
  } catch { Log ('자동 실행기 시작 실패: ' + $_.Exception.Message) }
}

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
  # 게시 시간대(아키텍트 결정 2026-10-02): 오전 7시~자정에만 공개 저장소에 올린다. 밤에는 받기·배분·AI 실행은 계속하고 올리기만 쉰다.
  # config.local.json "publish_hours": [시작, 끝]으로 바꿀 수 있다(끝 24 = 자정).
  $ph = if ($cfg.publish_hours) { @($cfg.publish_hours) } else { @(0, 24) }  # 2026-10-03 아키텍트: 24시간 게시
  function Quiet { $h = (Get-Date).Hour; return -not ($h -ge [int]$ph[0] -and $h -lt [int]$ph[1]) }

  # 한 번 동기화. 예약 작업은 10분마다 시작하지만, 그 안에서 1분 간격으로 여러 번 돌려
  # AI 결과·다른 PC 기록이 들어오면 1~2분 안에 대시보드에 반영되게 한다(바뀐 게 없으면 아무것도 올리지 않는다).
  function Sync-Once {
  if (Test-Path (Join-Path $PSScriptRoot '.local/pause')) { return }  # 반복 도중에 멈춤을 걸어도 바로 멈춘다
  $out = (git pull -q --rebase --autostash origin main 2>&1 | Out-String).Trim()
  if ($LASTEXITCODE) { Log "받기 실패: $out" }

  if ($role -eq 'node') {
    $pcid = $cfg.pc.id
    $out = Py 'node.py inbox'
    if ($LASTEXITCODE) { Log "수신 전달 실패: $out" } elseif ($out -notmatch '새 전달 0건') { Log "수신 전달: $out" }
    Start-Runner
    if (Quiet) { return }
    $out = Py 'node.py pack --if-changed'
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
  if ($cfg.github_repo) {
    $out = Py 'topics.py pull --close'
    if ($LASTEXITCODE) { Log "가져오기 실패: $out" } elseif ($out -notmatch '^새 주제·요청 없음') { Log "가져오기: $out" }
  }
  $out = Py 'topics.py import-proposals'
  if ($LASTEXITCODE) { Log "메모 가져오기 실패: $out" } elseif ($out -notmatch '메모 가져오기 0건') { Log "메모 가져오기: $out" }
  $out = Py 'topics.py spawn-followups'  # ★결과 확인에서 '후속 구현'을 고른 주제 → 새 구현 주제
  if ($LASTEXITCODE) { Log "후속 주제 만들기 실패: $out" } elseif ($out -notmatch '후속 구현 주제 0건') { Log "후속 주제: $out" }
  $out = Py 'topics.py dispatch'
  if ($LASTEXITCODE) { Log "자동 배분 실패: $out" } elseif ($out -notmatch '^자동 배분 0건$') { Log "자동 배분: $out" }
  $out = Py 'topics.py announce'
  if ($out -notmatch '새 알림 0건') { Log "알림: $out" }
  $out = Py 'topics.py tidy'
  if ($out -notmatch '수신함 정리 0건') { Log $out }
  # real-work 작업 폴더 README를 주제 기록으로 자동 갱신(README 작성자는 허브 readme-bot 하나, 10분에 한 번) — 실패해도 동기화는 계속
  $out = Py 'topics.py works-readme'
  if ($LASTEXITCODE) { Log "README 자동 갱신 실패: $out" } elseif ($out -match 'README 갱신 [1-9]|보류|못 읽음|실패') { Log "README 자동 갱신: $out" }
  Start-Runner

  # 작업물 저장소(real-work)를 받아 두어 주제 화면의 작업물 목록·상태가 최신이 되게 한다
  $wr = if ($cfg.work_repo) { $cfg.work_repo } else { 'D:\real-work' }
  # 실행기가 real-work git 작업 중이면(node-data/realwork.lock) 겹치지 않게 이번에는 건너뛴다
  $wlock = Join-Path $PSScriptRoot 'node-data/realwork.lock'
  if ((Test-Path (Join-Path $wr '.git')) -and -not (Test-Path $wlock)) {
    git -C $wr pull -q --rebase --autostash origin main 2>&1 | Out-Null
    # 받기 충돌이면 멈춘 rebase를 되돌리고 알린다(충돌 표식이 대시보드 작업물 화면에 실리지 않게)
    if ((Test-Path (Join-Path $wr '.git/rebase-merge')) -or (Test-Path (Join-Path $wr '.git/rebase-apply'))) { git -C $wr rebase --abort 2>&1 | Out-Null; Log '작업물 저장소 받기 충돌 — 받기를 되돌림(같은 파일을 다른 곳에서 고쳤는지 확인)' }
    $um = @(git -C $wr diff --name-only --diff-filter=U 2>$null)
    if ($um.Count) { Log "작업물 저장소 충돌 파일(정리 필요): $($um -join ', ')" }
  }
  if (Quiet) { return }  # 게시 시간대 밖: 만들고 올리기는 쉰다(07시가 되면 모아서 한 번에 게시)
  $out = Py 'build.py --skip-unchanged'
  if ($LASTEXITCODE -eq 10) {
    # 데이터는 그대로여도 도구 코드(실행기·엔진·화면)가 바뀌었으면 검증 뒤 게시한다 — 다른 PC(서버컴)는 원격본을 받아 쓰므로
    # 데이터 변화가 생길 때까지 코드 게시가 밀리지 않게(2026-10-03)
    $code = @(git status --porcelain -- runner.py topics.py build.py node.py testflow.py command.py command_reset.py release_queue.py sync.ps1 encrypt.mjs docs)
    if (-not $code.Count) { return }
  } elseif ($LASTEXITCODE) { Log "생성 실패: $out"; return }
  $out = Py 'tests/verify.py'
  if ($LASTEXITCODE) { Log "검증 실패 — 게시하지 않음: $out"; return }

  git add -A
  $staged = @(git diff --cached --name-only)
  $bad = $staged | Where-Object { $_ -match '^(data/(?!example\.json)|topics/|out/|\.local/|node-data/|config\.local\.json|routing\.json|GUIDE-LOCAL)' }
  if ($bad) { git reset -q; Log "평문 파일이 스테이징됨 — 중단: $($bad -join ', ')"; return }
  if ($staged.Count) { git commit -q -m ('sync ' + (Get-Date -Format 'yyyy-MM-dd HH:mm')) | Out-Null }
  if (Push-Safely $staged) { if ($staged.Count) { Log ('게시: ' + ($staged -join ', ')) } } else { Log '올리기 실패' }
  }

  Sync-Once
  if (-not $FromRunner) {
    foreach ($i in 1..8) {
      Start-Sleep -Seconds 60
      Set-Content $lock $PID  # 잠금 시각 갱신(다른 동기화가 겹치지 않게)
      Sync-Once
    }
  }
} catch {
  Log ('오류: ' + $_.Exception.Message)
} finally {
  Remove-Item Env:REAL_OPS_PASSWORD -ErrorAction SilentlyContinue
  Remove-Item $lock -ErrorAction SilentlyContinue
}
