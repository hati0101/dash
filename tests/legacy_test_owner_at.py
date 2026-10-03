"""끝냄 귀속 = 그 시점 담당(2026-10-03 검토 P1) 시험 — 임시 폴더."""
import json, os, sys, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
DASH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DASH))
tmp = Path(tempfile.mkdtemp(prefix="dash-owner-"))
fails = 0
def ok(c, m):
    global fails
    print(("통과 " if c else "실패 ") + m); fails += 0 if c else 1
(tmp / "data").mkdir()
cfg = {"pc": {"id": "dev", "label": "개발컴", "role": "hub"}, "node_data_dir": str(tmp / "nd"), "data_dir": str(tmp / "data"), "topics_dir": str(tmp / "topics"),
       "agents": [{"id": "dev-claude", "ai": "claude", "label": "C"}, {"id": "dev-astra", "ai": "gpt", "label": "A"}]}
(tmp / "cfg.json").write_text(json.dumps(cfg), encoding="utf-8"); os.environ["REAL_OPS_CONFIG"] = str(tmp / "cfg.json")
import node, topics
C = node.load_cfg()
KST = timezone(timedelta(hours=9))
known = {"dev-claude", "dev-astra", "server-claude", "server-astra"}
base = datetime(2026, 10, 3, 9, 0, tzinfo=KST)
def ts(m): return (base + timedelta(minutes=m)).isoformat(timespec="seconds")
def zts(m): return (base + timedelta(minutes=m)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
folder = tmp / "topics"; folder.mkdir()
def mk(tid, title, kind="기능·개선", assignee="dev-claude"):
    (folder / tid).mkdir()
    (folder / tid / "topic.json").write_text(json.dumps({"id": tid, "title": title, "priority": "P2", "kind": kind}, ensure_ascii=False), encoding="utf-8")
    (folder / tid / "claude.json").write_text(json.dumps({"assignee": assignee, "assigned_at": ts(0), "status": "active", "status_at": ts(0), "plan": {"goal": "g"}}), encoding="utf-8")
def udata():
    u = tmp / "data" / "user.json"; return u, (json.loads(u.read_text(encoding="utf-8")) if u.exists() else {})
def answer(gid, choice, m, note=""):
    u, d = udata(); d.setdefault("decisions_answered", []).append({"id": gid, "choice": choice, "note": note, "ts": zts(m)}); u.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
def assign(tid, agent, m):
    u, d = udata(); d.setdefault("topic_assign", []).append({"topic": tid, "agent": agent, "ts": zts(m)}); u.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
def done(tid, by, m, body="결과: 수정 끝, 파일 2개, 시험 방법 보스 처치 10회"):
    return {"topic": tid, "agent": by, "kind": "status", "status": "done", "ts": ts(m), "body": body}
def all_(rs): return topics.merged_topics(folder, C, rs, known)
def m_(rs, tid): return {x["id"]: x for x in all_(rs)}[tid]
def snap(rs): return topics.log_owners(C, all_(rs))
def lead(tid): return json.loads((folder / tid / "claude.json").read_text(encoding="utf-8"))

# 1) 옛 담당(착수 기록 없음)의 끝냄은 담당이 바뀐 뒤에도 인정 — 관문이 떨어져 나가지 않음
T1 = "T-20261003-ow0001"; mk(T1, "드랍 표시", assignee="dev-astra")
rs = [done(T1, "dev-astra", 5), done(T1, "dev-astra", 10, "자체 시험 끝: 체크리스트")]
ok(snap(rs) >= 1, "허브가 지금 담당을 이력에 기록")
g4 = m_(rs, T1)["gate"]
ok(g4 and g4["n"] == 4, "옛 담당 dev-astra 끝냄 2번 → ★4")
assign(T1, "server-claude", 12); snap(rs)
t = m_(rs, T1)
ok(t.get("gate") and t["gate"]["id"] == g4["id"], "담당을 서버컴으로 바꿔도 ★4 번호 그대로")
ok([e["agent"] for e in lead(T1)["owner_log"]] == ["dev-astra", "server-claude"], "이력: dev-astra → server-claude")

# 2) 나중에 담당이 된 작업자의 옛 끝냄은 뒤늦게 인정되지 않음
T2 = "T-20261003-ow0002"; mk(T2, "서번트 발동 수정")
rs2 = [done(T2, "dev-astra", 5)]
snap(rs2)
ok(m_(rs2, T2).get("stage") in (None, "work"), "검토자 dev-astra 끝냄 → 진행 그대로")
assign(T2, "dev-astra", 8); snap(rs2)
t = m_(rs2, T2)
ok(t.get("stage") in (None, "work") and not t.get("gate"), "dev-astra가 담당이 된 뒤에도 그 전 끝냄은 무효(진행 그대로)")
rs2 += [done(T2, "dev-astra", 9)]
ok(m_(rs2, T2).get("stage") == "test", "담당이 된 뒤의 끝냄 → 3 자체 시험")

# 3) 이력이 없던 때(기록 시작 전)의 끝냄은 예전 판정 그대로(지금 담당+맡았던 작업자)
T3 = "T-20261003-ow0003"; mk(T3, "보스 HP 바", assignee="dev-astra")
rs3 = [{"topic": T3, "agent": "dev-claude", "kind": "claim", "ts": ts(1), "body": "착수"}, done(T3, "dev-claude", 5)]
assign(T3, "dev-claude", 7)  # 이력 기록 없이 담당 변경
ok(m_(rs3, T3).get("stage") == "test", "이력 없음 → 예전 판정(지금 담당 dev-claude의 끝냄 인정)")

# 4) 이미 답한 관문을 연 끝냄은 담당 정보가 바뀌어도 그대로(조사 주제 ★결과 확인 → 보류)
T4 = "T-20261003-ow0004"; mk(T4, "로그 분석", kind="조사·분석")
rs4 = [done(T4, "dev-claude", 5, "분석 결과")]
g40 = m_(rs4, T4)["gate"]; ok(g40["n"] == 40, "조사 주제 끝냄 → ★결과 확인")
answer(g40["id"], "후속 구현 주제 만들기", 6)
assign(T4, "dev-astra", 7)  # 이력 없이 담당 변경(기록 시작 전과 같은 상황)
t = m_(rs4, T4)
ok(t["status"] == "done" and t["gate_history"] and t["gate_history"][-1]["id"] == g40["id"], "답한 관문은 담당이 바뀌어도 유지(완료 그대로)")
snap(rs4); ok(not lead(T4).get("owner_log"), "완료 주제는 이력 기록 안 함")

# 5) 이력 기록은 바뀔 때만 · 실게임 이관(dev-claude)은 원래 담당으로 기록 · 완료 주제는 기록 안 함
n0 = len(lead(T1)["owner_log"]); snap(rs + rs4); snap(rs + rs4)
ok(len(lead(T1)["owner_log"]) == n0, "같은 담당·시각이면 다시 적지 않음")
T5 = "T-20261003-ow0005"; mk(T5, "장비 UI", assignee="dev-astra")
rs5 = [done(T5, "dev-astra", 5), done(T5, "dev-astra", 10)]
t = m_(rs5, T5); ok(t.get("live_session") and t["assignee"] == "dev-claude", "★4 실게임 단계 → 담당 dev-claude 표시")
snap(rs5); ok(lead(T5)["owner_log"][-1]["agent"] == "dev-astra", "이력에는 실게임 이관 전 담당(dev-astra)")

# 6) 엣지: 시각 형식 섞임(Z/+09:00)·이력 순서 뒤섞임·깨진 항목
t = {"id": "T-x", "_owner_log": [{"agent": "b", "from": zts(10)}, {"agent": "a", "from": ts(0)}, {"agent": None, "from": ts(1)}, {"from": "깨짐"}],
     "_assigned_at": zts(20), "_base_assignee": "c"}
ok([topics.assignee_at(t, ts(m)) for m in (-1, 0, 9, 10, 19, 20, 99)] == [None, "a", "a", "b", "b", "c", "c"], "시점 담당 계산(경계 포함)")
ok([topics.owners_at(t, ts(m)) for m in (15, 19, 21, 29, 30)] == [{"a", "b"}, {"a", "b"}, {"b", "c"}, {"b", "c"}, {"c"}], "바뀐 지 10분 안이면 이전 담당도 인정, 10분부터는 새 담당만")
ok(topics.owners_at(t, ts(-1)) == set(), "이력 전 시각 → 빈 집합")
# 7) 자동 이관 직후(10분 안) 이전 담당이 끝냄 → 인정 · 10분 뒤 → 무효
T7 = "T-20261003-ow0007"; mk(T7, "버프 아이콘", assignee="dev-astra")
snap([]); assign(T7, "dev-claude", 20)
ok(m_([done(T7, "dev-astra", 25)], T7).get("stage") == "test", "이관 5분 뒤 이전 담당 끝냄 → 인정(돌던 작업)")
ok(m_([done(T7, "dev-astra", 31)], T7).get("stage") in (None, "work"), "이관 11분 뒤 이전 담당 끝냄 → 무효")
# 8) (검토 P1) 이관 → 허브 동기화로 이력 기록 → 유예 안 이전 담당 끝냄: 동기화 전후 판정이 같아야 함
T8 = "T-20261003-ow0008"; mk(T8, "버프 툴팁", assignee="dev-astra")
snap([]); assign(T8, "dev-claude", 20)
r8 = [done(T8, "dev-astra", 25)]
before = m_(r8, T8).get("stage"); snap(r8); after_ = m_(r8, T8).get("stage")
ok(before == after_ == "test", f"이관 5분 뒤 이전 담당 끝냄: 이력 기록 전후 모두 인정({before} → {after_})")
ok([e["agent"] for e in lead(T8)["owner_log"]] == ["dev-astra", "dev-claude"], "이력에 같은 담당이 겹쳐 적히지 않음")
# 9) (검토 P2) 이력이 없을 때도 유예: 자동 이관 전 담당(prev_assignees)의 이관 직후 끝냄 인정
T9 = "T-20261003-ow0009"; mk(T9, "상점 UI", assignee="dev-claude")
j = lead(T9); j.update(assigned_at=ts(20), prev_assignees=["dev-astra"]); (folder / T9 / "claude.json").write_text(json.dumps(j), encoding="utf-8")
ok(m_([done(T9, "dev-astra", 24)], T9).get("stage") == "test", "이력 없음 + 이관 4분 뒤 이전 담당 끝냄 → 인정")
ok(m_([done(T9, "dev-astra", 40)], T9).get("stage") in (None, "work"), "이력 없음 + 이관 20분 뒤 이전 담당 끝냄 → 무효")
# 10) (검토 P2) 깨진 시각의 이력은 무시(처음부터 담당으로 보지 않음)
t = {"id": "T-x", "_owner_log": [{"agent": "z", "from": "깨짐"}, {"agent": "a", "from": ts(10)}], "_assigned_at": None, "_base_assignee": "a"}
ok(topics.assignee_at(t, ts(5)) is None and topics.assignee_at(t, ts(11)) == "a", "깨진 시각 이력 무시, 시각 없는 지금 담당도 무시")
# 11) (검토 P2) 이력 시작 전: 착수 없는 A가 진행·시험을 끝내 ★4를 답받은 뒤 이력 없이 담당이 바뀌어도 관문 유지
T11 = "T-20261003-ow0011"; mk(T11, "보스 알림", assignee="dev-astra")
r11 = [done(T11, "dev-astra", 5), done(T11, "dev-astra", 10, "자체 시험 끝")]
g = m_(r11, T11)["gate"]; answer(g["id"], "통과", 12)
assign(T11, "server-claude", 14)
t = m_(r11, T11)
ok(t.get("gate") and t["gate"]["n"] == 5 and t["gate_history"][0]["id"] == g["id"], "답한 ★4 유지 → ★5 대기(앞 단계 끝냄도 같은 작업자라 인정)")
ok(topics.assignee_at({"id": "T-x"}, ts(5)) is None, "이력·담당 없음 → None(예전 판정)")
print("모두 통과" if not fails else f"실패 {fails}건"); sys.exit(1 if fails else 0)
