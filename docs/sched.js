'use strict';
/* REAL 작업실 — 스케줄러. 데이터는 docs/sched.enc.json(대시보드 비밀번호로 암호화).
   저장은 GitHub API로 그 파일을 바로 커밋한다(토큰: 이 기기에만 암호화 보관). 다른 기기 변경은 20초마다 확인. */
const REPO = 'hati0101/dash', PATH = 'docs/sched.enc.json', BRANCH = 'main';
const API = `https://api.github.com/repos/${REPO}/contents/${PATH}`;
const STATUS = [
  { k: 'todo', name: '대기', c: 'var(--todo)' },
  { k: 'doing', name: '진행 중', c: 'var(--doing)' },
  { k: 'review', name: '확인 대기', c: 'var(--review)' },
  { k: 'hold', name: '보류', c: 'var(--hold)' },
  { k: 'done', name: '완료', c: 'var(--done)' },
];
const SMAP = Object.fromEntries(STATUS.map(s => [s.k, s]));
const PRI = { high: '높음', normal: '보통', low: '낮음' };
const DAYS = ['일', '월', '화', '수', '목', '금', '토'];
const S = { env: null, key: null, sha: null, remote: [], tasks: [], queue: [], saving: false, syncText: '', syncErr: false,
  q: '', day: null, area: null, weekOff: 0, open: null, quick: false, showDone: 12, showHold: 20, token: null };

// ---------- 유틸
const $ = s => document.querySelector(s);
const store = {
  get(k, d = null) { try { const v = localStorage.getItem('realops.' + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem('realops.' + k, JSON.stringify(v)); } catch { /* 저장 불가 */ } },
  del(k) { try { localStorage.removeItem('realops.' + k); } catch { /* 무시 */ } },
};
function h(tag, a, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(a || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v; else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'css') for (const [p, x] of Object.entries(v)) el.style.setProperty(p, x);
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const c of kids.flat(Infinity)) if (c != null && c !== false) el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return el;
}
const pad = n => String(n).padStart(2, '0');
const ymd = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const todayStr = () => ymd(new Date());
const clone = x => JSON.parse(JSON.stringify(x));
function dueLabel(due) {
  if (!due) return null;
  const d = new Date(due + 'T00:00'); if (isNaN(d)) return null;
  const diff = Math.round((d - new Date(todayStr() + 'T00:00')) / 864e5);
  return { txt: diff === 0 ? '오늘' : diff === 1 ? '내일' : diff === -1 ? '어제' : `${d.getMonth() + 1}/${d.getDate()}(${DAYS[d.getDay()]})`, cls: diff < 0 ? 'late' : diff === 0 ? 'today' : '' };
}
function when(iso) {
  if (!iso) return '';
  const d = new Date(iso); if (isNaN(d)) return '';
  return ymd(d) === todayStr() ? `${pad(d.getHours())}:${pad(d.getMinutes())}` : `${d.getMonth() + 1}/${d.getDate()}`;
}
function toast(text, label, action, ms = 6000) {
  const btn = label ? h('button', { class: 'btn sm', type: 'button' }, label) : null;
  const t = h('div', { class: 'toast', role: 'status' }, h('span', null, text), btn);
  if (btn) btn.onclick = () => { action(); t.remove(); };
  $('#toasts').append(t); setTimeout(() => t.remove(), ms);
}
const isLate = t => t.status !== 'done' && t.status !== 'hold' && t.due && t.due < todayStr();
const newId = () => 'W-' + todayStr().replace(/-/g, '') + '-' + [...crypto.getRandomValues(new Uint8Array(3))].map(b => b.toString(16).padStart(2, '0')).join('');

