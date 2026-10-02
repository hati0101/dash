"""자동 실행기 — 배정된 일이 이 PC 작업자의 차례가 되면 그 AI를 화면 없이 깨워 처리시킨다.

안전 원칙
- AI에게는 읽기 도구만 준다(Claude: Read/Grep/Glob, Codex: 읽기 전용 샌드박스). AI는 명령을 실행하거나 파일을 고치지 않는다.
- AI는 '다음 행동'을 정해진 JSON으로만 답한다. 실제 기록(착수·진행 베이스·메모·완료·질문·메모 올리기·작업물 메모)은 이 실행기가 검증한 뒤 한다.
- 코드 적용·설치·재시작·DB·배포·운영 변경이 필요하면 AI는 'ask'로 아키텍트에게 묻고 멈춘다. 답은 대시보드 '결정이 필요한 문제'에서 버튼으로 한다.
- 같은 단계는 한 번만 깨운다. 깨우는 기준은 '자기 말고 다른 쪽의 변화'(다른 작업자 기록·아키텍트 답·담당/단계 변화)다.
  자기가 남긴 기록으로 자기를 다시 깨우지 않는다(작업 모드에서 결과물이 늘었을 때만 이어서 깨운다).
- 한 주제는 하루 최대 10번. 한 번 실행에 최대 3건.

  python runner.py            할 일이 있으면 처리
  python runner.py --dry-run  무엇을 깨울지만 보여 줌(실행 안 함)
"""
from __future__ import annotations

