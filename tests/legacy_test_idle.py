"""하루 한도 폐지·헛돎 알림(아키텍트 결정 2026-10-03) 시험 — 임시 폴더, 가짜 AI."""
import json, os, sys, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
DASH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DASH))
tmp = Path(tempfile.mkdtemp(prefix="dash-idle-"))
fails = 0
def ok(c, m):
    global fails
    print(("통과 " if c else "실패 ") + m); fails += 0 if c else 1
(tmp / "data").mkdir()
cfg = {"pc": {"id": "dev", "label": "개발컴", "role": "hub"}, "node_data_dir": str(tmp / "nd"), "data_dir": str(tmp / "data"), "topics_dir": str(tmp / "topics"),
       "agents": [{"id": "dev-claude", "ai": "claude", "label": "C"}, {"id": "dev-astra", "ai": "gpt", "label": "A"}]}
(tmp / "cfg.json").write_text(json.dumps(cfg), encoding="utf-8"); os.environ["REAL_OPS_CONFIG"] = str(tmp / "cfg.json")
import node, runner
runner.CFG = node.load_cfg()
runner.ensure_work = lambda j, create: None
runner.build_prompt = lambda *a, **k: "시험"
reply = {"actions": []}
runner.run_ai = lambda agent, prompt, tag, ws=None: (json.dumps({"summary": reply.get("summary", "요약"), "actions": reply["actions"]}), "", "")
KST = timezone(timedelta(hours=9))
T = "T-20261003-idle01"
topic = {"id": T, "title": "헛돎 시험", "turn": "dev-claude", "status": "active", "assignee": "dev-claude", "plan": {"goal": "g"}, "plan_by": "dev-claude", "notes": []}
data = {"topics": [topic], "agents": [], "meta": {}, "decisions_needed": [], "decisions_answered": [], "comments": []}
state = {"sig_v": runner.SIG_V}
job = lambda: {"agent": "dev-claude", "kind": "topic", "mode": "plan", "sig": "s", "reason": "시험", "topic": topic}
st = lambda: runner.job_state(state, job())

# 1) 하루 횟수 한도 없음: 진척 있는 실행 12번 → 계속 깨울 수 있음
reply["actions"] = [{"type": "state", "status": "ready", "body": "상태 바뀜"}]
for i in range(12):
    runner.run_job({**job(), "topic": {**topic, "status": "triage"}}, data, state)
s = st()
ok(s.get("count") == 12 and not s.get("retry_after") and not s.get("idle_runs"), f"진척 있는 실행 12번: 간격·헛돎 없음 ({s.get('count')}회)")
ok(any(j["topic"]["id"] == T for j in runner.find_jobs(data, json.loads(json.dumps(state)), only="dev-claude")), "12번 돌아도(옛 한도 10회) 다음 실행 대상")
q = runner.queue_summary("dev-claude", data, json.loads(json.dumps(state)))
ok("limit" not in q and not q["idle"], "대기열에 '하루 한도' 판정 없음 · 헛돎 알림 없음")

# 2) 헛돎: 메모만 3번 → 알림(번호 = 헛돎 시작 시각), 4번째도 같은 번호, 간격은 다음 동기화 → 30분
reply["actions"] = [{"type": "note", "kind": "memo", "body": "확인 중"}]
seen = []
for i in range(4):
    st().pop("retry_after", None)  # 시험: 간격을 건너뛰고 바로 다시 돌림
    runner.run_job(job(), data, state)
    q = runner.queue_summary("dev-claude", data, json.loads(json.dumps(state)))
    seen.append((st()["idle_runs"], [(x["runs"], x["since"]) for x in q["idle"]], bool(st().get("retry_after"))))
ok([x[0] for x in seen] == [1, 2, 3, 4], f"헛돎 횟수 1→4 {[x[0] for x in seen]}")
ok(not seen[0][1] and not seen[1][1] and seen[2][1] and seen[3][1], "3번째 헛돎부터 알림")
ok(seen[2][1][0][1] == seen[3][1][0][1] == st()["idle_since"], "알림 번호(시작 시각) 고정 — 같은 헛돎이면 새 알림 안 뜸")
ok([x[2] for x in seen] == [False, False, True, True], f"간격: 2번까지 바로, 3번째부터 30분 {[x[2] for x in seen]}")
q = runner.queue_summary("dev-claude", data, json.loads(json.dumps(state)))
ok(q["idle"][0]["every"] == 30 and q["idle"][0]["last"] == "요약", "알림에 간격(30분)·마지막 요약")
for i in range(2):
    st().pop("retry_after", None); runner.run_job(job(), data, state)
