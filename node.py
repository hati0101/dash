"""PC(작업 노드) 도구 — 각 PC의 각 AI(작업자)가 지금 무엇을 하는지 알리고, 배정받은 주제를 처리한다.

작업자 = PC + AI. 예: dev-claude(개발컴 Claude), server-gpt(서버컴 GPT).
배분은 허브(개발컴) 한 곳만 한다. 노드(서버컴 등)는 자기 작업자에게 배정된 것만 처리한다.

기록 파일(평문, 커밋 안 함): node-data/records.json   → `pack`이 docs/nodes/<pc>.enc.json으로 암호화해 올린다.

  python node.py init --pc server --label 서버컴 --role node --agent "server-claude|claude|Claude|C:/수신폴더"
  python node.py status --agent server-claude --project "맵서버 패킷 정리" --task PACKET-0001     지금 하는 일 알리기
  python node.py status --agent server-claude --idle                                              쉬는 중
  python node.py mine                                                                             내 PC 작업자에게 배정된 주제 보기
  python node.py claim <주제ID> --agent server-claude                                              착수(중복 착수는 대시보드에 충돌로 표시)
  python node.py plan <주제ID> --agent server-claude --goal ".." --scope ".." --first-step ".." --done-when ".."
  python node.py note <주제ID> --agent server-claude --kind memo|review|question|answer --body ".."
  python node.py state <주제ID> --agent server-claude --status active|done|parked [--task 작업ID]
  python node.py handoff <주제ID> --agent server-claude --to dev-claude --note "격리 검증 요청" [--work FT-…]   다른 작업자(다른 PC)에게 차례 넘기기
  python node.py hold <주제ID> --agent server-claude [--minutes 120] --note "대화 세션에서 직접 처리"     자동 실행기가 이 주제를 건드리지 않게
  python node.py release <주제ID> --agent server-claude
  python node.py inbox      배정·답을 각 작업자 수신 폴더에 메시지로 넣기(한 번씩만)
  python node.py pack       기록을 암호화해 docs/nodes/<pc>.enc.json으로 쓰기
  긴 글은 --body-file <파일>로 넘긴다(PowerShell이 따옴표 든 인자를 자르는 문제 방지).
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
AGENT_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,30}$")
TOPIC_RE = re.compile(r"^T-\d{8}-[a-z0-9]{3,8}$")
REF_RE = re.compile(r"^[A-Za-z0-9_.:\-]{1,200}$")
STATUSES = ("triage", "ready", "active", "done", "parked")
KINDS = ("claim", "plan", "memo", "review", "question", "answer", "status", "work", "handoff", "request", "reply")
WORK_ID_RE = re.compile(r"^[A-Z]{2,6}-\d{8}-[A-Za-z0-9]{1,12}$")


def now_iso() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def cfg_path() -> Path:
    return Path(os.environ.get("REAL_OPS_CONFIG") or ROOT / "config.local.json")


def load_cfg() -> dict:
    p = cfg_path()
    return json.loads(p.read_text(encoding="utf-8-sig")) if p.exists() else {}


def read_json(path: Path, default):
    import time
    for i in range(20):
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except FileNotFoundError:
            return default
        except PermissionError:  # 교체 중인 순간
            time.sleep(0.1)
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    import time
    for i in range(40):  # Windows: 다른 프로세스가 읽는 순간에는 교체가 거부된다(WinError 5/32) → 최대 약 8초 재시도
        try:
            tmp.replace(path)
            return
        except PermissionError:
            time.sleep(0.2)
    tmp.replace(path)


def node_dir(cfg) -> Path:
    return (ROOT / cfg.get("node_data_dir", "node-data")).resolve()


def records_path(cfg) -> Path:
    return node_dir(cfg) / "records.json"


class records_lock:
    """기록 파일을 고치는 동안 다른 프로세스(작업자별 실행기·대화 세션)가 동시에 고치지 못하게 잠근다.
    읽고-고치고-쓰는 사이에 다른 쪽 기록이 사라지는 것을 막는다. 2분 넘은 잠금은 죽은 것으로 보고 치운다."""
    def __init__(self, cfg):
        self.path = node_dir(cfg) / "records.lock"

    def __enter__(self):
        import time
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.time() + 60
        while True:
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > 120:
                        self.path.unlink(missing_ok=True)
                        continue
                except FileNotFoundError:
                    continue
                if time.time() > deadline:
                    sys.exit("기록 파일 잠금을 1분 동안 얻지 못했습니다(다른 실행이 붙잡고 있음).")
                time.sleep(0.2)

    def __exit__(self, *exc):
        self.path.unlink(missing_ok=True)
        return False


def update_records(cfg, fn):
    """잠근 채로 기록을 읽어 fn(rec)으로 고치고 저장한다. fn의 반환값을 돌려준다."""
    with records_lock(cfg):
        rec = load_records(cfg)
        out = fn(rec)
        rec["updated_at"] = now_iso()
        write_json(records_path(cfg), rec)
        return out


def body_arg(args) -> str:
    """--body 또는 --body-file(UTF-8)에서 본문을 읽는다."""
    f = getattr(args, "body_file", None)
    if f:
        return Path(f).read_text(encoding="utf-8-sig").strip()
    return (getattr(args, "body", None) or "").strip()


def pc_info(cfg) -> dict:
    pc = cfg.get("pc") or {}
    if not pc.get("id"):
        sys.exit("이 PC 설정이 없습니다. 먼저 python node.py init ... 을 실행하세요.")
    return pc


def my_agents(cfg) -> dict:
    return {a["id"]: a for a in cfg.get("agents", []) if a.get("id")}


def load_records(cfg) -> dict:
    pc = pc_info(cfg)
    rec = read_json(records_path(cfg), None) or {}
    rec.update({"pc": pc["id"], "label": pc.get("label", pc["id"]), "role": pc.get("role", "node")})
    rec.setdefault("topic_records", [])
    rec.setdefault("proposals", [])
    rec.setdefault("runs", [])     # 자동 실행기 실행 이력(시각·결과·실패 사유)
    rec.setdefault("holds", {})    # 대화 세션이 잡은 주제(실행기가 건드리지 않음)
    rec.setdefault("notice_acks", {})  # 허브 공지 확인: {공지ID: {작업자: {ts, via}}}
    # 설정에서 빠진 작업자는 현황에서도 뺀다(이름을 바꾸거나 정리한 경우)
    rec["agents"] = {k: v for k, v in (rec.get("agents") or {}).items() if k in my_agents(cfg)}
    for aid, a in my_agents(cfg).items():
        slot = rec["agents"].setdefault(aid, {})
        slot.update({"id": aid, "ai": a.get("ai", ""), "label": a.get("label", aid)})
    return rec


def check_agent(cfg, aid: str):
    if aid not in my_agents(cfg):
        sys.exit(f"이 PC에 등록되지 않은 작업자입니다: {aid} (등록: {', '.join(my_agents(cfg)) or '없음'})")


def password(args) -> str:
    if getattr(args, "password_file", None):
        return Path(args.password_file).read_text(encoding="utf-8").strip()
    if os.environ.get("REAL_OPS_PASSWORD"):
        return os.environ["REAL_OPS_PASSWORD"]
    return getpass.getpass("대시보드 비밀번호: ")


def main_file(cfg) -> Path:
    return ROOT / cfg.get("output", "docs/data.enc.json")


def nodes_dir(cfg) -> Path:
    return (ROOT / cfg.get("nodes_dir", "docs/nodes")).resolve()


def decrypt_main(cfg, pw: str) -> dict:
    res = subprocess.run(["node", str(ROOT / "encrypt.mjs"), "decrypt", str(main_file(cfg))],
                         env=dict(os.environ, REAL_OPS_PASSWORD=pw), capture_output=True)
    if res.returncode != 0:
        sys.exit("게시본을 열지 못했습니다(비밀번호 또는 파일 확인): " + res.stderr.decode("utf-8", "replace").strip())
    return json.loads(res.stdout.decode("utf-8"))


# ---------------------------------------------------------------- 설정

def cmd_init(args, cfg):
    if not AGENT_RE.match(args.pc):
        sys.exit("--pc는 영문 소문자·숫자·- 로 (예: server)")
    agents = []
    for spec in args.agent or []:
        parts = spec.split("|")
        if len(parts) < 3:
            sys.exit('--agent 형식: "작업자ID|ai|표시이름|수신폴더(선택)"')
        aid, ai, label = parts[0].strip(), parts[1].strip(), parts[2].strip()
        if not AGENT_RE.match(aid) or not aid.startswith(args.pc + "-"):
            sys.exit(f"작업자 ID는 '{args.pc}-'로 시작해야 합니다: {aid}")
        agents.append({"id": aid, "ai": ai, "label": label, "inbox": parts[3].strip() if len(parts) > 3 and parts[3].strip() else None})
    cfg["pc"] = {"id": args.pc, "label": args.label, "role": args.role}
    if agents:
        cfg["agents"] = agents
    cfg.setdefault("output", "docs/data.enc.json")
    cfg.setdefault("node_data_dir", "node-data")
    write_json(cfg_path(), cfg)
    print(f"이 PC: {args.label}({args.pc}, {args.role}) · 작업자 {', '.join(a['id'] for a in cfg.get('agents', [])) or '없음'}")


# ---------------------------------------------------------------- 작업자 기록

def cmd_status(args, cfg):
    check_agent(cfg, args.agent)
    if not args.idle and not args.project:
        sys.exit("--project(지금 하는 일) 또는 --idle 중 하나는 필요합니다.")

    def fn(rec):
        slot = rec["agents"][args.agent]
        ts = now_iso()
        if args.idle:
            slot["current"] = None
        else:
            prev = slot.get("current") or {}
            same = prev.get("project") == args.project
            slot["current"] = {"project": args.project[:200], "task": args.task, "topic": args.topic,
                               "note": (args.note or "")[:500], "since": prev.get("since") if same else ts}
        slot["last_seen"] = ts
    update_records(cfg, fn)
    print(f"{args.agent}: " + ("쉬는 중" if args.idle else f"{args.project}"))


def add_topic_record(cfg, topic: str, agent: str, kind: str, **fields):
    if not TOPIC_RE.match(topic):
        sys.exit(f"주제 ID 형식이 아닙니다: {topic}")
    check_agent(cfg, agent)

    def fn(rec):
        ts = now_iso()
        rec["topic_records"].append({"topic": topic, "agent": agent, "kind": kind, "ts": ts,
                                     **{k: v for k, v in fields.items() if v not in (None, "", [])}})
        rec["topic_records"] = rec["topic_records"][-3000:]
        rec["agents"][agent]["last_seen"] = ts
    update_records(cfg, fn)


# ---------------------------------------------------------------- 실행 이력·상태(자동 실행기가 쓴다)

def start_run(cfg, agent: str, topic: str | None, kind: str, mode: str, reason: str) -> str:
    """실행 시작을 남긴다(대시보드에 '실행 중'으로 보인다). 실행 ID를 돌려준다."""
    import secrets
    rid = f"R-{datetime.now(KST):%Y%m%d%H%M%S}-{secrets.token_hex(2)}"

    def fn(rec):
        rec["runs"].append({"id": rid, "agent": agent, "topic": topic, "kind": kind, "mode": mode,
                            "reason": reason[:300], "started": now_iso(), "result": "running"})
        rec["runs"] = rec["runs"][-300:]
        rec["agents"][agent]["last_seen"] = now_iso()
    update_records(cfg, fn)
    return rid


def end_run(cfg, rid: str, **fields):
    """실행 결과: result=ok|partial|fail|skipped, error, error_class, needs_user, summary, actions, work_id, failed."""
    def fn(rec):
        for r in reversed(rec["runs"]):
            if r.get("id") == rid:
                r.update({k: v for k, v in fields.items() if v is not None})
                r["ended"] = now_iso()
                break
    update_records(cfg, fn)


def set_health(cfg, agent: str, state: str, message: str = "", needs_user: bool = False, fix: str = ""):
    """작업자 실행 상태: ok | auth | tool | timeout | error. needs_user면 대시보드 '할 일'에 올라간다."""
    def fn(rec):
        prev = rec["agents"][agent].get("health") or {}
        same = prev.get("state") == state
        rec["agents"][agent]["health"] = {"state": state, "message": message[:400], "needs_user": needs_user, "fix": fix[:400],
                                          "at": now_iso(), "since": prev.get("since") if same and prev.get("since") else now_iso()}
    update_records(cfg, fn)


def active_holds(cfg) -> dict:
    """지금 유효한 잡기(대화 세션이 처리 중인 주제)."""
    holds = load_records(cfg).get("holds") or {}
    now = datetime.now(KST)
    return {k: v for k, v in holds.items() if v.get("until") and datetime.fromisoformat(v["until"]) > now}


def cmd_hold(args, cfg):
    check_agent(cfg, args.agent)
    if not TOPIC_RE.match(args.id):
        sys.exit(f"주제 ID 형식이 아닙니다: {args.id}")
    minutes = max(5, min(int(args.minutes or 120), 24 * 60))
    until = (datetime.now(KST) + timedelta(minutes=minutes)).isoformat(timespec="seconds")

    def fn(rec):
        rec["holds"][args.id] = {"agent": args.agent, "ts": now_iso(), "until": until, "note": (args.note or "대화 세션에서 직접 처리")[:300]}
    update_records(cfg, fn)
    print(f"{args.id}: {args.agent} 대화 세션이 잡음 — {until}까지 자동 실행기가 건드리지 않습니다(끝나면 release)")


def cmd_release(args, cfg):
    def fn(rec):
        return rec["holds"].pop(args.id, None)
    print(f"{args.id}: 잡기 풀림" if update_records(cfg, fn) else f"{args.id}: 잡은 기록 없음")


def cmd_handoff(args, cfg):
    if not re.match(r"^[a-z0-9]+-[a-z0-9-]+$", args.to or "") or args.to == args.agent:
        sys.exit("--to는 작업자 ID (예: dev-claude)")
    if args.work and not WORK_ID_RE.match(args.work):
        sys.exit("--work 형식 오류 (예: FT-20261002-abc123)")
    add_topic_record(cfg, args.id, args.agent, "handoff", to=args.to, work_id=args.work, body=body_arg(args) or f"{args.to}에게 넘김")
    print(f"{args.id}: {args.agent} → {args.to} 차례 넘김")


def notice_for(n: dict, agent: str) -> bool:
    to = n.get("to") or ["all"]
    return "all" in to or agent in to


def ack_notice(cfg, nid: str, agent: str, via: str):
    """허브 공지를 확인했다고 남긴다. via=session(대화 세션이 읽음) | runner(실행기가 지시문에 넣어 반영). 세션 확인이 더 강하다."""
    def fn(rec):
        slot = rec["notice_acks"].setdefault(nid, {})
        if slot.get(agent, {}).get("via") == "session" and via != "session":
            return
        slot[agent] = {"ts": now_iso(), "via": via}
    update_records(cfg, fn)


def cmd_notice_ack(args, cfg):
    check_agent(cfg, args.agent)
    if not re.match(r"^N-[A-Za-z0-9-]{3,40}$", args.id):
        sys.exit("공지 ID 형식 오류 (예: N-20261002-automation)")
    ack_notice(cfg, args.id, args.agent, "session")
    print(f"{args.id}: {args.agent} 확인 — 다음 동기화 때 대시보드에 표시됩니다")


def new_req_id(agent: str) -> str:
    import secrets
    return f"Q-{datetime.now(KST):%Y%m%d%H%M%S}-{secrets.token_hex(2)}"


def cmd_request(args, cfg):
    """담당은 그대로 두고 다른 작업자에게 자료·확인을 요청한다. 답(reply)이 오면 차례가 나에게 돌아온다."""
    if not re.match(r"^[a-z0-9]+-[a-z0-9-]+$", args.to or "") or args.to == args.agent:
        sys.exit("--to는 다른 작업자 ID (예: server-astra)")
    body = body_arg(args)
    if not body:
        sys.exit("--body 또는 --body-file로 무엇이 필요한지 적어 주세요.")
    rid = new_req_id(args.agent)
    add_topic_record(cfg, args.id, args.agent, "request", to=args.to, req_id=rid, body=body[:4000])
    print(f"{args.id}: {args.agent} → {args.to} 요청 {rid} — 답이 오면 {args.agent} 차례로 돌아옵니다")


def cmd_reply(args, cfg):
    if not re.match(r"^Q-\d{14}-[0-9a-f]{4}$", args.req or ""):
        sys.exit("--req 형식 오류 (예: Q-20261002164500-ab12)")
    body = body_arg(args)
    if not body:
        sys.exit("--body 또는 --body-file이 필요합니다.")
    if args.work and not WORK_ID_RE.match(args.work):
        sys.exit("--work 형식 오류")
    add_topic_record(cfg, args.id, args.agent, "reply", req_id=args.req, work_id=args.work, body=body[:6000])
    print(f"{args.id}: {args.agent} 요청 {args.req}에 답함 — 요청한 작업자 차례로 돌아갑니다")


def cmd_link_work(args, cfg):
    if not WORK_ID_RE.match(args.work):
        sys.exit("--work 형식 오류 (예: FT-20261002-abc123)")
    add_topic_record(cfg, args.id, args.agent, "work", work_id=args.work, body=f"작업물 연결: {args.work}")
    print(f"{args.id}: 작업물 {args.work} 연결")


def cmd_propose(args, cfg):
    """이 PC에서 모은 아이디어·이슈 메모를 한 건씩 올린다. 허브가 '미처리' 주제로 가져간다(배분은 착수 지시 후)."""
    import secrets
    check_agent(cfg, args.agent)
    title = args.title.strip()[:200]
    if not title:
        sys.exit("--title이 비어 있습니다.")
    pid = add_proposal(cfg, args.agent, title, body_arg(args), args.kind, args.priority, args.origin or "")
    print(f"메모 올림 {pid}: {title} — 다음 동기화 때 허브가 미처리 주제로 가져갑니다" if pid else f"이미 올린 메모입니다: {title}")


def add_ask(cfg, agent: str, topic: str | None, question: str, options: list[str]) -> str:
    """아키텍트 승인·결정이 필요할 때 질문을 남긴다. 허브가 대시보드 '결정이 필요한 문제'에 올린다."""
    import secrets
    check_agent(cfg, agent)
    q = question.strip()[:1500]
    if not q:
        sys.exit("질문이 비어 있습니다.")
    aid = f"DN-{agent}-{datetime.now(KST):%Y%m%d}-{secrets.token_hex(3)}"

    def fn(rec):
        rec.setdefault("asks", [])
        rec["asks"].append({"id": aid, "agent": agent, "topic": topic if topic and TOPIC_RE.match(topic) else None,
                            "question": q, "options": [str(o)[:200] for o in (options or [])][:6], "ts": now_iso()})
        rec["asks"] = rec["asks"][-500:]
        rec["agents"][agent]["last_seen"] = now_iso()
    update_records(cfg, fn)
    return aid


def add_proposal(cfg, agent: str, title: str, body: str, kind: str = "기타", priority: str = "P2", origin: str = "") -> str | None:
    import secrets
    check_agent(cfg, agent)
    title = (title or "").strip()[:200]
    if not title:
        return None
    pid = f"P-{pc_info(cfg)['id']}-{datetime.now(KST):%Y%m%d}-{secrets.token_hex(3)}"

    def fn(rec):
        if any(p.get("title") == title and p.get("agent") == agent for p in rec["proposals"]):
            return None
        rec["proposals"].append({"id": pid, "agent": agent, "title": title, "body": (body or "").strip()[:8000],
                                 "kind": kind if kind in ("기능·개선", "버그", "조사·분석", "디자인", "운영·도구", "기타") else "기타",
                                 "priority": priority if priority in ("P0", "P1", "P2", "P3") else "P2",
                                 "origin": (origin or "")[:300], "ts": now_iso()})
        rec["proposals"] = rec["proposals"][-2000:]
        return pid
    return update_records(cfg, fn)


def cmd_ask(args, cfg):
    q = Path(args.question_file).read_text(encoding="utf-8-sig") if args.question_file else (args.question or "")
    aid = add_ask(cfg, args.agent, args.topic, q, [o for o in (args.option or []) if o])
    print(f"질문 남김 {aid} — 다음 동기화 때 대시보드 '결정이 필요한 문제'에 올라갑니다")


def cmd_claim(args, cfg):
    add_topic_record(cfg, args.id, args.agent, "claim", status="active", body=args.note or "착수")
    print(f"{args.id}: {args.agent} 착수")


def cmd_plan(args, cfg):
    plan = {k: v for k, v in {"goal": args.goal, "scope": args.scope, "inputs": args.input, "first_steps": args.first_step,
                              "risks": args.risk, "done_when": args.done_when}.items() if v}
    if not plan:
        sys.exit("진행 베이스 항목(--goal 등)이 하나 이상 필요합니다.")
    # 상태는 지정했을 때만 바꾼다(착수 후 진행 베이스를 써도 '진행 중'이 유지되게)
    add_topic_record(cfg, args.id, args.agent, "plan", plan=plan, status=args.status, body=args.note or "진행 베이스 작성")
    print(f"{args.id}: {args.agent} 진행 베이스 기록")


def cmd_note(args, cfg):
    body = body_arg(args)
    if not body:
        sys.exit("--body 또는 --body-file이 필요합니다.")
    add_topic_record(cfg, args.id, args.agent, args.kind, body=body[:6000])
    print(f"{args.id}: {args.agent} {args.kind} 기록")


def cmd_state(args, cfg):
    if args.task and not REF_RE.match(args.task):
        sys.exit("--task 형식 오류")
    add_topic_record(cfg, args.id, args.agent, "status", status=args.status, linked_task_id=args.task,
                     body=args.note or f"상태 {args.status}")
    print(f"{args.id}: {args.agent} 상태 {args.status}")


# ---------------------------------------------------------------- 배정 확인·수신함

def assigned_to_me(cfg, data: dict) -> list[dict]:
    mine = set(my_agents(cfg))
    return [t for t in data.get("topics", []) if t.get("assignee") in mine and t.get("status") not in ("done", "parked", "dropped")]


def cmd_mine(args, cfg):
    data = decrypt_main(cfg, password(args))
    rows = assigned_to_me(cfg, data)
    if not rows:
        print("이 PC 작업자에게 배정된 진행 중 주제가 없습니다.")
    for t in rows:
        print(f"{t['id']}  [{t.get('status')}] {t.get('priority', '')}  담당={t['assignee']}  {t['title']}")
        if t.get("dispatch_reason"):
            print(f"    배분 근거: {t['dispatch_reason']}")


def write_message(folder: Path, mid: str, first: str, headers: dict, body: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{datetime.now(KST):%Y%m%d-%H%M%S}-{mid}.md"
    lines = [first, f"message_id: {mid}"] + [f"{k}: {v}" for k, v in headers.items() if v] + ["", body.strip(), ""]
    tmp = path.with_suffix(".tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    tmp.replace(path)
    return path


def cmd_inbox(args, cfg):
    """허브가 배분한 주제·사용자 답을 이 PC 작업자의 수신 폴더에 한 번씩 넣는다."""
    pc = pc_info(cfg)
    data = decrypt_main(cfg, password(args))
    agents = my_agents(cfg)
    done_path = node_dir(cfg) / "inbox-done.json"
    done = set(read_json(done_path, []))
    sent = 0
    me = Path(__file__).resolve()
    pc_note = ((data.get("meta", {}).get("routing", {}).get("pcs") or {}).get(pc["id"]) or {}).get("note")
    for t in assigned_to_me(cfg, data):
        a = agents[t["assignee"]]
        key = f"assign:{t['id']}:{t['assignee']}"
        if key in done or not a.get("inbox"):
            continue
        body = (f"주제: {t['title']}\n유형: {t.get('kind')} · 우선순위: {t.get('priority')}\n"
                f"배분 근거: {t.get('dispatch_reason') or '사용자 지정'}\n\n원래 메모:\n{t.get('body') or '(없음)'}\n\n"
                "처리 순서:\n"
                f"1. 착수: python \"{me}\" claim {t['id']} --agent {a['id']}\n"
                f"2. 진행 베이스: python \"{me}\" plan {t['id']} --agent {a['id']} --goal \"..\" --scope \"..\" --first-step \"..\" --done-when \"..\"\n"
                f"3. 지금 하는 일 알리기: python \"{me}\" status --agent {a['id']} --project \"..\" --topic {t['id']}\n"
                f"4. 끝나면: python \"{me}\" state {t['id']} --agent {a['id']} --status done\n\n"
                "구현·설치·DB 변경·운영 영향 작업은 이 PC의 기존 승인 규칙을 따른다. 배정은 승인이 아니다."
                + (f"\n\n[이 PC 규칙] {pc_note}" if pc_note else ""))
        p = write_message(Path(a["inbox"]), f"DASH-ASSIGN-{t['id']}-{a['id']}", f"[대시보드 → {a['label']}] 주제 배정: {t['title']}",
                          {"sender": "dashboard (허브 배분)", "recipient": a["id"], "kind": "topic assignment", "task_id": t["id"]}, body)
        done.add(key)
        sent += 1
        print(f"배정 전달: {p}")
    for c in data.get("comments", []):
        to = c.get("to")
        key = f"reply:{c.get('id')}"
        if to in agents and key not in done and agents[to].get("inbox") and (c.get("_author") == "user"):
            t = c.get("target") or {}
            p = write_message(Path(agents[to]["inbox"]), f"USR-REPLY-{c.get('id')}", f"[사용자 → {agents[to]['label']}] 대시보드 답: {t.get('title') or t.get('id')}",
                              {"sender": "user (대시보드)", "recipient": to, "kind": "user reply via dashboard",
                               "target": f"{t.get('kind')}:{t.get('id')}"}, c.get("body", ""))
            done.add(key)
            sent += 1
            print(f"답 전달: {p}")
    # 허브 공지: 이 PC 작업자 수신 폴더에 한 번씩 넣는다(확인 명령 포함)
    for n in data.get("notices", []):
        for aid, a in agents.items():
            key = f"notice:{n.get('id')}:{aid}"
            if key in done or not a.get("inbox") or not notice_for(n, aid):
                continue
            body = (n.get("body") or "") + (f"\n\n읽었으면 확인을 남긴다: python \"{me}\" notice-ack {n['id']} --agent {aid}"
                                            "\n(대시보드 작업자 화면의 '허브 공지'에 누가 확인했는지 보인다)")
            p = write_message(Path(a["inbox"]), f"DASH-NOTICE-{n['id']}-{aid}", f"[허브 공지 → {a['label']}] {n.get('title')}",
                              {"sender": "dashboard (허브 공지)", "recipient": aid, "kind": "hub notice"}, body)
            done.add(key)
            sent += 1
            print(f"공지 전달: {p}")
    write_json(done_path, sorted(done))
    print(f"{pc['label']}: 새 전달 {sent}건")


def cmd_pack(args, cfg):
    """기록을 암호화해 docs/nodes/<pc>.enc.json에 쓴다. 로컬 경로(수신 폴더)는 빼고 올린다."""
    import hashlib
    pc = pc_info(cfg)
    rec = load_records(cfg)
    public = json.loads(json.dumps(rec))
    for a in public["agents"].values():
        a.pop("inbox", None)
    public.pop("synced_at", None)
    digest = hashlib.sha256(json.dumps(public, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    marker = node_dir(cfg) / "last-pack.json"
    last = read_json(marker, {})
    if getattr(args, "if_changed", False) and last.get("digest") == digest and last.get("at"):
        age = (datetime.now(KST) - datetime.fromisoformat(last["at"])).total_seconds() / 60
        if age < 60:
            print("변경 없음 — 올리지 않습니다")
            sys.exit(10)
    public["synced_at"] = now_iso()
    out = nodes_dir(cfg) / f"{pc['id']}.enc.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    main = main_file(cfg)
    if not main.exists():
        sys.exit("게시본(docs/data.enc.json)이 없습니다. 먼저 git pull 하세요.")
    res = subprocess.run(["node", str(ROOT / "encrypt.mjs"), "encrypt", str(out), "--salt-from", str(main)],
                         input=json.dumps(public, ensure_ascii=False).encode("utf-8"),
                         env=dict(os.environ, REAL_OPS_PASSWORD=password(args)), capture_output=True)
    if res.returncode != 0:
        sys.exit("암호화 실패: " + res.stderr.decode("utf-8", "replace"))
    # 같은 비밀번호로 다시 열리는지 바로 확인한다(다른 비밀번호로 올리는 사고 방지)
    chk = subprocess.run(["node", str(ROOT / "encrypt.mjs"), "decrypt", str(out)],
                         env=dict(os.environ, REAL_OPS_PASSWORD=password(args)), capture_output=True)
    if chk.returncode != 0:
        out.unlink(missing_ok=True)
        sys.exit("검증 실패: 방금 만든 파일을 열 수 없어 지웠습니다.")
    write_json(marker, {"digest": digest, "at": public["synced_at"]})
    print(f"암호화 완료: {out} · 작업자 {len(public['agents'])} · 주제 기록 {len(public['topic_records'])}")


# ---------------------------------------------------------------- 허브용: 모든 PC 기록 모으기 (build.py·topics.py가 사용)

def collect_nodes(cfg: dict, pw: str | None) -> list[dict]:
    """이 PC의 기록(평문)과 다른 PC가 올린 docs/nodes/*.enc.json(복호화)을 모은다. 실패한 PC는 error로 표시."""
    out = []
    mine = (cfg.get("pc") or {}).get("id")
    if mine:
        rec = load_records(cfg)
        for a in rec["agents"].values():
            a.pop("inbox", None)
        rec["source"] = "이 PC"
        out.append(rec)
    folder = nodes_dir(cfg)
    for f in sorted(folder.glob("*.enc.json")) if folder.is_dir() else []:
        pcid = f.name.split(".")[0]
        if pcid == mine:
            continue
        if not pw:
            out.append({"pc": pcid, "error": "비밀번호 없음", "agents": {}, "topic_records": []})
            continue
        res = subprocess.run(["node", str(ROOT / "encrypt.mjs"), "decrypt", str(f)],
                             env=dict(os.environ, REAL_OPS_PASSWORD=pw), capture_output=True)
        if res.returncode != 0:
            out.append({"pc": pcid, "error": "열 수 없음(비밀번호가 다르거나 손상)", "agents": {}, "topic_records": []})
            continue
        try:
            rec = json.loads(res.stdout.decode("utf-8"))
        except ValueError:
            out.append({"pc": pcid, "error": "형식 오류", "agents": {}, "topic_records": []})
            continue
        # 다른 PC 파일은 자기 PC 작업자만 기록할 수 있다(이름 사칭 방지)
        rec["agents"] = {k: v for k, v in (rec.get("agents") or {}).items() if k.startswith(pcid + "-")}
        rec["topic_records"] = [r for r in rec.get("topic_records") or [] if str(r.get("agent", "")).startswith(pcid + "-")]
        rec["proposals"] = [p for p in rec.get("proposals") or [] if str(p.get("agent", "")).startswith(pcid + "-")]
        rec["asks"] = [q for q in rec.get("asks") or [] if str(q.get("agent", "")).startswith(pcid + "-")]
        rec["runs"] = [r for r in rec.get("runs") or [] if str(r.get("agent", "")).startswith(pcid + "-")]
        rec["holds"] = {k: v for k, v in (rec.get("holds") or {}).items() if str((v or {}).get("agent", "")).startswith(pcid + "-")}
        rec["notice_acks"] = {nid: {a: v for a, v in (by or {}).items() if str(a).startswith(pcid + "-")}
                              for nid, by in (rec.get("notice_acks") or {}).items() if isinstance(by, dict)}
        rec["pc"] = pcid
        rec["source"] = f.name
        out.append(rec)
    return out


def all_agents(nodes: list[dict]) -> list[dict]:
    rows = []
    for n in nodes:
        for a in (n.get("agents") or {}).values():
            rows.append({**a, "pc": n["pc"], "pc_label": n.get("label", n["pc"]), "pc_synced": n.get("synced_at") or n.get("updated_at")})
    return rows


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
    p = sub.add_parser("init"); p.add_argument("--pc", required=True); p.add_argument("--label", required=True)
    p.add_argument("--role", choices=["hub", "node"], default="node"); p.add_argument("--agent", action="append")
    p = sub.add_parser("status"); p.add_argument("--agent", required=True); p.add_argument("--project")
    p.add_argument("--task"); p.add_argument("--topic"); p.add_argument("--note"); p.add_argument("--idle", action="store_true")
    sub.add_parser("mine"); sub.add_parser("inbox")
    p = sub.add_parser("pack"); p.add_argument("--if-changed", action="store_true",
                                               help="기록이 바뀌었거나 마지막 업로드가 60분 지났을 때만 만듦(아니면 종료 코드 10)")
    p = sub.add_parser("propose", help="이 PC의 아이디어·이슈 메모를 한 건씩 올리기(허브가 미처리 주제로 가져감)")
    p.add_argument("--agent", required=True); p.add_argument("--title", required=True); p.add_argument("--body")
    p.add_argument("--kind", default="기타", choices=["기능·개선", "버그", "조사·분석", "디자인", "운영·도구", "기타"])
    p.add_argument("--priority", default="P2", choices=["P0", "P1", "P2", "P3"]); p.add_argument("--origin", help="원래 메모 위치(예: 스티커 메모, 파일 경로)")
    p.add_argument("--body-file")
    p = sub.add_parser("ask", help="아키텍트 결정·승인이 필요한 질문 남기기(대시보드 '결정이 필요한 문제')")
    p.add_argument("--agent", required=True); p.add_argument("--topic"); p.add_argument("--option", action="append")
    g = p.add_mutually_exclusive_group(required=True); g.add_argument("--question"); g.add_argument("--question-file")
    p = sub.add_parser("handoff", help="다른 작업자(다른 PC 포함)에게 이 주제의 차례를 넘긴다(예: 서버컴 조사 → 개발컴 구현·검증)")
    p.add_argument("id"); p.add_argument("--agent", required=True); p.add_argument("--to", required=True); p.add_argument("--work")
    p.add_argument("--body", "--note", dest="body"); p.add_argument("--body-file")
    p = sub.add_parser("request", help="담당은 그대로 두고 다른 작업자에게 자료·기획·확인을 요청(답이 오면 차례가 돌아옴)")
    p.add_argument("id"); p.add_argument("--agent", required=True); p.add_argument("--to", required=True)
    p.add_argument("--body"); p.add_argument("--body-file")
    p = sub.add_parser("reply", help="받은 요청에 답하기(자료 위치·요약·작업물)")
    p.add_argument("id"); p.add_argument("--agent", required=True); p.add_argument("--req", required=True); p.add_argument("--work")
    p.add_argument("--body"); p.add_argument("--body-file")
    p = sub.add_parser("hold", help="대화 세션이 이 주제를 직접 처리하는 동안 자동 실행기가 건드리지 않게 잡는다")
    p.add_argument("id"); p.add_argument("--agent", required=True); p.add_argument("--minutes", type=int, default=120); p.add_argument("--note")
    p = sub.add_parser("release", help="잡기 풀기"); p.add_argument("id")
    p = sub.add_parser("notice-ack", help="허브 공지를 읽었다고 남기기(대시보드에 확인 표시)")
    p.add_argument("id"); p.add_argument("--agent", required=True)
    p = sub.add_parser("link-work", help="주제에 작업물(real-work) 작업 ID를 연결한다(주제 하나에 작업 하나)")
    p.add_argument("id"); p.add_argument("--agent", required=True); p.add_argument("--work", required=True)
    p = sub.add_parser("claim"); p.add_argument("id"); p.add_argument("--agent", required=True); p.add_argument("--note")
    p = sub.add_parser("plan"); p.add_argument("id"); p.add_argument("--agent", required=True)
    p.add_argument("--goal"); p.add_argument("--scope", action="append"); p.add_argument("--input", action="append")
    p.add_argument("--first-step", action="append"); p.add_argument("--risk", action="append"); p.add_argument("--done-when")
    p.add_argument("--status", choices=STATUSES); p.add_argument("--note")
    p = sub.add_parser("note"); p.add_argument("id"); p.add_argument("--agent", required=True)
    p.add_argument("--kind", default="memo", choices=["memo", "review", "question", "answer"])
    g = p.add_mutually_exclusive_group(required=True); g.add_argument("--body"); g.add_argument("--body-file")
    p = sub.add_parser("state"); p.add_argument("id"); p.add_argument("--agent", required=True)
    p.add_argument("--status", required=True, choices=STATUSES); p.add_argument("--task"); p.add_argument("--note")
    args = ap.parse_args()
    cfg = load_cfg()
    {"init": cmd_init, "status": cmd_status, "mine": cmd_mine, "inbox": cmd_inbox, "pack": cmd_pack, "claim": cmd_claim, "propose": cmd_propose, "ask": cmd_ask,
     "plan": cmd_plan, "note": cmd_note, "state": cmd_state, "handoff": cmd_handoff, "hold": cmd_hold, "release": cmd_release,
     "link-work": cmd_link_work, "notice-ack": cmd_notice_ack, "request": cmd_request, "reply": cmd_reply}[args.cmd](args, cfg)


if __name__ == "__main__":
    main()
