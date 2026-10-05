// Synthetic encrypted repository only. No live data, credentials, or external writes.
const fs = require('node:fs'), path = require('node:path'), http = require('node:http');
const assert = require('node:assert/strict'), crypto = require('node:crypto'), zlib = require('node:zlib');
const { chromium } = require('playwright');
const root = path.resolve(__dirname, '../docs');
const out = path.resolve(process.env.UI_OUTPUT || path.join(__dirname, '../.local/screening-evidence'));
const salt = Buffer.alloc(16, 7).toString('base64'), password = 'synthetic-screening-test';
const key = crypto.pbkdf2Sync(password, Buffer.from(salt, 'base64'), 1000, 32, 'sha256');
const stamp = '2026-10-05T00:00:00.000Z';
const make = (id, status) => ({ id, status, title: '안건 ' + id, detail: '검토 내용 ' + id, area: id === 'B' ? '클라이언트' : '서버', priority: 'normal', created: stamp, updated: stamp, log: [{at: stamp, by: 'claude', text: '메모 ' + id}] });
function seal(tasks) {
  const iv = crypto.randomBytes(12), c = crypto.createCipheriv('aes-256-gcm', key, iv);
  const data = Buffer.concat([c.update(zlib.gzipSync(Buffer.from(JSON.stringify({v:1,tasks})))), c.final(), c.getAuthTag()]);
  return {v:1, alg:'AES-256-GCM', kdf:'PBKDF2-SHA256', iter:1000, gzip:true, salt, iv:iv.toString('base64'), data:data.toString('base64')};
}
function unseal(env) {
  const bytes = Buffer.from(env.data, 'base64'), d = crypto.createDecipheriv('aes-256-gcm', key, Buffer.from(env.iv, 'base64'));
  d.setAuthTag(bytes.subarray(-16));
  return JSON.parse(zlib.gunzipSync(Buffer.concat([d.update(bytes.subarray(0,-16)),d.final()]))).tasks;
}
let tasks = [make('A','todo'),make('B','screening'),make('C','screening'),make('D','doing'),{...make('X','screening'),deleted:stamp}];
let env = seal(tasks), revision = 0, conflict = true, writes = 0;
const server = http.createServer((req,res) => {
  const name = new URL(req.url, 'http://localhost').pathname.slice(1) || 'index.html';
  if (!['index.html','sched.js','sched.css','brand-mark.png','favicon.ico'].includes(name)) {res.writeHead(404).end();return;}
  let data = fs.readFileSync(path.join(root,name));
  if (name === 'sched.js') data = data.toString().replace(/boot\(\);\s*$/, '');
  res.setHeader('Content-Type', name.endsWith('.js') ? 'text/javascript' : name.endsWith('.css') ? 'text/css' : name.endsWith('.html') ? 'text/html' : 'image/png');
  res.end(data);
});
(async () => {
  fs.mkdirSync(out,{recursive:true});
  await new Promise(resolve => server.listen(0,'127.0.0.1',resolve));
  const browser = await chromium.launch({channel:'msedge',headless:true});
  const context = await browser.newContext({viewport:{width:1440,height:1000},permissions:['clipboard-read','clipboard-write']});
  const page = await context.newPage(), errors = [];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*', async route => {
    const request = route.request(), url = request.url();
    if (url.startsWith('http://127.0.0.1:')) return route.continue();
    if (!url.startsWith('https://api.github.com/repos/hati0101/dash/contents/docs/')) return route.abort();
    if (!url.includes('/sched.enc.json')) return route.fulfill({status:404,body:'{}'});
    if (request.method() === 'PUT') {
      if (conflict) {
        conflict = false; tasks.find(t=>t.id==='A').detail = '다른 기기 수정 보존'; env=seal(tasks); revision++;
        return route.fulfill({status:409,body:'{}'});
      }
      const payload=request.postDataJSON(); assert.equal(payload.sha,String(revision));
      env=JSON.parse(Buffer.from(payload.content,'base64')); tasks=unseal(env); revision++; writes++;
      return route.fulfill({json:{content:{sha:String(revision)}}});
    }
    return route.fulfill({json:{sha:String(revision),content:Buffer.from(JSON.stringify(env)).toString('base64')}});
  });
  const ready = async () => {
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.evaluate(async ({salt,password}) => {S.env={salt,iter:1000};S.key=await deriveKey(password,salt,1000,false);await tokenSet('fixture-token');await enter();},{salt,password});
  };
  const saved = () => page.waitForFunction(()=>!S.saving && !S.queue.length);
  try {
    await ready();
    await page.getByRole('button',{name:'안건 A 선별로 이동',exact:true}).click(); await saved();
    assert.equal(tasks.find(t=>t.id==='A').status,'screening');
    assert.equal(tasks.find(t=>t.id==='A').detail,'다른 기기 수정 보존');
    await page.locator('#side .nav').filter({hasText:/^선별/}).click();
    await page.screenshot({path:path.join(out,'screening-list.png')});
    await page.getByRole('searchbox',{name:'검색',exact:true}).fill('안건 B');
    await page.getByRole('button',{name:'선별 전체 복사 (3건)',exact:true}).click();
    let copied = await page.evaluate(()=>navigator.clipboard.readText());
    for (const id of ['A','B','C']) assert(copied.includes('ID: '+id));
    for (const id of ['D','X']) assert(!copied.includes('ID: '+id));
    assert(copied.includes('메모 B') && copied.includes('최종 결정은 아키텍트'));
    await page.getByRole('searchbox',{name:'검색',exact:true}).fill('');
    await page.getByRole('button',{name:'안건 B 선별 판단',exact:true}).click();
    await page.getByLabel('필요성',{exact:true}).fill('불편을 해결합니다');
    await page.getByLabel('추천',{exact:true}).selectOption('doing'); await saved();
    assert.equal(tasks.find(t=>t.id==='B').status,'screening');
    await page.getByLabel('판단 근거',{exact:true}).fill('사용 빈도가 높습니다');
    await page.getByLabel('판단 근거',{exact:true}).blur();
    await page.waitForFunction(()=>find(S.tasks,'B').screenReason==='사용 빈도가 높습니다'); await saved();
    const packet = await page.evaluate(()=>screeningText(screeningTasks()));
    for (const text of ['불편을 해결합니다','사용 빈도가 높습니다','추천: 진행','메모 B']) assert(packet.includes(text));
    assert(!packet.includes('fixture-token'));
    assert(await page.evaluate(()=>screeningText(Array.from({length:100},(_,i)=>({...find(S.tasks,'B'),id:'LONG-'+i,detail:'본문'.repeat(1000)}))).includes('ID: LONG-99')));
    await page.screenshot({path:path.join(out,'desktop-screening.png')});
    for (const [width,height,theme] of [[375,812,'dark'],[375,812,'light'],[812,375,'light']]) {
      await page.setViewportSize({width,height});
      await page.emulateMedia({reducedMotion:'reduce'});
      await page.evaluate(theme=>document.documentElement.dataset.theme=theme,theme);
      const overflow = await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,items:[...document.querySelectorAll('body *')].filter(el=>el.getBoundingClientRect().right>innerWidth+1).map(el=>({tag:el.tagName,cls:el.className,w:el.getBoundingClientRect().width})).slice(0,15)}));
      await page.screenshot({path:path.join(out,`screening-${width}-${theme}.png`)});
      assert(overflow.scroll<=overflow.width,JSON.stringify(overflow));
      assert(await page.locator('.e-card').evaluate(el=>el.scrollWidth<=el.clientWidth),'modal overflow');
      await page.screenshot({path:path.join(out,`screening-${width}-${theme}.png`)});
    }
    await page.setViewportSize({width:1440,height:1000});
    await page.getByRole('button',{name:'진행으로',exact:true}).click(); await saved();
    assert.equal(tasks.find(t=>t.id==='B').status,'doing');
    await page.getByRole('button',{name:'닫기',exact:true}).click();
    await ready();
    const b=await page.evaluate(()=>find(S.tasks,'B'));
    assert.equal(b.screenNeed,'불편을 해결합니다'); assert.equal(b.screenReason,'사용 빈도가 높습니다');
    assert.equal(b.screenRecommend,'doing'); assert(b.stages.doing);
    await page.locator('#side .nav').filter({hasText:/^선별/}).click();
    await page.getByRole('button',{name:'안건 C 선별 판단',exact:true}).click();
    await page.locator('.screen-decisions').getByRole('button',{name:'제외',exact:true}).click(); await saved();
    assert.equal(tasks.find(t=>t.id==='C').status,'excluded'); assert(!tasks.find(t=>t.id==='C').deleted);
    await page.getByRole('button',{name:'닫기',exact:true}).click();
    await page.getByRole('button',{name:'안건 A 선별 판단',exact:true}).click();
    await page.locator('.screen-decisions').getByRole('button',{name:'보류',exact:true}).click(); await saved();
    assert.equal(tasks.find(t=>t.id==='A').status,'hold');
    await page.getByRole('button',{name:'닫기',exact:true}).click();
    assert(await page.getByRole('button',{name:'선별 전체 복사 (0건)',exact:true}).isDisabled());
    // Existing shortcut 2 still means doing; newly assigned 6 means screening.
    await page.evaluate(()=>{S.focus='A';}); await page.keyboard.press('6'); await saved();
    assert.equal(tasks.find(t=>t.id==='A').status,'screening');
    await page.keyboard.press('2'); await saved(); assert.equal(tasks.find(t=>t.id==='A').status,'doing');
    await page.evaluate(()=>{S.sel=new Set(['A','B']);renderBulk();});
    await page.locator('#bulk').getByRole('button',{name:'선별',exact:true}).click(); await saved();
    assert.equal(tasks.filter(t=>t.status==='screening'&&!t.deleted).length,2);
    assert.equal(errors.length,0,errors.join('\n')); assert(writes>=5);
    console.log('PASS: screening transition, conflict retry, copy all despite search, recommendation does not start work, decisions, encrypted reload, retained excluded items, 375px/landscape light/dark layout, empty state.');
  } finally {await browser.close();server.close();}
})().catch(e=>{console.error(e);server.close();process.exitCode=1;});
