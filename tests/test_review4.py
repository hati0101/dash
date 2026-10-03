import json,sys,tempfile,unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import command,topics,node,runner

class Review4(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.known={'server-astra','dev-claude','dev-astra'};self.tid='T-20261003-abc123';self.wid='FT-20261003-abc123'
        self.cfg={'pc':{'id':'fixture','role':'hub'},'topics_dir':str(self.root/'topics'),'data_dir':str(self.root/'data'),'node_data_dir':str(self.root/'nodes'),'agents':[{'id':a,'ai':'gpt'} for a in self.known]}
        self.base=datetime(2026,10,3,12,tzinfo=timezone(timedelta(hours=9)))
        self.task=dict(id='code',title='목표 조사',scope='근거 조사',done_when='근거 확인',assignee='dev-claude',depends_on=[])
        self.payload=self.root/f'work/{self.wid}/dev-claude/result.md';self.payload.parent.mkdir(parents=True);self.payload.write_text('fixture evidence',encoding='utf-8')
        self.tp=self.root/'topics'/self.tid/'topic.json'
        topics.write_json(self.tp,dict(id=self.tid,title='시험',kind='기능·개선',command_mode=True))
        topics.write_json(self.tp.parent/'claude.json',dict(assignee='server-astra',assigned_at=self.ts(0)))
    def tearDown(self):self.tmp.cleanup()
    def ts(self,n):return (self.base+timedelta(minutes=n)).isoformat()
    def view(self):return topics.merged_topics(self.root/'topics',self.cfg,node.load_records(self.cfg)['topic_records'],self.known)[0]
    def cmd(self,n,op,who='server-astra',file='code',body='원인과 근거 확인',**kw):
        with patch.object(node,'now_iso',return_value=self.ts(n)):
            return command.apply_action({'topic':self.view(),'agent':who,'work_id':self.wid},dict(cmd=op,file=file,body=body,**kw),self.cfg,self.known,set(),self.root)
    def submit(self,n,file='code'):
        self.cmd(n,'submit','dev-claude',file,options=[self.payload.relative_to(self.root).as_posix()]);self.cmd(n+.1,'accept',file=file)
    def done(self,n,who):
        with patch.object(node,'now_iso',return_value=self.ts(n)):
            node.add_topic_record(self.cfg,self.tid,who,'status',status='done',body='핵심: 완료 근거 확인 / 정할 것: 결과 확인 / 권장: 다음 단계',command_revision=self.view()['command']['revision'])
    def answer(self,gate,choice,n):
        topics.write_json(self.root/'data/user.json',{'decisions_answered':[dict(id=gate['id'],choice=choice,note='더 확인해 주세요',ts=self.ts(n))]})
    def run_checks(self,n):
        for item in self.view()['command']['tests']:
            self.cmd(n,'test-start','dev-claude',item['id'])
            self.cmd(n+.01,'test-pass','dev-claude',item['id'],options=[self.payload.relative_to(self.root).as_posix()])
            self.cmd(n+.02,'test-accept',file=item['id'])
    def test_research_return_allows_amend_then_new_result_gate(self):
        data=json.loads(self.tp.read_text(encoding='utf-8'));data['kind']='조사·분석';topics.write_json(self.tp,data)
        self.cmd(0,'plan',body=json.dumps({'tasks':[self.task]}));self.submit(1);self.done(2,'server-astra')
        first=self.view()['gate'];self.assertEqual(first['n'],40)
        self.answer(first,'',12)
        t=self.view();self.assertEqual(t['stage'],'work');self.assertEqual(t['turn'],'server-astra');self.assertFalse(t.get('live_session'))
        self.cmd(3,'amend',body=json.dumps({'tasks':[self.task,dict(self.task,id='more',title='추가 조사',depends_on=['code'])]}))
        self.submit(4,'more');self.done(5,'server-astra')
        last=self.view()['gate'];self.assertEqual(last['n'],40);self.assertNotEqual(last['id'],first['id'])
    def check_clock(self,offset):
        self.cmd(0,'plan',body=json.dumps({'tasks':[self.task]}));self.submit(1);self.done(2,'server-astra')
        self.run_checks(3);self.done(4,'dev-claude');first=self.view()['gate'];self.assertEqual(first['n'],4)
        self.answer(first,'문제 있음',5+offset)
        t=self.view();self.assertTrue(t['test_reset_needed']);self.assertEqual(t['turn'],'server-astra');self.assertEqual(runner.stage_doer(t),'server-astra')
        self.cmd(6,'test-reset')
        t=self.view();self.assertFalse(t['test_reset_needed']);self.assertEqual(t['turn'],'dev-claude');self.assertEqual(runner.stage_doer(t),'dev-claude')
        self.assertEqual(t['command']['events'][-1]['review_gate_id'],first['id'])
        self.run_checks(7);self.done(8,'dev-claude')
        last=self.view()['gate'];self.assertEqual(last['n'],4);self.assertNotEqual(last['id'],first['id'])
    def test_browser_clock_ten_minutes_fast(self):self.check_clock(10)
    def test_browser_clock_ten_minutes_slow(self):self.check_clock(-10)

if __name__=='__main__':unittest.main()
