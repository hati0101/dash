"""자동 실행기 — 배정된 일이 이 PC 작업자의 차례가 되면 그 AI를 화면 없이 깨워 처리시킨다.

흐름
  아키텍트 지시(대시보드) → 허브 배분 → 차례가 된 작업자의 실행기가 AI를 깨움 → 결과·작업물 기록
  → 아키텍트 확인·메모·결정 → 그 변화로 다시 깨움 → … → 완료.
  다른 PC의 일이 필요하면 AI가 handoff로 차례를 넘긴다(예: 서버컴 조사 → 개발컴 구현·검증 → 서버컴 적용 준비).

안전 원칙
- 운영 변경(운영 서버 적용·재시작·DB 변경·배포·설치·공개)은 하지 않는다. 그 지점에서만 'ask'로 아키텍트에게 묻는다.
- 준비 작업(조사·문서·패치 후보·작업물·인계)은 묻지 않고 끝까지 한다.
- AI는 읽기 도구만 쓴다. 쓰기는 '작업 모드'에서 작업물 저장소(real-work)의 자기 폴더 안에서만 허용한다
  (운영 서버 PC도 같다: 운영 파일은 읽기만, 작업물 폴더에만 쓴다. config "implement": false면 끈다).
- AI는 '다음 행동'을 정해진 JSON으로만 답한다. 실제 기록은 이 실행기가 검증한 뒤 한다. 작업물 ID는 실행기가 정한다(AI가 짓지 않는다).
- 같은 단계는 한 번만 깨운다. 깨우는 기준은 '자기 말고 다른 쪽의 변화'다. 깨운 이유는 runner.log와 실행 이력에 남는다.
- 한 주제는 작업자마다 하루 최대 10번(답 반영 포함). 작업자마다 따로 돌고(서로 줄 서지 않음) 한 번에 최대 3건.
- 실패는 숨기지 않는다: 실행 이력에 결과·실패 사유를 남기고, 로그인 만료처럼 사람이 해야 할 일은 대시보드 '할 일'에 올린다.

  python runner.py                 작업자별로 할 일이 있으면 각각 따로 띄운다
  python runner.py --agent dev-claude   그 작업자 몫만 이 프로세스에서 처리
  python runner.py --dry-run       무엇을 왜 깨울지만 보여 줌(실행 안 함)
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import node  # noqa: E402

KST = timezone(timedelta(hours=9))
MAX_PER_RUN = 3
IDLE_ALERT_RUNS = 3  # 진척 없는 반복은 자문 요청으로 전환한다(2026-10-04).
AI_TIMEOUT = 20 * 60
ACTIVE = ("new", "triage", "ready", "active")
STATUSES = ("triage", "ready", "active", "done", "parked")
WORK_PY = Path(r"D:\real-work\work.py")
UTF8_ENV = {"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # 운영 PC 화면에 콘솔 창이 뜨지 않게(닫아서 끊기는 사고 방지)

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["summary", "actions"],
    "properties": {
        "summary": {"type": "string"},
        "actions": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["type", "kind", "body", "status", "plan", "work_id", "question", "options", "title", "origin", "task", "to", "file", "edits", "cmd"],
            "properties": {
                "type": {"type": "string", "enum": ["claim", "plan", "note", "state", "work_note", "ask", "propose", "handoff", "request", "reply",
                                                    "dev_edit", "dev_run", "dev_revert", "command"]},
                "file": {"type": ["string", "null"]},
                "edits": {"type": ["array", "null"], "items": {"type": "object", "additionalProperties": False, "required": ["old", "new"],
                                                                "properties": {"old": {"type": "string"}, "new": {"type": "string"}}}},
                "cmd": {"type": ["string", "null"]},
                "kind": {"type": ["string", "null"]},
                "body": {"type": ["string", "null"]},
                "status": {"type": ["string", "null"], "enum": ["triage", "ready", "active", "done", "parked", None]},
                "plan": {"type": ["object", "null"], "additionalProperties": False,
                         "required": ["goal", "scope", "inputs", "first_steps", "risks", "done_when"],
                         "properties": {"goal": {"type": "string"}, "scope": {"type": "array", "items": {"type": "string"}},
                                        "inputs": {"type": "array", "items": {"type": "string"}},
                                        "first_steps": {"type": "array", "items": {"type": "string"}},
                                        "risks": {"type": "array", "items": {"type": "string"}}, "done_when": {"type": "string"}}},
                "work_id": {"type": ["string", "null"]},
                "question": {"type": ["string", "null"]},
                "options": {"type": ["array", "null"], "items": {"type": "string"}},
                "title": {"type": ["string", "null"]},
                "origin": {"type": ["string", "null"]},
                "task": {"type": ["string", "null"]},
                "to": {"type": ["string", "null"]},
            }}},
    },
}


def now() -> datetime:
    return datetime.now(KST)


def log(msg: str):
    p = node.node_dir(CFG) / "runner.log"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(f"{now():%Y-%m-%d %H:%M:%S} {msg}\n")
    print(msg)


def child_env() -> dict:
    """하위 프로세스 환경: UTF-8 고정(cp949 출력 오류 방지)."""
    return {**os.environ, **UTF8_ENV}


def ai_env() -> dict:
    """AI 프로세스 환경: 대시보드 비밀번호는 넘기지 않는다."""
    return {k: v for k, v in child_env().items() if k != "REAL_OPS_PASSWORD"}


# ---------------------------------------------------------------- 데이터

def load_data(pw: str) -> dict:
    """허브는 지금 상태로 새로 모으고, 노드는 게시본을 연 뒤 이 PC에서 아직 게시에 반영되지 않은 기록을 덮어쓴다."""
    if (CFG.get("pc") or {}).get("role") == "hub":
        import build
        cfg = dict(CFG)
        example = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8-sig"))
        cfg["limits"] = {**example["limits"], **cfg.get("limits", {})}
        return build.build_payload(cfg, pw)
    data = node.decrypt_main(CFG, pw)
    overlay_local(data, node.load_records(CFG))
    return data


def overlay_local(data: dict, rec: dict, only_after_gen: bool = False):
    """이 PC 기록 중 게시본에 아직 없는 것을 반영한다.
    상태는 '게시본이 상태를 정한 시각(status_at)'보다 나중 기록만 이긴다. 그래서 허브가 이 PC 기록을 받기 전에
    게시본을 만들었더라도, 이 PC에서 끝낸(done) 주제를 다시 깨우지 않는다."""
    from topics import whose_turn, to_dt
    # 시각은 반드시 실제 시각으로 비교한다. 이 PC 기록은 +09:00, 아키텍트 답은 Z(세계 표준시)라 글자로 비교하면
    # "18:47 끝냄"이 "10:34Z(=19:34) 관문 답"보다 나중으로 잘못 판정된다(2026-10-03, 관문 답으로 다시 연 주제를 계속 건너뛴 결함)
    gen = to_dt((data.get("meta") or {}).get("generated_at"))
    known = {a.get("id") for a in data.get("agents", [])} | set(node.my_agents(CFG))
    mine: dict[str, list] = {}
    for r in rec.get("topic_records", []):
        mine.setdefault(r.get("topic"), []).append(r)
    for t in data.get("topics", []):
        if t.get("archived"):
            continue
        rows = sorted(mine.get(t["id"], []), key=lambda r: to_dt(r.get("ts")))
        if not rows:
            continue
        seen = {(n.get("ts"), n.get("by"), n.get("kind")) for n in t.get("notes", [])}
        changed = False
        for r in rows:
            ts = r.get("ts") or ""
            when = to_dt(ts)
            if r.get("status") in STATUSES and when > to_dt(t.get("status_at")) and t.get("status") != "dropped" and (not only_after_gen or when > gen):
                t["status"], t["status_at"], changed = r["status"], ts, True
            if r.get("plan") and (not t.get("plan") or when > gen):
                t["plan"], t["plan_by"], changed = r["plan"], r["agent"], True
            if r.get("work_id") and r.get("kind") in ("work", "handoff") and when > gen:
                t["work_id"] = r["work_id"]
            if r.get("kind") == "handoff" and r.get("to") in known and when > max(gen, to_dt((t.get("handoff") or {}).get("ts"))):
                t["assignee"], t["assign_by"], changed = r["to"], "handoff", True
                t["handoff"] = {"from": r.get("agent"), "to": r["to"], "ts": ts, "reason": (r.get("body") or "")[:300]}
            if r.get("kind") == "request" and r.get("to") in known and r.get("req_id") and r["req_id"] not in {x.get("id") for x in t.get("requests") or []}:
                q = {"id": r["req_id"], "from": r.get("agent"), "to": r["to"], "ts": ts, "body": (r.get("body") or "")[:1500], "status": "open"}
                t["requests"] = [x for x in t.get("requests") or [] if x.get("id") != q["id"]] + [q]
                t["open_request"], changed = q, True
            if r.get("kind") == "reply" and r.get("req_id") and any(x.get("id") == r["req_id"] and x.get("status") != "answered" for x in t.get("requests") or []):
                for x in t.get("requests") or []:
                    if x.get("id") == r["req_id"]:
                        x.update(status="answered", reply_by=r.get("agent"), reply_ts=ts, reply=(r.get("body") or "")[:1500])
                if (t.get("open_request") or {}).get("id") == r["req_id"]:
                    t["open_request"], changed = None, True
            if (ts, r.get("agent"), r.get("kind")) not in seen:
                t.setdefault("notes", []).append({"ts": ts, "kind": r.get("kind"), "body": r.get("body", ""), "by": r.get("agent")})
                changed = True
        if changed:
            t["turn"] = whose_turn(t)
        if t.get("command_mode"):
            import command
            t["command"] = command.project([r for r in rows if r.get("kind") == "command"], known, t.get("command"))
            t["turn"] = whose_turn(t)
            command.route_deputy(t, command.delegation(data))


# ---------------------------------------------------------------- 깨울 일 찾기

SIG_V = 2


def sig_parts(t: dict, who: str, mode: str, data: dict, st: dict) -> dict:
    """깨울지 판단하는 신호. 자기(who)가 남긴 기록은 세지 않는다(자기 재깨움 방지).
    - 단계(착수 전 → 착수 → 진행 베이스)와 모드(읽기/작업)는 한 방향으로만 바뀌므로 단계마다 한 번씩만 깨운다.
    - 다른 작업자 기록 수, 아키텍트·다른 작업자의 대화 수가 늘면 깨운다.
    - cont: 작업 모드에서 결과물이 늘었으면 실행기가 올려 이어서 깨운다(하루 한도 안에서)."""
    notes = t.get("notes", [])
    req = t.get("open_request") or {}
    if req.get("to") == who and who != t.get("assignee"):
        claimed = None
        stage = f"req-{req.get('id')}"
    elif t.get("stage") in ("test", "pack", "prep", "deploy") and t.get("stage_owner") == who:
        stage = f"stage-{t['stage']}-{t.get('status_at')}"  # 새 단계가 시작될 때마다 한 번
    elif who == t.get("assignee"):
        claimed = any(n.get("by") == who and n.get("kind") == "claim" for n in notes)
        stage = "planned" if t.get("plan") else "claimed" if claimed else "new"
    else:
        stage = "review"
    others = sum(1 for n in notes if n.get("by") != who)
    talk = sum(1 for c in data.get("comments", [])
               if (c.get("target") or {}).get("id") == t["id"] and (c.get("_author") or c.get("by")) != who)
    replies = sum(1 for q in t.get("requests") or [] if q.get("from") == who and q.get("status") == "answered")
    if t.get("command_mode") and t.get("stage", "work") in ("work", "test"):
        state = t.get('command') or {}
        meaningful = [e for e in state.get('events', []) if e.get('op') != 'test-progress']
        revision = meaningful[-1].get('revision', 0) if meaningful else (0 if state.get('events') else state.get('revision', 0))
        stage = f"command-{revision}"
        import command
        back = command.pending_return(t)
        if back and who == command.LEAD:
            stage += f"-return-{back.get('id')}"  # r5 I-1: ★40 보완·★4 반려 답이 오면 사령탑을 30분 재확인 없이 바로 깨운다(답 신호)
    return {"stage": stage, "mode": mode, "others": others, "talk": talk, "cont": st.get("cont", 0), "replies": replies}


def topic_sig(t: dict, who: str, mode: str, data: dict, st: dict) -> str:
    p = sig_parts(t, who, mode, data, st)
    return hashlib.sha1(json.dumps([t["id"], who, p["stage"], p["mode"], p["others"], p["talk"], p["cont"]],
                                   ensure_ascii=False).encode()).hexdigest()[:12]


def wake_reason(parts: dict, last: dict | None) -> str:
    """왜 깨우는지 사람이 읽을 수 있게."""
    if str(parts["stage"]).startswith("req-") and parts["stage"] != (last or {}).get("stage"):
        return "다른 작업자의 요청을 받음"
    if not last:
        return "처음 차례가 옴"
    out = []
    if parts.get("replies", 0) > last.get("replies", 0):
        out.append("내가 보낸 요청에 답이 옴")
    if parts["stage"] != last.get("stage"):
        out.append({"new": "착수 전", "claimed": "진행 베이스 작성", "planned": "진행", "review": "교차 검토"}.get(parts["stage"], parts["stage"]) + " 단계")
    if parts["mode"] != last.get("mode"):
        out.append("작업 모드로 바뀜" if parts["mode"] == "impl" else "읽기 모드로 바뀜")
    if parts["others"] > last.get("others", 0):
        out.append(f"다른 작업자 기록 +{parts['others'] - last.get('others', 0)}")
    if parts["talk"] > last.get("talk", 0):
        out.append(f"아키텍트·대화 +{parts['talk'] - last.get('talk', 0)}")
    if parts["cont"] > last.get("cont", 0):
        out.append("작업물 진척 → 이어서")
    return ", ".join(out) or "기록 변화"


def impl_allowed() -> bool:
    """작업 모드(작업물 폴더 쓰기) 허용. 개발 PC(허브)와 노드 모두 기본 허용 — 쓰기는 real-work의 자기 폴더로만 제한된다.
    운영 서버 PC에서 이것까지 막으려면 config "implement": false."""
    return CFG.get("implement", True) is not False and WORK_PY.exists()


def find_jobs(data: dict, state: dict, only: str | None = None) -> list[dict]:
    agents = {k: v for k, v in node.my_agents(CFG).items() if ((data.get("agent_locks") or {}).get(k) or {}).get("mode") != "all"}
    today = f"{now():%Y%m%d}"
    answers = {a["id"]: a for a in data.get("decisions_answered", [])}
    holds = node.active_holds(CFG)
    migrate = state.get("sig_v") != SIG_V
    state["sig_v"] = SIG_V
    stamp = now().isoformat(timespec="seconds")
    jobs = []
    from topics import to_dt
    open_asks: dict[str, set] = {}  # 작업자별로 아키텍트 답을 기다리는 AI 질문이 걸린 주제
    for q in data.get("decisions_needed", []):
        if q.get("_author") and q["id"] not in answers and q.get("kind") not in ("gate", "stall", "consultation"):
            open_asks.setdefault(q["_author"], set()).add(q.get("task_id"))

    def limited(st: dict) -> bool:
        # 하루 횟수 한도는 없다(아키텍트 결정 2026-10-03: 보류하지 않았으면 멈추지 않는다). 헛돌 때만 retry_after로 간격을 둔다
        return (st.get("retry_after") or "") > stamp

    def slowed(st: dict) -> bool:
        """지금 대기가 헛돎·개발 실패 감속인가(실행 실패 재시도 대기가 아니라). 옛 상태 파일은 횟수로 짐작한다."""
        kind = st.get("retry_kind") or ("slow" if (st.get("idle_runs") or 0) > 2 or (st.get("dev_fail") or 0) >= 3 else "error")
        return kind == "slow"

    for t in data.get("topics", []):
        who = t.get("turn")
        if who not in agents or (only and who != only) or t.get("status") not in ACTIVE:
            continue
        if t["id"] in holds or t.get("live_session") or t.get("deploy_session") or t.get("stage") == "queue":
            continue  # 대화 세션이 잡고 있다(실게임 시험은 개발컴 Claude, 8b 배포는 서버컴 Astra 대화 세션 몫). 배포 대기열은 아무도 안 깨움
        # 담당이고 진행 베이스가 있고 진행 중이면 '작업 모드'(작업물 저장소의 자기 폴더에 결과물을 직접 만든다)
        req_to_me = (t.get("open_request") or {}).get("to") == who
        stage_mine = t.get("stage") in ("test", "pack", "prep") and t.get("stage_owner") == who
        mode = "impl" if (impl_allowed() and (req_to_me or stage_mine or t.get("command_mode") or (who == t.get("assignee") and t.get("plan") and t.get("status") == "active"))) else "plan"
        st = state.setdefault("topics", {}).setdefault(t["id"], {})
        parts = sig_parts(t, who, mode, data, st)
        sig = topic_sig(t, who, mode, data, st)
        if migrate and st.get("last_sig") and st.get("last_sig") != sig:
            st["last_sig"], st["last_parts"] = sig, parts  # 계산 방식이 바뀐 첫 실행: 이미 처리한 주제를 한꺼번에 다시 깨우지 않는다
            continue
        reason = wake_reason(parts, st.get("last_parts"))
        if consultation_wait(st, parts):
            continue  # 시간 경과·AI 메모만으로 같은 시도를 반복하지 않는다.
        if limited(st):
            # 감속 중이어도 새 입력(아키텍트·대화, 내 요청에 온 답, 단계·모드 변화)이 오면 바로 깨운다 — 아키텍트가 '헛도는 중'을 보고
            # 개입한 답이 2시간 늦게 가지 않게(2026-10-03 포크 모의 검사 s16·s36). 실행기 자신의 '이어서'(cont)와 다른 AI 작업자의
            # 메모(others)는 새 입력으로 치지 않는다(헛도는 두 AI가 서로의 메모로 감속을 풀며 빠르게 도는 것 방지)
            last = st.get("last_parts") or {}
            if not ((slowed(st) or st.get("retry_kind") == "env") and last and any(parts.get(k) != last.get(k) for k in ("stage", "mode", "talk", "replies"))):
                continue
            reason = f"감속 중이지만 새 입력이 와서 바로 깨움({reason})"
        if st.get("last_sig") == sig:
            # 이 단계를 이미 처리했는데 차례가 그대로다(아키텍트가 보류하지 않았다) → 멈추지 않고 간격을 두고 다시 깨운다.
            # 아키텍트 답을 기다리는 질문이 있으면 그 답이 올 때까지는 기다린다(답이 오면 답 처리로 깨운다)
            if t["id"] in open_asks.get(who, set()):
                continue
            seen = (st.get("last_result") or {}).get("at") or st.get("skip_since")
            if not seen:
                continue  # 언제 처리했는지 모르면(옛 상태 파일) 이번에는 두고 다음 실행 기록부터 판단한다
            last = to_dt(seen)
            wait = 30 if st.get("idle_runs", 0) <= 2 else 120
            if (now() - last).total_seconds() < wait * 60:
                continue
            reason = f"이 단계를 처리한 뒤 변화 없이 차례가 그대로라 다시 깨움({wait}분 간격)"
        seen_at = (st.get("last_result") or {}).get("at")
        answered_at = max((h_.get("answered_at") for h_ in t.get("gate_history") or [] if h_.get("answered_at")), key=to_dt, default=None)
        decision = (bool(answered_at and (not seen_at or to_dt(answered_at) > to_dt(seen_at))) or "-return-" in str(parts["stage"])
                    or parts["talk"] > (st.get("last_parts") or {}).get("talk", 0))
        jobs.append({"kind": "topic", "agent": who, "topic": t, "sig": sig, "mode": mode, "parts": parts, "reason": reason, "decision": decision})
    jobs = batch_plan_jobs(jobs)
    jobs = batch_review_jobs(jobs)
    # 배포 묶음은 AI·운영 반영 없이 로컬 ZIP을 준비한다. 최신 데이터로 매번 구성원을 검증한다.
    if "server-astra" in agents and (only is None or only == "server-astra"):
        batches = sorted({(t.get("deploy_batch") or {}).get("id") for t in data.get("topics", [])
                          if t.get("command_mode") and t.get("stage") == "deploy" and t.get("status") == "active" and (t.get("deploy_batch") or {}).get("id")})
        for batch in batches:
            members = [t for t in data["topics"] if (t.get("deploy_batch") or {}).get("id") == batch and t.get("stage") == "deploy" and t.get("status") == "active"]
            fingerprint = hashlib.sha256(json.dumps([(t["id"], t.get("status_at"), t.get("work_id"), t.get("package_receipts")) for t in members], sort_keys=True).encode()).hexdigest()
            bst = state.setdefault("batches", {}).get(batch) or {}
            if bst.get("fingerprint") == fingerprint or limited(bst):
                continue
            jobs.append({"kind": "batch", "agent": "server-astra", "topic": None, "batch": batch, "fingerprint": fingerprint,
                         "sig": fingerprint, "mode": "local", "reason": "묶음 파일 자동 수신·검증·ZIP 준비"})
    # 내가 물었던 질문에 아키텍트가 답했으면 다시 깨운다(한 답에 한 번)
    used = state.setdefault("answers_used", [])
    for q in data.get("decisions_needed", []):
        if q.get("_author") in agents and (not only or q["_author"] == only) and q["id"] in answers and q["id"] not in used:
            t = next((x for x in data.get("topics", []) if x["id"] == q.get("task_id")), None)
            if (str(q.get("question") or "").startswith(PARK_ASK) or q.get("kind") == "consultation") and str(answers[q["id"]].get("choice") or "").startswith("보류"):
                # 아키텍트가 보류를 골랐다 → AI를 깨우지 않고 실행기가 보류로 기록하는 작업(run_job에서 처리)
                jobs.append({"kind": "park", "agent": q["_author"], "topic": t, "ask": q, "answer": answers[q["id"]], "sig": f"park-{q['id']}"})
                continue
            if t and t.get("status") in ("done", "parked", "dropped", "review_user"):
                used.append(q["id"])  # 이미 끝났거나 아키텍트 관문 대기: 이 답으로 AI가 할 일이 없으니 처리함으로(옛 답으로 나중에 다시 깨지 않게)
                continue
            if t and (t["id"] in holds or t.get("live_session") or t.get("deploy_session") or t.get("stage") == "queue"):
                continue  # 대화 세션 처리 중·실게임 시험 단계(개발컴 Claude 대화)·8b 배포(서버컴 대화)는 실행기가 깨우지 않는다
            ast_ = state.setdefault("topics", {}).setdefault(t["id"] if t else f"ans-{q['id']}", {})
            if limited(ast_) and not slowed(ast_):
                continue  # 실행 실패 재시도 대기만 기다린다. 헛돎 감속 중이어도 아키텍트 답은 바로 전한다
            jobs.append({"kind": "answer", "agent": q["_author"], "topic": t, "ask": q, "answer": answers[q["id"]],
                         "sig": f"ans-{q['id']}", "mode": "plan", "reason": "아키텍트 답 도착"})
    # 같은 주제·작업자에 답 처리가 여러 건이면 가장 최근 답 하나만 돌리고, 나머지는 그 실행에서 함께 처리함으로 표시한다
    newest: dict = {}
    for j in [j for j in jobs if j["kind"] == "answer"]:
        k = ((j.get("topic") or {}).get("id") or j["sig"], j["agent"])
        if k not in newest or (j["answer"].get("ts") or "") >= (newest[k]["answer"].get("ts") or ""):
            if k in newest:
                j.setdefault("older", []).extend([newest[k]["ask"]["id"], *newest[k].get("older", [])])
            newest[k] = j
        else:
            newest[k].setdefault("older", []).append(j["ask"]["id"])
    jobs = [j for j in jobs if j["kind"] != "answer" or newest.get(((j.get("topic") or {}).get("id") or j["sig"], j["agent"])) is j]
    ans_keys = {((j.get("topic") or {}).get("id"), j["agent"]) for j in jobs if j["kind"] == "answer"}
    jobs = [j for j in jobs if j["kind"] == "answer" or ((j.get("topic") or {}).get("id"), j["agent"]) not in ans_keys]
    jobs.sort(key=job_rank)
    if only:
        return jobs[:MAX_PER_RUN]
    return jobs


# ---------------------------------------------------------------- 개발 트리 수정·빌드·시험(아키텍트 승인 2026-10-03, 개발컴 실행기만)
# AI는 개발 트리에 직접 쓰지 않는다. dev_edit(바꿀 부분 old→new)·dev_run(정해진 이름의 명령)·dev_revert를 남기면 실행기가 검사 뒤 대신 한다.
# 고칠 때마다 원본 대비 diff를 작업물 patch/에 남긴다(운영 패치용). 백업·로그는 scratch(F 드라이브)에 모으고 정리 규칙대로 지운다.
# 운영 서버(서버컴)는 대상이 아니다. 설정: config agents[].dev = {root, write, scratch, scratch_cap_gb, commands{이름: [명령…]}, timeout_min}
import contextlib  # noqa: E402
import difflib  # noqa: E402
import time  # noqa: E402

DEV_DENY = re.compile(r"(^|/)(\.git|\.vs|harness|bin)(/|$)|\.(exe|dll|pdb|lib|obj|ilk|idb|exp)$", re.I)
# 고칠 수 있는 파일 종류(허용 목록, 2026-10-03 검토 P1): 빌드 설정(.vcxproj·.props·.targets·.sln·CMakeLists.txt)·스크립트는
# 빌드 때 임의 명령이 돌 수 있으므로 고치지 못한다.
DEV_ALLOW_EXT = {".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx", ".h", ".c", ".inl", ".inc", ".txt", ".yml", ".yaml", ".conf", ".sql"}
DEV_DENY_NAMES = {"cmakelists.txt"}
WIN_RESERVED = re.compile(r"^(con|prn|aux|nul|com[0-9]|lpt[0-9])(\..*)?$", re.I)


def dev_cfg(agent_id: str | None) -> dict | None:
    d = (node.my_agents(CFG).get(agent_id) or {}).get("dev") if agent_id else None
    return d if d and d.get("root") and Path(d["root"]).is_dir() else None


def dev_scratch(dev: dict) -> Path:
    return Path(dev.get("scratch") or r"F:\real-dev-scratch")


def dev_path(dev: dict, raw) -> tuple[str, Path]:
    """AI가 적은 경로 → (개발 트리 기준 실제 상대 경로, 실제 경로). 허용 폴더·허용 확장자만. 트리 밖·링크로 빠져나가는 경로와
    Windows가 다르게 읽는 이름(끝의 점·공백, ':' 스트림, 예약 이름, 8.3 짧은 이름)은 거부한다.
    링크·정션을 따라간 실제 경로로 한 번 더 검사하고, 기록(잠금·manifest) 키도 실제 경로(실제 대소문자)로 쓴다
    (2026-10-03 검토: 'src/MAP/Skill.cpp' 같은 대소문자 별칭으로 다른 주제의 잠금을 우회하지 못하게)."""
    def check(rel: str):
        parts = rel.split("/")
        bad = (not rel or any(p in ("", ".", "..") for p in parts) or DEV_DENY.search(rel) or parts[0] not in dev.get("write", [])
               or any(p != p.rstrip(" .") or ":" in p or WIN_RESERVED.match(p) or re.search(r"~\d", p) for p in parts))
        if bad:
            raise ValueError(f"고칠 수 없는 경로: {rel or '(없음)'} (허용 폴더: {', '.join(dev.get('write', []))})")
        if Path(rel).suffix.lower() not in DEV_ALLOW_EXT or parts[-1].lower() in DEV_DENY_NAMES:
            raise ValueError(f"고칠 수 없는 파일 종류: {rel} (허용: {' '.join(sorted(DEV_ALLOW_EXT))} · 빌드 설정·스크립트는 안 됨)")
    rel = str(raw or "").replace("\\", "/").strip().lstrip("/")
    check(rel)
    root = Path(dev["root"]).resolve()
    path = (root / rel).resolve()
    if root not in path.parents:
        raise ValueError(f"개발 트리 밖 경로: {rel}")
    real = path.relative_to(root).as_posix()
    check(real)
    return real, path


@contextlib.contextmanager
def dev_lock(sc: Path, wait: float = 300):
    """scratch의 기록(manifest·locks.json)을 고치는 동안 다른 실행(정리·다른 작업자)과 겹치지 않게 잠근다(2026-10-03 검토 P2).
    빌드처럼 오래 걸리는 일은 잠근 채로 하지 않는다. 1시간 넘은 잠금은 비정상 종료로 보고 푼다."""
    sc.mkdir(parents=True, exist_ok=True)
    lk = sc / "dev.lock"
    token = f"{os.getpid()}-{time.time_ns()}"
    t0 = time.monotonic()
    while True:
        try:
            fd = os.open(lk, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, token.encode())
            os.close(fd)
            break
        except FileExistsError:
            try:
                if time.time() - lk.stat().st_mtime > 3600:
                    # 오래된 잠금: 이름을 바꿔 치우면 둘이 동시에 와도 한쪽만 성공한다(지우고 잡는 경합 방지)
                    stale = lk.with_name(f"dev.lock.stale-{token}")
                    os.replace(lk, stale)
                    stale.unlink(missing_ok=True)
                    continue
            except OSError:
                pass
            if time.monotonic() - t0 > wait:
                raise ValueError("개발 트리 기록 잠금을 얻지 못함(다른 실행이 쓰는 중) — 다음 실행에서 다시")
            time.sleep(0.5)
    try:
        yield
    finally:
        try:  # 내 잠금일 때만 푼다
            if lk.read_text(encoding="utf-8", errors="replace") == token:
                lk.unlink(missing_ok=True)
        except OSError:
            pass


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _dev_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))  # verify-build의 result.json은 BOM이 붙는다
    except (OSError, ValueError):
        return default


def _dev_save(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    node.write_json(path, obj)


def _decode(raw: bytes) -> tuple[str, str]:
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8"), "utf-8-sig"
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return raw.decode("cp949"), "cp949"  # 둘 다 아니면 UnicodeDecodeError(ValueError) → 거부


def _decode_out(raw: bytes) -> str:
    """명령 출력: UTF-8 → cp949 순으로 읽고, 그래도 안 되면 깨진 글자만 바꿔서 읽는다(출력 때문에 실패하지 않게)."""
    for enc in ("utf-8", "cp949"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", errors="replace")


def _encode(text: str, enc: str) -> bytes:
    return (b"\xef\xbb\xbf" + text.encode("utf-8")) if enc == "utf-8-sig" else text.encode(enc)


def _apply_edits(rel: str, text: str, edits: list, exists: bool) -> tuple[str, str]:
    """바꿀 부분을 정확히 한 곳에서 찾아 바꾼다 → (쓸 글, 줄바꿈 종류). 줄바꿈은 파일 그대로 둔다.
    CRLF·LF가 섞인 파일은 전체를 한 종류로 바꾸지 않고, 찾은 곳의 줄바꿈 형태로만 바꾼다."""
    crlf = "\r\n" in text
    mixed = crlf and re.search(r"(?<!\r)\n", text) is not None
    work = text if mixed else text.replace("\r\n", "\n")
    for e in edits:
        old = str(e.get("old") or "").replace("\r\n", "\n")
        new = str(e.get("new") or "").replace("\r\n", "\n")
        if not exists and old == "" and len(edits) == 1:
            return new, "LF"  # 새 파일
        forms = {old, old.replace("\n", "\r\n")} if mixed else {old}
        hits = [(f, work.count(f)) for f in forms if f]
        n = sum(c for _, c in hits)
        if n != 1:
            raise ValueError(f"{rel}: 바꿀 부분을 정확히 한 곳에서 찾지 못함({n}곳) — 앞뒤 줄을 더 넣어 유일하게: {old[:80]!r}")
        found = next(f for f, c in hits if c == 1)
        work = work.replace(found, new.replace("\n", "\r\n") if "\r\n" in found else new, 1)
    if mixed:
        return work, "혼합(고친 곳만 그 형태로)"
    return (work.replace("\n", "\r\n") if crlf else work), ("CRLF" if crlf else "LF")


def dev_edit(agent_id: str, tid: str, a: dict, ws: Path | None) -> str:
    """바꿀 부분(old)을 정확히 한 곳에서 찾아 new로 바꾼다. 원래 인코딩·줄바꿈 유지, 처음 고칠 때 원본 백업, diff를 작업물에 남긴다.
    기록(manifest)을 먼저 쓰고 파일을 바꾼다: 중간에 멈춰도 되돌리기·다음 수정이 어느 쪽 내용인지 안다(2026-10-03 검토 P2)."""
    dev = dev_cfg(agent_id)
    if not dev:
        raise ValueError("이 작업자는 개발 트리를 고칠 수 없음")
    rel, path = dev_path(dev, a.get("file"))
    edits = a.get("edits") or []
    if not isinstance(edits, list) or not edits or len(edits) > 30 \
            or not all(isinstance(e, dict) and isinstance(e.get("old", ""), str) and isinstance(e.get("new", ""), str) for e in edits):
        raise ValueError('edits는 [{"old": 문자열, "new": 문자열}] 1~30개')
    sc = dev_scratch(dev)
    with dev_lock(sc):
        exists = path.exists()
        raw = path.read_bytes() if exists else b""
        text, enc = _decode(raw) if exists else ("", "utf-8")
        out_text, nl = _apply_edits(rel, text, edits, exists)
        try:
            out = _encode(out_text, enc)
        except UnicodeEncodeError:
            raise ValueError(f"{rel}: 원래 인코딩({enc})으로 쓸 수 없는 글자가 있음")
        locks = _dev_json(sc / "locks.json", {})
        if locks.get(rel) and locks[rel] != tid:
            raise ValueError(f"{rel}: 다른 주제({locks[rel]})가 고치는 중인 파일")
        mpath = sc / tid / "manifest.json"
        man = _dev_json(mpath, {"files": {}, "builds": [], "created": now().isoformat(timespec="seconds")})
        cur = _sha(raw) if exists else None
        f = man["files"].get(rel)
        if f:
            if cur not in (f.get("last_sha"), f.get("next_sha")):
                raise ValueError(f"{rel}: 이 주제가 마지막으로 고친 뒤 다른 곳에서 바뀜 — 대화 세션에서 확인 필요")
        else:
            bk = sc / tid / "backup" / rel
            if exists:
                bk.parent.mkdir(parents=True, exist_ok=True)
                if bk.exists() and _sha(bk.read_bytes()) != cur:  # 앞 회차 백업은 덮어쓰지 않고 이름을 바꿔 둔다
                    bk.replace(bk.with_name(f"{bk.name}.prev-{now():%Y%m%d%H%M%S}"))
                if not bk.exists():
                    bk.write_bytes(raw)
            # diff 이름: 앞 회차(정리 뒤 재작업) diff가 작업물에 있으면 덮어쓰지 않고 다음 번호로
            pdir = (ws or (sc / tid)) / "patch"
            stem = rel.replace("/", "__")
            name, k = f"{stem}.diff", 2
            while (pdir / name).exists():
                name, k = f"{stem}.{k}.diff", k + 1
            f = man["files"][rel] = {"base_sha": cur, "created": not exists, "enc": enc, "diff": name, "last_sha": cur}
        f["next_sha"] = _sha(out)
        _dev_save(mpath, man)
        locks[rel] = tid
        _dev_save(sc / "locks.json", locks)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".runner.tmp")
        tmp.write_bytes(out)
        os.replace(tmp, path)
        f["last_sha"] = f.pop("next_sha")
        _dev_save(mpath, man)
        # 원본 대비 diff(운영 패치용)를 작업물 patch/에
        base = sc / tid / "backup" / rel
        base_text = _decode(base.read_bytes())[0].replace("\r\n", "\n") if base.exists() and not f.get("created") else ""
        lines = list(difflib.unified_diff(base_text.splitlines(True), out_text.replace("\r\n", "\n").splitlines(True), f"a/{rel}", f"b/{rel}"))
        dest = (ws or (sc / tid)) / "patch" / (f.get("diff") or (rel.replace("/", "__") + ".diff"))
        note = f"diff patch/{dest.name}"
        try:  # 파일은 이미 바뀌었다: diff를 못 써도 '거부'로 기록하지 않고 알린다(다음 수정 때 다시 쓴다)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(f"# 원본 SHA256 {f['base_sha'] or '(새 파일)'}\n# 수정 SHA256 {f['last_sha']}\n# 인코딩 {enc} · 줄바꿈 {nl}\n" + "".join(lines), encoding="utf-8")
            try:
                f['diff_work_path'] = dest.resolve().relative_to(WORK_PY.parent.resolve()).as_posix()
                _dev_save(mpath,man)
            except ValueError:
                pass  # scratch 사본은 real-work 보존 근거가 아니다.
        except OSError as exc:
            note = f"diff 쓰기 실패({exc}) — 수정은 적용됨"
    add = sum(1 for x in lines if x.startswith("+") and not x.startswith("+++"))
    rem = sum(1 for x in lines if x.startswith("-") and not x.startswith("---"))
    return f"{rel} 수정(원본 대비 +{add}/-{rem}줄) · {note}"


def _is_build_dir(dev: dict, d) -> bool:
    """지워도 되는 빌드 사본인가: <개발 트리>/harness/runs/build-* 바로 아래 실제 폴더(링크·정션 아님)여야 한다(2026-10-03 검토 P2)."""
    try:
        p = Path(d)
        runs = (Path(dev["root"]) / "harness" / "runs").resolve()
        return (p.name.startswith("build-") and p.is_dir() and not p.is_symlink() and not p.is_junction()
                and p.resolve() == runs / p.name)
    except (OSError, ValueError, KeyError, TypeError):
        return False


def _rm_build(dev: dict, d) -> bool:
    if not _is_build_dir(dev, d):
        return False
    shutil.rmtree(d, ignore_errors=True)
    return True


def _build_result(dev: dict, text: str, since: datetime | None = None) -> tuple[dict, str | None]:
    """빌드 명령 출력 끝의 결과(JSON)에 적힌 경로로 이번 빌드 사본 폴더를 찾는다.
    폴더 비교로 짐작하지 않는다(같은 때 돈 다른 세션의 빌드를 지우지 않게, 2026-10-03 검토 P2)."""
    i = text.rfind("\n{")
    chunk = text[i + 1:] if i >= 0 else (text if text.lstrip().startswith("{") else "")
    j = chunk.rfind("}")
    try:
        res = json.loads(chunk[:j + 1]) if j >= 0 else {}
    except ValueError:
        res = {}
    if not isinstance(res, dict):
        res = {}
    for key in ("log", "artifact"):
        v = res.get(key)
        if not v:
            continue
        p = Path(str(v))
        for cand in (p, *p.parents):
            if cand.name.startswith("build-"):
                # 내 빌드 확인: 그 폴더의 result.json이 있고, 거기 적힌 경로가 그 폴더 안이고, 이번 실행 뒤에 만들어진 폴더여야 한다
                # (출력에 끼어든 다른 JSON으로 다른 세션 빌드를 내 것으로 잡아 지우지 않게)
                saved = _dev_json(cand / "result.json", None) if _is_build_dir(dev, cand) else None
                inside = isinstance(saved, dict) and str(saved.get(key) or "").replace("/", "\\").lower().startswith(str(cand).replace("/", "\\").lower() + "\\")
                try:
                    fresh = inside and (since is None or datetime.fromtimestamp(cand.stat().st_ctime, KST) >= since - timedelta(seconds=5))
                except OSError:
                    fresh = False
                if inside and fresh:
                    return saved, str(cand)
                break
    return res, None


def _run_tree(argv: list, cwd: str, timeout: float, out_path: Path) -> tuple[int, bytes]:
    """명령 실행. 비밀번호는 넘기지 않고(ai_env), 시간 초과면 자식(MSBuild 등)까지 모두 끝낸다(2026-10-03 검토).
    출력은 파이프가 아니라 파일로 받는다: 빌드가 띄운 상주 프로세스(mspdbsrv 등)가 출력을 물고 있어도 명령이 끝나면 바로 돌아온다."""
    env = {**ai_env(), "MSBUILDDISABLENODEREUSE": "1"}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as fh:
        p = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=fh, stderr=subprocess.STDOUT, env=env, creationflags=NO_WINDOW)
        try:
            rc = p.wait(timeout=timeout)
            tail = b""
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True, creationflags=NO_WINDOW)
            p.kill()
            try:
                p.wait(timeout=60)
            except subprocess.TimeoutExpired:
                pass
            rc, tail = -1, "\n[시간 초과 — 프로세스 트리 종료]".encode("utf-8")
    try:
        out = out_path.read_bytes()
    except OSError:
        out = b""
    return rc, out + tail


def dev_run(agent_id: str, tid: str, a: dict) -> tuple[str, bool]:
    """정해진 이름의 명령만 실행한다(빌드·검사) → (결과 꼬리, 성공 여부). 전체 기록은 scratch/logs에.
    빌드 사본은 이 명령 결과에 적힌 폴더만 관리한다(성공한 최신 하나만 남기고 나머지는 지운다)."""
    dev = dev_cfg(agent_id)
    if not dev:
        raise ValueError("이 작업자는 개발 명령을 돌릴 수 없음")
    name = str(a.get("cmd") or "").strip()
    argv = (dev.get("commands") or {}).get(name)
    if not argv:
        raise ValueError(f"없는 명령 '{name}' (가능: {', '.join(dev.get('commands') or {})})")
    sc = dev_scratch(dev)
    t0 = now()
    log_path = sc / tid / "logs" / f"{t0:%Y%m%d-%H%M%S}-{name}.log"
    raw_path = log_path.with_suffix(".raw")
    rc, out = _run_tree(argv, dev["root"], float(dev.get("timeout_min", 45)) * 60, raw_path)
    text = _decode_out(out) if out else ""
    secs = int((now() - t0).total_seconds())
    log_path.write_text(text, encoding="utf-8")
    try:
        raw_path.unlink(missing_ok=True)
    except OSError:
        pass  # 빌드가 띄운 상주 프로세스가 아직 잡고 있음 — 다음 정리 때 지운다
    res, run_dir = _build_result(dev, text, t0)
    ok = rc == 0 and (not run_dir or res.get("status", "PASS") == "PASS")
    artifact = ""
    with dev_lock(sc, wait=900):  # 빌드는 끝났다: 기록을 못 남기면 사본이 추적되지 않으므로 넉넉히 기다린다
        mpath = sc / tid / "manifest.json"
        man = _dev_json(mpath, {"files": {}, "builds": [], "created": now().isoformat(timespec="seconds")})
        if run_dir:
            man["builds"].append({"dir": run_dir, "cmd": name, "ok": ok, "at": t0.isoformat(timespec="seconds"), "artifact": res.get("artifact"), "sha256": res.get("sha256")})
            if ok and res.get("artifact"):
                artifact = f"\n빌드 결과물: {res['artifact']} (SHA256 {str(res.get('sha256'))[:16]}…)"
        elif name.startswith("build"):
            artifact = "\n(빌드 결과에서 사본 폴더를 찾지 못함 — 사본은 지우지 않고 그대로 둠)"
        # 정리: 실패했거나 더 새 성공 빌드로 대체된 사본은 바로 지운다(성공한 최신 하나만 실게임 시험용으로 남김)
        oks = [b for b in man["builds"] if b.get("ok") and not b.get("removed")]
        keep = oks[-1]["dir"] if oks else None
        for b in man["builds"]:
            if not b.get("removed") and b["dir"] != keep:
                _rm_build(dev, b["dir"])
                b["removed"] = True
        _dev_save(mpath, man)
    tail = text.strip()[-2500:]
    return f"[{name}] 종료 코드 {rc} · {secs}초{artifact}\n{tail}\n(전체 기록: {log_path})", ok


def _restart_diff_preserved(tid, name, f, raw, backup):
    """승계 원복 전 real-work의 diff를 현재 바이트·원본 해시·실제 차이와 대조."""
    import command
    if _sha(raw) != f.get('last_sha'):
        return False
    original = b'' if f.get('created') else backup.read_bytes() if backup.is_file() else None
    if original is None or (not f.get('created') and _sha(original) != f.get('base_sha')):
        return False
    before = _decode(original)[0].replace('\r\n','\n') if original else ''
    after = _decode(raw)[0].replace('\r\n','\n')
    expected = ''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),'a/'+name,'b/'+name))
    if not expected: return True  # 현재 바이트가 원본과 같아 보존할 변경이 없다.
    root = WORK_PY.parent
    candidates = []
    if f.get('diff_work_path'): candidates.append(root / f['diff_work_path'])
    for topic_id in (tid, f.get('inherited_from')):
        for wid in linked_work_ids(topic_id):
            candidates += list((root/'work'/wid).glob('*/patch/'+str(f.get('diff') or '__missing__')))
    for candidate in candidates:
        try:
            checked = command.safe_file(root,candidate.relative_to(root).as_posix())
            text = checked.read_text(encoding='utf-8-sig').replace('\r\n','\n')
            header = text.split('\n',3)
            if len(header)==4 and header[0]=='# 원본 SHA256 '+str(f.get('base_sha') or '(새 파일)') and header[1]=='# 수정 SHA256 '+f['last_sha'] and header[3]==expected:
                return True
        except (OSError,ValueError,UnicodeError): continue
    return False


def _dev_revert(dev: dict, tid: str, rel: str | None, force: bool) -> list[str]:
    sc = dev_scratch(dev)
    mpath = sc / tid / "manifest.json"
    man = _dev_json(mpath, None)
    if not man:
        return []
    msgs = []
    locks = _dev_json(sc / "locks.json", {})
    root = Path(dev["root"]).resolve()
    want = str(rel).replace("\\", "/").strip().lstrip("/") if rel else None
    if want:
        try:  # 고칠 때처럼 실제 경로(실제 대소문자)로 맞춘다
            want = (root / want).resolve().relative_to(root).as_posix()
        except (OSError, ValueError):
            pass
    for name, f in list(man["files"].items()):
        if want and name != want:
            continue
        path = (root / name).resolve()
        if root not in path.parents:
            msgs.append(f"{name}: 개발 트리 밖 경로라 되돌리지 않음")
            continue
        cur = _sha(path.read_bytes()) if path.exists() else None
        if cur not in (f.get("last_sha"), f.get("next_sha")) and not force:
            msgs.append(f"{name}: 다른 곳에서 바뀌어 되돌리지 않음")
            continue
        bk = sc / tid / "backup" / name
        if f.get('inherited_from') and not _restart_diff_preserved(tid,name,f,path.read_bytes() if path.is_file() else b'',bk):
            msgs.append(f"{name}: 승계 변경의 real-work diff·마지막 해시 검증 실패 — 원복하지 않고 보존")
            continue
        if f.get("created"):
            path.unlink(missing_ok=True)
        elif bk.exists():
            tmp = path.with_name(path.name + ".runner.tmp")
            tmp.write_bytes(bk.read_bytes())
            os.replace(tmp, path)
        else:
            msgs.append(f"{name}: 백업이 없어 되돌리지 못함")
            continue
        msgs.append(f"{name}: 원본으로 되돌림")
        man["files"].pop(name, None)
        if locks.get(name) == tid:
            locks.pop(name)
    if want and not msgs:
        msgs.append(f"{want}: 이 주제가 고친 파일이 아님")
    _dev_save(mpath, man)
    _dev_save(sc / "locks.json", locks)
    return msgs


def dev_revert(agent_id: str | None, tid: str, rel: str | None = None, force: bool = False) -> list[str]:
    """이 주제가 고친 파일을 원본으로 되돌린다. 그 뒤 다른 곳에서 바뀐 파일은 건드리지 않는다(force가 아니면)."""
    devs = [dev_cfg(agent_id)] if agent_id else [d for d in (a.get("dev") for a in node.my_agents(CFG).values()) if d]
    msgs = []
    for dev in [d for d in devs if d]:
        with dev_lock(dev_scratch(dev)):
            msgs += _dev_revert(dev, tid, rel, force)
    return msgs


def dev_passed(t: dict) -> bool:
    """정리해도 되는 '통과' 상태인가 — 지금 상태로만 판정한다(2026-10-03 검토 P1: ★4 통과 이력이 있어도 '문제 있음'·'수정'으로
    진행에 되돌아와 다시 고치는 중이면 백업·diff를 지우지 않는다). 완료, ★5·★7·★9 대기, 배포본 작성·운영 반영 단계."""
    return t.get("status") == "done" or (t.get("gate") or {}).get("n") in (5, 7, 9) or t.get("stage") in ("pack", "prep", "queue", "deploy")


def dev_cleanup(data: dict) -> list[str]:
    """정리 규칙(아키텍트 지시 2026-10-03: 시험 뒤에는 기술 문서와 diff만 남긴다).
    - 지금 ★4를 통과한 상태(★5 이후)거나 완료면: 개발 트리 변경은 그대로 두고 백업·로그·빌드 사본을 지운다
    - 보류·삭제된 주제: 그 뒤 손대지 않은 파일은 원본으로 되돌린 뒤 지운다. 되돌리지 못한 파일이 있으면 그 백업은 남긴다
    - 7일 지난 로그·빌드 사본은 지운다 · 전체가 상한(GB)을 넘으면 오래된 빌드부터 지운다
    - 지우는 빌드 사본은 <개발 트리>/harness/runs/build-* 아래 실제 폴더만(링크·다른 경로는 건드리지 않는다)"""
    out = []
    topics = {t["id"]: t for t in data.get("topics", [])}
    for aid, a in node.my_agents(CFG).items():
        dev = dev_cfg(aid)
        if not dev:
            continue
        sc = dev_scratch(dev)
        if not sc.is_dir():
            continue
        with dev_lock(sc):
            out += _dev_cleanup_one(dev, sc, topics)
    return out


def _inherit_restart_locks(sc, old, new, locks):
    """dev_lock 안에서 호출. 이전 자료를 남기고 기준·백업을 먼저 복제한 뒤 잠금 승계."""
    if not new or old == new or not re.fullmatch(r'T-\d{8}-[A-Za-z0-9_-]+', new):
        raise ValueError('재시작 잠금 승계 대상 오류')
    prior = _dev_json(sc / old / 'manifest.json', {})
    target = sc / new / 'manifest.json'
    man = _dev_json(target, {'files':{},'builds':[], 'created':now().isoformat()})
    moving = [name for name, owner in locks.items() if owner == old]
    for name in moving:
        original = (prior.get('files') or {}).get(name)
        if not original: raise ValueError('승계할 원본 manifest 항목 없음: '+name)
        if name in man['files']:
            if man['files'][name].get('inherited_from') != old: raise ValueError('새 주제의 기존 파일 기록과 승계 충돌: '+name)
            continue  # 중간 종료 뒤 재실행. 새 주제의 변경 기록을 덮지 않는다.
        rel = Path(name)
        if rel.is_absolute() or '..' in rel.parts: raise ValueError('승계 경로 오류')
        backup = sc / old / 'backup' / name
        dest = sc / new / 'backup' / name
        if not original.get('created'):
            if not backup.is_file() or _sha(backup.read_bytes()) != original.get('base_sha'):
                raise ValueError('승계할 원본 백업 해시 불일치: '+name)
            dest.parent.mkdir(parents=True,exist_ok=True)
            if not dest.exists() or _sha(dest.read_bytes()) != original['base_sha']:
                # manifest에 아직 등록하지 않은 중간 복사만 복구한다. 기존 바이트도 별도 보존.
                if dest.exists():
                    saved = dest.with_name(dest.name+'.interrupted-'+_sha(dest.read_bytes()))
                    if not saved.exists(): os.replace(dest,saved)
                tmp = dest.with_name(dest.name+'.inherit.tmp')
                tmp.write_bytes(backup.read_bytes())
                if _sha(tmp.read_bytes()) != original['base_sha']: raise ValueError('승계 임시 백업 해시 불일치: '+name)
                os.replace(tmp,dest)
        man['files'][name] = {**original, 'inherited_from':old}
    if moving:
        _dev_save(target,man)
        for name in moving: locks[name] = new
        _dev_save(sc / 'locks.json',locks)
    return len(moving)


def _dev_cleanup_one(dev: dict, sc: Path, topics: dict) -> list[str]:
    out = []
    locks = _dev_json(sc / "locks.json", {})
    cutoff = now() - timedelta(days=7)
    for d in [p for p in sc.iterdir() if p.is_dir()]:
        try:
            tid, man = d.name, _dev_json(d / "manifest.json", {"files": {}, "builds": []})
            t = topics.get(tid)
            if not t:
                continue  # 게시본에 없는 주제(읽기 오류 등)는 건드리지 않는다
            if t.get('archived') or t.get('restarted_as'):
                successor = t.get('restarted_as')
                if successor and successor in topics:
                    count = _inherit_restart_locks(sc, tid, successor, locks)
                    if count: out.append(f'{tid} → {successor}: 파일 잠금 {count}개 승계, 이전 백업·기준 보존')
                continue  # 재시작 보관은 삭제가 아니다. 개발 트리·백업을 자동 원복/정리하지 않는다.
            passed = dev_passed(t)
            gone = t.get("status") in ("parked", "dropped")
            if gone:
                _dev_save(sc / "locks.json", locks)
                out += [f"{tid} {m}" for m in _dev_revert(dev, tid, None, False)]
                man = _dev_json(d / "manifest.json", man)
                locks = _dev_json(sc / "locks.json", locks)
            if passed or gone:
                for b in man.get("builds", []):
                    if not b.get("removed"):
                        _rm_build(dev, b["dir"])
                        b["removed"] = True
                left = list(man.get("files", {})) if gone else []
                if left:  # 되돌리지 못한 파일: 백업·기록은 남기고 로그·빌드만 지운다
                    shutil.rmtree(d / "logs", ignore_errors=True)
                    _dev_save(d / "manifest.json", man)
                    out.append(f"{tid} 정리(보류·삭제): 되돌리지 못한 파일 {len(left)}개({', '.join(left[:3])}) — 백업 유지, 로그·빌드 사본만 삭제")
                    continue
                for name in list(man.get("files", {})):
                    if locks.get(name) == tid:
                        locks.pop(name)
                shutil.rmtree(d, ignore_errors=True)
                out.append(f"{tid} 정리({'완료·★4 통과' if passed else '보류·삭제'}): 백업·로그·빌드 사본 삭제, 문서·diff는 작업물에 남김")
                continue
            for b in man.get("builds", []):  # 7일 지난 빌드 사본
                if not b.get("removed") and b.get("at", "") < cutoff.isoformat():
                    _rm_build(dev, b["dir"])
                    b["removed"] = True
            for lg in [*(d / "logs").glob("*.log"), *(d / "logs").glob("*.raw")] if (d / "logs").is_dir() else []:
                try:
                    if lg.suffix == ".raw" or datetime.fromtimestamp(lg.stat().st_mtime, KST) < cutoff:
                        lg.unlink(missing_ok=True)  # .raw는 명령이 끝난 뒤 남은 출력 사본(내용은 .log에 있음)
                except OSError:
                    pass
            _dev_save(d / "manifest.json", man)
        except (OSError,ValueError) as exc:
            out.append(f'{d.name}: 정리·승계 실패 — 자료 보존, 다른 주제 계속: {exc}')
            locks = _dev_json(sc / 'locks.json',locks)

    _dev_save(sc / "locks.json", locks)
    # 용량 상한: 오래된 빌드 사본부터
    cap = float(dev.get("scratch_cap_gb", 20)) * 1024 ** 3

    def size(p: Path) -> int:
        return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.exists() else 0
    builds = sorted(((d.name, b) for d in sc.iterdir() if d.is_dir() for b in _dev_json(d / "manifest.json", {}).get("builds", []) if not b.get("removed") and d.name in topics and not (topics[d.name].get("archived") or topics[d.name].get("restarted_as"))),
                    key=lambda x: x[1].get("at", ""))
    total = size(sc) + sum(size(Path(b["dir"])) for _, b in builds)
    for tid, b in builds:
        if total <= cap:
            break
        s = size(Path(b["dir"]))
        _rm_build(dev, b["dir"])
        total -= s
        m = _dev_json(sc / tid / "manifest.json", {})
        for x in m.get("builds", []):
            if x.get("dir") == b["dir"]:
                x["removed"] = True
        _dev_save(sc / tid / "manifest.json", m)
        out.append(f"{tid} 용량 상한으로 빌드 사본 삭제: {b['dir']}")
    return out


# ---------------------------------------------------------------- 작업물(real-work)

def run_work(*args: str) -> subprocess.CompletedProcess:
    """작업물 저장소 도구 실행. 한글 출력이 깨지지 않게 UTF-8로 받는다."""
    with repo_lock():
        return subprocess.run([sys.executable, str(WORK_PY), *args], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", env=ai_env(), creationflags=NO_WINDOW)


def work_exists(wid: str | None) -> bool:
    return bool(wid) and node.WORK_ID_RE.match(wid) is not None and (WORK_PY.parent / "work" / wid / "README.md").exists()


def linked_work_ids(topic_id: str | None) -> list[str]:
    """작업물 저장소에서 이 주제에 연결된 작업 ID(README의 '대시보드 주제' 칸이 같은 것)."""
    base = WORK_PY.parent / "work"
    if not topic_id or not base.is_dir():
        return []
    ids = []
    for readme in sorted(base.glob("*/README.md")):
        try:
            m = re.search(r"^\| 대시보드 주제 \| (.*?) \|$", readme.read_text(encoding="utf-8", errors="replace"), re.M)
        except OSError:
            continue
        if m and m.group(1).strip() == topic_id:
            ids.append(readme.parent.name)
    return ids


def topic_work_id(t: dict) -> str | None:
    """주제 하나에 작업물 하나. 연결 기록 → README 주제 칸 → (없음) 순으로 이미 있는 것을 쓴다."""
    tid = t.get("id")
    local = [r.get("work_id") for r in node.load_records(CFG).get("topic_records", [])
             if r.get("topic") == tid and r.get("kind") in ("work", "handoff") and r.get("work_id")]
    for wid in [*reversed(local), t.get("work_id"), *linked_work_ids(tid)]:
        if work_exists(wid):
            return wid
    return None


def ensure_work(job: dict, create: bool) -> str | None:
    """이 주제의 작업물 ID를 정한다. create면 없을 때 FT-<주제>를 만들고 주제에 연결 기록을 남긴다."""
    t = job.get("topic") or {}
    if not t.get("id") or not WORK_PY.exists():
        return None
    wid = topic_work_id(t)
    if not wid and create:
        wid = "FT-" + t["id"][2:]
        if not work_exists(wid):
            r = run_work("new", wid, "--agent", job["agent"], "--kind", "기능", "--title", (t.get("title") or wid)[:120], "--topic", t["id"])
            if r.returncode != 0:
                job.setdefault("failed", []).append(f"작업물 만들기 실패: {(r.stdout or r.stderr).strip()[-300:]}")
                return None
    if wid and wid != t.get("work_id") and not any(r.get("work_id") == wid for r in node.load_records(CFG).get("topic_records", [])
                                                   if r.get("topic") == t["id"] and r.get("kind") in ("work", "handoff")):
        node.add_topic_record(CFG, t["id"], job["agent"], "work", work_id=wid, body=f"작업물 연결: real-work/work/{wid}/")
    job["work_id"] = wid
    return wid


def pull_work_repo():
    if WORK_PY.exists():
        with repo_lock():
            try:
                subprocess.run(["git", "-C", str(WORK_PY.parent), "pull", "-q", "--rebase", "--autostash", "origin", "main"],
                               capture_output=True, env=dict(ai_env(), GIT_TERMINAL_PROMPT="0"), creationflags=NO_WINDOW, timeout=180)
            except subprocess.TimeoutExpired:
                return
            gd = WORK_PY.parent / ".git"
            if (gd / "rebase-merge").exists() or (gd / "rebase-apply").exists():  # 받기 충돌: 멈춘 rebase를 되돌린다(충돌 표식이 남지 않게)
                subprocess.run(["git", "-C", str(WORK_PY.parent), "rebase", "--abort"], capture_output=True, creationflags=NO_WINDOW, timeout=60)


class repo_lock:
    """작업물 저장소(real-work)의 git 작업을 한 번에 하나만(같은 PC의 작업자 실행기·동기화끼리 겹치지 않게).
    sync.ps1도 이 잠금 파일이 있으면 real-work 받기를 건너뛴다."""
    def __init__(self):
        self.path = node.node_dir(CFG) / "realwork.lock"

    def __enter__(self):
        import time
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.time() + 180
        while True:
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > 300:
                        self.path.unlink(missing_ok=True)
                        continue
                except FileNotFoundError:
                    continue
                if time.time() > deadline:
                    return self  # 3분 넘게 못 잡으면 그냥 진행(멈추지 않게). 해제는 자기 것만.
                time.sleep(0.5)

    def __exit__(self, *exc):
        try:
            if self.path.read_text() == str(os.getpid()):
                self.path.unlink(missing_ok=True)
        except OSError:
            pass
        return False


# ---------------------------------------------------------------- 지시문

READ_HINT = {
    "claude": "읽기는 Read·Grep·Glob 도구로 한다. 이 도구들로 필요한 파일을 직접 열어 확인한다(도구가 없다고 판단하지 말 것).",
    "codex": "읽기 명령(Get-Content, Get-ChildItem, Select-String, rg, type, dir 등)은 실행해도 된다. 설치·네트워크·서비스 제어 명령은 막혀 있으니 시도하지 않는다.",
}


def dev_blocked(job: dict) -> str | None:
    """개발 트리 행동을 막는 경우(2026-10-03 검토 P2): 계획 모드, 배포본 작성·운영 반영 단계, 관문 대기·실게임 대화 단계."""
    t = job.get("topic") or {}
    if job.get("mode") != "impl":
        return "계획 모드에서는 개발 트리를 고치거나 빌드하지 않음(진행 베이스·교차 검토 뒤 작업 모드에서)"
    if t.get("stage") in ("pack", "prep", "queue", "deploy"):
        return "배포본 작성·배포 준비·배포 단계에서는 개발 트리를 고치지 않음"
    if t.get("gate") or t.get("live_session"):
        return "관문 대기·실게임 대화 단계에서는 자동 실행기가 개발 트리를 고치지 않음"
    return None


def dev_section(job: dict) -> str:
    """개발 트리 권한이 있는 작업자(개발컴 Claude)가 이 단계 담당일 때: 실제로 고치고 빌드·시험하는 방법."""
    dev = dev_cfg(job["agent"])
    if not dev or job["agent"] != stage_doer(job.get("topic") or {}) or dev_blocked(job):
        return ""
    cmds = "\n".join(f"  - `{k}`" for k in (dev.get("commands") or {}))
    return f"""## 개발 트리 직접 수정·빌드·시험 (아키텍트 승인 2026-10-03, 개발컴 격리 개발 트리만)
