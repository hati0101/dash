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
ACTION_TYPES = ("reply", "ack", "task-state", "decide", "assign", "activate")
AGENT_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,30}$")


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
    if prefer not in ("auto", "claude", "astra", "gpt") and not AGENT_RE.match(prefer):
        prefer = "auto"
    return {
        "id": tid,
        "title": title,
        "body": str(raw.get("body", ""))[:8000],
        "kind": str(raw.get("kind", "기타"))[:20],
        "priority": pri if pri in ("P0", "P1", "P2", "P3") else "P2",
        "prefer": prefer,
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
        to = norm_agent(str(raw.get("to") or "dev-claude"))
        a.update(target=clean_target(raw.get("target")), body=body[:6000], to=to if AGENT_RE.match(to) else "dev-claude")
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
    elif kind == "assign":
        topic, agent = str(raw.get("topic", "")), norm_agent(str(raw.get("agent", "")))
        if not ID_RE.match(topic) or not AGENT_RE.match(agent or ""):
            raise ValueError("담당 지정 형식 오류")
        a.update(topic=topic, agent=agent, note=str(raw.get("note", ""))[:1000])
    elif kind == "activate":
        topic = str(raw.get("topic", ""))
        if not ID_RE.match(topic):
            raise ValueError("착수 지시 형식 오류")
        a.update(topic=topic)
    return a


def data_dir(cfg) -> Path:
    return (ROOT / cfg.get("data_dir", "data")).resolve()


def user_file(cfg) -> tuple[Path, dict]:
    path = data_dir(cfg) / "user.json"
    rec = read_json(path, None) or {"author": "user", "_rule": "이 파일은 topics.py가 사용자 요청을 받아서만 쓴다."}
    for key in ("processed_actions", "comments", "tasks", "acks", "decisions_answered", "topic_assign", "topic_activate"):
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
        local = {"dev-claude": ("inbox-claude", "claude"), "dev-astra": ("inbox-astra", "astra")}
        if a["to"] in local:
            box, who = local[a["to"]]
            write_inbox(bridge / box, f"USR-REPLY-{a['id']}", f"[사용자 → {who.capitalize()}] 대시보드 답: {t.get('title') or t['id']}",
                        {"sender": "user (대시보드)", "recipient": who, "kind": "user reply via dashboard",
                         "task_id": t["id"] if t["kind"] in ("task", "topic") else None,
                         "in_reply_to": t["id"] if t["kind"] == "message" else None, "target": f"{t['kind']}:{t['id']}"},
                        a["body"] + f"\n\n(대시보드 대화창에서 보냄 · 답은 python topics.py comment --by {who} --target {t['kind']}:{t['id']} --body \"...\")")
            result = f"답 전달 → {a['to']} ({t['kind']}:{t['id']})"
        else:
            result = f"답 기록 → {a['to']} (그 PC의 node.py inbox가 전달)"
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
    elif a["type"] == "assign":
        rec["topic_assign"] = [r for r in rec["topic_assign"] if r.get("topic") != a["topic"]]
        rec["topic_assign"].append({"topic": a["topic"], "agent": a["agent"], "note": a["note"], "ts": a["created_at"] or ts})
        write_inbox(bridge / "inbox-claude", f"USR-ASSIGN-{a['id']}", f"[사용자 → Claude] 주제 담당 변경: {a['topic']} → {a['agent']}",
                    {"sender": "user (대시보드)", "recipient": "claude", "kind": "user topic assignment", "task_id": a["topic"]},
                    a["note"] or "대시보드에서 담당을 바꿨습니다.")
        result = f"주제 담당 지정 {a['topic']} → {a['agent']}"
    elif a["type"] == "activate":
        rec["topic_activate"] = [r for r in rec["topic_activate"] if r.get("topic") != a["topic"]]
        rec["topic_activate"].append({"topic": a["topic"], "ts": a["created_at"] or ts, "by": "dashboard"})
        result = f"미처리 주제 착수 지시 {a['topic']} — 다음 자동 배분 때 담당 지정"
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
    extra = {"backlog": True} if getattr(args, "backlog", False) else None
    save_topic(cfg, topic, getattr(args, "source", None) or "PC 직접 입력", extra)
    print(f"추가 {tid}{' (미처리)' if extra else ''} — {topic['title']}")


def cmd_activate(args, cfg):
    """미처리(백로그) 주제를 착수 대상으로 바꾼다. 다음 자동 배분 때 담당이 정해진다."""
    path, rec = user_file(cfg)
    if not (topic_path(cfg, args.id) / "topic.json").exists():
        sys.exit(f"주제가 없습니다: {args.id}")
    rec["topic_activate"] = [r for r in rec.get("topic_activate", []) if r.get("topic") != args.id]
    rec["topic_activate"].append({"topic": args.id, "ts": now_iso(), "by": "pc"})
    rec["updated_at"] = now_iso()
    write_json(path, rec)
    print(f"{args.id}: 착수 대상으로 전환 — 다음 자동 배분 때 담당 지정")


def cmd_import_proposals(args, cfg):
    """각 PC 작업자가 node.py propose로 올린 메모를 미처리 주제로 한 건씩 가져온다(허브 전용, 중복 없음)."""
    import hashlib
    from node import collect_nodes
    if (cfg.get("pc") or {}).get("role") != "hub":
        sys.exit("메모 가져오기는 허브 PC에서만 실행합니다.")
    pw = os.environ.get("REAL_OPS_PASSWORD") or (Path(args.password_file).read_text(encoding="utf-8").strip() if args.password_file else None)
    state_path = topics_dir(cfg) / ".imported-proposals.json"
    done = read_json(state_path, {})
    added = 0
    for n in collect_nodes(cfg, pw):
        for p in n.get("proposals") or []:
            pid = str(p.get("id", ""))
            if not pid or pid in done:
                continue
            day = str(p.get("ts", now_iso()))[:10].replace("-", "")
            tid = f"T-{day}-{hashlib.sha1(pid.encode()).hexdigest()[:6]}"
            try:
                topic = clean_topic({"id": tid, "title": p.get("title"), "body": p.get("body", ""), "kind": p.get("kind", "기타"),
                                     "priority": p.get("priority", "P2"), "prefer": "auto", "created_at": p.get("ts"), "from": n["pc"]})
            except ValueError as exc:
                done[pid] = {"error": str(exc), "at": now_iso()}
                continue
            label = f"{n.get('label', n['pc'])} {p.get('agent')} 메모"
            if save_topic(cfg, topic, label, {"backlog": True, "proposal_id": pid, "proposed_by": p.get("agent")}):
                added += 1
                print(f"가져옴 {tid} ← {label}: {topic['title']}")
            done[pid] = {"topic": tid, "at": now_iso()}
    write_json(state_path, done)
    print(f"메모 가져오기 {added}건")


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
    agent = norm_agent(args.assign)
    if not AGENT_RE.match(agent or ""):
        sys.exit("--assign은 작업자 ID여야 합니다 (예: dev-claude, server-gpt)")
    rec["assignee"] = agent
    rec["status"] = args.status or "triage"
    rec["dispatch_reason"] = f"수동 배정: {args.note}" if args.note else "수동 배정"
    add_note(rec, "triage", args.note or f"{agent}에게 배정")
    rec["updated_at"] = rec["assigned_at"] = rec["status_at"] = now_iso()
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
    if args.status or rec.get("status") in (None, "new", "triage"):
        rec["status"] = args.status or "ready"
        rec["status_at"] = now_iso()
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
        rec["status_at"] = now_iso()
    if args.task:
        rec["linked_task_id"] = args.task
    add_note(rec, "status", args.note or f"상태 {args.status or '유지'}" + (f", 작업 {args.task} 연결" if args.task else ""))
    rec["updated_at"] = now_iso()
    write_json(path, rec)
    print(f"{args.id}: 갱신")


# ---------------------------------------------------------------- 병합·조회 (build.py와 공유)

# 허브(개발컴)의 기존 작성자 파일 이름 → 작업자 ID
FILE_AGENT = {"claude": "dev-claude", "astra": "dev-astra"}
LEAD = "dev-claude"


def to_dt(v) -> datetime:
    """시각 문자열(UTC 'Z' 또는 +09:00 등)을 비교 가능한 값으로. 없거나 형식이 틀리면 가장 이른 시각."""
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=KST)
    except ValueError:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)


