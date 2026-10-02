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
ACTION_TYPES = ("reply", "ack", "task-state", "decide", "assign", "activate", "topic-edit", "topic-drop", "agent-lock")
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
    elif kind == "topic-edit":
        topic = str(raw.get("topic", ""))
        if not ID_RE.match(topic):
            raise ValueError("주제 수정 형식 오류")
        title = str(raw.get("title", "")).strip()[:200]
        if not title:
            raise ValueError("빈 제목")
        pri = raw.get("priority")
        kd = raw.get("kind")
        a.update(topic=topic, title=title, body=str(raw.get("body", "")).strip()[:8000],
                 priority=pri if pri in ("P0", "P1", "P2", "P3") else None, kind=kd if kd in KINDS else None)
    elif kind == "agent-lock":
        agent = norm_agent(str(raw.get("agent", "")))
        mode = raw.get("mode") or "assign"
        if not AGENT_RE.match(agent or "") or mode not in ("assign", "all"):
            raise ValueError("배정 잠금 형식 오류")
        a.update(agent=agent, lock=bool(raw.get("lock")), mode=mode)
    elif kind == "topic-drop":
        ids = raw.get("topics") or []
        if not isinstance(ids, list) or not ids or len(ids) > 300 or not all(isinstance(x, str) and ID_RE.match(x) for x in ids):
            raise ValueError("주제 삭제 목록 형식 오류")
        a.update(topics=ids, restore=bool(raw.get("restore")), note=str(raw.get("note", ""))[:1000])
    return a


def data_dir(cfg) -> Path:
    return (ROOT / cfg.get("data_dir", "data")).resolve()


def user_file(cfg) -> tuple[Path, dict]:
    path = data_dir(cfg) / "user.json"
    rec = read_json(path, None) or {"author": "user", "_rule": "이 파일은 topics.py가 사용자 요청을 받아서만 쓴다."}
    for key in ("processed_actions", "comments", "tasks", "acks", "decisions_answered", "topic_assign", "topic_activate", "topic_edit", "topic_drop"):
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
    elif a["type"] == "topic-edit":
        # 원본 topic.json은 그대로 두고, 아키텍트 수정본을 덮어 보이게 한다(되돌릴 수 있게)
        rec["topic_edit"] = [r for r in rec["topic_edit"] if r.get("topic") != a["topic"]]
        rec["topic_edit"].append({"topic": a["topic"], "title": a["title"], "body": a["body"], "priority": a["priority"],
                                  "kind": a["kind"], "ts": a["created_at"] or ts})
        result = f"주제 수정 {a['topic']}"
    elif a["type"] == "agent-lock":
        locks = rec.setdefault("agent_locks", {})
        if a["lock"]:
            locks[a["agent"]] = {"mode": a["mode"], "ts": a["created_at"] or ts}
        else:
            locks.pop(a["agent"], None)
        result = f"작업자 {a['agent']} " + (("배정 잠금" if a["mode"] == "assign" else "배정 잠금 + 자동 실행 멈춤") if a["lock"] else "잠금 풀림")
    elif a["type"] == "topic-drop":
        # 지우기 = 목록에서 빼기. 주제 폴더는 지우지 않으므로 '되살리기'로 복구된다
        drop = set(a["topics"])
        rec["topic_drop"] = [r for r in rec["topic_drop"] if r.get("topic") not in drop]
        if not a["restore"]:
            rec["topic_drop"] += [{"topic": x, "note": a["note"], "ts": a["created_at"] or ts} for x in a["topics"]]
        result = f"주제 {len(drop)}건 {'되살림' if a['restore'] else '삭제(목록에서 뺌)'}"
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


# ---------------------------------------------------------------- 단계·관문 (아키텍트 결정 2026-10-02, 정정본)
# 1 등록 → 2 진행 → 3 AI 자체 시험(자동, 관문 없음) → ★4 실게임 시험 → ★5 배포본 결정 → 6 배포본 작성(AI)
# → ★7 운영 반영 승인 → 8 운영 반영(서버컴) → ★9 완료 확정.  ★ = 아키텍트 관문(내 차례에 자동으로 올라옴).
# AI는 done을 직접 만들지 못한다. AI의 '끝냄'(state done)은 다음 단계·관문으로 넘기는 신호다. 완료(done)는 ★9에서만.
# 조사·분석 주제는 시험·배포가 없으므로 2 진행을 끝내면 바로 ★결과 확인(후속 구현 / 보류 / 완료 확정)으로 온다.
GATE_LABEL = {4: "실게임 시험", 5: "배포본 결정", 7: "운영 반영 승인", 9: "완료 확정", 40: "결과 확인"}
STAGE_STEP = {"work": (2, "진행"), "test": (3, "AI 자체 시험"), "pack": (6, "배포본 작성"), "deploy": (8, "운영 반영")}
STAGE_GATE = {"test": 4, "pack": 7, "deploy": 9}  # 그 단계에서 AI가 끝내면 열리는 관문(진행은 자체 시험으로 자동으로 넘어감)


