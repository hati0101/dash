"""REVIEW-5 후속(r5) 시험: I-1 amend 계약·거부·즉시 깨움, I-2 시계 어긋남·보류 재개·연속 답, 옛 기록 이관, 검수 위임.
실제 처리 경로(command.apply_action → 노드 기록 → merged_topics → runner 판정)로 재현한다. 운영/원격/AI 호출 없음."""
import json, sys, tempfile, unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import command, topics, node, runner

KST = timezone(timedelta(hours=9))
KNOWN = {'server-astra', 'dev-claude', 'dev-astra', 'server-claude'}
DONE_BODY = '핵심: 완료 근거 확인 / 정할 것: 결과 확인 / 권장: 다음 단계로 진행'


class Base(unittest.TestCase):
    research = False
    browser = 0      # 브라우저 시계 어긋남(분)
    lead_clock = 0   # 서버컴(사령탑) 시계 어긋남(분)
    dev_clock = 0    # 개발컴 시계 어긋남(분)
    hub_rx = True    # 허브 수신 시각 기록(r5 새 기록). False면 옛 기록 형식

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.tid, self.wid = 'T-20261003-abc123', 'FT-20261003-abc123'
        self.cfg = {'pc': {'id': 'fixture', 'role': 'hub'}, 'topics_dir': str(self.root / 'topics'), 'data_dir': str(self.root / 'data'),
                    'node_data_dir': str(self.root / 'nodes'), 'bridge_dir': str(self.root / 'bridge'),
                    'agents': [{'id': a, 'ai': 'gpt' if 'astra' in a else 'claude'} for a in KNOWN]}
        self.base = datetime(2026, 10, 3, 12, tzinfo=KST)
        self.task = dict(id='code', title='목표 조사', scope='근거 조사', done_when='근거 확인', assignee='dev-claude', depends_on=[])
        for who in ('dev-claude', 'server-claude'):
            p = self.root / f'work/{self.wid}/{who}/result.md'; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(f'{who} evidence', encoding='utf-8')
        self.tp = self.root / 'topics' / self.tid / 'topic.json'
        topics.write_json(self.tp, dict(id=self.tid, title='시험', kind='조사·분석' if self.research else '기능·개선', command_mode=True))
        topics.write_json(self.tp.parent / 'claude.json', dict(assignee='server-astra', assigned_at=self.ts(0)))
        self.user = {'decisions_answered': [], 'topic_resume': []}
        runner.CFG = self.cfg
        self.wp = patch.object(runner, 'WORK_PY', self.root / 'work.py'); self.wp.start()

    def tearDown(self):
        self.wp.stop(); self.tmp.cleanup()

    def ts(self, n): return (self.base + timedelta(minutes=n)).isoformat()
    def clock(self, who): return self.lead_clock if who == 'server-astra' else self.dev_clock
    def view(self): return topics.merged_topics(self.root / 'topics', self.cfg, node.load_records(self.cfg)['topic_records'], KNOWN)[0]

    def cmd(self, n, op, who='server-astra', file='code', body='원인과 근거 확인', **kw):
        with patch.object(node, 'now_iso', return_value=self.ts(n + self.clock(who))):
            return command.apply_action({'topic': self.view(), 'agent': who, 'work_id': self.wid}, dict(cmd=op, file=file, body=body, **kw),
                                        self.cfg, KNOWN, set(), self.root)

    def evidence(self, who): return [f'work/{self.wid}/{who}/result.md']

    def submit(self, n, file='code'):
        self.cmd(n, 'submit', 'dev-claude', file, options=self.evidence('dev-claude')); self.cmd(n + .1, 'accept', file=file)

    def done(self, n, who):
        with patch.object(node, 'now_iso', return_value=self.ts(n + self.clock(who))):
            node.add_topic_record(self.cfg, self.tid, who, 'status', status='done', body=DONE_BODY, command_revision=self.view()['command']['revision'])

    def _rec(self, n, **kw):
        r = dict(ts=self.ts(n + self.browser), **kw)
        if self.hub_rx: r['rx'] = self.ts(n + .05)  # 허브가 받은 시각(동기화 지연 몇 초)
        return r

    def answer(self, gate, choice, n, note='더 확인해 주세요'):
        self.user['decisions_answered'].append(self._rec(n, id=gate['id'], choice=choice, note=note))
        topics.write_json(self.root / 'data/user.json', self.user)

    def resume(self, n):
        self.user['topic_resume'].append(self._rec(n, topic=self.tid, note='다시 진행'))
        topics.write_json(self.root / 'data/user.json', self.user)

    def run_checks(self, n):
        for i, item in enumerate(self.view()['command']['tests']):
            m = n + i * .01
            self.cmd(m, 'test-start', 'dev-claude', item['id'])
            self.cmd(m + .001, 'test-pass', 'dev-claude', item['id'], options=self.evidence('dev-claude'))
            self.cmd(m + .002, 'test-accept', file=item['id'])

    def runner_done(self, who='server-astra'):
        t = self.view()
        with patch.object(node, 'now_iso', return_value=self.ts(50 + self.clock(who))):
            return runner.apply({'agent': who, 'topic': t, 'work_id': self.wid}, {'actions': [{'type': 'state', 'status': 'done', 'task': self.tid, 'body': DONE_BODY}]},
                                {'agents': [{'id': a} for a in KNOWN]})

    def to_impl_gate4(self):
        self.cmd(0, 'plan', body=json.dumps({'tasks': [self.task]})); self.submit(1); self.done(2, 'server-astra')
        self.assertEqual(self.view()['stage'], 'test')
        self.run_checks(20); self.done(22, 'dev-claude')
        g = self.view()['gate']; self.assertEqual(g['n'], 4)
        return g

    def retest_to_gate4(self, n, prev_ids):
        t = self.view()
        self.assertTrue(t['test_reset_needed']); self.assertEqual(t['turn'], 'server-astra'); self.assertEqual(runner.stage_doer(t), 'server-astra')
        self.cmd(n, 'test-reset')
        t = self.view(); self.assertFalse(t['test_reset_needed']); self.assertEqual(t['turn'], 'dev-claude')
        self.run_checks(n + 20); self.done(n + 22, 'dev-claude')
        g = self.view()['gate']
        self.assertIsNotNone(g, '재시험 끝냄이 버려져 ★4가 다시 열리지 않음')
        self.assertEqual(g['n'], 4); self.assertNotIn(g['id'], prev_ids)
        return g