개발 트리: `{dev['root']}` (고칠 수 있는 폴더: {', '.join(dev.get('write', []))}). 운영 서버는 대상이 아니다.
- 파일을 직접 쓰지 말고 행동으로 요청한다. 실행기가 검사 뒤 적용하고 결과를 이 주제 기록([실행기 …] 메모)으로 돌려준다.
- `dev_edit`: file=개발 트리 기준 상대 경로(예: src/map/skill.cpp), edits=[{{"old": 바꿀 부분 원문(정확히 한 곳에만 있도록 앞뒤 줄 포함), "new": 바꾼 내용}}]. 새 파일은 edits=[{{"old": "", "new": 전체 내용}}].
  원래 인코딩·줄바꿈은 실행기가 지킨다. 고칠 때마다 원본 대비 diff가 작업물 patch/에 자동으로 생긴다.
- `dev_run`: cmd=아래 이름 중 하나만(다른 명령은 거부). C++을 고쳤으면 관련 타깃을 빌드한다.
{cmds}
- `dev_revert`: file=되돌릴 파일(비우면 이 주제가 고친 파일 전부)을 원본으로.
- 한 번에 고치고(dev_edit) 이어서 빌드(dev_run)까지 같은 답에 넣어도 된다. 결과는 다음 실행에서 기록으로 보고 이어서 고친다.
- 2 진행: 실제로 고친다. 3 자체 시험: 관련 빌드·검사를 돌려 통과시킨다(실패하면 고치고 다시). 같은 문제로 세 번 실패하면 ask.
- 끝냄(state done) body와 작업물 DESIGN.md에는 정확한 기술 문서를 남긴다: 바꾼 파일·이유·영향, 빌드 결과(결과물 경로·SHA256), 시험 방법·체크리스트. 시험 뒤에는 이 문서와 diff만 남고 빌드 사본·백업은 정리된다.
"""


def impl_section(job: dict, ws: Path | None) -> str:
    if not ws:
        return ""
    return f"""## 작업 모드 (지금 실제로 일을 한다)
