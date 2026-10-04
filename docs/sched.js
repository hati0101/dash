'use strict';
/* REAL 작업실 — 목록형 스케줄러. 데이터는 docs/sched.enc.json(대시보드 비밀번호로 암호화).
   저장은 GitHub API로 그 파일을 바로 커밋한다(토큰: 이 기기에만 암호화 보관). 다른 기기 변경은 20초마다 확인. */
const REPO = 'hati0101/dash', PATH = 'docs/sched.enc.json', BRANCH = 'main';
const API = `https://api.github.com/repos/${REPO}/contents/${PATH}`;
const STATUS = [
  { k: 'todo', name: '대기', c: 'var(--todo)', ring: '' },
  { k: 'doing', name: '진행 중', c: 'var(--doing)', ring: 'half' },
  { k: 'review', name: '확인 대기', c: 'var(--review)', ring: 'half' },
  { k: 'hold', name: '보류', c: 'var(--hold)', ring: 'pause' },
  { k: 'done', name: '완료', c: 'var(--done)', ring: 'full' },
];
const SMAP = Object.fromEntries(STATUS.map(s => [s.k, s]));
const PRI = { high: '높음', normal: '보통', low: '낮음' };
const DAYS = ['일', '월', '화', '수', '목', '금', '토'];
const S = { env: null, key: null, sha: null, remote: [], tasks: [], queue: [], saving: false, token: null,
  view: 'all', status: 'todo', area: null, day: null, q: '', group: 'area', open: null, focus: null, collapsed: {}, sel: new Set(), anchor: null };

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
const find = (list, id) => list.find(x => x.id === id);
function shortDate(iso) { const d = new Date(iso); return isNaN(d) ? '' : `${d.getMonth() + 1}/${d.getDate()}`; }
function dayLabel(v) {
  if (!v) return null;
  const d = new Date(v + 'T00:00'); if (isNaN(d)) return null;
  const diff = Math.round((d - new Date(todayStr() + 'T00:00')) / 864e5);
  return { txt: diff === 0 ? '오늘' : diff === 1 ? '내일' : diff === -1 ? '어제' : `${d.getMonth() + 1}/${d.getDate()}`, diff };
}
function when(iso) {
  if (!iso) return '';
  const d = new Date(iso); if (isNaN(d)) return '';
  return ymd(d) === todayStr() ? `오늘 ${pad(d.getHours())}:${pad(d.getMinutes())}` : `${d.getMonth() + 1}/${d.getDate()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
function toast(text, label, action, ms = 6000) {
  const btn = label ? h('button', { class: 'btn', type: 'button' }, label) : null;
  const t = h('div', { class: 'toast', role: 'status' }, h('span', null, text), btn);
  if (btn) btn.onclick = () => { action(); t.remove(); };
  let box = $('#toasts'); if (!box) { box = h('div', { class: 'toasts', id: 'toasts', 'aria-live': 'polite' }); document.body.append(box); }
  box.append(t); setTimeout(() => t.remove(), ms);
}
const isLate = t => t.status !== 'done' && t.status !== 'hold' && t.due && t.due < todayStr();
const newId = () => 'W-' + todayStr().replace(/-/g, '') + '-' + [...crypto.getRandomValues(new Uint8Array(3))].map(b => b.toString(16).padStart(2, '0')).join('');
const ICONS = {
  plus: '<path d="M12 5v14M5 12h14"/>',
  theme: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l2 2m10 10 2 2M5 19l2-2M17 7l2-2"/>',
  lock: '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
  close: '<path d="m6 6 12 12M18 6 6 18"/>',
  settings: '<path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3"/><circle cx="15" cy="17" r="3"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 3v1.5M12 19.5V21M3 12h1.5M19.5 12H21"/>',
  week: '<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 10h16M9 3v4M15 3v4"/>',
  all: '<path d="M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01"/>',
  tag: '<path d="M3 12V4h8l10 10-8 8z"/><circle cx="7.5" cy="7.5" r="1.2"/>',
  search: '<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4 4"/>',
};
function icon(name, size) {
  const el = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  for (const [k, v] of Object.entries({ viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '1.8', 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true', width: size || 16, height: size || 16 })) el.setAttribute(k, v);
  el.innerHTML = ICONS[name] || ''; return el;
}
const ring = (k, size) => h('span', { class: `ring ${(SMAP[k] || SMAP.todo).ring}`, css: { '--c': (SMAP[k] || SMAP.todo).c, ...(size ? { width: size, height: size } : {}) }, 'aria-hidden': 'true' });

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
async function pullUsage() {
  try {
    let env;
    if (S.token) {
      const r = await fetch(`https://api.github.com/repos/${REPO}/contents/docs/usage.enc.json?ref=${BRANCH}&t=${Date.now()}`, { headers: { Authorization: `Bearer ${S.token}`, Accept: 'application/vnd.github+json' }, cache: 'no-store' });
      if (!r.ok) return;
      env = JSON.parse(atob((await r.json()).content.replace(/\s/g, '')));
    } else {
      const r = await fetch('usage.enc.json?t=' + Date.now(), { cache: 'no-store' }); if (!r.ok) return; env = await r.json();
    }
    S.usage = await openEnv(env, S.key);
    if ($('#usage')) renderUsage();
  } catch { /* 사용량은 없어도 된다 */ }
}
function ago(iso) { const m = Math.round((Date.now() - Date.parse(iso)) / 60000); return isNaN(m) ? '' : m < 1 ? '방금' : m < 60 ? `${m}분 전` : m < 1440 ? `${Math.round(m / 60)}시간 전` : `${Math.round(m / 1440)}일 전`; }
function resetIn(iso) { const m = Math.round((Date.parse(iso) - Date.now()) / 60000); if (isNaN(m)) return ''; if (m <= 0) return '초기화됨'; return m < 60 ? `${m}분 뒤` : m < 1440 ? `${Math.floor(m / 60)}시간 ${m % 60}분 뒤` : `${Math.floor(m / 1440)}일 ${Math.round((m % 1440) / 60)}시간 뒤`; }
function renderUsage() {
  const box = $('#usage'); if (!box) return;
  const u = S.usage;
  if (!u) { box.replaceChildren(h('div', { class: 'u-empty' }, '사용량 정보 없음')); return; }
  const bar = (label, w) => !w ? null : h('div', { class: 'u-row', title: w.resets_at ? `초기화 ${resetIn(w.resets_at)} (${w.resets_at.slice(5, 16).replace('T', ' ')})` : '' },
    h('span', { class: 'u-l' }, label), h('span', { class: 'u-bar' }, h('i', { css: { width: Math.min(100, w.pct) + '%', '--c': w.pct >= 90 ? 'var(--late)' : w.pct >= 70 ? 'var(--review)' : 'var(--accent)' } })),
    h('span', { class: 'u-p' }, `${w.pct}%`));
  box.replaceChildren(...u.accounts.map(a => h('div', { class: 'u-acc' },
    h('div', { class: 'u-name' }, h('b', null, a.name), a.plan ? h('span', null, String(a.plan).toUpperCase()) : null),
    a.error ? h('div', { class: 'u-empty' }, a.error) : null,
    bar('5시간', a.five_hour), bar('주간', a.seven_day),
    a.five_hour && !a.seven_day ? null : null)),
    h('div', { class: 'u-foot', title: `개발컴이 15분마다 올림 · 마지막 ${u.updated_at}` }, `${ago(u.updated_at)} 기준`));
}
async function pull() {
  const { sha, env } = await fetchRemote();
  if (sha && sha === S.sha) return false;
  const data = await openEnv(env, S.key);
  S.sha = sha; S.remote = data.tasks || [];
  S.tasks = clone(S.remote); for (const op of S.queue) op.fn(S.tasks);
  return true;
}
function mutate(fn, msg) { fn(S.tasks); S.queue.push({ fn, msg }); render(); flush(); }
async function flush() {
  if (S.saving || !S.queue.length) return;
  if (!S.token) { setSync('토큰이 없어 저장하지 못했습니다', 'err'); showTokenBox(); return; }
  S.saving = true; setSync('저장 중', 'busy');
  let tries = 0;
  while (S.queue.length && tries < 4) {
    const ops = S.queue.slice();
    const next = clone(S.remote); for (const op of ops) op.fn(next);
    try {
      const env = await sealEnv({ v: 1, tasks: next });
      const r = await fetch(API, { method: 'PUT', headers: { Authorization: `Bearer ${S.token}`, Accept: 'application/vnd.github+json', 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: '작업실: ' + (ops.length === 1 ? ops[0].msg : ops[0].msg + ` 외 ${ops.length - 1}건`), content: btoa(JSON.stringify(env)), sha: S.sha || undefined, branch: BRANCH }) });
      if (r.status === 409 || r.status === 422) { tries++; await pull(); continue; }  // 다른 기기가 먼저 저장 — 최신본에 다시 적용
      if (!r.ok) throw new Error(r.status === 401 ? '토큰이 만료됐거나 틀렸습니다' : r.status === 403 || r.status === 404 ? '토큰에 이 저장소의 Contents 쓰기 권한이 없습니다' : 'GitHub ' + r.status);
      const j = await r.json();
      S.sha = j.content.sha; S.remote = next; S.queue.splice(0, ops.length);
      S.tasks = clone(S.remote); for (const op of S.queue) op.fn(S.tasks);
      setSync('저장됨 ' + when(new Date().toISOString()));
    } catch (e) {
      setSync('저장 실패: ' + e.message, 'err'); S.saving = false;
      if (/권한|토큰/.test(e.message)) showTokenBox(e.message);
      return;
    }
  }
  S.saving = false; render();
  if (S.queue.length) setTimeout(flush, 1500);
}
function setSync(t, kind = '') { S.syncText = t; S.syncKind = kind; const el = $('#sync'); if (el) { el.className = 'sync ' + kind; el.replaceChildren(h('span', null, t)); el.title = t; } }

