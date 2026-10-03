"""사령탑 전환의 재시작 이관. sync가 capabilities 확인 뒤 호출한다.
원본/답/작업물은 보존하며 새 주제에는 원래 목표만 복사한다. 운영 파일 접근 없음.
"""
import hashlib
import json
from pathlib import Path

EPOCH = "astra-20261003-v1"

def pending(nodes):
    reasons=[]
    registered={a for n in nodes for a in (n.get('agents') or {})}
    for aid in ('server-astra','dev-claude'):
        if aid not in registered: reasons.append(aid+' 연결 대기')
    for n in nodes:
        for aid,a in (n.get('agents') or {}).items():
            if aid not in ('server-astra','dev-claude'): continue
            if n.get('error'): reasons.append(aid+' 동기화 오류')
            if a.get('command_version')!=1: reasons.append(aid+' 코드 업데이트 대기')
    return reasons


def migrate(cfg, current):
    from topics import data_dir, topics_dir, read_json, write_json, now_iso
    state_path = data_dir(cfg) / "command-reset.json"
    plan_path = data_dir(cfg) / 'command-reset-plan.json'
    state = read_json(state_path, {}) or read_json(plan_path, {})
    recovered = [read_json(p, {}) for p in topics_dir(cfg).glob('*/topic.json')]
    recovered = [t for t in recovered if t.get('restart_of') and t.get('command_epoch') == EPOCH]
    if not state and recovered:
        complete_plan = next((t.get('restart_plan') for t in recovered if t.get('restart_plan')), None)
        state = complete_plan or {'epoch': EPOCH, 'created_at': min(t['created_at'] for t in recovered),
                 'complete': True, 'topics': [{'old': t['restart_of'], 'new': t['id']} for t in recovered]}
        write_json(state_path, state)
    if state.get("epoch") == EPOCH and state.get("complete"):
        return state
    # 계획을 먼저 영속화하여 중간 종료 후 같은 목록/ID로 재개한다.
    if state.get("epoch") != EPOCH:
        rows = []
        for t in current:
            if t.get('command_mode') or t.get('restart_of') or t.get('archived'): continue
            if t.get("status") not in ("new", "triage", "ready", "active", "review_user"):
                continue
            digest = hashlib.sha256((EPOCH + t["id"]).encode()).hexdigest()[:6]
            rows.append({"old": t["id"], "new": "T-20261003-" + digest,
                         "title": t["title"], "body": t.get("body", ""), "kind": t.get("kind", "기타"),
                         "priority": t.get("priority", "P2"), "work_id": t.get("work_id"), "origin_topic": t.get("origin_topic"),
                         "previous_stage": t.get("stage"), "previous_gate": t.get("gate")})
        state = {"epoch": EPOCH, "created_at": now_iso(), "complete": False, "topics": rows}
        write_json(plan_path, state)
        write_json(state_path, state)
    remap = {x["old"]: x["new"] for x in state["topics"]}
    for row in state["topics"]:
        target = topics_dir(cfg) / row["new"] / "topic.json"
        previous = read_json(target, None)
        if previous:
            if previous.get("restart_of") != row["old"]:
                raise ValueError("재시작 주제 ID 충돌: " + row["new"])
            continue
        write_json(target, {"id": row["new"], "title": row["title"], "body": row["body"],
                            "kind": row["kind"], "priority": row["priority"], "prefer": "auto",
                            "created_at": state["created_at"], "received_at": state["created_at"],
                            "source": "사령탑 전환: 원래 목표부터 재검토", "restart_of": row["old"],
                            "reference_work": row.get("work_id"), "command_epoch": EPOCH,
                            "origin_topic": remap.get(row.get("origin_topic"), row.get("origin_topic")),
                            "restart_map": remap,
                            "restart_plan": {**state, 'complete': False},
                            "command_mode": True})
    state["complete"] = True
    write_json(state_path, state)
    return state