진행 베이스가 있고 진행 중이므로 이번에는 결과물을 직접 만든다.
- 작업 공간: `{ws}` (현재 폴더, 작업물 {job.get('work_id')}). **이 폴더 안에서만** 파일을 만들고 고칠 수 있다.
- 실제 프로젝트·운영 폴더는 읽기만 한다. 고칠 내용은 작업 공간에 만든다:
  - 새 파일(스크립트·NPC·설정 초안·문서)은 원래 들어갈 상대 경로를 살려 `files/` 아래에
  - 기존 파일 수정은 원본을 읽고 `patch/<파일이름>.diff`(통합 diff, 원본 경로·원본 SHA256 표기)로
  - 설계·결정 근거·적용 절차·백업·복구·시험 방법은 `DESIGN.md`에
- 한 번에 다 못 끝내면 진행한 만큼 만들고 `note`로 진척과 다음 할 일을 남긴다(다음 동기화 때 이어서 깨운다).
- 결과물이 다 준비되면: 개발컴 격리 검증이 필요하면 `handoff`로 개발컴 작업자에게 넘기고, 운영 적용만 남았으면 `ask`로 적용 승인을 묻는다.
- 작업 공간 파일은 실행기가 비밀값 검사 후 작업물 저장소에 올린다.
"""


STAGE_GUIDE = {
    "work": "2 진행: 진행 베이스 → 작업 → 교차 검토. 결과물이 준비되면 끝냄(state done) → 3 AI 자체 시험으로 넘어간다"
            "(조사·분석·기획 주제, 또는 바꾼 파일이 없어 끝냄 요약에 '시험할 것 없음'이라고 적으면 시험 없이 ★결과 확인으로).",
    "test": "3 AI 자체 시험(관문 없음, 네가 스스로 한다): 개발컴 격리 환경(server-dev) 기준으로 결과물을 검증한다. "
            "아래에 '개발 트리 직접 수정·빌드·시험' 칸이 있으면 실제로 관련 빌드·검사(dev_run)를 돌려 통과시키고 결과물 경로·SHA256을 남긴다. "
            "그 칸이 없으면(권한 없는 작업자) 정적 검증(실제 파일·데이터·호출부 대조, 근거 경로·줄)과 시험 절차·확인 체크리스트 작성까지 한다. 문제를 찾으면 스스로 고치고 다시 검증한다. 같은 문제로 세 번 실패하면 ask로 올린다. "
            "통과하면 끝냄(state done)의 body에 '실게임 시험 준비' 요약을 쓴다: 격리 서버에 반영할 빌드·파일, 실행 방법, "
            "아키텍트가 확인할 항목(체크리스트), 자체 검증 근거. 그러면 ★4 실게임 시험 관문이 열린다. 운영 서버에서는 이 단계를 하지 않는다. "
            "★4부터는 담당이 개발컴 Claude로 옮겨지고 아키텍트와 대화 세션에서 바로 시험·수정한다(자동 실행기는 손대지 않음).",
    "pack": "6 배포본 작성: 아키텍트가 배포본 작성을 골랐다(★5 배포본 만들기, 또는 ★7·★9에서 배포본 수정 — 직전 관문 메모가 고칠 내용). real-work 작업물에 배포본을 만든다: 적용 파일, 정확한 대상 경로, 적용 절차, "
            "백업 방법, 복구 수단, 각 파일 SHA256, 적용 후 확인 방법. 끝냄(state done)으로 ★7 운영 반영 승인 관문을 연다.",
    "prep": "8a 배포 준비(아키텍트가 ★7에서 '배포 대기열에 넣기'를 골랐다 — 바로 반영이 아니다, 2026-10-03). 운영 서버에는 아무것도 쓰지 않는다"
            "(적용·재시작·DB 변경 금지, 읽기와 real-work 작업물 쓰기만). 할 일: ① 실서버 기준 diff — 지금 운영본과 배포본을 대조한 diff를 작업물 deploy-prep/에 "
            "② 배포 대기열의 다른 항목과 겹치는 파일·충돌 확인 ③ 적용 순서·백업 위치·되돌리기 절차·적용 후 확인 항목을 deploy-prep/DEPLOY-PREP.md에. "
            "끝냄(state done) body는 '대상 파일: 경로1, 경로2'(운영 기준 상대 경로) 한 줄과 '겹침: 없음' 또는 '겹침: T-… (파일)' 한 줄을 반드시 넣고, "
            "그 아래에 diff·순서·백업·복구·확인 항목 요약과 작업물 경로를 쓴다. 그러면 '배포 준비 완료'로 배포 대기열에 들어간다(관문 없음). "
            "실제 배포는 아키텍트가 날을 잡아 배포 묶음을 만든 뒤 서버컴 Astra 대화에서 한다.",
    "deploy": "8b 배포(서버컴 Astra 대화 세션 몫 — 자동 실행기는 이 단계를 하지 않는다). 아키텍트가 배포 묶음에 넣었다. "
              "아키텍트와 대화하며 실서버 diff·패치를 검토하고 배포한 뒤, 묶음의 각 주제에 끝냄(state done)으로 "
              "'배포 완료(묶음 R-…, 시각, 확인 결과)' 또는 '배포 실패·되돌림(이유, 되돌린 방법)'을 남긴다 → ★9.",
}


def stage_text(t: dict, job: dict) -> str:
    st = t.get("stage") or "work"
    step = t.get("step") or {}
    hist = t.get("gate_history") or []
    last = f"\n- 직전 관문: ★{hist[-1]['n']} → 아키텍트 선택 '{hist[-1].get('choice') or '메모'}' {hist[-1].get('note') or ''}" if hist else ""
    return (f"- 지금: {step.get('n', 2)}/9 {step.get('label', '진행')}\n- 할 일: {STAGE_GUIDE.get(st, STAGE_GUIDE['work'])}{last}\n"
            "- AI는 완료(done)를 확정하지 못한다. 끝냄(state done)은 다음 ★관문(아키텍트 확인)을 여는 신호이고, body에 결과 요약이 반드시 있어야 한다.\n"
            "- 관문을 여는 끝냄의 body는 반드시 이 3줄로 시작한다(아키텍트가 화면에서 바로 판단하게, 2026-10-03):\n"
            "  핵심: 결과의 핵심을 원문 그대로 인용(예: 원래 메모는 'LOUNGE_PENDING.md 312행 \"트레저 고블린.\" 한 줄', 출현 조건·보상은 정해진 것 없음)\n"
            "  정할 것: 아키텍트가 지금 고를 것(예: 구체화해서 후속 구현으로 갈지 / 메모로 두고 완료할지)\n"
            "  권장: 너의 권장과 이유 한 줄\n"
            "  그 아래에 무엇을 했나·작업물 위치(파일 경로)·시험 방법을 쓴다. '정리를 완료합니다'처럼 내용 없는 요약은 거부된다.")


def agent_directory(data: dict) -> str:
    pcs = (data.get("meta", {}).get("routing", {}).get("pcs") or {})
    rows = []
    for a in data.get("agents", []):
        role = (pcs.get(a.get("pc")) or {}).get("역할") or ""
        rows.append(f"- {a['id']} · {a.get('pc_label')} {a.get('label') or ''}{' — ' + role if role else ''}")
    return "\n".join(rows) or "(정보 없음)"


def rule_files(agent_id: str | None = None) -> list[str]:
    """AI가 먼저 읽을 규칙 파일: 공통 기반 + PC 공통(config "rule_files", 둘 다 읽어도 되는 것) + 그 작업자 몫(agents[]."rule_files").
    AI 이름이 적힌 파일(예: '나는 server-claude'가 있는 CLAUDE.md)은 작업자별 칸에만 넣는다. 없는 파일·중복은 뺀다."""
    mine = (node.my_agents(CFG).get(agent_id) or {}).get("rule_files") or [] if agent_id else []
    out = []
    for f in [r"D:\real-ai-guidelines\FOUNDATION.md", *CFG.get("rule_files", []), *mine]:
        if f and Path(f).exists() and str(Path(f).resolve()).lower() not in {str(Path(x).resolve()).lower() for x in out}:
            out.append(f)
    return out



def release_contract_prompt(t, job):
    if not t.get("command_mode") or t.get("stage") not in ("test", "pack", "prep"):
        return ""
    return """## 자동 후속 단계와 배포 계약