// ---------- 작업 조작
function createTask(f) {
  const now = new Date().toISOString(), id = newId();
  const t = { id, title: f.title || '', detail: '', status: f.status || 'todo', start: todayStr(), due: f.due || '', priority: 'normal', area: f.area || '', stages: { [f.status || 'todo']: now }, log: [{ at: now, by: 'me', kind: 'change', field: 'status', text: `만듦 · ${(SMAP[f.status || 'todo'] || SMAP.todo).name}` }], created: now, updated: now };
  mutate(list => { if (!find(list, id)) list.push(clone(t)); }, `추가 "${t.title || '새 작업'}"`);
  return id;
}
const FIELD = { title: '제목', detail: '내용', start: '시작일', due: '마감일', priority: '중요도', area: '분류', status: '상태', public: '디스코드 공개', pubTitle: '공개 제목' };
function fmtVal(f, v) {
  if (f === 'status') return (SMAP[v] || {}).name || v || '없음';
  if (f === 'priority') return PRI[v] || v || '보통';
  if (f === 'start' || f === 'due') return v ? v.slice(5).replace('-', '/') : '없음';
  if (f === 'public') return v ? '공개' : '비공개';
  return v || '없음';
}
function applyPatch(t, patch, now) {
    const log = [...(t.log || [])];
    for (const [f, v] of Object.entries(patch)) {
      const old = t[f] ?? '';
      if (old === v) continue;
      const text = f === 'title' || f === 'detail' ? `${FIELD[f]} 수정` : `${FIELD[f] || f}: ${fmtVal(f, old)} → ${fmtVal(f, v)}`;
      const last = log.at(-1), norm = x => typeof v === 'boolean' ? !!x : (x ?? '');
      const merge = f !== 'status' && last && last.kind === 'change' && last.field === f && Date.parse(now) - Date.parse(last.at) < 600000;
      if (merge && (f === 'title' || f === 'detail')) log[log.length - 1] = { ...last, at: now };
      else if (merge) {
        const orig = 'from' in last ? last.from : old;
        if (norm(orig) === norm(v)) log.pop();  // 원래 값으로 돌아옴: 기록할 변화 없음
        else log[log.length - 1] = { ...last, at: now, from: orig, text: `${FIELD[f] || f}: ${fmtVal(f, orig)} → ${fmtVal(f, v)}` };
      } else log.push({ at: now, by: 'me', kind: 'change', field: f, from: old, text });
      if (f === 'status') t.stages = { ...(t.stages || {}), [v]: now };
    }
    Object.assign(t, clone(patch), { updated: now, log });
}
function patchTask(id, patch, msg) {
  const now = new Date().toISOString();
  mutate(list => { const t = find(list, id); if (t) applyPatch(t, patch, now); }, msg || '수정');
}
function bulkStatus(k) {
  const ids = [...S.sel].filter(id => { const t = find(S.tasks, id); return t && t.status !== k; });
  if (!ids.length) return toast(`이미 모두 ${SMAP[k].name}입니다`);
  const now = new Date().toISOString();
  mutate(list => { for (const id of ids) { const t = find(list, id); if (t && t.status !== k) applyPatch(t, { status: k }, now); } }, `일괄 → ${SMAP[k].name} (${ids.length}건)`);
  S.sel.clear(); renderRows(); renderBulk();
  toast(`${ids.length}건 → ${SMAP[k].name}`);
}
function bulkDelete() {
  const ids = [...S.sel], saved = ids.map(id => find(S.tasks, id)).filter(Boolean).map(clone);
  if (!saved.length) return;
  if (ids.includes(S.open)) S.open = null;
  S.sel.clear();
  mutate(list => { for (const id of ids) { const i = list.findIndex(x => x.id === id); if (i >= 0) list.splice(i, 1); } }, `일괄 삭제 (${saved.length}건)`);
  toast(`${saved.length}건 삭제했습니다`, '되돌리기', () => mutate(list => { for (const s of saved) if (!find(list, s.id)) list.push(clone(s)); }, `일괄 삭제 되돌리기 (${saved.length}건)`), 10000);
}
function bulkPatch(ids, patch, label) {
  const now = new Date().toISOString(), [f, v] = Object.entries(patch)[0];
  const same = (a, b) => typeof b === 'boolean' ? !!a === b : (a ?? '') === b;
  const todo = ids.filter(id => { const t = find(S.tasks, id); return t && !same(t[f], v); });
  if (!todo.length) return toast('바뀔 작업이 없습니다');
  mutate(list => { for (const id of todo) { const t = find(list, id); if (t && !same(t[f], v)) applyPatch(t, patch, now); } }, `일괄 ${label} (${todo.length}건)`);
  S.sel.clear(); renderRows(); renderBulk();
  toast(`${todo.length}건 → ${label}`);
}
function renameArea(from, to) {
  to = to.trim(); if (!to || to === from) return;
  const ids = S.tasks.filter(t => (t.area || '분류 없음') === from).map(t => t.id);
  if (S.area === from) S.area = to;
  bulkPatch(ids, { area: to === '분류 없음' ? '' : to }, `분류 ${from} → ${to}`);
}
function dragIds(e) { try { return JSON.parse(e.dataTransfer.getData('application/x-real-ids') || '[]'); } catch { return []; } }
function dropTarget(el, apply) {
  el.addEventListener('dragover', e => { if ([...e.dataTransfer.types].includes('application/x-real-ids')) { e.preventDefault(); el.classList.add('drop'); } });
  el.addEventListener('dragleave', () => el.classList.remove('drop'));
  el.addEventListener('drop', e => { e.preventDefault(); el.classList.remove('drop'); const ids = dragIds(e); if (ids.length) apply(ids); });
  return el;
}
function toggleSel(id, on) { if (on ?? !S.sel.has(id)) S.sel.add(id); else S.sel.delete(id); S.anchor = id; }
function visibleIds() { return [...document.querySelectorAll('#rows .row')].map(r => r.dataset.id); }
function stageDate(t, k) { return (t.stages || {})[k] || (k === 'todo' ? (t.start ? t.start + 'T00:00:00' : t.created) : null); }
function setStatus(id, k) {
  const t = find(S.tasks, id); if (!t || t.status === k) return;
  patchTask(id, { status: k }, `"${t.title}" → ${SMAP[k].name}`);
  toast(`"${t.title || '제목 없음'}" → ${SMAP[k].name}`);
}
function removeTask(id) {
  const t = find(S.tasks, id); if (!t) return;
  const saved = clone(t);
  if (S.open === id) S.open = null;
  mutate(list => { const i = list.findIndex(x => x.id === id); if (i >= 0) list.splice(i, 1); }, `삭제 "${t.title}"`);
  toast(`"${t.title || '제목 없음'}" 삭제했습니다`, '되돌리기', () => mutate(list => { if (!find(list, id)) list.push(clone(saved)); }, `되돌리기 "${saved.title}"`), 8000);
}
function addLog(id, text) {
  const at = new Date().toISOString();
  mutate(list => { const t = find(list, id); if (t) { t.log = [...(t.log || []), { at, by: 'me', text }]; t.updated = at; } }, '기록 추가');
}