# 시험·배포할 것이 없는 주제: 조사·분석 종류, 제목이 기획·구상·조사·연구·검토·연결 시험·메모 수집인 것
NO_TEST_RE = re.compile(r"기획|구상|조사|연구|분석|검토|여부|\[연결 시험\]|\[메모 수집\]|실사용 시험|자동실행 테스트")
NO_TEST_SAID = re.compile(r"시험할 것 없음|배포할 것 없음|바꾼 파일 없음")


def is_research(t: dict, body: str = "") -> bool:
    """True면 2 진행을 끝냈을 때 3 자체 시험을 건너뛰고 바로 ★결과 확인. AI가 끝냄 요약에 '시험할 것 없음'이라고 적어도 같다."""
    return t.get("kind") == "조사·분석" or bool(NO_TEST_RE.search(t.get("title") or "")) or bool(NO_TEST_SAID.search(body or ""))


SKIP_DONE = "즉시 완료 확정(남은 단계 건너뜀)"  # 아키텍트가 어느 관문에서든 바로 끝낼 수 있게(2026-10-03)


def gate_options(n: int, t: dict, tested: bool = False) -> list[str]:
    return {4: ["통과", "문제 있음(메모에 내용 적기 → 진행으로 되돌림)", "보류", SKIP_DONE],
            5: ["배포본 만들기", "보류", "수정", SKIP_DONE],
            7: ["서버컴에 반영", "보류", SKIP_DONE],
            9: ["완료 확정", "문제 있음(진행으로 되돌림)"],
            40: ["후속 구현 주제 만들기", "보류", "완료 확정(배포할 것 없음)"]}[n]


def gate_action(n: int, ans: dict) -> str:
    """관문 답 → 다음: work|pack|deploy|park|done|open5. 선택지 없이 메모만 오면 수정(진행으로)."""
    c = ans.get("choice") or ""
    if c.startswith("즉시 완료"):
        return "done"
    if "보류" in c:
        return "park"
    if n == 4:
        return "open5" if c.startswith("통과") else "work"
    if n == 5:
        return "pack" if "배포본" in c else "work"
    if n == 7:
        return "deploy" if "서버컴" in c else "park"
    if n == 40:
        return "done" if "완료 확정" in c else "work"
    return "done" if c.startswith("완료") else "work"


def gate_id(n: int, tid: str, ts) -> str:
    return f"G{n}-{tid[2:]}-{to_dt(ts).astimezone(KST):%Y%m%d%H%M%S}"


def run_gates(t: dict, finishes: list, answered: dict) -> dict:
    """AI의 끝냄 기록과 아키텍트 관문 답을 시간순으로 따라가 지금 단계·관문을 정한다."""
    # live: ★4 실게임(격리 서버) 시험이 열린 뒤 통과할 때까지는 개발컴 Claude 대화 세션 단계(아키텍트 결정 2026-10-02).
    # 이 동안 자동 실행기는 깨우지 않고, '문제 있음'으로 되돌아온 수정도 대화에서 고쳐 끝내면 자체 시험 없이 바로 ★4로 돌아온다.
    stage, since, gate, history, final, live = "work", None, None, [], None, False
    fin = sorted(finishes, key=lambda f: to_dt(f[0]))
    for _ in range(300):
        if gate is None:
            nxt = next((f for f in fin if since is None or to_dt(f[0]) > to_dt(since)), None)
            if not nxt:
                break
            ts, by, body = nxt
            since = ts
            if stage == "work" and not live and not is_research(t, body):
                stage = "test"  # 진행 끝 → AI 자체 시험(관문 없음)
                continue
            n = (4 if live else 40) if stage == "work" else STAGE_GATE[stage]
            gate = {"n": n, "id": gate_id(n, t["id"], ts), "opened_at": ts, "by": by, "summary": body, "from_stage": stage}
            live = live or n == 4
        ans = answered.get(gate["id"])
        if not ans and gate.get("legacy_id") and answered.get(gate["legacy_id"]):
            ans = answered[gate["legacy_id"]]
            gate["id"] = gate["legacy_id"]  # 예전 번호로 받은 답: 기록도 그 번호로(답한 것으로 보이게)
        if not ans:
            break
        act = gate_action(gate["n"], ans)
        history.append({**gate, "choice": ans.get("choice"), "note": ans.get("note"), "answered_at": ans.get("ts"), "act": act})
        since = ans.get("ts") or since
        prev, gate = gate, None
        if act in ("park", "done"):
            final, live = act, False
            break
        if act == "open5":
            live = False  # 실게임 통과 → 대화 세션 단계 끝, 다시 자동 흐름
            # ★5 번호는 ★4 번호에서 정한다(G4-… → G5-…). 대시보드가 ★4 통과 직후 ★5를 바로 띄워 이어서 답할 수 있게.
            # 예전 방식(답한 시각) 번호로 이미 받은 답도 인정한다
            gate = {"n": 5, "id": "G5-" + prev["id"][3:], "legacy_id": gate_id(5, t["id"], since), "opened_at": since, "by": prev["by"],
                    "summary": prev["summary"], "from_stage": prev["from_stage"]}
            continue
        stage = act
    return {"stage": stage, "since": since, "gate": gate, "history": history[-10:], "final": final, "live": live}


