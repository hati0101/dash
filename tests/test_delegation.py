import sys, unittest, copy
from pathlib import Path
from datetime import datetime, timedelta, timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import command

class Delegation(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,3,16,tzinfo=timezone(timedelta(hours=9)))
        self.data={'agents':[{'id':'server-astra','pc_synced':(self.now-timedelta(hours=3)).isoformat()},{'id':'dev-claude','pc_synced':self.now.isoformat()}], 'meta':{'generated_at':self.now.isoformat()}}
        self.proof=command.delegation(self.data,self.now)
        self.known={'server-astra','dev-claude','dev-astra'}
        self.state=command.initial()
        self.state['tasks']=[{'id':'code','assignee':'dev-astra','state':'review','attempt':1,'depends_on':[], 'result':{'by':'dev-astra','summary':'checked','evidence':[]}}]
        self.event={'agent':'dev-claude','op':'accept','task_id':'code','body':'독립 검증 결과 대조','revision':0,'ts':self.now.isoformat(),'delegation':self.proof,'event_id':'deputy-1'}
    def test_offline_accept_and_replay_keep_deputy_identity(self):
        updated=command.transition(self.state,self.event,self.known)
        self.assertEqual(updated['tasks'][0]['state'],'accepted')
        self.assertEqual(updated['tasks'][0]['accepted_by'],'dev-claude')
        self.assertEqual(updated['tasks'][0]['accepted_acting_for'],'server-astra')
        self.assertEqual(updated['events'][0]['agent'],'dev-claude')
        self.assertEqual(command.project([self.event],self.known,self.state)['revision'],1)
    def test_online_and_locked_deputy_cannot_delegate(self):
        self.data['agents'][0]['pc_synced']=self.now.isoformat()
        self.assertIsNone(command.delegation(self.data,self.now))
        self.data['agent_locks']={'server-astra':{'mode':'all'}}
        self.assertIsNotNone(command.delegation(self.data,self.now))
        self.data['agent_locks']['dev-claude']={'mode':'assign'}
        self.assertIsNone(command.delegation(self.data,self.now))
    def test_self_accept_expired_proof_and_privilege_expansion_rejected(self):
        cases=[{**self.event,'ts':(self.now+timedelta(minutes=3)).isoformat()},
               {**self.event,'op':'plan','tasks':[]}, {**self.event,'delegation':None}]
        for e in cases:
            with self.assertRaises(ValueError): command.transition(self.state,e,self.known)
        self.state['tasks'][0]['assignee']='dev-claude'
        with self.assertRaisesRegex(ValueError,'자기 작업'): command.transition(self.state,self.event,self.known)
    def test_concurrent_revision_cannot_overwrite(self):
        updated=command.transition(self.state,self.event,self.known)
        with self.assertRaises(ValueError): command.transition(updated,{**self.event,'agent':'server-astra','delegation':None},self.known)
    def test_routing_never_delegates_deploy_or_empty_plan(self):
        t={'command_mode':True,'stage':'work','turn':'server-astra','command':self.state}
        command.route_deputy(t,self.proof);self.assertEqual(t['turn'],'dev-claude')
        t.update(stage='prep',turn='server-astra');command.route_deputy(t,self.proof)
        self.assertEqual(t['turn'],'server-astra')
        t.update(stage='work',command=command.initial());command.route_deputy(t,self.proof)
        self.assertEqual(t['turn'],'server-astra')

if __name__=='__main__':unittest.main()
