// 합성 데이터만 사용. 외부 API 요청을 차단하고 Chromium에서 실제 UI/뒤로 가기를 검사한다.
const fs = require('fs'), path = require('path'), http = require('http'), assert = require('assert');
const { chromium } = require('playwright');
const root = path.resolve(__dirname, '..', 'docs');
const out = path.resolve(process.env.UI_OUTPUT || path.join(__dirname, '..', '..', 'ui-evidence'));
fs.mkdirSync(out, { recursive: true });
const ts = new Date().toISOString();
const task = { id:'code',title:'시험 기능 구현',scope:'대상 파일 수정',done_when:'실패 경로 검사 통과',assignee:'dev-claude',depends_on:[],state:'ready',attempt:1,feedback:'',result:null };
const topics = Array.from({length:18},(_,i)=>({ id:`T-20261003-${String(i).padStart(6,'0')}`,title:`시험 주제 ${i+1}`,body:'기능의 목표와 원하는 결과',kind:'기능·개선',priority:'P2',status:'active',assignee:'server-astra',commander:'server-astra',command_mode:true,stage:'work',turn:'dev-claude',notes:[],command:{version:1,revision:1,tasks:[task],events:[],rejected:[]},created_at:ts,updated_at:ts }));
topics.push({...topics[0],id:'T-20261003-aaaaaa',title:'재시작 전 기록',status:'parked',archived:true,restarted_as:topics[0].id,turn:null});
topics.push({...topics[0],id:'T-20261003-bbbbbb',title:'보류한 아이디어',status:'parked',turn:null});
topics.push({...topics[0],id:'T-20261003-cccccc',title:'완료한 개선',status:'done',turn:null});
topics.push({...topics[0],id:'T-20261003-dddddd',title:'다음 시즌 아이디어',status:'backlog',turn:null,command:{tasks:[]}});
topics.push({...topics[0],id:'T-20261003-eeeeee',title:'새 목표 정리',command:{tasks:[]},turn:'server-astra'});
topics.push({...topics[0],id:'T-20261003-ffffff',title:'구현 결과 검수',command:{tasks:[{...task,state:'review'}]},turn:'server-astra'});
// 배열 필드가 빠진 기록(depends_on·evidence 없음)도 화면이 깨지지 않아야 한다
topics.push({...topics[0],id:'T-20261003-ffff01',title:'필드 누락 기록',command:{tasks:[{...task,depends_on:undefined,state:'accepted',result:{summary:'근거 목록 없는 제출'}}],tests:[{id:'x',title:'선행 없음 시험',state:'pending'}]},stage:'test',turn:'dev-claude'});
const checks=['격리 환경 확인','정적 검사','빌드','거래 실패 경로','회귀·복구'].map((title,i)=>({id:`check${i}`,title,assignee:'dev-claude',method:'격리 fixture에서 실제 명령 실행',expected:'오류 0, 거래 잔액 보존',depends_on:i?[`check${i-1}`]:[],state:i<3?'passed':i===3?'failed':'pending',attempt:i<4?1:0,started_at:ts,updated_at:ts,summary:i===3?'동시 거래 충돌을 확인했습니다. 잠금 범위를 수정하고 재시험합니다.':'검사 결과 기록',evidence:[],history:[]}));
for(const [i,stage] of ['test','pack','prep','queue','deploy'].entries())topics.push({...topics[0],id:`T-20261003-aaa00${i}`,title:{test:'거래소 동시 거래 검사',pack:'아이콘 패치 묶음',prep:'서버 수신 확인',queue:'다음 점검에 반영할 개선',deploy:'10월 점검 묶음'}[stage],stage,command:{tasks:[{...task,state:'accepted'}],tests:checks},turn:stage==='test'?'dev-claude':stage==='queue'?null:'server-astra'});
const parent={...topics[0],id:'T-20261003-aaa005',title:'보상 구조 조사',status:'done',followed:true,body:'보상 중복을 막을 방법 조사',gate_history:[{choice:'후속 구현',note:'주간 보상부터 진행',answered_at:ts,summary:'중복 지급 경로를 확인했습니다.'}]};topics.push(parent);
// 결재 대기 ★4(답 안 보냄) · 답 보냄·반영 대기 ★5 · 배포 묶음 ★9(답 안 보냄)
topics.push({...topics[0],id:'T-20261003-aaa006',title:'주간 보상 후속 구현',status:'review_user',turn:null,gate:{id:'G4-aaa006',n:4,label:'실게임 시험',opened_at:ts,options:['통과','문제 있음']},prior_context:[{...parent,goal:parent.body,decisions:parent.gate_history,work_id:'FT-20261003-aaa005'}]});
topics.push({...topics[0],id:'T-20261003-aaa007',title:'배포본 결정 답함',status:'review_user',turn:null,gate:{id:'G5-aaa007',n:5,label:'배포본 결정',opened_at:ts,options:['배포본 만들기','보류']}});
topics.push({...topics[0],id:'T-20261003-aaa008',title:'10월 묶음 배포 끝남',status:'review_user',stage:'deploy',turn:null,deploy_batch:{id:'R-20261010',date:'2026-10-10'},gate:{id:'G9-aaa008',n:9,label:'완료 확정',batch:'R-20261010',opened_at:ts,summary:'배포 완료 · 적용 후 확인 통과',options:['완료 확정','배포 실패·되돌림']}});
const gateQ=(t,n,label)=>({id:t.gate.id,kind:'gate',gate:n,owner:'user',task_id:t.id,since:ts,_author:'server-astra',question:`[${n}/9 ${label}] ${t.title}\n\n${t.gate.summary||'결과 요약'}`,options:t.gate.options});
const byId=id=>topics.find(t=>t.id===id);
const decisions_needed=[gateQ(byId('T-20261003-aaa006'),4,'실게임 시험'),gateQ(byId('T-20261003-aaa007'),5,'배포본 결정'),gateQ(byId('T-20261003-aaa008'),9,'완료 확정')];
const decisions_answered=[{id:'G5-aaa007',choice:'배포본 만들기',note:'',ts}];
const fixture={meta:{project:'REAL 작업실',generated_at:ts,limits:{},repo:'fixture/offline',hub:'dev',coordination:{lead:'server-astra'},routing:{},command_epoch:'astra-20261003-v1'},tasks:[],topics,messages:[],sources:[{id:'s1',name:'작업표',ok:true,count:3,last_modified:ts},{id:'s2',name:'수신함',ok:false,error:'경로 없음',count:0}],validations:[],ledger:[],memory:[],decisions:[],decisions_needed,decisions_answered,user_actions:[],comments:[],works:{},handoffs:[],agents:['server-astra','dev-claude','dev-astra','server-claude'].map(id=>({id,label:id.endsWith('astra')?'Astra':'Claude',pc:id.split('-')[0],pc_label:id.startsWith('server')?'서버컴':'개발컴',ai:id.endsWith('astra')?'gpt':'claude',last_seen:ts})),runs:[],holds:[],notices:[]};
const server=http.createServer((req,res)=>{
 const file=path.resolve(root,'.'+decodeURIComponent(req.url.split('?')[0]==='/'?'/index.html':req.url.split('?')[0]));
 if(!file.startsWith(root+path.sep)||!fs.existsSync(file)){res.writeHead(404);res.end();return;}
 res.setHeader('Content-Type',file.endsWith('.js')?'application/javascript':file.endsWith('.css')?'text/css':file.endsWith('.html')?'text/html':'application/octet-stream');res.end(fs.readFileSync(file));
});
// 주 메뉴 이름(배지 숫자 제외)
const navNames=page=>page.locator('.side > .nav-btn').evaluateAll(els=>els.map(e=>[...e.childNodes].filter(n=>n.nodeType===3).map(n=>n.textContent).join('').trim()));
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const port=server.address().port;
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const errors=[];const page=await browser.newPage({viewport:{width:1440,height:1000}});
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',route=>route.request().url().startsWith(`http://127.0.0.1:${port}/`)?route.continue():route.abort());
 const done=[];
 try{
  await page.goto(`http://127.0.0.1:${port}/`);
  await page.evaluate(data=>{S.data=data;S.view='progress';enterApp();clearInterval(S.timer);},fixture);
  assert.equal(await page.locator('.flow-lane').count(),11);
  await page.getByRole('button',{name:'자동 시험 2건 보기',exact:true}).click();
  assert.equal(await page.locator('.flow-lane').count(),1);
  assert.equal(await page.locator('.flow-lane').getAttribute('data-stage'),'test');
  await page.getByRole('button',{name:'전체 단계',exact:true}).click();
  assert(await page.getByRole('heading',{name:'막힘·응답 대기 1건'}).count());
  // 막힘 카드에는 같은 자리 행동 버튼이 있다
  assert(await page.locator('.blocked-row').getByRole('button',{name:'시험 결과 보기',exact:true}).count());
  await page.locator('.flow-lane[data-stage="test"] .command-card').filter({hasText:'거래소 동시 거래 검사'}).click();
  await page.waitForSelector('.drawer.on');
  assert(await page.locator('.drawer .test-item.failed').count());
  assert.equal(await page.locator('.drawer .test-item.review').count(),3);
  assert((await page.locator('.drawer .test-box').textContent()).includes('Astra 검수 대기'));
  assert.equal(await page.evaluate(()=>testHeadline({stage:'test',command:{tests:[{state:'passed',title:'검사'}]}})), '시험 0/1 통과 · 검사: 통과 · Astra 검수 대기');
  assert.equal(await page.evaluate(()=>testHeadline({stage:'test',command:{tests:[{state:'passed',title:'검사',accepted_by:'server-astra'}]}})), '시험 1/1 통과 · 결과 정리');
  assert((await page.locator('.drawer .test-box').textContent()).includes('잠금 범위를 수정하고 재시험'));
  await page.locator('.drawer .test-box').screenshot({path:path.join(out,'test-detail.png')});
  await page.goBack();await page.waitForFunction(()=>!document.querySelector('.drawer'));
  // 배열 필드가 빠진 주제 상세도 오류 없이 열린다
  await page.locator('.flow-lane[data-stage="test"] .command-card').filter({hasText:'필드 누락 기록'}).click();
  await page.waitForSelector('.drawer.on .command-box');
  await page.goBack();await page.waitForFunction(()=>!document.querySelector('.drawer'));
  await page.locator('.flow-lane[data-stage="decision"] .command-card').filter({hasText:'주간 보상 후속 구현'}).click();
  await page.waitForSelector('.drawer.on');
  assert((await page.locator('.drawer .prior-context').textContent()).includes('주간 보상부터 진행'));
  await page.locator('.drawer .prior-context').screenshot({path:path.join(out,'followup-history.png')});
  await page.getByRole('button',{name:'이전 주제·시험 근거·전체 기록 열기',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('.drawer h3')?.textContent==='보상 구조 조사');
  await page.goBack();await page.waitForFunction(()=>!!document.querySelector('.drawer .prior-context'));
  await page.goBack();await page.waitForFunction(()=>!document.querySelector('.drawer'));
  assert.deepEqual(await navNames(page),['결재함','진행 현황','배포','기록']);

  // [P1-1] 결재 건수: 위쪽 버튼 · 사이드바 배지 · 진행 현황 · 결재함이 같은 기준(답 안 보낸 ★4·★9 = 2건, 답 보냄 ★5는 따로 1건)
  assert.equal(await page.locator('.top .mine-btn[data-approvals]').getAttribute('data-approvals'),'2');
  assert.equal((await page.locator('.top .mine-btn[data-approvals]').textContent()).trim(),'결재 2');
  assert.equal((await page.locator('.side > .nav-btn').first().locator('.badge').textContent()).trim(),'2');
  assert(await page.getByRole('heading',{name:'결재할 일 2건',exact:true}).count());
  assert(((await page.locator('.ps-wait').textContent())||'').includes('답 보냄 · 반영 대기 1건'));
  assert.equal(await page.evaluate(()=>approvals().total),2);
  await page.evaluate(()=>go('mine'));
  assert((await page.locator('.page-head h1 small').textContent()).includes('대응할 것 2건'));
  assert.equal(await page.locator('.mine-row').count(),2);  // ★ 관문 2(사령탑 전환 뒤에는 착수 고르기 목록 없음)
  await page.evaluate(()=>go('progress'));
  // 이미 답을 보낸 결정은 다시 보낼 수 없다
  assert.equal(await page.evaluate(async()=>decide(S.data.decisions_needed.find(q=>q.id==='G5-aaa007'),'보류','')),false);
  done.push('결재 건수 일치(위쪽·사이드바·진행 현황·결재함)','보낸 결정 다시 보내기 차단');

  await page.locator('.progress-search').fill('시험 주제');
  await page.getByRole('button',{name:'15건 더 보기',exact:true}).click();
  await page.evaluate(()=>window.scrollTo(0,450));
  const scroll=await page.evaluate(()=>window.scrollY);
  await page.locator('.command-card').nth(7).evaluate(el=>el.click());
  await page.waitForSelector('.drawer.on');
  await page.getByRole('textbox',{name:'답 입력',exact:true}).fill('반려 의견 초안');
  await page.goBack();
  await page.waitForFunction(()=>!document.querySelector('.drawer'));
  assert.equal(await page.locator('.progress-search').inputValue(),'시험 주제');
  await page.waitForFunction(y=>Math.abs(window.scrollY-y)<2,scroll);
  await page.goForward();
  await page.waitForSelector('.drawer.on');
  assert.equal(await page.getByRole('textbox',{name:'답 입력',exact:true}).inputValue(),'반려 의견 초안');
  await page.getByRole('button',{name:'이전 화면',exact:true}).click();
  await page.waitForFunction(()=>!document.querySelector('.drawer'));
  await page.getByRole('button',{name:'기록',exact:true}).click();
  await page.getByRole('button',{name:'재시작 전',exact:true}).click();
  assert(await page.getByRole('button',{name:/재시작 전 기록/}).count());
  assert(await page.evaluate(()=>parkedBox(S.d.topics.find(t=>t.archived)) === null));
  assert(await page.evaluate(()=>testBox({command:{tests:[{id:'x',title:'대행 시험',state:'passed',accepted_by:'dev-claude',accepted_acting_for:'server-astra',assignee:'dev-astra'}]}}).textContent.includes('개발컴 대행 검수')));
  await page.goBack();await page.waitForSelector('.progress-search');
  assert.equal(await page.locator('.progress-search').inputValue(),'시험 주제');
  // 검색어는 초안으로 저장하지 않는다(새로 고친 뒤 칸과 목록이 어긋나지 않게)
  assert.equal(await page.evaluate(()=>localStorage.getItem('realops.draft:progress-search')),null);

  // [P1-2] 기록 메뉴에서 완료(줄기·관문 이력·기간 칩) · 보류(다시 진행) · 전체 요약(완료율·팀 현황)에 닿는다
  await page.evaluate(()=>{S.f.progressQ='';S.f['expand:execute']=false;go('progress');});
  await page.getByRole('button',{name:'기록',exact:true}).click();
  await page.locator('.rec-bar').getByRole('button',{name:'완료',exact:true}).click();
  assert(await page.getByRole('group',{name:'완료 기간'}).count());
  assert(await page.locator('.done-row').filter({hasText:'완료한 개선'}).count());
  await page.locator('.rec-bar').getByRole('button',{name:'보류',exact:true}).click();
  assert.equal(await page.locator('.done-row').filter({hasText:'재시작 전 기록'}).count(),0);
  await page.locator('.done-row summary').filter({hasText:'보류한 아이디어'}).click();
  assert(await page.getByRole('button',{name:'다시 진행',exact:true}).count());
  await page.locator('.rec-bar').getByRole('button',{name:'전체 요약',exact:true}).click();
  assert(await page.locator('.ov-fit').count());
  assert(await page.getByRole('heading',{name:'완료율'}).count());
  assert(await page.getByRole('heading',{name:'팀 현황'}).count());
  assert.equal(await page.locator('.side > .nav-btn[aria-current="page"]').evaluate(e=>[...e.childNodes].filter(n=>n.nodeType===3).map(n=>n.textContent).join('').trim()),'기록');
  // 진행 현황의 '보류 N건'도 같은 보류 화면(다시 진행 버튼)으로
  await page.evaluate(()=>go('progress'));
  await page.locator('.page-head').getByRole('button',{name:'보류 1건',exact:true}).click();
  assert.equal(await page.locator('.done-row').filter({hasText:'재시작 전 기록'}).count(),0);
  await page.locator('.done-row summary').filter({hasText:'보류한 아이디어'}).click();
  assert(await page.getByRole('button',{name:'다시 진행',exact:true}).count());
  assert.equal(await page.evaluate(()=>S.view+':'+S.f.recordKind),'history:parked');
  // 결재함 요약 칩 '보류'도 같은 곳
  await page.evaluate(()=>go('mine'));
  await page.locator('.mine-summary').getByRole('button',{name:/^보류/}).click();
  assert.equal(await page.evaluate(()=>S.view+':'+S.f.recordKind),'history:parked');
  // 배포 메뉴는 배포 대기열 그대로(묶음 만들기 · 서버컴 Astra 대화 시작 문구 복사 · ★9 묶음 완료 확정)
  await page.getByRole('button',{name:'배포',exact:true}).click();
  assert(await page.getByRole('button',{name:'배포 묶음 만들기',exact:true}).count());
  assert(await page.getByRole('button',{name:'서버컴 Astra 대화 시작 문구 복사',exact:true}).count());
  done.push('기록 → 완료(기간 칩)','기록 → 보류(다시 진행)','기록 → 전체 요약','진행 현황·결재함 보류 → 같은 보류 화면','배포 대기열 메뉴');

  // [P1-3] 확인창은 뒤로/앞으로로 되살아나지 않는다
  await page.getByRole('button',{name:'★9 묶음 완료 확정 1건',exact:true}).click();
  await page.waitForSelector('.drawer.on');
  await page.goBack();await page.waitForFunction(()=>!document.querySelector('.drawer'));
  await page.goForward();await page.waitForTimeout(400);
  assert.equal(await page.locator('.drawer').count(),0);
  assert.equal(await page.evaluate(()=>S.view),'deploy');
  await page.getByRole('button',{name:'배포 묶음 만들기',exact:true}).click();
  await page.waitForSelector('.drawer.on');
  await page.goBack();await page.waitForFunction(()=>!document.querySelector('.drawer'));
  await page.goForward();await page.waitForTimeout(400);
  assert.equal(await page.locator('.drawer').count(),0);
  // 닫기·Esc 연타는 한 칸만: 진행 현황 → 배포 → 주제 상세에서 Esc 두 번 → 배포에 머문다
  await page.evaluate(()=>go('progress'));
  await page.evaluate(()=>go('deploy'));
  await page.locator('.link-btn').filter({hasText:'다음 점검에 반영할 개선'}).first().click();
  await page.waitForSelector('.drawer.on');
  // 같은 순간 두 번(뒤로 가기가 끝나기 전에 두 번째 Esc가 들어오는 연타)
  await page.evaluate(()=>{const k=()=>(document.activeElement||document.body).dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',code:'Escape',bubbles:true}));k();k();});
  await page.waitForFunction(()=>!document.querySelector('.drawer'));await page.waitForTimeout(400);
  assert.equal(await page.evaluate(()=>S.view+' '+location.hash),'deploy #/deploy');
  await page.goBack();await page.waitForFunction(()=>S.view==='progress');
  // 이전 화면 버튼 연타도 한 칸만
  await page.evaluate(()=>go('deploy'));
  await page.locator('.link-btn').filter({hasText:'다음 점검에 반영할 개선'}).first().click();
  await page.waitForSelector('.drawer.on');
  await page.evaluate(()=>{const b=document.querySelector('.drawer .drawer-h button');b.click();b.click();});
  await page.waitForFunction(()=>!document.querySelector('.drawer'));await page.waitForTimeout(400);
  assert.equal(await page.evaluate(()=>S.view),'deploy');
  // 이 앱의 첫 화면에서 연 창: 닫아도 사이트 밖으로 나가지 않는다(back 대신 같은 자리 기록 교체)
  await page.locator('.link-btn').filter({hasText:'다음 점검에 반영할 개선'}).first().click();
  await page.waitForSelector('.drawer.on');
  await page.evaluate(()=>history.replaceState({realops:screenId,depth:0},'',location.href));
  await page.evaluate(()=>{closeDrawer();closeDrawer();});
  await page.waitForTimeout(400);
  assert.equal(await page.locator('.drawer').count(),0);
  assert(await page.evaluate(p=>location.href.startsWith(`http://127.0.0.1:${p}/`)&&S.view==='deploy',port));
  // 해시를 직접 바꾼 방문은 한 번만 그리고 화면 식별값을 남긴다
  const renders=await page.evaluate(async()=>{let n=0;const o=render;window.render=render;render=function(){n++;return o.apply(this,arguments);};location.hash='#/history';await new Promise(r=>setTimeout(r,300));render=o;return {n,state:!!history.state?.realops,view:S.view};});
  assert.deepEqual(renders,{n:1,state:true,view:'history'});
  done.push('★9 묶음 확인창 뒤로/앞으로 복원 안 됨','묶음 만들기 창 복원 안 됨','Esc 연타 한 칸만','이전 화면 버튼 연타 한 칸만','첫 화면에서 닫기 사이트 이탈 없음','해시 이동 한 번만 렌더');

  for(const view of ['mine','progress','deploy','history','agents','sources','messages','verify','brain','tasks','topics','parked','done','overview']){
   await page.evaluate(v=>go(v),view);await page.waitForTimeout(40);
  }
  // 사이드바: 출처 상태 줄 · 접힌 관리 합계 배지(연결 이상 1)
  assert((await page.locator('.side-src').textContent()).includes('출처 2곳'));
  assert.equal((await page.locator('.side-admin > summary .badge').textContent()).trim(),'1');
  await page.evaluate(()=>{S.f.progressQ='';S.f.flowStage='all';S.f['expand:execute']=false;go('progress');window.scrollTo(0,0);});
  // 데스크톱 1440×1000: 진행 현황이 한 화면에 들어온다
  const fit=await page.evaluate(()=>({h:document.documentElement.scrollHeight,vh:innerHeight}));
  assert(fit.h<=fit.vh,`진행 현황 높이 ${fit.h}px > ${fit.vh}px`);
  await page.screenshot({path:path.join(out,'desktop.png'),fullPage:false});
  await page.locator('.full-flow').screenshot({path:path.join(out,'flow-board.png')});
  await page.setViewportSize({width:390,height:844});
  await page.evaluate(()=>go('progress'));
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.screenshot({path:path.join(out,'mobile.png'),fullPage:false});
  assert.deepEqual(errors,[]);
  const result={pass:true,checks:['주 메뉴 4개','9단계와 보관/완료 위치','단계 막대 클릭 필터','병목 및 실패 시험 상세·행동 버튼','배열 필드 누락 방어','후속작업 이전 결정 문맥','중첩 상세 뒤로 가기','작업 상세 뒤로/앞으로','스크롤 위치 보존','의견 초안 보존','메뉴 뒤로 가기 검색 보존','검색어 초안 저장 안 함','재시작 이력 접근','재시작 보관은 보류 수·목록·재개에서 제외','시험 대행 검수 표시',...done,'14개 화면 렌더','사이드바 출처 줄·관리 배지','데스크톱 진행 현황 한 화면','모바일 가로 넘침 없음'],errors,initialScroll:scroll,desktopHeight:fit};
  fs.writeFileSync(path.join(out,'result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }finally{await browser.close();server.close();}
})().catch(e=>{console.error(e);server.close();process.exitCode=1;});