LIVE_AGENT = "dev-claude"  # 실게임(격리 서버) 시험·즉시 수정은 개발컴 Claude 대화 세션에서


def stage_owner(stage: str, t: dict, known) -> str | None:
    """단계별로 움직일 작업자: 격리 시험·배포본은 개발컴, 운영 반영은 서버컴(메인 Astra)."""
    peers = sorted(known or [])
    a = t.get("assignee") or LEAD
    if stage in ("test", "pack"):
        return a if a.startswith("dev-") else LEAD
    if stage == "deploy":
        for cand in ("server-astra", *[p for p in peers if p.startswith("server-")]):
            if cand in (known or {cand}):
                return cand
    return None



def merged_topics(folder: Path, cfg: dict | None = None, node_records: list[dict] | None = None, known: set | None = None) -> list[dict]:
    """주제 원본 + 허브 작성자 파일(claude/astra) + 다른 PC 작업자 기록 + 사용자 지정 담당을 합친다."""
    out = []
    if not folder.is_dir():
        return out
    # 검토자 짝 계산용 작업자 목록(작업자 목록을 넘기지 않은 호출에서도 같은 짝이 나오게). 인계·요청 검증은 known만 쓴다
    peers = set(known) if known else ({a.get("id") for a in (cfg or {}).get("agents", []) if a.get("id")}
                                      | {r.get("agent") for r in node_records or [] if r.get("agent")})
    assigns = user_assigns(cfg)
    urec = (read_json(data_dir(cfg) / "user.json", None) or {}) if cfg else {}
    activations = {r.get("topic") for r in urec.get("topic_activate", [])}
    edits = {r.get("topic"): r for r in urec.get("topic_edit", [])}
    drops = {r.get("topic"): r for r in urec.get("topic_drop", [])}
    gate_answers = {r.get("id"): r for r in urec.get("decisions_answered", []) if str(r.get("id", "")).startswith("G")}
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
        handoff = None
        plan_ts: dict[str, str] = {}
        requests: dict[str, dict] = {}  # 요청 ID → 요청(담당은 그대로 두고 다른 작업자에게 자료·확인을 부탁)
        finishes: list[tuple] = []  # AI의 '끝냄'(state done) — 다음 관문을 여는 신호
        for _ts, a, r in sorted(events, key=lambda e: e[0] or ""):
            if r.get("status") in STATUSES:
                t["status"] = r["status"]
                t["status_at"] = _ts  # 실행기가 '이 PC에서 더 나중에 바꾼 상태'를 판단하는 기준
                if r["status"] == "done":
                    finishes.append((_ts, a, (r.get("body") or "")[:2000]))
            if r.get("work_id") and r.get("kind") in ("work", "handoff"):
                t["work_id"] = r["work_id"]  # 주제 하나에 작업물 하나: 가장 최근 연결
            if r.get("kind") == "request" and r.get("to") and r.get("req_id"):
                requests[r["req_id"]] = {"id": r["req_id"], "from": a, "to": norm_agent(r["to"]), "ts": _ts, "body": (r.get("body") or "")[:1500], "status": "open"}
            if r.get("kind") == "reply" and r.get("req_id") in requests:
                requests[r["req_id"]].update(status="answered", reply_by=a, reply_ts=_ts, reply=(r.get("body") or "")[:1500], reply_work=r.get("work_id"))
            if r.get("kind") == "handoff" and r.get("to"):
                handoff = {"from": a, "to": norm_agent(r["to"]), "ts": _ts, "reason": (r.get("body") or "")[:300]}
            if r.get("linked_task_id"):
                t["linked_task_id"] = r["linked_task_id"]
            if r.get("priority") in ("P0", "P1", "P2", "P3"):
                t["priority"] = r["priority"]
            if r.get("plan"):
                plans[a] = r["plan"]
                plan_ts[a] = _ts
            if r.get("kind") == "claim":
                claims.append((a, _ts or ""))
        lead = recs.get(LEAD) or {}
        t["assignee"] = norm_agent(lead.get("assignee") or (recs.get("dev-astra") or {}).get("assignee"))
        t["dispatch_reason"] = lead.get("dispatch_reason")
        t["dispatch_scores"] = lead.get("dispatch_scores")
        ua = assigns.get(t["id"])
        assigned_at = lead.get("assigned_at")  # 지금 담당이 정해진 시각(중복 착수 판정 기준)
        if ua and to_dt(ua.get("ts")) >= to_dt(lead.get("assigned_at")):
            t["assignee"], t["assign_by"], t["dispatch_reason"] = ua["agent"], "user", "사용자가 대시보드에서 지정"
            assigned_at = ua.get("ts")
        # 작업자끼리 차례 넘기기(예: 서버컴 조사 → 개발컴 구현·검증 → 서버컴 적용 준비). 그 뒤에 사용자가 다시 지정하면 사용자 지정이 이긴다.
        if handoff and AGENT_RE.match(handoff["to"] or "") and (known is None or handoff["to"] in known) and to_dt(handoff["ts"]) >= to_dt(lead.get("assigned_at")) \
                and (not ua or to_dt(handoff["ts"]) >= to_dt(ua.get("ts"))):
            t["assignee"], t["assign_by"] = handoff["to"], "handoff"
            t["dispatch_reason"] = f"{handoff['from']}이(가) 넘김: {handoff['reason'] or '-'}"
            t["handoff"] = handoff
            assigned_at = handoff["ts"]
        # 미처리(백로그): 착수 지시·담당 지정·작업 기록이 없으면 배분하지 않고 '미처리'로 둔다
        if base.get("backlog") and not t.get("assignee") and t["status"] == "new" and t["id"] not in activations:
            t["status"] = "backlog"
            if t["status"] == "new":
                t["status"] = "triage"
        if finishes:  # 단계·관문: AI 끝냄은 다음 단계·관문으로, 완료는 아키텍트 ★9(조사·분석은 결과 확인)에서만
            g = run_gates(t, finishes, gate_answers)
            t["gate_history"] = g["history"]
            if g["live"] and not g["final"]:  # 실게임 시험 단계: 담당을 개발컴 Claude로 옮기고 대화 세션에서 진행
                live_to = LIVE_AGENT if (known is None or LIVE_AGENT in known) else t.get("assignee")
                if t.get("assignee") != live_to:
                    t["live_from"] = t.get("assignee")
                t["assignee"], t["live_session"] = live_to, True
            if g["gate"]:
                gt = g["gate"]
                gt.update(label=GATE_LABEL[gt["n"]], options=gate_options(gt["n"], t), step=4 if gt["n"] == 40 else gt["n"])
                t["gate"], t["status"], t["status_at"] = gt, "review_user", gt["opened_at"]
            elif g["final"]:
                t["status"], t["confirmed"] = ("done", True) if g["final"] == "done" else ("parked", False)
                t["status_at"] = g["since"]
            else:
                t["status"], t["stage"] = "active", g["stage"]
                t["status_at"] = g["since"]
                t["stage_owner"] = stage_owner(g["stage"], t, known)
            step = (t["gate"]["step"], t["gate"]["label"] + " 대기") if t.get("gate") else STAGE_STEP.get(t.get("stage") or "work")
            t["step"] = {"n": step[0], "label": step[1]} if t["status"] not in ("done", "parked") else None
        ed = edits.get(t["id"])
        if ed:  # 아키텍트 수정본이 원본·작업자 기록보다 우선
            t["title"], t["body"] = ed.get("title") or t.get("title"), ed.get("body", t.get("body"))
            if ed.get("priority"):
                t["priority"] = ed["priority"]
            if ed.get("kind"):
                t["kind"] = ed["kind"]
            t["edited_at"] = ed.get("ts")
        if t["id"] in drops:  # 삭제한 주제: 배분·실행 대상에서 빠지고 화면에서는 '삭제됨'에만 보인다
            t["status"], t["dropped_at"] = "dropped", drops[t["id"]].get("ts")
            t.pop("gate", None); t.pop("live_session", None); t["step"] = None
            t["status_at"] = max(t.get("status_at") or "", drops[t["id"]].get("ts") or "")
        planner = t["assignee"] if t["assignee"] in plans else (next(iter(plans)) if plans else None)
        if planner:
            t["plan"], t["plan_by"], t["plan_at"] = plans[planner], planner, plan_ts.get(planner)
        reqs = [q for q in requests.values() if AGENT_RE.match(q["to"] or "") and (known is None or q["to"] in known)]
        t["requests"] = sorted(reqs, key=lambda q: q["ts"] or "")[-10:]
        # 끝냄 이전에 보낸 요청은 그 단계와 함께 닫힌다(요청 받은 쪽을 계속 깨우지 않음)
        last_fin = max((to_dt(f[0]) for f in finishes), default=None)
        for q in reqs:
            if q["status"] == "open" and last_fin and to_dt(q["ts"]) <= last_fin:
                q["status"] = "closed"
        opened = [q for q in reqs if q["status"] == "open"]
        t["open_request"] = max(opened, key=lambda q: q["ts"] or "") if opened else None
        t["reviewer"] = review_partner(t.get("assignee"), peers)
        t["claims"] = sorted({a for a, _ in claims})
        # 중복 착수 = 지금 담당이 정해진 뒤에 담당이 아닌 작업자가 착수한 경우만.
        # 인계·담당 변경 전에 남은 이전 담당의 착수 기록은 충돌이 아니다(거짓 경보 방지).
        since = to_dt(assigned_at)
        # 관문 대기·완료·보류에서는 아무도 작업하지 않으므로 경보하지 않는다. 실게임 시험 이관 전 원래 담당의 착수도 충돌이 아니다
        t["conflict"] = [] if t["status"] not in ("new", "triage", "ready", "active") else \
            sorted({a for a, ts in claims if t.get("assignee") and a not in (t["assignee"], t.get("live_from")) and to_dt(ts) > since})
        t["updated_at"] = max([base.get("received_at", "")] + [e[0] or "" for e in events])
        t["authors"] = sorted(set(list(recs) + [r.get("agent") for r in by_topic.get(t["id"], [])]))
        t["turn"] = whose_turn(t)
        out.append(t)
    return out