// ---------- 암호 (기존 작업실과 같은 형식·같은 비밀번호)
const b64 = {
  dec(s) { s = s.replace(/-/g, '+').replace(/_/g, '/').replace(/\s/g, ''); while (s.length % 4) s += '='; const b = atob(s); const u = new Uint8Array(b.length); for (let i = 0; i < b.length; i++) u[i] = b.charCodeAt(i); return u; },
  enc(u8) { let s = ''; for (let i = 0; i < u8.length; i += 0x8000) s += String.fromCharCode(...u8.subarray(i, i + 0x8000)); return btoa(s); },
};
async function deriveKey(pw, salt, iter, extractable) {
  const base = await crypto.subtle.importKey('raw', new TextEncoder().encode(pw), 'PBKDF2', false, ['deriveKey']);
  return crypto.subtle.deriveKey({ name: 'PBKDF2', hash: 'SHA-256', salt: b64.dec(salt), iterations: iter }, base, { name: 'AES-GCM', length: 256 }, extractable, ['encrypt', 'decrypt']);
}
async function openEnv(env, key) {
  const pt = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: b64.dec(env.iv) }, key, b64.dec(env.data));
  let bytes = pt;
  if (env.gzip) bytes = await new Response(new Blob([pt]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer();
  return JSON.parse(new TextDecoder().decode(bytes));
}
async function sealEnv(obj) {
  const gz = await new Response(new Blob([new TextEncoder().encode(JSON.stringify(obj))]).stream().pipeThrough(new CompressionStream('gzip'))).arrayBuffer();
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, S.key, gz));
  return { v: 1, alg: 'AES-256-GCM', kdf: 'PBKDF2-SHA256', iter: S.env.iter, gzip: true, salt: S.env.salt, iv: b64.enc(iv), data: b64.enc(ct), published_at: new Date().toISOString() };
}
async function tokenGet() {
  const s = store.get('ghtoken'); if (!s || !S.key) return null;
  try { return new TextDecoder().decode(await crypto.subtle.decrypt({ name: 'AES-GCM', iv: b64.dec(s.iv) }, S.key, b64.dec(s.ct))); } catch { return null; }
}
async function tokenSet(tok) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, S.key, new TextEncoder().encode(tok)));
  store.set('ghtoken', { iv: b64.enc(iv), ct: b64.enc(ct), at: new Date().toISOString() });
}

// ---------- 저장소 (GitHub)
async function fetchRemote() {
  if (S.token) {
    const r = await fetch(`${API}?ref=${BRANCH}&t=${Date.now()}`, { headers: { Authorization: `Bearer ${S.token}`, Accept: 'application/vnd.github+json' }, cache: 'no-store' });
    if (!r.ok) throw Object.assign(new Error('GitHub ' + r.status), { status: r.status });
    const j = await r.json();
    return { sha: j.sha, env: JSON.parse(atob(j.content.replace(/\s/g, ''))) };
  }
  const r = await fetch('sched.enc.json?t=' + Date.now(), { cache: 'no-store' });
  if (!r.ok) throw new Error('데이터 파일을 받지 못했습니다 (' + r.status + ')');
  return { sha: null, env: await r.json() };
}
async function pull() {
  const { sha, env } = await fetchRemote();
  if (sha && sha === S.sha) return false;
  const data = await openEnv(env, S.key);
  S.sha = sha; S.remote = data.tasks || [];
  S.tasks = clone(S.remote); for (const op of S.queue) op.fn(S.tasks);
  return true;
}
function mutate(fn, msg) {
  fn(S.tasks);
  S.queue.push({ fn, msg });
  render(); flush();
}
async function flush() {
  if (S.saving || !S.queue.length) return;
  if (!S.token) { setSync('토큰이 없어 저장하지 못했습니다', true); return; }
  S.saving = true; setSync('저장 중…');
  let tries = 0;
  while (S.queue.length && tries < 4) {
    const ops = S.queue.slice();
    const next = clone(S.remote); for (const op of ops) op.fn(next);
    try {
      const env = await sealEnv({ v: 1, tasks: next });
      const r = await fetch(API, { method: 'PUT', headers: { Authorization: `Bearer ${S.token}`, Accept: 'application/vnd.github+json', 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: '작업실: ' + (ops.length === 1 ? ops[0].msg : ops[0].msg + ` 외 ${ops.length - 1}건`), content: btoa(JSON.stringify(env)), sha: S.sha || undefined, branch: BRANCH }) });
      if (r.status === 409 || r.status === 422) { tries++; await pull(); continue; }  // 다른 기기가 먼저 저장 — 최신본에 다시 적용
      if (!r.ok) {
        const why = r.status === 401 ? '토큰이 만료됐거나 틀렸습니다' : r.status === 403 || r.status === 404 ? '토큰에 이 저장소의 Contents 쓰기 권한이 없습니다' : 'GitHub ' + r.status;
        throw new Error(why);
      }
      const j = await r.json();
      S.sha = j.content.sha; S.remote = next; S.queue.splice(0, ops.length);
      S.tasks = clone(S.remote); for (const op of S.queue) op.fn(S.tasks);
      setSync('저장됨 ' + when(new Date().toISOString()));
    } catch (e) {
      setSync('저장 실패: ' + e.message, true); S.saving = false;
      if (/권한|토큰/.test(e.message)) showTokenBox(e.message);
      return;
    }
  }
  S.saving = false;
  render();
  if (S.queue.length) setTimeout(flush, 1500);
}
function setSync(t, err = false) { S.syncText = t; S.syncErr = err; const el = $('#sync'); if (el) { el.textContent = t; el.className = 'sync' + (err ? ' err' : ''); } }

