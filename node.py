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
  python node.py inbox      배정·답을 각 작업자 수신 폴더에 메시지로 넣기(한 번씩만)
  python node.py pack       기록을 암호화해 docs/nodes/<pc>.enc.json으로 쓰기
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
KINDS = ("claim", "plan", "memo", "review", "question", "answer", "status")


def now_iso() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def cfg_path() -> Path:
    return Path(os.environ.get("REAL_OPS_CONFIG") or ROOT / "config.local.json")


def load_cfg() -> dict:
    p = cfg_path()
    return json.loads(p.read_text(encoding="utf-8-sig")) if p.exists() else {}


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return default


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def node_dir(cfg) -> Path:
    return (ROOT / cfg.get("node_data_dir", "node-data")).resolve()


def records_path(cfg) -> Path:
    return node_dir(cfg) / "records.json"


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
    rec = load_records(cfg)
    slot = rec["agents"][args.agent]
    ts = now_iso()
    if args.idle:
        slot["current"] = None
    else:
        if not args.project:
            sys.exit("--project(지금 하는 일) 또는 --idle 중 하나는 필요합니다.")
        prev = slot.get("current") or {}
        same = prev.get("project") == args.project
        slot["current"] = {"project": args.project[:200], "task": args.task, "topic": args.topic,
                           "note": (args.note or "")[:500], "since": prev.get("since") if same else ts}
    slot["last_seen"] = ts
    rec["updated_at"] = ts
    write_json(records_path(cfg), rec)
    print(f"{args.agent}: " + ("쉬는 중" if args.idle else f"{args.project}"))


def add_topic_record(cfg, topic: str, agent: str, kind: str, **fields):
    if not TOPIC_RE.match(topic):
        sys.exit(f"주제 ID 형식이 아닙니다: {topic}")
    check_agent(cfg, agent)
    rec = load_records(cfg)
    ts = now_iso()
    rec["topic_records"].append({"topic": topic, "agent": agent, "kind": kind, "ts": ts,
                                 **{k: v for k, v in fields.items() if v not in (None, "", [])}})
    rec["topic_records"] = rec["topic_records"][-3000:]
    rec["agents"][agent]["last_seen"] = ts
    rec["updated_at"] = ts
    write_json(records_path(cfg), rec)


def cmd_propose(args, cfg):
    """이 PC에서 모은 아이디어·이슈 메모를 한 건씩 올린다. 허브가 '미처리' 주제로 가져간다(배분은 착수 지시 후)."""
    import secrets
    check_agent(cfg, args.agent)
    title = args.title.strip()[:200]
    if not title:
        sys.exit("--title이 비어 있습니다.")
    rec = load_records(cfg)
    if any(p.get("title") == title and p.get("agent") == args.agent for p in rec["proposals"]):
        print(f"이미 올린 메모입니다: {title}")
        return
    pid = f"P-{pc_info(cfg)['id']}-{datetime.now(KST):%Y%m%d}-{secrets.token_hex(3)}"
    rec["proposals"].append({"id": pid, "agent": args.agent, "title": title, "body": (args.body or "").strip()[:8000],
                             "kind": args.kind, "priority": args.priority, "origin": (args.origin or "")[:300], "ts": now_iso()})
    rec["proposals"] = rec["proposals"][-2000:]
    rec["updated_at"] = now_iso()
    write_json(records_path(cfg), rec)
    print(f"메모 올림 {pid}: {title} — 다음 동기화 때 허브가 미처리 주제로 가져갑니다")