def norm_agent(x: str | None) -> str | None:
    return FILE_AGENT.get(x, x) if x else None


def user_assigns(cfg: dict | None) -> dict:
    if not cfg:
        return {}
    rec = read_json(data_dir(cfg) / "user.json", None) or {}
    out = {}
    for r in rec.get("topic_assign", []):
        out[r.get("topic")] = r
    return out


def merged_topics(folder: Path, cfg: dict | None = None, node_records: list[dict] | None = None) -> list[dict]:
    """주제 원본 + 허브 작성자 파일(claude/astra) + 다른 PC 작업자 기록 + 사용자 지정 담당을 합친다."""
    out = []
    if not folder.is_dir():
        return out
    assigns = user_assigns(cfg)
    activations = {r.get("topic") for r in (read_json(data_dir(cfg) / "user.json", None) or {}).get("topic_activate", [])} if cfg else set()
    by_topic: dict[str, list[dict]] = {}
    for r in node_records or []:
        by_topic.setdefault(r.get("topic"), []).append(r)
    for d in sorted(p for p in folder.iterdir() if p.is_dir() and ID_RE.match(p.name)):
        base = read_json(d / "topic.json")
        if not base:
            continue
        recs = {FILE_AGENT[a]: r for a in AUTHORS if (r := read_json(d / f"{a}.json", None))}
        t = dict(base)
        events = []  # (ts, agent, record) — 시간순으로 상태를 정한다
        notes = []
        for a, r in recs.items():
            notes += [{**n, "by": a} for n in r.get("notes", [])]
            # 상태는 '상태를 정한 시각' 기준으로 비교한다. 메모만 덧붙여도 옛 상태가 최신으로 바뀌지 않게.
            st_at = r.get("status_at") or r.get("assigned_at") or r.get("updated_at", "")
            events.append((st_at, a, {"status": r.get("status"), "linked_task_id": r.get("linked_task_id"),
                                      "priority": r.get("priority"), "plan": r.get("plan")}))
        for r in by_topic.get(t["id"], []):
            notes.append({"ts": r.get("ts"), "kind": r.get("kind"), "body": r.get("body", ""), "by": r.get("agent")})
            events.append((r.get("ts", ""), r.get("agent"), r))
        t["notes"] = sorted(notes, key=lambda n: n.get("ts") or "")
        t["status"] = "new"
        plans = {}
        claims = []
        for _ts, a, r in sorted(events, key=lambda e: e[0] or ""):
            if r.get("status") in STATUSES:
                t["status"] = r["status"]
            if r.get("linked_task_id"):
                t["linked_task_id"] = r["linked_task_id"]
            if r.get("priority") in ("P0", "P1", "P2", "P3"):
                t["priority"] = r["priority"]
            if r.get("plan"):
                plans[a] = r["plan"]
            if r.get("kind") == "claim":
                claims.append(a)
        lead = recs.get(LEAD) or {}
        t["assignee"] = norm_agent(lead.get("assignee") or (recs.get("dev-astra") or {}).get("assignee"))
        t["dispatch_reason"] = lead.get("dispatch_reason")
        t["dispatch_scores"] = lead.get("dispatch_scores")
        ua = assigns.get(t["id"])
        if ua and to_dt(ua.get("ts")) >= to_dt(lead.get("assigned_at")):
            t["assignee"], t["assign_by"], t["dispatch_reason"] = ua["agent"], "user", "사용자가 대시보드에서 지정"
        # 미처리(백로그): 착수 지시·담당 지정·작업 기록이 없으면 배분하지 않고 '미처리'로 둔다
        if base.get("backlog") and not t.get("assignee") and t["status"] == "new" and t["id"] not in activations:
            t["status"] = "backlog"
            if t["status"] == "new":
                t["status"] = "triage"
        planner = t["assignee"] if t["assignee"] in plans else (next(iter(plans)) if plans else None)
        if planner:
            t["plan"], t["plan_by"] = plans[planner], planner
        t["claims"] = sorted(set(claims))
        t["conflict"] = [a for a in t["claims"] if t.get("assignee") and a != t["assignee"]]
        t["updated_at"] = max([base.get("received_at", "")] + [e[0] or "" for e in events])
        t["authors"] = sorted(set(list(recs) + [r.get("agent") for r in by_topic.get(t["id"], [])]))
        t["turn"] = whose_turn(t)
        out.append(t)
    return out


