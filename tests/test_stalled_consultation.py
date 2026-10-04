"""진척 없음 자문, 시험 종료 차례, 과거 거절 기록의 회귀 검사. 외부 쓰기 없음."""
import copy
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.environ.get('FLOW_TEST_ROOT') or str(Path(__file__).resolve().parents[1]))
import build
import command
import runner
import topics
import testflow


class Consultation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cfg = {'pc': {'id': 'fixture', 'role': 'node'}, 'node_data_dir': self.tmp.name,
                    'agents': [{'id': 'dev-claude', 'ai': 'claude'}, {'id': 'server-astra', 'ai': 'gpt'}]}
        p = patch.object(runner, 'CFG', self.cfg); p.start(); self.addCleanup(p.stop)
        self.t = dict(id='T-20261004-abcdef', title='시험 주제', status='active', priority='P2',
                      turn='dev-claude', assignee='dev-claude', plan={'goal': '작업'}, notes=[])
        self.d = dict(topics=[self.t], comments=[], agents=[], decisions_needed=[], decisions_answered=[])
        self.st = dict(idle_runs=3, idle_since='2026-10-04T10:00:00+09:00', last_result={'summary': '실행 권한이 없어 반복 대기', 'at': '2026-10-01T10:00:00+09:00'})
        mode = 'impl' if runner.impl_allowed() else 'plan'
        self.st['last_parts'] = runner.sig_parts(self.t, 'dev-claude', mode, self.d, self.st)
        self.st['last_sig'] = runner.topic_sig(self.t, 'dev-claude', mode, self.d, self.st)
        self.state = dict(sig_v=runner.SIG_V, topics={self.t['id']: self.st})

    def jobs(self, data=None):
        return runner.find_jobs(data or self.d, copy.deepcopy(self.state), only='dev-claude')

    def questions(self):
        q = runner.queue_summary('dev-claude', self.d, self.state)
        return build.consultation_decisions([self.t], [{'id': 'dev-claude', 'queue': q}], self.d)

    def test_no_repeat_and_stable_actionable_question(self):
        self.assertEqual(self.jobs(), [])
        q = self.questions()
        self.assertEqual(len(q), 1)
        self.assertEqual(q[0]['id'], self.questions()[0]['id'])
        self.assertIn('실행 권한', q[0]['question'])
        self.assertIn('결정할 것', q[0]['question'])
        self.assertEqual(len(q[0]['options']), 3)
        self.st['cont'] = 200
        self.t['notes'].append(dict(by='server-astra', body='다시 대기'))
        self.assertEqual(self.jobs(), [])

    def test_answer_routes_once_and_park_is_explicit(self):
        self.d['decisions_needed'] = self.questions()
        q = self.d['decisions_needed'][0]
        self.d['decisions_answered'] = [dict(id=q['id'], choice='원인 조사·해결안 제시')]
        self.assertEqual(self.jobs()[0]['kind'], 'answer')
        self.state['answers_used'] = [q['id']]
        self.assertEqual(self.jobs(), [])
        self.state['answers_used'] = []
        self.d['decisions_answered'][0]['choice'] = '보류'
        self.assertEqual(self.jobs()[0]['kind'], 'park')

    def test_new_user_comment_wakes_but_other_topics_continue(self):
        self.d['comments'] = [dict(target={'id': self.t['id']}, by='user', body='새 방향')]
        self.assertTrue(self.jobs()[0]['decision'])
        self.d['comments'] = []
        other = dict(self.t, id='T-20261004-abcdee')
        self.d['topics'].append(other)
        self.assertEqual([j['topic']['id'] for j in self.jobs()], [other['id']])

    def test_stale_queue_and_existing_question_do_not_duplicate(self):
        queue = runner.queue_summary('dev-claude', self.d, self.state)
        self.t['turn'] = 'server-astra'
        self.assertEqual(build.consultation_decisions([self.t], [{'id':'dev-claude','queue':queue}], self.d), [])
        self.t['turn'] = 'dev-claude'
        self.d['decisions_needed'] = [dict(id='existing', task_id=self.t['id'])]
        self.assertEqual(self.questions(), [])

    def test_finished_tests_return_to_lead_without_auto_pass(self):
        rows = testflow.plan(None, {'dev-claude'})
        t = dict(self.t, command_mode=True, stage='test', stage_owner='dev-claude', command={'tests': rows})
        self.assertEqual(topics.whose_turn(t), 'dev-claude')
        rows[0]['state'] = 'passed'
        self.assertEqual(topics.whose_turn(t), command.LEAD)
        for row in rows:
            row.update(state='passed', accepted_by=command.LEAD)
        self.assertEqual(topics.whose_turn(t), command.LEAD)
        self.assertEqual(runner.stage_doer(t), command.LEAD)
        self.assertEqual(t['status'], 'active')
        t.update(status='review_user')
        self.assertIsNone(topics.whose_turn(t))

    def test_lead_finish_and_legacy_finish_preserved(self):
        rows = testflow.plan(None, {'dev-claude'})
        for row in rows:
            row.update(state='passed', accepted_by=command.LEAD, updated_at='2026-10-04T10:00:00+09:00')
        t = dict(self.t, command_mode=True, command={'events': []})
        with patch.object(command, 'project', return_value={'tests': rows}):
            for who in (command.LEAD, 'dev-claude'):
                self.assertTrue(topics.finish_counts(who, 'test', False, t, {command.LEAD,'dev-claude'}, '2026-10-04T11:00:00+09:00'))
            rows[0]['accepted_by'] = None
            self.assertFalse(topics.finish_counts(command.LEAD, 'test', False, t, {command.LEAD,'dev-claude'}, '2026-10-04T11:00:00+09:00'))


if __name__ == '__main__':
    unittest.main()