// ---------- 작업 조작
const find = (list, id) => list.find(x => x.id === id);
function createTask(f) {
  const now = new Date().toISOString(), id = newId();
  const t = { id, title: f.title || '', detail: f.detail || '', status: f.status || 'todo', due: f.due || '', priority: f.priority || 'normal', area: f.area || '', log: [], created: now, updated: now };
  mutate(list => { if (!find(list, id)) list.push(clone(t)); }, `추가 "${t.title || '새 작업'}"`);
  return id;
}
function patchTask(id, patch, msg) {
  const now = new Date().toISOString();
  mutate(list => { const t = find(list, id); if (t) Object.assign(t, clone(patch), { updated: now }); }, msg || '수정');
}
function setStatus(id, k) {
  const t = find(S.tasks, id); if (!t || t.status === k) return;
  patchTask(id, { status: k }, `"${t.title}" → ${SMAP[k].name}`);
}
function removeTask(id) {
  const t = find(S.tasks, id); if (!t) return;
  const saved = clone(t);
  if (S.open === id) closeDrawer();
  mutate(list => { const i = list.findIndex(x => x.id === id); if (i >= 0) list.splice(i, 1); }, `삭제 "${t.title}"`);
  toast(`"${t.title || '제목 없음'}" 삭제했습니다`, '되돌리기', () => mutate(list => { if (!find(list, id)) list.push(clone(saved)); }, `되돌리기 "${saved.title}"`), 8000);
}
function addLog(id, text) {
  const at = new Date().toISOString();
  mutate(list => { const t = find(list, id); if (t) { t.log = [...(t.log || []), { at, by: 'me', text }]; t.updated = at; } }, '기록 추가');
}