시험 중 발견한 문제는 개발컴에서 고쳐 재시험한다. 아키텍트가 시험을 반려해도 대화 복사를 요구하지 않는다.
자체 시험 뒤 실게임 판단이 필요하면 결재함에 결과·시험 방법을 올린다. 불필요하다고 분해 계획에서 정한 경우 배포본으로 자동 진행한다.
pack은 작업물 자기 폴더에 PACKAGE.json을 작성한다. version=1, topic=현재 주제 ID,
summary/apply_steps/rollback_steps/verify_steps는 비어 있지 않은 문자열.
changes 배열의 각 항목: operation=create|replace|patch|delete, target=server/상대경로 또는 client/상대경로,
source=작업물 저장소 기준 실제 전달 파일 경로(work/작업ID/개발작업자/파일),
before_sha256=기준 원본 해시(신규만 null), after_sha256=전달 파일 해시(삭제만 null).
소스·NPC·설정 텍스트는 전체 파일 대신 patch(.diff), source_sha256=diff 해시, after_sha256=적용 후 파일 해시로 전달한다.
evidence=[{path:작업물 저장소 상대경로,sha256:실제 검증 근거 파일 해시}]가 필수.
운영 비밀값·게임 소스 전체·사용자 데이터는 포함하지 않는다. 대형 바이너리는 기존 허용된 전달 경로를 사용해야 하며
계약에 필요한 파일이 실제 수신되지 않았다면 끝냄 대신 사령탑에 request로 막힌 원인을 보고한다.
pack 완료 → 서버컴 prep은 자동이다. prep 완료 전 실행기가 모든 전달 파일/근거 해시를 읽어 확인하고 candidate.zip을 만든다.
prep 요약에는 대상 파일: 과 겹침: 줄, 수신 검증 결과, 적용 순서·실제 운영 기준 확인 여부를 적는다.
운영 적용과 실제 배포 승인은 하지 않는다. ZIP은 배포 후보이며 실게임 QA를 증명하지 않는다.
"""

def build_prompt(job: dict, data: dict, workspace: Path | None, st: dict) -> str:
    a = node.my_agents(CFG)[job["agent"]]
    pc = CFG.get("pc", {})
    pcs = (data.get("meta", {}).get("routing", {}).get("pcs") or {})
    pc_rule = (pcs.get(pc.get("id")) or {}).get("note") or ""
    t = job.get("topic") or {}
    comments = [c for c in data.get("comments", []) if (c.get("target") or {}).get("id") == t.get("id")]
    notes = "\n".join(f"- [{n.get('ts', '')[:16]}] {n.get('by')} ({n.get('kind')}): {str(n.get('body', ''))[:700]}" for n in t.get("notes", [])[-18:]) or "(없음)"
    convo = "\n".join(f"- [{str(c.get('ts', ''))[:16]}] {c.get('_author') or c.get('by')}: {str(c.get('body', ''))[:900]}" for c in comments[-10:]) or "(없음)"
    plan = json.dumps(t.get("plan"), ensure_ascii=False, indent=1) if t.get("plan") else "(아직 없음)"
    req = t.get("open_request") if (t.get("open_request") or {}).get("to") == job["agent"] else None
    role = ("최종 사령탑" if job["agent"] == "server-astra" else "배정된 실행 작업자") if t.get("command_mode") else ("요청받은 작업자" if req else "담당" if t.get("assignee") == job["agent"] else "교차 검토자")
    mine_reqs = [q for q in t.get("requests") or [] if q.get("from") == job["agent"]][-3:]
    req_text = ""
    if req:
        req_text = (f"\n## 받은 요청 (이번에 깨운 이유) — 요청 ID {req.get('id')}\n요청한 작업자: {req.get('from')} (이 주제의 담당)\n요청 내용:\n{req.get('body')}\n"
                    "할 일: 요청 범위만 처리한다(담당 일 전체를 대신하지 않는다). 필요한 자료·기획·확인 결과를 찾아 `reply`(body=요약·근거 경로·작업물 위치)로 답한다.\n"
                    "자료 파일이 필요하면 작업 공간(있으면)에 두고 reply에 경로를 적는다. 답하면 차례가 요청한 작업자에게 자동으로 돌아간다.\n"
                    "요청을 처리할 수 없으면 그 이유와 대신 누가·어디서 찾을 수 있는지를 reply로 답한다(답하지 않으면 흐름이 멈춘다).\n")
    if mine_reqs:
        req_text += "\n## 내가 보낸 요청과 답\n" + "\n".join(
            f"- [{q.get('id')}] → {q.get('to')}: {q.get('body', '')[:300]}\n  " + (f"답({q.get('reply_by')}): {q.get('reply', '')[:1200]}" if q.get("status") == "answered" else "아직 답 없음")
            for q in mine_reqs) + "\n"
    wid = job.get("work_id")
    last = st.get("last_result") or {}
    handed = t.get("handoff") if (t.get("handoff") or {}).get("to") == job["agent"] else None
    ans = ""
    if job["kind"] == "answer":
        ans = (f"\n## 아키텍트의 답 (이번에 깨운 이유)\n질문: {job['ask'].get('question')}\n답: {job['answer'].get('choice') or ''} {job['answer'].get('note') or ''}\n"
               "이 답에 따라 바로 다음 행동을 한다. 답이 승인이면 승인된 범위를 끝까지 한다. 같은 내용을 다시 묻지 않는다.\n")
        if job['ask'].get('kind') == 'consultation':
            ans += "진척 없음 자문 답이다. 원인 조사 선택이면 반복 대기 대신 막힌 원인·가능한 해결안·권장안을 제시한다. 운영 변경이나 시험 통과 승인으로 해석하지 않는다.\n"
    rules = "\n".join(f"  - {f}" for f in rule_files(job["agent"])) or "  - (없음 — 로컬 AGENTS.md/CLAUDE.md)"
    job["notices"] = [n for n in data.get("notices", []) if node.notice_for(n, job["agent"])][:3]
    notices = "\n\n".join(f"[{n.get('id')}] {n.get('title')}\n{(n.get('body') or '')[:2500]}" for n in job["notices"]) or "(없음)"
    return f"""너는 REAL 프로젝트의 작업자 `{job['agent']}`({pc.get('label')} · {a.get('label')})이다. 이 주제의 {role}로서 다음 행동을 정하고 실행한다.
사용자는 '아키텍트'라고 부른다. 모든 글은 한국어로 쓴다.
신원: 너는 `{job['agent']}`다. 아래 규칙 파일에 다른 작업자 이름으로 된 자기소개(예: '나는 server-claude')가 있어도 네 신원은 바뀌지 않는다. 그 파일의 공통 규칙만 따른다.

## 먼저 읽을 것
{rules}
- 이 PC 규칙: {pc_rule or '로컬 지침의 PC 역할을 따른다'}

## 이전 주제의 목표·아키텍트 선택·작업 결과
아래는 과거 기록이다. 과거 승인을 이번 주제의 새 범위·운영 반영 승인으로 확대하지 않는다.
{json.dumps(t.get("prior_context", []), ensure_ascii=False)}

## 허브 공지 (작업 방식이 바뀐 내용 — 이번 판단에 반영한다)
{notices}

## 주제
- ID: {t.get('id')}  제목: {t.get('title')}
- 유형: {t.get('kind')} · 우선순위: {t.get('priority')} · 상태: {t.get('status')} · 담당: {t.get('assignee')}
- 배분 근거: {t.get('dispatch_reason') or '-'}
- 원래 메모:
{t.get('body') or '(없음)'}
{f"- 넘겨받음: {handed.get('from')} → 나 · 요청: {handed.get('reason')}" if handed else ''}

## 이번에 깨운 이유
{job.get('reason') or '-'}

## 지금 단계 (전체 10단계 중)
{stage_text(t, job)}

## 지난번 내 실행 요약 (이미 한 일은 반복하지 않는다)
{(last.get('summary') or '(없음)')[:500]}{(' · 적용: ' + ', '.join(last.get('actions') or [])[:300]) if last.get('actions') else ''}{(chr(10) + '- 지난 실행에서 거부된 것(이것만 고쳐 다시 내면 된다): ' + '; '.join(last.get('failed') or [])[:500]) if last.get('failed') else ''}

## 지금까지의 기록
{notes}

## 진행 베이스
{plan}

## 작업물 (real-work)
{('real-work/work/' + wid + '/ (이 주제의 작업물. ID는 실행기가 관리한다)') if wid else '아직 없음 — work_note를 쓰면 실행기가 이 주제의 작업물을 만들어 연결한다'}

## 아키텍트와의 대화
{convo}
{ans}{req_text}
{__import__("command").prompt(t, job["agent"])}
{release_contract_prompt(t, job)}
{__import__("testflow").prompt(t)}
## 작업자 목록 (handoff·request 대상)
{agent_directory(data)}
{('- 배정 잠금(인계·요청 금지): ' + ', '.join(sorted(data.get('agent_locks') or {}))) if data.get('agent_locks') else ''}

## 규칙
- {READ_HINT[job['runner']]}
- 할 수 있는 일은 끝까지 한다. 조사·정리·문서·패치 후보·작업물 작성·검토·인계는 승인 없이 한다(이미 맡겨진 일이다).
- `ask`는 실제 운영 변경 지점에서만 쓴다: 운영 서버 적용·재시작·DB 변경·배포·설치·공개, 또는 아키텍트만 정할 수 있는 기획 선택.
  완료 기준이 조금 모호하면 묻지 말고 합리적인 기준을 정해 note에 적고 진행한다.
- 아키텍트는 결재만 한다(직원처럼 알아서 진행, 2026-10-03). 파일 확인·조사·실험으로 알 수 있는 것은 묻지 말고 직접 알아내 결과로 올린다.
  `ask`는 권한·취향·위험 판단이 필요한 결정만. 관문에 올리기 전에 스스로 검증을 끝내고, 못 한 검증은 왜 못 했는지와 대신 한 것을 적는다('확인 필요'로 넘기지 않는다).
  아키텍트 메모가 한 줄이어도 뜻을 해석해 세부를 채우고, 모호하면 합리적인 쪽을 골라 결과로 다시 올린다(되묻지 않는다).
- 답을 기다리는 질문이 이미 있으면 새로 묻지 말고 그 질문과 무관한 할 일을 진행하거나 actions를 비운다.
- 담당은 내가 계속 하되 다른 작업자가 가진 자료·기획·확인이 필요하면 `request`(to=작업자 ID, body=무엇이 필요한지·어디쯤 있을지)로 요청한다.
  답이 오면 차례가 나에게 돌아오고 그 답으로 이어서 한다. 답을 기다리는 동안 이 주제는 건드리지 않는다.
- 일 자체를 다른 PC·작업자가 맡아야 하면 `handoff`(to=작업자 ID, body=무엇을 해 달라는지·작업물 위치)로 차례를 넘긴다.
  예: 운영 서버(서버컴)에서 조사한 버그 수정·격리 검증 → 개발컴 작업자, 개발컴에서 검증 끝난 핫픽스의 운영 적용 준비 → 서버컴 작업자.