# ---------------------------------------------------------------- I-1
class ResearchReturn(Base):
    research = True

    def to_gate40(self):
        self.cmd(0, 'plan', body=json.dumps({'tasks': [self.task]})); self.submit(1); self.done(2, 'server-astra')
        g = self.view()['gate']; self.assertEqual(g['n'], 40); return g

    def test_prompt_states_amend_contract_and_pending_return(self):
        g = self.to_gate40(); self.answer(g, '', 3)
        text = command.prompt(self.view(), 'server-astra')
        self.assertIn('cmd=amend', text); self.assertIn('되돌아온 관문 — 처리 필요', text); self.assertIn(g['id'], text)
        self.assertIn('더 확인해 주세요', text)

    def test_done_without_amend_is_rejected_with_reason(self):
        g = self.to_gate40(); self.answer(g, '', 3)
        done, failed = self.runner_done()
        self.assertFalse(done); self.assertTrue(failed); self.assertIn('amend', failed[0]); self.assertIn(g['id'], failed[0])
        self.assertFalse(any(r.get('status') == 'done' and r['ts'] > self.ts(10) for r in node.load_records(self.cfg)['topic_records']))
        # amend → 추가 작업 수락 뒤에는 끝냄을 받는다
        self.cmd(4, 'amend', body=json.dumps({'tasks': [self.task, dict(self.task, id='more', title='추가 조사', depends_on=['code'])]}))
        self.assertIsNone(command.pending_return(self.view()))
        self.submit(5, 'more')
        done, failed = self.runner_done(); self.assertFalse(failed); self.assertIn('state', done)
        g2 = self.view()['gate']; self.assertEqual(g2['n'], 40); self.assertNotEqual(g2['id'], g['id'])

    def test_answer_wakes_commander_immediately(self):
        g = self.to_gate40()
        t = self.view(); self.assertIsNone(t['turn'])
        self.answer(g, '', 3)
        t = self.view(); self.assertEqual(t['turn'], 'server-astra')
        st = {}
        parts = runner.sig_parts(t, 'server-astra', 'impl', {}, st)
        self.assertIn('return-' + g['id'], parts['stage'])
        last = dict(parts, stage=parts['stage'].split('-return-')[0])  # 답 전 마지막 처리 신호(같은 revision)
        self.assertNotEqual(parts['stage'], last['stage'])
        self.assertIn('command-', runner.wake_reason(parts, last))
        # amend로 처리하면 표시가 사라진다(다시 깨우지 않음)
        self.cmd(4, 'amend', body=json.dumps({'tasks': [self.task, dict(self.task, id='more', title='추가 조사', depends_on=['code'])]}))
        self.assertNotIn('return-', runner.sig_parts(self.view(), 'server-astra', 'impl', {}, st)['stage'])

    def test_worker_does_not_get_return_marker(self):
        g = self.to_gate40(); self.answer(g, '', 3)
        self.assertNotIn('return-', runner.sig_parts(self.view(), 'dev-claude', 'impl', {}, {})['stage'])