// ---------- 화면
function shell() {
  const app = $('#app');
  app.replaceChildren(
    h('header', { class: 'top' },
      h('div', { class: 'brand' }, h('div', { class: 'mark', 'aria-hidden': 'true' }, 'R'), h('h1', null, 'REAL 작업실')),
      h('span', { class: 'today', id: 'today' }), h('span', { class: 'sync', id: 'sync' }, S.syncText),
      h('span', { class: 'grow' }),
      h('label', { class: 'search' }, h('input', { id: 'q', type: 'search', placeholder: '작업 검색', autocomplete: 'off', 'aria-label': '작업 검색' }), h('span', { class: 'kbd' }, '/')),
      h('button', { class: 'btn icon-btn ghost', id: 'theme', type: 'button', 'aria-label': '밝기 전환', title: '밝기 전환' }, '◐'),
      h('button', { class: 'btn icon-btn ghost', id: 'lockbtn', type: 'button', 'aria-label': '잠그기', title: '잠그기' }, '⏻'),
      h('button', { class: 'btn primary', id: 'new', type: 'button' }, '+ 새 작업 ', h('span', { class: 'kbd' }, 'N'))),
    h('div', { id: 'tokenbox', class: 'banner', hidden: true }),
    h('div', { class: 'summary', id: 'summary' }),
    h('section', { 'aria-label': '이번 주 일정' }, h('div', { class: 'week', id: 'week' })),
    h('div', { class: 'filterbar', id: 'filterbar', hidden: true }),
    h('main', { class: 'board', id: 'board', 'aria-label': '작업 보드' }));
  $('#new').onclick = newTask;
  $('#q').addEventListener('input', e => { S.q = e.target.value; renderBoard(); });
  $('#theme').onclick = () => { const r = document.documentElement; const next = r.dataset.theme === 'light' ? 'dark' : 'light'; r.dataset.theme = next; store.set('theme', next); };
  $('#lockbtn').onclick = lockNow;
}
function renderTop() {
  const d = new Date();
  $('#today').textContent = `${d.getMonth() + 1}월 ${d.getDate()}일 ${DAYS[d.getDay()]}요일`;
  const cnt = k => S.tasks.filter(t => t.status === k).length;
  const late = S.tasks.filter(isLate).length, dueToday = S.tasks.filter(t => t.status !== 'done' && t.due === todayStr()).length;
  $('#summary').replaceChildren(
    ...STATUS.filter(s => s.k !== 'done').map(s => h('span', { class: 'pill' }, h('i', { class: 'dot', css: { '--c': s.c } }), s.name, h('b', null, cnt(s.k)))),
    h('span', { class: 'pill' }, h('i', { class: 'dot', css: { '--c': 'var(--accent)' } }), '오늘 마감', h('b', null, dueToday)),
    late ? h('span', { class: 'pill warn' }, h('i', { class: 'dot', css: { '--c': 'var(--late)' } }), '기한 지남', h('b', null, late)) : null);
}
function weekDays() {
  const base = new Date(); base.setHours(0, 0, 0, 0);
  const mon = new Date(base); mon.setDate(base.getDate() - ((base.getDay() + 6) % 7) + S.weekOff * 7);
  return [...Array(7)].map((_, i) => { const d = new Date(mon); d.setDate(mon.getDate() + i); return d; });
}
function renderWeek() {
  const t = todayStr();
  const cells = weekDays().map(d => {
    const key = ymd(d), open = S.tasks.filter(x => x.due === key && x.status !== 'done');
    const doneN = S.tasks.filter(x => x.due === key && x.status === 'done').length;
    return h('button', { type: 'button', class: `day${key === t ? ' is-today' : ''}${S.day === key ? ' sel' : ''}`, 'aria-pressed': S.day === key ? 'true' : 'false',
      onclick: () => { S.day = S.day === key ? null : key; render(); } },
      h('span', { class: 'd' }, h('strong', null, d.getDate()), DAYS[d.getDay()] + (key === t ? ' · 오늘' : '')),
      h('span', { class: 'bars' }, open.slice(0, 8).map(x => h('i', { css: { '--c': (SMAP[x.status] || SMAP.todo).c }, title: x.title }))),
      h('span', { class: 'n' }, open.length ? `마감 ${open.length}건` : doneN ? `완료 ${doneN}건` : '—'));
  });
  $('#week').replaceChildren(
    h('button', { class: 'nav', type: 'button', 'aria-label': '지난주', onclick: () => { S.weekOff--; render(); } }, '‹'), ...cells,
    h('button', { class: 'nav', type: 'button', 'aria-label': '다음 주', onclick: () => { S.weekOff++; render(); } }, '›'));
  const areas = [...new Set(S.tasks.map(x => x.area).filter(Boolean))].sort();
  const bits = [];
  if (S.weekOff) bits.push(h('button', { class: 'chip', type: 'button', onclick: () => { S.weekOff = 0; render(); } }, '이번 주로'));
  if (S.day) bits.push(h('span', null, `${S.day.slice(5).replace('-', '/')} 마감만 보는 중`), h('button', { class: 'chip', type: 'button', onclick: () => { S.day = null; render(); } }, '전체 보기'));
  if (areas.length) bits.push(h('span', null, '분류'), ...areas.map(a => h('button', { class: 'chip', type: 'button', 'aria-pressed': S.area === a ? 'true' : 'false', onclick: () => { S.area = S.area === a ? null : a; render(); } }, a)));
  $('#filterbar').replaceChildren(...bits); $('#filterbar').hidden = !bits.length;
}
function visible() {
  const q = S.q.trim().toLowerCase();
  return S.tasks.filter(t => (!S.day || t.due === S.day) && (!S.area || t.area === S.area)
    && (!q || [t.title, t.detail, t.area, ...(t.log || []).map(l => l.text)].join(' ').toLowerCase().includes(q)));
}
function sortTasks(list, k) {
  const pr = { high: 0, normal: 1, low: 2 };
  if (k === 'done' || k === 'hold') return list.sort((a, b) => (b.updated || '').localeCompare(a.updated || ''));
  return list.sort((a, b) => (pr[a.priority] ?? 1) - (pr[b.priority] ?? 1) || (a.due || '9999').localeCompare(b.due || '9999') || (b.created || '').localeCompare(a.created || ''));
}
function card(t) {
  const due = dueLabel(t.due), last = (t.log || []).at(-1);
  const el = h('button', { type: 'button', class: `task${S.open === t.id ? ' sel' : ''}`, draggable: 'true', onclick: () => openDrawer(t.id) },
    h('span', { class: 't' }, t.priority === 'high' ? h('span', { class: 'pri', title: '중요도 높음' }, '●') : null, t.title || '(제목 없음)'),
    (t.area || due || t.priority === 'low') ? h('span', { class: 'meta' }, t.area ? h('span', { class: 'tag' }, t.area) : null,
      due ? h('span', { class: `due ${t.status === 'done' ? '' : due.cls}` }, due.txt) : null, t.priority === 'low' ? h('span', null, '낮음') : null) : null,
    last ? h('span', { class: 'last' }, last.by === 'claude' ? h('span', { class: 'by' }, 'AI') : null, last.text) : null);
  el.addEventListener('dragstart', e => { e.dataTransfer.setData('text/plain', t.id); e.dataTransfer.effectAllowed = 'move'; el.classList.add('dragging'); });
  el.addEventListener('dragend', () => el.classList.remove('dragging'));
  return el;
}
function renderBoard() {
  const vis = visible();
  $('#board').replaceChildren(...STATUS.map(s => {
    let list = sortTasks(vis.filter(t => (t.status || 'todo') === s.k), s.k);
    const total = list.length, cap = s.k === 'done' ? S.showDone : s.k === 'hold' ? S.showHold : Infinity;
    list = list.slice(0, cap);
    const body = h('div', { class: 'col-body' });
    if (s.k === 'todo' && S.quick) {
      const inp = h('input', { placeholder: '할 일을 적고 Enter', 'aria-label': '빠른 추가', autocomplete: 'off' });
      inp.addEventListener('keydown', e => {
        if (e.key === 'Escape') { S.quick = false; renderBoard(); }
        else if (e.key === 'Enter' && !e.isComposing && inp.value.trim()) { const v = inp.value.trim(); inp.value = ''; createTask({ title: v, due: S.day || '' }); }
      });
      body.append(h('div', { class: 'quick' }, inp)); requestAnimationFrame(() => inp.focus());
    }
    body.append(...list.map(card));
    if (!total && !(s.k === 'todo' && S.quick)) body.append(h('div', { class: 'empty' }, s.k === 'todo' ? '할 일이 없습니다. + 를 눌러 추가하세요.' : '없음'));
    if (total > list.length) body.append(h('button', { class: 'more', type: 'button', onclick: () => { if (s.k === 'done') S.showDone += 30; else S.showHold += 30; renderBoard(); } }, `${total - list.length}건 더 보기`));
    const c = h('section', { class: 'col', 'aria-label': s.name },
      h('div', { class: 'col-head' }, h('i', { class: 'dot', css: { '--c': s.c } }), h('h2', null, s.name), h('span', { class: 'cnt' }, total),
        s.k === 'todo' ? h('button', { class: 'add', type: 'button', 'aria-label': '빠른 추가', title: '빠른 추가', onclick: () => { S.quick = !S.quick; renderBoard(); } }, '+') : null),
      body);
    c.addEventListener('dragover', e => { e.preventDefault(); c.classList.add('over'); });
    c.addEventListener('dragleave', e => { if (!c.contains(e.relatedTarget)) c.classList.remove('over'); });
    c.addEventListener('drop', e => { e.preventDefault(); c.classList.remove('over'); setStatus(e.dataTransfer.getData('text/plain'), s.k); });
    return c;
  }));
}