def review_partner(a: str | None, known: set | None) -> str | None:
    """교차 검토자: 같은 PC의 다른 작업자(검토가 한 사람에게 몰리지 않게). 없으면 사령탑, 사령탑 일이면 개발컴 Astra."""
    if not a:
        return None
    pc = a.split("-", 1)[0]
    mates = sorted(x for x in (known or set()) if x != a and x.split("-", 1)[0] == pc)
    if mates:
        return mates[0]
    return LEAD if a != LEAD else "dev-astra"


def whose_turn(t: dict) -> str | None:
    if t["status"] in ("done", "parked", "backlog", "dropped", "review_user"):
        return None
    if t.get("live_session"):
        return t.get("assignee")  # 실게임 시험 단계: 개발컴 Claude 대화 세션(자동 실행기는 깨우지 않음)
    req = t.get("open_request")
    if req and req.get("to"):
        return req["to"]  # 요청받은 쪽 차례. 답(reply)하면 담당에게 돌아간다
    if t.get("stage_owner") and t.get("stage") in ("test", "pack", "deploy"):
        return t["stage_owner"]  # 격리 시험·배포본 작성은 개발컴, 운영 반영은 서버컴
    a = t.get("assignee")
    if not a:
        return LEAD  # 배분 대기
    # 내가 보낸 요청에 답이 왔는데 그 뒤로 아직 손대지 않았으면 내 차례(답을 받아 이어서 한다. 검토는 그다음)
    for q in t.get("requests") or []:
        if q.get("from") == a and q.get("status") == "answered" and \
                not any(n.get("by") == a and (n.get("ts") or "") > (q.get("reply_ts") or "") for n in t.get("notes", [])):
            return a
    ho = t.get("handoff")
    if ho and ho.get("to") == a and not (t.get("plan_by") == a and (t.get("plan_at") or "") > (ho.get("ts") or "")):
        return a  # 넘겨받은 쪽 차례. 받은 쪽이 새 진행 베이스를 쓰면 아래 교차 검토 단계로 돌아간다
    if not t.get("plan"):
        return a  # 진행 베이스 작성 대기
    reviewer = t.get("reviewer") or (LEAD if a != LEAD else "dev-astra")
    # 인계받은 쪽이 새로 쓴 진행 베이스는 그 뒤의 검토만 인정한다(넘기기 전 검토로 건너뛰지 않게)
    since = (t.get("plan_at") or "") if ho and ho.get("to") == a else ""
    if not any(n.get("kind") == "review" and n.get("by") != a and (n.get("ts") or "") >= since for n in t.get("notes", [])):
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
    text = " ".join(str(topic.get(k, "")) for k in ("title", "body")).lower()
    now = datetime.now(KST)
    stale = routing.get("stale_minutes", 120)
    rows = []
    pcs = routing.get("pcs") or {}
    for a in agents:
        if a.get("accept_topics") is False:
            continue
        # 운영 서버처럼 '명시적으로 걸린 일만 받는' PC: 그 PC를 가리키는 규칙이 맞았거나 사용자가 직접 고른 경우만 후보
        pcfg = pcs.get(a["pc"]) or {}
        if pcfg.get("only_when_matched"):
            pointed = any(r.get("prefer_pc") == a["pc"] and any(w.lower() in text for w in r.get("match", []))
                          for r in routing.get("rules", []))
            also = pcfg.get("also_accept") or {}
            title = str(topic.get("title", "")).lower()  # 기획·조사 여부는 제목으로 판단(본문의 흔한 단어로 잘못 걸리지 않게)
            readable = any(w.lower() in title for w in also.get("match", [])) and not any(w.lower() in text for w in also.get("unless", []))
            if not pointed and not readable and norm_agent(topic.get("prefer") or "") != a["id"]:
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
            s += 1000; why.append("아키텍트가 이 작업자를 지정")  # 특정 작업자를 고르면 부하 감점과 상관없이 그 작업자에게 간다
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