# ---------------------------------------------------------------- I-2 조합
def research_park_resume_memo(self):
    """★40 보류 → 다시 진행 → 메모 → amend → 추가 작업 → 끝냄 → 새 ★40."""
    self.cmd(0, 'plan', body=json.dumps({'tasks': [self.task]})); self.submit(1); self.done(2, 'server-astra')
    g = self.view()['gate']; self.assertEqual(g['n'], 40)
    self.answer(g, '보류', 2.5)
    self.assertEqual(self.view()['status'], 'parked')
    self.resume(3)
    g2 = self.view()['gate']; self.assertIsNotNone(g2, '다시 진행했는데 관문이 다시 열리지 않음'); self.assertEqual(g2['n'], 40)
    self.answer(g2, '', 3.5)
    t = self.view(); self.assertEqual(t['stage'], 'work'); self.assertEqual(t['turn'], 'server-astra'); self.assertIsNone(t.get('gate'))
    self.cmd(4, 'amend', body=json.dumps({'tasks': [self.task, dict(self.task, id='more', title='추가 조사', depends_on=['code'])]}))
    self.submit(5, 'more'); self.done(6, 'server-astra')
    g3 = self.view()['gate']
    self.assertIsNotNone(g3, '추가 조사 끝냄이 무시됨'); self.assertEqual(g3['n'], 40); self.assertNotIn(g3['id'], (g['id'], g2['id']))


def impl_park_resume_reject(self):
    """★4 보류 → 다시 진행 → 반려 → test-reset → 재시험 → 새 ★4."""
    g = self.to_impl_gate4()
    self.answer(g, '보류', 22.5)
    self.resume(23)
    g2 = self.view()['gate']; self.assertIsNotNone(g2, '다시 진행했는데 ★4가 다시 열리지 않음'); self.assertEqual(g2['n'], 4)
    self.answer(g2, '문제 있음', 23.5)
    self.retest_to_gate4(24, (g['id'], g2['id']))


def impl_pass_then_fix(self):
    """★4 통과 → ★5 수정(연속 답) → test-reset → 재시험 → 새 ★4."""
    g = self.to_impl_gate4()
    self.answer(g, '통과', 22.5)
    g5 = self.view()['gate']; self.assertEqual(g5['n'], 5)
    self.answer(g5, '수정', 22.6)
    self.retest_to_gate4(24, (g['id'],))


def impl_reject_twice(self):
    """★4 반려 → 재시험 → ★4 반려 → 재시험 → ★4(같은 관문 재사용 없음)."""
    g = self.to_impl_gate4()
    self.answer(g, '문제 있음', 22.5)
    g2 = self.retest_to_gate4(24, (g['id'],))
    self.answer(g2, '문제 있음', 46.5)
    self.retest_to_gate4(48, (g['id'], g2['id']))


SCENARIOS = {'research_park_resume_memo': (research_park_resume_memo, True), 'impl_park_resume_reject': (impl_park_resume_reject, False),
             'impl_pass_then_fix': (impl_pass_then_fix, False), 'impl_reject_twice': (impl_reject_twice, False)}
