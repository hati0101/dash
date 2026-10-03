"""게시 전 검증: 암호문 왕복·오답·변조·평문 유출을 확인한다. 하나라도 실패하면 종료 코드 1.

  python tests/verify.py [--password-file 파일]   (없으면 REAL_OPS_PASSWORD)
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
ENC = DOCS / "data.enc.json"
PUBLIC_IP = re.compile(r"(?<![\w.])(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(?![\w.])")


def node_decrypt(path: Path, pw: str) -> tuple[int, bytes, str]:
    r = subprocess.run(["node", str(ROOT / "encrypt.mjs"), "decrypt", str(path)],
                       env=dict(os.environ, REAL_OPS_PASSWORD=pw), capture_output=True)
    return r.returncode, r.stdout, r.stderr.decode("utf-8", errors="replace")


def is_public(m) -> bool:
    a, b = int(m.group(1)), int(m.group(2))
    if any(int(x) > 255 for x in m.groups()):
        return False
    return not (a in (0, 10, 127) or (a == 192 and b == 168) or (a == 172 and 16 <= b <= 31) or (a == 169 and b == 254) or a >= 224)


def main():
    # 콘솔 문자표(cp949)에 없는 글자가 있어도 출력 때문에 멈추지 않게
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--password-file")
    ap.add_argument("--enc", help="검사할 암호문 경로(기본 docs/data.enc.json, 로컬 시험용)")
    args = ap.parse_args()
    global ENC
    if args.enc:
        ENC = Path(args.enc).resolve()
    pw = Path(args.password_file).read_text(encoding="utf-8").strip() if args.password_file else os.environ.get("REAL_OPS_PASSWORD", "")
    if not pw:
        sys.exit("비밀번호가 필요합니다 (--password-file 또는 REAL_OPS_PASSWORD).")
    results = []

    def check(name, ok, detail=""):
        results.append((name, ok, detail))

    # 코드 검사(교차 검수 P1, 2026-10-03): 코드도 게시되면 다른 PC(서버컴)가 받아 실행하므로 문법 오류·반쯤 고친 코드는 올리지 않는다
    try:
        unit = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py'],
                              cwd=ROOT, capture_output=True, timeout=120, env=dict(os.environ, PYTHONUTF8='1'))
        check('엔진 단위·통합 회귀', unit.returncode == 0, unit.stderr.decode('utf8', errors='replace')[-500:])
    except subprocess.TimeoutExpired:
        check('엔진 단위·통합 회귀', False, '120초 시간 제한 초과')
    for f in ("runner.py", "topics.py", "build.py", "node.py", "command.py", "command_reset.py", "release_queue.py", "testflow.py"):
        r = subprocess.run([sys.executable, "-m", "py_compile", str(ROOT / f)], capture_output=True)
        check(f"코드 문법 {f}", r.returncode == 0, r.stderr.decode("utf-8", errors="replace").strip()[-200:])
    r = subprocess.run(["node", "--check", str(DOCS / "app.js")], capture_output=True)
    check("코드 문법 docs/app.js", r.returncode == 0, r.stderr.decode("utf-8", errors="replace").strip()[-200:])
    r = subprocess.run([sys.executable, "-c", "import topics, node; assert topics.gate_options(4, {}) and topics.gate_action(4, {'choice': '통과'}) == 'open5'"],
                       cwd=ROOT, capture_output=True, env=dict(os.environ, PYTHONUTF8="1"))
    check("엔진 불러오기·관문 판정", r.returncode == 0, r.stderr.decode("utf-8", errors="replace").strip()[-200:])

    env = json.loads(ENC.read_text(encoding="utf-8"))
    salt, iv = base64.b64decode(env["salt"]), base64.b64decode(env["iv"])
    check("봉투 형식", env.get("v") == 1 and env.get("iter", 0) >= 600000 and len(salt) == 16 and len(iv) == 12,
          f"iter={env.get('iter')} salt={len(salt)}B iv={len(iv)}B")

    code, out, err = node_decrypt(ENC, pw)
    payload = None
    if code == 0:
        payload = json.loads(out.decode("utf-8"))
    check("올바른 비밀번호로 복호화", payload is not None, err.strip()[:200])

    code2, _, _ = node_decrypt(ENC, pw + "x")
    check("틀린 비밀번호 거부", code2 != 0)

    tampered = dict(env)
    raw = bytearray(base64.b64decode(env["data"]))
    raw[len(raw) // 2] ^= 0x01
    tampered["data"] = base64.b64encode(bytes(raw)).decode()
    with tempfile.TemporaryDirectory() as td:
        tp = Path(td) / "t.json"
        tp.write_text(json.dumps(tampered), encoding="utf-8")
        code3, _, _ = node_decrypt(tp, pw)
    check("변조 감지(GCM 태그)", code3 != 0)

    if payload:
        need = ("meta", "sources", "tasks", "messages", "validations", "ledger", "memory", "decisions", "topics")
        check("데이터 구조", all(k in payload for k in need), ", ".join(k for k in need if k not in payload))
        # 평문 유출 검사: 데이터에만 있어야 할 고유 문자열이 공개 파일에 보이면 실패
        probes = set()
        for t in payload["tasks"]:
            probes.update(x for x in (t.get("id"), t.get("title")) if x and len(x) >= 8)
        for m in payload["messages"][:200]:
            probes.update(x for x in (m.get("id"), m.get("title")) if x and len(x) >= 10)
        for s in payload["sources"]:
            if len(s["path"]) >= 8 and ("/" in s["path"] or "\\" in s["path"]):
                probes.add(s["path"])  # 실제 경로만 검사(짧은 설명 문구는 화면 글과 겹쳐 오탐이 남)
        for m in payload["memory"]:
            if len(m["id"]) >= 8:
                probes.add(m["id"])
        for t in payload.get("topics", []):
            probes.update(x for x in (t.get("id"), t.get("title")) if x and len(x) >= 6)
        leaks = []
        files = [p for p in DOCS.rglob("*") if p.is_file()] + [ROOT / n for n in ("README.md", "config.example.json") if (ROOT / n).exists()]
        for p in files:
            if p.suffix in (".png", ".ico"):
                continue
            text = p.read_text(encoding="utf-8", errors="ignore")
            for probe in probes:
                if probe in text:
                    leaks.append(f"{p.name}: {probe[:60]}")
            if p.suffix in (".html", ".js", ".css", ".md", ".txt"):
                for m in PUBLIC_IP.finditer(text):
                    if is_public(m):
                        leaks.append(f"{p.name}: 공인 IP {m.group(0)}")
        check(f"평문 유출 없음 (검사 문자열 {len(probes)}개 × 파일 {len(files)}개)", not leaks, "; ".join(leaks[:5]))
        plain = json.dumps(payload, ensure_ascii=False)
        pub = [m.group(0) for m in PUBLIC_IP.finditer(plain) if is_public(m)]
        check("데이터 안 공인 IP 마스킹", not pub, ", ".join(pub[:5]))

    width = max(len(n) for n, _, _ in results)
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name.ljust(width)}  {detail if not ok or detail.startswith('iter') else ''}")
    failed = [n for n, ok, _ in results if not ok]
    print(f"RESULT {'PASS' if not failed else 'FAIL'} {len(results) - len(failed)}/{len(results)}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