ra = datetime.fromisoformat(st()["retry_after"])
ok(st()["idle_runs"] == 6 and 110 <= (ra - datetime.now(KST)).total_seconds() / 60 <= 121, "5번째부터 2시간 간격(멈추지 않음)")
q = runner.queue_summary("dev-claude", data, json.loads(json.dumps(state)))
ok(q["idle"][0]["every"] == 120 and q["items"][T] == "retry", "알림 '2시간마다', 대기열은 '재시도 대기'(멈춤 아님)")

# 3) 진척 생기면 알림 해제
st().pop("retry_after", None)
reply["actions"] = [{"type": "handoff", "to": "dev-astra", "body": "넘김"}]
runner.run_job(job(), data, state)
q = runner.queue_summary("dev-claude", data, json.loads(json.dumps(state)))
ok(not st().get("idle_runs") and "idle_since" not in st() and not q["idle"], "진척(인계 시도) → 헛돎 0, 알림 사라짐")

# 4) 진척 판정 세부: 같은 진행 베이스 재제출은 진척 아님(무한 즉시 반복 방지), 빈 답은 헛돎
reply["actions"] = [{"type": "plan", "plan": {"goal": "g"}}]
runner.run_job(job(), data, state)
ok(st().get("idle_runs") == 1, "진행 베이스가 이미 있는데 다시 낸 plan → 헛돎")
reply["actions"] = []
st().pop("retry_after", None); runner.run_job(job(), data, state)
ok(st().get("idle_runs") == 2, "빈 답 → 헛돎")
reply["actions"] = [{"type": "claim", "body": "착수"}]
st().pop("retry_after", None); runner.run_job(job(), data, state)
ok(not st().get("idle_runs"), "착수 기록 → 진척")
# 5) 아키텍트 답을 기다리는 주제·대화 세션이 잡은 주제는 헛돎 알림에서 뺌
for i in range(3):
    st().pop("retry_after", None); reply["actions"] = [{"type": "note", "kind": "memo", "body": "x"}]; runner.run_job(job(), data, state)
d2 = {**data, "decisions_needed": [{"id": "DN-9", "_author": "dev-claude", "task_id": T, "question": "?"}]}
ok(not runner.queue_summary("dev-claude", d2, json.loads(json.dumps(state)))["idle"], "답 기다리는 주제는 헛돎 알림 안 올림")
# 6) (검토 P1) 가짜 진척은 헛돎: 이미 착수한 뒤 또 착수, 지금과 같은 상태, 거부된 행동, 요약 빠진 끝냄
def fresh():
    st().clear()
def idle_after(actions, n=3, **topic_extra):
    fresh(); reply["actions"] = actions
    tp = {**topic, **topic_extra}
    for i in range(n):
        st().pop("retry_after", None)
        runner.run_job({**job(), "topic": tp}, data, state)
    return st().get("idle_runs", 0), bool(st().get("retry_after"))
