"""서버컴 사령탑의 작업 분해·위임·검수. I/O 없는 재생 엔진과 근거 검사.

허브는 이벤트를 운반한다. 명령은 server-astra만, 제출은 배정된 작업자만 가능하다.
한 주제 안에서는 한 작업씩 실행하여 공유 개발 트리의 동시 쓰기를 피한다.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import stat
import testflow
from pathlib import Path, PurePosixPath
from datetime import datetime, timedelta, timezone

LEAD = "server-astra"
DEV = "dev-claude"
VERSION = 1
TASK_ID = re.compile(r"^[a-z][a-z0-9_-]{0,39}$")
DEPUTY_OPS = frozenset(('accept','revise','reassign','test-accept','test-revise','test-reassign','test-release'))


def unavailable(data, aid, at=None):
    """부재 알림은 대행 가능 여부와 독립적이다. 배정만 잠금은 실행 부재가 아니다."""
    at = at or datetime.now(timezone.utc)
    agent = next((a for a in data.get('agents', []) if a.get('id') == aid), None)
    if not agent: return '노드 정보 없음'
    if (data.get('agent_locks', {}).get(aid) or {}).get('mode') == 'all': return '자동 실행 잠금'
    if agent.get('error'): return '노드 동기화 오류'
    seen = agent.get('pc_synced') or agent.get('last_seen')
    try:
        last = datetime.fromisoformat(str(seen).replace('Z','+00:00'))
        if last.tzinfo is None: return '유효한 신호 시각 없음'
        if (at-last).total_seconds() >= 150*60: return '150분 이상 신호 없음'
    except (ValueError,TypeError): return '유효한 신호 시각 없음'
    return None


def delegation(data, at=None):
    """판정에 사용한 상태 스냅샷의 실제 생성 시각을 근거로 사용한다."""
    at = at or datetime.now(timezone.utc)
    agents = {a['id']: a for a in data.get('agents', [])}
    locks = data.get('agent_locks') or {}
    leader = agents.get(LEAD, {})
    if leader.get('error'): return None
    seen = leader.get('pc_synced') or leader.get('last_seen')
    observed = (data.get('meta') or {}).get('generated_at')
    try:
        last = datetime.fromisoformat(str(seen).replace('Z','+00:00'))
        snapshot = datetime.fromisoformat(str(observed).replace('Z','+00:00'))
        if last.tzinfo is None or snapshot.tzinfo is None or not 0 <= (at-snapshot).total_seconds() <= 120: return None
    except (ValueError,TypeError): return None
    if DEV in locks or unavailable(data, DEV, at): return None
    stopped = (locks.get(LEAD) or {}).get('mode') == 'all'
    if not stopped and (snapshot-last).total_seconds() < 150*60: return None
    return {'leader':LEAD,'deputy':DEV,'observed_at':observed,'last_seen':seen,'locked':stopped}


def availability_actions(data, topics, at=None):
    at = at or datetime.now(timezone.utc)
    active_topics = [t for t in topics if t.get('command_mode') and not t.get('archived') and t.get('status') not in ('done','dropped','parked','backlog')]
    if not active_topics: return []
    out = []
    reason = unavailable(data, LEAD, at)
    if reason:
        deputy_reason = unavailable(data, DEV, at)
        if DEV in (data.get('agent_locks') or {}): deputy_reason = '대행 배정 잠금'
        allowed = delegation(data, at) is not None
        if not allowed and not deputy_reason: deputy_reason = '대행 권한 근거 없음·만료 또는 노드 오류'
        title = '사령탑·대행 모두 불가' if not allowed else '사령탑 부재 · 개발컴 검수·배정 대행'
        out.append(dict(id='commander-unavailable',title=title,kind='offline',
            detail=reason + (' / 개발컴: '+deputy_reason if deputy_reason else ' / 최신 신호 근거가 확인된 행동만 대행 가능') + ' · 영향 주제 '+str(len(active_topics))+'건',
            topics=[t['id'] for t in active_topics]))
    stalled = {}
    for t in active_topics:
        who = t.get('turn')
        if who and who != LEAD and unavailable(data, who, at): stalled.setdefault(who, []).append(t['id'])
    for who, ids in stalled.items():
        out.append(dict(id='worker-unavailable-'+who,title='작업자 부재 · 재배정 필요: '+who,kind='offline',topics=ids,
            detail=unavailable(data,who,at)+' · 영향 주제 '+str(len(ids))+'건. 사령탑이 작업표에서 재배정합니다.'))
    return out


def delegated(event):
    proof = event.get('delegation')
    if not isinstance(proof,dict) or event.get('agent') != DEV or event.get('op') not in DEPUTY_OPS:
        return False
    try:
        observed=datetime.fromisoformat(proof['observed_at'].replace('Z','+00:00'))
        issued=datetime.fromisoformat(event['ts'].replace('Z','+00:00'))
        seen=datetime.fromisoformat(proof['last_seen'].replace('Z','+00:00'))
        return (proof.get('leader') == LEAD and proof.get('deputy') == DEV and
                0 <= (issued-observed).total_seconds() <= 120 and
                (proof.get('locked') is True or (observed-seen).total_seconds() >= 150*60))
    except (KeyError,ValueError,TypeError):
        return False


def route_deputy(topic, proof):
    topic.pop('acting_commander', None)
    topic.pop('delegation_reason', None)
    if not proof or not topic.get('command_mode') or topic.get('turn') != LEAD or topic.get('gate') or topic.get('live_session'):
        return
    state=topic.get('command') or initial()
    task=active(state) if topic.get('stage','work') == 'work' else testflow.current(state.get('tests',[])) if topic.get('stage') == 'test' else None
    if task and task.get('state') in ('review','blocked','passed'):
        topic['turn']=DEV
        topic['acting_commander']=DEV
        topic['delegation_reason']='서버컴 신호 끊김 또는 자동 실행 잠금 — 검수·재배정 대행'


def initial():
    return {"version": VERSION, "revision": 0, "tasks": [], "events": [], "rejected": []}


def active(state):
    tasks = state.get("tasks", [])
    for task in tasks:
        if task["state"] in ("review", "blocked"):
            return task
    accepted = {t["id"] for t in tasks if t["state"] in ("accepted", "cancelled")}
    return next((t for t in tasks if t["state"] == "ready" and set(t["depends_on"]) <= accepted), None)


def turn(state):
    task = active(state)
    if task and task["state"] == "review" and task.get("reviewer") and not task.get("review"):
        return task["reviewer"]  # 검수 실무(근거 대조·요약)는 검수 담당, 최종 수락·반려는 사령탑(서버컴 요청 REVIEW-DELEGATION)
    return LEAD if not task or task["state"] in ("review", "blocked") else task["assignee"]


def returned_gate(topic, acts=("work", "test")):
    """아키텍트가 보완·반려로 되돌린 가장 최근 관문(gate_history)."""
    return next((x for x in reversed(topic.get("gate_history") or []) if x.get("act") in acts), None)


def linked(event, gate):
    """이 amend/test-reset이 되돌아온 관문에 대한 처리인가. r4부터는 관문 ID로 잇는다.
    review_gate_id가 없는 옛 기록(r3 게시본이 남긴 것)은 r3 판정 그대로 답 시각 뒤의 기록을 인정한다(열린 ★4 이관 시 전체 재시험 최소화)."""
    if not gate:
        return False
    if "review_gate_id" in event:
        return event["review_gate_id"] == gate.get("id")
    def at(v):
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone(timedelta(hours=9)))
    try:
        return at(event.get("ts")) > at(gate.get("answered_at"))
    except (TypeError, ValueError):
        return False


def pending_return(topic, acts=("work", "test")):
    """되돌아온 관문 중 아직 사령탑이 처리(조사 amend·시험 test-reset)하지 않은 것. 없으면 None."""
    gate = returned_gate(topic, acts)
    if not gate:
        return None
    return None if handled((topic.get("command") or {}).get("events", []), gate) else gate


def _spec(r):
    """validate_tasks가 저장하는 것과 같은 기준으로 정리한 작업 내용(표기 차이·생략한 기본값은 변경이 아님)."""
    return (str(r.get("title") or "").strip()[:200], str(r.get("scope") or "").strip()[:3000], str(r.get("done_when") or "").strip()[:2000],
            r.get("assignee"), tuple(dict.fromkeys(r.get("depends_on") or [])))


def handled(events, gate):
    """되돌아온 관문을 사령탑이 처리한 근거. 시험 반려는 연결된 test-reset({'reset'}),
    조사 보완은 연결된 amend가 새로 더하거나 내용을 바꾼 작업 ID 집합(작업표 그대로인 amend는 빈 집합, r5 검토 P2-3·P3-1)."""
    if not gate:
        return {"none"}
    if gate.get("act") != "work":
        return {"reset"} if any(e.get("op") == "test-reset" and linked(e, gate) for e in events) else set()
    prior, ids = {}, set()
    for e in sorted((x for x in events if x.get("op") in ("plan", "amend")), key=lambda x: x.get("revision") if isinstance(x.get("revision"), int) else -1):
        rows = [r for r in e.get("tasks") or [] if isinstance(r, dict)]
        if e.get("op") == "amend" and linked(e, gate):
            ids |= {r.get("id") for r in rows if r.get("id") not in prior or _spec(r) != _spec(prior[r.get("id")])}
        prior.update({r.get("id"): r for r in rows})
    return ids


def return_cleared(events, gate, tasks):
    """조사 보완이 끝났는가: 보완 amend로 더하거나 바꾼 작업 중 하나 이상이 실제로 수락됨(추가 후 바로 취소는 아님)."""
    ids = handled(events, gate)
    if not gate or gate.get("act") != "work":
        return bool(ids)
    return any(t.get("id") in ids and t.get("state") == "accepted" for t in tasks)


def unfinished_return(topic):
    """끝냄을 받기 전 확인: 되돌아온 조사 주제의 보완이 아직 끝나지 않았으면 그 관문."""
    gate = returned_gate(topic, ("work",))
    state = topic.get("command") or {}
    return None if not gate or return_cleared(state.get("events", []), gate, state.get("tasks", [])) else gate


def finished(state):
    return any(t['state'] == 'accepted' for t in state.get('tasks', [])) and all(t["state"] in ("accepted", "cancelled") for t in state["tasks"])


def validate_tasks(tasks, known):
    if not isinstance(tasks, list) or not 1 <= len(tasks) <= 24:
        raise ValueError("작업은 1~24개여야 합니다")
    result, seen = [], set()
    for raw in tasks:
        if not isinstance(raw, dict):
            raise ValueError("작업 형식 오류")
        tid, who = raw.get("id"), raw.get("assignee")
        if not isinstance(tid, str) or not TASK_ID.fullmatch(tid) or tid in seen:
            raise ValueError("작업 ID 형식 오류 또는 중복")
        if who not in known or who == LEAD:
            raise ValueError("등록된 실행 작업자를 배정하세요. 사령탑은 검수 담당입니다")
        deps = raw.get("depends_on", [])
        if not isinstance(deps, list) or any(not isinstance(d, str) or d not in seen for d in deps):
            raise ValueError("의존 작업은 앞에 정의한 작업이어야 합니다(순환 금지)")
        title, scope, done = (str(raw.get(k) or "").strip() for k in ("title", "scope", "done_when"))
        if not title or not scope or not done:
            raise ValueError("작업 제목·범위·완료 기준이 필요합니다")
        reviewer = raw.get("reviewer") or None
        if reviewer is not None and (reviewer not in known or reviewer in (LEAD, who)):
            raise ValueError("검수 담당은 등록된 작업자이면서 사령탑·작업 담당이 아니어야 합니다(자기 검수 금지)")
        result.append({"id": tid, "assignee": who, "title": title[:200], "scope": scope[:3000],
                       "done_when": done[:2000], "depends_on": list(dict.fromkeys(deps)),
                       "state": "ready", "attempt": 1, "result": None, "feedback": "",
                       **({"reviewer": reviewer} if reviewer else {})})
        seen.add(tid)
    return result


def transition(state, event, known):
    """검증 후 새 상태 반환. revision으로 중복·낡은 응답이 새 작업을 덮지 못하게 한다."""
    if event.get("revision") != state["revision"]:
        raise ValueError("작업 상태가 바뀌었습니다. 최신 기록으로 다시 판단하세요")
    who, op = event.get("agent"), event.get("op")
    result = copy.deepcopy(state)
    task = active(result)
    acting = delegated(event)
    if acting:
        target = task if not str(op).startswith('test-') else testflow.current(result.get('tests',[]))
        if op in ('accept','test-accept') and target and (target.get('assignee') == DEV or (target.get('result') or {}).get('by') == DEV
                                                          or (target.get('review') or {}).get('by') == DEV):
            raise ValueError('대행자는 자기 작업을 수락할 수 없습니다. 다른 작업자에게 재배정해 독립 검증하세요')
        who = LEAD
    if op == "plan":
        if who != LEAD or result["tasks"]:
            raise ValueError("최초 작업 분해는 서버컴 Astra만 할 수 있습니다")
        result["tasks"] = validate_tasks(event.get("tasks"), known)
        result["tests"] = testflow.plan(event.get("tests"), known)
        if not isinstance(event.get("human_test", True), bool):
            raise ValueError("human_test는 true 또는 false여야 합니다")
        if event.get("human_test") is False and not str(event.get("test_reason") or "").strip():
            raise ValueError("실게임 시험 불필요 사유가 필요합니다")
        result["human_test"] = True  # D2: 요청 필드로 ★4를 생략할 수 없다.
        result["test_reason"] = str(event.get("test_reason") or "실게임 확인 필요")[:1000]
    elif op == 'amend':
        if who != LEAD or not str(event.get('body') or '').strip():
            raise ValueError('작업표 변경은 사령탑이 이유를 기록해야 합니다')
        revised = validate_tasks(event.get('tasks'), known)
        prior = {t['id']: t for t in result['tasks']}
        for entry in revised:
            old = prior.get(entry['id'])
            if old and all(entry[k] == old[k] for k in ('title','scope','done_when','assignee','depends_on')):
                reviewer = entry.get('reviewer')
                entry.update(copy.deepcopy(old))
                if reviewer != old.get('reviewer'):
                    entry.pop('review', None)
                    if reviewer: entry['reviewer'] = reviewer
                    else: entry.pop('reviewer', None)
        result['tasks'] = revised
    elif op == 'cancel':
        selected = next((t for t in result['tasks'] if t['id'] == event.get('task_id')), None)
        if who != LEAD or not selected or not str(event.get('body') or '').strip():
            raise ValueError('작업 취소는 사령탑이 대상과 이유를 기록해야 합니다')
        selected.update(state='cancelled', feedback=event['body'])
    elif str(op).startswith("test-"):
        if op == 'test-reassign' and (event.get('to') not in known or not str(event.get('to')).startswith('dev-')):
            raise ValueError('등록된 개발컴 시험 담당자가 필요합니다')
        result["tests"] = testflow.transition(result.get("tests", []), {**event,'agent':who})
        if acting:
            for item in result['tests']:
                if item['id'] == event.get('task_id'):
                    if op == 'test-accept': item.update(accepted_by=DEV,accepted_acting_for=LEAD)
                    if item.get('history'): item['history'][-1].update(agent=DEV,acting_for=LEAD)
    elif op == "submit":
        if not task or task["state"] != "ready" or who != task["assignee"] or event.get("task_id") != task["id"]:
            raise ValueError("지금 배정받은 작업만 제출할 수 있습니다")
        evidence = event.get("evidence")
        if not evidence or not str(event.get("body") or "").strip():
            raise ValueError("제출에는 결과 요약과 파일 근거가 필요합니다")
        if not isinstance(evidence, list) or len(evidence) > 32 or any(
                not isinstance(e, dict) or not isinstance(e.get("path"), str) or
                not re.fullmatch(r"[0-9a-f]{64}", str(e.get("sha256") or "")) for e in evidence):
            raise ValueError("근거 형식 오류")
        task.update(state="review", result={"summary": str(event["body"])[:6000], "evidence": evidence,
                    "by": who, "at": event.get("ts")})
        task.pop("review", None)
    elif op == "review-assign":
        if who != LEAD or not task or event.get("task_id") != task["id"] or task["state"] != "review":
            raise ValueError("검수 담당 지정은 사령탑이 제출된 작업에만 할 수 있습니다")
        to = event.get("to")
        if to not in known or to in (LEAD, task["assignee"], (task.get("result") or {}).get("by")):
            raise ValueError("검수 담당은 등록된 작업자이면서 사령탑·제출자가 아니어야 합니다(자기 검수 금지)")
        task.update(reviewer=to)
        task.pop("review", None)
    elif op == "review-report":
        if not task or task["state"] != "review" or event.get("task_id") != task["id"] or who != task.get("reviewer") or task.get("review"):
            raise ValueError("지금 검수를 맡은 작업자만 검수 보고를 낼 수 있습니다")
        if who in (task["assignee"], (task.get("result") or {}).get("by")):
            raise ValueError("자기 제출물은 검수할 수 없습니다")
        verdict = event.get("verdict")
        if verdict not in ("pass", "fail"):
            raise ValueError("검수 판정은 pass 또는 fail이어야 합니다")
        evidence = event.get("evidence")
        if not str(event.get("body") or "").strip() or not isinstance(evidence, list) or not evidence:
            raise ValueError("검수 보고에는 요약과 근거 파일이 필요합니다")
        task["review"] = {"by": who, "verdict": verdict, "summary": str(event["body"])[:6000], "evidence": evidence, "at": event.get("ts")}
    elif op == "blocked":
        if not task or task["state"] != "ready" or who != task["assignee"] or event.get("task_id") != task["id"]:
            raise ValueError("담당 작업의 문제만 보고할 수 있습니다")
        if not str(event.get("body") or "").strip():
            raise ValueError("막힌 원인이 필요합니다")
        task.update(state="blocked", feedback=str(event["body"])[:3000])
    elif op in ("accept", "revise", "reassign"):
        if who != LEAD or not task or event.get("task_id") != task["id"]:
            raise ValueError("검수·재작업·재배정은 서버컴 Astra만 할 수 있습니다")
        if not str(event.get("body") or "").strip():
            raise ValueError("검수 또는 재배정 이유가 필요합니다")
        if op in ('revise','reassign') and task['attempt'] >= 3:
            raise ValueError('작업 시도 3회 소진: 사령탑이 amend로 원인·범위·완료 기준을 변경해야 합니다')
        if op == "accept":
            if task["state"] != "review":
                raise ValueError("제출되지 않은 작업은 수락할 수 없습니다")
            task["state"] = "accepted"
            task['accepted_by'] = event['agent']
            task['accepted_acting_for'] = LEAD if acting else None
        elif op == "revise":
            if task["state"] not in ("review", "blocked"):
                raise ValueError("제출된 작업을 반려하세요")
            task.update(state="ready", attempt=task["attempt"] + 1, result=None)
            task.pop("review", None)
        else:
            if task["state"] not in ("ready", "blocked", "review") or event.get("to") not in known or event.get("to") == LEAD:
                raise ValueError("진행 작업의 등록된 실행 작업자만 재배정할 수 있습니다")
            if event["to"] == task["assignee"]:
                raise ValueError("같은 작업자 재배정은 변경이 아닙니다")
            task.update(assignee=event["to"], state="ready", attempt=task["attempt"] + 1, result=None)
            task.pop("review", None)
            if task.get("reviewer") == event["to"]:
                task.pop("reviewer", None)  # 새 담당이 자기 결과를 검수하지 않게
        task["feedback"] = str(event["body"])[:3000]
    else:
        raise ValueError("알 수 없는 사령탑 행동")
    result["revision"] += 1
    result["events"].append(copy.deepcopy(event))
    return result


def project(records, known, seed=None):
    state = copy.deepcopy(seed) if seed else initial()
    seen = {e.get("event_id") for e in state["events"]}
    # 같은 PC의 잠금으로 기록된 revision이 순서의 기준. 벽시계/PC 시계차에 의존하지 않는다.
    for e in sorted((x for x in records if isinstance(x, dict)), key=lambda x: (x.get("revision") if isinstance(x.get("revision"), int) else -1, str(x.get("event_id", "")))):
        if e.get("event_id") in seen or e.get("event_id") in {x.get("id") for x in state["rejected"]}:
            continue
        try:
            state = transition(state, e, known)
            seen.add(e.get("event_id"))
        except (ValueError, TypeError) as exc:
            state["rejected"].append({"id": e.get("event_id"), "reason": str(exc), "agent": e.get('agent'), "op": e.get('op'), "ts": e.get('ts')})
    return state


def safe_file(root, relative):
    if not isinstance(relative, str) or "\\" in relative or ":" in relative:
        raise ValueError("근거는 작업물 저장소 기준 상대 경로여야 합니다")
    parts = PurePosixPath(relative)
    if parts.is_absolute() or not parts.parts or any(p in ("..", ".git", ".local") for p in parts.parts):
        raise ValueError("근거 경로가 허용 범위를 벗어납니다")
    base = Path(root).resolve()
    cursor = base
    for part in parts.parts:
        cursor = cursor / part
        info = cursor.lstat()
        if (stat.S_ISREG(info.st_mode) and info.st_nlink > 1) or stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError("링크·재분석 지점은 작업물로 사용할 수 없습니다")
    p = (base / relative).resolve()
    if not p.is_relative_to(base) or not p.is_file() or p.stat().st_size > 50 * 1024 * 1024:
        raise ValueError("근거 파일 없음·범위 이탈·크기 초과")
    return p


def evidence(root, paths, prefix=None):
    if not isinstance(paths, list) or not 1 <= len(paths) <= 32:
        raise ValueError("근거 파일은 1~32개를 지정하세요")
    out = []
    for rel in paths:
        if prefix and (not isinstance(rel, str) or not rel.startswith(prefix + "/")):
            raise ValueError("자기 작업물 폴더의 근거만 제출하세요")
        p = safe_file(root, rel)
        out.append({"path": rel, "sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "size": p.stat().st_size})
    return out


def verify_evidence(root, rows):
    for row in rows:
        p = safe_file(root, row["path"])
        if hashlib.sha256(p.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError(f"근거 파일이 제출 후 바뀌었습니다: {row['path']}")


def _return_note(topic):
    gate = pending_return(topic)
    if not gate:
        return ""
    what = ("지금 할 일: cmd=amend로 추가 조사 작업을 배정한다(위 형식). 그 작업이 수락된 뒤에 state done으로 새 ★결과 확인을 연다."
            if gate.get("act") == "work" else "지금 할 일: cmd=test-reset, body=재시험 이유로 시험을 초기화한다.")
    return (f"## 되돌아온 관문 — 처리 필요\n관문 {gate.get('id')} (★{gate.get('n')}) 아키텍트 답: {gate.get('choice') or '(선택 없이 메모)'} / 메모: {gate.get('note') or '(없음)'}\n"
            f"{what}\n")


def prompt(topic, who):
    if not topic.get("command_mode"):
        return ""
    state = topic.get("command") or initial()
    task = active(state)
    return ("\n## 서버컴 Astra 사령탑 워크플로우\n"
            f"최종 사령탑은 {LEAD}. 개발컴 허브는 중계기이며 개발컴 Claude는 구현·검증 작업자다.\n"
            "사령탑은 command 행동으로 작업을 나누고 결과를 검수한다. 조사로 풀 수 있는 질문은 작업자에게 배정한다.\n"
            "command: cmd=plan, body=JSON {tasks:[{id,title,scope,done_when,assignee,depends_on:[]}],human_test:true,test_reason:\"실게임 확인 필요\"}로 최초 분해.\n"
            "작업자는 맡은 작업만 수행한 뒤 command: cmd=submit, file=작업ID, body=결과 요약,\n"
            "options=[작업물 저장소 기준 근거 파일 상대 경로]로 제출한다. 자기 폴더 파일의 실제 SHA256을 실행기가 기록한다.\n"
            "사령탑은 받은 파일을 직접 읽고 검증 근거를 대조하여 cmd=accept 또는 revise, file=작업ID, body=검수 이유로 처리한다.\n"
            "검수 위임: plan/amend의 작업에 reviewer(작업 담당·사령탑이 아닌 작업자, 보통 server-claude)를 적거나 제출된 작업에 cmd=review-assign,file=작업ID,to=검수 담당,body=이유를 쓰면,\n"
            "검수 담당이 제출 근거를 직접 읽고 command: cmd=review-report,file=작업ID,status=pass|fail,body=근거·문제·미확인 요약,options=[자기 폴더 검수 기록 파일]로 보고한다.\n"
            "그 뒤 사령탑은 검수 보고를 보고 accept/revise만 짧게 처리한다(자기 제출물 검수·무조건 자동 수락 금지).\n"
            "실행 불가·로그인·실패 문제는 작업자가 command: cmd=blocked,file=작업ID,body=원인으로 사령탑에 보고한다.\n"
            "사령탑은 cmd=reassign,file=작업ID,to=새 작업자,body=이유로 미제출 작업을 재배정할 수 있다.\n"
            "acting_commander=dev-claude일 때만 개발컴 Claude가 검수·재배정을 대행한다. 자기 결과를 수락하지 말고 다른 개발 작업자에게 재배정해 독립 검증한다. 운영 반영·최초 계획·관문 승인 권한은 대행하지 않는다.\n"
            "작업자 state done/ask/handoff로 단계를 넘기거나 아키텍트에게 중계시키지 않는다.\n"
            "사령탑만 권한·취향·위험 결정에 ask를 쓴다. question은 '끝낸 일: … / 결정할 것: … / 권장: …' 형식이며 options가 필요하다.\n"
            "모든 작업 수락 후 사령탑이 state done으로 다음 단계(구현: 자체 시험, 조사·분석: ★결과 확인)로 넘긴다. 시험·배포본은 개발컴, 수신·배포 준비는 서버컴이다.\n"
            "아키텍트가 ★결과 확인에서 보완을 요청해 되돌아온 조사 주제는 state done 전에 반드시 cmd=amend, file=null,\n"
            "body=JSON {tasks:[기존 작업 그대로 + 추가 조사 작업 {id,title,scope,done_when,assignee,depends_on}]}로 추가 조사를 배정한다. amend 없이 낸 done은 실행기가 거부한다.\n"
            "기존 작업의 담당·검수 담당이 그 사이 잠겼으면 amend가 거부된다. 그 작업은 잠기지 않은 작업자로 바꾸거나 검수 담당을 빼서 다시 낸다.\n"
            "운영 반영은 아키텍트와 서버컴 Astra 대화에서 승인된 묶음만 처리한다.\n"
            + _return_note(topic) +
            f"현재 revision={state['revision']}; 현재 작업={json.dumps(task, ensure_ascii=False)}\n"
            f"현재 대행={topic.get('acting_commander') or '없음'}\n"
            f"전체 작업={json.dumps(state['tasks'], ensure_ascii=False)}\n")


def apply_action(job, action, cfg, known, locked, work_root, authority=None):
    """실제 실행기가 쓰는 단일 입구. 완료 기록 전 근거를 직접 읽는다."""
    import node
    import secrets
    topic, who = job["topic"], job["agent"]
    if not topic.get("command_mode") or topic.get("gate") or (
        str(action.get("cmd", "")).startswith("test-") and topic.get("stage") != "test") or (
        not str(action.get("cmd", "")).startswith("test-") and topic.get("stage", "work") != "work"):
        raise ValueError("작업 분해 단계가 아닙니다")
    local = [r for r in node.load_records(cfg)["topic_records"] if r.get("topic") == topic["id"] and r.get("kind") == "command"]
    state = project(local, known, topic.get("command"))
    # 한 AI 응답으로 검수→다음 작업 종료까지 연쇄 처리하지 않도록 최초 revision을 고정한다.
    expected = (topic.get("command") or initial())["revision"]
    event = {"event_id": secrets.token_hex(12), "revision": expected, "agent": who,
             "op": action.get("cmd"), "task_id": action.get("file"), "body": action.get("body", ""),
             "ts": node.now_iso(), "to": action.get("to")}
    if who == DEV and event['op'] in DEPUTY_OPS and authority:
        event['delegation'] = copy.deepcopy(authority)
        event['acting_for'] = LEAD
    if event["op"] in ("plan", "amend"):
        spec = json.loads(action.get("body") or "{}")
        if not isinstance(spec, dict):
            raise ValueError("계획 본문은 JSON 객체여야 합니다")
        event["tasks"] = spec.get("tasks")
        validate_tasks(event["tasks"], known)
        event["tests"] = spec.get("tests")
        event["human_test"] = spec.get("human_test", True)
        event["test_reason"] = spec.get("test_reason", "")
        if any(t.get("assignee") in locked or t.get("reviewer") in locked for t in event["tasks"] or []):
            raise ValueError("잠긴 작업자에게 배정할 수 없습니다(검수 담당 포함)")
        if any(t.get('assignee') in locked for t in testflow.plan(event.get('tests'),known)):
            raise ValueError('잠긴 작업자에게 시험을 배정할 수 없습니다')
    returned = returned_gate(topic)
    if event['op'] in ('amend','test-reset'):
        event['review_gate_id'] = returned['id'] if returned else '-'  # 되돌아온 관문 없음도 '-'로 남긴다(빈 값은 기록에서 빠짐). 키 있음 = r5 이후 기록
    if event['op'] == 'review-report':
        event['verdict'] = action.get('status')
    if event['op'] == 'test-replan':
        spec = json.loads(action.get('body') or '{}')
        if not isinstance(spec, dict):
            raise ValueError('재계획은 reason·method를 가진 JSON 객체여야 합니다')
        event['body'], event['method'] = spec.get('reason'), spec.get('method')
    if event["op"] in ("submit", "test-pass", "test-fail", "review-report"):
        wid = job.get("work_id") or topic.get("work_id")
        if not wid:
            raise ValueError("작업물 ID가 없습니다")
        event["evidence"] = evidence(work_root, action.get("options"), f"work/{wid}/{who}")
    if event["op"] == "accept":
        task = active(state)
        verify_evidence(work_root, ((task or {}).get("result") or {}).get("evidence", []))
        # 검수 담당 보고가 있으면 그 근거도 수락 직전에 다시 대조한다(보고 뒤 변경·삭제 거부, r5 읽기 검토 P2)
        verify_evidence(work_root, ((task or {}).get("review") or {}).get("evidence", []))
    if event['op'] == 'test-accept':
        check = testflow.current(state.get('tests', []))
        verify_evidence(work_root, (check or {}).get('evidence', []))
    if event["op"] in ("reassign", "test-reassign", "review-assign") and event["to"] in locked:
        raise ValueError("잠긴 작업자에게 재배정할 수 없습니다")
    updated = transition(state, event, known)
    node.add_topic_record(cfg, topic["id"], who, "command", **{k: v for k, v in event.items() if k not in ("agent", "ts")})
    return updated