def whose_turn(t: dict) -> str | None:
    if t["status"] in ("done", "parked", "backlog"):
        return None
    a = t.get("assignee")
    if not a:
        return LEAD  # 배분 대기
    if not t.get("plan"):
        return a  # 진행 베이스 작성 대기
    reviewer = LEAD if a != LEAD else "dev-astra"
    if not any(n.get("kind") == "review" and n.get("by") != a for n in t.get("notes", [])):
        return reviewer  # 교차 검토 대기
    return a


def cmd_list(args, cfg):
    node_recs = []
    if cfg.get("pc"):
        from node import collect_nodes
        pw = os.environ.get("REAL_OPS_PASSWORD") or (Path(args.password_file).read_text(encoding="utf-8").strip() if args.password_file else None)
        node_recs = [r for n in collect_nodes(cfg, pw) for r in n.get("topic_records", [])]
    topics = merged_topics(topics_dir(cfg), cfg, node_recs)
    if not topics:
        print("주제 없음")
        return
    for t in sorted(topics, key=lambda x: x["created_at"], reverse=True):
        print(f"{t['id']}  [{t['status']:<6}] {t['priority']}  담당={t.get('assignee') or '-':<13} 차례={t.get('turn') or '-':<13} {t['title']}")
        if t.get("dispatch_reason"):
            print(f"    배분 근거: {t['dispatch_reason']}")