// ---------- 보기·목록 계산
function weekRange() {
  const base = new Date(); base.setHours(0, 0, 0, 0);
  const mon = new Date(base); mon.setDate(base.getDate() - ((base.getDay() + 6) % 7));
  return [...Array(7)].map((_, i) => { const d = new Date(mon); d.setDate(mon.getDate() + i); return d; });
}
function inView(t) {
  const today = todayStr();
  if (S.day) return t.due === S.day || t.start === S.day;
  if (S.view === 'pubdoing') return !!t.public && t.status === 'doing';
  if (S.view === 'pub') return !!t.public;
  if (S.view === 'today') return t.status !== 'done' && (t.due === today || (t.status === 'doing') || isLate(t));
  if (S.view === 'week') { const w = weekRange().map(ymd); return t.status !== 'done' && t.due && t.due >= w[0] && t.due <= w[6]; }
  return true;
}
function visible() {
  const q = S.q.trim().toLowerCase();
  return S.tasks.filter(t => inView(t) && (S.view !== 'all' || S.day || !S.status || (t.status || 'todo') === S.status) && (!S.area || (t.area || '분류 없음') === S.area)
    && (!q || [t.title, t.detail, t.area, ...(t.log || []).map(l => l.text)].join(' ').toLowerCase().includes(q)));
}
function sortRows(list) {
  const pr = { high: 0, normal: 1, low: 2 };
  return list.sort((a, b) => (pr[a.priority] ?? 1) - (pr[b.priority] ?? 1) || (a.title || '').localeCompare(b.title || '', 'ko') || (a.created || '').localeCompare(b.created || ''));
}
function groups(list) {
  if (S.group === 'none') return [{ key: '전체', items: sortRows(list) }];
  const key = S.group === 'status' ? t => (SMAP[t.status] || SMAP.todo).name : t => t.area || '분류 없음';
  const m = new Map();
  for (const t of list) { const k = key(t); if (!m.has(k)) m.set(k, []); m.get(k).push(t); }
  const order = S.group === 'status' ? STATUS.map(s => s.name) : [...m.keys()].sort((a, b) => m.get(b).length - m.get(a).length);
  return order.filter(k => m.has(k)).map(k => ({ key: k, items: sortRows(m.get(k)) }));
}

