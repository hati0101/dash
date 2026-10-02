"""주제 보드 도구 — 대시보드에서 던진 주제를 가져오고, Claude/Astra가 분배·진행 베이스·검토를 남긴다.

폴더 구조 (topics/는 평문이라 커밋하지 않음)
  topics/<주제ID>/topic.json    가져온 원본 (이 도구만 씀)
  topics/<주제ID>/claude.json   Claude 기록 (Claude만 씀)
  topics/<주제ID>/astra.json    Astra 기록 (Astra만 씀)

자주 쓰는 명령
  python topics.py pull                         GitHub 이슈의 암호문 주제를 가져옴
  python topics.py add-blob REALTOPIC1....      대시보드 "암호문 복사"로 받은 주제 추가
  python topics.py add --title "제목" --body "메모"
  python topics.py list                         누가 무엇을 할 차례인지 표시
  python topics.py triage <ID> --by claude --assign astra --note "분배 이유"
  python topics.py plan <ID> --by astra --goal "..." --scope "..." --first-step "..." --done-when "..."
  python topics.py note <ID> --by claude --kind review --body "검토 의견"
  python topics.py status <ID> --by claude --status active --task SESSION-RECONNECT-20261001
  python topics.py announce                     새 주제·배정·검토 요청을 수신함 메시지로 남김(중복 없음)
  python topics.py comment --by claude --target task:<작업ID> --body "답"   대시보드 대화창에 답 남기기

대시보드에서 보낸 "요청"([ops] 이슈)도 pull이 함께 처리한다. 결과는 data/user.json(사용자 몫, 이 도구만 씀)에 남는다.
  reply       대화창 답 → data/user.json comments + 받는 사람 수신함 메시지
  ack         밀린 메시지 일괄 확인 → inbox-claude 파일을 done/으로 이동(삭제 없음), 놓친 항목 확인 공유
  task-state  작업 여러 개 단계 변경 → data/user.json tasks
  decide      결정 필요 항목에 대한 사용자 선택 → data/user.json decisions_answered + Claude 수신함
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
KST = timezone(timedelta(hours=9))
ID_RE = re.compile(r"^T-\d{8}-[a-z0-9]{3,8}$")
BLOB_RE = re.compile(r"REALTOPIC1\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")
AUTHORS = ("claude", "astra")
STATUSES = ("new", "triage", "ready", "active", "done", "parked")
NOTE_KINDS = ("triage", "memo", "review", "plan", "question", "answer", "status")
KINDS = ("기능·개선", "버그", "조사·분석", "디자인", "운영·도구", "기타")
ACTION_ID_RE = re.compile(r"^A-\d{8}-[a-z0-9]{3,10}$")
REF_RE = re.compile(r"^[A-Za-z0-9_.:\-]{1,200}$")
TARGET_KINDS = ("task", "message", "topic", "decision", "general")
STAGES = ("request", "progress", "validating", "user_test", "blocked", "done")
ACTION_TYPES = ("reply", "ack", "task-state", "decide")


def now_iso() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def load_cfg() -> dict:
    # REAL_OPS_CONFIG로 다른 설정(시험용 등)을 지정할 수 있다
    path = Path(os.environ.get("REAL_OPS_CONFIG") or ROOT / "config.local.json")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def topics_dir(cfg: dict) -> Path:
    d = (ROOT / cfg.get("topics_dir", "topics")).resolve()
    d.mkdir(parents=True, exist_ok=True)
    return d


def topic_path(cfg: dict, tid: str) -> Path:
    if not ID_RE.match(tid):
        sys.exit(f"주제 ID 형식이 아닙니다: {tid}")
    return topics_dir(cfg) / tid


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return default


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def password(args) -> str:
    if getattr(args, "password_file", None):
        return Path(args.password_file).read_text(encoding="utf-8").strip()
    if os.environ.get("REAL_OPS_PASSWORD"):
        return os.environ["REAL_OPS_PASSWORD"]
    return getpass.getpass("대시보드 비밀번호: ")


def open_blob(blob: str, pw: str) -> dict:
    res = subprocess.run(["node", str(ROOT / "encrypt.mjs"), "open-topic", "-"], input=blob.encode(),
                         env=dict(os.environ, REAL_OPS_PASSWORD=pw), capture_output=True)
    if res.returncode != 0:
        raise ValueError(res.stderr.decode("utf-8", errors="replace").strip())
    return json.loads(res.stdout.decode("utf-8"))


def clean_topic(raw: dict) -> dict:
    """복호화된 주제를 검증·정규화한다. 브라우저에서 온 값이므로 형식을 강제한다."""
    if not isinstance(raw, dict):
        raise ValueError("주제 형식 오류")
    tid = str(raw.get("id", ""))
    if not ID_RE.match(tid):
        raise ValueError(f"주제 ID 형식 오류: {tid!r}")
    title = str(raw.get("title", "")).strip()[:200]
    if not title:
        raise ValueError("제목 없음")
    pri = str(raw.get("priority", "P2"))
    prefer = str(raw.get("prefer", "auto"))
    return {
        "id": tid,
        "title": title,
        "body": str(raw.get("body", ""))[:8000],
        "kind": str(raw.get("kind", "기타"))[:20],
        "priority": pri if pri in ("P0", "P1", "P2", "P3") else "P2",
        "prefer": prefer if prefer in ("auto", "claude", "astra") else "auto",
        "created_at": str(raw.get("created_at", now_iso()))[:40],
        "from": str(raw.get("from", "dashboard"))[:20],
    }


def save_topic(cfg: dict, topic: dict, source: str, extra: dict | None = None) -> bool:
    folder = topic_path(cfg, topic["id"])
    if (folder / "topic.json").exists():
        return False
    write_json(folder / "topic.json", {**topic, "source": source, "received_at": now_iso(), **(extra or {})})
    return True


# ---------------------------------------------------------------- 가져오기

def gh_token() -> str | None:
    if os.environ.get("GITHUB_TOKEN"):
        return os.environ["GITHUB_TOKEN"]
    gh = shutil.which("gh")
    if gh:
        r = subprocess.run([gh, "auth", "token"], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    return None


def fetch_issues(repo: str) -> list[dict]:
    token = gh_token()
    out = []
    for page in range(1, 11):
        req = urllib.request.Request(
            f"https://api.github.com/repos/{repo}/issues?state=all&per_page=100&page={page}",
            headers={"Accept": "application/vnd.github+json", "User-Agent": "real-ops-dashboard",
                     **({"Authorization": f"Bearer {token}"} if token else {})})
        with urllib.request.urlopen(req, timeout=30) as r:
            batch = json.loads(r.read().decode("utf-8"))
        out.extend(i for i in batch if "pull_request" not in i)
        if len(batch) < 100:
            break
    return out


def cmd_pull(args, cfg):
    repo = cfg.get("github_repo")
    if not repo:
        sys.exit("config.local.json에 github_repo(\"owner/name\")가 없습니다.")
    state_path = topics_dir(cfg) / ".pulled.json"
    pulled = read_json(state_path, {})
    issues = [i for i in fetch_issues(repo) if str(i.get("title", "")).startswith(("[topic]", "[ops]"))]
    todo = sorted((i for i in issues if str(i["number"]) not in pulled), key=lambda i: i["number"])
    if not todo:
        print(f"새 주제·요청 없음 (이슈 {len(issues)}건 확인)")
        return
    pw = password(args)
    added = acted = 0
    for i in todo:
        num = str(i["number"])
        m = BLOB_RE.search(i.get("body") or "")
        if not m:
            pulled[num] = {"result": "암호문 없음", "at": now_iso()}
            print(f"#{num}: 암호문 없음 — 건너뜀")
            continue
        try:
            raw = open_blob(m.group(0), pw)
            if isinstance(raw, dict) and raw.get("type") in ACTION_TYPES:
                action = clean_action(raw)
                if action["id"] not in i["title"]:
                    raise ValueError("이슈 제목과 요청 ID 불일치")
                print(f"#{num}: " + apply_action(cfg, action, f"GitHub 이슈 #{num}"))
                acted += 1
                pulled[num] = {"result": "ok", "action": action["id"], "at": now_iso()}
            else:
                topic = clean_topic(raw)
                if topic["id"] not in i["title"]:
                    raise ValueError("이슈 제목과 주제 ID 불일치")
                if save_topic(cfg, topic, f"GitHub 이슈 #{num}", {"issue_number": i["number"]}):
                    added += 1
                    print(f"#{num}: 주제 추가 {topic['id']} — {topic['title']}")
                pulled[num] = {"result": "ok", "topic": topic["id"], "at": now_iso()}
        except ValueError as exc:
            # 키를 모르는 사람이 만든 이슈이거나 비밀번호가 다름. 처리 완료로 표시하지 않고 다음에 다시 본다.
            print(f"#{num}: {exc}")
            continue
        if args.close and shutil.which("gh") and i.get("state") == "open":
            subprocess.run(["gh", "issue", "close", num, "--repo", repo, "--comment", "대시보드로 가져왔습니다."],
                           capture_output=True)
        write_json(state_path, pulled)  # 한 건씩 기록해 중간 실패에도 중복 처리하지 않는다
    write_json(state_path, pulled)
    print(f"가져온 주제 {added}건 · 처리한 요청 {acted}건")


def cmd_add_blob(args, cfg):
    try:
        raw = open_blob(args.blob, password(args))
        if isinstance(raw, dict) and raw.get("type") in ACTION_TYPES:
            print(apply_action(cfg, clean_action(raw), "대시보드 암호문 복사"))
            return
        topic = clean_topic(raw)
    except ValueError as exc:
        sys.exit(str(exc))
    print(("추가 " if save_topic(cfg, topic, "대시보드 암호문 복사") else "이미 있음 ") + f"{topic['id']} — {topic['title']}")


# ---------------------------------------------------------------- 대시보드 요청(답·일괄 확인·단계 변경·결정)

def clean_ref(v, what: str) -> str:
    v = str(v or "")
    if not REF_RE.match(v):
        raise ValueError(f"{what} 형식 오류: {v[:40]!r}")
    return v


def clean_target(t) -> dict:
    if not isinstance(t, dict) or t.get("kind") not in TARGET_KINDS:
        raise ValueError("대상 형식 오류")
    return {"kind": t["kind"], "id": clean_ref(t.get("id") or "general", "대상 ID"),
            "title": str(t.get("title", ""))[:200]}


def clean_action(raw: dict) -> dict:
    """브라우저에서 온 요청을 검증·정규화한다. 형식이 틀리면 ValueError."""
    aid = str(raw.get("id", ""))
    if not ACTION_ID_RE.match(aid):
        raise ValueError(f"요청 ID 형식 오류: {aid!r}")
    kind = raw["type"]
    a = {"id": aid, "type": kind, "created_at": str(raw.get("created_at", now_iso()))[:40]}
    if kind == "reply":
        body = str(raw.get("body", "")).strip()
        if not body:
            raise ValueError("빈 답")
        a.update(target=clean_target(raw.get("target")), body=body[:6000],
                 to=raw.get("to") if raw.get("to") in AUTHORS else "claude")
    elif kind == "ack":
        msgs, keys = raw.get("messages") or [], raw.get("keys") or []
        if not isinstance(msgs, list) or not isinstance(keys, list) or len(msgs) > 1000 or len(keys) > 1000:
            raise ValueError("확인 목록 형식 오류")
        a.update(messages=[clean_ref(x, "메시지 ID") for x in msgs],
                 keys=[str(k)[:300] for k in keys if isinstance(k, str)])
    elif kind == "task-state":
        ids = raw.get("ids") or []
        if not isinstance(ids, list) or not ids or len(ids) > 200:
            raise ValueError("작업 목록 형식 오류")
        stage = raw.get("stage")
        if stage not in STAGES:
            raise ValueError("단계 값 오류")
        a.update(ids=[clean_ref(x, "작업 ID") for x in ids], stage=stage, note=str(raw.get("note", ""))[:2000])
    elif kind == "decide":
        a.update(target=clean_ref(raw.get("decision_id"), "결정 ID"), choice=str(raw.get("choice", "")).strip()[:500],
                 note=str(raw.get("note", "")).strip()[:3000])
        if not a["choice"] and not a["note"]:
            raise ValueError("빈 결정")
    return a


def data_dir(cfg) -> Path:
    return (ROOT / cfg.get("data_dir", "data")).resolve()


def user_file(cfg) -> tuple[Path, dict]:
    path = data_dir(cfg) / "user.json"
    rec = read_json(path, None) or {"author": "user", "_rule": "이 파일은 topics.py가 사용자 요청을 받아서만 쓴다."}
    for key in ("processed_actions", "comments", "tasks", "acks", "decisions_answered"):
        rec.setdefault(key, [])
    return path, rec


def inbox_message_index(folder: Path) -> dict:
    """inbox 폴더의 message_id → 파일 경로. 헤더가 없으면 파일 이름(확장자 제외)."""
    out = {}
    for p in folder.glob("*.md"):
        mid = p.stem
        try:
            for line in p.read_text(encoding="utf-8-sig", errors="replace").splitlines()[:15]:
                m = re.match(r"^\s*message[_-]id:\s*(\S+)", line, re.I)
                if m:
                    mid = m.group(1)
                    break
        except OSError:
            continue
        out.setdefault(mid, p)
    return out


def apply_action(cfg, a: dict, source: str) -> str:
    path, rec = user_file(cfg)
    if a["id"] in rec["processed_actions"]:
        return f"이미 처리한 요청 {a['id']}"
    bridge = Path(cfg["bridge_dir"])
    ts = now_iso()
    if a["type"] == "reply":
        rec["comments"].append({"id": a["id"], "ts": a["created_at"] or ts, "target": a["target"],
                                "to": a["to"], "body": a["body"], "source": source})
        t = a["target"]
        box = bridge / ("inbox-astra" if a["to"] == "astra" else "inbox-claude")
        write_inbox(box, f"USR-REPLY-{a['id']}", f"[사용자 → {a['to'].capitalize()}] 대시보드 답: {t.get('title') or t['id']}",
                    {"sender": "user (대시보드)", "recipient": a["to"], "kind": "user reply via dashboard",
                     "task_id": t["id"] if t["kind"] in ("task", "topic") else None,
                     "in_reply_to": t["id"] if t["kind"] == "message" else None, "target": f"{t['kind']}:{t['id']}"},
                    a["body"] + f"\n\n(대시보드 대화창에서 보냄 · 답은 python topics.py comment --by {a['to']} --target {t['kind']}:{t['id']} --body \"...\")")
        result = f"답 전달 → {a['to']} ({t['kind']}:{t['id']})"
    elif a["type"] == "ack":
        inbox = bridge / "inbox-claude"
        done = inbox / "done"
        done.mkdir(parents=True, exist_ok=True)
        index = inbox_message_index(inbox)
        moved = 0
        for mid in a["messages"]:
            src = index.get(mid)
            if not src or not src.exists():
                continue
            dst = done / src.name
            n = 1
            while dst.exists():
                dst = done / f"{src.stem}-{n}{src.suffix}"
                n += 1
            src.replace(dst)  # 이동만 한다. 삭제하지 않는다.
            moved += 1
        for k in a["keys"]:
            rec["acks"].append({"key": k, "ts": ts, "action": a["id"]})
        rec["acks"] = rec["acks"][-2000:]
        result = f"일괄 확인: 메시지 {moved}/{len(a['messages'])}건 done으로 이동, 놓친 항목 {len(a['keys'])}건 확인"
    elif a["type"] == "task-state":
        for tid in a["ids"]:
            rec["tasks"] = [r for r in rec["tasks"] if r.get("id") != tid]
            rec["tasks"].append({"id": tid, "stage": a["stage"], "state": f"user_set_{a['stage']}",
                                 "user_note": a["note"] or None, "updated_at": a["created_at"] or ts})
        write_inbox(bridge / "inbox-claude", f"USR-STATE-{a['id']}", f"[사용자 → Claude] 작업 단계 변경 {len(a['ids'])}건 → {a['stage']}",
                    {"sender": "user (대시보드)", "recipient": "claude", "kind": "user task-state via dashboard"},
                    "\n".join(f"- {x}" for x in a["ids"]) + (f"\n\n메모: {a['note']}" if a["note"] else ""))
        result = f"작업 {len(a['ids'])}건 단계 → {a['stage']}"
    else:  # decide
        rec["decisions_answered"] = [r for r in rec["decisions_answered"] if r.get("id") != a["target"]]
        rec["decisions_answered"].append({"id": a["target"], "choice": a["choice"], "note": a["note"], "ts": a["created_at"] or ts})
        write_inbox(bridge / "inbox-claude", f"USR-DECIDE-{a['id']}", f"[사용자 → Claude] 결정: {a['target']} → {a['choice'] or '(메모)'}",
                    {"sender": "user (대시보드)", "recipient": "claude", "kind": "user decision via dashboard", "in_reply_to": a["target"]},
                    (a["choice"] or "") + (f"\n\n{a['note']}" if a["note"] else ""))
        result = f"결정 기록 {a['target']} → {a['choice'] or '메모'}"
    rec["processed_actions"].append(a["id"])
    rec["processed_actions"] = rec["processed_actions"][-3000:]
    rec["updated_at"] = ts
    write_json(path, rec)
    return result


def cmd_comment(args, cfg):
    kind, _, ref = args.target.partition(":")
    if kind not in TARGET_KINDS or not REF_RE.match(ref or ""):
        sys.exit("--target 형식: task:<ID> | message:<ID> | topic:<ID> | decision:<ID> | general:all")
    path = data_dir(cfg) / f"{args.by}.json"
    rec = read_json(path, None) or {"author": args.by}
    rec.setdefault("comments", []).append({"id": f"C-{datetime.now(KST):%Y%m%d}-{secrets.token_hex(3)}", "ts": now_iso(),
                                           "target": {"kind": kind, "id": ref}, "body": args.body.strip()})
    write_json(path, rec)  # updated_at은 바꾸지 않는다(작업 갱신 시각과 혼동 방지)
    print(f"{args.by} 답 기록 → {kind}:{ref}")


def cmd_add(args, cfg):
    d = datetime.now(KST)
    tid = f"T-{d:%Y%m%d}-{secrets.token_hex(3)}"
    topic = clean_topic({"id": tid, "title": args.title, "body": args.body or "", "kind": args.kind,
                         "priority": args.priority, "prefer": args.prefer, "created_at": now_iso(), "from": "pc"})
    save_topic(cfg, topic, "PC 직접 입력")
    print(f"추가 {tid} — {topic['title']}")


# ---------------------------------------------------------------- 작성자 기록

def author_file(cfg, tid: str, by: str) -> tuple[Path, dict]:
    if by not in AUTHORS:
        sys.exit("--by는 claude 또는 astra만 허용합니다.")
    folder = topic_path(cfg, tid)
    if not (folder / "topic.json").exists():
        sys.exit(f"주제가 없습니다: {tid}")
    path = folder / f"{by}.json"
    return path, read_json(path, {"author": by, "notes": []})


def add_note(rec: dict, kind: str, body: str | None):
    if body:
        rec.setdefault("notes", []).append({"ts": now_iso(), "kind": kind, "body": body.strip()})


def cmd_triage(args, cfg):
    path, rec = author_file(cfg, args.id, args.by)
    rec["assignee"] = args.assign
    rec["status"] = args.status or "triage"
    add_note(rec, "triage", args.note or f"{args.assign}에게 배정")
    rec["updated_at"] = now_iso()
    write_json(path, rec)
    print(f"{args.id}: 담당 {args.assign}, 상태 {rec['status']}")


def cmd_plan(args, cfg):
    path, rec = author_file(cfg, args.id, args.by)
    plan = rec.get("plan", {})
    for key, val in (("goal", args.goal), ("done_when", args.done_when)):
        if val:
            plan[key] = val
    for key, vals in (("scope", args.scope), ("inputs", args.input), ("first_steps", args.first_step), ("risks", args.risk)):
        if vals:
            plan[key] = vals
    rec["plan"] = plan
    rec["status"] = args.status or "ready"
    add_note(rec, "plan", args.note or "진행 베이스 작성")
    rec["updated_at"] = now_iso()
    write_json(path, rec)
    print(f"{args.id}: 진행 베이스 기록, 상태 {rec['status']}")


def cmd_note(args, cfg):
    path, rec = author_file(cfg, args.id, args.by)
    add_note(rec, args.kind, args.body)
    rec["updated_at"] = now_iso()
    write_json(path, rec)
    print(f"{args.id}: {args.by} {args.kind} 기록")


def cmd_status(args, cfg):
    path, rec = author_file(cfg, args.id, args.by)
    if args.status:
        rec["status"] = args.status
    if args.task:
        rec["linked_task_id"] = args.task
    add_note(rec, "status", args.note or f"상태 {args.status or '유지'}" + (f", 작업 {args.task} 연결" if args.task else ""))
    rec["updated_at"] = now_iso()
    write_json(path, rec)
    print(f"{args.id}: 갱신")


# ---------------------------------------------------------------- 병합·조회 (build.py와 공유)

def merged_topics(folder: Path) -> list[dict]:
    out = []
    if not folder.is_dir():
        return out
    for d in sorted(p for p in folder.iterdir() if p.is_dir() and ID_RE.match(p.name)):
        base = read_json(d / "topic.json")
        if not base:
            continue
        recs = {a: read_json(d / f"{a}.json") for a in AUTHORS}
        recs = {a: r for a, r in recs.items() if r}
        t = dict(base)
        t["notes"] = sorted(({**n, "by": a} for a, r in recs.items() for n in r.get("notes", [])), key=lambda n: n.get("ts", ""))
        ordered = sorted(recs.items(), key=lambda kv: kv[1].get("updated_at", ""))
        t["status"] = "new"
        for a, r in ordered:  # 가장 최근 기록의 상태가 이긴다
            if r.get("status") in STATUSES:
                t["status"] = r["status"]
            if r.get("linked_task_id"):
                t["linked_task_id"] = r["linked_task_id"]
            if r.get("priority") in ("P0", "P1", "P2", "P3"):
                t["priority"] = r["priority"]
        # 담당 지정은 사령탑(Claude) 기록 우선
        t["assignee"] = (recs.get("claude") or {}).get("assignee") or (recs.get("astra") or {}).get("assignee")
        planner = t["assignee"] if t["assignee"] in recs and recs[t["assignee"]].get("plan") else \
            next((a for a, r in ordered[::-1] if r.get("plan")), None)
        if planner:
            t["plan"], t["plan_by"] = recs[planner]["plan"], planner
        t["updated_at"] = max([base.get("received_at", "")] + [r.get("updated_at", "") for r in recs.values()])
        t["authors"] = sorted(recs)
        t["turn"] = whose_turn(t, recs)
        out.append(t)
    return out


def whose_turn(t: dict, recs: dict) -> str | None:
    if t["status"] in ("done", "parked"):
        return None
    if not recs:
        return "claude"  # 사령탑 분배 대기
    a = t.get("assignee")
    if a and not (recs.get(a) or {}).get("plan") and t["status"] in ("new", "triage"):
        return a  # 진행 베이스 작성 대기
    other = {"claude": "astra", "astra": "claude"}.get(a or "")
    if a and other and (recs.get(a) or {}).get("plan"):
        reviewed = any(n.get("kind") == "review" for n in (recs.get(other) or {}).get("notes", []))
        if not reviewed:
            return other  # 교차 검토 대기
    return a


def cmd_list(args, cfg):
    topics = merged_topics(topics_dir(cfg))
    if not topics:
        print("주제 없음")
        return
    for t in sorted(topics, key=lambda x: x["created_at"], reverse=True):
        print(f"{t['id']}  [{t['status']:<6}] {t['priority']}  담당={t.get('assignee') or '-':<6} 차례={t.get('turn') or '-':<6} {t['title']}")


# ---------------------------------------------------------------- 알림 (수신함 메시지, 중복 없음)

def write_inbox(folder: Path, mid: str, first_line: str, headers: dict, body: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(KST).strftime("%Y%m%d-%H%M%S")
    path = folder / f"{stamp}-{mid}.md"
    lines = [first_line, f"message_id: {mid}"] + [f"{k}: {v}" for k, v in headers.items() if v] + ["", body.strip(), ""]
    tmp = path.with_suffix(".tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    tmp.replace(path)
    return path


def cmd_announce(args, cfg):
    bridge = Path(cfg["bridge_dir"])
    folder = topics_dir(cfg)
    sent = 0
    for t in merged_topics(folder):
        state_path = folder / t["id"] / ".announced.json"
        done = set(read_json(state_path, []))
        turn, short = t.get("turn"), t["id"]
        brief = f"주제: {t['title']}\n유형: {t.get('kind')} · 우선순위: {t['priority']} · 선호: {t.get('prefer')}\n\n원래 메모:\n{t.get('body') or '(없음)'}"
        jobs = []
        if t["status"] == "new" and not t["authors"]:
            jobs.append(("new", bridge / "inbox-claude", f"DASH-TOPIC-NEW-{short}",
                         f"[대시보드 → Claude] 새 주제 분배 필요: {t['title']}",
                         {"sender": "dashboard", "recipient": "Claude lead", "kind": "topic new; triage needed", "task_id": short},
                         brief + f"\n\n다음: python topics.py triage {short} --by claude --assign <claude|astra> --note \"이유\""))
        if turn == "astra" and t.get("assignee") == "astra" and not t.get("plan"):
            jobs.append(("assign-astra", bridge / "inbox-astra", f"C2A-TOPIC-ASSIGN-{short}",
                         f"[Claude → Astra] 주제 배정 — 진행 베이스 작성 요청: {t['title']}",
                         {"sender": "Claude (사령탑)", "recipient": "Astra", "kind": "topic assignment; plan requested", "task_id": short},
                         brief + "\n\n요청: 목표·범위·필요한 입력·첫 단계·위험·완료 기준을 진행 베이스로 남겨주세요. 구현·설치·DB 변경은 하지 않습니다.\n"
                         f"기록: python \"{ROOT / 'topics.py'}\" plan {short} --by astra --goal \"...\" --scope \"...\" --first-step \"...\" --done-when \"...\"\n"
                         f"(직접 편집 시 {folder / short / 'astra.json'} 만 수정)"))
        if turn == "astra" and t.get("assignee") == "claude" and t.get("plan"):
            jobs.append(("review-astra", bridge / "inbox-astra", f"C2A-TOPIC-REVIEW-{short}",
                         f"[Claude → Astra] 주제 진행 베이스 교차 검토 요청: {t['title']}",
                         {"sender": "Claude (사령탑)", "recipient": "Astra", "kind": "topic review request", "task_id": short},
                         brief + "\n\nClaude 진행 베이스:\n" + json.dumps(t["plan"], ensure_ascii=False, indent=1) +
                         f"\n\n기록: python \"{ROOT / 'topics.py'}\" note {short} --by astra --kind review --body \"검토 의견\""))
        for key, box, mid, first, headers, body in jobs:
            if key in done:
                continue
            p = write_inbox(box, mid, first, headers, body)
            done.add(key)
            sent += 1
            print(f"작성: {p}")
        if jobs:
            write_json(state_path, sorted(done))
    print(f"새 알림 {sent}건" + (" — Astra가 쉬는 중이면 delegate.py queue로 같은 message_id를 한 번 전달하세요." if sent else ""))


# ---------------------------------------------------------------- CLI

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--password-file")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pull"); p.add_argument("--close", action="store_true", help="가져온 이슈를 닫음(gh 필요)")
    p = sub.add_parser("add-blob"); p.add_argument("blob")
    p = sub.add_parser("add"); p.add_argument("--title", required=True); p.add_argument("--body")
    p.add_argument("--kind", default="기타", choices=KINDS); p.add_argument("--priority", default="P2", choices=["P0", "P1", "P2", "P3"])
    p.add_argument("--prefer", default="auto", choices=["auto", "claude", "astra"])
    sub.add_parser("list")
    sub.add_parser("announce")
    p = sub.add_parser("triage"); p.add_argument("id"); p.add_argument("--by", required=True, choices=AUTHORS)
    p.add_argument("--assign", required=True, choices=AUTHORS); p.add_argument("--status", choices=STATUSES); p.add_argument("--note")
    p = sub.add_parser("plan"); p.add_argument("id"); p.add_argument("--by", required=True, choices=AUTHORS)
    p.add_argument("--goal"); p.add_argument("--scope", action="append"); p.add_argument("--input", action="append")
    p.add_argument("--first-step", action="append"); p.add_argument("--risk", action="append"); p.add_argument("--done-when")
    p.add_argument("--status", choices=STATUSES); p.add_argument("--note")
    p = sub.add_parser("note"); p.add_argument("id"); p.add_argument("--by", required=True, choices=AUTHORS)
    p.add_argument("--kind", default="memo", choices=NOTE_KINDS); p.add_argument("--body", required=True)
    p = sub.add_parser("status"); p.add_argument("id"); p.add_argument("--by", required=True, choices=AUTHORS)
    p.add_argument("--status", choices=STATUSES); p.add_argument("--task"); p.add_argument("--note")
    p = sub.add_parser("comment"); p.add_argument("--by", required=True, choices=AUTHORS)
    p.add_argument("--target", required=True, help="task:<ID> | message:<ID> | topic:<ID> | decision:<ID> | general:all")
    p.add_argument("--body", required=True)
    args = ap.parse_args()
    cfg = load_cfg()
    {"pull": cmd_pull, "add-blob": cmd_add_blob, "add": cmd_add, "list": cmd_list, "announce": cmd_announce,
     "triage": cmd_triage, "plan": cmd_plan, "note": cmd_note, "status": cmd_status, "comment": cmd_comment}[args.cmd](args, cfg)


if __name__ == "__main__":
    main()