# ---------------------------------------------------------------- 자동 배분 (허브 한 곳에서만 실행)

def load_routing(cfg) -> dict:
    p = ROOT / cfg.get("routing_file", "routing.json")
    r = read_json(p, None) or read_json(ROOT / "routing.example.json", {}) or {}
    return r


def score_agents(topic: dict, agents: list[dict], loads: dict, routing: dict) -> list[tuple[float, str, list[str]]]:
    text = " ".join(str(topic.get(k, "")) for k in ("title", "body", "kind")).lower()
    now = datetime.now(KST)
    stale = routing.get("stale_minutes", 120)
    rows = []
    pcs = routing.get("pcs") or {}
    for a in agents:
        if a.get("accept_topics") is False:
            continue
        # 운영 서버처럼 '명시적으로 걸린 일만 받는' PC: 그 PC를 가리키는 규칙이 맞았거나 사용자가 직접 고른 경우만 후보
        if (pcs.get(a["pc"]) or {}).get("only_when_matched"):
            pointed = any(r.get("prefer_pc") == a["pc"] and any(w.lower() in text for w in r.get("match", []))
                          for r in routing.get("rules", []))
            if not pointed and norm_agent(topic.get("prefer") or "") != a["id"]:
                continue
        s, why = 0.0, []
        for rule in routing.get("rules", []):
            hits = [w for w in rule.get("match", []) if w.lower() in text]
            if not hits:
                continue
            w = float(rule.get("weight", 3))
            if rule.get("prefer_pc") and a["pc"] == rule["prefer_pc"]:
                s += w; why.append(f"'{hits[0]}' → {a['pc_label']} +{w:g}")
            if rule.get("prefer_ai") and a.get("ai") == rule["prefer_ai"]:
                s += w; why.append(f"'{hits[0]}' → {a.get('ai')} +{w:g}")
        km = (routing.get("kind_map") or {}).get(topic.get("kind"), {})
        if km.get("prefer_pc") == a["pc"]:
            s += float(km.get("weight", 2)); why.append(f"유형 {topic.get('kind')} → {a['pc_label']}")
        if km.get("prefer_ai") == a.get("ai"):
            s += float(km.get("weight", 2)); why.append(f"유형 {topic.get('kind')} → {a.get('ai')}")
        pref = topic.get("prefer") or "auto"
        if norm_agent(pref) == a["id"]:
            s += 20; why.append("사용자 선호 +20")
        elif pref in ("claude", "gpt") and a.get("ai") == pref:
            s += 5; why.append(f"사용자 선호 {pref} +5")
        load = loads.get(a["id"], 0)
        if load:
            pen = load * float(routing.get("load_penalty", 1.5))
            s -= pen; why.append(f"맡은 주제 {load}건 −{pen:g}")
        seen = a.get("last_seen") or a.get("pc_synced")
        if not seen:
            s -= float(routing.get("unknown_penalty", 15)); why.append("신호 기록 없음")
        else:
            try:
                mins = (now - datetime.fromisoformat(seen.replace("Z", "+00:00"))).total_seconds() / 60
            except ValueError:
                mins = 10 ** 6
            if mins > stale:
                pen = float(routing.get("offline_penalty", 8))
                s -= pen; why.append(f"{int(mins // 60)}시간 신호 없음 −{pen:g}")
            elif a.get("last_seen"):
                s += 1; why.append("최근 직접 활동 +1")  # PC만 살아 있는 것보다 본인이 활동 중인 작업자를 우대
        if a["id"] == routing.get("default_agent", LEAD):
            s += 0.5  # 동점이면 사령탑
        rows.append((round(s, 2), a["id"], why))
    rows.sort(key=lambda r: -r[0])
    return rows


