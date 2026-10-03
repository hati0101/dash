"""후속 줄기(아키텍트 2026-10-03) 시험 — 후속으로 이어짐·줄기 완료·후속 보류·후속 삭제 시 ★결과 확인 다시."""
import json, os, sys, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
DASH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DASH))
tmp = Path(tempfile.mkdtemp(prefix="dash-ch-"))
fails = 0
def ok(c, m):
    global fails
    print(("통과 " if c else "실패 ") + m); fails += 0 if c else 1
(tmp / "data").mkdir()
cfg = {"pc": {"id": "dev", "label": "개발컴", "role": "hub"}, "node_data_dir": str(tmp / "nd"), "data_dir": str(tmp / "data"), "topics_dir": str(tmp / "topics"),
       "bridge_dir": str(tmp), "agents": [{"id": "dev-claude", "ai": "claude", "label": "C"}, {"id": "dev-astra", "ai": "gpt", "label": "A"}]}
(tmp / "cfg.json").write_text(json.dumps(cfg), encoding="utf-8"); os.environ["REAL_OPS_CONFIG"] = str(tmp / "cfg.json")
import node, topics
C = node.load_cfg()
KST = timezone(timedelta(hours=9))
known = {"dev-claude", "dev-astra", "server-claude", "server-astra"}
base = datetime(2026, 10, 3, 15, 0, tzinfo=KST)
def ts(m): return (base + timedelta(minutes=m)).isoformat(timespec="seconds")
def zts(m): return (base + timedelta(minutes=m)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
folder = tmp / "topics"; folder.mkdir()
def mk(tid, title, m, origin=None, kind="조사·분석"):
    (folder / tid).mkdir()
    (folder / tid / "topic.json").write_text(json.dumps({"id": tid, "title": title, "priority": "P2", "kind": kind, "created_at": ts(m),
                                                          **({"origin_topic": origin} if origin else {})}, ensure_ascii=False), encoding="utf-8")
    (folder / tid / "claude.json").write_text(json.dumps({"assignee": "dev-claude", "assigned_at": ts(m), "status": "active", "status_at": ts(m), "plan": {"goal": "g"}}), encoding="utf-8")
n_act = [0]
def act(**kw):
    n_act[0] += 1
    return topics.apply_action(C, topics.clean_action({"id": f"A-20261003-ch{n_act[0]:04d}", **kw}), "시험")
def answer(gid, choice, m): return act(type="decide", decision_id=gid, choice=choice, note="", created_at=zts(m))
def done(tid, m, body="결과: 조사 끝, 근거 3가지, 정할 것 x 권장 y"):
    return {"topic": tid, "agent": "dev-claude", "kind": "status", "status": "done", "ts": ts(m), "body": body}
def all_(rs): return {x["id"]: x for x in topics.merged_topics(folder, C, rs, known)}

R, F = "T-20261003-ch0001", "T-20261003-ch0002"
mk(R, "경매장", 0)
rs = [done(R, 5)]
answer(all_(rs)[R]["gate"]["id"], "후속 구현 주제 만들기", 10)
mk(F, "후속 구현: 경매장", 11, origin=R, kind="기능·개선")
d = all_(rs)
ok(d[R]["status"] == "done" and d[R].get("followed"), "후속 구현 → 원래 주제는 '후속으로 이어짐'(done+followed)")
ch = d[F].get("chain") or {}
ok(ch.get("root") == R and [m["id"] for m in ch.get("members", [])] == [R, F] and ch.get("state") == "active", f"줄기: 원래 → 후속, 진행 중 {ch.get('state')}")
ok(d[R].get("chain") == ch, "원래·후속 어느 쪽을 열어도 같은 줄기")
ok(ch["head"].startswith("경매장 → 후속 구현: 경매장 · 지금"), f"줄기 머리 한 줄: {ch.get('head')}")
# 후속 보류
rs += [done(F, 20), done(F, 21)]
g4 = all_(rs)[F]["gate"]; answer(g4["id"], "보류", 25)
d = all_(rs); ok(d[F]["status"] == "parked" and d[R]["chain"]["state"] == "parked" and d[R]["chain"]["label"] == "후속 보류", "후속 보류 → 줄기 '후속 보류'")
act(type="topic-resume", topic=F, note="", created_at=zts(26))
g4 = all_(rs)[F]["gate"]; ok(g4["n"] == 4, "다시 진행 → 후속 ★4")
answer(g4["id"], "즉시 완료 확정(남은 단계 건너뜀)", 30)
d = all_(rs); ok(d[F]["status"] == "done" and d[R]["chain"]["state"] == "done" and d[R]["chain"]["head"].endswith("완료"), "후속 완료 → 줄기 완료(원래 주제도 완료로 셈)")
# 후속 삭제 → 원래 주제 ★결과 확인 다시 → 완료 확정
R2, F2 = "T-20261003-ch0003", "T-20261003-ch0004"
mk(R2, "트레저 고블린", 40)
rs += [done(R2, 45)]
answer(all_(rs)[R2]["gate"]["id"], "후속 구현 주제 만들기", 50)
mk(F2, "후속 구현: 트레저 고블린", 51, origin=R2, kind="기능·개선")
ok(all_(rs)[R2].get("followed"), "전제: 후속으로 이어짐")
act(type="topic-drop", topics=[F2], note="필요 없음", created_at=zts(60))
d = all_(rs)
ok(d[R2]["status"] == "review_user" and d[R2]["gate"]["n"] == 40 and not d[R2].get("followed") and "후속 주제가 삭제됨" in d[R2]["gate"]["summary"],
   "후속 삭제 → 원래 주제 ★결과 확인 다시(아키텍트에게 묻기)")
ok(d[R2]["gate"]["options"][0] == "후속 구현 주제 만들기", "다시 묻는 선택지: 후속 구현 다시 만들기 / 보류 / 완료 확정")
g = d[R2]["gate"]["id"]
answer(g, "완료 확정(배포할 것 없음)", 65)
d = all_(rs); ok(d[R2]["status"] == "done" and not d[R2].get("followed"), "다시 연 결과 확인 → 완료 확정(후속 없이 완료)")
# 후속 삭제 → 다시 후속 구현 → 새 후속(재판정 안정)
R3, F3, F4 = "T-20261003-ch0005", "T-20261003-ch0006", "T-20261003-ch0007"
mk(R3, "풍선껌 검수", 70)
rs += [done(R3, 72)]
answer(all_(rs)[R3]["gate"]["id"], "후속 구현 주제 만들기", 73)
mk(F3, "후속 구현: 풍선껌", 74, origin=R3, kind="기능·개선")
act(type="topic-drop", topics=[F3], created_at=zts(80))
g = all_(rs)[R3]["gate"]["id"]
answer(g, "후속 구현 주제 만들기", 85)
mk(F4, "후속 구현: 풍선껌 2", 86, origin=R3, kind="기능·개선")
d = all_(rs)
ok(d[R3]["status"] == "done" and d[R3].get("followed") and len(d[R3]["gate_history"]) == 2, f"삭제 뒤 다시 후속 구현 → 다시 이어짐, 관문 기록 2개 {len(d[R3]['gate_history'])}")
ok(d[R3]["chain"]["state"] == "active" and d[R3]["chain"]["current"] == F4, "줄기 현재 = 새 후속")
# 후속의 후속(여러 단계)
F5 = "T-20261003-ch0008"
rs += [done(F4, 90)]  # 기능 주제 → 자체 시험
mk(F5, "후속의 후속", 91, origin=F4, kind="기능·개선")
d = all_(rs); ok([m["id"] for m in d[F5]["chain"]["members"]] == [R3, F3, F4, F5], "후속의 후속도 같은 줄기(삭제된 후속 포함 기록)")
print(f"\n실패 {fails}건")
sys.exit(1 if fails else 0)