// ---------- 상세 창
let drawerEl = null, scrimEl = null;
function closeDrawer() { S.open = null; drawerEl?.remove(); scrimEl?.remove(); drawerEl = scrimEl = null; renderBoard(); }
function openDrawer(id) { S.open = id; renderBoard(); renderDrawer(true); }
function renderDrawer(fresh) {
  const t = find(S.tasks, S.open);
  if (!t) { if (drawerEl) { closeDrawer(); toast('다른 곳에서 삭제된 작업입니다.'); } return; }
  const a = document.activeElement;
  if (!fresh && drawerEl && drawerEl.contains(a) && a.matches('input, textarea, select')) { refreshLog(t); refreshStatus(t); return; }
  const keep = drawerEl?.querySelector('.dr-body')?.scrollTop || 0;
  drawerEl?.remove(); scrimEl?.remove();
  scrimEl = h('div', { class: 'scrim', onclick: closeDrawer });
  const bind = (field, el, tf = v => v) => {
    let timer;
    const go = () => { clearTimeout(timer); const v = tf(el.value), cur = find(S.tasks, t.id); if (cur && (cur[field] ?? '') !== v) patchTask(t.id, { [field]: v }, `"${cur.title}" ${field === 'title' ? '제목' : field === 'detail' ? '내용' : field === 'due' ? '마감일' : field === 'priority' ? '중요도' : '분류'} 수정`); };
    el.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(go, 900); });
    el.addEventListener('change', go); el.addEventListener('blur', go);
  };
  const title = h('textarea', { class: 'f-title', rows: 1, 'aria-label': '제목', placeholder: '작업 제목' }); title.value = t.title || '';
  const fit = () => { title.style.height = 'auto'; title.style.height = title.scrollHeight + 'px'; };
  title.addEventListener('input', fit); title.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.isComposing) { e.preventDefault(); title.blur(); } });
  bind('title', title, v => v.trim());
  const due = h('input', { type: 'date', id: 'f-due' }); due.value = t.due || ''; bind('due', due);
  const pri = h('select', { id: 'f-pri' }, Object.entries(PRI).map(([k, v]) => h('option', { value: k }, v))); pri.value = t.priority || 'normal'; bind('priority', pri);
  const area = h('input', { id: 'f-area', placeholder: '예: 서버, 라운지', list: 'areas', autocomplete: 'off' }); area.value = t.area || ''; bind('area', area, v => v.trim());
  const areas = h('datalist', { id: 'areas' }, [...new Set(S.tasks.map(x => x.area).filter(Boolean))].map(v => h('option', { value: v })));
  const detail = h('textarea', { class: 'f-detail', id: 'f-detail', placeholder: '무엇을, 어디까지 할지 적어 두세요.' }); detail.value = t.detail || ''; bind('detail', detail);
  const memo = h('textarea', { placeholder: '진행 상황이나 지시를 남깁니다', 'aria-label': '기록 남기기' });
  const addMemo = () => { const v = memo.value.trim(); if (!v) return; memo.value = ''; addLog(t.id, v); };
  memo.addEventListener('keydown', e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); addMemo(); } });
  drawerEl = h('aside', { class: 'drawer', role: 'dialog', 'aria-label': '작업 상세' },
    h('div', { class: 'dr-head' }, h('span', { class: 'id' }, `${t.id} · 수정 ${when(t.updated)}`), h('span', { class: 'grow' }),
      h('button', { class: 'btn icon-btn ghost', type: 'button', 'aria-label': '닫기', onclick: closeDrawer }, '✕')),
    h('div', { class: 'dr-body' }, title, h('div', { class: 'statusrow', id: 'statusrow' }),
      h('div', { class: 'fields' },
        h('div', { class: 'field' }, h('label', { for: 'f-due' }, '마감일'), due),
        h('div', { class: 'field' }, h('label', { for: 'f-pri' }, '중요도'), pri),
        h('div', { class: 'field' }, h('label', { for: 'f-area' }, '분류'), area, areas)),
      h('div', { class: 'field' }, h('label', { for: 'f-detail' }, '내용'), detail),
      h('div', null, h('div', { class: 'sec-label' }, '진행 기록'), h('div', { id: 'log' })),
      h('div', { class: 'memo' }, memo, h('div', { class: 'row' }, h('span', null, 'Ctrl+Enter'), h('button', { class: 'btn sm', type: 'button', onclick: addMemo }, '기록 남기기')))),
    h('div', { class: 'dr-foot' }, h('button', { class: 'btn danger ghost', type: 'button', onclick: () => removeTask(t.id) }, '삭제'), h('span', { class: 'grow' }), h('span', { class: 'sync' }, '자동 저장')));
  document.body.append(scrimEl, drawerEl);
  drawerEl.querySelector('.dr-body').scrollTop = keep;
  fit(); refreshLog(t); refreshStatus(t);
  if (fresh && !t.title) title.focus();
}
function refreshStatus(t) {
  const row = $('#statusrow'); if (!row) return;
  row.replaceChildren(...STATUS.map(s => h('button', { type: 'button', class: 'st', css: { '--c': s.c }, 'aria-pressed': (t.status || 'todo') === s.k ? 'true' : 'false', onclick: () => setStatus(t.id, s.k) }, h('i', { class: 'dot', css: { '--c': s.c } }), s.name)));
}
function refreshLog(t) {
  const box = $('#log'); if (!box) return;
  const log = [...(t.log || [])].reverse();
  box.replaceChildren(...(log.length ? log.map(l => h('div', { class: 'entry' }, h('span', { class: 'when' }, when(l.at)),
    h('div', { class: 'txt' }, h('span', { class: `who ${l.by === 'claude' ? 'claude' : 'me'}` }, l.by === 'claude' ? 'AI' : '나'), l.text)))
    : [h('div', { class: 'empty' }, '아직 기록이 없습니다.')]));
}
function render() { if (!$('#board')) return; renderTop(); renderWeek(); renderBoard(); if (S.open) renderDrawer(false); }
function newTask() { const id = createTask({ title: '', due: S.day || '' }); S.open = id; renderDrawer(true); }