- 조사는 읽기 도구로 실제 파일을 읽고 근거(경로·줄)를 적는다. 추측은 추측이라고 적는다.
- 작업물 기록은 `work_note`로 남긴다(work_id는 비워 둔다. 실행기가 이 주제의 작업물에 쓴다).
- 메모 수집 주제라면 찾은 메모를 한 건씩 `propose`로 올린다(비밀값은 [가림]). 이미 올린 것은 다시 올리지 않는다.
- 이 단계의 일이 끝났으면 반드시 `state`(status="done")로 끝낸다. body에 결과 요약(무엇을 했나·작업물 위치·시험 방법·권장 다음 단계)을 적는다. 요약이 없으면 거부된다.
- 이번에 다 끝내지 못하면 `note`에 한 일·남은 일·다음 실행에서 이어서 할 첫 단계를 적는다(그래야 실행기가 이어서 깨운다). 진척 없이 같은 말만 반복하면 멈춤으로 아키텍트에게 올라간다.
- 막혀서 더 못 하면(자료·권한·결정이 없음) 이어서 하겠다고 하지 말고 `ask`로 무엇이 필요한지 묻는다.
- 보류(state parked)는 아키텍트만 정한다. 보류가 맞다고 보면 parked를 남기되 body에 이유를 쓴다 — 아키텍트에게 '보류 제안'으로 올라간다.
- 끝냄(done)은 이 단계 담당만 한다. 교차 검토자·요청받은 작업자는 `note`(review/memo)나 `reply`로 끝낸다(done을 남겨도 메모로 바뀐다).

{impl_section(job, workspace)}
{dev_section(job)}
## 단계 가이드
사령탑 워크플로우(command_mode) 주제는 앞의 command 규칙을 따른다. 아래 1~6은 이전 주제에만 적용한다.
1) 담당인데 착수 기록이 없으면 `claim`
2) 진행 베이스가 없으면 `plan` (goal·scope·inputs·first_steps·risks·done_when)
3) 교차 검토자면 진행 베이스를 읽고 `note`(kind="review")로 검토 의견
4) 읽기로 할 수 있는 조사·확인은 해서 결과를 `note`(kind="memo")로
5) 다른 PC 일이 필요하면 `handoff`, 운영 변경 승인이 필요하면 `ask`
6) 이 단계가 끝났으면 `state`(status="done", body=결과 요약) → 아키텍트 관문으로

