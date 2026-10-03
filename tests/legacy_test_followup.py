"""후속 주제 연결·중복 방지·제안 출처(보고서 2번, 2026-10-03) 시험 — 임시 폴더."""
import argparse, json, os, sys, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
DASH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DASH))
tmp = Path(tempfile.mkdtemp(prefix="dash-fu-"))
fails = 0
def ok(c, m):
    global fails
    print(("통과 " if c else "실패 ") + m); fails += 0 if c else 1
(tmp / "data").mkdir()
cfg = {"pc": {"id": "dev", "label": "개발컴", "role": "hub"}, "node_data_dir": str(tmp / "nd"), "data_dir": str(tmp / "data"), "topics_dir": str(tmp / "topics"),
       "bridge_dir": str(tmp), "agents": [{"id": "dev-claude", "ai": "claude", "label": "C"}, {"id": "dev-astra", "ai": "gpt", "label": "A"}]}
(tmp / "cfg.json").write_text(json.dumps(cfg), encoding="utf-8"); os.environ["REAL_OPS_CONFIG"] = str(tmp / "cfg.json")
os.environ.pop("REAL_OPS_PASSWORD", None)
import node, topics
C = node.load_cfg()
KST = timezone(timedelta(hours=9))
known = {"dev-claude", "dev-astra"}
base = datetime(2026, 10, 3, 9, 0, tzinfo=KST)
def ts(m): return (base + timedelta(minutes=m)).isoformat(timespec="seconds")
def zts(m): return (base + timedelta(minutes=m)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
folder = tmp / "topics"; folder.mkdir()
def mk(tid, title, kind="조사·분석", **extra):
    (folder / tid).mkdir()
    (folder / tid / "topic.json").write_text(json.dumps({"id": tid, "title": title, "priority": "P2", "kind": kind, **extra}, ensure_ascii=False), encoding="utf-8")
    (folder / tid / "claude.json").write_text(json.dumps({"assignee": "dev-claude", "assigned_at": ts(0), "status": "active", "status_at": ts(0), "plan": {"goal": "g"}}), encoding="utf-8")
def answer(gid, choice, m, note=""):
    u = tmp / "data" / "user.json"; d = json.loads(u.read_text(encoding="utf-8")) if u.exists() else {}
    d.setdefault("decisions_answered", []).append({"id": gid, "choice": choice, "note": note, "ts": zts(m)}); u.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
def rec(tid, m, body="조사 결과: 권장안 A, 근거 3가지, 구현 범위 화면 1곳"):
    node.add_topic_record(C, tid, "dev-claude", "status", status="done", body=body)
def all_():
    nodes = node.collect_nodes(C, None)
    return {t["id"]: t for t in topics.merged_topics(folder, C, [r for n in nodes for r in n.get("topic_records") or []], known)}
NS = argparse.Namespace(password_file=None)

# 1) 결과 확인 → 후속 구현 → 후속 주제 생성 + 양방향 연결
A = "T-20261003-fu0001"; mk(A, "카드 등급 조사")
rec(A, 5)
g = all_()[A]["gate"]; ok(g["n"] == 40 and g["options"][0] == "후속 구현 주제 만들기", "전제: ★결과 확인(후속 없음 → 기본 선택지)")
answer(g["id"], "후속 구현 주제 만들기", 10)
topics.cmd_spawn_followups(NS, C)
d = all_()
fu = [x for x in d.values() if x.get("origin_topic") == A]
ok(len(fu) == 1 and d[A]["status"] == "done", "후속 구현 → 후속 주제 1건, 원래 주제 완료")
ok(d[A].get("followup_topics") and d[A]["followup_topics"][0]["id"] == fu[0]["id"], "원래 주제 → 후속 주제 연결")
ok(fu[0].get("origin", {}).get("id") == A and fu[0]["origin"]["title"] == "카드 등급 조사", "후속 주제 → 원래 주제 연결(제목 포함)")
topics.cmd_spawn_followups(NS, C)
ok(len([x for x in all_().values() if x.get("origin_topic") == A]) == 1, "다시 돌려도 중복 없음")

# 2) 후속이 이미 있는 주제의 결과 확인 → 선택지 '완료 확정(후속 주제 있음)·보류' → 완료 확정 = 완료
B = "T-20261003-fu0002"; mk(B, "이름 색 기획")
rec(B, 5)
mk("T-20261003-fu0003", "이름 색 구현", kind="기능·개선", origin_topic=B)
g = all_()[B]["gate"]
ok(g["options"] == ["완료 확정(후속 주제 있음)", "보류"], f"후속 있음 → 선택지 바뀜 {g['options']}")
answer(g["id"], "완료 확정(후속 주제 있음)", 10)
ok(all_()[B]["status"] == "done", "완료 확정(후속 주제 있음) → 완료")
# 3) 후속이 있는데 옛 화면 선택지로 '후속 구현'이 눌림 → 새로 만들지 않음
Cc = "T-20261003-fu0004"; mk(Cc, "합성 연출 조사")
rec(Cc, 5)
mk("T-20261003-fu0005", "합성 연출 구현", kind="기능·개선", origin_topic=Cc)
answer(all_()[Cc]["gate"]["id"], "후속 구현 주제 만들기", 10)
topics.cmd_spawn_followups(NS, C)
ok(len([x for x in all_().values() if x.get("origin_topic") == Cc]) == 1, "후속 이미 있음 → 옛 선택지로 눌러도 중복 생성 안 함")

# 4) AI 제안: 주제 진행 중 올린 제안에 원래 주제가 붙고, 후속 구현을 고른 주제의 제안은 바로 배분(미처리 아님)
Dd = "T-20261003-fu0006"; mk(Dd, "등급 표시 기획")
rec(Dd, 5)
answer(all_()[Dd]["gate"]["id"], "후속 구현 주제 만들기", 10)
node.add_proposal(C, "dev-claude", "등급 접두어 구현", "본문", "기능·개선", "P2", "", Dd)
E = "T-20261003-fu0007"; mk(E, "다른 진행 주제", kind="기능·개선")
node.add_proposal(C, "dev-claude", "덤으로 떠오른 아이디어", "본문", "기타", "P2", "", E)
node.add_proposal(C, "dev-claude", "출처 없는 메모", "본문", "기타", "P2", "", "")
node.add_proposal(C, "dev-claude", "잘못된 출처", "본문", "기타", "P2", "", "../x")
topics.cmd_import_proposals(NS, C)
byt = {x["title"]: x for x in all_().values()}
p1, p2, p3, p4 = byt["등급 접두어 구현"], byt["덤으로 떠오른 아이디어"], byt["출처 없는 메모"], byt["잘못된 출처"]
ok(p1.get("origin_topic") == Dd and not p1.get("backlog") and p1["status"] == "new", "후속 구현을 고른 주제의 제안 → 원래 주제 연결 + 바로 배분 대상(새 주제)")
ok(p2.get("origin_topic") == E and p2.get("backlog") and p2["status"] == "backlog", "다른 주제 진행 중 제안 → 원래 주제 연결, 미처리")
ok(not p3.get("origin_topic") and p3["status"] == "backlog", "출처 없는 제안 → 지금처럼 미처리")
ok(not p4.get("origin_topic"), "잘못된 출처 ID는 무시")
topics.cmd_spawn_followups(NS, C)
ok(len([x for x in all_().values() if x.get("origin_topic") == Dd]) == 1, "제안으로 후속이 생긴 주제는 후속 만들기에서 또 만들지 않음")
# 5) (검토 P1) 조사 중 올린 상관없는 미처리 제안은 '후속'으로 세지 않음 → 선택지 그대로, 연결 표시는 됨
F = "T-20261003-fu0010"; mk(F, "보스 패턴 조사")
node.add_proposal(C, "dev-claude", "덤 아이디어(미처리)", "본문", "기타", "P2", "", F)
topics.cmd_import_proposals(NS, C)
rec(F, 5)
x = all_()[F]
ok(x["gate"]["options"][0] == "후속 구현 주제 만들기", "미처리 제안만 있으면 '후속 구현' 선택지 그대로")
ok(x.get("followup_topics") and x["followup_topics"][0]["status"] == "backlog", "미처리 제안도 연결로는 보임")
answer(x["gate"]["id"], "후속 구현 주제 만들기", 10)
topics.cmd_spawn_followups(NS, C)
real = [y for y in all_().values() if y.get("origin_topic") == F and y["status"] != "backlog"]
ok(len(real) == 1 and real[0]["title"].startswith("후속 구현:"), "후속 구현 → 진짜 후속 주제가 만들어짐(미처리 제안 때문에 건너뛰지 않음)")
# 6) (검토 P2) 후속이 이미 만들어진 뒤 늦게 온 제안 → 미처리(바로 배분 후속 2건 안 됨)
node.add_proposal(C, "dev-claude", "늦게 온 구현 제안", "본문", "기능·개선", "P2", "", F)
topics.cmd_import_proposals(NS, C)
late = {y["title"]: y for y in all_().values()}["늦게 온 구현 제안"]
ok(late["status"] == "backlog" and late.get("origin_topic") == F, "후속이 이미 있으면 늦게 온 제안은 미처리(연결은 유지)")
# 7) (검토 P3) 후속을 삭제하면 다시 만들 수 있게 선택지가 돌아옴
G = "T-20261003-fu0020"; mk(G, "드랍 표 조사")
rec(G, 5)
mk("T-20261003-fu0021", "드랍 표 구현", kind="기능·개선", origin_topic=G)
ok(all_()[G]["gate"]["options"][0].startswith("완료 확정(후속"), "전제: 후속 있음 → 선택지 바뀜")
u = tmp / "data" / "user.json"; d = json.loads(u.read_text(encoding="utf-8"))
d.setdefault("topic_drop", []).append({"topic": "T-20261003-fu0021", "ts": zts(20)}); u.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
ok(all_()[G]["gate"]["options"][0] == "후속 구현 주제 만들기", "후속을 삭제하면 '후속 구현' 선택지가 돌아옴")
print("모두 통과" if not fails else f"실패 {fails}건"); sys.exit(1 if fails else 0)