// ---------- 토큰 안내 (저장하려면 Contents 쓰기 권한 토큰 필요)
function showTokenBox(reason) {
  const box = $('#tokenbox'); if (!box) return;
  const inp = h('input', { type: 'password', placeholder: 'GitHub 토큰 붙여넣기 (github_pat_…)', autocomplete: 'off', 'aria-label': 'GitHub 토큰' });
  const save = h('button', { class: 'btn sm', type: 'button' }, '저장');
  save.onclick = async () => {
    const v = inp.value.trim(); if (!v) return;
    const r = await fetch(`https://api.github.com/repos/${REPO}`, { headers: { Authorization: `Bearer ${v}`, Accept: 'application/vnd.github+json' } });
    if (!r.ok) { toast(`GitHub가 토큰을 거절했습니다 (${r.status})`); return; }
    const j = await r.json();
    if (!j.permissions || !j.permissions.push) { toast('이 토큰은 저장소에 쓸 권한이 없습니다. Contents: Read and write를 주세요.'); return; }
    await tokenSet(v); S.token = v; box.hidden = true; toast('토큰을 저장했습니다'); flush();
  };
  box.replaceChildren(h('span', null, (reason ? reason + ' — ' : '') + '변경을 저장하려면 이 저장소(hati0101/dash)에 Contents: Read and write 권한이 있는 GitHub 토큰이 필요합니다.'), inp, save);
  box.hidden = false;
}