def add_ask(cfg, agent: str, topic: str | None, question: str, options: list[str]) -> str:
    """아키텍트 승인·결정이 필요할 때 질문을 남긴다. 허브가 대시보드 '결정이 필요한 문제'에 올린다."""
    import secrets
    check_agent(cfg, agent)
    q = question.strip()[:1000]
    if not q:
        sys.exit("질문이 비어 있습니다.")
    rec = load_records(cfg)
    rec.setdefault("asks", [])
    aid = f"DN-{agent}-{datetime.now(KST):%Y%m%d}-{secrets.token_hex(3)}"
    rec["asks"].append({"id": aid, "agent": agent, "topic": topic if topic and TOPIC_RE.match(topic) else None,
                        "question": q, "options": [str(o)[:200] for o in (options or [])][:6], "ts": now_iso()})
    rec["asks"] = rec["asks"][-500:]
    rec["agents"][agent]["last_seen"] = now_iso()
    rec["updated_at"] = now_iso()
    write_json(records_path(cfg), rec)
    return aid


def add_proposal(cfg, agent: str, title: str, body: str, kind: str = "기타", priority: str = "P2", origin: str = "") -> str | None:
    import secrets
    check_agent(cfg, agent)
    title = (title or "").strip()[:200]
    if not title:
        return None
    rec = load_records(cfg)
    if any(p.get("title") == title and p.get("agent") == agent for p in rec["proposals"]):
        return None
    pid = f"P-{pc_info(cfg)['id']}-{datetime.now(KST):%Y%m%d}-{secrets.token_hex(3)}"
    rec["proposals"].append({"id": pid, "agent": agent, "title": title, "body": (body or "").strip()[:8000],
                             "kind": kind if kind in ("기능·개선", "버그", "조사·분석", "디자인", "운영·도구", "기타") else "기타",
                             "priority": priority if priority in ("P0", "P1", "P2", "P3") else "P2",
                             "origin": (origin or "")[:300], "ts": now_iso()})
    rec["proposals"] = rec["proposals"][-2000:]
    rec["updated_at"] = now_iso()
    write_json(records_path(cfg), rec)
    return pid


def cmd_ask(args, cfg):
    aid = add_ask(cfg, args.agent, args.topic, args.question, [o for o in (args.option or []) if o])
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
    add_topic_record(cfg, args.id, args.agent, args.kind, body=args.body.strip()[:6000])
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
    return [t for t in data.get("topics", []) if t.get("assignee") in mine and t.get("status") not in ("done", "parked")]


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
    p = sub.add_parser("ask", help="아키텍트 결정·승인이 필요한 질문 남기기(대시보드 '결정이 필요한 문제')")
    p.add_argument("--agent", required=True); p.add_argument("--topic"); p.add_argument("--question", required=True); p.add_argument("--option", action="append")
    p = sub.add_parser("claim"); p.add_argument("id"); p.add_argument("--agent", required=True); p.add_argument("--note")
    p = sub.add_parser("plan"); p.add_argument("id"); p.add_argument("--agent", required=True)
    p.add_argument("--goal"); p.add_argument("--scope", action="append"); p.add_argument("--input", action="append")
    p.add_argument("--first-step", action="append"); p.add_argument("--risk", action="append"); p.add_argument("--done-when")
    p.add_argument("--status", choices=STATUSES); p.add_argument("--note")
    p = sub.add_parser("note"); p.add_argument("id"); p.add_argument("--agent", required=True)
    p.add_argument("--kind", default="memo", choices=[k for k in KINDS if k not in ("claim", "plan", "status")]); p.add_argument("--body", required=True)
    p = sub.add_parser("state"); p.add_argument("id"); p.add_argument("--agent", required=True)
    p.add_argument("--status", required=True, choices=STATUSES); p.add_argument("--task"); p.add_argument("--note")
    args = ap.parse_args()
    cfg = load_cfg()
    {"init": cmd_init, "status": cmd_status, "mine": cmd_mine, "inbox": cmd_inbox, "pack": cmd_pack, "claim": cmd_claim, "propose": cmd_propose, "ask": cmd_ask,
     "plan": cmd_plan, "note": cmd_note, "state": cmd_state}[args.cmd](args, cfg)


if __name__ == "__main__":
    main()
