"""REAL 운영 대시보드 생성기.

로컬 작업 기록(조정 작업표, Claude<->Astra 메시지, QA 검증, 감사 원장, Claude 메모리,
수동 큐레이션 파일)을 읽어 하나의 JSON으로 합치고, 민감 정보를 가린 뒤
encrypt.mjs로 비밀번호 암호화해 docs/data.enc.json에 씁니다.

평문은 디스크에 남기지 않습니다(--dump를 준 경우만 out/ 아래에 씁니다).
표준 라이브러리만 사용합니다.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
KST = timezone(timedelta(hours=9))
GENERATOR_VERSION = 1

STAGES = ["request", "progress", "validating", "user_test", "blocked", "done"]
PEOPLE = {"user", "claude", "astra", "cli"}


# ---------------------------------------------------------------- 공통 유틸

def now() -> datetime:
    return datetime.now(KST)


def iso(dt: datetime | None) -> str | None:
    return dt.astimezone(KST).isoformat(timespec="seconds") if dt else None


def mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, KST)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def parse_iso(value) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    v = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(v)
    except ValueError:
        m = re.match(r"(\d{4}-\d{2}-\d{2})", v)
        if not m:
            return None
        dt = datetime.fromisoformat(m.group(1))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    return dt


def stamp_from_name(name: str) -> datetime | None:
    """파일명 앞의 YYYYMMDD-HHMM(SS) 시각을 읽는다. 날짜만 있으면 None."""
    m = re.match(r"(\d{8})-(\d{6}|\d{4})(?!\d)", name)
    if not m:
        return None
    d, t = m.groups()
    t = t.ljust(6, "0")
    try:
        return datetime.strptime(d + t, "%Y%m%d%H%M%S").replace(tzinfo=KST)
    except ValueError:
        return None


def who(text: str | None) -> str | None:
    if not text:
        return None
    t = text.lower()
    if "astra" in t or "아스트라" in t or "codex" in t:
        return "astra"
    if "cli" in t and "claude" in t:
        return "cli"
    if "claude" in t or "클로드" in t:
        return "claude"
    if "user" in t or "사용자" in t:
        return "user"
    return None


def clip(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit].rstrip() + "\n…(생략)"


class SourceLog:
    """출처별 수집 결과(연결 화면용)."""

    def __init__(self):
        self.rows = []

    def add(self, sid, name, kind, path, count, last=None, error=None, note=None):
        self.rows.append({
            "id": sid, "name": name, "kind": kind, "path": str(path),
            "count": count, "last_modified": iso(last), "ok": error is None,
            "error": error, "note": note,
        })


# ---------------------------------------------------------------- 작업표

def stage_of(state: str, live_test: str = "") -> str:
    s = (state or "").lower()
    if any(k in s for k in ("completed", "done", "closed", "installed_verified")):
        return "done"
    if any(k in s for k in ("blocked", "failed", "fail_", "refused", "stalled")):
        return "blocked"
    if "user_test" in s or "ready_for_user" in s:
        return "user_test"
    if any(k in s for k in ("validat", "review", "reported", "verified")):
        return "validating"
    if any(k in s for k in ("prepared", "queued", "request", "assigned", "unassigned")):
        return "request"
    return "progress"


def load_tasks(bridge: Path, log: SourceLog):
    path = bridge / "coordination-v2" / "tasks.json"
    try:
        data = json.loads(read_text(path))
    except Exception as exc:  # noqa: BLE001 - 출처 오류는 화면에 표시
        log.add("tasks", "조정 작업표", "tasks.json", path, 0, error=str(exc))
        return [], [], {}
    file_time = mtime(path)
    updated = parse_iso(data.get("updated_at")) or file_time
    tasks = []
    for t in data.get("tasks", []):
        fields = {k: v for k, v in t.items() if k not in ("id",)}
        tasks.append({
            "id": t.get("id"),
            "title": t.get("title") or t.get("scope") or t.get("id"),
            "area": None,
            "owner": who(t.get("owner")) or "claude",
            "implementer": t.get("implementer"),
            "state": t.get("state", ""),
            "stage": stage_of(t.get("state", ""), str(t.get("live_test", ""))),
            "priority": (re.match(r"(P\d)", str(t.get("priority", ""))) or [None, None])[1],
            "next_action": t.get("next_action"),
            "live_test": t.get("live_test"),
            "updated_at": iso(updated),
            "source": "tasks.json",
            "authors": ["tasks.json"],
            "fields": fields,
        })
    meta = {k: data.get(k) for k in ("lead", "astra_role", "writer", "updated_at")}
    meta["handoff"] = data.get("handoff")
    log.add("tasks", "조정 작업표", "tasks.json", path, len(tasks), file_time,
            note=f"기록자: {data.get('writer', '?')}")
    return tasks, data.get("messages", []), meta


# ---------------------------------------------------------------- 메시지

HEADER_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_ -]{0,30}):\s*(.*)$")
TITLE_RE = re.compile(r"^\[([^\]]+)\]\s*(.+)$")


def parse_message(path: Path, box: str, cfg_limits: dict, cutoff_full: datetime):
    raw = read_text(path)
    lines = raw.splitlines()
    headers, title, i = {}, None, 0
    # 첫 줄이 "[보낸이 → 받는이] 제목" 형식이면 제목으로
    if lines and TITLE_RE.match(lines[0].strip()):
        m = TITLE_RE.match(lines[0].strip())
        title, headers["route"] = m.group(2).strip(), m.group(1).strip()
        i = 1
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            if headers:
                i += 1
                break
            i += 1
            continue
        m = HEADER_RE.match(line)
        if not m or m.group(1).strip().lower() in ("http", "https"):
            break
        headers[m.group(1).strip().lower().replace(" ", "_")] = m.group(2).strip()
        i += 1
    body = "\n".join(lines[i:]).strip()
    if not title:
        for line in lines[i:]:
            s = line.strip().lstrip("#").strip()
            if s:
                title = s
                break
    stem = path.stem
    ts = stamp_from_name(path.name) or mtime(path)
    mid = headers.get("message_id") or headers.get("message-id") or stem
    sender = who(headers.get("sender")) or who(headers.get("route", "").split("→")[0])
    recipient = who(headers.get("recipient")) or who(headers.get("route", "").split("→")[-1])
    if box.startswith("inbox-claude"):
        sender = sender or ("user" if "user" in stem.lower() else "astra")
        recipient = recipient or "claude"
    else:
        sender = sender or ("user" if "user" in stem.lower() else "claude")
        recipient = recipient or "astra"
    limit = cfg_limits["message_body_chars"] if ts >= cutoff_full else cfg_limits["message_old_body_chars"]
    return {
        "id": mid,
        "file": path.name,
        "box": box,
        "ts": iso(ts),
        "sender": sender,
        "recipient": recipient,
        "kind": headers.get("kind"),
        "task_id": headers.get("task_id"),
        "in_reply_to": headers.get("in_reply_to"),
        "priority": (re.search(r"\b(P[0-3])\b", headers.get("priority", "") + " " + (title or "")) or [None, None])[1],
        "title": clip(title or stem, 200),
        "body": clip(body, limit),
        "headers": {k: v for k, v in headers.items() if k not in ("message_id", "message-id")},
    }


def load_messages(bridge: Path, limits: dict, log: SourceLog):
    cutoff_full = now() - timedelta(days=limits["message_full_body_days"])
    out = []
    for box, rel, label in (
        ("inbox-claude", "inbox-claude", "Astra → Claude 수신함 (미처리)"),
        ("inbox-claude/done", "inbox-claude/done", "Astra → Claude 처리 완료"),
        ("inbox-astra", "inbox-astra", "Claude → Astra 발신함"),
    ):
        folder = bridge / rel
        files = sorted(p for p in folder.glob("*.md") if p.is_file()) if folder.is_dir() else []
        last = max((mtime(p) for p in files), default=None)
        errors = []
        for p in files:
            try:
                out.append(parse_message(p, box, limits, cutoff_full))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{p.name}: {exc}")
        log.add(box.replace("/", "-"), label, "messages", folder, len(files), last,
                error="; ".join(errors[:3]) if errors else (None if folder.is_dir() else "폴더 없음"))
    # 답장 그래프
    replies: dict[str, list[str]] = {}
    for m in out:
        if m["in_reply_to"]:
            for ref in re.split(r"[,\s]+", m["in_reply_to"]):
                if ref:
                    replies.setdefault(ref, []).append(m["id"])
    # in_reply_to가 없어도 본문·헤더에서 다른 메시지 ID를 인용하면 답장으로 본다(보낸이가 다를 때)
    by_id = {m["id"]: m for m in out if len(m["id"]) >= 12}
    token_re = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{11,}")
    for m in out:
        text = m["body"] + " " + " ".join(m["headers"].values())
        for tok in set(token_re.findall(text)):
            ref = by_id.get(tok)
            if ref and ref is not m and ref["sender"] != m["sender"] and m["id"] not in replies.get(tok, []):
                replies.setdefault(tok, []).append(m["id"])
    # 같은 작업에 대해 상대가 나중에 보낸 메시지는 후속 응답으로 본다
    for m in out:
        m["replies"] = replies.get(m["id"], [])
        m["followups"] = [x["id"] for x in out if m["task_id"] and x["task_id"] == m["task_id"]
                          and x["sender"] == m["recipient"] and (x["ts"] or "") > (m["ts"] or "")][:5]
        # 대시보드 자동 알림(DASH-*)·아키텍트 행동 사본(USR-*)은 처리할 '미처리'가 아니라 기록이다
        m["auto"] = bool(re.match(r"^(DASH|USR)-", str(m.get("id") or "")))
        m["unprocessed"] = m["box"] == "inbox-claude" and not m["auto"]
    out.sort(key=lambda m: m["ts"] or "", reverse=True)
    return out


# ---------------------------------------------------------------- 검증

def summarize_validation(data: dict) -> dict:
    keep = {}
    for k, v in data.items():
        if k == "files":
            continue
        if isinstance(v, (str, int, float, bool)) or v is None:
            keep[k] = v
        elif isinstance(v, dict) and all(isinstance(x, (str, int, float, bool)) for x in v.values()):
            keep[k] = ", ".join(f"{a}={b}" for a, b in v.items())
        elif isinstance(v, list) and all(isinstance(x, str) for x in v):
            keep[k] = "; ".join(v)
    return keep


def load_validations(bridge: Path, log: SourceLog):
    folder = bridge / "qa"
    rows, errors = [], []
    files = sorted(folder.rglob("HEAD-VALIDATION.json")) if folder.is_dir() else []
    for p in files:
        try:
            data = json.loads(read_text(p))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{p.parent.name}: {exc}")
            continue
        summary = summarize_validation(data)
        exit_code = data.get("exit_code")
        text = json.dumps(summary, ensure_ascii=False).upper()
        if isinstance(exit_code, int) and exit_code != 0 or "FAIL" in text and "PASS" not in text:
            result = "fail"
        elif exit_code == 0 or "PASS" in text:
            result = "pass"
        else:
            result = "unknown"
        rows.append({
            "id": p.parent.name,
            "ts": iso(parse_iso(data.get("verified_at")) or mtime(p)),
            "job": data.get("job"),
            "reviewer": data.get("reviewer"),
            "by": who(data.get("reviewer")) or "astra",
            "result": result,
            "live": "pending" if "NOT_RUN" in text or "PENDING" in text else None,
            "root_cause": data.get("root_cause"),
            "summary": summary,
            "path": str(p),
            "file_count": len(data.get("files", {}) or {}),
        })
    rows.sort(key=lambda r: r["ts"] or "", reverse=True)
    log.add("qa", "QA 검증 결과", "HEAD-VALIDATION.json", folder, len(rows),
            max((mtime(p) for p in files), default=None),
            error="; ".join(errors[:3]) if errors else None)
    return rows


def load_handoffs(bridge: Path, log: SourceLog):
    folder = bridge / "handoffs"
    rows = []
    if folder.is_dir():
        for p in folder.iterdir():
            rows.append({"id": p.stem, "ts": iso(mtime(p)), "path": str(p), "kind": "dir" if p.is_dir() else "file"})
    rows.sort(key=lambda r: r["ts"], reverse=True)
    log.add("handoffs", "인계 묶음", "handoffs", folder, len(rows),
            parse_iso(rows[0]["ts"]) if rows else None, error=None if folder.is_dir() else "폴더 없음")
    return rows


# ---------------------------------------------------------------- 감사 원장

LEDGER_START = re.compile(r"^(?:#{2,3}\s+)?(?:`n)?(\d{4}-\d{2}-\d{2})\b")
LEDGER_TIME = re.compile(r"\b(\d{1,2}):(\d{2})\s*KST\b")
STATUS_WORDS = ["REVERTED", "FAILED", "FAIL", "NONPASS", "PENDING", "NOT_RUN", "DEPLOYED", "VERIFIED", "PASS", "DONE", "COMPLETE"]


def ledger_status(text: str) -> str:
    """대문자 상태어(원장 관례)만 본다. 본문 소문자 'failed' 같은 서술은 상태로 보지 않는다."""
    head = text[:700]
    title = text.split("\n", 1)[0]
    if re.search(r"\bREVERTED\b", head) or "되돌" in title:
        return "reverted"
    if re.search(r"\b(FAILED|FAIL)\b", head):
        return "fail"
    if re.search(r"\b(PENDING|NOT_RUN|BACKGROUND_RUNNING)\b", head) or "대기" in title:
        return "pending"
    if re.search(r"\b(PASS|VERIFIED|DEPLOYED|DEPLOYED_VERIFIED|PUBLISHED_VERIFIED|COMPLETE|DONE)\b", head) or "완료" in title:
        return "pass"
    return "note"


def load_ledger(path: Path, limits: dict, log: SourceLog):
    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            fh.seek(max(0, size - 600_000))
            tail = fh.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        log.add("ledger", "감사 원장", "AUDIT_LEDGER.md", path, 0, error=str(exc))
        return []
    lines = tail.splitlines()[1:]  # 첫 줄은 잘렸을 수 있음
    entries, cur = [], None
    prev_blank = True
    for line in lines:
        m = LEDGER_START.match(line.strip())
        # 제목(#), 빈 줄 뒤, 또는 들여쓰기 없이 날짜로 시작하는 줄은 새 항목이다
        starts = bool(m) and (line.startswith("#") or prev_blank or line[:1].isdigit() or line.startswith("`n"))
        if starts:
            if cur:
                entries.append(cur)
            cur = {"date": m.group(1), "lines": [line.strip().lstrip("#").strip().removeprefix("`n")]}
        elif cur is not None:
            cur["lines"].append(line.rstrip())
        prev_blank = not line.strip()
    if cur:
        entries.append(cur)
    out = []
    for e in entries[-limits["ledger_entries"]:]:
        text = "\n".join(e["lines"]).strip()
        first = e["lines"][0]
        title = re.sub(r"^\d{4}-\d{2}-\d{2}\s*(—|-)?\s*", "", first)
        title = re.split(r"(?<=[^0-9]):\s|\.\s", title, maxsplit=1)[0]
        tm = LEDGER_TIME.search(first)
        ts = datetime.fromisoformat(e["date"]).replace(tzinfo=KST)
        if tm:
            ts = ts.replace(hour=int(tm.group(1)), minute=int(tm.group(2)))
        out.append({
            "date": e["date"],
            "ts": iso(ts),
            "has_time": bool(tm),
            "title": clip(title, 160),
            "status": ledger_status(text),
            "body": clip(text, limits["ledger_body_chars"]),
        })
    out.reverse()
    log.add("ledger", "감사 원장", "AUDIT_LEDGER.md", path, len(out), mtime(path),
            note=f"최근 {len(out)}건만 수집")
    return out


# ---------------------------------------------------------------- Claude 메모리

def load_memory(folder: Path, log: SourceLog):
    rows = []
    if not folder.is_dir():
        log.add("memory", "Claude 메모리", "memory", folder, 0, error="폴더 없음")
        return rows
    files = sorted(p for p in folder.glob("*.md") if p.name != "MEMORY.md")
    for p in files:
        raw = read_text(p)
        meta, body = {}, raw
        if raw.startswith("---"):
            parts = raw.split("---", 2)
            if len(parts) == 3:
                body = parts[2].strip()
                for line in parts[1].splitlines():
                    m = re.match(r"^\s*([A-Za-z_]+):\s*(.*)$", line)
                    if m:
                        meta[m.group(1)] = m.group(2).strip().strip('"')
        rows.append({
            "id": meta.get("name") or p.stem,
            "description": meta.get("description", "").replace('\\"', '"'),
            "type": meta.get("type", "note"),
            "ts": iso(parse_iso(meta.get("modified")) or mtime(p)),
            "body": clip(body, 5000),
            "links": re.findall(r"\[\[([^\]]+)\]\]", body),
        })
    rows.sort(key=lambda r: r["ts"] or "", reverse=True)
    log.add("memory", "Claude 메모리", "memory", folder, len(rows),
            max((mtime(p) for p in files), default=None))
    return rows


def load_ai_runs(folder: Path, log: SourceLog):
    if not folder.is_dir():
        log.add("ai-runs", "AI 작업 기록(real.py)", "runs", folder, 0, error="폴더 없음")
        return
    dirs = [p for p in folder.iterdir() if p.is_dir()]
    log.add("ai-runs", "AI 작업 기록(real.py)", "runs", folder, len(dirs),
            max((mtime(p) for p in dirs), default=None))


# ---------------------------------------------------------------- 큐레이션(Claude·Astra 직접 기록)

CURATED_KEYS = ("tasks", "decisions_needed", "decisions", "user_actions", "notes",
                "comments", "acks", "decisions_answered", "notices")


def load_curated(files: list[str], log: SourceLog):
    merged = {k: [] for k in CURATED_KEYS}
    merged["processed_actions"] = []
    for rel in files:
        path = (ROOT / rel).resolve()
        author = path.stem
        if not path.exists():
            log.add(f"curated-{author}", f"직접 기록 · {author}", "curated", path, 0, error="파일 없음(선택)")
            continue
        try:
            data = json.loads(read_text(path))
            author = data.get("author", author)
            count = 0
            for key in CURATED_KEYS:
                for row in data.get(key, []) or []:
                    if not isinstance(row, dict):
                        continue
                    row = dict(row)
                    row["_author"] = author
                    row["_file_updated"] = data.get("updated_at")
                    merged[key].append(row)
                    count += 1
            merged["processed_actions"].extend(x for x in data.get("processed_actions", []) if isinstance(x, str))
            log.add(f"curated-{author}", f"직접 기록 · {author}", "curated", path, count, mtime(path),
                    note=f"갱신 {data.get('updated_at', '?')}")
        except Exception as exc:  # noqa: BLE001
            log.add(f"curated-{author}", f"직접 기록 · {author}", "curated", path, 0, error=str(exc))
    return merged


def merge_tasks(base: list[dict], curated: list[dict]):
    """큐레이션 작업이 같은 id의 tasks.json 작업을 덮어쓴다. 서로 다른 작성자가 같은 id를 쓰면 충돌로 표시."""
    by_id = {t["id"]: t for t in base}
    conflicts = []
    seen_author: dict[str, str] = {}
    for row in curated:
        tid = row.get("id")
        if not tid:
            continue
        author = row["_author"]
        # 사용자가 대시보드에서 바꾼 단계는 충돌이 아니라 우선 적용 대상이다
        if author != "user":
            if tid in seen_author and seen_author[tid] != author:
                conflicts.append({"id": tid, "authors": [seen_author[tid], author]})
            seen_author[tid] = author
        t = by_id.get(tid)
        if t is None:
            t = {"id": tid, "title": tid, "owner": author, "state": "", "stage": "progress",
                 "priority": None, "next_action": None, "updated_at": None,
                 "source": "curated", "authors": [], "fields": {}}
            by_id[tid] = t
            base.append(t)
        prev_time = parse_iso(t.get("updated_at"))
        row_time = parse_iso(row.get("updated_at")) or parse_iso(row.get("_file_updated"))
        if prev_time and row_time and row_time < prev_time and t["source"] == "curated" and author != "user":
            continue  # 더 오래된 큐레이션은 무시
        if author == "user":
            t["user_set"] = {"stage": row.get("stage"), "note": row.get("user_note"), "at": row.get("updated_at")}
        for key in ("title", "area", "owner", "state", "priority", "next_action", "due",
                    "waiting_on", "live_test", "summary", "evidence", "progress", "hidden", "hidden_reason"):
            if row.get(key) not in (None, ""):
                t[key] = row[key]
        if row.get("stage") in STAGES:
            t["stage"] = row["stage"]
        elif row.get("state"):
            t["stage"] = stage_of(row["state"])
        if row_time:
            t["updated_at"] = iso(row_time)
        t["source"] = "curated" if t["source"] == "curated" else "tasks.json+curated"
        t["authors"] = sorted(set(t.get("authors", []) + [author]))
    return base, conflicts


def load_nodes(cfg: dict, pw: str | None, log: SourceLog):
    """각 PC(작업 노드)의 작업자 현황·주제 기록을 모은다."""
    from node import collect_nodes, all_agents
    if not cfg.get("pc"):
        return [], [], [], [], [], [], {}
    nodes = collect_nodes(cfg, pw)
    for n in nodes:
        last = parse_iso(n.get("synced_at") or n.get("updated_at"))
        log.add(f"node-{n['pc']}", f"PC · {n.get('label', n['pc'])}", "node", n.get("source", ""),
                len(n.get("agents") or {}), last, error=n.get("error"),
                note=f"주제 기록 {len(n.get('topic_records') or [])}건")
    agents = all_agents(nodes)
    summary = [{"pc": n["pc"], "label": n.get("label", n["pc"]), "role": n.get("role"), "synced_at": n.get("synced_at") or n.get("updated_at"),
                "error": n.get("error"), "agents": sorted((n.get("agents") or {}).keys())} for n in nodes]
    records = [r for n in nodes for r in n.get("topic_records") or []]
    # 작업자가 남긴 승인·결정 질문 → 대시보드 '결정이 필요한 문제'
    asks = [{"id": q["id"], "question": q.get("question", ""), "options": q.get("options") or [], "owner": "user",
             "task_id": q.get("topic"), "since": q.get("ts"), "_author": q.get("agent"), "from_pc": n["pc"]}
            for n in nodes for q in n.get("asks") or [] if q.get("id")]
    # 자동 실행기 실행 이력(시각·결과·실패 사유)과 대화 세션이 잡은 주제
    runs = sorted(({**r, "pc": n["pc"]} for n in nodes for r in n.get("runs") or [] if r.get("id")),
                  key=lambda r: r.get("started") or "", reverse=True)[:400]
    stamp = iso(now())
    holds = [{"topic": k, **v, "pc": n["pc"]} for n in nodes for k, v in (n.get("holds") or {}).items()
             if (v or {}).get("until") and v["until"] > stamp]
    # 허브 공지를 각 작업자가 확인한 기록(대화 세션 확인 / 실행기 반영)
    notice_acks: dict[str, dict] = {}
    for n in nodes:
        for nid, by in (n.get("notice_acks") or {}).items():
            notice_acks.setdefault(nid, {}).update(by or {})
    return summary, agents, records, asks, runs, holds, notice_acks


HEALTH_LABEL = {"auth": "로그인 만료", "tool": "실행 도구 없음", "timeout": "시간 초과", "encoding": "인코딩 오류",
                "parse": "답 형식 오류", "error": "실행 오류"}


def health_actions(agents: list[dict]) -> list[dict]:
    """사람이 해야 고쳐지는 작업자 문제(로그인 만료 등) → 대시보드 '할 일'."""
    out = []
    for a in agents:
        h = a.get("health") or {}
        if h.get("needs_user") and h.get("state") not in (None, "ok"):
            out.append({"id": f"health-{a['id']}-{h.get('since') or h.get('at')}", "title": f"{a.get('pc_label')} {a.get('label') or a['id']}: {HEALTH_LABEL.get(h['state'], h['state'])}",
                        "detail": f"{h.get('fix') or ''} (원인: {h.get('message') or '-'})", "since": h.get("since") or h.get("at"), "kind": "health", "agent": a["id"]})
    return out


def load_works(cfg: dict, topics: list[dict], log: SourceLog) -> dict:
    """작업물 저장소(real-work)의 작업 목록. 파일 내용은 넣지 않고 목록·상태·작업자 메모 끝부분만 넣는다(게임 소스 비공개 원칙)."""
    repo = Path(cfg.get("work_repo") or r"D:\real-work")
    base = repo / "work"
    if not base.is_dir():
        log.add("works", "작업물(real-work)", "works", base, 0, error="선택: 작업물 저장소 없음")
        return {}
    url = (cfg.get("work_repo_url") or "https://github.com/hati0101/real-work").rstrip("/")
    works, last = {}, None
    for readme in sorted(base.glob("*/README.md")):
        d = readme.parent
        text = read_text(readme)
        g = lambda k: ((re.search(rf"^\| {k} \| (.*?) \|$", text, re.M) or [None, ""])[1] or "").strip("` ")  # noqa: E731
        agents = {}
        files = []
        for sub in sorted(x for x in d.iterdir() if x.is_dir()):
            notes = sub / "NOTES.md"
            ntext = read_text(notes) if notes.exists() else ""
            heads = re.findall(r"^## (\S+) · (.+)$", ntext, re.M)
            fl = [p for p in sub.rglob("*") if p.is_file()]
            agents[sub.name] = {"files": len(fl), "notes_tail": ntext[-1500:].strip(), "notes_count": len(heads),
                                "last_note_at": heads[-1][0] if heads else None}
            files += [{"path": p.relative_to(d).as_posix(), "size": p.stat().st_size} for p in fl]
            for p in fl + ([notes] if notes.exists() else []):
                m = datetime.fromtimestamp(p.stat().st_mtime, KST)
                last = max(last, m) if last else m
        hist = re.findall(r"^- (\S+) `([^`]+)` (.+)$", text, re.M)
        works[d.name] = {"id": d.name, "title": text.splitlines()[0].lstrip("# ").split(" — ", 1)[-1] if text else d.name,
                         "owner": g("담당"), "kind": g("종류"), "state": g("상태"), "topic": g("대시보드 주제"),
                         "approval": g("아키텍트 승인"), "created": g("만든 시각"), "agents": agents,
                         "files": sorted(files, key=lambda f: f["path"])[:80], "file_count": len(files),
                         "history": [{"ts": a, "by": b, "what": c[:200]} for a, b, c in hist[-12:]],
                         "url": f"{url}/tree/main/work/{d.name}"}
    by_topic: dict[str, str] = {}
    for w in sorted(works.values(), key=lambda w: w.get("created") or ""):
        if re.match(r"^T-\d{8}-", w.get("topic") or ""):
            by_topic[w["topic"]] = w["id"]
    for t in topics:  # 연결 기록이 없으면 README의 주제 칸으로 잇는다
        if not t.get("work_id") and by_topic.get(t["id"]):
            t["work_id"] = by_topic[t["id"]]
    log.add("works", "작업물(real-work)", "works", base, len(works), last, note=f"주제 연결 {sum(1 for t in topics if t.get('work_id'))}건")
    return works


def load_topics(cfg: dict, log: SourceLog, node_records: list | None = None, known: set | None = None):
    from topics import merged_topics  # 같은 병합 규칙을 쓴다
    folder = (ROOT / cfg.get("topics_dir", "topics")).resolve()
    try:
        rows = merged_topics(folder, cfg, node_records or [], known)
    except Exception as exc:  # noqa: BLE001
        log.add("topics", "주제 보드", "topics", folder, 0, error=str(exc))
        return []
    last = max((parse_iso(t.get("updated_at")) for t in rows if parse_iso(t.get("updated_at"))), default=None)
    turns: dict[str, int] = {}
    for t in rows:
        if t.get("turn"):
            turns[t["turn"]] = turns.get(t["turn"], 0) + 1
    log.add("topics", "주제 보드", "topics", folder, len(rows), last,
            note="차례: " + (", ".join(f"{k} {v}" for k, v in sorted(turns.items())) or "없음"))
    return rows


# ---------------------------------------------------------------- 민감 정보 마스킹

IP_RE = re.compile(r"(?<![\w.])(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(?![\w.])")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
SECRET_RE = re.compile(r"(?i)\b(password|passwd|pwd|비밀번호|암호|secret|api[_-]?key|access[_-]?token|token)(\s*[:=]\s*)([^\s,;\"']{4,})")
TOKEN_RE = re.compile(r"\b(sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|xox[abp]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16})\b")


def private_ip(parts: tuple[int, ...]) -> bool:
    a, b = parts[0], parts[1]
    return (a in (0, 10, 127) or (a == 192 and b == 168) or (a == 172 and 16 <= b <= 31)
            or (a == 169 and b == 254) or a >= 224)


class Masker:
    def __init__(self):
        self.counts = {"ip": 0, "email": 0, "secret": 0, "token": 0}

    def text(self, s: str) -> str:
        def ip(m):
            parts = tuple(int(x) for x in m.groups())
            if any(p > 255 for p in parts) or private_ip(parts):
                return m.group(0)
            self.counts["ip"] += 1
            return "[공인IP]"

        def secret(m):
            self.counts["secret"] += 1
            return m.group(1) + m.group(2) + "[가림]"

        def token(_m):
            self.counts["token"] += 1
            return "[토큰]"

        def email(_m):
            self.counts["email"] += 1
            return "[이메일]"

        s = IP_RE.sub(ip, s)
        s = TOKEN_RE.sub(token, s)
        s = SECRET_RE.sub(secret, s)
        s = EMAIL_RE.sub(email, s)
        return s

    def walk(self, value):
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, list):
            return [self.walk(v) for v in value]
        if isinstance(value, dict):
            return {k: self.walk(v) for k, v in value.items()}
        return value


# ---------------------------------------------------------------- 조립

def build_payload(cfg: dict, pw: str | None = None) -> dict:
    log = SourceLog()
    bridge = Path(cfg["bridge_dir"])
    limits = cfg["limits"]
    tasks, task_msgs, coord_meta = load_tasks(bridge, log)
    messages = load_messages(bridge, limits, log)
    validations = load_validations(bridge, log)
    handoffs = load_handoffs(bridge, log)
    ledger = load_ledger(Path(cfg["ledger_path"]), limits, log)
    memory = load_memory(Path(cfg["claude_memory_dir"]), log)
    load_ai_runs(Path(cfg["ai_runs_dir"]), log)
    curated = load_curated(cfg.get("curated_files", []), log)
    tasks, conflicts = merge_tasks(tasks, curated["tasks"])
    # 아키텍트가 업무 보드에서 빼라고 한 작업(hidden)은 화면 목록에서 제외하고, 무엇을 뺐는지만 남긴다
    hidden_tasks = [{"id": t["id"], "title": t.get("title"), "reason": t.get("hidden_reason")} for t in tasks if t.get("hidden")]
    tasks = [t for t in tasks if not t.get("hidden")]
    nodes, agents, node_records, asks, runs, holds, notice_acks = load_nodes(cfg, pw, log)
    notices = sorted(({**n, "acks": notice_acks.get(n.get("id"), {})} for n in curated["notices"] if n.get("id")),
                     key=lambda n: n.get("ts") or "", reverse=True)[:30]
    curated["decisions_needed"] += asks
    curated["user_actions"] += health_actions(agents)
    topics = load_topics(cfg, log, node_records, {a["id"] for a in agents} or None)
    works = load_works(cfg, topics, log)
    from topics import load_routing
    routing = load_routing(cfg)

    # tasks.json의 메시지 상태(ACK 대기)를 메시지 목록에 반영
    ack_pending = {m.get("id") for m in task_msgs if str(m.get("ack", "")).lower() in ("pending", "")
                   or m.get("state") in ("queued", "queued_unacknowledged")}
    if coord_meta.get("handoff", {}) and coord_meta["handoff"].get("status", "").startswith("queued"):
        ack_pending.add(coord_meta["handoff"].get("message_id"))
    ack_pending.discard(None)

    payload = {
        "meta": {
            "project": cfg.get("project_name", "REAL 운영체제"),
            "generated_at": iso(now()),
            "generator_version": GENERATOR_VERSION,
            "limits": limits,
            "coordination": coord_meta,
            "conflicts": conflicts,
            "hidden_tasks": hidden_tasks,
            "ack_pending": sorted(ack_pending),
            "repo": cfg.get("github_repo") or None,
            "hub": (cfg.get("pc") or {}).get("id"),
            "routing": {"auto": routing.get("auto", True), "default_agent": routing.get("default_agent", "dev-claude"),
                        "rules": routing.get("rules", []), "stale_minutes": routing.get("stale_minutes", 120),
                        "pcs": routing.get("pcs", {})},
        },
        "topics": topics,
        "nodes": nodes,
        "agents": agents,
        "runs": runs,
        "holds": holds,
        "works": works,
        "notices": notices,
        "sources": log.rows,
        "tasks": tasks,
        "messages": messages,
        "validations": validations,
        "handoffs": handoffs,
        "ledger": ledger,
        "memory": memory,
        "decisions": curated["decisions"],
        "decisions_needed": curated["decisions_needed"],
        "user_actions": curated["user_actions"],
        "notes": curated["notes"],
        "comments": curated["comments"],
        "acks": [a.get("key") for a in curated["acks"] if a.get("key")],
        "decisions_answered": curated["decisions_answered"],
        "processed_actions": curated["processed_actions"],
    }
    masker = Masker()
    payload = masker.walk(payload)
    payload["meta"]["masked"] = masker.counts
    return payload


# ---------------------------------------------------------------- 암호화

def get_password(args) -> str:
    if args.password_file:
        pw = Path(args.password_file).read_text(encoding="utf-8").strip()
    elif os.environ.get("REAL_OPS_PASSWORD"):
        pw = os.environ["REAL_OPS_PASSWORD"]
    else:
        pw = getpass.getpass("대시보드 비밀번호: ")
        if args.new_salt or not (ROOT / "docs" / "data.enc.json").exists():
            if getpass.getpass("한 번 더 입력: ") != pw:
                sys.exit("비밀번호가 일치하지 않습니다.")
    if len(pw) < 10:
        sys.exit("비밀번호는 10자 이상이어야 합니다.")
    return pw


def encrypt(payload: dict, out_path: Path, password: str, new_salt: bool):
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    env = dict(os.environ, REAL_OPS_PASSWORD=password)
    cmd = ["node", str(ROOT / "encrypt.mjs"), "encrypt", str(out_path)]
    if new_salt:
        cmd.append("--new-salt")
    res = subprocess.run(cmd, input=data, env=env, capture_output=True)
    if res.returncode != 0:
        sys.exit("암호화 실패: " + res.stderr.decode("utf-8", errors="replace"))
    return len(data), res.stdout.decode("utf-8", errors="replace").strip()


def stamp_assets():
    """index.html의 app.css/app.js 주소에 내용 해시를 붙여 캐시된 옛 화면이 남지 않게 한다."""
    import hashlib
    index = ROOT / "docs" / "index.html"
    html = read_text(index)
    for name in ("app.css", "app.js"):
        digest = hashlib.sha256((ROOT / "docs" / name).read_bytes()).hexdigest()[:10]
        html = re.sub(rf'{re.escape(name)}\?v=[0-9a-zA-Z]+', f"{name}?v={digest}", html)
    index.write_text(html, encoding="utf-8")


def main():
    # 콘솔 문자표(cp949)에 없는 글자가 있어도 출력 때문에 멈추지 않게
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=os.environ.get("REAL_OPS_CONFIG") or str(ROOT / "config.local.json"))
    ap.add_argument("--password-file", help="비밀번호를 담은 파일(로컬 시험용). 없으면 REAL_OPS_PASSWORD 또는 입력")
    ap.add_argument("--new-salt", action="store_true", help="새 salt로 암호화(비밀번호를 바꿀 때)")
    ap.add_argument("--dump", help="평문 JSON을 이 경로에 저장(디버그 전용, out/ 아래 권장)")
    ap.add_argument("--output", help="암호문 출력 경로(로컬 시험용). 시험 비밀번호로는 docs/에 쓰지 않는다")
    ap.add_argument("--no-encrypt", action="store_true", help="암호화하지 않고 --dump만 수행")
    ap.add_argument("--skip-unchanged", action="store_true",
                    help="생성 시각 말고 내용이 지난번과 같으면 암호문을 다시 만들지 않고 종료 코드 10으로 끝냄(자동 동기화용)")
    args = ap.parse_args()

    cfg = json.loads(read_text(Path(args.config)))
    example = json.loads(read_text(ROOT / "config.example.json"))
    cfg["limits"] = {**example["limits"], **cfg.get("limits", {})}
    if args.output:
        cfg["output"] = str(Path(args.output).resolve())
    # 다른 PC 기록을 열 때도 비밀번호가 필요하므로 먼저 받는다(--no-encrypt면 있을 때만 쓴다)
    if args.no_encrypt:
        pw = Path(args.password_file).read_text(encoding="utf-8").strip() if args.password_file else os.environ.get("REAL_OPS_PASSWORD")
    else:
        pw = get_password(args)
    payload = build_payload(cfg, pw)

    if args.dump:
        dump = Path(args.dump)
        dump.parent.mkdir(parents=True, exist_ok=True)
        dump.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    counts = {k: len(v) for k, v in payload.items() if isinstance(v, list)}
    print("수집:", json.dumps(counts, ensure_ascii=False))
    print("마스킹:", json.dumps(payload["meta"]["masked"], ensure_ascii=False))
    bad = [s for s in payload["sources"] if not s["ok"]]
    for s in bad:
        print(f"출처 경고: {s['name']} — {s['error']}")
    if args.no_encrypt:
        return
    import hashlib
    body = {k: v for k, v in payload.items() if k != "meta"}
    body["meta"] = {k: v for k, v in payload["meta"].items() if k != "generated_at"}
    assets = "".join(hashlib.sha256((ROOT / "docs" / n).read_bytes()).hexdigest() for n in ("app.js", "app.css"))
    digest = hashlib.sha256((json.dumps(body, ensure_ascii=False, sort_keys=True) + assets).encode("utf-8")).hexdigest()
    out = Path(args.output).resolve() if args.output else ROOT / cfg.get("output", "docs/data.enc.json")
    marker = ROOT / ".local" / ("last-content.sha256" if not args.output else "last-content-test.sha256")
    file_sha = lambda: hashlib.sha256(out.read_bytes()).hexdigest() if out.exists() else ""  # noqa: E731
    # 내용 해시와 함께 게시 파일 자체의 해시도 비교한다(다른 비밀번호로 만든 파일이 남아 있으면 다시 만든다)
    if args.skip_unchanged and marker.exists() and marker.read_text().split() == [digest, file_sha()]:
        print("변경 없음 — 다시 만들지 않습니다")
        sys.exit(10)
    stamp_assets()
    size, info = encrypt(payload, out, pw, args.new_salt)
    marker.parent.mkdir(exist_ok=True)
    marker.write_text(f"{digest} {file_sha()}")
    print(f"암호화 완료: {out} (평문 {size:,} bytes) {info}")


if __name__ == "__main__":
    main()