## 답 형식 (이 JSON 하나만 출력. 다른 글 금지)
{{"summary": "한 줄 요약", "actions": [{{"type": "claim|plan|note|state|work_note|ask|propose|handoff|request|reply|dev_edit|dev_run|dev_revert|command", "kind": null, "body": null, "status": null, "plan": null, "work_id": null, "question": null, "options": null, "title": null, "origin": null, "task": null, "to": null, "file": null, "edits": null, "cmd": null}}]}}
- 각 action의 쓰지 않는 칸은 null로 둔다.
"""


# ---------------------------------------------------------------- AI 실행

def find_claude() -> list[str] | None:
    for name in ("claude.cmd", "claude.exe", "claude"):
        p = shutil.which(name)
        if p:
            return ["cmd", "/c", p] if p.lower().endswith(".cmd") else [p]
    return None


def find_codex() -> str | None:
    p = shutil.which("codex") or shutil.which("codex.exe")
    if p:
        return p
    base = Path(os.environ.get("LOCALAPPDATA", "")) / "OpenAI" / "Codex" / "bin"
    found = sorted(base.glob("*/codex.exe"), key=lambda x: x.stat().st_mtime, reverse=True) if base.is_dir() else []
    return str(found[0]) if found else None


def read_dirs(agent_id: str | None = None) -> list[str]:
    dirs = [d for d in CFG.get("read_dirs", []) if Path(d).is_dir()]
    for d in (r"D:\real-ai-guidelines", str(WORK_PY.parent), *[str(Path(f).parent) for f in rule_files(agent_id)]):
        if Path(d).is_dir() and d not in dirs:
            dirs.append(d)
    return dirs


# AI가 작업 공간에 만들면 다음 실행의 권한·지시를 바꿀 수 있는 파일(설정·지시문). 실행 전후로 치운다.
CONTROL_NAMES = (".claude", ".codex", ".mcp.json", "CLAUDE.md", "CLAUDE.local.md", "AGENTS.md", "AGENTS.override.md", ".git")


def sanitize_workspace(ws: Path | None) -> list[str]:
    """작업 공간 안의 설정·지시 파일을 '_blocked_<이름>'으로 바꿔 무력화한다(지우지 않는다). 바꾼 이름 목록."""
    if not ws or not ws.is_dir():
        return []
    moved = []
    for p in sorted(ws.rglob("*"), key=lambda x: len(x.parts)):
        if p.name in CONTROL_NAMES and p.exists():
            dst = p.with_name(f"_blocked_{p.name.lstrip('.')}")
            n = 1
            while dst.exists():
                dst, n = p.with_name(f"_blocked_{p.name.lstrip('.')}-{n}"), n + 1
            try:
                p.rename(dst)
                moved.append(str(p.relative_to(ws)))
            except OSError:
                pass
    return moved


def neutral_dir() -> Path:
    """읽기 모드 AI의 시작 폴더. 대시보드 폴더(비밀번호 파일이 있는 곳)에서 띄우지 않는다."""
    d = node.node_dir(CFG) / "runner" / "readonly-cwd"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------- 구독 한도 사용률(작업자 화면 '사용량')
# Claude: `claude -p --output-format stream-json`의 rate_limit_event(계정 전체 5시간·주간 사용률).
# Codex: ~/.codex/sessions 기록의 마지막 token_count 이벤트 rate_limits(계정 전체). 둘 다 추가 실행·비용 없이 읽는다.
def _epoch_iso(v) -> str | None:
    try:
        return datetime.fromtimestamp(float(v), KST).isoformat(timespec="seconds")
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def claude_usage(info: dict | None) -> dict | None:
    if not isinstance(info, dict):
        return None
    win = dict(info.get("unifiedWindows") or {})
    if info.get("rateLimitType") and info.get("rateLimitType") not in win:
        win[info["rateLimitType"]] = {"utilization": info.get("utilization"), "resetsAt": info.get("resetsAt")}
    out = {"source": "claude", "status": info.get("status"), "overage": bool(info.get("isUsingOverage")), "seen_at": now().isoformat(timespec="seconds")}
    for k in ("five_hour", "seven_day"):
        w = win.get(k) or {}
        if w.get("utilization") is not None:
            out[k] = {"pct": round(float(w["utilization"]) * 100), "resets_at": _epoch_iso(w.get("resetsAt"))}
    return out if ("five_hour" in out or "seven_day" in out) else None


def codex_usage(home: Path | None = None) -> dict | None:
    base = (home or Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")) / "sessions"
    days = [base / (now() - timedelta(days=i)).strftime("%Y/%m/%d") for i in range(8)]
    files = sorted((f for d in days if d.is_dir() for f in d.glob("*.jsonl")), key=lambda f: f.stat().st_mtime, reverse=True)
    for f in files[:6]:
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
            rl = ((o.get("payload") or {}).get("rate_limits")) if isinstance(o, dict) else None
            if not isinstance(rl, dict):
                continue
            out = {"source": "codex", "plan_type": rl.get("plan_type"), "seen_at": o.get("timestamp"),
                   "status": "limited" if rl.get("rate_limit_reached_type") else "allowed"}
            for key in ("primary", "secondary"):
                x = rl.get(key)
                if isinstance(x, dict) and x.get("used_percent") is not None:
                    slot = "five_hour" if (x.get("window_minutes") or 0) <= 600 else "seven_day"
                    out[slot] = {"pct": round(float(x["used_percent"])), "resets_at": _epoch_iso(x.get("resets_at"))}
            cr = rl.get("credits")
            if isinstance(cr, dict) and cr.get("has_credits"):
                try:
                    out["credits"] = {"balance": round(float(cr.get("balance") or 0)), "unlimited": bool(cr.get("unlimited"))}
                except (TypeError, ValueError):
                    pass
            if "five_hour" in out or "seven_day" in out:
                return out
    return None


def record_usage(agent_id: str | None, info: dict | None) -> None:
    if agent_id and info:
        try:
            node.set_usage(CFG, agent_id, info)
        except Exception as exc:  # noqa: BLE001 — 표시용이라 실패해도 실행은 계속
            log(f"사용량 기록 실패 {agent_id}: {exc}")


def run_ai(agent: dict, prompt: str, tag: str, workspace: Path | None = None) -> tuple[str, str, str]:
    """(결과 JSON 텍스트, 오류, 오류 원문 꼬리) — 오류가 있으면 결과는 빈 문자열.
    workspace가 있으면 '작업 모드': 그 폴더 안에서만 파일을 만들고 고칠 수 있다(실제 프로젝트 폴더는 읽기만)."""
    kind = agent.get("runner") or ("codex" if agent.get("ai") == "gpt" else "claude")
    out_dir = node.node_dir(CFG) / "runner"
    out_dir.mkdir(parents=True, exist_ok=True)
    if kind == "claude":
        exe = find_claude()
        if not exe:
            return "", "claude 명령을 찾지 못함", ""
        # 설정은 사용자 설정만 읽는다(작업 공간·프로젝트에 놓인 설정·훅으로 권한이 넓어지지 않게), 권한 방식 고정, MCP 끔
        # stream-json: 마지막 result 줄이 결과, 중간의 rate_limit_event가 구독 한도 사용률(대시보드 사용량 표시)
        base = exe + ["-p", "--output-format", "stream-json", "--verbose", "--setting-sources", "user", "--permission-mode", "default", "--strict-mcp-config"]
        blocked = [f"{t}(./{n}{'/**' if not n.endswith('.md') and not n.endswith('.json') else ''})" for n in CONTROL_NAMES for t in ("Edit", "Write", "MultiEdit")]
        if workspace:
            args = base + ["--allowedTools", "Read", "Grep", "Glob", "Edit(./**)", "Write(./**)", "MultiEdit(./**)",
                           "--disallowedTools", "Bash", "NotebookEdit", "WebFetch", "WebSearch",
                           "Edit(./NOTES.md)", "Write(./NOTES.md)", "Edit(./MANIFEST.md)", "Write(./MANIFEST.md)", *blocked]
        else:
            args = base + ["--allowedTools", "Read", "Grep", "Glob",
                           "--disallowedTools", "Bash", "Edit", "Write", "MultiEdit", "NotebookEdit", "WebFetch", "WebSearch"]
        for d in read_dirs(agent.get("id")):
            args += ["--add-dir", d]
        try:
            r = subprocess.run(args, input=prompt.encode("utf-8"), capture_output=True, timeout=AI_TIMEOUT, cwd=str(workspace or neutral_dir()),
                               env=ai_env(), creationflags=NO_WINDOW)
        except subprocess.TimeoutExpired:
            return "", "시간 초과", ""
        raw, err = r.stdout.decode("utf-8", errors="replace"), r.stderr.decode("utf-8", errors="replace")
        (out_dir / f"{tag}.claude.json").write_text(raw + "\n--- stderr ---\n" + err, encoding="utf-8")
        obj, limit = None, None
        for ln in raw.splitlines():
            try:
                o = json.loads(ln)
            except ValueError:
                continue
            if isinstance(o, dict) and o.get("type") == "result":
                obj = o
            elif isinstance(o, dict) and o.get("type") == "rate_limit_event":
                limit = o.get("rate_limit_info")
        if obj is None:  # 예전 형식(json 한 덩어리)도 받는다
            try:
                obj = json.loads(raw)
            except ValueError:
                obj = None
        record_usage(agent.get("id"), claude_usage(limit))
        if r.returncode != 0 or (isinstance(obj, dict) and obj.get("is_error")):
            detail = ((obj or {}).get("result") if isinstance(obj, dict) else "") or (raw + "\n" + err)
            return "", f"claude 종료 코드 {r.returncode}", str(detail)[-800:]
        return (obj.get("result", "") if isinstance(obj, dict) else raw), "", ""
    if kind == "codex":
        exe = find_codex()
        if not exe:
            return "", "codex 명령을 찾지 못함", ""
        schema = out_dir / "schema.json"
        schema.write_text(json.dumps(SCHEMA, ensure_ascii=False), encoding="utf-8")
        last = out_dir / f"{tag}.codex.txt"
        mode = ["-s", "workspace-write", "-C", str(workspace)] if workspace else ["-s", "read-only", "-C", str(neutral_dir())]
        args = [exe, "exec", *mode, "--skip-git-repo-check", "--output-schema", str(schema), "-o", str(last), "-"]
        try:
            r = subprocess.run(args, input=prompt.encode("utf-8"), capture_output=True, timeout=AI_TIMEOUT, cwd=str(workspace or neutral_dir()),
                               env=ai_env(), creationflags=NO_WINDOW)
        except subprocess.TimeoutExpired:
            return "", "시간 초과", ""
        out, err = r.stdout.decode("utf-8", errors="replace"), r.stderr.decode("utf-8", errors="replace")
        (out_dir / f"{tag}.codex.log").write_text(out[-20000:] + "\n--- stderr ---\n" + err[-20000:], encoding="utf-8")
        record_usage(agent.get("id"), codex_usage())
        if r.returncode != 0 or not last.exists():
            return "", f"codex 종료 코드 {r.returncode}", err[-800:] or out[-400:]
        return last.read_text(encoding="utf-8", errors="replace"), "", ""
    return "", f"자동 실행 안 함(runner={kind})", ""


# CLI가 실제로 내는 인증 오류 문구만(주제 내용에 '로그인'이 들어가도 오판하지 않게)
AUTH_RE = re.compile(r"(?i)\b401\b|oauth token|token (has )?expired|not logged in|please (run|use) .{0,20}login|run /login|"
                     r"unauthori[sz]ed|invalid (api|x-api)[- ]?key|authentication_error")


def classify(err: str, detail: str, runner: str) -> tuple[str, bool, str]:
    """실패를 (종류, 사람이 해야 하는가, 해결 방법)으로 나눈다."""
    text = f"{err}\n{detail}"
    if err.startswith("답 해석 실패"):
        return "parse", False, "AI 답이 정해진 형식이 아니었습니다. 10분 뒤 다시 시도합니다."
    if "찾지 못함" in err:
        return "tool", True, f"이 PC에 {runner} CLI가 없거나 PATH에 없습니다. 설치·PATH를 확인한 뒤 다음 동기화를 기다리면 됩니다."
    if AUTH_RE.search(text):
        how = "터미널에서 `claude` 실행 → `/login`" if runner == "claude" else "터미널에서 `codex login`"
        return "auth", True, f"{runner} 로그인이 만료됐습니다. 그 PC에서 {how}으로 다시 로그인하세요. 다음 동기화 때 자동으로 다시 시도합니다."
    if "시간 초과" in err:
        return "timeout", False, "20분 안에 끝나지 않았습니다. 10분 뒤 자동으로 다시 시도합니다."
    if re.search(r"UnicodeEncodeError|UnicodeDecodeError|cp949", text):
        return "encoding", False, "출력 인코딩 오류. UTF-8 환경으로 다시 시도합니다."
    if err.startswith("답 해석 실패"):
        return "parse", False, "AI 답이 정해진 형식이 아니었습니다. 10분 뒤 다시 시도합니다."
    return "error", False, "10분 뒤 자동으로 다시 시도합니다. 반복되면 runner.log를 확인하세요."


def parse_actions(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("JSON 없음")
    obj = json.loads(m.group(0))
    if not isinstance(obj, dict) or not isinstance(obj.get("actions"), list):
        raise ValueError("형식 오류")
    obj["summary"] = str(obj.get("summary") or "")
    return obj


# ---------------------------------------------------------------- 기록 적용(검증 후)

def apply(job: dict, result: dict, data: dict | None = None) -> tuple[list[str], list[str]]:
    """(적용한 것, 실패·거부한 것)."""
    agent, t = job["agent"], job.get("topic") or {}
    tid = t.get("id")
    done, failed, work_touched = [], list(job.get("failed") or []), False
    known = {a.get("id") for a in (data or {}).get("agents", [])} | set(node.my_agents(CFG))
    locked = set((data or {}).get("agent_locks") or {})
    for a in result.get("actions", [])[:12]:
        if not isinstance(a, dict):
            failed.append("형식이 틀린 행동 건너뜀")
            continue
        typ = a.get("type")
        body = (a.get("body") or "").strip()
        try:
            import command
            managed = t.get("command_mode") and t.get("stage", "work") == "work"
            if typ == "command":
                authority = None
                if agent == command.DEV and a.get('cmd') in command.DEPUTY_OPS:
                    pw = os.environ.get('REAL_OPS_PASSWORD')
                    latest = load_data(pw) if pw else (data or {})
                    authority = command.delegation(latest)
                command.apply_action(job, a, CFG, known, locked, WORK_PY.parent, authority=authority)
                done.append("command-progress" if a.get("cmd") == "test-progress" else "command")
                continue
            if managed and typ in ("handoff", "request", "reply", "plan"):
                raise ValueError("사령탑 작업표를 사용하세요(command). 별도 인계·진행 베이스는 만들지 않습니다")
            if managed and typ == 'state' and a.get('status') == 'parked' and agent != command.LEAD:
                task = command.active(t.get('command') or command.initial()) or {}
                command.apply_action(job, {'cmd':'blocked','file':task.get('id'),'body':body or '작업자가 보류를 제안했습니다'}, CFG, known, locked, WORK_PY.parent)
                done.append('command')
                continue
            if managed and typ == "state" and a.get("status") == "done":
                if agent != command.LEAD or not command.finished(t.get("command") or command.initial()):
                    raise ValueError("작업자는 command submit, 사령탑은 모든 작업 수락 후 끝냄을 사용하세요")
                back = command.unfinished_return(t)
                if back:  # r5 I-1: 단계 판정이 조용히 버리던 끝냄을 실행기가 이유와 함께 돌려준다
                    if command.pending_return(t, ("work",)):
                        raise ValueError(f"관문 {back.get('id')}에서 아키텍트가 보완을 요청해 되돌아온 조사 주제입니다. 끝냄 전에 "
                                         "command cmd=amend, body=JSON {tasks:[기존 작업 그대로 + 추가 조사 작업]}로 추가 조사를 배정하고, "
                                         "그 작업을 수락한 뒤 끝내세요")
                    raise ValueError(f"관문 {back.get('id')} 보완으로 더하거나 바꾼 조사 작업이 아직 하나도 수락되지 않았습니다. "
                                     "그 작업의 제출을 검수해 accept한 뒤 끝내세요(취소만 하고 끝낼 수 없음)")
            if t.get("command_mode") and typ == "state" and a.get("status") == "done" and t.get("stage") == "test":
                import testflow
                checks = (t.get("command") or {}).get("tests", [])
                if not testflow.finished(checks) or t.get("test_reset_needed"):
                    raise ValueError("모든 필수 시험 결과를 기록하고 통과해야 합니다")
                for check in checks:
                    command.verify_evidence(WORK_PY.parent, check.get("evidence", []))
            if t.get("command_mode") and typ == "ask":
                if agent != command.LEAD:
                    if managed:
                        action = {"cmd": "blocked", "file": (command.active(t.get("command") or command.initial()) or {}).get("id"),
                                  "body": a.get("question") or body}
                        command.apply_action(job, action, CFG, known, locked, WORK_PY.parent)
                        done.append("command")
                        continue
                    if not (t.get("open_request") or {}).get("id"):
                        node.add_topic_record(CFG, tid, agent, "request", to=command.LEAD,
                                              req_id=node.new_req_id(agent), body=(a.get("question") or body)[:4000])
                        done.append("request")
                    continue
                q = a.get("question") or ""
                if not all(k in q for k in ("끝낸 일", "결정할 것", "권장")) or len(a.get("options") or []) < 2:
                    raise ValueError("결재 요청에는 끝낸 일·결정할 것·권장과 선택지 2개 이상이 필요합니다")
            if typ == "claim" and tid:
                if t.get("assignee") != agent:  # 담당만 착수한다(검토·요청 처리 중인 작업자의 착수는 중복 착수가 된다)
                    done.append("착수 건너뜀(담당 아님)")
                    continue
                node.add_topic_record(CFG, tid, agent, "claim", status="active", body=body or "자동 실행기: 착수")
            elif typ == "plan" and tid and isinstance(a.get("plan"), dict):
                p = {k: v for k, v in a["plan"].items() if k in ("goal", "scope", "inputs", "first_steps", "risks", "done_when") and v}
                node.add_topic_record(CFG, tid, agent, "plan", plan=p, body=body or "진행 베이스 작성(자동 실행기)")
            elif typ == "note" and tid and body:
                kind = a.get("kind") if a.get("kind") in ("memo", "review", "question", "answer") else "memo"
                node.add_topic_record(CFG, tid, agent, kind, body=body[:6000])
            elif typ == "state" and tid and a.get("status") in ("done", "parked") and agent != stage_doer(job.get("topic") or {}):
                # 그 단계 담당이 아닌 작업자(교차 검토자·요청받은 작업자 등)의 끝냄·보류는 단계를 바꾸지 않는다 → 메모로 남긴다
                node.add_topic_record(CFG, tid, agent, "review" if (job.get("topic") or {}).get("reviewer") == agent else "memo",
                                      body=(f"[{'끝냄' if a['status'] == 'done' else '보류 제안'} — 이 단계 담당이 아니라 메모로 기록] " + (body or "(내용 없음)"))[:6000])
                done.append("끝냄→메모(단계 담당 아님)")
            elif typ == "state" and tid and a.get("status") == "parked":
                # 보류는 아키텍트만 정한다: AI의 보류는 '보류할까요?' 질문으로 바꿔 올린다(아키텍트가 보류를 고르면 실행기가 보류로 기록)
                answered = {x["id"] for x in (data or {}).get("decisions_answered", [])}
                if not any(q.get("_author") == agent and q.get("task_id") == tid and q["id"] not in answered for q in (data or {}).get("decisions_needed", [])):
                    node.add_ask(CFG, agent, tid, f"{PARK_ASK} {body or '(이유 없음)'}"[:1500], ["보류", "계속 진행"])
                done.append("보류→질문")
            elif typ == "state" and tid and a.get("status") == "done" and len(body) < 40:
                failed.append("끝냄 거부: 결과 요약(무엇을 했나·작업물 위치·시험 방법·권장 다음 단계)이 없음 — 다시 깨워 요약을 받음")
                job["redo"] = True
                continue
            elif typ == "state" and tid and a.get("status") == "done" and (job.get("topic") or {}).get("stage") == "prep" \
                    and not (re.search(r"대상 파일\s*[:：]", body) and re.search(r"겹침\s*[:：]", body)):
                failed.append("끝냄 거부: 배포 준비 요약에 '대상 파일:'·'겹침:' 줄이 없음(배포 대기열 겹침 확인에 씀) — 다시 깨워 요약을 받음")
                job["redo"] = True
                continue
            elif typ == "state" and tid and a.get("status") == "done" and opens_gate(job.get("topic") or {}, body) \
                    and not (re.search(r"정할 것", body[:1500]) and re.search(r"권장", body[:1500])):
                # 관문을 여는 끝냄은 맨 앞에 핵심·정할 것·권장이 있어야 한다(아키텍트 2026-10-03 '어디서 찾아보냐'). 없으면 다시 요약을 받는다
                failed.append("끝냄 거부: 맨 앞 3줄(핵심·정할 것·권장)이 없음 — 다시 깨워 요약을 받음")
                job["redo"] = True
                continue
            elif typ == "state" and tid and a.get("status") in STATUSES:
                receipt = {}
                if t.get('command_mode') and a.get('status') == 'done':
                    receipt['command_revision'] = (t.get('command') or {}).get('revision', 0)
                if t.get('command_mode') and a.get('status') == 'done' and t.get('stage') in ('pack','prep'):
                    import release_queue
                    wid = job.get('work_id') or t.get('work_id')
                    package = release_queue.load_package(WORK_PY.parent, wid, tid)
                    if t['stage'] == 'prep':
                        release_queue.require_pin(package, (t.get('package_receipts') or {}).get('pack'))
                        dst = ROOT / '.local' / 'release-candidates' / tid / 'candidate.zip'
                        release_queue.export_packages([package], WORK_PY.parent, dst, batch=tid)
                    receipt.update(package_stage=t['stage'], package_sha256=package['manifest_sha256'])
                node.add_topic_record(CFG, tid, agent, "status", status=a["status"], body=body or f"상태 {a['status']}",
                                      linked_task_id=a.get("task") if a.get("task") and node.REF_RE.match(a["task"]) else None, **receipt)
            elif typ == "handoff" and tid:
                to = (a.get("to") or "").strip()
                if to == agent or to not in known:
                    failed.append(f"넘기기 거부: '{to}'는 작업자 목록에 없음")
                    continue
                if to in locked:
                    failed.append(f"넘기기 거부: '{to}'는 아키텍트가 배정을 잠갔음")
                    continue
                wid = job.get("work_id") or topic_work_id(t)
                node.add_topic_record(CFG, tid, agent, "handoff", to=to, work_id=wid, body=(body or f"{to}에게 넘김")[:2000])
                if wid:
                    r = run_work("note", wid, "--agent", agent, "--kind", "메모", "--body", f"인계 → {to}: {body or '-'}"[:4000])
                    work_touched = work_touched or r.returncode == 0
            elif typ == "request" and tid and body:
                to = (a.get("to") or "").strip()
                if to == agent or to not in known:
                    failed.append(f"요청 거부: '{to}'는 작업자 목록에 없음")
                    continue
                if to in locked:
                    failed.append(f"요청 거부: '{to}'는 아키텍트가 배정을 잠갔음")
                    continue
                if (t.get("open_request") or {}).get("from") == agent:
                    node.add_topic_record(CFG, tid, agent, "memo", body=f"(답을 기다리는 요청에 덧붙임) {body[:1500]}")
                    done.append("request→덧붙임")
                    continue
                node.add_topic_record(CFG, tid, agent, "request", to=to, req_id=node.new_req_id(agent), body=body[:4000])
            elif typ == "reply" and tid and body:
                req = t.get("open_request") or {}
                if req.get("to") != agent:
                    failed.append("답 거부: 나에게 온 열린 요청이 없음")
                    continue
                node.add_topic_record(CFG, tid, agent, "reply", req_id=req["id"], work_id=job.get("work_id"), body=body[:6000])
            elif typ == "ask" and (a.get("question") or "").strip():
                answered = {x["id"] for x in (data or {}).get("decisions_answered", [])}
                waiting = [q for q in (data or {}).get("decisions_needed", [])
                           if q.get("_author") == agent and q.get("task_id") == tid and q["id"] not in answered]
                local = [q for q in node.load_records(CFG).get("asks", []) if q.get("agent") == agent and q.get("topic") == tid
                         and q["id"] not in answered and q["id"] not in {w["id"] for w in waiting}]
                if (waiting or local) and tid:
                    # 같은 주제에 답을 기다리는 질문이 이미 있으면 새로 쌓지 않고 메모로만 남긴다(아키텍트 대기열 중복 방지)
                    node.add_topic_record(CFG, tid, agent, "question", body=f"(이전 질문에 덧붙임) {a['question'][:1500]}")
                    done.append("ask→덧붙임")
                    continue
                node.add_ask(CFG, agent, tid, a["question"], a.get("options") or [])
            elif typ in ("dev_edit", "dev_run", "dev_revert") and tid:
                # 개발 트리 수정·빌드·시험: 개발 권한이 있는 작업자가 이 단계 담당일 때만. 결과는 주제 기록으로 남겨 다음 실행이 읽는다
                if not dev_cfg(agent):
                    failed.append(f"{typ} 거부: 이 작업자는 개발 트리 권한이 없음")
                    continue
                if agent != stage_doer(job.get("topic") or {}):
                    failed.append(f"{typ} 거부: 이 단계 담당만 할 수 있음")
                    continue
                why = dev_blocked(job)
                if why:
                    node.add_topic_record(CFG, tid, agent, "memo", body=f"[실행기 {typ} 거부] {why}")
                    failed.append(f"{typ} 거부: {why}")
                    continue
                try:
                    ok = True
                    if typ == "dev_edit":
                        msg = dev_edit(agent, tid, a, job.get("ws"))
                    elif typ == "dev_run":
                        msg, ok = dev_run(agent, tid, a)
                    else:
                        msg = "; ".join(dev_revert(agent, tid, a.get("file"))) or "되돌릴 것 없음"
                    node.add_topic_record(CFG, tid, agent, "memo", body=f"[실행기 {typ}] {msg}"[:6000])
                    done.append(typ if ok else f"{typ}(실패)")
                    continue
                except Exception as exc:  # noqa: BLE001 — 형식 오류·디스크·권한·실행 오류도 실행 전체를 멈추지 않고 거부로 기록
                    node.add_topic_record(CFG, tid, agent, "memo", body=f"[실행기 {typ} 거부] {exc}"[:2000])
                    failed.append(f"{typ} 거부: {exc}")
                    continue
            elif typ == "propose" and (a.get("title") or "").strip():
                # 주제 진행 중 올린 제안에는 그 주제를 원래 주제로 단다(후속 주제 연결, 2026-10-03)
                if not node.add_proposal(CFG, agent, a["title"], body, a.get("kind") or "기타", "P2", a.get("origin") or "", tid or ""):
                    done.append("propose→이미 올림")
                    continue
            elif typ == "work_note" and body and tid:
                # 작업물 ID는 실행기가 정한다. AI가 적은 ID는 이 주제의 작업물과 같을 때만 받아들인다.
                wid = job.get("work_id") or ensure_work(job, create=True)
                if not wid:
                    failed.append("작업물 메모 실패: 작업물을 만들지 못함")
                    continue
                if a.get("work_id") and a["work_id"] != wid:
                    done.append(f"작업물 ID 바로잡음({a['work_id']}→{wid})")
                kind = a.get("kind") if a.get("kind") in ("메모", "검토", "검증", "질문", "답변", "적용기록") else "메모"
                r = run_work("note", wid, "--agent", agent, "--kind", kind, "--body", body[:6000])
                if r.returncode != 0:
                    failed.append(f"작업물 메모 실패: {(r.stdout or r.stderr).strip()[-300:]}")
                    continue
                work_touched = True
            else:
                done.append(f"건너뜀({typ})")
                continue
            done.append(typ)
        except (SystemExit, ValueError, OSError, TypeError) as exc:  # 행동·파일 검증 실패
            failed.append(f"{typ} 거부: {exc}")
    if work_touched:
        r = run_work("sync", "--agent", agent, "--message", f"자동 실행기 {tid or ''}")
        note_sync(r, done, failed)
    return done, failed


def note_sync(r: subprocess.CompletedProcess, done: list, failed: list):
    """작업물 올리기 결과를 기록한다. 0=다 올림, 3=검사에 걸린 파일만 빼고 올림(보류 목록을 남김), 그 밖=실패."""
    out = (r.stdout or r.stderr or "").strip()
    if r.returncode == 0:
        done.append("작업물 올림")
    elif r.returncode == 3:
        done.append("작업물 올림")
        held = out.split("보류한 파일", 1)[-1]
        if f"작업물 일부 보류{held[:200]}" not in " ".join(failed):  # 같은 보류를 한 실행에 두 번 적지 않게
            failed.append(f"작업물 일부 보류(비밀값 의심 파일은 [가림] 사본이나 patch로): 보류한 파일{held[:400]}")
    else:
        failed.append(f"작업물 올리기 실패: {out[-300:]}")


def clear_inbox(agent_id: str, topic_id: str | None, before: datetime | None = None) -> int:
    """실행기가 처리한 주제의 배정·답 메시지를 수신 폴더 done\\으로 옮긴다(미처리로 남아 오해하지 않게). 지우지 않는다."""
    inbox = (node.my_agents(CFG).get(agent_id) or {}).get("inbox")
    if not inbox or not topic_id or not Path(inbox).is_dir():
        return 0
    moved = 0
    done = Path(inbox) / "done"
    for p in sorted(Path(inbox).glob("*.md")):
        try:
            head = "\n".join(p.read_text(encoding="utf-8-sig", errors="replace").splitlines()[:15])
        except OSError:
            continue
        if before and p.stat().st_mtime >= before.timestamp():
            continue  # 실행 중에 새로 온 답은 다음 실행이 읽도록 남긴다
        mid = re.search(r"^message_id:\s*(\S+)", head, re.M)
        if not mid or not re.match(r"^(DASH-|USR-REPLY-)", mid.group(1)):
            continue
        if not re.search(rf"^(task_id|target):\s*(topic:)?{re.escape(topic_id)}\s*$", head, re.M):
            continue
        done.mkdir(exist_ok=True)
        dst, n = done / p.name, 1
        while dst.exists():
            dst, n = done / f"{p.stem}-{n}{p.suffix}", n + 1
        try:
            p.replace(dst)
            moved += 1
        except OSError:
            pass
    return moved


# ---------------------------------------------------------------- 실행

def state_path(agent: str) -> Path:
    return node.node_dir(CFG) / f"runner-state-{agent}.json"


def load_state(agent: str) -> dict:
    p = state_path(agent)
    if p.exists():
        return node.read_json(p, {}) or {}
    return node.read_json(node.node_dir(CFG) / "runner-state.json", {}) or {}  # 작업자별 분리 전 상태를 이어받는다


def take_lock(lock: Path) -> bool:
    """작업자별 잠금을 한 번에(동시에 두 개가 잡지 못하게) 잡는다. 90분 넘은 잠금은 죽은 것으로 보고 치운다."""
    lock.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return True
        except FileExistsError:
            try:
                if now().timestamp() - lock.stat().st_mtime < 90 * 60:
                    return False
                lock.unlink(missing_ok=True)
            except FileNotFoundError:
                pass
    return False


def run_agent(agent_id: str, pw: str, dry: bool) -> bool:
    """한 작업자 몫을 처리한다. 결과가 생겼으면 True."""
    lock = node.node_dir(CFG) / f"runner-{agent_id}.lock"
    if dry:
        state = load_state(agent_id)
        for j in find_jobs(load_data(pw), state, only=agent_id):
            print(f"[깨울 예정] {j['agent']} ← {j['kind']} {(j.get('topic') or {}).get('id')} {(j.get('topic') or {}).get('title')} · 이유: {j.get('reason')} · {j.get('mode')}")
        return False
    if not take_lock(lock):
        print(f"{agent_id}: 실행 중인 실행기가 있어 건너뜀")
        return False
    produced = False
    state = load_state(agent_id)
    try:
        try:
            data = load_data(pw)
            jobs = find_jobs(data, state, only=agent_id)
            if jobs:
                pull_work_repo()
            for j in jobs:
                try:
                    produced = run_job(j, data, state) or produced
                except Exception as exc:  # noqa: BLE001 — 한 건이 깨져도 기록을 남기고 다음 건으로
                    log(f"  예외: {type(exc).__name__}: {exc}")
                    st = job_state(state, j)
                    if j.get("rid"):
                        try:
                            node.end_run(CFG, j["rid"], result="fail", error=f"실행기 예외 {type(exc).__name__}: {exc}"[:500], error_class="error",
                                         needs_user=False, fix="10분 뒤 자동으로 다시 시도합니다. 반복되면 runner.log를 확인하세요.")
                        except BaseException:  # noqa: BLE001
                            pass
                    if j.get("applied"):  # 이미 기록을 적용했으면 같은 행동을 반복하지 않게 신호를 소비한다
                        mark_done(st, j)
                    else:
                        fail_backoff(st, False, "error", f"실행기 예외 {type(exc).__name__}: {exc}")
                    produced = True
        finally:
            node.write_json(state_path(agent_id), state)
    finally:
        lock.unlink(missing_ok=True)
    return produced


PLAN_BATCH = 5  # 한 번의 모델 호출로 최초 분해하는 최대 주제 수
PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def job_rank(j: dict) -> tuple:
    """한 번에 MAX_PER_RUN건만 돌므로 순서가 곧 우선권이다(아키텍트 지시 45e1a32).
    P0 긴급 → 아키텍트 결정·답이 들어온 안건 → 우선순위 → 오래 기다린 순. 실행 중인 일은 끊지 않고 다음 실행부터 적용된다."""
    t = j.get("topic") or {}
    subs = [x.get("topic") or {} for x in j.get("subjobs") or []]
    pr = min((PRIORITY_ORDER.get(x.get("priority"), 2) for x in subs), default=PRIORITY_ORDER.get(t.get("priority"), 2))
    answer = j.get("kind") in ("answer", "park")
    lane = 0 if pr == 0 else 1 if answer or j.get("decision") else 2
    since = min((str(x.get("status_at") or x.get("created_at") or "") for x in subs), default=str(t.get("status_at") or t.get("created_at") or ""))
    return (lane, pr, 0 if answer else 1 if j.get("kind") in ("plan_batch", "review_batch") else 2, since or "~")  # 같은 우선순위면 최초 분해 묶음 먼저(다른 작업자 일을 연다)


FAIL_STEPS = (10, 30, 60)  # 같은 주제의 연속 실행 실패 재시도 간격(분). 세 번째부터 '환경 차단'


def fail_backoff(st: dict, needs_user: bool, cls: str, err: str):
    """실행 실패가 이어지면 그 안건만 간격을 늘리고 '환경 차단'으로 표시한다(다른 주제는 계속 처리).
    같은 실패를 10분마다 되풀이하지 않는다. 새 입력이 오면 바로 다시 깨우고(find_jobs), 성공하면 풀린다."""
    n = st["fail_n"] = int(st.get("fail_n") or 0) + 1
    mins = max(30 if needs_user else 0, FAIL_STEPS[min(n, len(FAIL_STEPS)) - 1])
    st["retry_after"] = (now() + timedelta(minutes=mins)).isoformat(timespec="seconds")
    st["retry_kind"] = "env" if n >= len(FAIL_STEPS) else "error"
    if n >= len(FAIL_STEPS):
        st["env_block"] = {"since": (st.get("env_block") or {}).get("since") or now().isoformat(timespec="seconds"),
                           "cls": cls, "error": str(err)[:200], "fails": n}


def clear_fail(st: dict):
    for k in ("fail_n", "env_block"):
        st.pop(k, None)


def unplanned(t: dict) -> bool:
    """사령탑이 아직 최초 분해(plan)를 하지 않은 주제: 새 흐름, 진행 단계, 작업 0개, revision 0, 관문·보관·보류·완료 아님."""
    c = t.get("command") or {}
    return bool(t.get("command_mode") and not t.get("archived") and not t.get("gate") and (t.get("stage") or "work") == "work"
                and t.get("status") in ("new", "triage", "ready", "active") and not c.get("tasks") and not c.get("revision"))


def batch_plan_jobs(jobs: list[dict]) -> list[dict]:
    """사령탑 차례인 미분해 주제 일감을 P0·P1 → 오래 기다린 순으로 최대 PLAN_BATCH건씩 '한 번의 호출' 일감으로 묶는다.
    나머지 일감(검수·시험·다른 작업자)은 그대로 둔다."""
    import command
    planq = [j for j in jobs if j["kind"] == "topic" and j["agent"] == command.LEAD and unplanned(j["topic"])]
    if not planq:
        return jobs
    rest = [j for j in jobs if j not in planq]
    planq.sort(key=lambda j: (PRIORITY_ORDER.get(j["topic"].get("priority") or "P2", 2),
                              str(j["topic"].get("status_at") or j["topic"].get("created_at") or ""), j["topic"]["id"]))
    groups = [planq[i:i + PLAN_BATCH] for i in range(0, len(planq), PLAN_BATCH)]
    return [{"kind": "plan_batch", "agent": command.LEAD, "topic": None, "subjobs": g, "mode": "plan",
             "sig": "plan-batch:" + ",".join(x["topic"]["id"] for x in g),
             "reason": f"최초 분해 {len(g)}건 일괄(우선순위·대기순)"} for g in groups] + rest


def roster_text(data: dict) -> str:
    """배분 문맥: 작업자별 가용성·지금 업무량·사용량. 사용량은 확인 시각이 6시간 넘었거나 없으면 '미확인'(추정하지 않는다)."""
    from topics import to_dt
    locks = data.get("agent_locks") or {}
    load: dict[str, int] = {}
    for t in data.get("topics", []):
        if t.get("archived") or t.get("status") in ("done", "dropped", "parked", "backlog"):
            continue
        for x in (t.get("command") or {}).get("tasks") or []:
            if x.get("state") in ("ready", "review", "blocked"):
                load[x.get("assignee")] = load.get(x.get("assignee"), 0) + 1
    rows = []
    for a in data.get("agents", []):
        aid = a.get("id")
        lk = (locks.get(aid) or {}).get("mode")
        seen = a.get("last_seen") or a.get("pc_synced")
        alive = bool(seen) and (now() - to_dt(seen)).total_seconds() < 150 * 60
        u = a.get("usage") or {}
        seen_u = u.get("seen_at") or u.get("at")
        fresh = bool(seen_u) and (now() - to_dt(seen_u)).total_seconds() < 6 * 3600
        parts = [f"{k} 남음 {100 - int(v.get('pct') or 0)}%" + (f"(초기화 {v.get('resets_at')})" if v.get("resets_at") else "")
                 for k, v in u.items() if isinstance(v, dict) and "pct" in v] if fresh else []
        state = "배정 불가(잠금)" if lk else ("신호 없음 — 배정하지 말 것" if not alive else "가능")
        rows.append(f"- {aid} · {a.get('pc_label') or ''} {a.get('label') or ''} · {state} · 맡은 하위 작업 {load.get(aid, 0)}건 · 사용량 "
                    + (", ".join(parts) if parts else "미확인(추정하지 말 것)"))
    return "\n".join(rows) or "(작업자 정보 없음)"


def plan_batch_prompt(subs: list[dict], data: dict) -> str:
    """여러 주제의 최초 분해를 한 번에 쓰는 사령탑 지시문. 답은 주제마다 command plan 하나(task 칸에 주제 ID)."""
    blocks = []
    for j in subs:
        t = j["topic"]
        ctx = t.get("prior_context")
        ctx = json.dumps(ctx, ensure_ascii=False)[:1500] if ctx else "(없음)"
        blocks.append(f"### {t['id']} · {t.get('title')}\n- 우선순위 {t.get('priority') or 'P2'} · 종류 {t.get('kind') or '-'} · 대기 시작 {t.get('status_at') or t.get('created_at')}\n"
                      f"- 이전 작업물: {t.get('reference_work') or t.get('work_id') or '(없음)'} · 재시작 전 주제: {t.get('restart_of') or '(없음)'}\n"
                      f"- 원래 목표·메모:\n{(t.get('body') or '').strip()[:1500]}\n- 이전 문맥: {ctx}")
    ids = ", ".join(j["topic"]["id"] for j in subs)
    return f"""너는 REAL 작업실의 최종 사령탑 server-astra다. 아래 {len(subs)}개 주제는 아직 작업 분해 전(배정 대기)이다.
