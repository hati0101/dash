"""배포 대기열·묶음 배포(아키텍트 2026-10-03) 시험 — 임시 폴더."""
import json, os, sys, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
DASH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DASH))
tmp = Path(tempfile.mkdtemp(prefix="dash-dq-"))
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
base = datetime(2026, 10, 3, 13, 0, tzinfo=KST)
def ts(m): return (base + timedelta(minutes=m)).isoformat(timespec="seconds")
def zts(m): return (base + timedelta(minutes=m)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
folder = tmp / "topics"; folder.mkdir()
def mk(tid, title):
    (folder / tid).mkdir()
    (folder / tid / "topic.json").write_text(json.dumps({"id": tid, "title": title, "priority": "P2", "kind": "기능·개선"}, ensure_ascii=False), encoding="utf-8")
    (folder / tid / "claude.json").write_text(json.dumps({"assignee": "dev-claude", "assigned_at": ts(0), "status": "active", "status_at": ts(0), "plan": {"goal": "g"}}), encoding="utf-8")
def udata():
    u = tmp / "data" / "user.json"; return u, (json.loads(u.read_text(encoding="utf-8")) if u.exists() else {})
n_act = [0]
def act(**kw):
    n_act[0] += 1
    a = topics.clean_action({"id": f"A-20261003-dq{n_act[0]:04d}", **kw})
    return topics.apply_action(C, a, "시험")
def answer(gid, choice, m, note=""):
    return act(type="decide", decision_id=gid, choice=choice, note=note, created_at=zts(m))
def batch(op, b, tids, m, date="", note=""):
    return act(type="deploy-batch", op=op, batch=b, topics=tids, date=date, note=note, created_at=zts(m))
def done(tid, by, m, body="결과: 수정 끝, 파일 2개, 시험 방법 보스 처치 10회, 정할 것 x 권장 y"):
    return {"topic": tid, "agent": by, "kind": "status", "status": "done", "ts": ts(m), "body": body}
def m_(rs, tid=None):
    d = {x["id"]: x for x in topics.merged_topics(folder, C, rs, known)}
    return d[tid] if tid else d

def to7(tid, rs, m0):
    """진행 → 자체 시험 → ★4 통과 → ★5 배포본 → 배포본 끝냄 → ★7"""
    rs += [done(tid, "dev-claude", m0), done(tid, "dev-claude", m0 + 1)]
    answer(m_(rs, tid)["gate"]["id"], "통과", m0 + 2)
    answer(m_(rs, tid)["gate"]["id"], "배포본 만들기", m0 + 3)
    rs.append(done(tid, "dev-claude", m0 + 4))
    return m_(rs, tid)

# 형식 검사
for bad, why in ((dict(type="deploy-batch", op="add", batch="X-1", topics=["T-20261003-aaaaaa"]), "묶음 번호"),
                 (dict(type="deploy-batch", op="add", batch="R-20261005", topics=[]), "빈 목록"),
                 (dict(type="deploy-batch", op="zap", batch="R-20261005", topics=["T-20261003-aaaaaa"]), "op"),
                 (dict(type="deploy-batch", op="add", batch="R-20261005", topics=["T-20261003-aaaaaa"], date="10/5"), "날짜")):
    try:
        topics.clean_action({"id": "A-20261003-bad001", **bad}); e = ""
    except ValueError as x:
        e = str(x)
    ok(bool(e), f"형식 거부: {why}")
ok("topic-resume" in topics.ACTION_TYPES and "deploy-batch" in topics.ACTION_TYPES, "가져오기 허용 목록에 다시 진행·배포 묶음(다시 진행이 빠져 있던 결함)")

A, B, X = "T-20261003-dqaaaa", "T-20261003-dqbbbb", "T-20261003-dqxxxx"
for t_, n in ((A, "보스 알림"), (B, "툴팁"), (X, "장비창")):
    mk(t_, n)
rs = []
t = to7(A, rs, 1); ok(t["gate"]["n"] == 7 and t["gate"]["options"][0] == "배포 대기열에 넣기", "★7 첫 선택지 = 배포 대기열에 넣기")
answer(t["gate"]["id"], "배포 대기열에 넣기", 10)
t = m_(rs, A)
ok(t["status"] == "active" and t["stage"] == "prep" and t["stage_owner"] == "server-astra" and t.get("turn", "x") != "x" or t["stage"] == "prep",
   f"★7 → 8a 배포 준비(서버컴 Astra) {t['stage']}/{t.get('stage_owner')}")
ok(topics.whose_turn(t) == "server-astra" and not t.get("deploy_session"), "배포 준비는 서버컴 Astra 자동 실행기 차례")
ok(t["step"]["label"].startswith("배포 준비"), "단계 이름: 배포 준비")
rs.append(done(A, "dev-claude", 11, "개발컴이 끝냄"))
ok(m_(rs, A)["stage"] == "prep", "개발컴 끝냄은 배포 준비를 넘기지 않음")
rs.append(done(A, "server-astra", 12, "배포 준비 완료\n대상 파일: npc/real/boss.txt, src/map/mob.cpp\n겹침: 없음\n순서·백업·복구: DEPLOY-PREP.md"))
t = m_(rs, A)
ok(t["stage"] == "queue" and t["status"] == "active" and not t.get("gate"), "배포 준비 끝 → 배포 대기열(관문 없음)")
ok(topics.whose_turn(t) is None, "대기열: 아무도 깨우지 않음")
ok(t["deploy_prep"]["files"] == ["npc/real/boss.txt", "src/map/mob.cpp"], f"준비 요약의 대상 파일 {t['deploy_prep'].get('files')}")
rs.append(done(A, "server-astra", 13, "대기열 중 끝냄(무시돼야)"))
ok(m_(rs, A)["stage"] == "queue", "대기열 중 끝냄은 단계를 넘기지 않음")

# B도 대기열로 — 같은 파일(겹침), X는 준비 중
t = to7(B, rs, 20); answer(t["gate"]["id"], "배포 대기열에 넣기", 30)
rs.append(done(B, "server-astra", 31, "준비\n대상 파일: src/map/mob.cpp\n겹침: T-20261003-dqaaaa (mob.cpp)"))
t = to7(X, rs, 40); answer(t["gate"]["id"], "서버컴에 반영", 50)  # 옛 선택지 답 → 대기열 쪽(배포 준비)
d = m_(rs)
ok(d[X]["stage"] == "prep", "옛 '서버컴에 반영' 답 → 바로 반영이 아니라 배포 준비")
ok(any(c["id"] == B and "src/map/mob.cpp" in c["files"] for c in d[A].get("deploy_conflicts") or []), "A↔B 겹침(같은 파일)")
ok(any(c["id"] == A for c in d[B].get("deploy_conflicts") or []), "B에서도 A 겹침 표시")

# 묶음 만들기 → 8b 배포(대화)
msg = batch("add", "R-20261005", [A, B], 60, "2026-10-05", "주말 점검 때")
d = m_(rs)
ok(d[A]["stage"] == "deploy" and d[A].get("deploy_session") and d[A]["deploy_batch"]["id"] == "R-20261005" and d[A]["deploy_batch"]["date"] == "2026-10-05",
   f"묶음에 넣음 → 8b 배포(서버컴 대화) {msg}")
ok(topics.whose_turn(d[A]) == "server-astra", "8b 배포 차례 = 서버컴 Astra(대화 세션)")
ok(list((tmp / "inbox-claude").glob("*USR-BATCH-*.md")), "사령탑 수신함에 묶음 알림")
# 빼기 → 대기열, 다시 다른 묶음에
batch("remove", "R-20261005", [B], 65, note="다음 묶음으로")
d = m_(rs); ok(d[B]["stage"] == "queue" and not d[B].get("deploy_batch") and not d[B].get("deploy_session"), "묶음에서 빼기 → 대기열로")
batch("add", "R-20261012", [B], 66, "2026-10-12")
ok(m_(rs, B)["deploy_batch"]["id"] == "R-20261012", "다음 묶음에 넣기")
batch("add", "R-20261006", [A], 67, "2026-10-06")
ok(m_(rs, A)["deploy_batch"]["id"] == "R-20261006", "배포 중 다른 묶음으로 옮김")
batch("add", "R-20261005", [A], 68)
# 배포 완료 → ★9(묶음 표시) → 완료 확정
rs.append(done(A, "server-astra", 70, "배포 완료(묶음 R-20261005, 2026-10-05 07:10, 맵서버 재시작 뒤 보스 출현 확인)"))
t = m_(rs, A)
ok(t["status"] == "review_user" and t["gate"]["n"] == 9 and t["gate"].get("batch") == "R-20261005" and t["deploy_batch"]["id"] == "R-20261005", "서버컴 배포 완료 → ★9(묶음 번호 붙음)")
ok(t["gate"]["options"][1].startswith("배포 실패"), "★9 선택지에 배포 실패·되돌림")
ok(t.get("deploy_prep", {}).get("files"), "★9에서도 배포 준비 요약 보임")
answer(t["gate"]["id"], "완료 확정", 75)
ok(m_(rs, A)["status"] == "done", "★9 완료 확정 → 완료")
# B: 배포 실패·되돌림 → 대기열 → 새 묶음 → 완료
rs.append(done(B, "server-astra", 80, "배포 실패·되돌림(묶음 R-20261012): 맵서버 로드 오류, 백업으로 복구 확인"))
t = m_(rs, B); ok(t["gate"]["n"] == 9, "실패 보고도 ★9로")
answer(t["gate"]["id"], "배포 실패·되돌림 — 다시 대기열로(배포본 그대로)", 85)
t = m_(rs, B); ok(t["stage"] == "queue" and not t.get("deploy_batch"), "배포 실패 → 다시 대기열(묶음 풀림)")
rs.append(done(B, "server-astra", 86, "대기열에서 끝냄"))
ok(m_(rs, B)["stage"] == "queue", "실패 뒤 대기열에서 옛 묶음 기록으로 바로 배포로 가지 않음")
batch("add", "R-20261019", [B], 90)
ok(m_(rs, B)["stage"] == "deploy", "새 묶음에 넣으면 다시 8b")
# X: ★9 배포본 고침 → 배포본 작성 → ★7
rs.append(done(X, "server-astra", 91, "준비\n대상 파일: db/item_db.yml\n겹침: 없음"))
batch("add", "R-20261019", [X], 92)
rs.append(done(X, "server-astra", 93, "배포 완료"))
answer(m_(rs, X)["gate"]["id"], "문제 있음 — 배포본 고침(배포본 작성으로)", 94, "아이템 설명 오타")
t = m_(rs, X); ok(t["stage"] == "pack" and not t.get("deploy_batch"), "★9 배포본 고침 → 배포본 작성(묶음 풀림)")
rs.append(done(X, "dev-claude", 95))
ok(m_(rs, X)["gate"]["n"] == 7, "고친 배포본 → ★7 다시")
# 대기열 다시 진행(보류 해제) 형식: topic-resume가 가져오기에서도 처리
print(f"\n실패 {fails}건")
sys.exit(1 if fails else 0)
