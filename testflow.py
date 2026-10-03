"""주제별 시험 계획과 실행 기록. 시험 통과는 실제 근거 파일 해시와 함께만 기록한다."""
import copy
import re

DEFAULTS = [('environment','격리 환경 확인'),('static','변경·정적 검사'),('build','빌드·파서 검사'),
            ('scenario','핵심 동작·실패 경로 시험'),('regression','회귀·재시작·복구 시험')]

def plan(rows, known):
    if rows is None:
        rows = [dict(id=i,title=t,assignee='dev-claude',depends_on=[DEFAULTS[n-1][0]] if n else [],
                     method='주제의 변경 범위에 맞는 검사 명령과 환경을 기록', expected='범위에 해당하는 검사 통과')
                for n,(i,t) in enumerate(DEFAULTS)]
    if not isinstance(rows,list) or not 1 <= len(rows) <= 32:
        raise ValueError('시험 계획은 1~32개여야 합니다')
    result, seen = [], set()
    for x in rows:
        if not isinstance(x,dict) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,39}',str(x.get('id',''))) or x['id'] in seen:
            raise ValueError('시험 ID 오류 또는 중복')
        deps = x.get('depends_on',[])
        if not isinstance(deps,list) or any(d not in seen for d in deps):
            raise ValueError('시험 선행 항목은 앞에 정의해야 합니다')
        if x.get('assignee') not in known or not str(x['assignee']).startswith('dev-'):
            raise ValueError('자동 시험은 등록된 개발컴 작업자가 맡습니다')
        if any(not isinstance(x.get(k),str) or not x[k].strip() for k in ('title','method','expected')):
            raise ValueError('시험 이름·방법·통과 기준이 필요합니다')
        result.append({k:copy.deepcopy(x[k]) for k in ('id','title','assignee','method','expected')} |
                      dict(depends_on=deps,state='pending',attempt=0,history=[],evidence=[],updated_at=None))
        seen.add(x['id'])
    return result

def current(rows):
    completed = {x['id'] for x in rows if x['state'] == 'skipped' or (x['state'] == 'passed' and x.get('accepted_by'))}
    return next((x for x in rows if x['id'] not in completed and set(x['depends_on']) <= completed),None)

def finished(rows):
    return bool(rows) and all(x['state'] == 'skipped' or (x['state'] == 'passed' and x.get('accepted_by')) for x in rows)

