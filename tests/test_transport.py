"""두 PC 폴더, 실제 암호화/복호화, 허브 분배·재시작·사령탑 위임 왕복. 원격 접근 없음."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import build
import command
import node
import topics
import runner


class Transport(unittest.TestCase):
    def test_two_pc_encrypted_restart_and_delegation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); common=root/'wire';common.mkdir()
            cfg=json.loads((Path(topics.__file__).parent/'config.example.json').read_text(encoding='utf8'))
            cfg.update(bridge_dir=str(root/'bridge'),ledger_path=str(root/'ledger.md'),ai_runs_dir=str(root/'runs'),
                       claude_memory_dir=str(root/'memory'),curated_files=[],topics_dir=str(root/'topics'),data_dir=str(root/'data'),
                       nodes_dir=str(common/'nodes'),output=str(common/'data.enc.json'),work_repo=str(root/'workrepo'))
            dev={**cfg,'pc':{'id':'dev','label':'개발컴','role':'hub'},'node_data_dir':str(root/'dev'),
                 'agents':[{'id':'dev-claude','ai':'claude'},{'id':'dev-astra','ai':'gpt'}]}
            server={**cfg,'pc':{'id':'server','label':'서버컴','role':'node'},'node_data_dir':str(root/'server'),
                    'agents':[{'id':'server-astra','ai':'gpt'},{'id':'server-claude','ai':'claude'}]}
            pw='fixture-only-test-password'
            args=argparse.Namespace(password_file=None,if_changed=False)
            def publish(payload):
                result=subprocess.run(['node',str(Path(topics.__file__).parent/'encrypt.mjs'),'encrypt',cfg['output']],
                                      input=json.dumps(payload,ensure_ascii=False).encode(),capture_output=True,
                                      env={**os.environ,'REAL_OPS_PASSWORD':pw})
                self.assertEqual(result.returncode,0,result.stderr)
            old='T-20261003-old001'
            topics.write_json(Path(cfg['topics_dir'])/old/'topic.json',{'id':old,'title':'원래 요청','body':'원래 목표','kind':'기능·개선','priority':'P2'})
            topics.write_json(Path(cfg['topics_dir'])/old/'claude.json',{'assignee':'dev-claude','status':'active'})
            publish({'meta':{},'topics':[]})
            with patch.dict(os.environ,{'REAL_OPS_PASSWORD':pw}):
                node.cmd_pack(args,server)
                topics.cmd_dispatch(args,dev)
                payload=build.build_payload(dev,pw)
                self.assertEqual(payload['meta']['coordination']['lead'],'server-astra')
                self.assertTrue(payload['meta']['command_epoch'])
                archived=next(t for t in payload['topics'] if t['id']==old)
                self.assertTrue(archived['archived'])
                new=next(t for t in payload['topics'] if t.get('restart_of')==old)
                self.assertEqual(new['turn'],'server-astra')
                publish(payload)
                received=node.decrypt_main(server,pw)
                topic=next(t for t in received['topics'] if t['id']==new['id'])
                command.apply_action({'topic':topic,'agent':'server-astra'}, {'cmd':'plan','body':json.dumps({'tasks':[{'id':'implement','title':'구현','scope':'한 기능','done_when':'격리 시험','assignee':'dev-claude','depends_on':[]} ]})},server,
                                     {'server-astra','server-claude','dev-claude','dev-astra'},set(),root/'workrepo')
                node.cmd_pack(args,server)
                payload2=build.build_payload(dev,pw)
                if os.environ.get('FIXTURE_OUTPUT'):
                    publish(payload2)
                    Path(os.environ['FIXTURE_OUTPUT']).write_bytes(Path(cfg['output']).read_bytes())
                delegated=next(t for t in payload2['topics'] if t['id']==new['id'])
                self.assertEqual(delegated['turn'],'dev-claude')
                with patch.object(runner,'CFG',dev,create=True):
                    jobs=runner.find_jobs(payload2,{},only='dev-claude')
                self.assertEqual(len(jobs),1)
                self.assertEqual(jobs[0]['topic']['id'],new['id'])
                topics.cmd_dispatch(args,dev)
                self.assertEqual(len(topics.merged_topics(Path(cfg['topics_dir']),dev)),2)


if __name__=='__main__':unittest.main(verbosity=2)