for name, (fn, research) in SCENARIOS.items():
    for b in (-10, -3, 0, 3, 10):
        for lead, dev in ((0, 0), (0, 5), (0, -5)):
            for rx in (True, False):
                if not rx and b > 0:
                    continue  # 허브 수신 시각이 없는 옛 기록 + 빠른 브라우저는 아래 P3 시험에서 따로 확인
                cls = type(f'Clock_{name}_b{b}_l{lead}_d{dev}_{"rx" if rx else "old"}'.replace('-', 'm'), (Base,),
                           dict(research=research, browser=b, lead_clock=lead, dev_clock=dev, hub_rx=rx, test_scenario=fn))
                globals()[cls.__name__] = cls


# ---------------------------------------------------------------- P3 · 이관
class FastBrowserPack(Base):
    browser = 10

    def test_pack_finish_after_fast_answer_is_kept(self):
        g = self.to_impl_gate4()
        self.answer(g, '통과', 22.5); g5 = self.view()['gate']
        self.answer(g5, '배포본 만들기', 23)
        self.assertEqual(self.view()['stage'], 'pack')
        self.done(24, 'dev-claude')  # 실제로는 답 1분 뒤(브라우저 시각보다 9분 이름)
        g7 = self.view()['gate']
        self.assertIsNotNone(g7, '빠른 브라우저 답 때문에 배포본 끝냄이 버려짐'); self.assertEqual(g7['n'], 7)


class LegacyResetMigration(Base):
    def test_r3_reset_without_gate_id_keeps_open_gate4(self):
        """r3 게시본이 남긴 review_gate_id 없는 test-reset(반려 답 뒤)은 r3 판정대로 인정 → 열린 ★4가 사라지지 않는다."""
        g = self.to_impl_gate4()
        self.answer(g, '문제 있음', 22.5)
        rev = self.view()['command']['revision']
        with patch.object(node, 'now_iso', return_value=self.ts(24)):
            node.add_topic_record(self.cfg, self.tid, 'server-astra', 'command', event_id='legacyreset0001', revision=rev, op='test-reset',
                                  task_id=None, body='재시험 초기화(r3)', to=None)
        t = self.view(); self.assertFalse(t['test_reset_needed']); self.assertEqual(t['turn'], 'dev-claude')
        self.run_checks(44)
        with patch.object(node, 'now_iso', return_value=self.ts(46)):  # r3 끝냄: command_revision 없음
            node.add_topic_record(self.cfg, self.tid, 'dev-claude', 'status', status='done', body=DONE_BODY)
        g2 = self.view()['gate']; self.assertIsNotNone(g2); self.assertEqual(g2['n'], 4); self.assertNotEqual(g2['id'], g['id'])

    def test_r3_reset_before_answer_does_not_count(self):
        g = self.to_impl_gate4()
        rev = self.view()['command']['revision']
        with patch.object(node, 'now_iso', return_value=self.ts(22.2)):
            node.add_topic_record(self.cfg, self.tid, 'server-astra', 'command', event_id='legacyreset0002', revision=rev, op='test-reset',
                                  task_id=None, body='반려 전 초기화', to=None)
        self.answer(g, '문제 있음', 22.5)
        self.assertTrue(self.view()['test_reset_needed'])


class SameSyncParkResume(Base):
    def test_park_and_resume_received_in_same_second(self):
        """보류와 다시 진행을 1분 안에 눌러 허브가 같은 동기화(같은 초)에 받아도 다시 진행이 적용된다."""
        g = self.to_impl_gate4()
        self.user['decisions_answered'].append(dict(id=g['id'], choice='보류', note='', ts=self.ts(22.5), rx=self.ts(23)))
        self.user['topic_resume'].append(dict(topic=self.tid, note='', ts=self.ts(22.7), rx=self.ts(23)))
        topics.write_json(self.root / 'data/user.json', self.user)
        g2 = self.view()['gate']; self.assertEqual(g2['n'], 4); self.assertNotEqual(g2['id'], g['id'])

    def test_resume_before_park_in_same_second_is_not_used(self):
        g = self.to_impl_gate4()
        self.user['topic_resume'].append(dict(topic=self.tid, note='', ts=self.ts(22.4), rx=self.ts(23)))
        self.user['decisions_answered'].append(dict(id=g['id'], choice='보류', note='', ts=self.ts(22.5), rx=self.ts(23)))
        topics.write_json(self.root / 'data/user.json', self.user)
        self.assertEqual(self.view()['status'], 'parked')