def transition(rows,event):
    rows = copy.deepcopy(rows)
    op, who = event['op'],event['agent']
    if op == 'test-reset':
        if who != 'server-astra' or not event.get('body'):
            raise ValueError('재시험 초기화는 사령탑이 이유를 남겨야 합니다')
        for x in rows:
            x['history'].append(dict(op=op,agent=who,ts=event.get('ts'),body=event['body'],previous_attempt=x['attempt'],previous_state=x['state']))
            x.update(state='pending',attempt=0,evidence=[],accepted_by=None,accepted_acting_for=None,updated_at=event.get('ts'),started_at=None,summary=event['body'])
        return rows
    if op == 'test-replan':
        item = current(rows)
        method = event.get('method')
        if who != 'server-astra' or not item or item['id'] != event.get('task_id') or item['state'] not in ('blocked','pending'):
            raise ValueError('사령탑만 멈춘 시험을 재계획할 수 있습니다')
        if not event.get('body') or not isinstance(method, str) or not method.strip() or method.strip() == item['method']:
            raise ValueError('원인 분석과 변경된 시험 방법이 필요합니다')
        item['history'].append(dict(op=op, agent=who, ts=event.get('ts'), body=event['body'], previous_method=item['method'], previous_attempt=item['attempt']))
        item.update(method=method.strip(), attempt=0, state='pending', accepted_by=None, evidence=[], updated_at=event.get('ts'))
        return rows
    item = current(rows)
    if not item or item['id'] != event.get('task_id'):
        raise ValueError('현재 선행 조건이 충족된 시험만 처리하세요')
    if who != item['assignee'] and not (op in ('test-skip','test-release','test-reassign','test-accept','test-revise') and who == 'server-astra'):
        raise ValueError('시험 담당자만 결과를 기록할 수 있습니다')
    if not str(event.get('body') or '').strip():
        raise ValueError('시험 과정·결과 또는 다음 조치가 필요합니다')
    if op == 'test-start':
        if item['attempt'] >= 3:
            raise ValueError('시험 시도 3회 소진: 사령탑이 원인 확인 후 재계획해야 합니다')
        if item['state'] not in ('pending','failed'):
            raise ValueError('시작 가능한 시험 상태가 아닙니다')
        item.update(state='running',attempt=item['attempt']+1,started_at=event.get('ts'),evidence=[],accepted_by=None)
    elif op in ('test-pass','test-fail','test-blocked','test-progress'):
        if item['state'] != 'running':
            raise ValueError('먼저 시험 시작을 기록하세요')
        if op in ('test-pass','test-fail') and not event.get('evidence'):
            raise ValueError('시험 결과 로그 근거가 필요합니다')
        item['state'] = {'test-pass':'passed','test-fail':'failed','test-blocked':'blocked','test-progress':'running'}[op]
        if op == 'test-fail' and item['attempt'] >= 3:
            item['state']='blocked'  # 반복 실패는 사령탑이 원인·시험 범위를 다시 판단한다.
        item['evidence'] = event.get('evidence',item['evidence'])
    elif op in ('test-accept', 'test-revise'):
        if who != 'server-astra' or item['state'] != 'passed':
            raise ValueError('사령탑이 제출된 시험 결과를 검수해야 합니다')
        if op == 'test-accept': item['accepted_by'] = who
        else: item.update(state='pending',accepted_by=None,evidence=[])
    elif op == 'test-reassign':
        if who != 'server-astra' or item['state']=='running':
            raise ValueError('사령탑만 멈춘 시험을 재배정할 수 있습니다')
        item.update(assignee=event['to'],state='pending')
    elif op == 'test-release':
        if who != 'server-astra' or item['state'] != 'blocked' or item['attempt'] >= 3:
            raise ValueError('사령탑만 환경 문제 해결 후 재개합니다')
        item['state']='pending'
    elif op == 'test-skip':
        if who != 'server-astra':
            raise ValueError('시험 제외는 사령탑이 사유를 확인해야 합니다')
        item['state']='skipped'
    else:
        raise ValueError('알 수 없는 시험 행동')
    item.update(summary=event['body'],updated_at=event.get('ts'))
    item['history'].append({k:copy.deepcopy(event.get(k)) for k in ('op','agent','ts','body','evidence')})
    return rows

def prompt(topic):
    if not topic.get('command_mode'): return ''
    import json
    return '''\n## 시험 세부 기록
plan JSON의 tests=[{id,title,assignee,depends_on:[],method,expected}]로 주제에 필요한 시험을 구체적으로 설계한다.
자동 시험은 환경 확인→정적 검사→빌드→핵심 동작/실패 경로→회귀/복구를 기본으로 하되 주제에 맞게 항목을 늘린다.
test 단계: command cmd=test-start,file=시험ID,body=실행할 명령·환경·통과 기준을 먼저 제출한다.
다음 실행에서 실제 시험 후 cmd=test-pass 또는 test-fail,file=시험ID,body=관찰 결과·원인·다음 조치,
options=[자기 작업물 폴더의 실제 로그 경로]로 기록한다. 진행은 test-progress, 환경 문제는 test-blocked로 보고한다.
test-pass는 검수 대기이며 사령탑이 근거를 읽고 test-accept 또는 test-revise로 판단하기 전에는 다음 시험으로 넘어가지 않는다.
실패는 수정 후 test-start로 재시험한다. blocked는 사령탑이 원인을 해결하고 test-release로 재개하거나 test-reassign,to=개발작업자로 재배정한다. 제외는 서버컴 Astra에 request로 사유를 보내고 Astra만 test-skip한다.
세 번 실패한 시험은 단순 release로 반복하지 않는다. 사령탑이 test-replan,file=시험ID,body=JSON {reason:"원인 분석",method:"기존과 다른 시험 방법"}으로 기록을 보존하고 새 시도를 연다.
실게임 반려로 시험 단계에 돌아왔으면 사령탑이 test-reset으로 기록을 보존하며 재시험을 열어야 한다.
모든 필수 시험 통과 전에는 state done 금지. 단순 실행·빌드 성공을 실제 동작 통과로 기록하지 않는다.
''' + json.dumps(topic.get('command',{}).get('tests',[]),ensure_ascii=False)