이번 한 번의 답으로 각 주제의 최초 작업 분해(plan)를 모두 작성한다. 주제마다 따로 판단하고, 한 주제가 애매해도 다른 주제는 정상으로 작성한다.

## 배정 규칙
- 하위 작업은 1~24개. 각 항목: id(영문·숫자·하이픈, 주제 안에서 고유), title, scope, done_when, assignee, depends_on(앞에서 정의한 id만), reviewer(선택).
- size를 꼭 정한다: small=메뉴·문구·설정처럼 작은 일(작업 1~2개, 시험 단계 없이 바로 ★4 실게임), normal=기본, risk=보상·재화·권한·데이터 변경(이때만 교차 검토 작업·추가 시험).
- 작업자 역할: dev-claude = 구현·빌드·격리 시험(개발 트리 권한), dev-astra = 조사·기획·교차 검토, server-claude = 읽기 조사·근거 정리·독립 검토만(운영 쓰기 금지),
  server-astra(너) = 분배·최종 수락/반려만 — 너에게 구현 작업을 배정하지 않는다.
- 검수 실무 위임(선택): 작업에 reviewer(그 작업 담당이 아닌 작업자, 보통 server-claude)를 적으면 제출 뒤 검수 담당이 근거를 대조해 보고하고, 너는 그 보고로 수락/반려만 한다.
- 아래 작업자 현황에서 '배정 불가'·'신호 없음'인 작업자에게 배정하지 않는다. 맡은 작업이 많은 작업자보다 여유 있는 작업자를 고른다.
  사용량이 '미확인'이면 추정하지 말고 업무량만 본다. 같은 계정의 여유를 PC별로 따로 더하지 않는다.
- 실게임 확인이 필요한 구현은 human_test=true(기본). 조사·기획만이면 tests 없이 작업만.
- 범위는 요청 크기에 맞춘다(아키텍트 지시): 완료 기준은 사용자가 보게 될 결과 한두 문장. 단순 메뉴·문구·설정 추가는 구현 작업 1개(+필요하면 짧은 확인 1개), 시험은 그 동작과 직접 영향만.
  무관한 전체 회귀·여러 번의 독립 검토·중복 보고서·단계 쪼개기를 넣지 않는다. 보상·재화·권한·데이터 변경만 위험에 맞게 검증을 더한다.
- 운영 서버 변경은 계획에 넣지 않는다(배포는 ★7 승인 뒤 배포 대기열 → 묶음 배포 대화에서만).

## 작업자 현황(배분 문맥)
{roster_text(data)}

## 주제({ids})
{chr(10).join(blocks)}

## 답 형식(JSON 하나만)
{{"summary": "한 줄 요약", "actions": [{{"type": "command", "cmd": "plan", "task": "<주제 ID>", "body": "<JSON 문자열: {{\"tasks\":[...],\"size\":\"small|normal|risk\",\"human_test\":true,\"test_reason\":\"...\"}}>",
  "kind": null, "status": null, "plan": null, "work_id": null, "question": null, "options": null, "title": null, "origin": null, "to": null, "file": null, "edits": null}}]}}
주제마다 plan 행동은 정확히 하나. task 칸에 그 주제 ID를 넣는다. 다른 행동(note·ask·state 등)은 쓰지 않는다.
"""


def run_plan_batch(j: dict, data: dict, state: dict) -> bool:
    """일괄 최초 분해: 모델 호출 1번 → 주제별로 나눠 기존 검증으로 적용. 빠지거나 틀린 주제만 다음 회차에 다시(채택된 계획은 덮지 않는다)."""
    agent_id = j["agent"]
    agent = node.my_agents(CFG)[agent_id]
    subs = j["subjobs"]
    tag = f"{now():%Y%m%d-%H%M%S}-{agent_id}-plan{len(subs)}"
    rids = {x["topic"]["id"]: node.start_run(CFG, agent_id, x["topic"]["id"], "topic", "plan", j["reason"]) for x in subs}
    log(f"깨움 {agent_id} ← 최초 분해 일괄 {len(subs)}건: {', '.join(rids)}")
    j["runner"] = agent.get("runner") or ("codex" if agent.get("ai") == "gpt" else "claude")
    try:
        return _plan_batch_body(j, data, state, agent, agent_id, subs, tag, rids)
    except Exception as exc:  # noqa: BLE001
        for rid in rids.values():
            node.end_run(CFG, rid, result="fail", error=f"실행기 예외 {type(exc).__name__}: {exc}"[:500], error_class="error",
                         needs_user=False, fix="10분 뒤 자동으로 다시 시도합니다")
        for x in subs:
            st = job_state(state, x)
            st["retry_after"], st["retry_kind"] = (now() + timedelta(minutes=10)).isoformat(timespec="seconds"), "error"
        raise


def _plan_batch_body(j, data, state, agent, agent_id, subs, tag, rids) -> bool:
    text, err, detail = run_ai(agent, plan_batch_prompt(subs, data), tag, None)
    result = None
    if not err:
        try:
            result = parse_actions(text)
        except ValueError as exc:
            err, detail = f"답 해석 실패: {exc}", text[-500:]
    retry = (now() + timedelta(minutes=10)).isoformat(timespec="seconds")
    if err:
        cls, needs_user, fix = classify(err, detail, j["runner"])
        log(f"  실패({cls}): {err} {detail[-200:]!r}")
        node.set_health(CFG, agent_id, cls, f"{err} {detail[-300:]}".strip(), needs_user, fix)
        for x in subs:
            st = job_state(state, x)
            fail_backoff(st, needs_user, cls, err)
            node.end_run(CFG, rids[x["topic"]["id"]], result="fail", error=f"{err} {detail[-300:]}".strip()[:500], error_class=cls, needs_user=needs_user, fix=fix)
        return True
    node.set_health(CFG, agent_id, "ok", "정상 실행")
    by: dict[str, list] = {}
    for a in result.get("actions") or []:
        if isinstance(a, dict):
            by.setdefault(str(a.get("task") or ""), []).append(a)
    ok = 0
    for x in subs:
        t, st = x["topic"], job_state(state, x)
        mine = by.get(t["id"], [])
        plans = [a for a in mine if a.get("type") == "command" and a.get("cmd") == "plan"]
        failed = [f"일괄 계획에서 무시한 행동 {len(mine) - len(plans[:1])}건(plan 하나만 받음)"] if len(mine) > len(plans[:1]) else []
        if not plans:
            failed.append("일괄 계획 답에 이 주제의 plan이 없음 — 다음 회차에 다시")
            done = []
        else:
            act = dict(plans[0])
            act.pop("task", None)
            done, more = apply(dict(x, mode="plan"), {"actions": [act], "summary": result.get("summary") or ""}, data)
            failed += more
        if "command" in done:
            ok += 1
            mark_done(st, x)
            for k in ("retry_after", "retry_kind", "idle_runs", "idle_since"):
                st.pop(k, None)
            clear_fail(st)
        else:
            st["retry_after"], st["retry_kind"] = retry, "slow"
        node.end_run(CFG, rids[t["id"]], result="ok" if "command" in done and not failed else "partial",
                     summary=(result.get("summary") or "")[:500], actions=done[:20], failed=failed[:10])
    log(f"  일괄 분해 결과: {ok}/{len(subs)}건 채택")
    return True


REVIEW_BATCH = 5  # 한 번의 호출로 검수하는 최대 주제 수(아키텍트 10-04 흐름 경량화)
REVIEW_OPS = {"work": ("accept", "revise"), "test": ("test-accept", "test-revise")}


def review_item(t: dict) -> dict | None:
    """사령탑이 수락/반려만 하면 되는 대기 항목: 진행 단계의 제출된 작업(검수 담당 보고가 남았으면 제외) 또는 시험 단계의 통과 제출."""
    import command
    import testflow
    if not t.get("command_mode") or t.get("gate") or t.get("live_session") or t.get("test_reset_needed"):
        return None
    state = t.get("command") or {}
    stage = t.get("stage") or "work"
    try:
        return _review_item(state, stage, command, testflow)
    except (KeyError, TypeError, AttributeError):
        return None  # 필드가 빠진 옛·부분 기록은 묶지 않고 예전처럼 주제 단위로 처리


def _review_item(state, stage, command, testflow):
    if stage == "work":
        x = command.active(state)
        if x and x.get("state") == "review" and not (x.get("reviewer") and not x.get("review")):
            return {"stage": "work", "x": x}
    if stage == "test":
        x = testflow.current(state.get("tests", []))
        if x and x.get("state") == "passed" and not x.get("accepted_by"):
            return {"stage": "test", "x": x}
    return None


def batch_review_jobs(jobs: list[dict]) -> list[dict]:
    """사령탑 차례 중 '수락/반려만 남은' 주제를 최대 REVIEW_BATCH건씩 한 번의 호출로 묶는다(2건 이상일 때만)."""
    import command
    revq = [j for j in jobs if j["kind"] == "topic" and j["agent"] == command.LEAD and review_item(j["topic"])]
    if len(revq) < 2:
        return jobs
    rest = [j for j in jobs if j not in revq]
    revq.sort(key=job_rank)
    groups = [revq[i:i + REVIEW_BATCH] for i in range(0, len(revq), REVIEW_BATCH)]
    out = []
    for g in groups:
        if len(g) == 1:
            out += g
            continue
        out.append({"kind": "review_batch", "agent": command.LEAD, "topic": None, "subjobs": g, "mode": "impl",
                    "decision": any(x.get("decision") for x in g),
                    "sig": "review-batch:" + ",".join(x["topic"]["id"] for x in g), "reason": f"검수 {len(g)}건 일괄(수락/반려만)"})
    return out + rest


def review_batch_prompt(subs: list[dict]) -> str:
    blocks = []
    for j in subs:
        t = j["topic"]
        it = review_item(t)
        x = it["x"]
        res = x.get("result") or {}
        ev = res.get("evidence") or x.get("evidence") or []
        rv = x.get("review") or {}
        blocks.append(
            f"### {t['id']} · {t.get('title')} · 크기 {(t.get('command') or {}).get('size') or 'normal'}\n"
            f"- {'작업' if it['stage'] == 'work' else '시험'} {x['id']} '{x.get('title')}' · 담당 {x.get('assignee')} · 시도 {x.get('attempt')}\n"
            f"- 완료 기준: {x.get('done_when') or x.get('expected') or '-'}\n"
            f"- 제출 요약: {(res.get('summary') or x.get('summary') or '').strip()[:1500]}\n"
            f"- 근거: " + "; ".join(f"{e.get('path')} (SHA256 {str(e.get('sha256'))[:16]}…)" for e in ev[:8]) + "\n"
            + (f"- 검수 담당 보고({rv.get('by')}, {rv.get('verdict')}): {str(rv.get('summary') or '')[:800]}\n" if rv else "")
            + f"- 답할 cmd: {' 또는 '.join(REVIEW_OPS[it['stage']])}, file={x['id']}")
    ids = ", ".join(j["topic"]["id"] for j in subs)
    return f"""너는 REAL 작업실의 최종 사령탑 server-astra다. 아래 {len(subs)}개 주제는 작업자가 결과를 제출했고 너의 수락/반려만 남았다.
이번 한 번의 답으로 주제마다 수락 또는 반려를 하나씩 정한다(아키텍트 10-04: 결재 병목을 줄이는 검수 묶음).

## 검수 기준
- 완료 기준과 제출 요약·근거를 대조한다. 필요하면 근거 파일을 직접 읽는다(읽기만). 실행기가 수락 직전에 근거 SHA256을 다시 확인한다.
- 범위는 요청 크기에 맞춘다: 작은 일은 그 동작과 직접 영향이 확인됐으면 수락. 무관한 추가 검증·재검토를 요구하지 않는다.
- 반려(revise·test-revise)는 고칠 점을 구체적으로 적는다. 수락·반려 모두 body에 이유 한두 문장.
- 확신이 없으면 그 주제만 반려 대신 답에서 빼도 된다(다음에 그 주제만 다시 깨움). 다른 주제는 그대로 처리한다.

## 주제({ids})
{chr(10).join(blocks)}

## 답 형식(JSON 하나만)
{{"summary": "한 줄 요약", "actions": [{{"type": "command", "cmd": "accept|revise|test-accept|test-revise", "task": "<주제 ID>", "file": "<작업·시험 ID>", "body": "이유",
  "kind": null, "status": null, "plan": null, "work_id": null, "question": null, "options": null, "title": null, "origin": null, "to": null, "edits": null}}]}}