class IndependentReviewFollowups(Base):
    """독립 검토(r5 1차) 지적 재현을 회귀로 고정."""
    def test_reset_before_gate4_does_not_satisfy_later_reject(self):
        self.browser = -10
        self.cmd(0, 'plan', body=json.dumps({'tasks': [self.task]})); self.submit(1); self.done(2, 'server-astra')
        self.cmd(15, 'test-reset')  # ★4 전 초기화: 되돌아온 관문 없음 → '-'
        self.assertEqual([e for e in self.view()['command']['events'] if e['op'] == 'test-reset'][-1]['review_gate_id'], '-')
        self.run_checks(16); self.done(22, 'dev-claude')
        g = self.view()['gate']; self.answer(g, '문제 있음', 22.5)
        self.assertTrue(self.view()['test_reset_needed'])
        self.done(24, 'dev-claude')  # 재시험 없이 끝냄
        self.assertIsNone(self.view().get('gate'))

    def test_status_at_after_reject_is_not_overwritten_by_node_record(self):
        g = self.to_impl_gate4()
        self.done(22.3, 'dev-claude')  # ★4 대기 중 대화 세션의 끝냄(중복)
        self.answer(g, '문제 있음', 22.5)
        self.cmd(24, 'test-reset')
        t = self.view(); self.assertEqual(t['turn'], 'dev-claude')
        data = {'topics': [t], 'meta': {'generated_at': self.ts(25)}, 'agents': [{'id': a} for a in KNOWN]}
        with patch.object(node, 'my_agents', return_value={'dev-claude': {}, 'dev-astra': {}}):
            runner.overlay_local(data, node.load_records(self.cfg))
        self.assertEqual((data['topics'][0]['status'], data['topics'][0]['turn']), ('active', 'dev-claude'))

    def test_locked_reviewer_rejected(self):
        with patch.object(node, 'now_iso', return_value=self.ts(0)), self.assertRaises(ValueError):
            command.apply_action({'topic': self.view(), 'agent': 'server-astra', 'work_id': self.wid},
                                 dict(cmd='plan', file=None, body=json.dumps({'tasks': [dict(self.task, reviewer='server-claude')]})),
                                 self.cfg, KNOWN, {'server-claude'}, self.root)

    def test_deputy_cannot_accept_what_it_reviewed(self):
        state = command.initial()
        state['tasks'] = [dict(self.task, state='review', attempt=1, feedback='', reviewer='dev-claude',
                               result={'by': 'dev-astra', 'summary': 's', 'evidence': []}, review={'by': 'dev-claude', 'verdict': 'pass'})]
        seen, observed = self.ts(-200), self.ts(0)
        ev = {'event_id': 'x1', 'revision': 0, 'agent': 'dev-claude', 'op': 'accept', 'task_id': 'code', 'body': '대행 수락', 'ts': self.ts(0.1),
              'delegation': {'leader': 'server-astra', 'deputy': 'dev-claude', 'observed_at': observed, 'last_seen': seen, 'locked': False}}
        state['tasks'][0]['assignee'] = 'dev-astra'
        self.assertTrue(command.delegated(ev))
        with self.assertRaises(ValueError):
            command.transition(state, ev, KNOWN)


class ResearchNoopAmend(Base):
    research = True

    def test_amend_without_new_or_changed_task_is_not_handled(self):
        self.cmd(0, 'plan', body=json.dumps({'tasks': [self.task]})); self.submit(1); self.done(2, 'server-astra')
        g = self.view()['gate']; self.answer(g, '', 3)
        self.cmd(4, 'amend', body=json.dumps({'tasks': [self.task]}))  # 작업표 그대로
        self.assertIsNotNone(command.pending_return(self.view()))
        done, failed = self.runner_done(); self.assertTrue(failed)
        self.done(5, 'server-astra'); self.assertIsNone(self.view().get('gate'))
        self.cmd(6, 'amend', body=json.dumps({'tasks': [dict(self.task, scope='근거 조사 + 아키텍트 메모 반영')]}))  # 기존 작업 내용 변경
        self.assertIsNone(command.pending_return(self.view()))