def rebalance(cfg, topics: list[dict], agents: list[dict], loads: dict, routing: dict, labels: dict) -> int:
    """부하 재분배: 자동 배분됐지만 담당이 아직 손대지 않은 주제(착수·진행 베이스·메모 없음, 30분 지남)를
    점수가 확실히 더 높은 한가한 작업자에게 옮긴다. 아키텍트 지정·인계·진행 중인 일은 건드리지 않는다. 한 번에 최대 3건."""
    margin = float(routing.get("rebalance_margin", 6))
    if routing.get("rebalance") is False:
        return 0
    now = datetime.now(KST)
    moved = 0
    for t in sorted(topics, key=lambda x: x.get("created_at") or ""):
        if moved >= 3:
            break
        cur = t.get("assignee")
        if not cur or t["status"] not in ("new", "triage") or t.get("assign_by") in ("user", "handoff") or t.get("plan") or t.get("open_request"):
            continue
        if any(n.get("by") == cur and n.get("kind") not in ("triage",) for n in t.get("notes", [])):
            continue  # 담당이 이미 손댔다
        if norm_agent(t.get("prefer") or "") == cur:
            continue  # 아키텍트가 고른 작업자
        path, rec = author_file(cfg, t["id"], "claude")
        if (now - to_dt(rec.get("assigned_at"))).total_seconds() < 30 * 60:
            continue
        others = {k: v for k, v in loads.items()}
        others[cur] = max(0, others.get(cur, 0) - 1)  # 이 주제를 뺀 부하로 비교
        rows = score_agents(t, agents, others, routing)
        if not rows:
            continue
        best = rows[0]
        cur_score = next((r[0] for r in rows if r[1] == cur), None)
        # 지금 담당이 후보에서 빠졌으면(배정 잠금·받을 수 없는 일) 점수 차와 상관없이 옮긴다
        if best[1] == cur or (cur_score is not None and best[0] < cur_score + margin):
            continue
        ts = now_iso()
        reason = (f"부하 재분배: {labels.get(cur, cur)}(맡은 주제 {loads.get(cur, 0)}건) → {labels.get(best[1], best[1])}"
                  f"(맡은 주제 {loads.get(best[1], 0)}건) · 점수 {best[0]:g} vs " + (f"{cur_score:g}" if cur_score is not None else "담당 불가(잠금·대상 아님)")
                  + f" ({', '.join(best[2])})")
        rec.update({"assignee": best[1], "dispatch_reason": reason, "dispatch_scores": {r[1]: r[0] for r in rows},
                    "assigned_at": ts, "status_at": ts, "updated_at": ts})
        add_note(rec, "triage", reason)
        write_json(path, rec)
        loads[cur] = max(0, loads.get(cur, 0) - 1)
        loads[best[1]] = loads.get(best[1], 0) + 1
        moved += 1
        print(f"{t['id']} {reason}")
    return moved


