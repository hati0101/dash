"""r7 시험: 작업 흐름 경량화(아키텍트 10-04) — 작은 일은 시험 단계 없이 ★4, 크기 검증, 사령탑 검수 묶음. 바뀐 동작만 확인한다."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import command
import node
import runner
import topics
from test_review5 import Base, KNOWN


class SmallTask(Base):
    def plan(self, size, tasks=None):
        self.cmd(0, 'plan', body=json.dumps({'tasks': tasks or [self.task], 'size': size}))

    def test_small_goes_straight_to_gate4_and_reject_returns_to_work(self):
        self.plan('small')
        self.assertEqual(self.view()['command']['size'], 'small')
        self.submit(1); self.done(2, 'server-astra')
        g = self.view()['gate']
        self.assertEqual(g['n'], 4, '작은 일은 자체 시험 단계 없이 바로 ★4')
        self.answer(g, '문제 있음', 3)
        t = self.view()
        self.assertEqual((t['stage'], t['turn']), ('work', 'server-astra'))
        self.assertFalse(t.get('test_reset_needed'))
        self.assertIsNotNone(command.pending_return(t), '고칠 작업 amend 전에는 보완 미처리')
        done, failed = self.runner_done(); self.assertTrue(failed)
        self.cmd(4, 'amend', body=json.dumps({'tasks': [self.task, dict(self.task, id='fix', title='실게임 지적 수정', depends_on=['code'])]}))
        self.submit(5, 'fix'); self.done(6, 'server-astra')
        g2 = self.view()['gate']
        self.assertEqual(g2['n'], 4); self.assertNotEqual(g2['id'], g['id'])

    def test_size_validation_and_normal_unchanged(self):
        with self.assertRaises(ValueError):
            self.plan('small', [self.task, dict(self.task, id='b'), dict(self.task, id='c')])
        with self.assertRaises(ValueError):
            self.plan('huge')
        self.plan('normal')
        self.submit(1); self.done(2, 'server-astra')
        self.assertEqual(self.view()['stage'], 'test', '보통 크기는 예전처럼 자체 시험 단계')

    def test_prompts_explain_size(self):
        self.plan('small')
        text = command.prompt(self.view(), 'server-astra')
        self.assertIn('크기=small', text); self.assertIn('교차 검토 작업은 risk에만', text)
        self.assertIn('size를 꼭 정한다', runner.plan_batch_prompt([{'topic': self.view()}], {'agents': []}))


class ReviewBatch(Base):
    IDS = ('T-20261004-rb0001', 'T-20261004-rb0002', 'T-20261004-rb0003')

    def setUp(self):
        super().setUp()
        for tid in self.IDS:
            p = self.root / 'topics' / tid
            topics.write_json(p / 'topic.json', dict(id=tid, title=f'검수 {tid[-1]}', kind='기능·개선', command_mode=True, priority='P2'))
            topics.write_json(p / 'claude.json', dict(assignee='server-astra', assigned_at=self.ts(0)))
            wid = 'FT-' + tid[2:]
            f = self.root / f'work/{wid}/dev-claude/result.md'; f.parent.mkdir(parents=True, exist_ok=True); f.write_text(tid, encoding='utf-8')
            self.on(tid, 0, 'plan', body=json.dumps({'tasks': [self.task]}))
            self.on(tid, 1, 'submit', 'dev-claude', options=[f'work/{wid}/dev-claude/result.md'])

    def views(self):
        return {t['id']: t for t in topics.merged_topics(self.root / 'topics', self.cfg, node.load_records(self.cfg)['topic_records'], KNOWN)}

    def on(self, tid, n, op, who='server-astra', file='code', body='근거 확인', **kw):
        with patch.object(node, 'now_iso', return_value=self.ts(n)):
            return command.apply_action({'topic': self.views()[tid], 'agent': who, 'work_id': 'FT-' + tid[2:]}, dict(cmd=op, file=file, body=body, **kw),
                                        self.cfg, KNOWN, set(), self.root)

    def test_one_call_reviews_many_and_bad_answers_only_retry_that_topic(self):
        vs = self.views()
        data = {'topics': [vs[i] for i in self.IDS], 'agents': [{'id': a} for a in KNOWN], 'agent_locks': {}, 'meta': {},
                'decisions_needed': [], 'decisions_answered': [], 'comments': []}
        with patch.object(node, 'my_agents', return_value={'server-astra': {'ai': 'gpt'}}):
            jobs = runner.find_jobs(data, {'sig_v': runner.SIG_V}, only='server-astra')
        self.assertEqual([j['kind'] for j in jobs], ['review_batch'])
        self.assertEqual(sorted(x['topic']['id'] for x in jobs[0]['subjobs']), list(self.IDS))
        prompt = runner.review_batch_prompt(jobs[0]['subjobs'])
        self.assertIn('완료 기준: 근거 확인', prompt); self.assertIn('accept 또는 revise', prompt)
        a, b, c = self.IDS
        reply = {'summary': '검수 묶음', 'actions': [
            {'type': 'command', 'cmd': 'accept', 'task': a, 'file': 'code', 'body': '근거와 완료 기준 일치'},
            {'type': 'command', 'cmd': 'plan', 'task': a, 'body': '{}'},  # 묶음에서 받지 않는 행동
            {'type': 'command', 'cmd': 'revise', 'task': b, 'file': 'code', 'body': '근거 파일에 확인 결과가 없음'}]}
        calls = []
        with patch.object(node, 'my_agents', return_value={'server-astra': {'ai': 'gpt'}}), \
                patch.object(runner, 'run_ai', side_effect=lambda *a_, **k: (calls.append(1), (json.dumps(reply), '', ''))[1]):
            st = {'sig_v': runner.SIG_V}
            runner.run_job(jobs[0], data, st)
        self.assertEqual(len(calls), 1, '모델 호출 한 번')
        vs = self.views()
        self.assertEqual(vs[a]['command']['tasks'][0]['state'], 'accepted')
        self.assertEqual((vs[b]['command']['tasks'][0]['state'], vs[b]['command']['tasks'][0]['attempt']), ('ready', 2))
        self.assertEqual(vs[c]['command']['tasks'][0]['state'], 'review', '답이 없는 주제는 그대로(다음에 그 주제만)')
        self.assertIn('last_sig', st['topics'][a]); self.assertNotIn('last_sig', st['topics'].get(c, {}))

    def test_single_reviewable_topic_is_not_batched(self):
        vs = self.views()
        data = {'topics': [vs[self.IDS[0]]], 'agents': [{'id': a} for a in KNOWN], 'agent_locks': {}, 'meta': {},
                'decisions_needed': [], 'decisions_answered': [], 'comments': []}
        with patch.object(node, 'my_agents', return_value={'server-astra': {'ai': 'gpt'}}):
            jobs = runner.find_jobs(data, {'sig_v': runner.SIG_V}, only='server-astra')
        self.assertEqual([j['kind'] for j in jobs], ['topic'])


if __name__ == '__main__':
    unittest.main()
