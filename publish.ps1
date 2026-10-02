# 대시보드 갱신·게시: 주제 가져오기 → 수집·암호화 → 검증 → git push
#   .\publish.ps1               평소 갱신
#   .\publish.ps1 -NewPassword  비밀번호 변경(새 salt). 기억해 둔 기기는 다시 입력해야 함
#   .\publish.ps1 -NoPush       로컬 생성·검증만
param([switch]$NewPassword, [switch]$NoPush)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

function Read-Plain([string]$prompt) {
  $s = Read-Host -AsSecureString $prompt
  $b = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s)
  try { [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b) }
}

$hadEnv = [bool]$env:REAL_OPS_PASSWORD
if (-not $hadEnv) {
  $pw = Read-Plain '대시보드 비밀번호'
  if ($NewPassword -or -not (Test-Path 'docs/data.enc.json')) {
    if ((Read-Plain '한 번 더 입력') -ne $pw) { throw '비밀번호가 일치하지 않습니다.' }
  }
  $env:REAL_OPS_PASSWORD = $pw
}
try {
  $cfg = Get-Content 'config.local.json' -Raw -Encoding UTF8 | ConvertFrom-Json
  if ($cfg.github_repo) {
    python topics.py pull; if ($LASTEXITCODE) { Write-Warning '주제 가져오기 실패 — 계속 진행' }
    python topics.py announce
  }
  $buildArgs = @('build.py'); if ($NewPassword) { $buildArgs += '--new-salt' }
  python @buildArgs; if ($LASTEXITCODE) { throw '생성 실패' }
  python tests/verify.py; if ($LASTEXITCODE) { throw '검증 실패 — 게시하지 않습니다' }
  if ($NoPush) { Write-Host '로컬 생성·검증 완료 (push 안 함)'; return }
  if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'git이 설치되어 있지 않습니다.' }
  git add -A
  $staged = git diff --cached --name-only
  $bad = $staged | Where-Object { $_ -match '^(data/(?!example\.json)|topics/|out/|config\.local\.json)' }
  if ($bad) { throw "평문 파일이 스테이징됨: $($bad -join ', ')" }
  if ($staged) {
    git commit -m ("dashboard " + (Get-Date -Format 'yyyy-MM-dd HH:mm')) | Out-Null
    if ($LASTEXITCODE) { throw '커밋 실패' }
  } else { Write-Host '바뀐 내용 없음 — 올라가지 않은 커밋만 확인합니다' }
  # 처음이거나 이전 push가 실패했어도 원격 연결과 업로드를 함께 처리한다
  git push -u origin HEAD
  if ($LASTEXITCODE) { throw 'push 실패 — 게시되지 않았습니다. 위 git 메시지를 확인하세요.' }
  Write-Host '게시 완료 — 1~2분 뒤 GitHub Pages에 반영됩니다.'
} finally {
  if (-not $hadEnv) { Remove-Item Env:REAL_OPS_PASSWORD -ErrorAction SilentlyContinue }
}
