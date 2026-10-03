"""보류 메뉴·다시 진행(아키텍트 2026-10-03) 시험 — 임시 폴더."""
import json, os, sys, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
DASH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DASH))
tmp = Path(tempfile.mkdtemp(prefix="dash-park-"))
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
base = datetime(2026, 10, 3, 9, 0, tzinfo=KST)
def ts(m): return (base + timedelta(minutes=m)).isoformat(timespec="seconds")
def zts(m): return (base + timedelta(minutes=m)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
folder = tmp / "topics"; folder.mkdir()
def mk(tid, title, plan=True):
    (folder / tid).mkdir()
    (folder / tid / "topic.json").write_text(json.dumps({"id": tid, "title": title, "priority": "P2", "kind": "기능·개선"}, ensure_ascii=False), encoding="utf-8")
    (folder / tid / "claude.json").write_text(json.dumps({"assignee": "dev-claude", "assigned_at": ts(0), "status": "active", "status_at": ts(0), **({"plan": {"goal": "g"}} if plan else {})}), encoding="utf-8")
def udata():
    u = tmp / "data" / "user.json"; return u, (json.loads(u.read_text(encoding="utf-8")) if u.exists() else {})
def answer(gid, choice, m, note=""):
    u, d = udata(); d.setdefault("decisions_answered", []).append({"id": gid, "choice": choice, "note": note, "ts": zts(m)}); u.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
n_act = [0]
def resume(tid, m, note=""):
    n_act[0] += 1
    a = topics.clean_action({"id": f"A-20261003-rs{n_act[0]:04d}", "type": "topic-resume", "topic": tid, "note": note, "created_at": zts(m)})
    return topics.apply_action(C, a, "시험")
def done(tid, by, m, body="결과: 수정 끝, 파일 2개, 시험 방법 보스 처치 10회, 권장 다음 단계"):
    return {"topic": tid, "agent": by, "kind": "status", "status": "done", "ts": ts(m), "body": body}
def via_queue(tid, rs, m, bno):
    """★7 뒤 새 흐름(2026-10-03): 서버컴 배포 준비 끝냄 → 대기열 → 묶음 → 서버컴 배포 완료 끝냄 → ★9"""
    rs.append(done(tid, "server-astra", m, "배포 준비\n대상 파일: npc/x.txt\n겹침: 없음"))
    n_act[0] += 1
    topics.apply_action(C, topics.clean_action({"id": f"A-20261003-bq{n_act[0]:04d}", "type": "deploy-batch", "op": "add", "batch": bno,
                                                "topics": [tid], "created_at": zts(m + 1)}), "시험")
    rs.append(done(tid, "server-astra", m + 2, "반영 확인: 대상 파일 SHA256 일치, 맵서버 정상 로그"))
def m_(rs, tid): return {x["id"]: x for x in topics.merged_topics(folder, C, rs, known)}[tid]

# 형식 검사
try:
    topics.clean_action({"id": "A-20261003-bad001", "type": "topic-resume", "topic": "../x"}); bad = ""
except ValueError as e:
    bad = str(e)
ok("다시 진행 형식" in bad, "잘못된 주제 ID 거부")

# 1) ★4에서 보류 → 보류 메뉴 → 다시 진행 → ★4 다시 열림 → 통과 → ★5
T = "T-20261003-pk0001"; mk(T, "보스 알림")
rs = [done(T, "dev-claude", 5), done(T, "dev-claude", 10, "실게임 시험 준비: 체크리스트 3항목")]
g4 = m_(rs, T)["gate"]; ok(g4["n"] == 4, "전제: ★4")
answer(g4["id"], "보류", 15, "다음 주 점검 뒤에")
t = m_(rs, T); ok(t["status"] == "parked" and not t.get("gate") and not t.get("live_session"), "★4 보류 → 보류 상태(실게임 단계 아님)")
ok(t["gate_history"][-1]["act"] == "park" and t["gate_history"][-1]["note"] == "다음 주 점검 뒤에", "보류 기록·메모 남음(보류 메뉴에 표시)")
msg = resume(T, 30, "이제 점검 끝남")
t = m_(rs, T)
ok(t["status"] == "review_user" and t["gate"]["n"] == 4 and t["gate"]["id"] != g4["id"], f"다시 진행 → ★4 새 번호로 다시 열림 ({msg})")
ok("다시 진행" in t["gate"]["summary"] and t["gate_history"][-1].get("resumed_at") == zts(30), "다시 연 관문에 '다시 진행' 표시·재개 시각 기록")
ok(t.get("live_session"), "★4 다시 열림 → 실게임 대화 단계로")
ok(list((tmp / "inbox-claude").glob("*USR-RESUME-*.md")), "사령탑 수신함에 다시 진행 알림")
answer(t["gate"]["id"], "통과", 35)
t = m_(rs, T); ok(t["gate"]["n"] == 5, "다시 연 ★4 통과 → ★5")
# 2) ★5에서 또 보류 → 다시 진행 → ★5 다시 (보류·재개 여러 번)
answer(t["gate"]["id"], "보류", 40)
ok(m_(rs, T)["status"] == "parked", "★5 보류 → 보류")
resume(T, 50)
t = m_(rs, T); ok(t["status"] == "review_user" and t["gate"]["n"] == 5, "다시 진행 → ★5 다시 열림(두 번째 보류·재개)")
ok(sum(1 for h in t["gate_history"] if h["act"] == "park") == 2, "보류 두 번 모두 기록")
# 3) 재개가 보류보다 먼저면 보류를 풀지 않음
T3 = "T-20261003-pk0003"; mk(T3, "툴팁")
resume(T3, 1)
r3 = [done(T3, "dev-claude", 5), done(T3, "dev-claude", 10)]
answer(m_(r3, T3)["gate"]["id"], "보류", 20)
ok(m_(r3, T3)["status"] == "parked", "보류 전의 옛 '다시 진행'은 무시")
# 4) 진행 중 보류(아키텍트 보류 결정 기록) — 앞선 끝냄이 있어도 보류 유지(결함 수정) → 다시 진행 → 진행 중(자체 시험)
T4 = "T-20261003-pk0004"; mk(T4, "장비 UI")
r4 = [done(T4, "dev-claude", 5), {"topic": T4, "agent": "dev-claude", "kind": "status", "status": "parked", "ts": ts(20), "body": "[아키텍트 보류 결정] 우선순위 낮음"}]
t = m_(r4, T4); ok(t["status"] == "parked", f"자체 시험 중 아키텍트 보류 결정 → 보류(전에는 진행 중으로 덮임) {t['status']}")
resume(T4, 30)
t = m_(r4, T4); ok(t["status"] == "active" and t.get("stage") == "test", f"다시 진행 → 자체 시험 단계로 돌아감 {t['status']}/{t.get('stage')}")
ok(t.get("turn") == "dev-claude", "다시 진행 뒤 차례 = 담당(실행기가 깨움)")
# 5) 끝냄 없는 진행 중 보류 → 다시 진행 → 진행 중 / 진행 베이스 없으면 검토 중
T5 = "T-20261003-pk0005"; mk(T5, "깃 검토")
r5 = [{"topic": T5, "agent": "dev-claude", "kind": "status", "status": "parked", "ts": ts(5), "body": "[아키텍트 보류 결정] 나중에"}]
ok(m_(r5, T5)["status"] == "parked", "끝냄 없는 보류 → 보류")
resume(T5, 10)
ok(m_(r5, T5)["status"] == "active", "다시 진행 → 진행 중")
T6 = "T-20261003-pk0006"; mk(T6, "구상", plan=False)
r6 = [{"topic": T6, "agent": "dev-claude", "kind": "status", "status": "parked", "ts": ts(5), "body": "[아키텍트 보류 결정] 보류"}]
resume(T6, 10)
ok(m_(r6, T6)["status"] == "triage", "진행 베이스 없이 보류된 주제 → 다시 진행 시 검토 중")
# 6) 보류 뒤 다른 상태 기록이 오면 그 보류는 지난 것(끝냄 뒤 진행 중 덮지 않음)
T7 = "T-20261003-pk0007"; mk(T7, "드랍")
r7 = [done(T7, "dev-claude", 5), {"topic": T7, "agent": "dev-claude", "kind": "status", "status": "parked", "ts": ts(8), "body": "[아키텍트 보류 결정] x"},
      {"topic": T7, "agent": "dev-claude", "kind": "status", "status": "active", "ts": ts(9), "body": "다시 착수"}]
ok(m_(r7, T7)["status"] == "active", "보류 뒤 다시 착수 기록 → 진행 중")

# 7) (검토 P1·P2) 진행 중 보류를 다시 진행 → 상태 시각 = 재개 시각, 재개가 주제 기록(실행기 깨움·AI 메모)에
t = m_(r4, T4)
ok(t["status_at"] == zts(30), f"재개 뒤 상태 시각 = 재개 시각(노드 덮어쓰기 방지) {t['status_at']}")
ok(any(n.get("kind") == "resume" and n.get("by") == "user" for n in t["notes"]), "재개가 주제 기록에(실행기 깨움 신호·AI 지시문)")
t = m_(rs, T)
ok(any(n.get("kind") == "resume" and "이제 점검 끝남" in n["body"] for n in t["notes"]), "재개 메모가 주제 기록에 남음")
# 8) ★9 되돌림 지점 고르기(보고서 3번): '운영 반영만 다시' → 배포본 작성 → ★7 / '실게임부터 다시' → 진행
T9 = "T-20261003-pk0009"; mk(T9, "운영 반영 주제")
r9 = [done(T9, "dev-claude", 5), done(T9, "dev-claude", 10, "실게임 시험 준비: 체크리스트 3항목")]
answer(m_(r9, T9)["gate"]["id"], "통과", 12); answer("G5-" + m_(r9, T9)["gate_history"][0]["id"][3:], "배포본 만들기", 13)
r9 += [done(T9, "dev-claude", 20, "배포본: 파일 목록·SHA256·백업·복구 절차 정리 완료")]
answer(m_(r9, T9)["gate"]["id"], "서버컴에 반영", 25)
via_queue(T9, r9, 38, "R-20261005")
g9 = m_(r9, T9)["gate"]
ok(g9["n"] == 9 and len(g9["options"]) == 4 and "배포본 고침" in g9["options"][2], f"★9 선택지 4개(대기열로·배포본 고침·실게임부터) {g9['options']}")
answer(g9["id"], g9["options"][2], 45)
t = m_(r9, T9); ok(t["status"] == "active" and t.get("stage") == "pack", f"운영 반영만 다시 → 배포본 작성 단계 {t['status']}/{t.get('stage')}")
r9 += [done(T9, "dev-claude", 50, "배포본 고침: 누락 파일 추가, SHA256 갱신, 복구 절차 보강")]
ok(m_(r9, T9)["gate"]["n"] == 7, "고친 배포본 끝냄 → ★7 운영 반영 승인(실게임·배포본 결정 생략)")
T10 = "T-20261003-pk0010"; mk(T10, "되돌림 주제")
r10 = [done(T10, "dev-claude", 5), done(T10, "dev-claude", 10, "실게임 시험 준비: 체크리스트 3항목")]
answer(m_(r10, T10)["gate"]["id"], "통과", 12); answer("G5-" + m_(r10, T10)["gate_history"][0]["id"][3:], "배포본 만들기", 13)
r10 += [done(T10, "dev-claude", 20, "배포본: 파일 목록·SHA256·백업·복구 절차 정리 완료")]
answer(m_(r10, T10)["gate"]["id"], "서버컴에 반영", 25)
via_queue(T10, r10, 38, "R-20261005")
answer(m_(r10, T10)["gate"]["id"], "문제 있음 — 실게임부터 다시(진행으로 되돌림)", 45)
t = m_(r10, T10); ok(t["status"] == "active" and t.get("stage") == "work", "실게임부터 다시 → 진행")
answer2 = None
# 9) ★7 배포본 수정(가지 시뮬레이션): [배포본 수정]·새 규칙 뒤 메모만 → 배포본 작성(담당에게) → ★7 다시 / 정오 전 메모만 → 예전처럼 같은 관문
def to_g7(tid):
    rr = [done(tid, "dev-claude", 5), done(tid, "dev-claude", 10, "실게임 시험 준비: 체크리스트 3항목")]
    answer(m_(rr, tid)["gate"]["id"], "통과", 12); answer("G5-" + m_(rr, tid)["gate_history"][0]["id"][3:], "배포본 만들기", 13)
    rr += [done(tid, "dev-claude", 20, "배포본: 파일 목록·SHA256·백업·복구 절차 정리 완료")]
    return rr
T11 = "T-20261003-pk0011"; mk(T11, "배포본 수정 주제"); r11 = to_g7(T11)
g7 = m_(r11, T11)["gate"]; ok(g7["n"] == 7 and any(o.startswith("배포본 수정") for o in g7["options"]), f"★7 선택지에 배포본 수정 {g7['options']}")
answer(g7["id"], "배포본 수정(메모에 고칠 내용)", 30, "복구 절차에 DB 백업 추가")
t = m_(r11, T11); ok(t["status"] == "active" and t.get("stage") == "pack" and t.get("turn") == "dev-claude", "배포본 수정 → 배포본 작성(담당 차례)")
r11 += [done(T11, "dev-claude", 40, "배포본 고침: 복구 절차에 DB 백업 추가, SHA256 갱신")]
ok(m_(r11, T11)["gate"]["n"] == 7, "고친 배포본 → ★7 다시")
T12 = "T-20261003-pk0012"; mk(T12, "옛 메모 주제"); r12 = to_g7(T12)
answer(m_(r12, T12)["gate"]["id"], "", 30, "이거 확인")  # 09:30 — 새 규칙 전
t = m_(r12, T12); ok(t["status"] == "review_user" and t["gate"]["n"] == 7, "정오 전 ★7 메모만 → 예전처럼 같은 관문 다시(지난 흐름 안 바뀜)")
T13 = "T-20261003-pk0013"; mk(T13, "새 메모 주제"); r13 = to_g7(T13)
answer(m_(r13, T13)["gate"]["id"], "", 200, "SHA 다시")  # 12:20 — 새 규칙 뒤
t = m_(r13, T13); ok(t["status"] == "active" and t.get("stage") == "pack", "정오 뒤 ★7 메모만 → 배포본 수정과 같음")
print("모두 통과" if not fails else f"실패 {fails}건"); sys.exit(1 if fails else 0)