// ---------- 잠금
async function boot() {
  const th = store.get('theme'); if (th) document.documentElement.dataset.theme = th;
  $('#lock-form').addEventListener('submit', unlock);
  if (!window.isSecureContext || !crypto.subtle) { $('#lock-msg').textContent = 'HTTPS에서만 열 수 있습니다.'; return; }
  try { S.env = (await fetchRemote()).env; } catch (e) { $('#lock-msg').textContent = e.message; return; }
  const saved = store.get('key');
  if (saved && saved.salt === S.env.salt) {
    try { S.key = await crypto.subtle.importKey('raw', b64.dec(saved.k), 'AES-GCM', false, ['encrypt', 'decrypt']); await openEnv(S.env, S.key); return enter(); }
    catch { store.del('key'); S.key = null; }
  }
  $('#remember').checked = !!store.get('rememberPref', false);
  $('#pw').focus();
}
async function unlock(ev) {
  ev.preventDefault();
  const pw = $('#pw').value, remember = $('#remember').checked, btn = $('#unlock'), msg = $('#lock-msg');
  if (!pw || !S.env) return;
  btn.disabled = true; msg.textContent = '여는 중…';
  try {
    const key = await deriveKey(pw, S.env.salt, S.env.iter, true);
    await openEnv(S.env, key);
    const raw = new Uint8Array(await crypto.subtle.exportKey('raw', key));
    if (remember) store.set('key', { salt: S.env.salt, k: b64.enc(raw) }); else store.del('key');
    S.key = await crypto.subtle.importKey('raw', raw, 'AES-GCM', false, ['encrypt', 'decrypt']);
    store.set('rememberPref', remember); $('#pw').value = '';
    enter();
  } catch { msg.textContent = '비밀번호가 맞지 않습니다.'; btn.disabled = false; $('#pw').select(); }
}
function lockNow() { store.del('key'); location.reload(); }
async function enter() {
  $('#lock').hidden = true; $('#app').hidden = false;
  S.token = await tokenGet();
  shell();
  try { await pull(); setSync(S.token ? '최신' : '읽기 전용'); } catch (e) { setSync('불러오기 실패: ' + e.message, true); }
  if (!S.token) showTokenBox();
  render();
  setInterval(async () => {  // 다른 기기 변경 확인
    if (S.saving || S.queue.length || document.hidden) return;
    try { if (await pull()) render(); } catch { /* 다음에 다시 */ }
  }, 20000);
  document.addEventListener('visibilitychange', async () => { if (!document.hidden && !S.saving && !S.queue.length) { try { if (await pull()) render(); } catch { /* 무시 */ } } });
}
document.addEventListener('keydown', e => {
  if (!$('#board')) return;
  const typing = e.target.matches('input, textarea, select');
  if (e.key === 'Escape') { if (typing) e.target.blur(); else if (S.open) closeDrawer(); return; }
  if (typing || e.ctrlKey || e.metaKey || e.altKey) return;
  if (e.key === '/') { e.preventDefault(); $('#q').focus(); }
  else if (e.code === 'KeyN') { e.preventDefault(); newTask(); }
});
window.addEventListener('beforeunload', e => { if (S.queue.length || S.saving) { e.preventDefault(); e.returnValue = ''; } });
boot();
