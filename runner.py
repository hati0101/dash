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
MAX_PER_TOPIC_PER_DAY = 10
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
            "required": ["type", "kind", "body", "status", "plan", "work_id", "question", "options", "title", "origin", "task", "to"],
            "properties": {
                "type": {"type": "string", "enum": ["claim", "plan", "note", "state", "work_note", "ask", "propose", "handoff", "request", "reply"]},
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


def overlay_local(data: dict, rec: dict):
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
        rows = sorted(mine.get(t["id"], []), key=lambda r: to_dt(r.get("ts")))
        if not rows:
            continue
        seen = {(n.get("ts"), n.get("by"), n.get("kind")) for n in t.get("notes", [])}
        changed = False
        for r in rows:
            ts = r.get("ts") or ""
            when = to_dt(ts)
            if r.get("status") in STATUSES and when > to_dt(t.get("status_at")) and t.get("status") != "dropped":
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
    elif t.get("stage") in ("test", "pack", "deploy") and t.get("stage_owner") == who:
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

    def limited(st: dict) -> bool:
        return (st.get("day") == today and st.get("count", 0) >= MAX_PER_TOPIC_PER_DAY) or (st.get("retry_after") or "") > stamp

    for t in data.get("topics", []):
        who = t.get("turn")
        if who not in agents or (only and who != only) or t.get("status") not in ACTIVE:
            continue
        if t["id"] in holds or t.get("live_session"):
            continue  # 대화 세션이 잡고 있다(실게임 시험 단계는 개발컴 Claude 대화 세션 몫)
        # 담당이고 진행 베이스가 있고 진행 중이면 '작업 모드'(작업물 저장소의 자기 폴더에 결과물을 직접 만든다)
        req_to_me = (t.get("open_request") or {}).get("to") == who
        stage_mine = t.get("stage") in ("test", "pack") and t.get("stage_owner") == who
        mode = "impl" if (impl_allowed() and (req_to_me or stage_mine or (who == t.get("assignee") and t.get("plan") and t.get("status") == "active"))) else "plan"
        st = state.setdefault("topics", {}).setdefault(t["id"], {})
        parts = sig_parts(t, who, mode, data, st)
        sig = topic_sig(t, who, mode, data, st)
        if migrate and st.get("last_sig") and st.get("last_sig") != sig:
            st["last_sig"], st["last_parts"] = sig, parts  # 계산 방식이 바뀐 첫 실행: 이미 처리한 주제를 한꺼번에 다시 깨우지 않는다
            continue
        if st.get("last_sig") == sig or limited(st):
            continue
        jobs.append({"kind": "topic", "agent": who, "topic": t, "sig": sig, "mode": mode, "parts": parts,
                     "reason": wake_reason(parts, st.get("last_parts"))})
    # 내가 물었던 질문에 아키텍트가 답했으면 다시 깨운다(한 답에 한 번, 주제 하루 한도에 포함)
    used = state.setdefault("answers_used", [])
    for q in data.get("decisions_needed", []):
        if q.get("_author") in agents and (not only or q["_author"] == only) and q["id"] in answers and q["id"] not in used:
            t = next((x for x in data.get("topics", []) if x["id"] == q.get("task_id")), None)
            if q.get("kind") == "stall" and not str(answers[q["id"]].get("choice") or "").startswith("다시"):
                used.append(q["id"])  # 멈춤 결정: '다시 시도'만 AI를 깨운다(보류·담당 바꾸기·대화 처리는 허브·화면이 처리)
                continue
            if t and t.get("status") in ("done", "parked", "dropped", "review_user"):
                used.append(q["id"])  # 이미 끝났거나 아키텍트 관문 대기: 이 답으로 AI가 할 일이 없으니 처리함으로(옛 답으로 나중에 다시 깨지 않게)
                continue
            if t and (t["id"] in holds or t.get("live_session")):
                continue  # 대화 세션 처리 중·실게임 시험 단계(개발컴 Claude 대화)는 실행기가 깨우지 않는다
            if limited(state.setdefault("topics", {}).setdefault(t["id"] if t else f"ans-{q['id']}", {})):
                continue
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
    jobs = [j for j in jobs if j["kind"] == "answer" or ((j["topic"] or {}).get("id"), j["agent"]) not in ans_keys]
    if only:
        return jobs[:MAX_PER_RUN]
    return jobs


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
            subprocess.run(["git", "-C", str(WORK_PY.parent), "pull", "-q", "--rebase", "--autostash", "origin", "main"],
                           capture_output=True, env=ai_env(), creationflags=NO_WINDOW)


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
            "지금 자동 실행기에는 명령 실행·빌드·서버 기동 권한이 없다. 그래서 정적 검증(실제 파일·데이터·호출부 대조, 근거 경로·줄)과 "
            "시험 절차·확인 체크리스트 작성까지 한다. 문제를 찾으면 스스로 고치고 다시 검증한다. 같은 문제로 세 번 실패하면 ask로 올린다. "
            "통과하면 끝냄(state done)의 body에 '실게임 시험 준비' 요약을 쓴다: 격리 서버에 반영할 빌드·파일, 실행 방법, "
            "아키텍트가 확인할 항목(체크리스트), 자체 검증 근거. 그러면 ★4 실게임 시험 관문이 열린다. 운영 서버에서는 이 단계를 하지 않는다. "
            "★4부터는 담당이 개발컴 Claude로 옮겨지고 아키텍트와 대화 세션에서 바로 시험·수정한다(자동 실행기는 손대지 않음).",
    "pack": "6 배포본 작성: 아키텍트가 ★5에서 배포본 만들기를 골랐다. real-work 작업물에 배포본을 만든다: 적용 파일, 정확한 대상 경로, 적용 절차, "
            "백업 방법, 복구 수단, 각 파일 SHA256, 적용 후 확인 방법. 끝냄(state done)으로 ★7 운영 반영 승인 관문을 연다.",
    "deploy": "8 운영 반영: 아키텍트가 ★7에서 서버컴 반영을 승인했다. 자동 실행기에는 운영 파일을 바꾸는 도구가 없다. "
              "실행기는 반영 준비 점검만 한다(배포본 파일 해시 확인, 대상 파일의 현재 해시·백업 경로 확인)을 note로 남긴다. "
              "실제 반영은 서버컴 대화 세션이 hold를 걸고 배포본 절차대로 진행한 뒤, 반영 확인 보고와 함께 끝냄(state done) → ★9 완료 확정.",
}