// ---------- 화면
function shell() {
  $('#app').replaceChildren(
    h('nav', { class: 'side', id: 'side', 'aria-label': '보기' }),
    h('section', { class: 'list' },
      h('div', { class: 'lhead' }, h('h1', { id: 'ltitle' }), h('span', { class: 'count', id: 'lcount' }), h('span', { class: 'grow' }),
        h('label', { class: 'search' }, icon('search', 15), h('input', { id: 'q', type: 'search', placeholder: '제목·내용·기록 검색', autocomplete: 'off', 'aria-label': '검색' }), h('span', { class: 'kbd' }, '/')),
        h('div', { class: 'seg', id: 'groupseg', role: 'group', 'aria-label': '묶기' })),
      h('div', { id: 'tokenbox', class: 'banner', hidden: true }),
      h('label', { class: 'addrow' }, h('span', { class: 'plus' }, icon('plus', 16)), h('input', { id: 'addinput', placeholder: '할 일 추가 — 적고 Enter (시작일은 오늘)', autocomplete: 'off', 'aria-label': '할 일 추가' }), h('span', { class: 'kbd' }, 'N')),
      h('div', { class: 'rows', id: 'rows', role: 'list' }),
      h('div', { class: 'bulk', id: 'bulk', hidden: true, role: 'toolbar', 'aria-label': '선택한 작업' })),
    h('aside', { class: 'pane idle', id: 'pane', 'aria-label': '작업 상세' }));
  $('#q').addEventListener('input', e => { S.q = e.target.value; renderRows(); });
  const add = $('#addinput');
  add.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.isComposing && add.value.trim()) {
      const st = S.view === 'all' && S.status ? S.status : 'todo';
      const id = createTask({ title: add.value.trim(), status: st, area: S.area && S.area !== '분류 없음' ? S.area : '' });
      add.value = ''; S.focus = id; renderRows();
    } else if (e.key === 'Escape') add.blur();
  });
}
function navBtn(label, count, current, onclick, lead) {
  return h('button', { class: 'nav', type: 'button', 'aria-current': current ? 'true' : 'false', onclick }, lead || null, h('span', null, label), count == null ? null : h('span', { class: 'c' }, count));
}
function renderSide() {
  const today = todayStr(), cnt = k => S.tasks.filter(t => (t.status || 'todo') === k).length;
  const areas = new Map(); for (const t of S.tasks) { const a = t.area || '분류 없음'; areas.set(a, (areas.get(a) || 0) + 1); }
  const pick = patch => () => { Object.assign(S, { day: null }, patch); S.focus = null; render(); $('#rows').scrollTop = 0; };
  $('#side').replaceChildren(
    h('div', { class: 'brand' }, h('img', { class: 'mark-img', src: 'brand-mark.png?v=s7', alt: '', width: 34, height: 34 }), h('div', null, h('b', null, 'REAL 작업실'), h('small', null, (() => { const d = new Date(); return `${d.getMonth() + 1}월 ${d.getDate()}일 ${DAYS[d.getDay()]}요일`; })()))),
    h('button', { class: 'new-btn', type: 'button', onclick: () => $('#addinput').focus() }, icon('plus', 16), '새 작업', h('span', { class: 'kbd' }, 'N')),
    h('div', { class: 'sec' }, '상태'),
    ...STATUS.map(s => dropTarget(navBtn(s.name, cnt(s.k), S.view === 'all' && !S.day && S.status === s.k && !S.area, pick({ view: 'all', status: s.k, area: null }), ring(s.k)), ids => bulkPatch(ids, { status: s.k }, s.name))),
    navBtn('전체', S.tasks.length, S.view === 'all' && !S.day && !S.status && !S.area, pick({ view: 'all', status: null, area: null }), h('span', { class: 'ico' }, icon('all', 15))),
    h('div', { class: 'sec' }, '분류'),
    ...[...areas.entries()].sort((a, b) => b[1] - a[1]).map(([a, n]) => {
      const b = navBtn(a, n, S.view === 'all' && !S.day && S.area === a, pick({ view: 'all', status: null, area: a }), h('span', { class: 'ico' }, icon('tag', 14)));
      b.title = '더블클릭: 이름 바꾸기 · 작업을 끌어 놓으면 이 분류로';
      b.addEventListener('dblclick', e => {
        e.preventDefault();
        const inp = h('input', { class: 'nav-edit', 'aria-label': '분류 이름' }); inp.value = a;
        let done = false; const finish = ok => { if (done) return; done = true; if (ok) renameArea(a, inp.value); else renderSide(); };
        inp.addEventListener('keydown', ev => { if (ev.key === 'Enter' && !ev.isComposing) finish(true); else if (ev.key === 'Escape') finish(false); ev.stopPropagation(); });
        inp.addEventListener('blur', () => finish(true));
        b.replaceWith(inp); inp.focus(); inp.select();
      });
      return dropTarget(b, ids => bulkPatch(ids, { area: a === '분류 없음' ? '' : a }, `분류 ${a}`));
    }),
    h('div', { class: 'sec' }, '디스코드'),
    navBtn('발행 대상', S.tasks.filter(t => t.public && t.status === 'doing').length, S.view === 'pubdoing', pick({ view: 'pubdoing', status: null, area: null }), h('span', { class: 'ico disc' }, '●')),
    navBtn('공개 체크 전체', S.tasks.filter(t => t.public).length, S.view === 'pub', pick({ view: 'pub', status: null, area: null }), h('span', { class: 'ico disc' }, '○')),
    h('div', { class: 'sec' }, '사용량 · 개발컴'),
    h('div', { class: 'usage', id: 'usage' }),
    h('div', { class: 'side-foot' }, h('div', { class: `sync ${S.syncKind || ''}`, id: 'sync', title: S.syncText || '' }, h('span', null, S.syncText || '')), h('span', { class: 'grow' }),
      h('button', { class: 'ibtn', type: 'button', title: '저장 설정(GitHub 토큰)', 'aria-label': '저장 설정', onclick: () => { const b = $('#tokenbox'); if (b.hidden) showTokenBox(); else b.hidden = true; } }, icon('settings', 16)),
      h('button', { class: 'ibtn', type: 'button', title: '밝기 전환', 'aria-label': '밝기 전환', onclick: () => { const r = document.documentElement, n = r.dataset.theme === 'light' ? 'dark' : 'light'; r.dataset.theme = n; store.set('theme', n); } }, icon('theme', 16)),
      h('button', { class: 'ibtn', type: 'button', title: '잠그기', 'aria-label': '잠그기', onclick: () => { store.del('key'); location.reload(); } }, icon('lock', 16))));
}
function viewTitle() {
  if (S.day) { const d = new Date(S.day + 'T00:00'); return `${d.getMonth() + 1}월 ${d.getDate()}일 (${DAYS[d.getDay()]})`; }
  if (S.view === 'pubdoing') return '디스코드 발행 대상';
  if (S.view === 'pub') return '디스코드 공개 체크';
  if (S.view === 'today') return '오늘';
  if (S.view === 'week') return '이번 주 마감';
  if (S.area) return S.area;
  return S.status ? SMAP[S.status].name : '전체';
}
function rowEl(t) {
  const due = dayLabel(t.due), mine = (t.log || []).filter(l => !/스케줄러에 옮김|대기로 이동\(이전/.test(l.text)), last = mine.at(-1);
  const st = h('button', { class: 'st-btn', type: 'button', title: `${SMAP[t.status]?.name || '대기'} — 눌러서 다음 상태`, 'aria-label': '상태 바꾸기',
    onclick: e => { e.stopPropagation(); const order = ['todo', 'doing', 'review', 'done']; const i = order.indexOf(t.status); setStatus(t.id, order[(i + 1) % order.length] || 'doing'); } }, ring(t.status));
  const pick = h('input', { type: 'checkbox', class: 'pick', 'aria-label': '선택', onclick: e => { e.stopPropagation(); if (e.shiftKey && S.anchor) rangeSel(S.anchor, t.id); else toggleSel(t.id, e.target.checked); renderRows(); renderBulk(); } });
  pick.checked = S.sel.has(t.id);
  const el = h('div', { class: `row${S.open === t.id ? ' sel' : ''}${S.sel.has(t.id) ? ' picked' : ''}${t.status === 'done' ? ' done' : ''}`, role: 'listitem', tabindex: '-1', 'data-id': t.id,
    onclick: e => {
      if (e.ctrlKey || e.metaKey) { toggleSel(t.id); renderRows(); renderBulk(); return; }
      if (e.shiftKey && S.anchor) { rangeSel(S.anchor, t.id); renderRows(); renderBulk(); return; }
      // 같은 줄을 0.4초 안에 두 번 누르면 더블클릭: 체크(선택) 토글
      const now = Date.now();
      if (S.lastClick && S.lastClick.id === t.id && now - S.lastClick.at < 400) {
        S.lastClick = null; window.getSelection()?.removeAllRanges(); toggleSel(t.id); renderRows(); renderBulk(); return;
      }
      S.lastClick = { id: t.id, at: now };
      openTask(t.id);
    } },
    pick, st,
    h('span', { class: `flag${t.priority === 'low' ? ' low' : ''}`, title: t.priority ? PRI[t.priority] : '' }, t.priority === 'high' ? '▲' : t.priority === 'low' ? '▽' : ''),
    h('span', { class: 'title' }, t.title || '(제목 없음)', t.public ? h('span', { class: 'pub-badge', title: '디스코드 공개' + (t.pubTitle ? ' · ' + t.pubTitle : '') }, '공개') : null),
    S.group !== 'area' && t.area ? h('span', { class: 'tag' }, t.area) : h('span'),
    h('span', { class: `note${last && last.by === 'claude' ? ' ai' : ''}`, title: last ? last.text : '' }, last ? '●' : ''),
    h('span', { class: 'dt' }),
    h('span', { class: 'upd', title: '마지막 수정 ' + when(t.updated) }, shortDate(t.updated)));
  el.draggable = true;
  el.addEventListener('dragstart', e => {
    const ids = S.sel.has(t.id) ? [...S.sel] : [t.id];
    e.dataTransfer.setData('application/x-real-ids', JSON.stringify(ids)); e.dataTransfer.setData('text/plain', ids.length + '건'); e.dataTransfer.effectAllowed = 'move';
    el.classList.add('dragging');
  });
  el.addEventListener('dragend', () => el.classList.remove('dragging'));
  return el;
}
function renderRows() {
  const list = visible();
  $('#ltitle').textContent = viewTitle();
  $('#lcount').textContent = `${list.length}건`;
  $('#groupseg').replaceChildren(...[['area', '분류별'], ['status', '상태별'], ['none', '묶지 않음']].map(([k, n]) =>
    h('button', { type: 'button', 'aria-pressed': S.group === k ? 'true' : 'false', onclick: () => { S.group = k; store.set('sched.group', k); renderRows(); } }, n)));
  const box = $('#rows'), keep = box.scrollTop;
  if (!list.length) {
    box.replaceChildren(h('div', { class: 'empty' }, h('b', null, S.q ? '검색 결과가 없습니다' : '여기는 비어 있습니다'), S.q ? '다른 낱말로 찾아보세요.' : '위의 입력칸에 할 일을 적고 Enter를 누르면 추가됩니다.'));
    return;
  }
  const out = [];
  for (const g of groups(list)) {
    const closed = !!S.collapsed[S.group + ':' + g.key];
    if (S.group !== 'none') {
      const all = g.items.every(x => S.sel.has(x.id)), some = g.items.some(x => S.sel.has(x.id));
      const gp = h('input', { type: 'checkbox', class: 'pick', 'aria-label': `${g.key} 전체 선택`, onclick: e => { e.stopPropagation(); for (const x of g.items) toggleSel(x.id, e.target.checked); renderRows(); renderBulk(); } });
      gp.checked = all; gp.indeterminate = some && !all;
      out.push(h('div', { class: 'ghead-wrap' }, gp, h('button', { class: 'ghead', type: 'button', 'aria-expanded': closed ? 'false' : 'true',
        onclick: () => { S.collapsed[S.group + ':' + g.key] = !closed; store.set('sched.collapsed', S.collapsed); renderRows(); } },
        h('span', { class: 'chev', 'aria-hidden': 'true' }, '▾'), g.key, h('span', { class: 'c' }, g.items.length))));
    }
    if (!closed) out.push(...g.items.map(rowEl));
  }
  box.replaceChildren(...out);
  box.scrollTop = keep;
}

// ---------- 상세 창
function openTask(id) { S.open = id; S.focus = id; renderRows(); renderPane(true); }
function closeTask() { S.open = null; renderRows(); renderPane(true); }
function renderPane(fresh) {
  const pane = $('#pane'); if (!pane) return;
  const t = S.open && find(S.tasks, S.open);
  document.querySelector('.scrim')?.remove();
  if (!t) {
    if (S.open) { S.open = null; toast('다른 곳에서 삭제된 작업입니다.'); }
    pane.classList.add('idle');
    return renderOverview(pane);
  }
  pane.classList.remove('idle');
  if (matchMedia('(max-width: 1180px)').matches) document.body.append(h('div', { class: 'scrim', onclick: closeTask }));
  const a = document.activeElement;
  if (!fresh && pane.contains(a) && a.matches('input, textarea, select')) { refreshLog(t); refreshStatus(t); return; }
  const keep = pane.querySelector('.p-body')?.scrollTop || 0;
  const bind = (field, el, tf = v => v, label) => {
    let timer;
    const go = () => { clearTimeout(timer); const v = tf(el.value), cur = find(S.tasks, t.id); if (cur && (cur[field] ?? '') !== v) patchTask(t.id, { [field]: v }, `"${cur.title}" ${label} 수정`); };
    el.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(go, 900); });
    el.addEventListener('change', go); el.addEventListener('blur', go);
  };
  const title = h('textarea', { class: 'f-title', rows: 1, 'aria-label': '제목', placeholder: '작업 제목' }); title.value = t.title || '';
  const fit = () => { title.style.height = 'auto'; title.style.height = title.scrollHeight + 'px'; };
  title.addEventListener('input', fit); title.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.isComposing) { e.preventDefault(); title.blur(); } });
  bind('title', title, v => v.trim(), '제목');
  const inp = (id, type, v, field, label, tf) => { const el = h('input', { id, type, autocomplete: 'off' }); el.value = v || ''; bind(field, el, tf, label); return el; };
  const pri = h('select', { id: 'f-pri' }, Object.entries(PRI).map(([k, v]) => h('option', { value: k }, v))); pri.value = t.priority || 'normal'; bind('priority', pri, v => v, '중요도');
  const area = inp('f-area', 'text', t.area, 'area', '분류', v => v.trim()); area.setAttribute('list', 'areas'); area.placeholder = '분류 없음';
  const detail = h('textarea', { class: 'f-detail', id: 'f-detail', placeholder: '무엇을, 어디까지 할지 적어 두세요.' }); detail.value = t.detail || ''; bind('detail', detail, v => v, '내용');
  const memo = h('textarea', { placeholder: '진행 상황이나 지시를 남깁니다', 'aria-label': '기록 남기기' });
  const addMemo = () => { const v = memo.value.trim(); if (!v) return; memo.value = ''; addLog(t.id, v); };
  memo.addEventListener('keydown', e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); addMemo(); } });
  pane.replaceChildren(
    h('div', { class: 'p-head' }, h('span', { class: 'id' }, t.id), h('span', { class: 'grow' }),
      h('button', { class: 'ibtn', type: 'button', title: '닫기 (Esc)', 'aria-label': '닫기', onclick: closeTask }, icon('close', 16))),
    h('div', { class: 'p-body' },
      title,
      h('div', { class: 'stseg', id: 'stseg', role: 'group', 'aria-label': '상태' }),
      h('div', { class: 'stages', id: 'stages', 'aria-label': '단계별 날짜' }),
      h('div', { class: 'props' },
        h('label', { for: 'f-start' }, '시작일'), inp('f-start', 'date', t.start, 'start', '시작일'),
        h('label', { for: 'f-pri' }, '중요도'), pri,
        h('label', { for: 'f-area' }, '분류'), area,
        h('label', { for: 'f-pub' }, '디스코드'), (() => {
          const cb = h('input', { type: 'checkbox', id: 'f-pub', class: 'pub-cb' }); cb.checked = !!t.public;
          cb.addEventListener('change', () => patchTask(t.id, { public: cb.checked }, `"${t.title}" 디스코드 ${cb.checked ? '공개' : '비공개'}`));
          return h('label', { class: 'pub-row', for: 'f-pub' }, cb, h('span', null, '진행 중일 때 개발 현황 채널에 공개'));
        })(),
        h('label', { for: 'f-pubtitle' }, '공개 제목'), (() => { const el = inp('f-pubtitle', 'text', t.pubTitle, 'pubTitle', '공개 제목', v => v.trim()); el.placeholder = '비우면 제목 그대로'; return el; })(),
        h('datalist', { id: 'areas' }, [...new Set(S.tasks.map(x => x.area).filter(Boolean))].map(v => h('option', { value: v })))),
      h('div', null, h('div', { class: 'blk-label' }, '내용'), detail),
      h('div', null, h('div', { class: 'blk-label' }, '진행 기록'), h('div', { class: 'timeline', id: 'log' })),
      h('div', { class: 'memo' }, memo, h('div', { class: 'r' }, h('span', null, 'Ctrl+Enter'), h('button', { class: 'btn', type: 'button', onclick: addMemo }, '기록 남기기')))),
    h('div', { class: 'p-foot' }, h('button', { class: 'btn danger', type: 'button', onclick: () => removeTask(t.id) }, '삭제'), h('span', { class: 'grow' }), h('span', null, '수정 ' + when(t.updated))));
  attachResizer(pane);
  // 높이가 바뀌는 것(제목·내용 칸 맞춤, 기록·상태)을 먼저 끝낸 뒤 스크롤 위치를 되돌린다(위로 튀지 않게)
  fit(); const fitDetail = () => { const y = pane.querySelector('.p-body').scrollTop; detail.style.height = 'auto'; detail.style.height = Math.min(Math.max(150, detail.scrollHeight + 2), Math.round(window.innerHeight * 0.4)) + 'px'; pane.querySelector('.p-body').scrollTop = y; }; fitDetail(); detail.addEventListener('input', fitDetail);
  refreshLog(t); refreshStatus(t);
  pane.querySelector('.p-body').scrollTop = fresh ? 0 : keep;
  if (fresh && !t.title) title.focus();
}
function attachResizer(pane) {
  const grip = h('div', { class: 'resizer', role: 'separator', 'aria-orientation': 'vertical', 'aria-label': '상세 창 폭 조절', title: '끌어서 폭 조절 · 더블클릭: 기본 폭(창의 약 절반)' });
  grip.addEventListener('pointerdown', e => {
    e.preventDefault(); grip.setPointerCapture(e.pointerId); document.body.classList.add('resizing');
    const move = ev => setPaneWidth(window.innerWidth - ev.clientX);
    const up = () => { grip.removeEventListener('pointermove', move); grip.removeEventListener('pointerup', up); document.body.classList.remove('resizing'); store.set('sched.paneW', S.paneW); };
    grip.addEventListener('pointermove', move); grip.addEventListener('pointerup', up);
  });
  grip.addEventListener('dblclick', () => { store.del('sched.paneW'); setPaneWidth(defaultPaneW()); });
  pane.prepend(grip);
}
function defaultPaneW() { return Math.round(window.innerWidth * 0.48); }  // 아키텍트 기준 화면(2000px에서 약 950px)
function setPaneWidth(w) {
  const max = Math.max(320, Math.min(1100, window.innerWidth - 560));
  S.paneW = Math.round(Math.max(320, Math.min(max, w)));
  document.documentElement.style.setProperty('--pane-w', S.paneW + 'px');
}
function refreshStages(t) {
  const box = $('#stages'); if (!box) return;
  const flow = ['todo', 'doing', 'review', 'done'].concat((t.stages || {}).hold || t.status === 'hold' ? ['hold'] : []);
  box.replaceChildren(...flow.map((k, i) => {
    const d = stageDate(t, k), cur = (t.status || 'todo') === k;
    return h('div', { class: `stage${d ? ' on' : ''}${cur ? ' cur' : ''}`, css: { '--c': SMAP[k].c } }, i ? h('span', { class: 'arrow', 'aria-hidden': 'true' }, '›') : null,
      h('span', { class: 'sdot' }), h('span', { class: 'sn' }, SMAP[k].name), h('span', { class: 'sd' }, d ? ((t.stages || {})[k] ? when(d) : shortDate(d)) : '—'));
  }));
}
function refreshStatus(t) {
  refreshStages(t);
  const row = $('#stseg'); if (!row) return;
  row.replaceChildren(...STATUS.map(s => h('button', { type: 'button', css: { '--c': s.c }, 'aria-pressed': (t.status || 'todo') === s.k ? 'true' : 'false', onclick: () => setStatus(t.id, s.k) }, ring(s.k, '12px'), s.name)));
}
function refreshLog(t) {
  const box = $('#log'); if (!box) return;
  const log = [...(t.log || [])].reverse();
  box.replaceChildren(...(log.length ? log.map(l => l.kind === 'change'
    ? h('div', { class: `ev chg${l.by === 'claude' ? ' ai' : ''}` }, h('div', { class: 'chg-line' }, h('span', { class: 'chg-t' }, l.text), h('span', { class: 'chg-w' }, when(l.at))))
    : h('div', { class: `ev${l.by === 'claude' ? ' ai' : ''}` },
    h('div', { class: 'meta' }, h('b', null, l.by === 'claude' ? 'AI' : '나'), when(l.at)), h('div', { class: 'txt' }, l.text)))
    : [h('div', { class: 'ev' }, h('div', { class: 'txt' }, '아직 기록이 없습니다.'))]));
}
function renderOverview(pane) {
  const n = S.tasks.length || 1, cnt = k => S.tasks.filter(t => (t.status || 'todo') === k).length;
  const today = todayStr();
  pane.replaceChildren(h('div', { class: 'overview' },
    h('div', null, h('h2', null, '한눈에 보기'), h('p', null, '목록에서 작업을 고르면 여기에 상세가 열립니다.')),
    h('div', { class: 'stat' },
      h('div', null, h('b', null, cnt('doing')), h('span', null, ring('doing', '10px'), '진행 중')),
      h('div', null, h('b', null, cnt('review')), h('span', null, ring('review', '10px'), '확인 대기')),
      h('div', null, h('b', null, cnt('todo')), h('span', null, ring('todo', '10px'), '대기')),
      h('div', null, h('b', null, cnt('hold')), h('span', null, ring('hold', '10px'), '보류'))),
    h('div', null, h('div', { class: 'blk-label' }, `상태 비율 · 전체 ${S.tasks.length}건`),
      h('div', { class: 'bar' }, STATUS.map(s => h('i', { css: { '--c': s.c, width: (cnt(s.k) / n * 100) + '%' }, title: `${s.name} ${cnt(s.k)}` })))),
    h('div', null, h('div', { class: 'blk-label' }, '오늘 시작한 작업'), h('p', null, `${S.tasks.filter(t => t.start === today).length}건`)),
    h('div', null, h('div', { class: 'blk-label' }, '단축키'),
      h('div', { class: 'keys' }, h('span', { class: 'kbd' }, 'N'), '할 일 추가', h('span', { class: 'kbd' }, '/'), '검색',
        h('span', { class: 'kbd' }, '↑ ↓'), '목록 이동', h('span', { class: 'kbd' }, 'Enter'), '상세 열기',
        h('span', { class: 'kbd' }, '더블클릭'), '체크(선택)', h('span', { class: 'kbd' }, '1~5'), '상태: 대기·진행·확인·보류·완료', h('span', { class: 'kbd' }, 'Del'), '삭제(선택한 것 전부)', h('span', { class: 'kbd' }, 'X'), '선택', h('span', { class: 'kbd' }, 'Esc'), '닫기'))));
  attachResizer(pane);
}
function rangeSel(a, b) {
  const ids = visibleIds(), i = ids.indexOf(a), j = ids.indexOf(b);
  if (i < 0 || j < 0) return toggleSel(b, true);
  for (const id of ids.slice(Math.min(i, j), Math.max(i, j) + 1)) S.sel.add(id);
  S.anchor = b;
}
function areaPicker() {
  const areas = [...new Set(S.tasks.map(x => x.area).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'ko'));
  const sel = h('select', { class: 'bulk-area', 'aria-label': '분류 지정' },
    h('option', { value: '', disabled: true, selected: true }, '분류 지정…'),
    ...areas.map(a => h('option', { value: a }, a)), h('option', { value: '__none' }, '분류 없음'), h('option', { value: '__new' }, '+ 새 분류'));
  sel.onchange = () => {
    const ids = [...S.sel];
    if (sel.value === '__new') {
      const inp = h('input', { class: 'bulk-new', placeholder: '새 분류 이름 후 Enter', 'aria-label': '새 분류 이름' });
      inp.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.isComposing && inp.value.trim()) bulkPatch(ids, { area: inp.value.trim() }, `분류 ${inp.value.trim()}`); else if (e.key === 'Escape') renderBulk(); e.stopPropagation(); });
      sel.replaceWith(inp); inp.focus(); return;
    }
    bulkPatch(ids, { area: sel.value === '__none' ? '' : sel.value }, sel.value === '__none' ? '분류 없음' : `분류 ${sel.value}`);
  };
  return sel;
}
function renderBulk() {
  const bar = $('#bulk'); if (!bar) return;
  for (const id of [...S.sel]) if (!find(S.tasks, id)) S.sel.delete(id);
  const n = S.sel.size;
  bar.hidden = !n; if (!n) return;
  let armed = false;
  const del = h('button', { class: 'btn danger', type: 'button' }, `삭제 ${n}건`);
  del.onclick = () => { if (!armed) { armed = true; del.textContent = '한 번 더 누르면 삭제'; setTimeout(() => { armed = false; del.textContent = `삭제 ${n}건`; }, 3000); return; } bulkDelete(); };
  bar.replaceChildren(
    h('span', { class: 'bulk-n' }, h('b', null, n), '개 선택'),
    h('span', { class: 'bulk-sep' }),
    h('span', { class: 'bulk-l' }, '진행도'),
    ...STATUS.map(s => h('button', { class: 'bulk-st', type: 'button', title: `${n}건을 ${s.name}(으)로`, onclick: () => bulkStatus(s.k) }, ring(s.k, '12px'), s.name)),
    h('span', { class: 'bulk-sep' }),
    h('button', { class: 'bulk-st', type: 'button', onclick: () => bulkPatch([...S.sel], { public: true }, '디스코드 공개') }, '공개'),
    h('button', { class: 'bulk-st', type: 'button', onclick: () => bulkPatch([...S.sel], { public: false }, '디스코드 비공개') }, '비공개'),
    h('span', { class: 'bulk-sep' }),
    areaPicker(),
    h('span', { class: 'bulk-sep' }),
    del,
    h('button', { class: 'btn', type: 'button', onclick: () => { S.sel.clear(); renderRows(); renderBulk(); } }, '선택 해제'));
}
function render() { if (!$('#rows')) return; renderSide(); renderUsage(); renderRows(); renderBulk(); renderPane(false); }