claimed = {"notes": [{"by": "dev-claude", "kind": "claim", "ts": "2026-10-03T01:00:00+09:00"}]}
ok(idle_after([{"type": "claim", "body": "착수"}], **claimed) == (3, True), "이미 착수한 뒤 또 착수 → 헛돎(3번째부터 간격)")
ok(idle_after([{"type": "state", "status": "active", "body": "진행 중"}]) == (3, True), "지금과 같은 상태(진행 중) 반복 → 헛돎")
ok(idle_after([{"type": "handoff", "to": "dev-claude", "body": "나에게"}])[0] == 3, "거부된 인계(자기 자신) → 헛돎")
ok(idle_after([{"type": "handoff", "to": "nobody-x", "body": "?"}])[0] == 3, "거부된 인계(없는 작업자) → 헛돎")
r = idle_after([{"type": "state", "status": "done", "body": "끝"}])
ok(r == (3, True), f"요약 빠진 끝냄 반복 → 헛돎·간격(무한 즉시 반복 없음) {r}")
fresh(); reply["actions"] = [{"type": "note", "kind": "review", "body": "검토: 범위 적절"}]
runner.run_job({**job(), "topic": {**topic, "assignee": "dev-astra", "reviewer": "dev-claude"}}, data, state)
ok(not st().get("idle_runs"), "교차 검토자의 검토 메모 → 진척")
fresh(); reply["actions"] = [{"type": "plan", "plan": {"goal": "새 목표"}}]
runner.run_job({**job(), "topic": {**topic, "plan_by": "dev-astra"}}, data, state)
ok(not st().get("idle_runs"), "인계받아 다른 작업자 진행 베이스를 새로 씀 → 진척")
fresh(); st()["idle_runs"] = 5  # 배포 전부터 헛돌던 주제(시작 시각 없음)
q = runner.queue_summary("dev-claude", data, json.loads(json.dumps(state)))
ok(q["idle"] and q["idle"][0]["since"] == "", "시작 시각 없는 옛 헛돎 → 번호 고정('')")
reply["actions"] = [{"type": "note", "kind": "memo", "body": "x"}]; runner.run_job(job(), data, state)
ok(st().get("idle_since"), "다음 헛돎 실행 때 시작 시각 채움")
# 7) (2차 검토) 요청받은 작업자의 review 메모, 검토자의 plan, 단계 담당 아닌 끝냄→메모, 관문 지난 주제의 같은 상태 반복은 헛돎
ok(idle_after([{"type": "note", "kind": "review", "body": "검토"}], assignee="dev-astra", reviewer="dev-claude",
              open_request={"id": "Q-1", "to": "dev-claude", "from": "dev-astra"})[0] == 3, "요청받은 작업자의 review 메모 → 헛돎(답해야 진척)")
ok(idle_after([{"type": "plan", "plan": {"goal": "검토자 계획"}}], assignee="dev-astra", reviewer="dev-claude", plan_by="dev-astra")[0] == 3, "검토자가 낸 진행 베이스 → 헛돎")
ok(idle_after([{"type": "state", "status": "done", "body": "끝냈습니다: " + "요약 " * 20}], assignee="dev-astra", reviewer="server-x")[0] == 3,
   "단계 담당 아닌 작업자의 끝냄(메모로 바뀜) → 헛돎(검토 차례 아님)")
ok(idle_after([{"type": "state", "status": "ready", "body": "준비"}], status="active")[0] == 3, "관문 지난(진행 중) 주제에서 같은 상태 반복 → 헛돎")
fresh(); reply["actions"] = [{"type": "state", "status": "done", "body": "끝냈습니다: " + "요약 " * 20}]
runner.run_job({**job(), "topic": {**topic, "assignee": "dev-astra", "reviewer": "dev-claude"}}, data, state)
ok(not st().get("idle_runs"), "교차 검토 차례의 끝냄(→검토 메모) → 진척")
# 8) (포크 s16·s36) 감속 중이어도 새 입력(아키텍트 대화)이 오면 바로 깨움 · 실행기 자신의 '이어서'만 바뀐 것은 계속 감속 · 실패 재시도는 기다림
fresh(); reply["actions"] = [{"type": "note", "kind": "memo", "body": "확인 중"}]
for i in range(3):
    st().pop("retry_after", None); runner.run_job(job(), data, state)