def stage_text(t: dict, job: dict) -> str:
    st = t.get("stage") or "work"
    step = t.get("step") or {}
    hist = t.get("gate_history") or []
    last = f"\n- 직전 관문: ★{hist[-1]['n']} → 아키텍트 선택 '{hist[-1].get('choice') or '메모'}' {hist[-1].get('note') or ''}" if hist else ""
    return (f"- 지금: {step.get('n', 2)}/9 {step.get('label', '진행')}\n- 할 일: {STAGE_GUIDE.get(st, STAGE_GUIDE['work'])}{last}\n"
            "- AI는 완료(done)를 확정하지 못한다. 끝냄(state done)은 다음 ★관문(아키텍트 확인)을 여는 신호이고, body에 결과 요약이 반드시 있어야 한다.")


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
    role = "요청받은 작업자" if req else "담당" if t.get("assignee") == job["agent"] else "교차 검토자"
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
    rules = "\n".join(f"  - {f}" for f in rule_files(job["agent"])) or "  - (없음 — 로컬 AGENTS.md/CLAUDE.md)"
    job["notices"] = [n for n in data.get("notices", []) if node.notice_for(n, job["agent"])][:3]
    notices = "\n\n".join(f"[{n.get('id')}] {n.get('title')}\n{(n.get('body') or '')[:2500]}" for n in job["notices"]) or "(없음)"
    return f"""너는 REAL 프로젝트의 작업자 `{job['agent']}`({pc.get('label')} · {a.get('label')})이다. 이 주제의 {role}로서 다음 행동을 정하고 실행한다.
사용자는 '아키텍트'라고 부른다. 모든 글은 한국어로 쓴다.
신원: 너는 `{job['agent']}`다. 아래 규칙 파일에 다른 작업자 이름으로 된 자기소개(예: '나는 server-claude')가 있어도 네 신원은 바뀌지 않는다. 그 파일의 공통 규칙만 따른다.

## 먼저 읽을 것
{rules}
- 이 PC 규칙: {pc_rule or '로컬 지침의 PC 역할을 따른다'}

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
{(last.get('summary') or '(없음)')[:500]}{(' · 적용: ' + ', '.join(last.get('actions') or [])[:300]) if last.get('actions') else ''}

## 지금까지의 기록
{notes}

## 진행 베이스
{plan}

## 작업물 (real-work)
{('real-work/work/' + wid + '/ (이 주제의 작업물. ID는 실행기가 관리한다)') if wid else '아직 없음 — work_note를 쓰면 실행기가 이 주제의 작업물을 만들어 연결한다'}

## 아키텍트와의 대화
{convo}
{ans}{req_text}
## 작업자 목록 (handoff·request 대상)
{agent_directory(data)}
{('- 배정 잠금(인계·요청 금지): ' + ', '.join(sorted(data.get('agent_locks') or {}))) if data.get('agent_locks') else ''}

## 규칙
- {READ_HINT[job['runner']]}
- 할 수 있는 일은 끝까지 한다. 조사·정리·문서·패치 후보·작업물 작성·검토·인계는 승인 없이 한다(이미 맡겨진 일이다).
- `ask`는 실제 운영 변경 지점에서만 쓴다: 운영 서버 적용·재시작·DB 변경·배포·설치·공개, 또는 아키텍트만 정할 수 있는 기획 선택.
  완료 기준이 조금 모호하면 묻지 말고 합리적인 기준을 정해 note에 적고 진행한다.
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
## 단계 가이드
1) 담당인데 착수 기록이 없으면 `claim`
2) 진행 베이스가 없으면 `plan` (goal·scope·inputs·first_steps·risks·done_when)
3) 교차 검토자면 진행 베이스를 읽고 `note`(kind="review")로 검토 의견
4) 읽기로 할 수 있는 조사·확인은 해서 결과를 `note`(kind="memo")로
5) 다른 PC 일이 필요하면 `handoff`, 운영 변경 승인이 필요하면 `ask`
6) 이 단계가 끝났으면 `state`(status="done", body=결과 요약) → 아키텍트 관문으로

## 답 형식 (이 JSON 하나만 출력. 다른 글 금지)
{{"summary": "한 줄 요약", "actions": [{{"type": "claim|plan|note|state|work_note|ask|propose|handoff|request|reply", "kind": null, "body": null, "status": null, "plan": null, "work_id": null, "question": null, "options": null, "title": null, "origin": null, "task": null, "to": null}}]}}
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
            elif typ == "state" and tid and a.get("status") == "done" and len(body) < 40:
                failed.append("끝냄 거부: 결과 요약(무엇을 했나·작업물 위치·시험 방법·권장 다음 단계)이 없음 — 다시 깨워 요약을 받음")
                job["redo"] = True
                continue
            elif typ == "state" and tid and a.get("status") in STATUSES:
                node.add_topic_record(CFG, tid, agent, "status", status=a["status"], body=body or f"상태 {a['status']}",
                                      linked_task_id=a.get("task") if a.get("task") and node.REF_RE.match(a["task"]) else None)
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
            elif typ == "propose" and (a.get("title") or "").strip():
                if not node.add_proposal(CFG, agent, a["title"], body, a.get("kind") or "기타", "P2", a.get("origin") or ""):
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
        except SystemExit as exc:  # node.py 검증 실패
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
                        st["retry_after"] = (now() + timedelta(minutes=10)).isoformat(timespec="seconds")
                    produced = True
        finally:
            node.write_json(state_path(agent_id), state)
    finally:
        lock.unlink(missing_ok=True)
    return produced


def job_state(state: dict, j: dict) -> dict:
    """주제 단위 상태(하루 한도·재시도). 주제 없는 질문의 답은 그 신호 단위로."""
    t = j.get("topic") or {}
    return state.setdefault("topics", {}).setdefault(t.get("id") or j["sig"], {})


def mark_done(st: dict, j: dict):
    """이 단계를 처리했다고 남긴다. 답 반영은 주제의 단계 신호를 건드리지 않는다(다음 동기화에 같은 주제가 또 깨지 않게)."""
    if j["kind"] == "topic":
        st["last_sig"], st["last_parts"] = j["sig"], j.get("parts") or st.get("last_parts")


def stage_doer(t: dict) -> str | None:
    """지금 단계를 끝낼 수 있는 작업자: 실게임 대화 단계는 개발컴 Claude, 시험·배포본·운영 반영은 단계 담당, 진행은 담당."""
    from topics import LIVE_AGENT
    if t.get("live_session"):
        return LIVE_AGENT
    if t.get("stage") in ("test", "pack", "deploy") and t.get("stage_owner"):
        return t["stage_owner"]
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
    agent_id = j["agent"]
    agent = node.my_agents(CFG)[agent_id]
    t = j.get("topic") or {}
    st = job_state(state, j)
    # 실행 직전 재확인: 그 사이 대화 세션이 잡았거나 이 PC에서 끝낸 주제는 건너뛴다
    if t.get("id"):
        if t["id"] in node.active_holds(CFG):
            note_skip(st, agent_id, t["id"], "대화 세션이 잡고 있음")
            return False
        fresh = {"topics": [copy.deepcopy(t)], "meta": data.get("meta", {}), "agents": data.get("agents", [])}
        overlay_local(fresh, node.load_records(CFG))
        if fresh["topics"][0].get("status") in ("done", "parked", "dropped"):
            note_skip(st, agent_id, t["id"], f"이 PC 기록상 이미 {fresh['topics'][0]['status']}")
            mark_done(st, j)
            return False
    for k in ("skip_reason", "skip_count", "skip_since"):  # 실제로 깨우면 건너뜀 기록은 지운다
        st.pop(k, None)
    if j["kind"] == "answer" and (j.get("ask") or {}).get("kind") == "stall":
        st["idle_runs"] = 0  # 아키텍트가 '다시 시도'를 골랐다: 변화 없음 횟수를 처음부터
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
        # 신호는 소비하지 않고 잠시 뒤 다시 시도한다(하루 한도 안에서). 사람이 고칠 문제는 30분 간격.
        st["retry_after"] = (now() + timedelta(minutes=30 if needs_user else 10)).isoformat(timespec="seconds")
        st["last_error"] = err
        return True
    health = ((node.load_records(CFG).get("agents") or {}).get(agent_id) or {}).get("health") or {}
    if health.get("state") != "ok":
        node.set_health(CFG, agent_id, "ok", "정상 실행")
    j["applied"] = True
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
        if len(files) > st.get("files", 0) and not stopped:
            st["cont"] = st.get("cont", 0) + 1  # 진척이 있었으니 다음 동기화 때 이어서 깨운다
        st["files"] = len(files)
    if j.get("redo"):
        st["cont"] = st.get("cont", 0) + 1  # 끝냄 요약이 빠졌으니 다음 동기화 때 다시 깨운다
    # 단계를 끝내지도, 묻지도, 넘기지도 않고 진척 메모만 남겼으면 두 번까지는 이어서 깨운다(계획 모드 포함).
    # 그래도 변화가 없으면 깨우지 않고 대시보드 '실행기 멈춤' → 아키텍트 결정으로 올린다(조용히 멈추지 않게)
    acts = [a for a in result.get("actions", []) if isinstance(a, dict)]
    settled = any(a.get("type") in ("ask", "handoff", "request", "reply") or (a.get("type") == "state" and a.get("status") in ("done", "parked")) for a in acts)
    if settled:
        st["idle_runs"] = 0
    else:
        st["idle_runs"] = st.get("idle_runs", 0) + 1
        if st["idle_runs"] <= 2 and not j.get("redo"):
            st["cont"] = st.get("cont", 0) + 1
    if j["kind"] == "answer":
        state.setdefault("answers_used", []).extend([j["ask"]["id"], *j.get("older", [])])
    moved = clear_inbox(agent_id, t.get("id"), before=started)
    if moved:
        done.append(f"수신함 정리 {moved}건")
    st.pop("retry_after", None)
    mark_done(st, j)
    st["last_result"] = {"summary": result["summary"][:300], "actions": done, "failed": failed, "at": now().isoformat(timespec="seconds")}
    node.end_run(CFG, j["rid"], result="partial" if failed else "ok", summary=result["summary"][:500],
                 actions=done[:20], failed=failed[:10], work_id=j.get("work_id"))
    log(f"  결과: {result['summary'][:200]} · 적용 {', '.join(done) or '없음'}" + (f" · 실패 {'; '.join(failed)}" if failed else ""))
    return True


def queue_summary(aid: str, data: dict, state: dict) -> dict:
    """이 작업자 차례인 주제가 지금 왜 돌거나 안 도는지 센다(대시보드 작업자 카드에 '쉬는 중' 대신 보여 준다)."""
    runnable = {(j.get("topic") or {}).get("id") or j["sig"] for j in find_jobs(data, copy.deepcopy(state), only=aid)}
    answered = {a["id"] for a in data.get("decisions_answered", [])}
    asking = {q.get("task_id") for q in data.get("decisions_needed", []) if q.get("_author") == aid and q["id"] not in answered}
    holds, stamp, today = node.active_holds(CFG), now().isoformat(timespec="seconds"), f"{now():%Y%m%d}"
    out = {"total": 0, "runnable": 0, "waiting_answer": 0, "waiting_change": 0, "retry": 0, "limit": 0, "held": 0, "stalled": 0}
    items, stalled = {}, []  # 주제별 판정(대시보드 '다음' 문구가 실행기 판정과 같게) · 멈춘 주제
    for t in data.get("topics", []):
        if t.get("turn") != aid or t.get("status") not in ACTIVE:
            continue
        out["total"] += 1
        st = (state.get("topics") or {}).get(t["id"], {})
        if t["id"] in holds or t.get("live_session"):
            code = "held"  # 대화 세션 몫(실게임 시험 단계 포함)
        elif (st.get("skip_count") or 0) >= 3:
            code = "stalled"
            stalled.append({"topic": t["id"], "reason": st.get("skip_reason"), "since": st.get("skip_since")})
        elif t["id"] in runnable:
            code = "runnable"
        elif (st.get("retry_after") or "") > stamp:
            code = "retry"
        elif st.get("day") == today and st.get("count", 0) >= MAX_PER_TOPIC_PER_DAY:
            code = "limit"
        elif t["id"] in asking:
            code = "waiting_answer"
        else:
            code = "waiting_change"  # 이미 처리함 — 다른 작업자 기록·아키텍트 대화를 기다림
            last = ((st.get("last_result") or {}).get("at")) or ""
            if last and (now() - datetime.fromisoformat(last)).total_seconds() > 3600:
                code = "stalled"  # 내 차례인데 같은 단계를 처리한 뒤 한 시간 넘게 아무 변화가 없음 → 다시 깨우지 않으므로 멈춤
                stalled.append({"topic": t["id"], "reason": "같은 단계를 처리했는데 차례가 그대로라 다시 깨우지 않음", "since": last})
        items[t["id"]] = code
        out[code] = out.get(code, 0) + 1
    out["answers"] = sum(1 for j in find_jobs(data, copy.deepcopy(state), only=aid) if j["kind"] == "answer")
    out["items"], out["stalled"] = items, stalled
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