// ---------- 토큰 안내 (저장하려면 Contents 쓰기 권한 토큰 필요)
function showTokenBox(reason) {
  const box = $('#tokenbox'); if (!box) return;
  const inp = h('input', { type: 'password', placeholder: 'GitHub 토큰 붙여넣기 (github_pat_…)', autocomplete: 'off', 'aria-label': 'GitHub 토큰' });
  const save = h('button', { class: 'btn', type: 'button' }, '저장');
  save.onclick = async () => {
    const v = inp.value.trim(); if (!v) return;
    const r = await fetch(`https://api.github.com/repos/${REPO}`, { headers: { Authorization: `Bearer ${v}`, Accept: 'application/vnd.github+json' } });
    if (!r.ok) { toast(`GitHub가 토큰을 거절했습니다 (${r.status})`); return; }
    const j = await r.json();
    if (!j.permissions || !j.permissions.push) { toast('이 토큰은 저장소에 쓸 권한이 없습니다. Contents: Read and write를 주세요.'); return; }
    await tokenSet(v); S.token = v; box.hidden = true; toast('토큰을 저장했습니다'); flush();
  };
  box.replaceChildren(h('span', null, (reason ? reason + ' — ' : '') + '변경을 저장하려면 hati0101/dash 저장소에 Contents: Read and write 권한이 있는 GitHub 토큰이 필요합니다.'), inp, save);
  box.hidden = false;
}

