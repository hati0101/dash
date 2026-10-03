"""실제 command→node 기록→topics 투영→runner 배분 통합 시험. 운영/원격/AI 호출 없음."""
import copy
import hashlib
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import command
import command_reset
import node
import runner
import topics
import release_queue

KNOWN = {"server-astra", "dev-claude", "dev-astra", "server-claude"}
T = "T-20261003-abcdef"
W = "FT-20261003-abcdef"


class Workflow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cfg = {"pc": {"id": "fixture", "label": "시험", "role": "hub"},
                    "node_data_dir": str(self.root / "nodes"), "topics_dir": str(self.root / "topics"),
                    "data_dir": str(self.root / "data"), "bridge_dir": str(self.root / "bridge"),
                    "agents": [{"id": a, "ai": "gpt" if "astra" in a else "claude"} for a in KNOWN]}
        runner.CFG = self.cfg
        self.wp = patch.object(runner, "WORK_PY", self.root / "work.py")
        self.wp.start()
        (self.root / "work.py").write_text("# fixture", encoding="utf8")
        topics.write_json(self.root / "topics" / T / "topic.json", {"id": T, "title": "시험 주제", "body": "목표", "kind": "기능·개선", "priority": "P2", "command_mode": True})
        topics.write_json(self.root / "topics" / T / "claude.json", {"assignee": command.LEAD, "assigned_at": "2026-10-03T10:00:00+09:00"})
        self.task = {"id": "code", "title": "구현", "scope": "대상만 수정", "done_when": "회귀 시험 통과", "assignee": "dev-claude", "depends_on": []}
        self.cfg_other = {**self.cfg, "node_data_dir": str(self.root / "other")}

    def tearDown(self):
        self.wp.stop()
        self.tmp.cleanup()

    def view(self):
        records = node.load_records(self.cfg)["topic_records"]
        return topics.merged_topics(self.root / "topics", self.cfg, records, KNOWN)[0]

    def action(self, who, cmd, body="근거 확인", file="code", options=None, **kw):
        t = self.view()
        j = {"agent": who, "topic": t, "work_id": W, "mode": "impl"}
        return command.apply_action(j, {"cmd": cmd, "body": body, "file": file, "options": options, **kw}, self.cfg, KNOWN, set(), self.root)

    def plan(self, **kw):
        return self.action(command.LEAD, "plan", json.dumps({"tasks": [self.task], **kw}))

    def submit(self):
        rel = f"work/{W}/dev-claude/RESULT.md"
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("fixture 검사 통과, 실게임 미실행", encoding="utf8")
        self.action("dev-claude", "submit", "구현 및 격리 검사 결과", options=[rel])
        return p

    def test_server_is_commander_developer_is_stage_worker(self):
        self.assertEqual(self.view()["turn"], command.LEAD)
        self.assertEqual(topics.stage_owner("test", self.view(), KNOWN), "dev-claude")
        self.assertEqual(topics.stage_owner("pack", self.view(), KNOWN), "dev-claude")
        self.assertEqual(topics.stage_owner("prep", self.view(), KNOWN), command.LEAD)

    def test_developers_cannot_issue_plan(self):
        for actor in KNOWN - {command.LEAD}:
            with self.assertRaises(ValueError):
                self.action(actor, "plan", json.dumps({"tasks": [self.task]}))

    def test_amend_and_cancel_require_commander_and_preserve_history(self):
        self.plan(); self.submit(); self.action(command.LEAD, 'accept')
        extra = {**self.task, 'id':'extra','depends_on':['code']}
        body = json.dumps({'tasks':[self.task, extra]})
        with self.assertRaises(ValueError): self.action('dev-claude', 'amend', body)
        self.action(command.LEAD, 'amend', body)
        self.assertEqual(self.view()['command']['tasks'][0]['state'], 'accepted')
        self.assertFalse(command.finished(self.view()['command']))
        self.action(command.LEAD, 'cancel', '중복 조사라서 제외', file='extra')
        self.assertTrue(command.finished(self.view()['command']))
        self.assertEqual(self.view()['command']['events'][-1]['op'],'cancel')

    def test_full_plan_submit_accept_pipeline(self):
        self.plan()
        t = self.view()
        self.assertEqual(t["turn"], "dev-claude")
        jobs = runner.find_jobs({"topics": [t], "agents": list(node.my_agents(self.cfg).values())}, {}, only="dev-claude")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["mode"], "impl")
        self.assertEqual(runner.stage_doer(t), "dev-claude")
        self.submit()
        self.assertEqual(self.view()["turn"], command.LEAD)
        self.action(command.LEAD, "accept")
        self.assertTrue(command.finished(self.view()["command"]))

    def test_tampered_evidence_blocks_accept(self):
        self.plan(); p = self.submit(); p.write_text("바뀜", encoding="utf8")
        with self.assertRaises(ValueError): self.action(command.LEAD, "accept")
        self.assertEqual(self.view()["command"]["tasks"][0]["state"], "review")

    def test_revision_retry_and_old_event(self):
        self.plan(); self.submit()
        self.action(command.LEAD, "revise", "실패 경로 추가 확인")
        self.assertEqual(self.view()["turn"], "dev-claude")
        s = self.view()["command"]
        self.assertEqual(s["tasks"][0]["attempt"], 2)
        self.assertEqual(command.project(s["events"], KNOWN, s)["revision"], s["revision"])
        with self.assertRaises(ValueError): command.transition(s, {"revision": 0, "agent": "dev-claude", "op": "submit"}, KNOWN)

    def test_no_self_accept_no_missing_evidence(self):
        self.plan()
        with self.assertRaises(ValueError): self.action("dev-claude", "submit", options=[])
        self.submit()
        with self.assertRaises(ValueError): self.action("dev-claude", "accept")

    def test_block_and_reassignment(self):
        self.plan(); self.action("dev-claude", "blocked", "로그인 만료")
        self.assertEqual(self.view()["turn"], command.LEAD)
        with self.assertRaises(ValueError): self.action(command.LEAD, "accept")
        self.action(command.LEAD, "reassign", "개발컴 Astra가 이어서 검증", to="dev-astra")
        self.assertEqual(self.view()["turn"], "dev-astra")

    def test_dependency_cycle_unknown_and_duplicate_rejected(self):
        for tasks in ([{**self.task, "depends_on": ["code"]}], [self.task, self.task], [{**self.task, "assignee": "missing"}]):
            with self.assertRaises(ValueError): command.validate_tasks(tasks, KNOWN)

    def test_dependency_released_only_after_accept(self):
        task2 = {**self.task, "id": "review", "assignee": "dev-astra", "depends_on": ["code"]}
        self.action(command.LEAD, "plan", json.dumps({"tasks": [self.task, task2]}))
        self.submit(); self.assertEqual(self.view()["turn"], command.LEAD)
        self.action(command.LEAD, "accept")
        self.assertEqual(self.view()["turn"], "dev-astra")

    def test_runner_prevents_worker_done_and_routes_question(self):
        self.plan(); t = self.view()
        j = {"agent": "dev-claude", "topic": t, "work_id": W}
        data = {"agents": [{"id": a} for a in KNOWN]}
        done, failed = runner.apply(j, {"actions": [{"type": "state", "status": "done", "body": "완료" * 30}]}, data)
        self.assertTrue(failed); self.assertFalse(done)
        done, failed = runner.apply(j, {"actions": [{"type": "ask", "question": "환경 로그인 만료"}]}, data)
        self.assertFalse(failed); self.assertIn("command", done)
        self.assertFalse(node.load_records(self.cfg).get("asks"))
        self.assertEqual(self.view()["turn"], command.LEAD)

    def test_commander_incomplete_question_rejected(self):
        j = {"agent": command.LEAD, "topic": self.view()}
        done, failed = runner.apply(j, {"actions": [{"type": "ask", "question": "다음에 뭐 할까요?"}]}, {"agents": [{"id": a} for a in KNOWN]})
        self.assertTrue(failed); self.assertFalse(done)

    def test_local_overlay_rehydrates_command(self):
        t = self.view(); self.plan()
        data = {"topics": [t], "agents": [{"id": a} for a in KNOWN], "meta": {"generated_at": "2026-10-03T00:00:00+09:00"}}
        runner.overlay_local(data, node.load_records(self.cfg))
        self.assertEqual(data["topics"][0]["turn"], "dev-claude")

    def test_path_escape_denied(self):
        for value in ("../secret", "C:/secret", "a\\b", "/root", ".git/config"):
            with self.assertRaises(ValueError): command.safe_file(self.root, value)

    def test_reset_idempotent_preserves_original_and_held(self):
        prior = self.view()
        prior.update(status="active", command_mode=False)
        held = {**prior, "id": "T-20261003-parked", "status": "parked"}
        before = (self.root / "topics" / T / "topic.json").read_bytes()
        a = command_reset.migrate(self.cfg, [prior, held])
        self.assertEqual(len(a["topics"]), 1)
        b = command_reset.migrate(self.cfg, [prior, held])
        self.assertEqual(a, b)
        self.assertEqual(before, (self.root / "topics" / T / "topic.json").read_bytes())
        views = topics.merged_topics(self.root / "topics", self.cfg, [], KNOWN)
        old = next(x for x in views if x["id"] == T)
        new = next(x for x in views if x["id"] != T)
        self.assertTrue(old["archived"]); self.assertIsNone(old["turn"])
        self.assertEqual(new["status"], "new"); self.assertNotIn("gate", new)
        self.assertNotIn("work_id", new)

    def test_reset_recovers_partial_migration_without_duplicate_or_lost_topic(self):
        first = self.view(); first.update(status='active',command_mode=False)
        second = {**first, 'id':'T-20261003-bbbbbb'}
        topics.write_json(self.root/'topics'/second['id']/'topic.json',second)
        original_write = topics.write_json
        count = 0
        def fail_second(path, value):
            nonlocal count
            if value.get('restart_of'):
                count += 1
                if count == 2: raise OSError('fixture power loss')
            return original_write(path,value)
        with patch.object(topics,'write_json',fail_second), self.assertRaises(OSError):
            command_reset.migrate(self.cfg,[first,second])
        (self.root/'data/command-reset.json').unlink()
        (self.root/'data/command-reset-plan.json').unlink()
        recovered = command_reset.migrate(self.cfg,[first,second])
        self.assertTrue(recovered['complete']); self.assertEqual(len(recovered['topics']),2)
        self.assertEqual(len(list((self.root/'topics').glob('*/topic.json'))),4)
        self.assertEqual(recovered,command_reset.migrate(self.cfg,[first,second]))

    def test_managed_gate_sequence(self):
        self.plan(human_test=False, test_reason="UI 도구 시험으로 확인")
        self.submit(); self.action(command.LEAD, "accept")
        base = datetime(2026, 10, 3, 12, tzinfo=timezone(timedelta(hours=9)))
        ts = lambda n: (base + timedelta(minutes=n)).isoformat()
        state = self.view()["command"]
        for event in state["events"]: event["ts"] = ts(0)
        for check in state['tests']:
            for op in ('test-start','test-pass','test-accept'):
                state=command.transition(state,dict(event_id=f'{check["id"]}-{op}',revision=state['revision'],
                    agent='server-astra' if op == 'test-accept' else 'dev-claude',op=op,task_id=check['id'],body='fixture 검사',ts=ts(1.5),
                    evidence=[{'path':'fixture/log','sha256':'a'*64}]),KNOWN)
        t = {"id": T, "kind": "기능·개선", "assignee": command.LEAD, "command_mode": True, "command": state}
        finishes = [(ts(1),command.LEAD,"구현 검수 완료"),(ts(2),"dev-claude","자체 시험 통과"),(ts(3),"dev-claude","배포본 수신 준비"),(ts(4),command.LEAD,"대상 파일: server/test.txt\n겹침: 없음")]
        g = topics.run_gates(t, finishes, {}, KNOWN)
        self.assertEqual(g["stage"], "test"); self.assertEqual(g["gate"]["n"], 4)
        t["command"]["human_test"] = True
        g = topics.run_gates(t, finishes[:2], {}, KNOWN)
        self.assertEqual(g["gate"]["n"],4); self.assertTrue(g["live"])
        answer = {g["gate"]["id"]: {"choice":"통과", "ts":ts(3)}}
        g = topics.run_gates(t, finishes[:2], answer, KNOWN)
        self.assertEqual(g["gate"]["n"],5); self.assertFalse(g["live"])
        revised5 = {**answer,g['gate']['id']:{'choice':'수정','note':'배포 전 동작 수정','ts':ts(3.5)}}
        after5 = topics.run_gates(t,finishes[:2]+[(ts(4),'dev-claude','예전 시험 재사용')],revised5,KNOWN)
        self.assertEqual(after5['stage'],'test');self.assertFalse(after5['live']);self.assertIsNone(after5['gate'])
        self.assertEqual(after5['history'][-1]['act'],'test')
        self.assertEqual(topics.whose_turn(dict(status='active',stage='test',command_mode=True,live_session=after5['live'],test_reset_needed=True)),command.LEAD)
        answer[g["gate"]["id"]] = {"choice":"배포본 만들기", "ts":ts(3.5)}
        packed = topics.run_gates(t, finishes[:2] + [(ts(4), 'dev-claude', '배포본 완료')], answer, KNOWN)
        self.assertEqual(packed['gate']['n'], 7)
        first=topics.run_gates(t,finishes[:2],{},KNOWN)
        rejected={first['gate']['id']:{'choice':'수정','note':'동시 거래를 다시 확인','ts':ts(3)}}
        stale=topics.run_gates(t,finishes[:2]+[(ts(4),'dev-claude','예전 통과 재사용')],rejected,KNOWN)
        self.assertEqual(stale['stage'],'test');self.assertIsNone(stale['gate']);self.assertFalse(stale['live'])
        self.assertEqual(topics.whose_turn(dict(status='active',stage='test',command_mode=True,live_session=stale['live'],test_reset_needed=True)), command.LEAD)
        retry=command.transition(t['command'],dict(event_id='reset',revision=t['command']['revision'],agent=command.LEAD,op='test-reset',body='반려 원인 수정',ts=ts(4)),KNOWN)
        for check in retry['tests']:
            for op in ('test-start','test-pass','test-accept'):
                retry=command.transition(retry,dict(event_id=f"retry-{check['id']}-{op}",revision=retry['revision'],agent=command.LEAD if op=='test-accept' else 'dev-claude',op=op,task_id=check['id'],body='재시험 완료',ts=ts(5),evidence=[{'path':'fixture/newlog','sha256':'b'*64}]),KNOWN)
        t['command']=retry
        reopened=topics.run_gates(t,finishes[:2]+[(ts(6),'dev-claude','새 시험 완료')],rejected,KNOWN)
        self.assertEqual(reopened['gate']['n'],4)
        self.assertNotEqual(reopened['gate']['id'],first['gate']['id'])