ok(st().get("retry_after") and st().get("retry_kind") == "slow", "전제: 헛돎 3번 → 감속(slow)")
md = "impl" if runner.impl_allowed() else "plan"  # find_jobs와 같은 모드
st()["last_parts"] = runner.sig_parts(topic, "dev-claude", md, data, st())
st()["last_sig"] = runner.topic_sig(topic, "dev-claude", md, data, st())
ids = lambda d: [j["topic"]["id"] for j in runner.find_jobs(d, json.loads(json.dumps(state)), only="dev-claude") if j.get("topic")]
ok(T not in ids(data), "새 입력 없음 → 감속 유지")
st()["cont"] = st().get("cont", 0) + 1
ok(T not in ids(data), "실행기 자신의 '이어서'(cont)만 바뀜 → 감속 유지")
d2 = {**data, "comments": [{"target": {"kind": "topic", "id": T}, "by": "user", "body": "이렇게 해: A안으로 진행"}]}
js = [j for j in runner.find_jobs(d2, json.loads(json.dumps(state)), only="dev-claude") if (j.get("topic") or {}).get("id") == T]
ok(js and "새 입력" in js[0]["reason"], f"아키텍트 대화 → 감속 중이어도 바로 깨움 ({js[0]['reason'] if js else '-'})")
st()["retry_kind"] = "error"
ok(T not in ids(d2), "실행 실패 재시도 대기는 새 입력이 와도 기다림")
st()["retry_kind"] = "slow"
d3 = {**data, "decisions_needed": [{"id": "DN-7", "_author": "dev-claude", "task_id": T, "question": "?"}], "decisions_answered": [{"id": "DN-7", "choice": "A"}]}
ok(any(j["kind"] == "answer" for j in runner.find_jobs(d3, json.loads(json.dumps(state)), only="dev-claude")), "감속 중이어도 아키텍트 답은 바로 전달")
st().pop("retry_kind", None); st()["idle_runs"] = 5
ok(any((j.get("topic") or {}).get("id") == T for j in runner.find_jobs(d2, json.loads(json.dumps(state)), only="dev-claude")), "옛 상태(감속 종류 없음·헛돎 5회) → 감속으로 보고 새 입력에 깨움")
d4 = {**data, "topics": [{**topic, "notes": [{"by": "dev-astra", "kind": "memo", "ts": "2026-10-03T05:00:00+09:00", "body": "다른 AI 메모"}]}]}
ok(T not in ids(d4), "다른 AI 작업자의 메모만 늘어남 → 감속 유지(AI끼리 빠른 반복 방지)")
# 9) 관문을 여는 끝냄은 맨 앞 3줄(핵심·정할 것·권장)이 있어야 함(아키텍트 2026-10-03)
LONG = "무엇을 했나: 수정 후보 작성, 작업물 real-work/work/FT-x, 시험 방법: 재현 절차 3단계 실행해 확인"
GOOD = "핵심: 원래 메모는 '트레저 고블린.' 한 줄\n정할 것: 구체화해 후속 구현 / 메모로 두고 완료\n권장: 메모로 두고 완료\n" + LONG
def try_done(body, **tp):
    j = {**job(), "topic": {**topic, **tp}}
    dn, fl = runner.apply(j, {"actions": [{"type": "state", "status": "done", "body": body}]}, data)
    return dn, fl, j.get("redo")
dn, fl, rd = try_done(LONG, stage="test", stage_owner="dev-claude")
ok(any("맨 앞 3줄" in x for x in fl) and rd and "state" not in dn, "자체 시험 끝냄(→★4)인데 3줄 없음 → 거부·다시 요약")
dn, fl, rd = try_done(GOOD, stage="test", stage_owner="dev-claude")
ok("state" in dn and not rd, "3줄 있으면 받음")
dn, fl, rd = try_done(LONG, kind="조사·분석")
ok(any("맨 앞 3줄" in x for x in fl), "조사 주제 진행 끝냄(→결과 확인)도 3줄 필요")
dn, fl, rd = try_done(LONG, stage="work", kind="기능·개선")
ok("state" in dn and not rd, "구현 주제 진행 끝냄(→자체 시험, 관문 없음)은 3줄 없어도 받음")
# 10) (검토 P2) 끝냄이 거부된 실행은 진척 없음 → 3번째부터 간격, 다음 지시문에 거부 사유
fresh(); reply["actions"] = [{"type": "claim", "body": "착수"}, {"type": "state", "status": "done", "body": LONG}]
tp = {**topic, "stage": "test", "stage_owner": "dev-claude", "notes": [{"by": "dev-claude", "kind": "claim", "ts": "2026-10-03T01:00:00+09:00"}]}
for i in range(3):
    st().pop("retry_after", None)
    runner.run_job({**job(), "topic": tp}, data, state)
ok(st().get("idle_runs") == 3 and st().get("retry_after"), f"끝냄 거부가 반복되면 헛돎으로 세어 간격 {st().get('idle_runs')}")
ok(any("맨 앞 3줄" in x for x in (st().get("last_result") or {}).get("failed", [])), "거부 사유가 실행 기록에(다음 지시문에 들어감)")
print("모두 통과" if not fails else f"실패 {fails}건"); sys.exit(1 if fails else 0)