// ---------- 잠금
async function boot() {
  const th = store.get('theme'); if (th) document.documentElement.dataset.theme = th;
  S.group = store.get('sched.group', 'area'); S.collapsed = store.get('sched.collapsed', {}) || {};
  setPaneWidth(store.get('sched.paneW', null) ?? defaultPaneW());
  window.addEventListener('resize', () => setPaneWidth(store.get('sched.paneW', null) ?? defaultPaneW()));
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
async function enter() {
  $('#lock').hidden = true; $('#app').hidden = false;
  S.token = await tokenGet();
  shell();
  try { await pull(); S.syncText = S.token ? '최신 상태' : '읽기 전용'; } catch (e) { S.syncText = '불러오기 실패: ' + e.message; S.syncKind = 'err'; }
  render();
  pullUsage();
  setInterval(pullUsage, 300000);
  setInterval(async () => {  // 다른 기기 변경 확인
    if (S.saving || S.queue.length || document.hidden) return;
    try { if (await pull()) render(); } catch { /* 다음에 다시 */ }
  }, 20000);
  document.addEventListener('visibilitychange', async () => { if (!document.hidden && !S.saving && !S.queue.length) { try { if (await pull()) render(); } catch { /* 무시 */ } } });
}

// ---------- 키보드
function moveFocus(dir) {
  const rows = [...document.querySelectorAll('#rows .row')]; if (!rows.length) return;
  const cur = rows.findIndex(r => r.dataset.id === (S.open || S.focus));
  const next = rows[Math.max(0, Math.min(rows.length - 1, cur < 0 ? 0 : cur + dir))];
  openTask(next.dataset.id);
  document.querySelector(`#rows .row[data-id="${next.dataset.id}"]`)?.scrollIntoView({ block: 'nearest' });
}
document.addEventListener('keydown', e => {
  if (!$('#rows')) return;
  const typing = !!(e.target.matches && e.target.matches('input, textarea, select'));
  if (e.key === 'Escape') { if (typing) e.target.blur(); else if (S.sel.size) { S.sel.clear(); renderRows(); renderBulk(); } else if (S.open) closeTask(); return; }
  if (!typing && (e.ctrlKey || e.metaKey) && e.code === 'KeyA') { e.preventDefault(); for (const id of visibleIds()) S.sel.add(id); renderRows(); renderBulk(); return; }
  if (typing || e.ctrlKey || e.metaKey || e.altKey) return;
  if (e.key === 'Delete') {
    e.preventDefault();
    if (S.sel.size) { bulkDelete(); return; }
    if (S.open) {
      const ids = visibleIds(), i = ids.indexOf(S.open), next = ids[i + 1] || ids[i - 1];
      removeTask(S.open);
      if (next && find(S.tasks, next)) openTask(next);
    }
    return;
  }
  if (e.code === 'KeyX') { const id = S.open || S.focus; if (id) { toggleSel(id); renderRows(); renderBulk(); } return; }
  if (e.key === '/') { e.preventDefault(); $('#q').focus(); }
  else if (e.code === 'KeyN') { e.preventDefault(); $('#addinput').focus(); }
  else if (e.key === 'ArrowDown' || e.key === 'j') { e.preventDefault(); moveFocus(1); }
  else if (e.key === 'ArrowUp' || e.key === 'k') { e.preventDefault(); moveFocus(-1); }
  else if (e.key === 'Enter' && S.focus) { e.preventDefault(); openTask(S.focus); }
  else if (/^[1-5]$/.test(e.key) && S.open) { e.preventDefault(); setStatus(S.open, STATUS[+e.key - 1].k); }
});
window.addEventListener('beforeunload', e => { if (S.queue.length || S.saving) { e.preventDefault(); e.returnValue = ''; } });
boot();