# ---------------------------------------------------------------- 독립 검토 2차 재현(검토자 작성 시험을 회귀로 고정)
class Review2Research(Base):
    research = True
    def to40(self):
        self.cmd(0, 'plan', body=json.dumps({'tasks': [self.task]})); self.submit(1); self.done(2, 'server-astra')
        g = self.view()['gate']; self.answer(g, '', 3); return g


class P_HandledRawCompare(Review2Research):
    """작업표 그대로인데 원문 표기만 다른 amend(제목 앞뒤 공백, depends_on 생략)가 처리로 인정되는가."""
    def test_whitespace_title(self):
        self.to40()
        self.cmd(4, 'amend', body=json.dumps({'tasks': [dict(self.task, title=' ' + self.task['title'] + ' ')]}))
        task = self.view()['command']['tasks'][0]
        self.assertEqual(task['state'], 'accepted')  # 실행기 상태로는 그대로(재작업 없음)
        self.assertIsNotNone(command.pending_return(self.view()), '공백만 바꾼 amend가 보완 처리로 인정됨')

    def test_omit_depends_on(self):
        self.to40()
        t = dict(self.task); t.pop('depends_on')
        self.cmd(4, 'amend', body=json.dumps({'tasks': [t]}))
        self.assertEqual(self.view()['command']['tasks'][0]['state'], 'accepted')
        self.assertIsNotNone(command.pending_return(self.view()), 'depends_on만 생략한 amend가 보완 처리로 인정됨')


class Q_AddThenCancel(Review2Research):
    """새 작업을 더한 뒤 바로 취소하면 추가 조사 없이 끝냄이 통과하는가(사령탑만 가능한 경로)."""
    def test(self):
        g = self.to40()
        self.cmd(4, 'amend', body=json.dumps({'tasks': [self.task, dict(self.task, id='more', title='추가 조사', depends_on=['code'])]}))
        self.cmd(4.1, 'cancel', file='more', body='불필요')
        done, failed = self.runner_done()
        g2 = self.view().get('gate')
        self.assertIsNone(g2, f'추가 조사 없이 새 ★40이 열림: failed={failed}')


class R_ParkRecordInGateWindow(Base):
    """★4가 열린 동안 남은 '[아키텍트 보류 결정]' 보류 기록이 반려 뒤 주제를 보류로 만드는가(보류 분기는 status_at이 아니라 since 비교)."""
    def test(self):
        g = self.to_impl_gate4()
        with patch.object(node, 'now_iso', return_value=self.ts(22.3)):
            node.add_topic_record(self.cfg, self.tid, 'dev-claude', 'status', status='parked', body='[아키텍트 보류 결정] 다른 질문 답')
        self.answer(g, '문제 있음', 22.5)
        t = self.view()
        self.assertEqual(t['status'], 'active', f"반려 뒤 상태 {t['status']} (status_at {t['status_at']})")