def agent_locks(cfg) -> dict:
    """아키텍트가 잠근 작업자: {작업자: {mode: assign|all, ts}}. assign=새 배정·재분배·인계·요청 안 받음, all=자동 실행도 멈춤."""
    return (read_json(data_dir(cfg) / "user.json", None) or {}).get("agent_locks", {}) if cfg else {}


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
    all_list = all_agents(nodes)
    if not all_list:
        sys.exit("등록된 작업자가 없습니다. node.py init으로 이 PC 작업자를 등록하세요.")
    locks = agent_locks(cfg)
    agents = [a for a in all_list if a["id"] not in locks]  # 잠긴 작업자는 새 배정·재분배 대상에서 뺀다
    node_recs = [r for n in nodes for r in n.get("topic_records", [])]
    topics = merged_topics(topics_dir(cfg), cfg, node_recs, {a["id"] for a in all_list})
    loads: dict[str, int] = {}
    for t in topics:
        if t.get("assignee") and t["status"] not in ("done", "parked", "dropped", "review_user"):
            loads[t["assignee"]] = loads.get(t["assignee"], 0) + 1
    labels = {a["id"]: f"{a['pc_label']} {a.get('label', a['id'])}" for a in all_list}
    if not agents:
        print("모든 작업자가 배정 잠금 상태 — 자동 배분 0건")
        return
    done = 0
    for t in topics:
        if t.get("assignee") or t["status"] in ("done", "parked", "backlog", "dropped", "review_user"):
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
    moved = rebalance(cfg, topics, agents, loads, routing, labels)
    print(f"자동 배분 {done}건" + (f" · 재분배 {moved}건" if moved else ""))


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
    # 허브 공지: 허브 PC 작업자 수신함에 한 번씩(다른 PC 작업자는 그 PC의 node.py inbox가 넣는다)
    notices = []
    for rel in cfg.get("curated_files", []):
        rec = read_json((ROOT / rel).resolve(), None) or {}
        notices += [n for n in rec.get("notices", []) if isinstance(n, dict) and n.get("id")]
    sent_path = data_dir(cfg) / ".notices-sent.json"
    sent_keys = set(read_json(sent_path, []))
    for n in notices:
        for aid, box in boxes.items():
            to = n.get("to") or ["all"]
            key = f"{n['id']}:{aid}"
            if key in sent_keys or not ("all" in to or aid in to):
                continue
            p = write_inbox(box, f"DASH-NOTICE-{n['id']}-{aid}", f"[허브 공지 → {aid}] {n.get('title')}",
                            {"sender": "dashboard (허브 공지)", "recipient": aid, "kind": "hub notice"},
                            (n.get("body") or "") + f"\n\n읽었으면 확인을 남긴다: python \"{ROOT / 'node.py'}\" notice-ack {n['id']} --agent {aid}")
            sent_keys.add(key)
            sent += 1
            print(f"공지 작성: {p}")
    if notices:
        write_json(sent_path, sorted(sent_keys))
    print(f"새 알림 {sent}건" + (" — Astra 수신함에 쓴 경우 Astra가 쉬는 중이면 delegate.py queue로 같은 message_id를 한 번 전달하세요." if sent else ""))


