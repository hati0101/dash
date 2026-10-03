"""r8 시험: 진행 중 주제 범위 조정(rescope) — 크기 지정·미착수 작업 취소·대기 시험 제외를 한 번에(서버컴 13b5928). 바뀐 동작만."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import command
from test_review5 import Base


class Rescope(Base):
    def plan3(self, size=None):
        tasks = [self.task, dict(self.task, id='review', title='교차 검토', assignee='dev-astra', depends_on=['code']),
                 dict(self.task, id='extra', title='추가 회귀', depends_on=['code'])]
        self.cmd(0, 'plan', body=json.dumps({'tasks': tasks, **({'size': size} if size else {})}))

    def rescope(self, n, **spec):
        return self.cmd(n, 'rescope', file=None, body=json.dumps({'reason': '작은 화면 수정 — 중복 검토·회귀 제외', **spec}))

    def test_one_command_trims_and_small_goes_to_gate4(self):
        self.plan3()
        self.submit(1)
        tests = [x['id'] for x in self.view()['command']['tests']]
        self.rescope(2, size='small', cancel=['review', 'extra'], skip=tests)
        c = self.view()['command']
        self.assertEqual(c['size'], 'small')
        self.assertEqual({t['id']: t['state'] for t in c['tasks']}, {'code': 'accepted', 'review': 'cancelled', 'extra': 'cancelled'})
        self.assertTrue(all(x['state'] == 'skipped' for x in c['tests']))
        self.assertEqual(sum(1 for e in c['events'] if e['op'] == 'rescope'), 1, '명령 한 번')
        self.done(3, 'server-astra')
        self.assertEqual(self.view()['gate']['n'], 4, '작은 일: 시험 단계 없이 ★4')

    def test_guards(self):
        self.plan3('risk')
        self.submit(1)
        bad = [dict(cancel=['code']),                 # 수락된 작업
               dict(cancel=['nope']),                 # 없는 ID
               dict(size='small'),                    # risk는 낮추지 않음
               dict(size='huge')]
        for spec in bad:
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                self.rescope(2, **spec)
        with self.assertRaises(ValueError):
            self.cmd(2, 'rescope', 'dev-claude', file=None, body=json.dumps({'reason': '작업자 시도', 'cancel': ['extra']}))
        with self.assertRaises(ValueError):
            self.cmd(2, 'rescope', file=None, body=json.dumps({'cancel': ['extra']}))  # 이유 없음

    def test_small_needs_at_most_two_open_tasks(self):
        self.plan3()
        with self.assertRaises(ValueError):
            self.rescope(1, size='small')  # 남은 작업 3개
        self.rescope(1, size='small', cancel=['extra'])
        self.assertEqual(self.view()['command']['size'], 'small')

    def test_in_test_stage_skips_pending_and_finishes(self):
        self.cmd(0, 'plan', body=json.dumps({'tasks': [self.task]}))
        self.submit(1); self.done(2, 'server-astra')
        t = self.view(); self.assertEqual(t['stage'], 'test')
        first = t['command']['tests'][0]['id']
        self.cmd(3, 'test-start', 'dev-claude', first)
        with self.assertRaises(ValueError):
            self.rescope(4, skip=[first])  # 진행 중 시험은 제외 못 함
        rest = [x['id'] for x in t['command']['tests'][1:]]
        self.rescope(4, skip=rest)
        self.cmd(5, 'test-pass', 'dev-claude', first, options=self.evidence('dev-claude'))
        self.cmd(5.1, 'test-accept', file=first)
        self.done(6, 'dev-claude')
        self.assertEqual(self.view()['gate']['n'], 4, '남은 시험을 제외한 뒤 바로 ★4')
        self.assertIn('rescope', command.prompt({'command_mode': True, 'command': command.initial()}, 'server-astra'))


if __name__ == '__main__':
    unittest.main()