주제마다 행동은 정확히 하나. task 칸에 그 주제 ID. 다른 행동은 쓰지 않는다.
"""


def run_review_batch(j: dict, data: dict, state: dict) -> bool:
    """검수 묶음: 모델 호출 1번 → 주제별로 기존 command 검증(근거 해시 재확인 포함)으로 적용. 빠지거나 틀린 주제만 다음 회차에."""
    agent_id = j["agent"]
    agent = node.my_agents(CFG)[agent_id]
    subs = j["subjobs"]
    tag = f"{now():%Y%m%d-%H%M%S}-{agent_id}-review{len(subs)}"
    rids = {x["topic"]["id"]: node.start_run(CFG, agent_id, x["topic"]["id"], "topic", "impl", j["reason"]) for x in subs}
    log(f"깨움 {agent_id} ← 검수 일괄 {len(subs)}건: {', '.join(rids)}")
    j["runner"] = agent.get("runner") or ("codex" if agent.get("ai") == "gpt" else "claude")
    try:
        text, err, detail = run_ai(agent, review_batch_prompt(subs), tag, None)
        result = None
        if not err:
            try:
                result = parse_actions(text)
            except ValueError as exc:
                err, detail = f"답 해석 실패: {exc}", text[-500:]
        if err:
            cls, needs_user, fix = classify(err, detail, j["runner"])
            log(f"  실패({cls}): {err} {detail[-200:]!r}")
            node.set_health(CFG, agent_id, cls, f"{err} {detail[-300:]}".strip(), needs_user, fix)
            for x in subs:
                fail_backoff(job_state(state, x), needs_user, cls, err)
                node.end_run(CFG, rids[x["topic"]["id"]], result="fail", error=f"{err} {detail[-300:]}".strip()[:500], error_class=cls, needs_user=needs_user, fix=fix)
            return True
        node.set_health(CFG, agent_id, "ok", "정상 실행")
        by: dict[str, list] = {}
        for a in result.get("actions") or []:
            if isinstance(a, dict):
                by.setdefault(str(a.get("task") or ""), []).append(a)
        ok = 0
        for x in subs:
            t, st = x["topic"], job_state(state, x)
            it = review_item(t)
            allowed = REVIEW_OPS[it["stage"]] if it else ()
            mine = by.get(t["id"], [])
            acts = [a for a in mine if a.get("type") == "command" and a.get("cmd") in allowed]
            failed = [f"검수 묶음에서 무시한 행동 {len(mine) - len(acts[:1])}건(수락/반려 하나만 받음)"] if len(mine) > len(acts[:1]) else []
            done = []
            if acts:
                act = dict(acts[0])
                act.pop("task", None)
                done, more = apply(dict(x, mode="impl"), {"actions": [act], "summary": result.get("summary") or ""}, data)
                failed += more
            else:
                failed.append("검수 묶음 답에 이 주제의 수락/반려가 없음 — 다음 회차에 이 주제만 다시")
            if "command" in done:
                ok += 1
                mark_done(st, x)
                for k in ("retry_after", "retry_kind", "idle_runs", "idle_since"):
                    st.pop(k, None)
                clear_fail(st)
            node.end_run(CFG, rids[t["id"]], result="ok" if "command" in done and not failed else "partial",
                         summary=(result.get("summary") or "")[:500], actions=done[:20], failed=failed[:10])
        log(f"  검수 일괄 결과: {ok}/{len(subs)}건 처리")
        return True
    except Exception as exc:  # noqa: BLE001
        for rid in rids.values():
            node.end_run(CFG, rid, result="fail", error=f"실행기 예외 {type(exc).__name__}: {exc}"[:500], error_class="error",
                         needs_user=False, fix="10분 뒤 자동으로 다시 시도합니다")
        for x in subs:
            fail_backoff(job_state(state, x), False, "error", f"실행기 예외 {type(exc).__name__}: {exc}")
        raise


def job_state(state: dict, j: dict) -> dict:
    """주제 단위 상태(하루 한도·재시도). 주제 없는 질문의 답은 그 신호 단위로."""
    t = j.get("topic") or {}
    return state.setdefault("topics", {}).setdefault(t.get("id") or j["sig"], {})


def mark_done(st: dict, j: dict):
    """이 단계를 처리했다고 남긴다. 답 반영은 주제의 단계 신호를 건드리지 않는다(다음 동기화에 같은 주제가 또 깨지 않게)."""
    if j["kind"] == "topic":
        st["last_sig"], st["last_parts"] = j["sig"], j.get("parts") or st.get("last_parts")


PARK_ASK = "[보류 제안] 이 주제를 보류할까요?"  # AI의 보류 → 아키텍트 질문(앞머리로 알아본다)
ARCH_PARK = "[아키텍트 보류 결정]"  # 아키텍트가 '보류'를 고른 뒤 실행기가 남기는 보류 기록(엔진은 이 표시가 있는 AI 보류만 받는다)


def opens_gate(t: dict, body: str) -> bool:
    """이 끝냄이 아키텍트 관문을 여나: 자체 시험(→★4)·배포본(→★7)·운영 반영(→★9)·실게임 수정 대화(→★4), 조사 주제 진행(→결과 확인).
    구현 주제의 진행 끝냄(→ 자체 시험, 관문 없음)은 아니다."""
    from topics import is_research
    if t.get("stage") == "prep":
        return False  # 배포 준비 끝냄은 관문이 아니라 배포 대기열로(형식은 따로 검사: 대상 파일·겹침 줄)
    if t.get("live_session") or t.get("stage") in ("test", "pack", "deploy"):
        return True
    return is_research(t, body)


def stage_doer(t: dict) -> str | None:
    """지금 단계를 끝낼 수 있는 작업자: 실게임 대화 단계는 개발컴 Claude, 시험·배포본·운영 반영은 단계 담당, 진행은 담당."""
    from topics import LIVE_AGENT
    if t.get("live_session"):
        return LIVE_AGENT
    if t.get('command_mode') and t.get('stage') == 'test':
        if t.get('test_reset_needed'): return 'server-astra'
        import testflow
        check=testflow.current((t.get('command') or {}).get('tests',[]))
        if check:
            return 'server-astra' if t.get('test_reset_needed') or check['state'] in ('blocked','passed') else check['assignee']
        return 'server-astra'
    if t.get("stage") in ("test", "pack", "prep", "deploy") and t.get("stage_owner"):
        return t["stage_owner"]
    if t.get("command_mode") and t.get("stage", "work") == "work":
        import command
        return command.turn(t.get("command") or command.initial())
    return t.get("assignee")


def note_skip(st: dict, agent_id: str, tid: str, reason: str):
    """건너뜀을 주제 상태에 센다. 같은 사유는 처음 한 번과 60회마다만 로그에 남긴다(매분 같은 줄이 쌓이지 않게).
    3회 넘게 같은 사유로 건너뛰면 대시보드에 '실행기 멈춤'으로 올라간다(queue_summary → stalled)."""
    if st.get("skip_reason") != reason:
        st.update(skip_reason=reason, skip_count=1, skip_since=now().isoformat(timespec="seconds"))
        log(f"건너뜀 {agent_id} ← {tid}: {reason}")
        return
    st["skip_count"] = st.get("skip_count", 1) + 1
    if st["skip_count"] % 60 == 0:
        log(f"건너뜀 {agent_id} ← {tid}: {reason} (같은 사유 {st['skip_count']}회째, {st.get('skip_since')}부터)")


def run_job(j: dict, data: dict, state: dict) -> bool:
    if j.get("kind") == "plan_batch":
        return run_plan_batch(j, data, state)
    if j.get("kind") == "review_batch":
        return run_review_batch(j, data, state)
    if j.get("kind") == "batch":
        import release_queue
        rows = []
        try:
            if not re.fullmatch(r"R-\d{8}(-[0-9a-z]{1,8})?", j["batch"]):
                raise ValueError("묶음 ID 오류")
            rows = release_queue.select_batch(data, j["batch"])
            packages = [release_queue.load_topic_package(WORK_PY.parent, t) for t in rows]
            dest = ROOT / ".local" / "release-batches" / (j["batch"] + ".zip")
            receipt = release_queue.export_packages(packages, WORK_PY.parent, dest, j["batch"])
            node.write_json(dest.with_suffix(".json"), receipt)
            state.setdefault("batches", {})[j["batch"]] = {"fingerprint": j["fingerprint"], "result": receipt}
            for t in rows:
                node.add_topic_record(CFG, t["id"], "server-astra", "memo", body=f"[묶음 준비] {j['batch']} · ZIP SHA256 {receipt['sha256']} · 운영 미적용. 서버컴 .local/release-batches에서 직접 검토 가능")
        except (ValueError, OSError, TypeError, KeyError) as exc:
            state.setdefault("batches", {})[j["batch"]] = {"error": str(exc), "fingerprint": j["fingerprint"], "requires_change": True}
            for t in rows:
                node.add_topic_record(CFG, t["id"], "server-astra", "memo", body=f"[묶음 준비 실패] {exc}. 운영 미적용")
        return True
    agent_id = j["agent"]
    agent = node.my_agents(CFG)[agent_id]
    t = j.get("topic") or {}
    st = job_state(state, j)
    if j["kind"] == "park":  # 아키텍트가 '보류'를 고른 보류 질문: AI 없이 보류로 기록
        if t.get("id") and t.get("status") in ACTIVE:
            node.add_topic_record(CFG, t["id"], agent_id, "status", status="parked", body=f"{ARCH_PARK} {j['answer'].get('note') or ''}".strip())
            log(f"보류 기록 {agent_id} ← {t['id']}: 아키텍트가 보류를 고름")
        state.setdefault("answers_used", []).append(j["ask"]["id"])
        return True
    # 실행 직전 재확인: 그 사이 대화 세션이 잡았거나 이 PC에서 끝낸 주제는 건너뛴다
    if t.get("id"):
        if t["id"] in node.active_holds(CFG):
            note_skip(st, agent_id, t["id"], "대화 세션이 잡고 있음")
            return False
        # 허브는 방금 같은 기록으로 판정했으니 다시 덮어 보지 않는다(엔진 규칙 없이 덮으면 이관·관문 판정을 거스른다).
        # 노드는 게시본보다 나중에 이 PC에서 남긴 기록만 덮어 본다. 같은 사유로 3번 넘게 건너뛰면 허브 판정을 믿고 실행한다
        if (CFG.get("pc") or {}).get("role") != "hub" and (st.get("skip_count") or 0) < 3:
            fresh = {"topics": [copy.deepcopy(t)], "meta": data.get("meta", {}), "agents": data.get("agents", [])}
            overlay_local(fresh, node.load_records(CFG), only_after_gen=True)
            if fresh["topics"][0].get("status") in ("done", "parked", "dropped"):
                note_skip(st, agent_id, t["id"], f"이 PC 기록상 이미 {fresh['topics'][0]['status']}")
                mark_done(st, j)
                return False
    for k in ("skip_reason", "skip_count", "skip_since"):  # 실제로 깨우면 건너뜀 기록은 지운다
        st.pop(k, None)
    if (j["kind"] == "answer" and (j.get("ask") or {}).get("kind") in ("stall", "consultation")) or j.get("decision"):
        st["idle_runs"] = 0
        st.pop("idle_since", None)
    started = now()
    tag = f"{started:%Y%m%d-%H%M%S}-{agent_id}-{t.get('id') or 'answer'}"
    log(f"깨움 {agent_id} ← {t.get('id')} {t.get('title')} · 이유: {j.get('reason')} · {j.get('mode')}")
    j["runner"] = agent.get("runner") or ("codex" if agent.get("ai") == "gpt" else "claude")
    j["rid"] = node.start_run(CFG, agent_id, t.get("id"), j["kind"], j.get("mode", "plan"), j.get("reason") or "")
    today = f"{now():%Y%m%d}"
    st["count"] = (st.get("count", 0) + 1) if st.get("day") == today else 1
    st["day"] = today
    ws = None
    if j.get("mode") == "impl":
        wid = ensure_work(j, create=True)
        if wid:
            ws = WORK_PY.parent / "work" / wid / agent_id
            ws.mkdir(parents=True, exist_ok=True)
    else:
        ensure_work(j, create=False)
    blocked = sanitize_workspace(ws)
    grew = False
    text, err, detail = run_ai(agent, build_prompt(j, data, ws, st), tag, ws)
    blocked += sanitize_workspace(ws)  # AI가 만든 설정·지시 파일은 다음 실행 전에 무력화
    result = None
    if not err:
        try:
            result = parse_actions(text)
        except ValueError as exc:
            err, detail = f"답 해석 실패: {exc}", text[-500:]
    if err:
        cls, needs_user, fix = classify(err, detail, j["runner"])
        log(f"  실패({cls}): {err} {detail[-200:]!r}")
        node.set_health(CFG, agent_id, cls, f"{err} {detail[-300:]}".strip(), needs_user, fix)
        node.end_run(CFG, j["rid"], result="fail", error=f"{err} {detail[-300:]}".strip()[:500], error_class=cls,
                     needs_user=needs_user, fix=fix, work_id=j.get("work_id"))
        # 신호는 소비하지 않고 잠시 뒤 다시 시도한다. 사람이 고칠 문제는 30분, 연속 실패는 10→30→60분 + '환경 차단'(r6)
        fail_backoff(st, needs_user, cls, err)
        st["last_error"] = err
        # 실행기 인증·한도 오류는 health와 retry로 처리한다. 업무 실패로 바꿔 다른 AI를 깨우지 않는다.
        return True
    health = ((node.load_records(CFG).get("agents") or {}).get(agent_id) or {}).get("health") or {}
    if health.get("state") != "ok":
        node.set_health(CFG, agent_id, "ok", "정상 실행")
    j["applied"] = True
    j["ws"] = ws
    done, failed = apply(j, result, data)
    if blocked:
        failed.append("작업 공간의 설정·지시 파일을 무력화함: " + ", ".join(blocked[:5]))
    for n in j.get("notices") or []:  # 지시문에 넣어 반영한 공지는 '실행기 반영'으로 확인 표시
        if agent_id not in (n.get("acks") or {}):
            node.ack_notice(CFG, n["id"], agent_id, "runner")
    if ws:  # 작업 공간 결과물 올리기(비밀값 검사 포함)
        r = run_work("sync", "--agent", agent_id, "--message", f"작업 모드 {t.get('id')}")
        note_sync(r, done, failed)
        files = [p for p in ws.rglob("*") if p.is_file() and p.name not in ("NOTES.md", "MANIFEST.md")]
        stopped = any(isinstance(a, dict) and (a.get("type") in ("ask", "handoff", "request", "reply") or (a.get("type") == "state" and a.get("status") in ("done", "parked")))
                      for a in result.get("actions", []))
        grew = len(files) > st.get("files", 0)
        if grew and not stopped:
            st["cont"] = st.get("cont", 0) + 1  # 진척이 있었으니 다음 동기화 때 이어서 깨운다
        st["files"] = len(files)
    # 진척 없음(메모만·빈 답)이면 멈추지 않고 계속 다시 깨운다(계획 모드 포함, 아키텍트에게 묻지 않음).
    # 두 번까지는 다음 동기화 때 바로, 그 뒤로는 30분 → 2시간 간격으로. 하루 횟수 한도는 없다(아키텍트 결정 2026-10-03).
    # 진척 = 상태 변화(착수·끝냄 등)·인계·요청·답·질문·작업 공간 파일 증가·첫 진행 베이스. 3번 연속 진척 없으면 알림(queue_summary idle)
    # 진척은 실제로 적용되고(done) 실제로 바뀐 것만 센다(2026-10-03 검토 P1: 같은 착수·같은 상태 반복, 거부된 행동은 진척이 아니다 —
    # 하루 한도가 없으므로 가짜 진척이면 매 동기화마다 즉시 다시 돈다)
    acts = [a for a in result.get("actions", []) if isinstance(a, dict)]
    applied = set(done)
    as_memo = "끝냄→메모(단계 담당 아님)" in applied  # 단계 담당이 아닌 작업자의 끝냄은 메모로 바뀌었다(상태 변화 아님)
    ended = "state" in applied and not as_memo and any(a.get("type") == "state" and a.get("status") in ("done", "parked") for a in acts)
    settled = bool(applied & {"ask", "handoff", "request", "reply", "보류→질문"}) or ended
    notes = t.get("notes") or []
    first_claim = "claim" in applied and not any(n.get("by") == agent_id and n.get("kind") == "claim" for n in notes)
    # 상태 진척은 시작 단계(새 주제·분류·준비)에서 바뀔 때만: 관문을 지난 주제는 엔진이 상태를 진행 중으로 덮으므로 같은 상태 반복이 매번 '변화'로 보인다
    new_state = "state" in applied and not as_memo and t.get("status") in ("new", "triage", "ready") \
        and any(a.get("type") == "state" and a.get("status") in STATUSES and a.get("status") != t.get("status") for a in acts)
    # 진행 베이스는 담당이 처음 쓰거나 인계받아 새로 쓸 때만(엔진은 담당의 베이스를 고르므로 검토자 plan은 늘 '다른 작업자'로 보인다)
    new_plan = "plan" in applied and agent_id == t.get("assignee") and (not t.get("plan") or t.get("plan_by") != agent_id)
    to_me = ((t.get("open_request") or {}).get("to") == agent_id)
    reviewed = (t.get("reviewer") == agent_id and agent_id != t.get("assignee") and not to_me   # 교차 검토 차례의 검토만
                and (("note" in applied and any(a.get("type") == "note" and a.get("kind") == "review" for a in acts)) or as_memo))
    progressed = settled or grew or first_claim or new_state or new_plan or reviewed or "command" in applied
    backoff = None
    dev_did = any(x in ("dev_edit", "dev_revert") for x in done)  # 고치지 않고 빌드만 반복하는 것은 진척이 아니다
    dev_bad = "dev_run(실패)" in done or any(x.startswith(("dev_edit 거부", "dev_run 거부", "dev_revert 거부")) for x in failed)
    if j.get("redo"):  # 끝냄이 거부됐다(요약 형식·내용): 이번 실행은 진척 없음 — 같은 일을 매번 바로 다시 돌지 않게(검토 P2)
        dev_did = dev_bad = progressed = False
    if dev_did or dev_bad:
        # 실제로 고치거나 빌드했다: 결과를 보고 이어서 하도록 다음 동기화 때 바로 깨운다.
        # 빌드 실패·거부가 연달아 세 번 넘으면 30분 → 2시간 간격으로(같은 실패로 매분 돌지 않게, 2026-10-03 검토 P2)
        st["idle_runs"] = 0
        st["dev_fail"] = (st.get("dev_fail", 0) + 1) if dev_bad and not ("dev_run" in done) else 0
        st["cont"] = st.get("cont", 0) + 1
        if st["dev_fail"] >= 3:
            backoff = 30 if st["dev_fail"] <= 4 else 120
    elif progressed:
        st["idle_runs"] = 0
        if not settled:
            st["cont"] = st.get("cont", 0) + 1  # 진척이 있었으니 다음 동기화 때 이어서
    else:
        # 헛돎(메모만·빈 답·거부된 행동·요약 빠진 끝냄 다시 받기·빌드만 반복): 두 번까지는 다음 동기화 때 바로, 그 뒤로 30분 → 2시간
        st["idle_runs"] = st.get("idle_runs", 0) + 1
        if "dev_run" in done:
            st["dev_fail"] = 0
        if not st.get("idle_since"):
            st["idle_since"] = now().isoformat(timespec="seconds")  # 이번 헛돎이 시작된 때(알림 번호 고정용)
        st["cont"] = st.get("cont", 0) + 1
        if st["idle_runs"] > 2:
            backoff = 30 if st["idle_runs"] <= 4 else 120
    if not st.get("idle_runs"):
        st.pop("idle_since", None)  # 진척이 생기면 헛돎 알림도 지운다
    if j["kind"] == "answer":
        state.setdefault("answers_used", []).extend([j["ask"]["id"], *j.get("older", [])])
    moved = clear_inbox(agent_id, t.get("id"), before=started)
    if moved:
        done.append(f"수신함 정리 {moved}건")
    st.pop("retry_after", None)
    st.pop("retry_kind", None)
    clear_fail(st)
    if backoff:
        st["retry_after"] = (now() + timedelta(minutes=backoff)).isoformat(timespec="seconds")
        st["retry_kind"] = "slow"  # 헛돎·개발 실패 감속: 새 입력이 오면 바로 깨운다(find_jobs)
    mark_done(st, j)
    st["last_result"] = {"summary": result["summary"][:300], "actions": done, "failed": failed, "at": now().isoformat(timespec="seconds")}
    node.end_run(CFG, j["rid"], result="partial" if failed else "ok", summary=result["summary"][:500],
                 actions=done[:20], failed=failed[:10], work_id=j.get("work_id"))
    log(f"  결과: {result['summary'][:200]} · 적용 {', '.join(done) or '없음'}" + (f" · 실패 {'; '.join(failed)}" if failed else ""))
    return True


def consultation_wait(st: dict, parts: dict) -> bool:
    if (st.get("idle_runs") or 0) < IDLE_ALERT_RUNS:
        return False
    last = st.get("last_parts") or {}
    return not last or all(parts.get(k) == last.get(k) for k in ("stage", "mode", "talk", "replies"))


def queue_summary(aid: str, data: dict, state: dict) -> dict:
    """이 작업자 차례인 주제가 지금 왜 돌거나 안 도는지 센다(대시보드 작업자 카드에 '쉬는 중' 대신 보여 준다)."""
    runnable, order = set(), []
    for j in find_jobs(data, copy.deepcopy(state), only=aid):  # 일괄 분해 일감은 묶인 주제들을 각각 '곧 실행'으로
        ids = [x["topic"]["id"] for x in j.get("subjobs") or []] or [(j.get("topic") or {}).get("id") or j["sig"]]
        runnable |= set(ids)
        order += [i for i in ids if i not in order]
    answered = {a["id"] for a in data.get("decisions_answered", [])}
    asking = {q.get("task_id") for q in data.get("decisions_needed", []) if q.get("_author") == aid and q["id"] not in answered
              and q.get("kind") not in ("gate", "stall", "consultation")}  # 자문 요청은 같은 대기 기록으로 유지한다.
    holds, stamp, today = node.active_holds(CFG), now().isoformat(timespec="seconds"), f"{now():%Y%m%d}"
    out = {"total": 0, "runnable": 0, "waiting_answer": 0, "waiting_change": 0, "retry": 0, "env": 0, "held": 0, "stalled": 0}
    items, stalled, idle, env = {}, [], [], []  # 주제별 판정(대시보드 '다음' 문구가 실행기 판정과 같게) · 멈춘 주제 · 헛도는 주제
    for t in data.get("topics", []):
        if t.get("turn") != aid or t.get("status") not in ACTIVE:
            continue
        out["total"] += 1
        st = (state.get("topics") or {}).get(t["id"], {})
        if t["id"] in holds or t.get("live_session") or t.get("deploy_session"):
            code = "held"  # 대화 세션 몫(실게임 시험·8b 배포 단계 포함)
        elif (st.get("skip_count") or 0) >= 3:
            code = "stalled"
            stalled.append({"topic": t["id"], "reason": st.get("skip_reason"), "since": st.get("skip_since")})
        elif t["id"] in runnable:
            code = "runnable"
        elif (st.get("idle_runs") or 0) >= IDLE_ALERT_RUNS:
            code = "waiting_answer"
        elif st.get("env_block") and (st.get("retry_after") or "") > stamp:
            code = "env"  # 같은 실행 실패가 이어져 이 안건만 간격을 둠(다른 주제는 계속 처리)
            env.append({"topic": t["id"], "since": st["env_block"].get("since") or "", "fails": st["env_block"].get("fails"),
                        "error": st["env_block"].get("error") or "", "next": st.get("retry_after")})
        elif (st.get("retry_after") or "") > stamp:
            code = "retry"
        elif t["id"] in asking:
            code = "waiting_answer"
        else:
            code = "waiting_change"  # 이미 처리함 — 변화가 없으면 30분(반복 시 2시간) 뒤 실행기가 다시 깨운다(find_jobs)
        items[t["id"]] = code
        out[code] = out.get(code, 0) + 1
        if (st.get("idle_runs") or 0) >= IDLE_ALERT_RUNS and code == "waiting_answer" and t["id"] not in asking:
            # 자문 답이나 실제 단계 변화가 있을 때 이 안건만 재개한다.
            idle.append({"topic": t["id"], "runs": st["idle_runs"], "since": st.get("idle_since") or "",  # 번호 고정(실행 때마다 바뀌지 않게)
                         "last": ((st.get("last_result") or {}).get("summary") or "")[:200], "next": st.get("retry_after"),
                         "every": 30 if st["idle_runs"] <= 4 else 120})
    out["answers"] = sum(1 for j in find_jobs(data, copy.deepcopy(state), only=aid) if j["kind"] == "answer")
    out["items"], out["stalled"], out["idle"], out["env_blocked"], out["order"] = items, stalled, idle, env, order[:MAX_PER_RUN]
    return out


def publish_queue(aid: str, data: dict, state: dict):
    q = queue_summary(aid, data, state)
    cur = ((node.load_records(CFG).get("agents") or {}).get(aid) or {}).get("queue") or {}
    if {k: v for k, v in cur.items() if k != "at"} == q:
        return  # 그대로면 기록 파일을 건드리지 않는다

    def fn(rec):
        slot = rec["agents"][aid]
        if {k: v for k, v in (slot.get("queue") or {}).items() if k != "at"} != q:  # 숫자가 바뀔 때만(매분 업로드 방지)
            slot["queue"] = {**q, "at": now().isoformat(timespec="seconds")}
    node.update_records(CFG, fn)


def spawn(agent_id: str):
    """작업자마다 따로 띄운다(한 AI가 오래 걸려도 다른 AI가 줄 서지 않게)."""
    subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--agent", agent_id], cwd=str(ROOT), env=child_env(),
                     creationflags=NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--agent", help="이 작업자 몫만 처리")
    ap.add_argument("--password-file")
    args = ap.parse_args()
    global CFG, WORK_PY
    CFG = node.load_cfg()
    WORK_PY = Path(CFG.get("work_repo") or r"D:\real-work") / "work.py"
    if Path(__file__).with_name("STOPPED").exists():  # 2026-10-04 아키텍트 지시: 주제 방식 폐기, 모든 PC 실행기 정지(저장소로 전파)
        print("자동 실행기 정지(STOPPED)")
        return
    if CFG.get("runner_enabled") is False:
        print("자동 실행기 꺼짐(config runner_enabled=false)")
        return
    pw = Path(args.password_file).read_text(encoding="utf-8").strip() if args.password_file else os.environ.get("REAL_OPS_PASSWORD")
    if not pw:
        sys.exit("비밀번호가 필요합니다(REAL_OPS_PASSWORD).")
    os.environ["REAL_OPS_PASSWORD"] = pw  # 따로 띄우는 작업자 실행기에 넘긴다(AI 프로세스에는 넘기지 않음)
    agents = node.my_agents(CFG)
    if args.agent:
        if args.agent not in agents:
            sys.exit(f"이 PC 작업자가 아닙니다: {args.agent}")
        if run_agent(args.agent, pw, args.dry_run):
            publish()
        return
    if args.dry_run:
        for aid in agents:
            run_agent(aid, pw, True)
        return
    # 어느 작업자에게 일이 있는지만 가볍게 보고 각각 띄운다
    data = load_data(pw)
    waiting = []
    for aid in agents:
        try:
            publish_queue(aid, data, load_state(aid))
        except Exception as exc:  # noqa: BLE001 — 표시용이라 실패해도 실행은 계속
            log(f"차례 현황 기록 실패 {aid}: {exc}")
        if (agents[aid].get("runner") or agents[aid].get("ai")) in ("gpt", "codex"):
            record_usage(aid, codex_usage())  # Codex는 대화 세션 사용분도 기록 파일에 남으므로 실행이 없어도 매번 읽는다
        try:
            if now().timestamp() - (node.node_dir(CFG) / f"runner-{aid}.lock").stat().st_mtime < 90 * 60:
                continue
        except FileNotFoundError:
            pass
        if find_jobs(data, load_state(aid), only=aid):
            waiting.append(aid)
    try:  # 개발 트리 작업 정리(백업·로그·빌드 사본): 매 회차 가볍게 확인
        for m in dev_cleanup(data):
            log(f"정리: {m}")
    except Exception as exc:  # noqa: BLE001 — 정리가 실패해도 실행은 계속
        log(f"정리 실패: {exc}")
    for aid in waiting:
        spawn(aid)
    print(f"띄움: {', '.join(waiting)}" if waiting else "깨울 일 없음")


def publish():
    """결과가 생겼으면 다음 정기 동기화를 기다리지 않고 바로 올린다(대시보드에 빨리 반영)."""
    sync = ROOT / "sync.ps1"
    if sync.exists():
        log("결과 바로 올리기: sync.ps1 -FromRunner")
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(sync), "-FromRunner"],
                       cwd=str(ROOT), capture_output=True, timeout=15 * 60, env=child_env())


CFG: dict = {}

if __name__ == "__main__":
    main()