class Package(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        (self.root / "work.py").write_text("SECRET_RES=[('fixture',__import__('re').compile('fixture-secret'))]\ndef scan_file(p):\n    return ['fixture secret'] if b'fixture-secret' in p.read_bytes() else []\n", encoding="utf8")
        self.folder = self.root / "work" / W / "dev-claude"; self.folder.mkdir(parents=True)
        (self.folder / "fix.txt").write_bytes(b"new")
        (self.folder / "RESULT.md").write_bytes(b"fixture PASS")
        self.data = {"version":1,"topic":T,"summary":"시험 수정","apply_steps":"정지·백업 후 교체","rollback_steps":"백업 복구","verify_steps":"기동 확인",
                     "changes":[{"operation":"replace","target":"client/a.bin","source":f"work/{W}/dev-claude/fix.txt","before_sha256":hashlib.sha256(b"old").hexdigest(),"after_sha256":hashlib.sha256(b"new").hexdigest()}],
                     "evidence": command.evidence(self.root,[f"work/{W}/dev-claude/RESULT.md"])}
        self.save()

    def save(self): (self.folder / "PACKAGE.json").write_text(json.dumps(self.data),encoding="utf8")
    def tearDown(self): self.tmp.cleanup()
    def load(self): return release_queue.load_package(self.root,W,T)

    def test_sensitive_create_and_sql_replace_denied(self):
        original=copy.deepcopy(self.data)
        for target,operation in [('server/conf/import/custom.txt','create'),('server/conf/map_athena.conf','create'),('server/change.sql','replace')]:
            self.data=copy.deepcopy(original)
            self.data['changes'][0].update(target=target,operation=operation)
            if operation=='create':self.data['changes'][0]['before_sha256']=None
            self.save()
            with self.subTest(target=target), self.assertRaises(ValueError):self.load()

    def test_package_receive_export_and_baseline(self):
        p=self.load(); target=self.root/"target";target.mkdir();(target/"a.bin").write_bytes(b"old")
        result=release_queue.export_packages([p],self.root,self.root/"batch.zip","R-20261003",{"client":str(target)})
        self.assertTrue(result["baseline_checked"]);self.assertFalse(result["operating_applied"])
        self.assertEqual((target/"a.bin").read_bytes(),b"old")

    def test_missing_tampered_wrong_topic_rejected(self):
        with self.assertRaises(ValueError): release_queue.load_package(self.root,W,"T-20261003-ffffff")
        (self.folder/"fix.txt").write_bytes(b"tampered")
        with self.assertRaises(ValueError): self.load()

    def test_batch_overlap_fails(self):
        p=self.load()
        with self.assertRaises(ValueError): release_queue.export_packages([p,p],self.root,self.root/"batch.zip","R-20261003")
        self.assertFalse((self.root/"batch.zip").exists())

    def test_stale_production_baseline_fails(self):
        p=self.load();target=self.root/"target";target.mkdir();(target/"a.bin").write_bytes(b"different")
        with self.assertRaises(ValueError): release_queue.check_targets([p],{"client":str(target)})

    def test_manifest_changes_after_read_fails(self):
        p=self.load();self.data["summary"]="changed";self.save()
        with self.assertRaises(ValueError): release_queue.export_packages([p],self.root,self.root/"batch.zip","R-20261003")

    def test_target_path_and_no_evidence_fail(self):
        self.data["changes"][0]["target"]="server/../../escape";self.save()
        with self.assertRaises(ValueError): self.load()
        self.data['changes'][0]['target']='client/a.bin';self.data['evidence']=[];self.save()
        with self.assertRaisesRegex(ValueError,'검증 근거'): self.load()

    def test_zip_does_not_bypass_source_scanner(self):
        self.data["summary"] = "fixture-secret";self.save()
        with self.assertRaisesRegex(ValueError,"공유 검사"): self.load()

    def test_minimal_diff_contract(self):
        raw=b"--- a/server/a.txt\n+++ b/server/a.txt\n@@ -1 +1 @@\n-old\n+new\n"
        (self.folder/"change.diff").write_bytes(raw)
        self.data["changes"][0].update(operation="patch",target="server/a.txt",source=f"work/{W}/dev-claude/change.diff",source_sha256=hashlib.sha256(raw).hexdigest())
        self.save();p=self.load()
        release_queue.export_packages([p],self.root,self.root/"batch.zip","R-20261003")
        target=self.root/'baseline';target.mkdir();(target/'a.txt').write_bytes(b'old\n')
        self.data['changes'][0].update(before_sha256=hashlib.sha256(b'old\n').hexdigest(),after_sha256=hashlib.sha256(b'new\n').hexdigest())
        self.save();p=self.load()
        release_queue.check_targets([p],{'server':str(target)},self.root)
        self.assertEqual((target/'a.txt').read_bytes(),b'old\n')
        self.data['changes'][0]['after_sha256']='a'*64;self.save();p=self.load()
        with self.assertRaisesRegex(ValueError,'격리 diff'):release_queue.check_targets([p],{'server':str(target)},self.root)

    def test_batch_job_is_local_and_does_not_deploy(self):
        cfg={"pc":{"id":"server","label":"서버컴","role":"node"},"agents":[{"id":"server-astra","ai":"gpt"}],"node_data_dir":str(self.root/"nodes")}
        data={"agents":[{"id":"server-astra"}],"topics":[{"id":T,"title":"배포 시험","work_id":W,"status":"active","stage":"deploy","deploy_session":True,"command_mode":True,"deploy_batch":{"id":"R-20261003"},"status_at":"2026-10-03T15:00:00+09:00"}]}
        state={}
        data['topics'][0]['package_receipts'] = {'prep': self.load()['manifest_sha256']}
        with patch.object(runner,"CFG",cfg,create=True),patch.object(runner,"ROOT",self.root),patch.object(runner,"WORK_PY",self.root/"work.py"):
            jobs=runner.find_jobs(data,state,only="server-astra")
            self.assertEqual(len(jobs),1);self.assertEqual(jobs[0]["kind"],"batch")
            runner.run_job(jobs[0],data,state)
            self.assertFalse(state["batches"]["R-20261003"]["result"]["operating_applied"])
            self.assertEqual(runner.find_jobs(data,state,only="server-astra"),[])

    def test_prepared_contract_mutation_is_rejected(self):
        topic = {'id': T, 'work_id': W, 'package_receipts': {'prep': self.load()['manifest_sha256']}}
        self.data['summary'] = '준비 후 몰래 바뀐 계약'; self.save()
        with self.assertRaisesRegex(ValueError, '제출된 배포 계약'):
            release_queue.load_topic_package(self.root, topic)

    def test_batch_failure_waits_for_changed_approved_input(self):
        cfg={'pc': {'id': 'server', 'role': 'node'}, 'agents': [{'id':'server-astra','ai':'gpt'}], 'node_data_dir':str(self.root/'nodes')}
        topic={'id':T,'title':'묶음 실패','work_id':W,'status':'active','stage':'deploy','deploy_session':True,'command_mode':True,'deploy_batch':{'id':'R-20261003'}}
        data={'agents':cfg['agents'],'topics':[topic]}; state={}
        with patch.object(runner,'CFG',cfg), patch.object(runner,'ROOT',self.root), patch.object(runner,'WORK_PY',self.root/'work.py'):
            job=runner.find_jobs(data,state,only='server-astra')[0]
            runner.run_job(job,data,state)
            self.assertTrue(state['batches']['R-20261003']['requires_change'])
            self.assertEqual(runner.find_jobs(data,state,only='server-astra'),[])
            topic['package_receipts']={'prep':self.load()['manifest_sha256']}
            self.assertEqual(len(runner.find_jobs(data,state,only='server-astra')),1)


if __name__ == "__main__": unittest.main(verbosity=2)