def cmd_tidy(args, cfg):
    """허브 PC 작업자 수신함의 자동 알림(DASH-*)과 아키텍트 행동 사본(USR-*) 가운데 반영이 끝난 것을 done/으로 옮긴다(지우지 않는다).
    실행기는 수신함 파일이 아니라 대시보드 데이터(차례·결정·대화)로 일하므로, 이 파일들은 처리 주체 없이 쌓여 '미처리'로 보였다."""
    from node import collect_nodes, all_agents
    pw = os.environ.get("REAL_OPS_PASSWORD") or (Path(args.password_file).read_text(encoding="utf-8").strip() if args.password_file else None)
    nodes = collect_nodes(cfg, pw) if cfg.get("pc") else []
    recs = [r for n in nodes for r in n.get("topic_records", [])]
    known = {a["id"] for a in all_agents(nodes)} or None
    topics = {t["id"]: t for t in merged_topics(topics_dir(cfg), cfg, recs, known)}
    _, urec = user_file(cfg)
    answered = {d.get("id"): d for d in urec.get("decisions_answered", [])}
    comments = {c.get("id"): c for c in urec.get("comments", [])}
    asks = {q.get("id"): q for n in nodes for q in n.get("asks") or []}
    acks: dict[str, dict] = {}
    for n in nodes:
        for nid, by in (n.get("notice_acks") or {}).items():
            acks.setdefault(nid, {}).update(by or {})
    now = datetime.now(KST)

    def acted_after(tid, who, ts) -> bool:
        t = topics.get(tid)
        if not t:
            return True  # 주제가 없어졌으면 더 할 일 없음
        if t["status"] in ("done", "parked", "dropped"):
            return True
        return any(n.get("by") == who and to_dt(n.get("ts")) > to_dt(ts) for n in t.get("notes", []))

    def settled(mid: str, head: str, age_h: float) -> str | None:
        m = re.match(r"^DASH-TOPIC-(CONFLICT|NEW|ASSIGN|REVIEW)-(T-\d{8}-[a-z0-9]+)(?:-([a-z0-9-]+))?$", mid)
        if m:
            kind, tid, who = m.groups()
            t = topics.get(tid)
            if not t or t["status"] in ("done", "parked", "dropped"):
                return "주제 종료"
            if kind == "CONFLICT" and who not in (t.get("conflict") or []):
                return "중복 착수 해소"
            if kind == "NEW" and (t.get("assignee") or t["status"] != "new"):
                return "배분됨"
            if kind == "ASSIGN" and (t.get("assignee") != who or t.get("plan")):
                return "착수·진행 베이스 작성됨"
            if kind == "REVIEW" and t.get("turn") != who:
                return "검토 끝남"
        m = re.match(r"^DASH-ASSIGN-(T-\d{8}-[a-z0-9]+)-([a-z0-9-]+)$", mid)
        if m:
            t = topics.get(m.group(1))
            if not t or t["status"] in ("done", "parked", "dropped") or t.get("assignee") != m.group(2) or t.get("plan"):
                return "착수·진행 베이스 작성됨"
        m = re.match(r"^DASH-NOTICE-(N-[A-Za-z0-9-]+?)-((?:dev|server|[a-z0-9]+)-[a-z0-9]+)$", mid)
        if m and (acks.get(m.group(1), {}).get(m.group(2)) or {}).get("via") == "session":
            return "공지 확인됨"  # 대화 세션이 직접 확인한 경우만(실행기 반영만으로는 수신함 메시지를 남겨 둔다)
        if mid.startswith(("USR-STATE-", "USR-ASSIGN-")):
            return "대시보드에서 이미 적용됨(사본)"
        if mid.startswith("USR-DECIDE-"):
            did = (re.search(r"^in_reply_to:\s*(\S+)", head, re.M) or [None, ""])[1]
            d, q = answered.get(did), asks.get(did)
            if d and q and q.get("topic") and acted_after(q["topic"], q.get("agent"), d.get("ts")):
                return "질문한 작업자가 결정 반영"
        if mid.startswith("USR-REPLY-"):
            c = comments.get(mid[len("USR-REPLY-"):]) or {}
            tg = c.get("target") or {}
            if tg.get("kind") == "topic" and acted_after(tg.get("id"), c.get("to"), c.get("ts")):
                return "받는 작업자가 답 반영"
        if mid.startswith(("USR-", "DASH-")) and age_h > 48:
            return "48시간 지난 자동 알림·사본"
        return None

    moved: dict[str, int] = {}
    for a in cfg.get("agents", []):
        box = Path(a.get("inbox") or "")
        if not a.get("inbox") or not box.is_dir():
            continue
        for p in sorted(box.glob("*.md")):
            try:
                head = "\n".join(p.read_text(encoding="utf-8-sig", errors="replace").splitlines()[:15])
            except OSError:
                continue
            mid = (re.search(r"^message_id:\s*(\S+)", head, re.M) or [None, ""])[1]
            if not mid.startswith(("USR-", "DASH-")):
                continue  # AI가 보낸 실제 보고는 건드리지 않는다
            why = settled(mid, head, (now.timestamp() - p.stat().st_mtime) / 3600)
            if not why:
                continue
            if getattr(args, "dry_run", False):
                print(f"  [옮길 예정] {p.name} — {why}")
                moved[why] = moved.get(why, 0) + 1
                continue
            done = box / "done"
            done.mkdir(exist_ok=True)
            dst, k = done / p.name, 1
            while dst.exists():
                dst, k = done / f"{p.stem}-{k}{p.suffix}", k + 1
            try:
                p.replace(dst)
                moved[why] = moved.get(why, 0) + 1
            except OSError:
                pass
    total = sum(moved.values())
    print(f"수신함 정리 {total}건" + (": " + ", ".join(f"{k} {v}" for k, v in moved.items()) if total else ""))


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
    p = sub.add_parser("tidy", help="자동 알림(DASH-*)·아키텍트 행동 사본(USR-*) 중 반영이 끝난 것을 수신함 done/으로 옮김")
    p.add_argument("--dry-run", action="store_true")
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
     "dispatch": cmd_dispatch, "activate": cmd_activate, "import-proposals": cmd_import_proposals, "tidy": cmd_tidy}[args.cmd](args, cfg)


if __name__ == "__main__":
    main()
