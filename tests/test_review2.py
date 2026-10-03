import copy, hashlib, json, os, sys, tempfile, unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import command, command_reset, runner, topics, testflow, release_queue

class Review2(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.now=datetime.now(timezone.utc)
        self.data={'meta':{'generated_at':self.now.isoformat()},'agents':[
            {'id':'server-astra','pc_synced':(self.now-timedelta(hours=3)).isoformat()},
            {'id':'dev-claude','pc_synced':self.now.isoformat()}]}
    def tearDown(self): self.tmp.cleanup()
    def test_alarm_even_without_deputy_node_or_signal(self):
        ts=[dict(id=str(i),command_mode=True,status='active',turn='server-astra') for i in range(31)]
        for data in ({'agents':[]},dict(self.data,agent_locks={'dev-claude':{'mode':'all'}}),
                     {'agents':[{'id':'server-astra','error':'decrypt failed'}]}):
            alerts=command.availability_actions(data,ts,self.now)
            self.assertEqual(len(alerts),1); self.assertIn('사령탑·대행 모두 불가',alerts[0]['title'])
            self.assertEqual(len(alerts[0]['topics']),31)
    def test_worker_offline_or_stopped_alert_aggregates(self):
        ts=[dict(id=str(i),command_mode=True,status='active',turn='dev-astra') for i in range(3)]
        data=copy.deepcopy(self.data);data['agents'][0]['pc_synced']=self.now.isoformat()
        for extra in ({'id':'dev-astra'}, {'id':'dev-astra','pc_synced':(self.now-timedelta(hours=4)).isoformat()}):
            data['agents'].append(extra)
            alerts=command.availability_actions(data,ts,self.now)
            self.assertEqual(len(alerts),1);self.assertEqual(alerts[0]['topics'],['0','1','2'])
            data['agents'].pop()
        data['agents'].append({'id':'dev-astra','pc_synced':self.now.isoformat()})
        data['agent_locks']={'dev-astra':{'mode':'all'}}
        self.assertEqual(len(command.availability_actions(data,ts,self.now)),1)
    def test_new_command_topic_excluded_from_restart(self):
        cfg={'topics_dir':str(self.root/'topics'),'data_dir':str(self.root/'data')}
        (self.root/'topics').mkdir()
        current=[dict(id='T-20261003-aaa111',title='new',status='active',command_mode=True),
                 dict(id='T-20261003-bbb222',title='legacy',status='active')]
        state=command_reset.migrate(cfg,current)
        self.assertEqual([x['old'] for x in state['topics']],['T-20261003-bbb222'])
    def test_third_attempt_pass_then_reset_can_run_again_keeps_history(self):
        rows=testflow.plan(None,{'dev-claude'})
        item=rows[0];item.update(state='passed',accepted_by='server-astra',attempt=3,history=[{'op':'test-pass'}])
        e=dict(op='test-reset',agent='server-astra',body='실게임 반려 원인 수정',ts=self.now.isoformat())
        rows=testflow.transition(rows,e)
        self.assertEqual(rows[0]['history'][-1]['previous_attempt'],3)
        rows=testflow.transition(rows,dict(e,op='test-start',agent='dev-claude',task_id='environment'))
        self.assertEqual(rows[0]['attempt'],1);self.assertEqual(rows[0]['state'],'running')
        self.assertEqual(rows[0]['history'][0]['op'],'test-pass')
    def test_assign_lock_and_stale_snapshot_do_not_delegate(self):
        data=copy.deepcopy(self.data);data['agents'][0]['pc_synced']=self.now.isoformat()
        data['agent_locks']={'server-astra':{'mode':'assign'}}
        self.assertIsNone(command.delegation(data,self.now))
        data['agent_locks']['server-astra']['mode']='all'
        self.assertIsNotNone(command.delegation(data,self.now))
        data['meta']['generated_at']=(self.now-timedelta(minutes=3)).isoformat()
        self.assertIsNone(command.delegation(data,self.now))
        self.assertNotIn('test-replan',command.DEPUTY_OPS)
    def test_restart_lock_transfer_preserves_original_and_allows_edit(self):
        sc=self.root/'scratch';tree=self.root/'dev';(tree/'src').mkdir(parents=True)
        old='T-20261003-aaa111';new='T-20261003-bbb222';rel='src/test.cpp'
        base=b'base\n';raw=b'previous change\n';(tree/rel).write_bytes(raw)
        bk=sc/old/'backup'/rel;bk.parent.mkdir(parents=True);bk.write_bytes(base)
        f=dict(base_sha=runner._sha(base),last_sha=runner._sha(raw),enc='utf-8',created=False,diff='test.diff')
        man={'files':{rel:f},'builds':[]};runner._dev_save(sc/old/'manifest.json',man)
        before=(sc/old/'manifest.json').read_bytes()
        locks={rel:old};runner._dev_save(sc/'locks.json',locks)
        self.assertEqual(runner._inherit_restart_locks(sc,old,new,locks),1)
        self.assertEqual(runner._inherit_restart_locks(sc,old,new,locks),0)
        self.assertEqual(locks[rel],new);self.assertEqual((sc/new/'backup'/rel).read_bytes(),base)
        dev={'root':str(tree),'scratch':str(sc),'write':['src']}
        with patch.object(runner,'dev_cfg',return_value=dev):
            runner.dev_edit('dev-claude',new,{'file':rel,'edits':[{'old':'previous change','new':'new change'}]},None)
        self.assertEqual((tree/rel).read_bytes(),b'new change\n')
        self.assertEqual((sc/old/'manifest.json').read_bytes(),before);self.assertEqual(bk.read_bytes(),base)
        after=runner._dev_json(sc/new/'manifest.json',{})
        self.assertEqual(after['files'][rel]['base_sha'],f['base_sha'])
        # 원래 주제의 보존 빌드 사본은 용량 정리로도 삭제하지 않는다.
        with patch.object(runner,'_rm_build') as rm:
            runner._dev_cleanup_one(dict(dev,scratch_cap_gb=0),sc,{old:{'archived':True,'restarted_as':new},new:{'status':'active'}})
            rm.assert_not_called()
    def test_missing_secret_rules_and_hardlink_fail_closed(self):
        tool=self.root/'work.py';tool.write_text('def scan_file(p): return []')
        src=self.root/'proof';src.write_bytes(b'proof')
        with self.assertRaisesRegex(ValueError,'SECRET_RES'):release_queue.scan_sources(self.root,[src])
        os.link(src,self.root/'alias')
        with self.assertRaises(ValueError):command.safe_file(self.root,'alias')
    def test_work_retry_limit_requires_changed_plan(self):
        state=command.initial()
        state['tasks']=[dict(id='code',assignee='dev-claude',state='blocked',attempt=3,depends_on=[])]
        for op in ('revise','reassign'):
            with self.assertRaisesRegex(ValueError,'3회 소진'):
                command.transition(state,dict(agent='server-astra',revision=0,op=op,task_id='code',body='반복',to='dev-astra'),{'server-astra','dev-astra','dev-claude'})

    def test_windows_path_alias_rejected(self):
        for value in ['server/x.conf.','server/dir /a.bin']:
            with self.assertRaises(ValueError):release_queue.relative(value)

if __name__=='__main__':unittest.main()
