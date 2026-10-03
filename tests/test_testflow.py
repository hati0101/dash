import sys, unittest, tempfile, json
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import command, testflow, topics, runner, command_reset

class TestFlow(unittest.TestCase):
    def setUp(self):
        self.rows=testflow.plan(None,{'dev-claude','server-astra'})
    def event(self,op,tid='environment',who='dev-claude',**kw):
        return dict(op=op,task_id=tid,agent=who,body='명령·환경·관찰 결과·다음 조치',ts='2026-10-03T16:00:00+09:00',**kw)
    def test_no_pass_before_start_or_without_logs(self):
        with self.assertRaises(ValueError):testflow.transition(self.rows,self.event('test-pass'))
        rows=testflow.transition(self.rows,self.event('test-start'))
        with self.assertRaises(ValueError):testflow.transition(rows,self.event('test-pass'))
    def test_dependency_and_actor(self):
        for e in [self.event('test-start','build'),self.event('test-start',who='server-claude'),self.event('test-skip')]:
            with self.assertRaises(ValueError):testflow.transition(self.rows,e)
    def test_failure_retry_history_and_reset(self):
        rows=testflow.transition(self.rows,self.event('test-start'))
        rows=testflow.transition(rows,self.event('test-fail',evidence=[dict(path='log',sha256='a'*64)]))
        self.assertFalse(testflow.finished(rows));self.assertEqual(rows[0]['state'],'failed')
        rows=testflow.transition(rows,self.event('test-start'))
        rows=testflow.transition(rows,self.event('test-pass',evidence=[dict(path='log2',sha256='b'*64)]))
        self.assertEqual(rows[0]['attempt'],2);self.assertEqual(len(rows[0]['history']),4)
        self.assertEqual(testflow.current(rows)['id'],'environment')
        with self.assertRaises(ValueError):testflow.transition(rows,self.event('test-accept'))
        rows=testflow.transition(rows,self.event('test-accept',who='server-astra'))
        self.assertEqual(testflow.current(rows)['id'],'static')
        rows=testflow.transition(rows,self.event('test-reset',who='server-astra'))
        self.assertEqual(rows[0]['state'],'pending');self.assertEqual(len(rows[0]['history']),6);self.assertEqual(rows[0]['attempt'],0)
    def test_blocked_goes_to_commander_then_resume(self):
        rows=testflow.transition(self.rows,self.event('test-start'))
        rows=testflow.transition(rows,self.event('test-blocked'))
        topic=dict(status='active',stage='test',command_mode=True,command=dict(tests=rows))
        self.assertEqual(topics.whose_turn(topic),'server-astra')
        rows=testflow.transition(rows,self.event('test-release',who='server-astra'))
        self.assertEqual(rows[0]['state'],'pending')
    def test_skip_is_not_pass_and_has_reason(self):
        rows=testflow.transition(self.rows,self.event('test-skip',who='server-astra'))
        self.assertEqual(rows[0]['state'],'skipped');self.assertTrue(rows[0]['summary'])
    def test_saved_topic_requires_activation(self):
        raw=topics.clean_topic(dict(id='T-20261003-abc123',title='나중에',backlog=True))
        self.assertTrue(raw['backlog'])
        self.assertIsNone(topics.whose_turn(dict(status='backlog',command_mode=True)))
    def test_transition_drain_prevents_old_runner_start(self):
        self.assertEqual(runner.find_jobs(dict(meta=dict(command_version=1,command_epoch=None)),{}),[])
    def test_test_progress_changes_runner_signal(self):
        t=dict(id='T-20261003-abc123',status='active',stage='test',command_mode=True,command=dict(revision=1))
        a=runner.topic_sig(t,'dev-claude','impl',{},{});t['command']['revision']=2
        self.assertNotEqual(a,runner.topic_sig(t,'dev-claude','impl',{},{}))
    def test_progress_only_does_not_reset_idle_signal(self):
        t=dict(id='T-20261003-abc123',status='active',stage='test',command_mode=True,command=dict(revision=3,events=[dict(op='test-start',revision=1),dict(op='test-progress',revision=2)]))
        a=runner.topic_sig(t,'dev-claude','impl',{}, {})
        t['command']['revision']=4;t['command']['events'].append(dict(op='test-progress',revision=3))
        self.assertEqual(a,runner.topic_sig(t,'dev-claude','impl',{},{}))
    def test_prior_choices_are_context_not_new_approval(self):
        parent=dict(id='root',title='원래 조사',body='최초 목표',gate_history=[dict(choice='후속 구현',note='주간만 진행')])
        child=dict(id='next',title='후속 구현',origin_topic='root',status='new')
        topics.attach_context([parent,child])
        self.assertEqual(child['prior_context'][0]['decisions'][0]['note'],'주간만 진행')
        self.assertEqual(child['status'],'new');self.assertNotIn('gate_history',child)
        parent['origin_topic']='next';topics.attach_context([parent,child])
        self.assertLessEqual(len(child['prior_context']),2)
    def test_three_failed_attempts_escalate(self):
        rows=self.rows
        for i in range(3):
            rows=testflow.transition(rows,self.event('test-start'))
            rows=testflow.transition(rows,self.event('test-fail',evidence=[dict(path='log',sha256='a'*64)]))
        self.assertEqual(rows[0]['state'],'blocked')
        with self.assertRaises(ValueError):testflow.transition(rows,self.event('test-release',who='server-astra'))
        with self.assertRaises(ValueError):testflow.transition(rows,self.event('test-replan',method='새 환경에서 실패 경로 확인'))
        revised=testflow.transition(rows,self.event('test-replan',who='server-astra',method='새 환경에서 실패 경로 확인'))
        self.assertEqual(revised[0]['attempt'],0)
        self.assertEqual(revised[0]['history'][-1]['previous_attempt'],3)
        self.assertEqual(testflow.transition(revised,self.event('test-start'))[0]['state'],'running')
    def test_unrelated_running_does_not_block_migration(self):
        nodes=[dict(pc='fixture',agents={a:{'command_version':1} for a in ['server-astra','dev-claude']},runs=[])]
        self.assertFalse(command_reset.pending(nodes))
        nodes[0]['runs']=[dict(result='running',agent='dev-claude',topic='old')]
        self.assertFalse(command_reset.pending(nodes))
        nodes[0]['runs']=[];nodes[0]['agents']['dev-claude']['command_version']=0
        self.assertTrue(command_reset.pending(nodes))

if __name__=='__main__':unittest.main(verbosity=2)