# ---------------------------------------------------------------- 검수 위임(REVIEW-DELEGATION)
class ReviewDelegation(Base):
    def plan(self, **task):
        self.cmd(0, 'plan', body=json.dumps({'tasks': [dict(self.task, **task)]}))

    def test_reviewer_reports_then_commander_accepts(self):
        self.plan(reviewer='server-claude')
        self.cmd(1, 'submit', 'dev-claude', options=self.evidence('dev-claude'))
        t = self.view(); self.assertEqual(t['turn'], 'server-claude')
        with self.assertRaises(ValueError):
            self.cmd(1.1, 'review-report', 'server-claude', status='maybe', options=self.evidence('server-claude'))
        self.cmd(1.2, 'review-report', 'server-claude', status='pass', body='근거 2건 대조, 문제 없음', options=self.evidence('server-claude'))
        t = self.view(); self.assertEqual(t['turn'], 'server-astra')
        rv = t['command']['tasks'][0]['review']; self.assertEqual((rv['by'], rv['verdict']), ('server-claude', 'pass')); self.assertEqual(len(rv['evidence'][0]['sha256']), 64)
        self.assertIn('review-report', command.prompt(t, 'server-claude'))
        self.cmd(1.3, 'accept', body='검수 보고 확인')
        self.assertEqual(self.view()['command']['tasks'][0]['state'], 'accepted')

    def test_accept_rechecks_review_evidence(self):
        """검수 보고 근거가 보고 뒤 바뀌거나 지워지면 사령탑 수락을 거부한다(r5 읽기 검토 P2). 그대로면 수락."""
        rv_file = self.root / f'work/{self.wid}/server-claude/result.md'
        for change in ('modify', 'delete', 'keep'):
            with self.subTest(change=change):
                self.tearDown(); self.setUp()
                rv_file = self.root / f'work/{self.wid}/server-claude/result.md'
                self.plan(reviewer='server-claude')
                self.cmd(1, 'submit', 'dev-claude', options=self.evidence('dev-claude'))
                self.cmd(1.1, 'review-report', 'server-claude', status='pass', body='근거 대조', options=self.evidence('server-claude'))
                if change == 'modify':
                    rv_file.write_text('바뀐 검수 기록', encoding='utf-8')
                elif change == 'delete':
                    rv_file.unlink()
                if change == 'keep':
                    self.cmd(1.2, 'accept', body='검수 보고 확인')
                    self.assertEqual(self.view()['command']['tasks'][0]['state'], 'accepted')
                else:
                    with self.assertRaises((ValueError, OSError)):
                        self.cmd(1.2, 'accept', body='검수 보고 확인')
                    self.assertEqual(self.view()['command']['tasks'][0]['state'], 'review')

    def test_self_review_and_wrong_reporter_rejected(self):
        with self.assertRaises(ValueError): self.plan(reviewer='dev-claude')
        with self.assertRaises(ValueError): self.plan(reviewer='server-astra')
        self.plan()
        self.cmd(1, 'submit', 'dev-claude', options=self.evidence('dev-claude'))
        with self.assertRaises(ValueError): self.cmd(1.1, 'review-assign', to='dev-claude', body='자기 검수')
        with self.assertRaises(ValueError): self.cmd(1.1, 'review-report', 'server-claude', status='pass', options=self.evidence('server-claude'))
        self.cmd(1.2, 'review-assign', to='server-claude', body='검수 위임')
        self.assertEqual(self.view()['turn'], 'server-claude')
        with self.assertRaises(ValueError): self.cmd(1.3, 'review-report', 'dev-astra', status='pass', options=self.evidence('server-claude'))
        with self.assertRaises(ValueError): self.cmd(1.3, 'accept', 'server-claude', body='검수 담당의 수락')

    def test_revise_clears_report_and_resubmission_needs_new_review(self):
        self.plan(reviewer='server-claude')
        self.cmd(1, 'submit', 'dev-claude', options=self.evidence('dev-claude'))
        self.cmd(1.1, 'review-report', 'server-claude', status='fail', body='근거 누락', options=self.evidence('server-claude'))
        self.cmd(1.2, 'revise', body='검수 지적 반영')
        task = self.view()['command']['tasks'][0]; self.assertNotIn('review', task); self.assertEqual(task['state'], 'ready')
        self.cmd(2, 'submit', 'dev-claude', options=self.evidence('dev-claude'))
        self.assertEqual(self.view()['turn'], 'server-claude')

    def test_reassign_to_reviewer_drops_reviewer(self):
        self.plan(reviewer='server-claude')
        self.cmd(1, 'reassign', to='server-claude', body='담당 변경')
        task = self.view()['command']['tasks'][0]; self.assertEqual(task['assignee'], 'server-claude'); self.assertNotIn('reviewer', task)

    def test_amend_reviewer_change_keeps_result(self):
        self.plan(reviewer='server-claude')
        self.cmd(1, 'submit', 'dev-claude', options=self.evidence('dev-claude'))
        self.cmd(1.1, 'review-report', 'server-claude', status='pass', body='확인', options=self.evidence('server-claude'))
        self.cmd(1.2, 'amend', body=json.dumps({'tasks': [dict(self.task, reviewer='dev-astra')]}))
        task = self.view()['command']['tasks'][0]
        self.assertEqual(task['state'], 'review'); self.assertEqual(task['reviewer'], 'dev-astra'); self.assertNotIn('review', task)
        self.assertEqual(self.view()['turn'], 'dev-astra')


if __name__ == '__main__':
    unittest.main()