import argparse
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

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["summary", "actions"],
    "properties": {
        "summary": {"type": "string"},
        "actions": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["type", "kind", "body", "status", "plan", "work_id", "question", "options", "title", "origin", "task"],
            "properties": {
                "type": {"type": "string", "enum": ["claim", "plan", "note", "state", "work_note", "ask", "propose"]},
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


# ---------------------------------------------------------------- 데이터

def load_data(pw: str) -> dict:
    """허브는 지금 상태로 새로 모으고, 노드는 게시본을 연 뒤 이 PC의 최신 기록을 덮어쓴다."""
    if (CFG.get("pc") or {}).get("role") == "hub":
        import build
        cfg = dict(CFG)
        example = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8-sig"))
        cfg["limits"] = {**example["limits"], **cfg.get("limits", {})}
        return build.build_payload(cfg, pw)
    data = node.decrypt_main(CFG, pw)
    rec = node.load_records(CFG)
    mine = {}
    for r in rec.get("topic_records", []):
        mine.setdefault(r.get("topic"), []).append(r)
    for t in data.get("topics", []):  # 게시 뒤에 이 PC에서 한 기록을 반영
        for r in mine.get(t["id"], []):
            if r.get("ts", "") > (data["meta"].get("generated_at") or ""):
                if r.get("status") in STATUSES:
                    t["status"] = r["status"]
                if r.get("plan"):
                    t["plan"], t["plan_by"] = r["plan"], r["agent"]
                t.setdefault("notes", []).append({"ts": r.get("ts"), "kind": r.get("kind"), "body": r.get("body", ""), "by": r.get("agent")})
    return data


SIG_V = 2


def topic_sig(t: dict, who: str, mode: str, data: dict, st: dict) -> str:
    """깨울지 판단하는 신호. 자기(who)가 남긴 기록은 세지 않는다(자기 재깨움 방지).
    - 단계(착수 전 → 착수 → 진행 베이스)와 모드(읽기/작업)는 한 방향으로만 바뀌므로 단계마다 한 번씩만 깨운다.
    - 다른 작업자 기록 수, 아키텍트·다른 작업자의 대화 수가 늘면 깨운다.
    - cont: 작업 모드에서 결과물이 늘었으면 실행기가 올려 이어서 깨운다(하루 한도 안에서)."""
    notes = t.get("notes", [])
    if who == t.get("assignee"):
        claimed = any(n.get("by") == who and n.get("kind") == "claim" for n in notes)
        stage = "planned" if t.get("plan") else "claimed" if claimed else "new"
    else:
        stage = "review"
    others = sum(1 for n in notes if n.get("by") != who)
    talk = sum(1 for c in data.get("comments", [])
               if (c.get("target") or {}).get("id") == t["id"] and (c.get("_author") or c.get("by")) != who)
    return hashlib.sha1(json.dumps([t["id"], who, stage, mode, others, talk, st.get("cont", 0)],
                                   ensure_ascii=False).encode()).hexdigest()[:12]


def find_jobs(data: dict, state: dict) -> list[dict]:
    agents = node.my_agents(CFG)
    today = f"{now():%Y%m%d}"
    answers = {a["id"]: a for a in data.get("decisions_answered", [])}
    migrate = state.get("sig_v") != SIG_V
    state["sig_v"] = SIG_V
    jobs = []
    for t in data.get("topics", []):
        who = t.get("turn")
        if who not in agents or t.get("status") not in ACTIVE:
            continue
        # 담당이고 진행 베이스가 있고 진행 중이면 '작업 모드'(작업물 저장소의 자기 폴더에 결과물을 직접 만든다).
        # 개발 PC(허브)는 기본 허용, 다른 PC는 config "implement": true일 때만(운영 서버 보호).
        impl_ok = CFG.get("implement", (CFG.get("pc") or {}).get("role") == "hub")
        mode = "impl" if (impl_ok and who == t.get("assignee") and t.get("plan") and t.get("status") == "active" and WORK_PY.exists()) else "plan"
        st = state.setdefault("topics", {}).setdefault(t["id"], {})
        sig = topic_sig(t, who, mode, data, st)
        if migrate and st.get("last_sig") and st.get("last_sig") != sig:
            st["last_sig"] = sig  # 계산 방식이 바뀐 첫 실행: 이미 처리한 주제를 한꺼번에 다시 깨우지 않는다
            continue
        if st.get("last_sig") == sig:
            continue
        if st.get("day") == today and st.get("count", 0) >= MAX_PER_TOPIC_PER_DAY:
            continue
        jobs.append({"kind": "topic", "agent": who, "topic": t, "sig": sig, "mode": mode})
    # 내가 물었던 질문에 아키텍트가 답했으면 다시 깨운다
    for q in data.get("decisions_needed", []):
        if q.get("_author") in agents and q["id"] in answers and q["id"] not in state.setdefault("answers_used", []):
            t = next((x for x in data.get("topics", []) if x["id"] == q.get("task_id")), None)
            jobs.append({"kind": "answer", "agent": q["_author"], "topic": t, "ask": q, "answer": answers[q["id"]], "sig": f"ans-{q['id']}"})
    return jobs[:MAX_PER_RUN]


# ---------------------------------------------------------------- 지시문

READ_HINT = {
    "claude": "읽기는 Read·Grep·Glob 도구로 한다. 이 도구들로 필요한 파일을 직접 열어 확인한다.",
    "codex": "너는 읽기 전용 샌드박스에서 돈다. 읽기 명령(Get-Content, Get-ChildItem, Select-String, rg, type, dir 등)은 실행해도 된다. 쓰기·설치·네트워크·서비스 제어 명령은 막혀 있으니 시도하지 않는다.",
}

def impl_section(job: dict, ws: Path | None) -> str:
    if not ws:
        return ""
    return f"""## 작업 모드 (지금 실제로 일을 한다)
진행 베이스가 있고 진행 중이므로 이번에는 결과물을 직접 만든다.
- 작업 공간: `{ws}` (현재 폴더). **이 폴더 안에서만** 파일을 만들고 고칠 수 있다. 위 규칙의 '파일 수정 금지'는 이 폴더에는 적용되지 않는다.
- 실제 프로젝트 폴더(개발 서버·클라이언트·라운지 소스 등)는 읽기만 한다. 고칠 내용은 작업 공간에 만든다:
  - 새 파일(스크립트·NPC·설정 초안·문서)은 원래 들어갈 상대 경로를 살려 `files/` 아래에
  - 기존 파일 수정은 원본을 읽고 `patch/<파일이름>.diff`(통합 diff, 원본 경로 표기)로
  - 설계·결정 근거·시험 방법은 `DESIGN.md`에
- 한 번에 다 못 끝내면 진행한 만큼 만들고 `note`로 진척과 다음 할 일을 남긴다(다음 동기화 때 이어서 깨운다).
- 결과물이 다 준비되면 `note`로 무엇을 만들었는지·적용 방법·시험 방법을 쓰고, `ask`로 적용 승인을 묻는다
  (선택지 예: "개발 서버에 적용하고 시험" / "수정 요청" / "보류"). 적용은 승인 뒤 별도 단계다.
- 작업 공간 파일은 실행기가 비밀값 검사 후 작업물 저장소(work_id={job.get('work_id')})에 올린다.
"""


def run_work(*args: str) -> subprocess.CompletedProcess:
    """작업물 저장소 도구 실행. 한글 출력이 깨지지 않게 UTF-8로 받는다."""
    env = {**{k: v for k, v in os.environ.items() if k != "REAL_OPS_PASSWORD"}, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    return subprocess.run([sys.executable, str(WORK_PY), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env)


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


def allowed_work_ids(job: dict) -> list[str]:
    ids = set(linked_work_ids((job.get("topic") or {}).get("id")))
    if job.get("work_id"):
        ids.add(job["work_id"])
    return sorted(ids)


def prepare_workspace(job: dict) -> Path | None:
    """작업물 저장소에 이 주제의 작업 폴더를 만든다(FT-날짜-번호/<작업자>/). 실패하면 None(읽기 모드로)."""
    t = job["topic"]
    wid = "FT-" + t["id"][2:]
    base = WORK_PY.parent / "work" / wid
    if not (base / "README.md").exists():
        r = run_work("new", wid, "--agent", job["agent"], "--kind", "기능", "--title", (t.get("title") or wid)[:120], "--topic", t["id"])
        if r.returncode != 0:
            log(f"  작업 폴더 만들기 실패: {r.stdout.strip() or r.stderr.strip()}")
            return None
    ws = base / job["agent"]
    ws.mkdir(parents=True, exist_ok=True)
    job["work_id"] = wid
    return ws


def build_prompt(job: dict, data: dict, workspace: Path | None = None) -> str:
    a = node.my_agents(CFG)[job["agent"]]
    pc = CFG.get("pc", {})
    pcs = (data.get("meta", {}).get("routing", {}).get("pcs") or {})
    pc_rule = (pcs.get(pc.get("id")) or {}).get("note") or ""
    t = job.get("topic") or {}
    comments = [c for c in data.get("comments", []) if (c.get("target") or {}).get("id") == t.get("id")]
    notes = "\n".join(f"- [{n.get('ts', '')[:16]}] {n.get('by')} ({n.get('kind')}): {str(n.get('body', ''))[:600]}" for n in t.get("notes", [])[-15:]) or "(없음)"
    convo = "\n".join(f"- {c.get('_author') or c.get('by')}: {str(c.get('body', ''))[:800]}" for c in comments[-10:]) or "(없음)"
    plan = json.dumps(t.get("plan"), ensure_ascii=False, indent=1) if t.get("plan") else "(아직 없음)"
    role = "담당" if t.get("assignee") == job["agent"] else "교차 검토자"
    work_ids = ", ".join(allowed_work_ids(job)) or "(없음)"
    ans = ""
    if job["kind"] == "answer":
        ans = (f"\n## 아키텍트의 답\n질문: {job['ask'].get('question')}\n답: {job['answer'].get('choice') or ''} {job['answer'].get('note') or ''}\n"
               "이 답에 따라 다음 행동을 정하라. 답이 승인이면 승인된 범위만 한다.\n")
    return f"""너는 REAL 프로젝트의 작업자 `{job['agent']}`({pc.get('label')} · {a.get('label')})이다. 이 주제의 {role}로서 다음 행동을 정한다.
사용자는 '아키텍트'라고 부른다. 모든 글은 한국어로 쓴다.

## 먼저 읽을 것(읽을 수 있으면)
- 공통 지침: D:\\real-ai-guidelines\\FOUNDATION.md (없으면 로컬 AGENTS.md/CLAUDE.md)
- 이 PC 규칙: {pc_rule or '로컬 지침의 PC 역할을 따른다'}

## 주제
- ID: {t.get('id')}  제목: {t.get('title')}
- 유형: {t.get('kind')} · 우선순위: {t.get('priority')} · 상태: {t.get('status')} · 담당: {t.get('assignee')}
- 배분 근거: {t.get('dispatch_reason') or '-'}
- 원래 메모:
{t.get('body') or '(없음)'}

## 지금까지의 기록
{notes}

## 진행 베이스
{plan}

## 연결된 작업물 ID (real-work)
{work_ids}

## 아키텍트와의 대화
{convo}
{ans}
## 규칙
- {READ_HINT[job['runner']]}
- 파일 수정·설치·재시작·DB 변경·배포·네트워크 사용은 하지 않는다(막혀 있다).
- 조사가 필요하면 읽기 도구로 실제 파일을 읽고 근거(경로·줄)를 메모에 적는다. 추측은 추측이라고 적는다.
- 코드 적용·빌드 산출물 설치·서버 재시작·DB 변경·배포·운영 설정 변경이 필요하면 직접 하지 말고 `ask`로 아키텍트에게 질문하고 멈춘다(선택지를 2~4개 준다).
- 작업물 교환 저장소에 남길 내용이 있으면 `work_note`로 남긴다. work_id는 아래 '연결된 작업물 ID'에서만 고른다(비어 있으면 work_note를 쓰지 않는다. ID를 지어내지 않는다).
- 메모 수집 주제라면 찾은 메모를 한 건씩 `propose`로 올린다(비밀값은 [가림]).
- 이미 끝낸 단계는 다시 하지 않는다. 할 일이 없으면 actions를 비워도 된다.

{impl_section(job, workspace)}
## 단계 가이드
1) 담당인데 착수 기록이 없으면 `claim`
2) 진행 베이스가 없으면 `plan` (goal·scope·inputs·first_steps·risks·done_when)
3) 교차 검토자면 진행 베이스를 읽고 `note`(kind="review")로 검토 의견
4) 읽기로 할 수 있는 조사·확인은 해서 결과를 `note`(kind="memo")로
5) 주제가 요구한 일이 끝났으면 `state`(status="done")
6) 승인이 필요하면 `ask`

## 답 형식 (이 JSON 하나만 출력. 다른 글 금지)
{{"summary": "한 줄 요약", "actions": [{{"type": "claim|plan|note|state|work_note|ask|propose", "kind": null, "body": null, "status": null, "plan": null, "work_id": null, "question": null, "options": null, "title": null, "origin": null, "task": null}}]}}
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


def read_dirs() -> list[str]:
    dirs = [d for d in CFG.get("read_dirs", []) if Path(d).is_dir()]
    for d in (r"D:\real-ai-guidelines", r"D:\real-work"):
        if Path(d).is_dir() and d not in dirs:
            dirs.append(d)
    return dirs


def run_ai(agent: dict, prompt: str, tag: str, workspace: Path | None = None) -> tuple[str, str]:
    """(결과 JSON 텍스트, 오류) — 오류가 있으면 결과는 빈 문자열.
    workspace가 있으면 '작업 모드': 그 폴더 안에서만 파일을 만들고 고칠 수 있다(실제 프로젝트 폴더는 읽기만)."""
    kind = agent.get("runner") or ("codex" if agent.get("ai") == "gpt" else "claude")
    out_dir = node.node_dir(CFG) / "runner"
    out_dir.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k != "REAL_OPS_PASSWORD"}  # AI 프로세스에는 비밀번호를 넘기지 않는다
    if kind == "claude":
        exe = find_claude()
        if not exe:
            return "", "claude 명령을 찾지 못함"
        if workspace:
            # 작업 공간(현재 폴더) 안에서만 쓰기 허용. 명령 실행·웹은 막는다.
            args = exe + ["-p", "--output-format", "json", "--allowedTools", "Read", "Grep", "Glob", "Edit(./**)", "Write(./**)", "MultiEdit(./**)",
                          "--disallowedTools", "Bash", "NotebookEdit", "WebFetch", "WebSearch"]
        else:
            args = exe + ["-p", "--output-format", "json", "--allowedTools", "Read", "Grep", "Glob",
                          "--disallowedTools", "Bash", "Edit", "Write", "NotebookEdit", "WebFetch", "WebSearch"]
        for d in read_dirs():
            args += ["--add-dir", d]
        try:
            r = subprocess.run(args, input=prompt.encode("utf-8"), capture_output=True, timeout=AI_TIMEOUT, cwd=str(workspace or ROOT), env=env)
        except subprocess.TimeoutExpired:
            return "", "시간 초과"
        raw = r.stdout.decode("utf-8", errors="replace")
        (out_dir / f"{tag}.claude.json").write_text(raw + "\n--- stderr ---\n" + r.stderr.decode("utf-8", errors="replace"), encoding="utf-8")
        if r.returncode != 0:
            return "", f"claude 종료 코드 {r.returncode}"
        try:
            return json.loads(raw).get("result", ""), ""
        except ValueError:
            return raw, ""
    if kind == "codex":
        exe = find_codex()
        if not exe:
            return "", "codex 명령을 찾지 못함"
        schema = out_dir / "schema.json"
        schema.write_text(json.dumps(SCHEMA, ensure_ascii=False), encoding="utf-8")
        last = out_dir / f"{tag}.codex.txt"
        mode = ["-s", "workspace-write", "-C", str(workspace)] if workspace else ["-s", "read-only", "-C", str(ROOT)]
        args = [exe, "exec", *mode, "--skip-git-repo-check", "--output-schema", str(schema), "-o", str(last), "-"]
        try:
            r = subprocess.run(args, input=prompt.encode("utf-8"), capture_output=True, timeout=AI_TIMEOUT, cwd=str(workspace or ROOT), env=env)
        except subprocess.TimeoutExpired:
            return "", "시간 초과"
        (out_dir / f"{tag}.codex.log").write_text(r.stdout.decode("utf-8", errors="replace")[-20000:] + "\n--- stderr ---\n" +
                                                  r.stderr.decode("utf-8", errors="replace")[-20000:], encoding="utf-8")
        if r.returncode != 0 or not last.exists():
            return "", f"codex 종료 코드 {r.returncode}"
        return last.read_text(encoding="utf-8", errors="replace"), ""
    return "", f"자동 실행 안 함(runner={kind})"


def parse_actions(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("JSON 없음")
    obj = json.loads(m.group(0))
    if not isinstance(obj, dict) or not isinstance(obj.get("actions"), list):
        raise ValueError("형식 오류")
    return obj


# ---------------------------------------------------------------- 기록 적용(검증 후)

WORK_PY = Path(r"D:\real-work\work.py")


def apply(job: dict, result: dict, data: dict | None = None) -> list[str]:
    agent, t = job["agent"], job.get("topic") or {}
    tid = t.get("id")
    done, work_touched = [], False
    for a in result.get("actions", [])[:12]:
        typ = a.get("type")
        body = (a.get("body") or "").strip()
        try:
            if typ == "claim" and tid:
                node.add_topic_record(CFG, tid, agent, "claim", status="active", body=body or "자동 실행기: 착수")
            elif typ == "plan" and tid and isinstance(a.get("plan"), dict):
                p = {k: v for k, v in a["plan"].items() if k in ("goal", "scope", "inputs", "first_steps", "risks", "done_when") and v}
                node.add_topic_record(CFG, tid, agent, "plan", plan=p, body=body or "진행 베이스 작성(자동 실행기)")
            elif typ == "note" and tid and body:
                kind = a.get("kind") if a.get("kind") in ("memo", "review", "question", "answer") else "memo"
                node.add_topic_record(CFG, tid, agent, kind, body=body[:6000])
            elif typ == "state" and tid and a.get("status") in STATUSES:
                node.add_topic_record(CFG, tid, agent, "status", status=a["status"], body=body or f"상태 {a['status']}",
                                      linked_task_id=a.get("task") if a.get("task") and node.REF_RE.match(a["task"]) else None)
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
                node.add_proposal(CFG, agent, a["title"], body, a.get("kind") or "기타", "P2", a.get("origin") or "")
            elif typ == "work_note" and body and a.get("work_id") and WORK_PY.exists():
                kind = a.get("kind") if a.get("kind") in ("메모", "검토", "검증", "질문", "답변", "적용기록") else "메모"
                allowed = allowed_work_ids(job)
                if a["work_id"] not in allowed:
                    done.append(f"작업물 메모 거부: {a['work_id']}는 이 주제에 연결된 작업이 아님({', '.join(allowed) or '연결 없음'})")
                    continue
                r = run_work("note", a["work_id"], "--agent", agent, "--kind", kind, "--body", body[:6000])
                if r.returncode != 0:
                    done.append(f"작업물 메모 실패: {r.stdout.strip() or r.stderr.strip()}")
                    continue
                work_touched = True
            else:
                done.append(f"건너뜀({typ})")
                continue
            done.append(typ)
        except SystemExit as exc:  # node.py 검증 실패
            done.append(f"{typ} 거부: {exc}")
    if work_touched:
        r = run_work("sync", "--agent", agent, "--message", f"자동 실행기 {tid or ''}")
        done.append("작업물 올림" if r.returncode == 0 else f"작업물 올리기 실패: {r.stdout.strip()[-300:]}")
    return done


# ---------------------------------------------------------------- 실행

def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--password-file")
    args = ap.parse_args()
    global CFG
    CFG = node.load_cfg()
    if CFG.get("runner_enabled") is False:
        print("자동 실행기 꺼짐(config runner_enabled=false)")
        return
    pw = Path(args.password_file).read_text(encoding="utf-8").strip() if args.password_file else os.environ.get("REAL_OPS_PASSWORD")
    if not pw:
        sys.exit("비밀번호가 필요합니다(REAL_OPS_PASSWORD).")
    lock = node.node_dir(CFG) / "runner.lock"
    if lock.exists() and (now().timestamp() - lock.stat().st_mtime) < 90 * 60 and not args.dry_run:
        print("실행 중인 실행기가 있어 건너뜀")
        return
    state_path = node.node_dir(CFG) / "runner-state.json"
    state = node.read_json(state_path, {}) or {}
    data = load_data(pw)
    jobs = find_jobs(data, state)
    if not jobs:
        if not args.dry_run:
            node.write_json(state_path, state)  # 신호 계산 방식 이전 표시 등은 저장해 둔다
        print("깨울 일 없음")
        return
    if args.dry_run:
        for j in jobs:
            print(f"[깨울 예정] {j['agent']} ← {j['kind']} {(j.get('topic') or {}).get('id')} {(j.get('topic') or {}).get('title')}")
        return
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(str(os.getpid()))
    try:
        for j in jobs:
            agent = node.my_agents(CFG)[j["agent"]]
            t = j.get("topic") or {}
            tag = f"{now():%Y%m%d-%H%M%S}-{j['agent']}-{t.get('id') or 'answer'}"
            log(f"깨움 {j['agent']} ← {t.get('id')} {t.get('title')}")
            j["runner"] = agent.get("runner") or ("codex" if agent.get("ai") == "gpt" else "claude")
            ws = prepare_workspace(j) if j.get("mode") == "impl" else None
            text, err = run_ai(agent, build_prompt(j, data, ws), tag, ws)
            st = state.setdefault("topics", {}).setdefault(t.get("id") or j["sig"], {})
            today = f"{now():%Y%m%d}"
            st["count"] = (st.get("count", 0) + 1) if st.get("day") == today else 1
            st["day"] = today
            if err:
                log(f"  실패: {err}")
                st["last_error"] = err
                if t.get("id"):  # 대시보드에서도 보이게 남긴다
                    node.add_topic_record(CFG, t["id"], j["agent"], "memo", body=f"자동 실행기: AI를 깨우지 못함 — {err}")
                st["last_sig"] = j["sig"]
                continue
            try:
                result = parse_actions(text)
            except ValueError as exc:
                log(f"  답 해석 실패: {exc}")
                st["last_error"] = f"답 해석 실패: {exc}"
                st["last_sig"] = j["sig"]
                continue
            done = apply(j, result, data)
            if ws:  # 작업 공간 결과물 올리기(비밀값 검사 포함)
                r = run_work("sync", "--agent", j["agent"], "--message", f"작업 모드 {t.get('id')}")
                done.append("작업물 올림" if r.returncode == 0 else f"작업물 올리기 보류: {(r.stdout or r.stderr).strip()[-300:]}")
                files = [p for p in ws.rglob("*") if p.is_file()]
                if t.get("id") and len(files) != st.get("files", 0):  # 파일이 늘었을 때만 기록(같은 단계 반복 깨움 방지)
                    node.add_topic_record(CFG, t["id"], j["agent"], "memo",
                                          body=f"작업물: real-work/work/{j.get('work_id')}/{j['agent']}/ 에 파일 {len(files)}개")
                    stopped = any(a.get("type") == "ask" or (a.get("type") == "state" and a.get("status") in ("done", "parked"))
                                  for a in result.get("actions", []))
                    if len(files) > st.get("files", 0) and not stopped:
                        st["cont"] = st.get("cont", 0) + 1  # 진척이 있었으니 다음 동기화 때 이어서 깨운다
                st["files"] = len(files)
            if j["kind"] == "answer":
                state.setdefault("answers_used", []).append(j["ask"]["id"])
            st["last_sig"] = j["sig"]
            st["last_result"] = {"summary": result.get("summary", "")[:300], "actions": done, "at": now().isoformat(timespec="seconds")}
            log(f"  결과: {result.get('summary', '')[:200]} · 적용 {', '.join(done) or '없음'}")
    finally:
        node.write_json(state_path, state)
        lock.unlink(missing_ok=True)
    # 결과가 생겼으면 다음 정기 동기화를 기다리지 않고 바로 올린다(대시보드에 빨리 반영)
    if any((state.get("topics", {}).get((j.get("topic") or {}).get("id") or j["sig"], {}).get("last_result") or {}).get("actions") for j in jobs):
        sync = ROOT / "sync.ps1"
        if sync.exists():
            log("결과 바로 올리기: sync.ps1 -FromRunner")
            subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(sync), "-FromRunner"],
                           cwd=str(ROOT), capture_output=True, timeout=15 * 60)


CFG: dict = {}

if __name__ == "__main__":
    main()