def cmd_dispatch(args, cfg):
    """분배되지 않은 새 주제를 규칙 점수로 작업자 한 명에게 배정하고 근거를 사령탑 기록에 남긴다."""
    from node import collect_nodes, all_agents  # 같은 폴더의 PC 도구
    if (cfg.get("pc") or {}).get("role") != "hub":
        sys.exit("자동 배분은 허브 PC(role=hub)에서만 실행합니다. 중복 배분을 막기 위한 규칙입니다.")
    routing = load_routing(cfg)
    if routing.get("auto") is False:
        print("자동 배분 꺼짐(routing.json auto=false)")
        return
    pw = os.environ.get("REAL_OPS_PASSWORD") or (Path(args.password_file).read_text(encoding="utf-8").strip() if args.password_file else None)
    nodes = collect_nodes(cfg, pw)
    agents = all_agents(nodes)
    if not agents:
        sys.exit("등록된 작업자가 없습니다. node.py init으로 이 PC 작업자를 등록하세요.")
    node_recs = [r for n in nodes for r in n.get("topic_records", [])]
    topics = merged_topics(topics_dir(cfg), cfg, node_recs)
    loads: dict[str, int] = {}
    for t in topics:
        if t.get("assignee") and t["status"] not in ("done", "parked"):
            loads[t["assignee"]] = loads.get(t["assignee"], 0) + 1
    labels = {a["id"]: f"{a['pc_label']} {a.get('label', a['id'])}" for a in agents}
    done = 0
    for t in topics:
        if t.get("assignee") or t["status"] in ("done", "parked", "backlog"):
            continue
        rows = score_agents(t, agents, loads, routing)
        if not rows:
            continue
        best = rows[0]
        runner = rows[1] if len(rows) > 1 else None
        reason = f"{labels[best[1]]} (점수 {best[0]:g}: {', '.join(best[2]) or '규칙 일치 없음 → 기본 담당'})"
        if runner:
            reason += f" · 차점 {labels[runner[1]]} {runner[0]:g}"
        path, rec = author_file(cfg, t["id"], "claude")
        ts = now_iso()
        rec.update({"assignee": best[1], "status": rec.get("status") if rec.get("status") not in (None, "new") else "triage",
                    "dispatch_reason": reason, "dispatch_scores": {r[1]: r[0] for r in rows}, "assigned_at": ts, "status_at": ts, "updated_at": ts})
        add_note(rec, "triage", f"자동 배분: {reason}")
        write_json(path, rec)
        loads[best[1]] = loads.get(best[1], 0) + 1
        done += 1
        print(f"{t['id']} → {best[1]} · {reason}")
    print(f"자동 배분 {done}건")


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
    """허브 PC 작업자(dev-*)에게 배정·검토 차례를 수신함 메시지로 한 번씩 알린다. 다른 PC 작업자는 그 PC의 node.py inbox가 맡는다."""
    from node import collect_nodes
    bridge = Path(cfg["bridge_dir"])
    folder = topics_dir(cfg)
    pw = os.environ.get("REAL_OPS_PASSWORD") or (Path(args.password_file).read_text(encoding="utf-8").strip() if args.password_file else None)
    node_recs = [r for n in collect_nodes(cfg, pw) for r in n.get("topic_records", [])] if cfg.get("pc") else []
    boxes = {"dev-claude": bridge / "inbox-claude", "dev-astra": bridge / "inbox-astra"}
    file_of = {"dev-claude": "claude", "dev-astra": "astra"}
    sent = 0
    for t in merged_topics(folder, cfg, node_recs):
        state_path = folder / t["id"] / ".announced.json"
        done = set(read_json(state_path, []))
        turn, short, a = t.get("turn"), t["id"], t.get("assignee")
        brief = (f"주제: {t['title']}\n유형: {t.get('kind')} · 우선순위: {t['priority']} · 선호: {t.get('prefer')}\n"
                 f"배분 근거: {t.get('dispatch_reason') or '-'}\n\n원래 메모:\n{t.get('body') or '(없음)'}")
        jobs = []
        if t["status"] == "new" and not a:
            jobs.append(("new", boxes["dev-claude"], f"DASH-TOPIC-NEW-{short}",
                         f"[대시보드 → Claude] 새 주제 (자동 배분 대기): {t['title']}",
                         {"sender": "dashboard", "recipient": "Claude lead", "kind": "topic new", "task_id": short},
                         brief + f"\n\n자동 배분이 꺼져 있으면: python topics.py triage {short} --by claude --assign <작업자ID> --note \"이유\""))
        if a in boxes and turn == a and not t.get("plan"):
            who = file_of[a]
            jobs.append((f"assign-{a}", boxes[a], f"DASH-TOPIC-ASSIGN-{short}-{a}",
                         f"[대시보드 → {who.capitalize()}] 주제 배정 — 진행 베이스 작성 요청: {t['title']}",
                         {"sender": "dashboard (허브 배분)", "recipient": who, "kind": "topic assignment; plan requested", "task_id": short},
                         brief + "\n\n요청: 목표·범위·필요한 입력·첫 단계·위험·완료 기준을 진행 베이스로 남겨주세요. 배정은 구현·설치·DB 변경 승인이 아닙니다.\n"
                         f"기록: python \"{ROOT / 'topics.py'}\" plan {short} --by {who} --goal \"...\" --scope \"...\" --first-step \"...\" --done-when \"...\""))
        if turn in boxes and turn != a and t.get("plan"):
            who = file_of[turn]
            jobs.append((f"review-{turn}", boxes[turn], f"DASH-TOPIC-REVIEW-{short}-{turn}",
                         f"[대시보드 → {who.capitalize()}] 진행 베이스 교차 검토 요청: {t['title']}",
                         {"sender": "dashboard", "recipient": who, "kind": "topic review request", "task_id": short},
                         brief + f"\n\n담당 {a}의 진행 베이스:\n" + json.dumps(t["plan"], ensure_ascii=False, indent=1) +
                         f"\n\n기록: python \"{ROOT / 'topics.py'}\" note {short} --by {who} --kind review --body \"검토 의견\""))
        for c in t.get("conflict") or []:
            jobs.append((f"conflict-{c}", boxes["dev-claude"], f"DASH-TOPIC-CONFLICT-{short}-{c}",
                         f"[대시보드 → Claude] 중복 착수 감지: {t['title']}",
                         {"sender": "dashboard", "recipient": "Claude lead", "kind": "duplicate claim", "task_id": short},
                         f"담당은 {a}인데 {c}도 착수했습니다. 한쪽을 멈추거나 담당을 바꿔주세요."))
        for key, box, mid, first, headers, body in jobs:
            if key in done:
                continue
            p = write_inbox(box, mid, first, headers, body)
            done.add(key)
            sent += 1
            print(f"작성: {p}")
        if jobs:
            write_json(state_path, sorted(done))
    print(f"새 알림 {sent}건" + (" — Astra 수신함에 쓴 경우 Astra가 쉬는 중이면 delegate.py queue로 같은 message_id를 한 번 전달하세요." if sent else ""))


