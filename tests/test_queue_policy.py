"""r6 시험: 막힌 안건 건너뛰기·결정 우선 재개(서버컴 45e1a32), 연속 실행 실패 → 환경 차단. 바뀐 동작만 확인한다(전체 회귀는 기존 시험)."""
import copy
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
KST = timezone(timedelta(hours=9))


def iso(m):
    return (datetime.now(KST) + timedelta(minutes=m)).isoformat(timespec="seconds")


class QueuePolicy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = Path(tempfile.mkdtemp(prefix="dash-queue-"))
        (tmp / "data").mkdir()
        cfg = {"pc": {"id": "dev", "label": "개발컴", "role": "hub"}, "node_data_dir": str(tmp / "nd"), "data_dir": str(tmp / "data"),
               "topics_dir": str(tmp / "topics"), "agents": [{"id": "dev-astra", "ai": "gpt", "label": "Astra"}]}
        (tmp / "cfg.json").write_text(json.dumps(cfg), encoding="utf-8")
        os.environ["REAL_OPS_CONFIG"] = str(tmp / "cfg.json")
        import node
        import runner
        runner.CFG = node.load_cfg()
        cls.node, cls.runner = node, runner

    def topic(self, n, pri, waited, **kw):
        t = {"id": f"T-20261004-q{n:05d}", "title": f"주제 {n}", "priority": pri, "status": "active", "status_at": iso(-waited),
             "created_at": iso(-waited), "turn": "dev-astra", "assignee": "dev-astra", "plan": {"goal": "g"}, "notes": []}
        t.update(kw)
        return t

    def data(self, topics):
        return {"topics": topics, "agents": [{"id": "dev-astra", "last_seen": iso(0)}], "agent_locks": {}, "meta": {},
                "decisions_needed": [], "decisions_answered": [], "comments": []}

    def order(self, topics, state=None):
        st = state or {"sig_v": self.runner.SIG_V}
        cap, self.runner.MAX_PER_RUN = self.runner.MAX_PER_RUN, 100
        try:
            return [j["topic"]["id"][-3:] for j in self.runner.find_jobs(self.data(topics), st, only="dev-astra")]
        finally:
            self.runner.MAX_PER_RUN = cap

    def test_priority_then_age_and_p0_first(self):
        ts = [self.topic(1, "P2", 300), self.topic(2, "P1", 10), self.topic(3, "P3", 900), self.topic(4, "P0", 1), self.topic(5, "P1", 200)]
        self.assertEqual(self.order(ts), ["004", "005", "002", "001", "003"])

    def test_decision_resumes_before_other_priorities(self):
        """마지막 처리 뒤 아키텍트 관문 답이 온 P3 안건이 P1보다 먼저(같은 실행에서 P0는 여전히 맨 앞)."""
        resumed = self.topic(3, "P3", 900, gate_history=[{"id": "G4-x", "answered_at": iso(-1), "act": "test"}])
        ts = [self.topic(1, "P1", 10), resumed, self.topic(4, "P0", 1)]
        state = {"sig_v": self.runner.SIG_V, "topics": {resumed["id"]: {"last_result": {"at": iso(-30)}, "last_sig": "old"}}}
        self.assertEqual(self.order(ts, state), ["004", "003", "001"])
        # 이미 처리한 결정(답 뒤에 실행함)은 우선권이 없다
        state["topics"][resumed["id"]]["last_result"]["at"] = iso(0)
        state["topics"][resumed["id"]]["last_sig"] = "old"
        self.assertEqual(self.order(ts, state), ["004", "001", "003"])

    def test_cap_takes_highest_ranked(self):
        ts = [self.topic(i, "P2", 100 - i) for i in range(1, 6)] + [self.topic(9, "P1", 1)]
        jobs = self.runner.find_jobs(self.data(ts), {"sig_v": self.runner.SIG_V}, only="dev-astra")
        self.assertEqual(len(jobs), self.runner.MAX_PER_RUN)
        self.assertEqual(jobs[0]["topic"]["id"][-3:], "009")

    def test_repeated_failure_becomes_env_block_and_skips_only_that_topic(self):
        r = self.runner
        st = {}
        mins = []
        for _ in range(3):
            before = datetime.now(KST)
            r.fail_backoff(st, False, "error", "git: pipe 생성 실패")
            mins.append(round((datetime.fromisoformat(st["retry_after"]) - before).total_seconds() / 60))
        self.assertEqual(mins, [10, 30, 60])
        self.assertEqual(st["retry_kind"], "env")
        self.assertEqual(st["env_block"]["fails"], 3)
        blocked, other = self.topic(1, "P0", 10), self.topic(2, "P3", 10)
        state = {"sig_v": r.SIG_V, "topics": {blocked["id"]: st}}
        self.assertEqual(self.order([blocked, other], copy.deepcopy(state)), ["002"], "막힌 안건만 빠지고 다른 주제는 실행")
        q = r.queue_summary("dev-astra", self.data([blocked, other]), copy.deepcopy(state))
        self.assertEqual(q["items"][blocked["id"]], "env")
        self.assertEqual(q["env"], 1)
        self.assertEqual(q["env_blocked"][0]["topic"], blocked["id"])
        self.assertIn("pipe", q["env_blocked"][0]["error"])
        self.assertEqual(q["order"], [other["id"]])
        # 새 입력(아키텍트 메모)이 오면 대기 시간 전이라도 바로 다시 깨운다
        st["last_parts"] = r.sig_parts(blocked, "dev-astra", "impl", self.data([]), st)
        st["last_sig"] = "old"
        talk = self.data([blocked, other])
        talk["comments"] = [{"target": {"id": blocked["id"]}, "by": "user"}]
        jobs = r.find_jobs(talk, {"sig_v": r.SIG_V, "topics": {blocked["id"]: st}}, only="dev-astra")
        self.assertEqual(jobs[0]["topic"]["id"], blocked["id"])
        self.assertTrue(jobs[0]["decision"])
        # 성공하면 풀린다
        r.clear_fail(st)
        self.assertNotIn("env_block", st)
        self.assertNotIn("fail_n", st)

    def test_needs_user_failure_waits_at_least_30_minutes(self):
        st = {}
        before = datetime.now(KST)
        self.runner.fail_backoff(st, True, "auth", "로그인 만료")
        self.assertGreaterEqual((datetime.fromisoformat(st["retry_after"]) - before).total_seconds(), 29 * 60)
        self.assertEqual(st["retry_kind"], "error")

    def test_prompts_carry_right_size_rule(self):
        import command
        text = command.prompt({"command_mode": True, "command": command.initial()}, "server-astra")
        self.assertIn("시험 결과를 기다리지 말고 바로 state done", text)
        self.assertIn("직접 영향만", text)
        batch = self.runner.plan_batch_prompt([{"topic": self.topic(1, "P2", 1)}], self.data([]))
        self.assertIn("범위는 요청 크기에 맞춘다", batch)


if __name__ == "__main__":
    unittest.main()
