"""일괄 최초 분해(서버컴 BATCH-DISPATCH-ASSIGNMENT 10-03) 시험 — 임시 폴더, 가짜 AI.
29개 미분해 주제 → 최초 분해 호출 최대 6회, P0/P1 우선·대기순, 정상/잘못된 응답 섞임, 중복 재실행, 잠금, 사용량 미확인, 보관·계획 완료 제외."""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

DASH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DASH))
KST = timezone(timedelta(hours=9))


def iso(m):
    return (datetime(2026, 10, 3, 9, 0, tzinfo=KST) + timedelta(minutes=m)).isoformat(timespec="seconds")


class BatchPlan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = Path(tempfile.mkdtemp(prefix="dash-batch-"))
        (tmp / "data").mkdir()
        cfg = {"pc": {"id": "server", "label": "서버컴", "role": "node"}, "node_data_dir": str(tmp / "nd"), "data_dir": str(tmp / "data"),
               "topics_dir": str(tmp / "topics"),
               "agents": [{"id": "server-astra", "ai": "gpt", "label": "Astra"}, {"id": "server-claude", "ai": "claude", "label": "C"}]}
        (tmp / "cfg.json").write_text(json.dumps(cfg), encoding="utf-8")
        os.environ["REAL_OPS_CONFIG"] = str(tmp / "cfg.json")
        import node
        import runner
        runner.CFG = node.load_cfg()
        cls.node, cls.runner = node, runner
        cls.calls = []
        cls.reply = {"actions": []}

        def fake_ai(agent, prompt, tag, ws=None):
            cls.calls.append(prompt)
            return json.dumps({"summary": "일괄 분해", "actions": cls.reply["actions"]}), "", ""
        runner.run_ai = fake_ai
        now = datetime.now(KST).isoformat(timespec="seconds")
        cls.agents = [{"id": a, "pc_label": a.split("-")[0], "label": a, "last_seen": now} for a in ("server-astra", "server-claude", "dev-claude", "dev-astra")]
        cls.agents[2]["usage"] = {"seen_at": now, "five_hour": {"pct": 30, "resets_at": "2026-10-03T20:00:00+09:00"}}
        cls.agents[3]["usage"] = {"seen_at": "2026-10-02T01:00:00+09:00", "five_hour": {"pct": 10}}  # 오래된 사용량 → 미확인

    def topics(self):
        out = []
        for i in range(29):
            pri = "P0" if i in (20, 27) else "P1" if i in (3, 15) else "P2"
            out.append({"id": f"T-20261003-bp{i:04d}", "title": f"주제 {i}", "priority": pri, "status": "triage", "status_at": iso(i),
                        "created_at": iso(i), "turn": "server-astra", "assignee": "server-astra", "command_mode": True, "notes": [], "body": f"목표 {i}"})
        out.append({**out[0], "id": "T-20261003-bparch", "archived": True})                       # 보관(재시작 전) 제외
        out.append({**out[0], "id": "T-20261003-bpback", "status": "backlog"})                    # 보관(시작 전) 제외
        out.append({**out[0], "id": "T-20261003-bpdone", "command": {"revision": 1, "tasks": [{"id": "a", "state": "ready", "assignee": "dev-claude"}]}})  # 이미 계획
        return out

    def data(self, topics, locks=None):
        return {"topics": topics, "agents": self.agents, "agent_locks": locks or {}, "meta": {}, "decisions_needed": [], "decisions_answered": [], "comments": []}

    @staticmethod
    def plan(tid, assignee="dev-claude", bad=False):
        tasks = [{"id": "impl", "title": "구현", "scope": "범위", "done_when": "기준", "assignee": assignee, "depends_on": ["nope"] if bad else []}]
        return {"type": "command", "cmd": "plan", "task": tid, "body": json.dumps({"tasks": tasks, "human_test": True, "test_reason": "실게임"}, ensure_ascii=False)}

    def plans_in_records(self):
        recs = self.node.load_records(self.runner.CFG)["topic_records"]
        return [r for r in recs if r.get("kind") == "command" and (r.get("op") == "plan" or (r.get("event") or {}).get("op") == "plan")]

    def test_1_batches_and_order(self):
        capped = self.runner.find_jobs(self.data(self.topics()), {"sig_v": self.runner.SIG_V}, only="server-astra")
        self.assertEqual([len(j["subjobs"]) for j in capped], [5, 5, 5], "한 회차 일감 3개 제한(MAX_PER_RUN) 안에서 15건")
        cap, self.runner.MAX_PER_RUN = self.runner.MAX_PER_RUN, 100
        try:
            jobs = self.runner.find_jobs(self.data(self.topics()), {"sig_v": self.runner.SIG_V}, only="server-astra")
        finally:
            self.runner.MAX_PER_RUN = cap
        pb = [j for j in jobs if j["kind"] == "plan_batch"]
        ids = [x["topic"]["id"] for j in pb for x in j["subjobs"]]
        self.assertEqual(len(pb), 6, "29건 → 일괄 호출 6번(두 회차)")
        self.assertTrue(all(len(j["subjobs"]) <= 5 for j in pb))
        self.assertEqual(ids[:4], ["T-20261003-bp0020", "T-20261003-bp0027", "T-20261003-bp0003", "T-20261003-bp0015"], "P0 → P1 → 대기순")
        self.assertEqual(ids[4], "T-20261003-bp0000", "같은 순위는 오래 기다린 순")
        self.assertFalse({"T-20261003-bparch", "T-20261003-bpback", "T-20261003-bpdone"} & set(ids), "보관·시작 전·이미 계획 제외")
        self.assertFalse([j for j in jobs if j["kind"] == "topic" and j["topic"]["id"] in ids], "묶인 주제는 따로 깨우지 않음")
        q = self.runner.queue_summary("server-astra", self.data(self.topics()), {"sig_v": self.runner.SIG_V})
        self.assertEqual(q.get("runnable"), 15, "작업자 카드 곧 실행은 묶인 주제 각각으로(한 회차 15건)")

    def test_2_mixed_responses_and_duplicates(self):
        topics = self.topics()
        state = {"sig_v": self.runner.SIG_V}
        data = self.data(topics, locks={"dev-astra": {"mode": "all"}})
        group = [j for j in self.runner.find_jobs(data, state, only="server-astra") if j["kind"] == "plan_batch"][0]
        g = [x["topic"]["id"] for x in group["subjobs"]]
        before = len(self.calls)
        self.reply["actions"] = [self.plan(g[0]), self.plan(g[1], bad=True), self.plan(g[2], assignee="dev-astra"),  # 정상 · 선행 작업 오류 · 잠긴 작업자
                                 self.plan(g[3], assignee="server-claude"), {"type": "note", "task": g[3], "body": "덤"}]  # 서버컴 Claude 배정 허용 · 잡음
        self.runner.run_job(group, data, state)                                                       # g[4]는 답 없음
        self.assertEqual(len(self.calls) - before, 1, "5건을 모델 호출 1번으로")
        prompt = self.calls[-1]
        self.assertIn("dev-astra", prompt)
        self.assertIn("배정 불가(잠금)", prompt)
        self.assertIn("미확인(추정하지 말 것)", prompt, "오래된 사용량은 미확인")
        self.assertIn("남음 70%", prompt, "최근 사용량은 그대로")
        planned = {r["topic"] for r in self.plans_in_records()}
        self.assertEqual(planned & set(g), {g[0], g[3]}, "정상 계획만 채택(잘못된 응답이 다른 주제를 막지 않음)")
        st = lambda tid: self.runner.job_state(state, {"topic": {"id": tid}, "sig": tid})
        self.assertTrue(all(st(t).get("retry_after") for t in (g[1], g[2], g[4])), "틀린·빠진 주제만 다음 회차에 다시")
        self.assertFalse(st(g[0]).get("retry_after"))
        # 같은 묶음을 다시 돌려도(게시본이 아직 옛 상태여도) 채택된 계획을 덮거나 중복 배정하지 않음
        self.reply["actions"] = [self.plan(t) for t in g]
        self.runner.run_job(group, data, state)
        counts = {t: sum(1 for r in self.plans_in_records() if r["topic"] == t) for t in g}
        self.assertEqual(counts[g[0]], 1, "이미 채택된 계획은 다시 적용되지 않음(revision 충돌)")
        self.assertEqual(counts[g[1]], 1, "재시도에서 고친 계획은 채택")


if __name__ == "__main__":
    unittest.main()