# ---------------------------------------------------------------- CLI

def main():
    # 콘솔 문자표(cp949)에 없는 글자가 있어도 출력 때문에 멈추지 않게
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--password-file")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pull"); p.add_argument("--close", action="store_true", help="가져온 이슈를 닫음(gh 필요)")
    p = sub.add_parser("add-blob"); p.add_argument("blob")
    p = sub.add_parser("add"); p.add_argument("--title", required=True); p.add_argument("--body")
    p.add_argument("--kind", default="기타", choices=KINDS); p.add_argument("--priority", default="P2", choices=["P0", "P1", "P2", "P3"])
    p.add_argument("--prefer", default="auto")
    p.add_argument("--backlog", action="store_true", help="미처리(백로그)로 올림 — 착수 지시 전에는 배분하지 않음")
    p.add_argument("--source", help="출처 표기(예: 스티커 메모(개발컴))")
    p = sub.add_parser("activate", help="미처리 주제를 착수 대상으로"); p.add_argument("id")
    sub.add_parser("import-proposals", help="각 PC 작업자가 올린 메모를 미처리 주제로 가져오기(허브)")
    sub.add_parser("list")
    sub.add_parser("announce")
    sub.add_parser("dispatch", help="새 주제 자동 배분(허브 PC에서만)")
    p = sub.add_parser("triage"); p.add_argument("id"); p.add_argument("--by", required=True, choices=AUTHORS)
    p.add_argument("--assign", required=True, help="작업자 ID (예: dev-claude, server-gpt). claude/astra도 허용")
    p.add_argument("--status", choices=STATUSES); p.add_argument("--note")
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
     "triage": cmd_triage, "plan": cmd_plan, "note": cmd_note, "status": cmd_status, "comment": cmd_comment,
     "dispatch": cmd_dispatch, "activate": cmd_activate, "import-proposals": cmd_import_proposals}[args.cmd](args, cfg)


if __name__ == "__main__":
    main()
