"""개발컴 Claude·GPT(Codex) 사용량을 읽어 작업실(docs/usage.enc.json)에 올린다.
- Claude: `claude -p`(haiku, 1턴) 응답의 rate_limit_event에서 계정 5시간·주간 사용률
- Codex: ~/.codex/sessions 최근 기록의 rate_limits(추가 실행 없음)
비밀번호는 환경변수 REAL_OPS_PASSWORD(usage-sync.ps1이 DPAPI 파일에서 넣는다). 출력·커밋에 비밀값을 남기지 않는다."""
import json, os, subprocess, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
KST = timezone(timedelta(hours=9))
now = lambda: datetime.now(KST)


def iso(v):
    try:
        return datetime.fromtimestamp(float(v), KST).isoformat(timespec="seconds")
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def claude():
    cmd = ["claude", "-p", "ok", "--model", "haiku", "--output-format", "stream-json", "--verbose", "--max-turns", "1", "--strict-mcp-config"]
    try:
        p = subprocess.run(cmd, cwd=os.environ.get("TEMP") or str(HERE), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180, shell=(os.name == "nt"))
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"error": f"claude 실행 실패: {type(e).__name__}"}
    for ln in p.stdout.splitlines():
        if '"rate_limit_event"' not in ln:
            continue
        try:
            info = json.loads(ln).get("rate_limit_info") or {}
        except ValueError:
            continue
        win = info.get("unifiedWindows") or {}
        out = {"status": info.get("status"), "seen_at": now().isoformat(timespec="seconds")}
        for k in ("five_hour", "seven_day"):
            w = win.get(k) or {}
            if w.get("utilization") is not None:
                out[k] = {"pct": round(float(w["utilization"]) * 100), "resets_at": iso(w.get("resetsAt"))}
        return out
    return {"error": "사용량 정보를 받지 못함"}


def codex():
    base = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "sessions"
    files = sorted(base.rglob("*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True) if base.is_dir() else []
    for f in files[:8]:
        try:
            with open(f, "rb") as fh:
                fh.seek(max(0, f.stat().st_size - 400_000))
                lines = fh.read().decode("utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for ln in reversed(lines):
            if '"rate_limits"' not in ln:
                continue
            try:
                o = json.loads(ln)
            except ValueError:
                continue
            rl = (o.get("payload") or {}).get("rate_limits") if isinstance(o, dict) else None
            if not isinstance(rl, dict):
                continue
            out = {"plan": rl.get("plan_type"), "seen_at": o.get("timestamp"), "status": "limited" if rl.get("rate_limit_reached_type") else "allowed"}
            for key in ("primary", "secondary"):
                x = rl.get(key)
                if isinstance(x, dict) and x.get("used_percent") is not None:
                    slot = "five_hour" if (x.get("window_minutes") or 0) <= 600 else "seven_day"
                    out[slot] = {"pct": round(float(x["used_percent"])), "resets_at": iso(x.get("resets_at"))}
            cr = rl.get("credits")
            if isinstance(cr, dict) and cr.get("has_credits"):
                out["credits"] = {"balance": cr.get("balance"), "unlimited": bool(cr.get("unlimited"))}
            if "five_hour" in out or "seven_day" in out:
                return out
    return {"error": "최근 Codex 기록에 사용량이 없음"}


def main():
    if not os.environ.get("REAL_OPS_PASSWORD"):
        sys.exit("REAL_OPS_PASSWORD 없음")
    data = {"v": 1, "updated_at": now().isoformat(timespec="seconds"), "pc": "개발컴",
            "accounts": [{"id": "claude", "name": "Claude", "plan": "Max", **claude()},
                         {"id": "codex", "name": "GPT · Codex", **codex()}]}
    out = HERE / "docs" / "usage.enc.json"
    enc = subprocess.run(["node", "encrypt.mjs", "encrypt", str(out), "--salt-from", str(HERE / "docs" / "data.enc.json")],
                         cwd=HERE, input=json.dumps(data, ensure_ascii=False).encode("utf-8"), capture_output=True)
    if enc.returncode:
        sys.exit("암호화 실패")
    git = lambda *a: subprocess.run(["git", *a], cwd=HERE, capture_output=True, text=True, encoding="utf-8", errors="replace")
    git("add", "-f", "docs/usage.enc.json")
    if git("diff", "--cached", "--quiet").returncode == 0:
        print("변경 없음"); return
    git("commit", "-q", "-m", "작업실: 사용량 갱신")
    for _ in range(3):
        if git("push", "-q", "origin", "HEAD:main").returncode == 0:
            print("사용량 올림", data["updated_at"]); return
        git("pull", "-q", "--rebase", "--autostash", "origin", "main")
    print("푸시 실패")


if __name__ == "__main__":
    main()
