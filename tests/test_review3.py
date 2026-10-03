import copy, difflib, sys, tempfile, unittest
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import runner, command

class Review3(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.sc=self.root/'scratch';self.tree=self.root/'tree';self.work=self.root/'real-work'
        self.old='T-20261003-aaa111';self.new='T-20261003-bbb222';self.rel='src/test.cpp'
        self.base=b'base\n';self.raw=b'changed\n'
        self.path=self.tree/self.rel;self.path.parent.mkdir(parents=True);self.path.write_bytes(self.raw)
        self.backup=self.sc/self.old/'backup'/self.rel;self.backup.parent.mkdir(parents=True);self.backup.write_bytes(self.base)
        self.f=dict(base_sha=runner._sha(self.base),last_sha=runner._sha(self.raw),created=False,enc='utf-8',diff='test.diff')
        runner._dev_save(self.sc/self.old/'manifest.json',{'files':{self.rel:self.f},'builds':[]})
        self.locks={self.rel:self.old};runner._dev_save(self.sc/'locks.json',self.locks)
        self.dev={'root':str(self.tree),'scratch':str(self.sc)}
        self.work.mkdir();self.wp=patch.object(runner,'WORK_PY',self.work/'work.py');self.wp.start()
    def tearDown(self):self.wp.stop();self.tmp.cleanup()
    def inherit(self):runner._inherit_restart_locks(self.sc,self.old,self.new,self.locks)
    def save_diff(self,text):
        folder=self.work/'work/FT-20261003-test';folder.mkdir(parents=True,exist_ok=True)
        (folder/'README.md').write_text('| 대시보드 주제 | '+self.old+' |',encoding='utf8')
        p=folder/'dev-claude/patch/test.diff';p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf8')
        return p
    def content(self):
        return '# 원본 SHA256 '+self.f['base_sha']+'\n# 수정 SHA256 '+self.f['last_sha']+'\n# 인코딩 utf-8 · 줄바꿈 LF\n'+''.join(difflib.unified_diff(self.base.decode().splitlines(True),self.raw.decode().splitlines(True),'a/'+self.rel,'b/'+self.rel))
    def test_inherited_revert_denied_without_exact_diff_even_force(self):
        self.inherit()
        for text in (None,self.content().replace('changed','wrong'),self.content().replace(self.f['last_sha'],'0'*64)):
            if text:self.save_diff(text)
            msgs=runner._dev_revert(self.dev,self.new,None,True)
            self.assertEqual(self.path.read_bytes(),self.raw);self.assertTrue(any('검증 실패' in m for m in msgs))
            self.assertIn(self.rel,runner._dev_json(self.sc/self.new/'manifest.json',{})['files'])
        self.save_diff(self.content())
        msgs=runner._dev_revert(self.dev,self.new,None,False)
        self.assertEqual(self.path.read_bytes(),self.base);self.assertTrue(any('원본으로 되돌림' in m for m in msgs))
        self.assertEqual(self.backup.read_bytes(),self.base)
    def test_cleanup_park_delete_preserves_missing_diff(self):
        self.inherit()
        for state in ('parked','dropped'):
            msgs=runner._dev_cleanup_one(self.dev,self.sc,{self.old:{'archived':True,'restarted_as':self.new},self.new:{'status':state}})
            self.assertEqual(self.path.read_bytes(),self.raw);self.assertTrue(any('원복하지 않고 보존' in m for m in msgs))
    def test_partial_destination_and_interrupted_temp_copy_recover(self):
        dest=self.sc/self.new/'backup'/self.rel;dest.parent.mkdir(parents=True);dest.write_bytes(b'ba')
        original=Path.write_bytes
        def interrupted(p,data):
            if p.name.endswith('.inherit.tmp'):
                original(p,data[:2]);raise OSError('fixture interrupted copy')
            return original(p,data)
        with patch.object(Path,'write_bytes',interrupted),self.assertRaises(OSError):self.inherit()
        self.assertEqual(runner._dev_json(self.sc/'locks.json',{})[self.rel],self.old)
        self.inherit()
        self.assertEqual(dest.read_bytes(),self.base);self.assertEqual(self.locks[self.rel],self.new)
        self.assertEqual(self.backup.read_bytes(),self.base)
        self.assertEqual(list(dest.parent.glob('*.interrupted-*'))[0].read_bytes(),b'ba')
        self.assertEqual(runner._inherit_restart_locks(self.sc,self.old,self.new,self.locks),0)
    def test_one_bad_topic_does_not_stop_other_cleanup(self):
        other='T-20261003-ccc333';runner._dev_save(self.sc/other/'manifest.json',{'files':{},'builds':[]})
        with patch.object(runner,'_inherit_restart_locks',side_effect=ValueError('fixture broken backup')):
            msgs=runner._dev_cleanup_one(self.dev,self.sc,{self.old:{'archived':True,'restarted_as':self.new},self.new:{'status':'active'},other:{'status':'parked'}})
        self.assertTrue(any('다른 주제 계속' in m for m in msgs));self.assertFalse((self.sc/other).exists())
        self.assertTrue(self.backup.is_file())
    def test_missing_lead_with_online_deputy_reports_unavailable(self):
        now=datetime.now(timezone.utc)
        data={'agents':[{'id':'dev-claude','pc_synced':now.isoformat()}],'meta':{'generated_at':now.isoformat()}}
        out=command.availability_actions(data,[{'id':'topic','command_mode':True,'status':'active'}],now)
        self.assertEqual(out[0]['title'],'사령탑·대행 모두 불가')

if __name__=='__main__':unittest.main()
