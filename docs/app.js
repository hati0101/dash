'use strict';
/* REAL 운영체제 대시보드 — 브라우저에서 복호화 후 렌더링. 외부 요청 없음. */

// ------------------------------------------------------------ 기본 유틸
const $ = (s, r = document) => r.querySelector(s);
const store = {
  get(k, d = null) { try { const v = localStorage.getItem('realops.' + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem('realops.' + k, JSON.stringify(v)); } catch { /* 저장 불가 환경 */ } },
  del(k) { try { localStorage.removeItem('realops.' + k); } catch { /* 무시 */ } },
};

function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  if (attrs) {
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === 'class') el.className = v;
      else if (k === 'text') el.textContent = v;
      else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
      else if (k === 'style' && typeof v === 'object') for (const [p, x] of Object.entries(v)) el.style.setProperty(p, x);
      else el.setAttribute(k, v === true ? '' : v);
    }
  }
  append(el, kids);
  return el;
}
function append(el, kids) {
  for (const k of kids.flat(Infinity)) {
    if (k == null || k === false) continue;
    el.append(k instanceof Node ? k : document.createTextNode(String(k)));
  }
  return el;
}

const ICON_PATHS = {
  overview: '<rect x="3.5" y="3.5" width="7" height="7" rx="1.8"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.8"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.8"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.8"/>',
  topics: '<path d="M9.5 18h5M10.5 21h3"/><path d="M12 3a6 6 0 0 0-3.6 10.8c.7.6 1.1 1.3 1.1 2.2h5c0-.9.4-1.6 1.1-2.2A6 6 0 0 0 12 3z"/>',
  tasks: '<path d="M10 6.5h10M10 12h10M10 17.5h10"/><path d="M3.8 6.5l1.4 1.4 2.3-2.4M3.8 12l1.4 1.4 2.3-2.4M3.8 17.5l1.4 1.4 2.3-2.4"/>',
  messages: '<path d="M4 5.5h16v11H9l-5 4z"/>',
  verify: '<path d="M12 3l7.5 3v5.6c0 4.4-3.2 8.2-7.5 9.4-4.3-1.2-7.5-5-7.5-9.4V6z"/><path d="M8.8 12l2.3 2.3 4.2-4.6"/>',
  brain: '<path d="M12 5.2A3 3 0 0 0 6.8 6a3 3 0 0 0-2.4 4.2A3.2 3.2 0 0 0 5.6 16a3 3 0 0 0 3.9 3.3A2.6 2.6 0 0 0 12 18z"/><path d="M12 5.2A3 3 0 0 1 17.2 6a3 3 0 0 1 2.4 4.2 3.2 3.2 0 0 1-1.2 5.8 3 3 0 0 1-3.9 3.3A2.6 2.6 0 0 1 12 18z"/><path d="M12 5.2V18"/>',
  sources: '<path d="M9 3.5v4.5M15 3.5v4.5"/><path d="M7 8h10v3a5 5 0 0 1-10 0z"/><path d="M12 16v4.5"/>',
  bell: '<path d="M6 16v-5a6 6 0 1 1 12 0v5l1.5 2h-15z"/><path d="M10 20.5a2 2 0 0 0 4 0"/>',
  search: '<circle cx="11" cy="11" r="6.5"/><path d="M16 16l4 4"/>',
  lock: '<rect x="5" y="11" width="14" height="9.5" rx="2"/><path d="M8.5 11V8a3.5 3.5 0 0 1 7 0v3"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2.5 12h2M19.5 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  moon: '<path d="M19.5 14.5A7.5 7.5 0 0 1 9.5 4.5a7.5 7.5 0 1 0 10 10z"/>',
  refresh: '<path d="M19.5 11A7.5 7.5 0 0 0 6 6.8L4.5 8.5M4.5 4.5v4h4M4.5 13A7.5 7.5 0 0 0 18 17.2l1.5-1.7M19.5 19.5v-4h-4"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  inbox: '<path d="M4 13l2.5-7h11L20 13v6H4z"/><path d="M4 13h4.5l1 2h5l1-2H20"/>',
  alert: '<path d="M12 3.5l9 16h-18z"/><path d="M12 10v4M12 17v.5"/>',
  play: '<path d="M8 5.5l10.5 6.5L8 18.5z"/>',
  eye: '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3"/>',
  flask: '<path d="M9 3.5h6M10 3.5v5.5l-5 8.8A1.8 1.8 0 0 0 6.6 20.5h10.8a1.8 1.8 0 0 0 1.6-2.7L14 9V3.5"/><path d="M7.5 14.5h9"/>',
  done: '<circle cx="12" cy="12" r="8.5"/><path d="M8.5 12l2.5 2.5 4.5-5"/>',
  clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
  scale: '<path d="M12 4v16M6 20h12M5.5 7.5h13"/><path d="M5.5 7.5L3 13a2.6 2.6 0 0 0 5 0zM18.5 7.5L16 13a2.6 2.6 0 0 0 5 0z"/>',
  calendar: '<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 10h16M9 3v4M15 3v4"/>',
  file: '<path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5"/>',
  menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
  x: '<path d="M6 6l12 12M18 6L6 18"/>',
  arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  send: '<path d="M4 12l16-8-6 16-2.5-6.5z"/><path d="M11.5 13.5L20 4"/>',
  copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3"/>',
  pause: '<rect x="6.5" y="5" width="3.5" height="14" rx="1"/><rect x="14" y="5" width="3.5" height="14" rx="1"/>',
  user: '<circle cx="12" cy="8.5" r="3.5"/><path d="M5 20a7 7 0 0 1 14 0"/>',
  link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
};
function icon(name) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('fill', 'none');
  svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', '1.8');
  svg.setAttribute('stroke-linecap', 'round');
  svg.setAttribute('stroke-linejoin', 'round');
  svg.setAttribute('aria-hidden', 'true');
  svg.innerHTML = ICON_PATHS[name] || '';
  return svg;
}

// ------------------------------------------------------------ 시간·이름
const DAY = ['일', '월', '화', '수', '목', '금', '토'];
const pad = n => String(n).padStart(2, '0');
const toMs = ts => (ts ? Date.parse(ts) : NaN);
function fmtAbs(ts, dateOnly = false) {
  const t = toMs(ts); if (isNaN(t)) return '—';
  const d = new Date(t);
  return dateOnly ? `${pad(d.getMonth() + 1)}.${pad(d.getDate())}` : `${pad(d.getMonth() + 1)}.${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
function fmtRel(ts) {
  const t = toMs(ts); if (isNaN(t)) return '기록 없음';
  const s = (Date.now() - t) / 1000;
  if (s < 0) return '방금';
  if (s < 90) return '방금';
  if (s < 3600) return `${Math.round(s / 60)}분 전`;
  if (s < 86400) return `${Math.round(s / 3600)}시간 전`;
  if (s < 86400 * 14) return `${Math.round(s / 86400)}일 전`;
  return fmtAbs(ts, true);
}
const hoursSince = ts => (Date.now() - toMs(ts)) / 36e5;

const PEOPLE = {
  user: { name: '나', full: '사용자', role: '목표·우선순위·실게임 판단', ini: '나' },
  claude: { name: 'Claude', full: 'Claude', role: '사령탑 · 분배·통합', ini: 'C' },
  astra: { name: 'Astra', full: 'Astra (Codex)', role: '보조 검증 · 백그라운드 시험', ini: 'A' },
  cli: { name: 'CLI', full: 'Claude CLI 작업자', role: '지정 사본 구현·조사', ini: 'W' },
  dashboard: { name: '대시보드', full: '대시보드', role: '자동 기록', ini: 'D' },
};
const person = id => PEOPLE[id] || { name: id || '?', full: id || '?', role: '', ini: (id || '?').slice(0, 1).toUpperCase() };
function av(id, small) {
  const p = person(id);
  const known = PEOPLE[id] ? id : 'cli';
  return h('span', { class: `av ${known}${small ? ' sm' : ''}`, title: p.full, 'aria-label': p.full }, p.ini);
}

const STAGES = [
  { id: 'request', label: '요청', icon: 'inbox' },
  { id: 'progress', label: '진행', icon: 'play' },
  { id: 'validating', label: '검증', icon: 'eye' },
  { id: 'user_test', label: '테스트 대기', icon: 'flask' },
  { id: 'blocked', label: '막힘', icon: 'alert' },
  { id: 'done', label: '완료', icon: 'done' },
];
const STAGE = Object.fromEntries(STAGES.map(s => [s.id, s]));
function stChip(stage) {
  const s = STAGE[stage] || { label: stage || '?', icon: 'clock' };
  return h('span', { class: `st ${STAGE[stage] ? stage : 'neutral'}` }, icon(s.icon), s.label);
}
const TOPIC_STATES = [
  { id: 'new', label: '새 주제', cls: 'request', icon: 'topics' },
  { id: 'triage', label: '검토 중', cls: 'validating', icon: 'eye' },
  { id: 'ready', label: '준비됨', cls: 'done', icon: 'file' },
  { id: 'active', label: '진행 중', cls: 'progress', icon: 'play' },
  { id: 'done', label: '완료', cls: 'done', icon: 'done' },
  { id: 'parked', label: '보류', cls: 'neutral', icon: 'pause' },
];
const TOPIC = Object.fromEntries(TOPIC_STATES.map(s => [s.id, s]));
function topicChip(state) {
  const s = TOPIC[state] || TOPIC.new;
  return h('span', { class: `st ${s.cls}` }, icon(s.icon), s.label);
}
const NOTE_KIND = { triage: '분배', memo: '메모', review: '검토', plan: '진행 베이스', question: '질문', answer: '답변', status: '상태' };
const LEDGER_ST = {
  pass: { label: '통과', cls: 'done', icon: 'done' }, pending: { label: '대기', cls: 'user_test', icon: 'clock' },
  fail: { label: '실패', cls: 'blocked', icon: 'alert' }, reverted: { label: '되돌림', cls: 'blocked', icon: 'refresh' },
  note: { label: '기록', cls: 'neutral', icon: 'file' },
};
const priChip = p => (p ? h('span', { class: `pri ${p}` }, p) : null);

// ------------------------------------------------------------ 상태
const S = {
  env: null, key: null, data: null, d: null,
  view: 'overview', q: '',
  f: { owner: 'all', window: '24h', msg: 'all', ledger: 'all', taskOwner: 'all', taskWait: 'all' },
  msgSel: null,
  acks: new Set(store.get('acks', [])),
};

// ------------------------------------------------------------ 암호
const b64 = {
  dec(s) { s = s.replace(/-/g, '+').replace(/_/g, '/'); while (s.length % 4) s += '='; const b = atob(s); const u = new Uint8Array(b.length); for (let i = 0; i < b.length; i++) u[i] = b.charCodeAt(i); return u; },
  enc(u8, url) { let s = ''; for (let i = 0; i < u8.length; i++) s += String.fromCharCode(u8[i]); s = btoa(s); return url ? s.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '') : s; },
};
async function deriveKey(pw, saltB64, iter, extractable) {
  const base = await crypto.subtle.importKey('raw', new TextEncoder().encode(pw), 'PBKDF2', false, ['deriveKey']);
  return crypto.subtle.deriveKey({ name: 'PBKDF2', hash: 'SHA-256', salt: b64.dec(saltB64), iterations: iter },
    base, { name: 'AES-GCM', length: 256 }, extractable, ['encrypt', 'decrypt']);
}
async function openEnvelope(env, key) {
  const pt = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: b64.dec(env.iv) }, key, b64.dec(env.data));
  let bytes = pt;
  if (env.gzip) bytes = await new Response(new Blob([pt]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer();
  return JSON.parse(new TextDecoder().decode(bytes));
}
async function sealTopic(obj) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, S.key, new TextEncoder().encode(JSON.stringify(obj))));
  return ['REALTOPIC1', b64.enc(b64.dec(S.env.salt), true), b64.enc(iv, true), b64.enc(ct, true)].join('.');
}
async function fetchEnvelope() {
  const r = await fetch('data.enc.json?t=' + Date.now(), { cache: 'no-store' });
  if (!r.ok) throw new Error('데이터 파일을 받지 못했습니다 (' + r.status + ')');
  return r.json();
}

// ------------------------------------------------------------ 잠금
async function boot() {
  const theme = store.get('theme');
  if (theme) document.documentElement.dataset.theme = theme;
  const msg = $('#lock-msg');
  $('#lock-form').addEventListener('submit', unlock);
  if (!window.isSecureContext || !crypto.subtle) { msg.textContent = 'HTTPS(또는 localhost)에서만 열 수 있습니다.'; return; }
  try {
    S.env = await fetchEnvelope();
    $('#lock-published').textContent = '마지막 게시 ' + fmtAbs(S.env.published_at) + ' (' + fmtRel(S.env.published_at) + ')';
  } catch (e) { msg.textContent = e.message; return; }
  const saved = store.get('key');
  if (saved && saved.salt === S.env.salt) {
    try {
      S.key = await crypto.subtle.importKey('raw', b64.dec(saved.k), 'AES-GCM', false, ['encrypt', 'decrypt']);
      S.data = await openEnvelope(S.env, S.key);
      return enterApp();
    } catch { store.del('key'); S.key = null; }
  }
  $('#remember').checked = !!store.get('rememberPref', false);
  $('#pw').focus();
}
async function unlock(ev) {
  ev.preventDefault();
  const pw = $('#pw').value, remember = $('#remember').checked, btn = $('#unlock'), msg = $('#lock-msg');
  if (!pw || !S.env) return;
  btn.disabled = true; msg.className = 'lock-msg ok'; msg.textContent = '여는 중…';
  try {
    const key = await deriveKey(pw, S.env.salt, S.env.iter, remember);
    S.data = await openEnvelope(S.env, key);
    if (remember) {
      store.set('key', { salt: S.env.salt, k: b64.enc(new Uint8Array(await crypto.subtle.exportKey('raw', key))) });
      S.key = await crypto.subtle.importKey('raw', new Uint8Array(await crypto.subtle.exportKey('raw', key)), 'AES-GCM', false, ['encrypt', 'decrypt']);
    } else { store.del('key'); S.key = key; }
    store.set('rememberPref', remember);
    $('#pw').value = '';
    enterApp();
  } catch {
    msg.className = 'lock-msg'; msg.textContent = '비밀번호가 맞지 않습니다.';
    btn.disabled = false; $('#pw').select();
  }
}
function lockNow() {
  store.del('key'); S.key = null; S.data = null; S.d = null;
  $('#app').replaceChildren(); $('#app').hidden = true; $('#lock').hidden = false;
  $('#lock-msg').textContent = ''; $('#unlock').disabled = false;
  closeDrawer(true);
  $('#pw').focus();
}

// ------------------------------------------------------------ 파생 계산
const REQ_RE = /assign|request|요청|배정|gate|question|질문|correction|review|검토/i;
function derive(data) {
  const L = data.meta.limits || {};
  const staleH = L.stale_hours || 24, unansH = L.unanswered_hours || 6;
  const tasks = data.tasks.map(t => {
    const age = hoursSince(t.updated_at);
    return { ...t, _age: age, _stale: !['done', 'user_test'].includes(t.stage) && age > staleH, _waitLong: t.stage === 'user_test' && age > 72 };
  });
  const msgs = data.messages;
  const unprocessed = msgs.filter(m => m.unprocessed);
  const unanswered = msgs.filter(m => m.box === 'inbox-astra' && m.sender === 'claude' && !m.replies.length && !(m.followups || []).length
    && REQ_RE.test((m.kind || '') + ' ' + m.title) && hoursSince(m.ts) > unansH && hoursSince(m.ts) < 72);
  const topics = (data.topics || []).map(t => ({ ...t, _age: hoursSince(t.created_at) }));

  const missed = [];
  if (unprocessed.length) {
    const latest = unprocessed[0];
    missed.push({ key: `unprocessed:${latest.id}:${unprocessed.length}`, level: 'warn', icon: 'inbox',
      title: `Astra → Claude 미처리 수신 ${unprocessed.length}건`, sub: `가장 최근: ${latest.title}`, go: () => go('messages', { msg: 'unprocessed' }) });
  }
  if (unanswered.length) missed.push({ key: `unanswered:${unanswered[0].id}:${unanswered.length}`, level: 'warn', icon: 'messages',
    title: `Astra 답장 없는 요청 ${unanswered.length}건 (최근 3일)`, sub: `가장 최근: ${unanswered[0].title}`, go: () => go('messages', { msg: 'unanswered' }) });
  for (const id of data.meta.ack_pending || []) missed.push({ key: `ack:${id}`, level: 'warn', icon: 'clock',
    title: `수신 확인(ACK) 대기: ${id}`, sub: 'tasks.json 기록 기준', go: () => go('messages') });
  for (const t of tasks.filter(t => t._stale)) missed.push({ key: `stale:${t.id}:${t.updated_at}`, level: 'bad', icon: 'alert',
    title: `멈춘 작업: ${t.title}`, sub: `${Math.round(t._age)}시간 동안 갱신 없음 · ${STAGE[t.stage]?.label || t.stage}`, go: () => openTask(t) });
  for (const t of tasks.filter(t => t._waitLong)) missed.push({ key: `usertest:${t.id}:${t.updated_at}`, level: 'warn', icon: 'flask',
    title: `사용자 테스트 대기 ${Math.round(t._age / 24)}일째: ${t.title}`, sub: t.next_action || '', go: () => openTask(t) });
  for (const c of data.meta.conflicts || []) missed.push({ key: `conflict:${c.id}`, level: 'bad', icon: 'alert',
    title: `기록 충돌: ${c.id}`, sub: `${c.authors.join(' · ')}가 같은 작업을 기록`, go: () => go('sources') });
  for (const s of data.sources.filter(s => !s.ok && !/선택/.test(s.error || ''))) missed.push({ key: `source:${s.id}:${s.error}`, level: 'bad', icon: 'sources',
    title: `출처 오류: ${s.name}`, sub: s.error, go: () => go('sources') });
  for (const t of topics.filter(t => t.status === 'new' && t._age > 12)) missed.push({ key: `topic:${t.id}`, level: 'warn', icon: 'topics',
    title: `분배되지 않은 주제: ${t.title}`, sub: `${Math.round(t._age)}시간 경과`, go: () => openTopic(t) });

  const lastBy = who => msgs.find(m => m.sender === who)?.ts || null;
  return { tasks, unprocessed, unanswered, missed, topics, lastBy };
}
const openMissed = () => S.d.missed.filter(m => !S.acks.has(m.key));
function ack(keys) { for (const k of [].concat(keys)) S.acks.add(k); store.set('acks', [...S.acks].slice(-500)); render(); }
function filterTasks(list, owner) {
  if (!owner || owner === 'all') return list;
  if (owner === 'user') return list.filter(t => t.waiting_on === 'user' || t.owner === 'user');
  return list.filter(t => t.owner === owner || t.waiting_on === owner || (owner === 'cli' && /cli/i.test(t.implementer || '')));
}

// ------------------------------------------------------------ 앱 골격
const NAV = [
  { id: 'overview', label: '개요', icon: 'overview' },
  { id: 'topics', label: '주제', icon: 'topics' },
  { id: 'tasks', label: '업무', icon: 'tasks' },
  { id: 'messages', label: '메시지', icon: 'messages' },
  { id: 'verify', label: '검증', icon: 'verify' },
  { id: 'brain', label: '세컨드 브레인', icon: 'brain' },
  { id: 'sources', label: '연결', icon: 'sources' },
];

function enterApp() {
  S.d = derive(S.data);
  $('#lock').hidden = true;
  $('#app').hidden = false;
  readHash();
  render();
  if (!S.timer) S.timer = setInterval(refresh, 5 * 60 * 1000);
}
async function refresh(manual) {
  try {
    const env = await fetchEnvelope();
    if (env.published_at === S.env?.published_at) { if (manual) toast('이미 최신입니다 · 게시 ' + fmtRel(env.published_at)); render(); return; }
    if (env.salt !== S.env.salt) { S.env = env; toast('비밀번호가 바뀌었습니다. 다시 열어주세요.'); return lockNow(); }
    S.env = env; S.data = await openEnvelope(env, S.key); S.d = derive(S.data);
    render(); toast('새 데이터를 반영했습니다');
  } catch (e) { if (manual) toast('갱신 실패: ' + e.message); }
}
function readHash() {
  const [v, qs] = location.hash.replace(/^#\/?/, '').split('?');
  if (NAV.some(n => n.id === v)) S.view = v;
  if (qs) { const q = new URLSearchParams(qs).get('q'); if (q != null) S.q = q; }
}
function go(view, opts = {}) {
  S.view = view;
  if (opts.msg) S.f.msg = opts.msg;
  if (opts.stage) S.f.stage = opts.stage;
  if (opts.q != null) S.q = opts.q;
  history.replaceState(null, '', '#/' + view + (view === 'brain' && S.q ? '?q=' + encodeURIComponent(S.q) : ''));
  $('.side')?.classList.remove('on');
  render();
  window.scrollTo({ top: 0 });
}

function render() {
  if (!S.data) return;
  const app = $('#app');
  const keepScroll = window.scrollY;
  app.replaceChildren(sidebar(), h('div', { class: 'main' }, topbar(), page()));
  if (S._keepScroll) window.scrollTo({ top: keepScroll });
  S._keepScroll = false;
}

function sidebar() {
  const d = S.d, data = S.data;
  const badges = {
    topics: d.topics.filter(t => t.status === 'new').length || null,
    tasks: d.tasks.filter(t => t.stage !== 'done').length,
    messages: d.unprocessed.length || null,
    sources: data.sources.filter(s => !s.ok && !/선택/.test(s.error || '')).length || null,
  };
  const hot = { topics: true, messages: true, sources: true };
  const srcRows = data.sources.filter(s => !/선택/.test(s.error || '') || s.count).map(s => {
    const stale = s.last_modified && hoursSince(s.last_modified) > 48;
    return h('button', { class: 'src-row', title: `${s.name} · ${s.count}건 · ${fmtRel(s.last_modified)}`, onclick: () => go('sources') },
      h('span', { class: 'src-name' }, s.name), h('span', { class: `dot${!s.ok ? ' bad' : stale ? ' warn' : ''}`, 'aria-label': !s.ok ? '오류' : stale ? '오래됨' : '정상' }));
  });
  return h('nav', { class: 'side', 'aria-label': '주 메뉴' },
    h('div', { class: 'side-brand' }, h('span', { class: 'brand-mark', 'aria-hidden': 'true' }), data.meta.project || 'REAL 운영체제'),
    NAV.map(n => h('button', { class: 'nav-btn', 'aria-current': S.view === n.id ? 'page' : null, onclick: () => go(n.id) },
      icon(n.icon), n.label, badges[n.id] ? h('span', { class: `badge${hot[n.id] ? ' hot' : ''}` }, badges[n.id]) : null)),
    h('div', { class: 'side-h' }, 'SOURCES'),
    srcRows,
    h('div', { class: 'side-h' }, 'TEAM'),
    h('div', { class: 'team-row' }, ['user', 'claude', 'astra', 'cli'].map(id => av(id))),
    h('div', { class: 'side-foot' },
      h('div', { class: 'row' }, av('user'), h('b', null, '내 계정'),
        h('button', { class: 'icon-btn', style: { 'margin-left': 'auto' }, title: '테마 바꾸기', 'aria-label': '테마 바꾸기', onclick: toggleTheme },
          icon(document.documentElement.dataset.theme === 'light' ? 'moon' : 'sun')),
        h('button', { class: 'icon-btn', title: '잠그기', 'aria-label': '잠그기', onclick: lockNow }, icon('lock'))),
      h('div', { class: 'muted', style: { 'font-size': '11.5px' } }, `생성 ${fmtAbs(data.meta.generated_at)} · ${fmtRel(data.meta.generated_at)}`)));
}
function toggleTheme() {
  const next = document.documentElement.dataset.theme === 'light' ? 'dark' : 'light';
  document.documentElement.dataset.theme = next; store.set('theme', next); render();
}

function topbar() {
  const gen = S.data.meta.generated_at, age = hoursSince(gen);
  const nav = NAV.find(n => n.id === S.view);
  const missed = openMissed().length;
  const search = h('input', { type: 'search', placeholder: '검색', 'aria-label': '전체 검색', value: S.view === 'brain' ? S.q : '',
    onkeydown: e => { if (e.key === 'Enter') go('brain', { q: e.target.value }); } });
  return h('header', { class: 'top' },
    h('button', { class: 'icon-btn menu-btn', 'aria-label': '메뉴', onclick: () => $('.side').classList.toggle('on') }, icon('menu')),
    h('div', { class: 'crumb' }, icon('overview'), '워크스페이스', h('span', null, '›'), h('b', null, nav?.label)),
    h('label', { class: 'top-search' }, icon('search'), search, h('span', { class: 'kbd' }, 'Ctrl K')),
    h('span', { class: `live${age > 1.5 ? ' stale' : ''}`, title: '데이터 생성 ' + fmtAbs(gen) },
      h('span', { class: 'dot' }), h('span', { class: 'lbl' }, age > 1.5 ? fmtRel(gen) + ' 갱신' : 'live')),
    h('button', { class: 'icon-btn', title: '새 데이터 확인', 'aria-label': '새 데이터 확인', onclick: () => refresh(true) }, icon('refresh')),
    h('button', { class: 'icon-btn bell', title: `놓친 항목 ${missed}`, 'aria-label': `놓친 항목 ${missed}건`, onclick: () => { go('overview'); setTimeout(() => $('#missed')?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 50); } },
      icon('bell'), missed ? h('span', { class: 'count' }, missed) : null));
}

function page() {
  const views = { overview: vOverview, topics: vTopics, tasks: vTasks, messages: vMessages, verify: vVerify, brain: vBrain, sources: vSources };
  return h('div', { class: 'page' }, (views[S.view] || vOverview)());
}
function head(eyebrow, title, small, ...tools) {
  return h('div', { class: 'page-head' },
    h('div', null, h('div', { class: 'eyebrow' }, eyebrow), h('h1', null, title, small ? h('small', null, small) : null)),
    tools.length ? h('div', { class: 'tools' }, tools) : null);
}
function chips(options, value, onPick, label) {
  return h('div', { class: 'chip-group', role: 'group', 'aria-label': label },
    options.map(([v, text, extra]) => h('button', { 'aria-pressed': String(value === v), onclick: () => onPick(v) }, extra || null, text)));
}
function card(title, opts, ...body) {
  const { big, unit, right, cls, id, accent } = opts || {};
  return h('section', { class: `card ${cls || ''}`, id },
    h('div', { class: 'card-h' }, h('h2', null, title),
      big != null ? h('span', { class: `big${accent ? ' accent' : ''}` }, big) : null, unit ? h('span', { class: 'unit' }, unit) : null,
      right ? h('div', { class: 'right' }, right) : null),
    body);
}
const empty = text => h('div', { class: 'empty' }, text);

// ------------------------------------------------------------ 개요
function vOverview() {
  const d = S.d, data = S.data, now = new Date();
  const tasks = filterTasks(d.tasks, S.f.owner);
  const total = tasks.length, done = tasks.filter(t => t.stage === 'done').length;
  const pct = total ? Math.round(done / total * 100) : 0;
  const ownerChips = chips([['all', '전체'], ['claude', 'Claude', av('claude', true)], ['astra', 'Astra', av('astra', true)], ['user', '나', av('user', true)]],
    S.f.owner, v => { S.f.owner = v; render(); }, '담당 필터');

  return [
    head('OVERVIEW', '전체 현황', `${pad(now.getMonth() + 1)}.${pad(now.getDate())} (${DAY[now.getDay()]})`, ownerChips),
    h('div', { class: 'grid g-4' },
      completionCard(pct, done, total - done, tasks),
      collectedCard(),
      pipelineCard(tasks),
      missedCard()),
    h('div', { class: 'grid g-2 section-gap' }, todayCard(), decisionsNeededCard()),
    h('div', { class: 'section-gap' }, card('진행 중인 프로젝트', { big: tasks.filter(t => t.stage !== 'done').length, unit: '건' },
      projGrid(tasks.filter(t => t.stage !== 'done').sort(taskSort)))),
    h('div', { class: 'grid g-2 section-gap' }, blockedCard(tasks), weekCard(tasks)),
    h('div', { class: 'section-gap' }, card('팀 현황', null, teamGrid())),
    h('div', { class: 'section-gap' }, card('최근 활동', { right: h('button', { class: 'btn', onclick: () => go('messages') }, '메시지 전체', icon('arrow')) }, timeline(40))),
  ];
}
const PRI_ORDER = { P0: 0, P1: 1, P2: 2, P3: 3 };
const STAGE_ORDER = { blocked: 0, progress: 1, request: 2, validating: 3, user_test: 4, done: 5 };
function taskSort(a, b) {
  return (PRI_ORDER[a.priority] ?? 9) - (PRI_ORDER[b.priority] ?? 9) || STAGE_ORDER[a.stage] - STAGE_ORDER[b.stage] || toMs(b.updated_at) - toMs(a.updated_at);
}

function completionCard(pct, done, left, tasks) {
  const r = 52, C = 2 * Math.PI * r;
  const ring = h('div', { class: 'ring', role: 'img', 'aria-label': `완료율 ${pct}퍼센트` });
  ring.innerHTML = `<svg viewBox="0 0 132 132"><circle class="track" cx="66" cy="66" r="${r}" fill="none" stroke-width="12"/>` +
    `<circle class="val" cx="66" cy="66" r="${r}" fill="none" stroke-width="12" stroke-linecap="round" stroke-dasharray="${C.toFixed(2)}" stroke-dashoffset="${C.toFixed(2)}"/></svg>`;
  ring.append(h('div', { class: 'pct' }, h('b', null, pct, h('small', null, '%'))));
  requestAnimationFrame(() => requestAnimationFrame(() => { const v = ring.querySelector('.val'); if (v) v.style.strokeDashoffset = (C * (1 - pct / 100)).toFixed(2); }));
  const waiting = tasks.filter(t => t.stage === 'user_test').length;
  return card('Completion', null,
    h('div', { class: 'ring-wrap' }, ring,
      h('div', { class: 'kv' }, h('div', null, h('div', { class: 'k' }, 'DONE'), h('div', { class: 'v' }, done)),
        h('div', null, h('div', { class: 'k' }, 'LEFT'), h('div', { class: 'v' }, left)))),
    h('div', { class: 'foot-note' }, waiting ? `실게임 대기 ${waiting}건은 완료로 세지 않습니다.` : '실게임 확인 전에는 완료로 세지 않습니다.'));
}

function inWindow(ts, hours, dateOnly) {
  let t = toMs(ts); if (isNaN(t)) return false;
  if (dateOnly) t += 86399e3;
  return Date.now() - t <= hours * 36e5;
}
function collectedCard() {
  const data = S.data, hours = S.f.window === '24h' ? 24 : 24 * 7;
  const rows = [
    { label: 'Astra → Claude', n: data.messages.filter(m => m.sender === 'astra' && inWindow(m.ts, hours)).length, c: 's1', ini: 'A', go: () => go('messages', { msg: 'a2c' }) },
    { label: 'Claude → Astra', n: data.messages.filter(m => m.sender === 'claude' && inWindow(m.ts, hours)).length, c: 's2', ini: 'C', go: () => go('messages', { msg: 'c2a' }) },
    { label: 'QA 검증', n: data.validations.filter(v => inWindow(v.ts, hours)).length, c: 's3', ini: 'Q', go: () => go('verify') },
    { label: '감사 원장', n: data.ledger.filter(e => inWindow(e.ts, hours, !e.has_time)).length, c: 's4', ini: 'L', go: () => go('verify') },
    { label: '인계 묶음', n: data.handoffs.filter(x => inWindow(x.ts, hours)).length, c: 's5', ini: 'H', go: () => go('sources') },
    { label: '메모리·결정', n: data.memory.filter(x => inWindow(x.ts, hours)).length + data.decisions.filter(x => inWindow(x.date, hours, true)).length, c: 's6', ini: 'M', go: () => go('brain') },
  ];
  const total = rows.reduce((a, r) => a + r.n, 0), max = Math.max(1, ...rows.map(r => r.n));
  return card('Collected', { big: total, unit: '건', right: chips([['24h', '24h'], ['7d', '7일']], S.f.window, v => { S.f.window = v; render(); }, '수집 기간') },
    h('div', { class: 'bars' }, rows.map(r => h('button', { class: 'bar-row', onclick: r.go, 'aria-label': `${r.label} ${r.n}건` },
      h('span', { class: 'ico-dot', style: { background: `var(--${r.c})` } }, r.ini),
      h('span', { class: 'lbl' }, r.label),
      h('span', { class: 'track-bar' }, h('i', { style: { width: (r.n / max * 100) + '%', background: `var(--${r.c})` } })),
      h('span', { class: 'n' }, r.n)))));
}
function pipelineCard(tasks) {
  const active = tasks.filter(t => t.stage !== 'done').length;
  const max = Math.max(1, ...STAGES.map(s => tasks.filter(t => t.stage === s.id).length));
  return card('Pipeline', { big: active, accent: true, unit: '진행 중' },
    h('div', { class: 'bars' }, STAGES.map(s => {
      const n = tasks.filter(t => t.stage === s.id).length;
      return h('button', { class: 'bar-row', onclick: () => go('tasks', { stage: s.id }), 'aria-label': `${s.label} ${n}건` },
        h('span', { style: { color: `var(--st-${s.id})`, display: 'grid' } }, icon(s.icon)),
        h('span', { class: 'lbl' }, s.label),
        h('span', { class: 'track-bar' }, h('i', { style: { width: (n / max * 100) + '%', background: `var(--st-${s.id})` } })),
        h('span', { class: 'n' }, n));
    })));
}
function missedCard() {
  const items = openMissed();
  return card('Missed', { id: 'missed', big: items.length, unit: '건',
    right: items.length ? h('button', { class: 'icon-btn', title: '모두 확인', 'aria-label': '놓친 항목 모두 확인', onclick: () => ack(items.map(i => i.key)) }, icon('check')) : null },
    items.length ? h('div', { class: 'list' }, items.slice(0, 6).map(missedItem), items.length > 6 ? h('div', { class: 'empty' }, `외 ${items.length - 6}건`) : null)
      : empty('놓친 항목이 없습니다.'));
}
function missedItem(i) {
  return h('div', { class: 'item' },
    h('span', { class: `lead-ico ${i.level}` }, icon(i.icon)),
    h('button', { class: 'body', style: { border: '0', background: 'none', 'text-align': 'left', padding: '0', color: 'inherit' }, onclick: i.go },
      h('div', { class: 't clamp-2' }, i.title), i.sub ? h('div', { class: 's clamp-2' }, i.sub) : null),
    h('button', { class: 'icon-btn ack-btn', title: '확인함', 'aria-label': '확인함으로 표시', onclick: () => ack(i.key) }, icon('check')));
}

function todayCard() {
  const d = S.d, data = S.data;
  const items = [];
  for (const a of data.user_actions) items.push({ ico: 'user', lv: 'warn', t: a.title, s: a.detail, who: 'user', when: a.since, go: () => a.task_id && openTaskById(a.task_id) });
  for (const t of d.tasks.filter(t => t.priority === 'P0' && t.stage !== 'done')) items.push({ ico: 'alert', lv: 'bad', t: `P0 · ${t.title}`, s: t.next_action, who: t.waiting_on || t.owner, when: t.updated_at, go: () => openTask(t) });
  for (const t of d.topics.filter(t => t.status === 'new')) items.push({ ico: 'topics', lv: '', t: `새 주제 · ${t.title}`, s: '분배 대기', who: 'claude', when: t.created_at, go: () => openTopic(t) });
  const fresh = d.unprocessed.filter(m => hoursSince(m.ts) < 24);
  if (fresh.length) items.push({ ico: 'inbox', lv: '', t: `Astra 보고 ${fresh.length}건 확인`, s: fresh[0].title, who: 'claude', when: fresh[0].ts, go: () => go('messages', { msg: 'unprocessed' }) });
  return card('오늘 확인할 일', { big: items.length, unit: '건' },
    items.length ? h('div', { class: 'list' }, items.map(i => h('button', { class: 'item', onclick: i.go },
      h('span', { class: `lead-ico ${i.lv}` }, icon(i.ico)),
      h('span', { class: 'body' }, h('div', { class: 't' }, i.t), i.s ? h('div', { class: 's clamp-2' }, i.s) : null,
        h('div', { class: 'meta' }, h('span', { class: 'wait' }, av(i.who, true), person(i.who).name), h('span', { class: 'when' }, fmtRel(i.when)))))))
      : empty('오늘 확인할 일이 없습니다.'));
}
function decisionsNeededCard() {
  const list = S.data.decisions_needed;
  return card('결정이 필요한 문제', { big: list.length, unit: '건' },
    list.length ? h('div', { class: 'list' }, list.map(q => h('div', { class: 'item' },
      h('span', { class: 'lead-ico warn' }, icon('scale')),
      h('div', { class: 'body' }, h('div', { class: 't' }, q.question),
        q.options?.length ? h('div', { class: 's' }, '선택지: ' + q.options.join(' / ')) : null,
        q.recommendation ? h('div', { class: 's' }, h('b', null, '권장 '), q.recommendation) : null,
        h('div', { class: 'meta' }, h('span', { class: 'wait' }, av(q.owner || 'user', true), (person(q.owner || 'user').name) + ' 결정'),
          h('span', { class: 'tag' }, `${q._author} 제기`), h('span', { class: 'when' }, fmtRel(q.since)))))))
      : empty('지금 결정할 문제가 없습니다.'));
}
function projGrid(tasks) {
  if (!tasks.length) return empty('해당하는 작업이 없습니다.');
  return h('div', { class: 'proj-grid' }, tasks.map(projCard));
}
function projCard(t) {
  const rel = S.data.messages.filter(m => m.task_id === t.id).length;
  return h('button', { class: 'proj', onclick: () => openTask(t) },
    h('div', { class: 'row' }, priChip(t.priority), stChip(t.stage), t.area ? h('span', { class: 'tag' }, t.area) : null,
      t._stale ? h('span', { class: 'st blocked' }, icon('clock'), '멈춤') : null),
    h('div', { class: 'ttl' }, t.title),
    t.next_action ? h('div', { class: 'next clamp-3' }, t.next_action) : null,
    h('div', { class: 'foot' }, av(t.owner, true), t.waiting_on ? h('span', { class: 'wait' }, '대기: ', person(t.waiting_on).name) : null,
      rel ? h('span', null, `메시지 ${rel}`) : null, h('span', { style: { 'margin-left': 'auto' } }, fmtRel(t.updated_at))));
}
function blockedCard(tasks) {
  const list = tasks.filter(t => t.stage === 'blocked' || t._stale).sort(taskSort);
  return card('막힌 업무', { big: list.length, unit: '건' },
    list.length ? h('div', { class: 'list' }, list.map(t => h('button', { class: 'item', onclick: () => openTask(t) },
      h('span', { class: 'lead-ico bad' }, icon('alert')),
      h('span', { class: 'body' }, h('div', { class: 't' }, t.title),
        h('div', { class: 's' }, t.stage === 'blocked' ? '막힘으로 기록됨' : `${Math.round(t._age)}시간 갱신 없음`, ' · ', t.next_action || '다음 행동 미기록'),
        h('div', { class: 'meta' }, priChip(t.priority), stChip(t.stage), av(t.owner, true))))))
      : empty('막힌 업무가 없습니다.'));
}
function weekCard(tasks) {
  const list = tasks.filter(t => t.due && t.stage !== 'done' && toMs(t.due) - Date.now() < 7 * 864e5).sort((a, b) => toMs(a.due) - toMs(b.due));
  return card('이번 주 마감', { big: list.length, unit: '건' },
    list.length ? h('div', { class: 'list' }, list.map(t => {
      const days = Math.ceil((toMs(t.due) - Date.now()) / 864e5);
      return h('button', { class: 'item', onclick: () => openTask(t) },
        h('span', { class: `lead-ico ${days < 0 ? 'bad' : days <= 1 ? 'warn' : ''}` }, icon('calendar')),
        h('span', { class: 'body' }, h('div', { class: 't' }, t.title),
          h('div', { class: 'meta' }, h('span', { class: 'tag' }, fmtAbs(t.due, true) + (days < 0 ? ` · ${-days}일 지남` : days === 0 ? ' · 오늘' : ` · D-${days}`)), stChip(t.stage), av(t.owner, true))));
    })) : empty('마감일이 정해진 작업이 없습니다. 직접 기록 파일의 due로 지정할 수 있습니다.'));
}
function teamGrid() {
  const d = S.d, data = S.data;
  const owned = id => d.tasks.filter(t => t.owner === id && t.stage !== 'done').length;
  const waiting = id => d.tasks.filter(t => t.waiting_on === id && t.stage !== 'done').length;
  const lastVal = data.validations[0]?.ts;
  const members = [
    { id: 'user', stats: [[data.user_actions.length, '할 일'], [data.decisions_needed.length, '결정'], [waiting('user'), '대기 작업']], last: null, lastLabel: '실게임·결정 담당' },
    { id: 'claude', stats: [[owned('claude'), '담당'], [waiting('claude'), '내 차례'], [d.unprocessed.length, '미처리']], last: d.lastBy('claude') },
    { id: 'astra', stats: [[owned('astra'), '담당'], [waiting('astra'), '차례'], [d.unanswered.length, '답장 대기']], last: d.lastBy('astra') },
    { id: 'cli', stats: [[d.tasks.filter(t => /cli/i.test(t.implementer || '') && t.stage !== 'done').length, '구현'], [data.validations.length, 'QA'], [data.validations.filter(v => v.live === 'pending').length, '실게임 전']], last: lastVal, lastLabel: '최근 QA' },
  ];
  return h('div', { class: 'team' }, members.map(m => h('div', { class: 'member' },
    h('div', { class: 'hd' }, av(m.id), h('div', null, h('div', { class: 'nm' }, person(m.id).full), h('div', { class: 'rl' }, person(m.id).role))),
    h('div', { class: 'stats' }, m.stats.map(([n, l]) => h('div', null, h('b', null, n), h('span', null, l)))),
    h('div', { class: 'muted', style: { 'font-size': '12px' } }, m.last ? `${m.lastLabel || '마지막 메시지'} ${fmtRel(m.last)}` : (m.lastLabel || '활동 기록 없음')))));
}
function timelineEvents() {
  const data = S.data, ev = [];
  for (const m of data.messages.slice(0, 80)) ev.push({ ts: m.ts, who: m.sender, color: `var(--who-${PEOPLE[m.sender] ? m.sender : 'cli'})`, t: m.title, s: `${person(m.sender).name} → ${person(m.recipient).name}${m.kind ? ' · ' + m.kind : ''}`, go: () => openMessage(m) });
  for (const v of data.validations) ev.push({ ts: v.ts, color: v.result === 'fail' ? 'var(--st-blocked)' : 'var(--st-done)', t: `QA ${v.result === 'fail' ? '실패' : '통과'} · ${v.id}`, s: v.reviewer || '', go: () => openValidation(v) });
  for (const e of data.ledger.slice(0, 40)) ev.push({ ts: e.ts, dateOnly: !e.has_time, color: `var(--st-${({ pass: 'done', pending: 'user_test', fail: 'blocked', reverted: 'blocked' })[e.status] || 'request'})`, t: e.title, s: '감사 원장 · ' + LEDGER_ST[e.status].label, go: () => openLedger(e) });
  for (const x of data.handoffs) ev.push({ ts: x.ts, color: 'var(--s5)', t: '인계 묶음 · ' + x.id, s: x.kind === 'dir' ? '폴더' : '파일', go: () => go('sources') });
  for (const m of data.memory) ev.push({ ts: m.ts, color: 'var(--who-claude)', t: '메모리 갱신 · ' + m.id, s: m.description, go: () => openMemory(m) });
  for (const t of S.d.topics) ev.push({ ts: t.created_at, color: 'var(--accent)', t: '새 주제 · ' + t.title, s: TOPIC[t.status]?.label, go: () => openTopic(t) });
  return ev.filter(e => !isNaN(toMs(e.ts))).sort((a, b) => toMs(b.ts) - toMs(a.ts));
}
function timeline(n) {
  const ev = timelineEvents().slice(0, n);
  if (!ev.length) return empty('활동 기록이 없습니다.');
  return h('div', { class: 'tl' }, ev.map(e => h('button', { class: 'tl-item', onclick: e.go },
    h('span', { class: 'tm' }, e.dateOnly ? fmtAbs(e.ts, true) : fmtAbs(e.ts)),
    h('span', { class: 'pip' }, h('i', { style: { background: e.color } })),
    h('span', { class: 'tx' }, h('b', { class: 'clamp-2' }, e.t), e.s ? h('div', { class: 's clamp-2' }, e.s) : null))));
}

// ------------------------------------------------------------ 주제
function vTopics() {
  const d = S.d, repo = S.data.meta.repo;
  const pending = (store.get('pendingTopics', []) || []).filter(p => !d.topics.some(t => t.id === p.id));
  store.set('pendingTopics', pending);
  return [
    head('TOPICS', '주제 보드', null),
    h('div', { class: 'grid g-3' },
      h('div', { class: 'span-2' }, composerCard(repo)),
      card('흐름', null, h('ol', { class: 'hint', style: { margin: '0', 'padding-left': '18px', display: 'grid', gap: '6px' } },
        h('li', null, h('b', null, '보내기'), ' — 주제를 적고 보내면 암호문만 GitHub 이슈로 올라갑니다.'),
        h('li', null, h('b', null, '가져오기'), ' — PC에서 ', h('span', { class: 'mono' }, 'topics.py pull'), '이 복호화해 주제 폴더를 만듭니다.'),
        h('li', null, h('b', null, '분배'), ' — Claude(사령탑)가 검토해 Claude/Astra에 배정합니다.'),
        h('li', null, h('b', null, '진행 베이스'), ' — 담당자가 목표·범위·입력·첫 단계·위험·완료 기준을 씁니다.'),
        h('li', null, h('b', null, '교차 검토'), ' — 다른 쪽이 검토 메모를 남기고, 게시하면 여기 보입니다.')))),
    pending.length ? h('div', { class: 'section-gap' }, card('이 기기에서 보낸 주제 · 가져오기 대기', { big: pending.length, unit: '건' },
      h('div', { class: 'list' }, pending.map(p => h('div', { class: 'item' },
        h('span', { class: 'lead-ico' }, icon('send')),
        h('div', { class: 'body' }, h('div', { class: 't' }, p.title), h('div', { class: 's' }, `${p.id} · ${fmtRel(p.created_at)} · PC에서 topics.py pull 후 반영`)),
        h('button', { class: 'icon-btn', title: '목록에서 지우기', 'aria-label': '목록에서 지우기', onclick: () => { store.set('pendingTopics', pending.filter(x => x.id !== p.id)); render(); } }, icon('x'))))))) : null,
    h('div', { class: 'section-gap board topics' }, TOPIC_STATES.map(s => {
      const list = d.topics.filter(t => (t.status || 'new') === s.id).sort((a, b) => toMs(b.updated_at || b.created_at) - toMs(a.updated_at || a.created_at));
      return h('div', { class: 'col' }, h('div', { class: 'col-h' }, topicChip(s.id), h('span', { class: 'badge' }, list.length)),
        list.length ? list.map(topicCard) : h('div', { class: 'empty' }, '없음'));
    })),
  ];
}
function composerCard(repo) {
  const title = h('input', { id: 'tp-title', placeholder: '주제 (예: 거래소 검색 속도 개선)', maxlength: '120', required: true });
  const body = h('textarea', { id: 'tp-body', placeholder: '대략적인 내용·배경·원하는 결과. 정리 안 된 메모여도 됩니다.' });
  const kind = h('select', { id: 'tp-kind', 'aria-label': '유형' }, ['기능·개선', '버그', '조사·분석', '디자인', '운영·도구', '기타'].map(k => h('option', null, k)));
  const pri = h('select', { id: 'tp-pri', 'aria-label': '우선순위' }, ['P2 보통', 'P1 높음', 'P0 긴급', 'P3 낮음'].map(k => h('option', { value: k.slice(0, 2) }, k)));
  const prefer = h('select', { id: 'tp-prefer', 'aria-label': '담당 선호' }, [['auto', '자동 분배'], ['claude', 'Claude 우선'], ['astra', 'Astra 우선']].map(([v, l]) => h('option', { value: v }, l)));
  const status = h('div', { class: 'hint', role: 'status', 'aria-live': 'polite' });
  async function make() {
    if (!title.value.trim()) { title.focus(); status.textContent = '주제를 적어주세요.'; return null; }
    const now = new Date();
    const id = `T-${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${b64.enc(crypto.getRandomValues(new Uint8Array(3)), true).toLowerCase().replace(/[^a-z0-9]/g, 'x')}`;
    const topic = { id, title: title.value.trim(), body: body.value.trim(), kind: kind.value, priority: pri.value, prefer: prefer.value, created_at: now.toISOString(), from: 'dashboard' };
    return { topic, blob: await sealTopic(topic) };
  }
  function remember(topic) {
    const list = store.get('pendingTopics', []) || [];
    list.push({ id: topic.id, title: topic.title, created_at: topic.created_at });
    store.set('pendingTopics', list);
    title.value = ''; body.value = '';
  }
  const send = h('button', { class: 'btn primary', disabled: !repo, onclick: async () => {
    const r = await make(); if (!r) return;
    const issueBody = `REAL 운영체제 주제 (암호화됨 · 대시보드 비밀번호로만 열립니다)\n\n아래 줄을 수정하지 마세요.\n\n${r.blob}\n`;
    const url = `https://github.com/${repo}/issues/new?title=${encodeURIComponent('[topic] ' + r.topic.id)}&body=${encodeURIComponent(issueBody)}`;
    const w = window.open(url, '_blank', 'noopener');
    remember(r.topic);
    status.textContent = w ? 'GitHub 창에서 "Submit new issue"를 눌러야 전송됩니다.' : '팝업이 막혔습니다. 아래 "암호문 복사"를 써주세요.';
    S._keepScroll = true; render();
  } }, icon('send'), '보내기 (GitHub)');
  const copy = h('button', { class: 'btn', onclick: async () => {
    const r = await make(); if (!r) return;
    try { await navigator.clipboard.writeText(`python topics.py add-blob ${r.blob}`); remember(r.topic); toast('복사했습니다. PC 터미널에 붙여넣으세요.'); S._keepScroll = true; render(); }
    catch { status.textContent = '클립보드 복사가 막혔습니다.'; }
  } }, icon('copy'), '암호문 복사 (PC용)');
  return card('주제 던지기', null,
    h('div', { class: 'composer' }, title, body, h('div', { class: 'row' }, kind, pri, prefer),
      h('div', { class: 'row' }, send, copy),
      !repo ? h('div', { class: 'callout warn' }, h('b', null, 'GitHub 저장소가 아직 연결되지 않았습니다. '), '연결 전에는 "암호문 복사"로 PC에서 넣을 수 있습니다.') : null,
      status,
      h('div', { class: 'hint' }, '내용은 이 브라우저에서 대시보드 비밀번호 키로 암호화됩니다. 이슈에는 암호문과 주제 번호만 남습니다.')));
}
function topicCard(t) {
  const last = (t.notes || []).at(-1);
  return h('button', { class: 'proj', onclick: () => openTopic(t) },
    h('div', { class: 'row' }, priChip(t.priority), t.kind ? h('span', { class: 'tag' }, t.kind) : null, t.linked_task_id ? h('span', { class: 'tag' }, '작업 연결') : null),
    h('div', { class: 'ttl' }, t.title),
    t.body ? h('div', { class: 'next clamp-2' }, t.body) : null,
    last ? h('div', { class: 's clamp-2', style: { 'font-size': '12px', color: 'var(--ink-3)' } }, `${person(last.by).name} · ${NOTE_KIND[last.kind] || last.kind}: ${last.body}`) : null,
    h('div', { class: 'foot' }, t.assignee ? h('span', { class: 'wait' }, av(t.assignee, true), person(t.assignee).name) : h('span', { class: 'wait' }, '미배정'),
      t.turn ? h('span', { class: 'tag' }, `차례: ${person(t.turn).name}`) : null,
      (t.notes || []).length ? h('span', null, `메모 ${(t.notes || []).length}`) : null,
      h('span', { style: { 'margin-left': 'auto' } }, fmtRel(t.updated_at || t.created_at))));
}

// ------------------------------------------------------------ 업무
function vTasks() {
  const stageFocus = S.f.stage;
  const tasks = filterTasks(S.d.tasks, S.f.taskOwner);
  return [
    head('TASKS', '업무 보드', null,
      chips([['all', '전체'], ['claude', 'Claude'], ['astra', 'Astra'], ['cli', 'CLI'], ['user', '나 대기']], S.f.taskOwner, v => { S.f.taskOwner = v; render(); }, '담당 필터'),
      stageFocus ? h('button', { class: 'btn', onclick: () => { S.f.stage = null; render(); } }, icon('x'), STAGE[stageFocus].label + ' 강조 해제') : null),
    h('div', { class: 'board' }, STAGES.map(s => {
      const list = tasks.filter(t => t.stage === s.id).sort(taskSort);
      return h('div', { class: 'col', style: stageFocus && stageFocus !== s.id ? { opacity: '.45' } : null },
        h('div', { class: 'col-h' }, h('span', { style: { color: `var(--st-${s.id})`, display: 'grid' } }, icon(s.icon)), s.label, h('span', { class: 'badge' }, list.length)),
        list.length ? list.map(projCard) : h('div', { class: 'empty' }, '없음'));
    })),
    h('p', { class: 'hint section-gap' }, '단계는 tasks.json의 state와 직접 기록 파일(data/claude.json, data/astra.json)의 stage로 정합니다. 24시간 넘게 갱신이 없으면 "멈춤"으로 표시합니다.'),
  ];
}

// ------------------------------------------------------------ 메시지
function vMessages() {
  const all = S.data.messages;
  const f = S.f.msg;
  const filt = {
    all: () => true, a2c: m => m.sender === 'astra', c2a: m => m.sender === 'claude',
    unprocessed: m => m.unprocessed, unanswered: m => S.d.unanswered.includes(m),
  }[f] || (() => true);
  const list = all.filter(filt).slice(0, 300);
  if (!S.msgSel || !list.includes(S.msgSel)) S.msgSel = list[0] || null;
  const narrow = matchMedia('(max-width: 880px)').matches;
  return [
    head('MESSAGES', 'Claude ↔ Astra', `${all.length}건`,
      chips([['all', '전체'], ['a2c', 'Astra→Claude'], ['c2a', 'Claude→Astra'], ['unprocessed', `미처리 ${S.d.unprocessed.length}`], ['unanswered', `답장 대기 ${S.d.unanswered.length}`]], f, v => { S.f.msg = v; S.msgSel = null; render(); }, '메시지 필터')),
    h('div', { class: 'split' },
      h('div', { class: 'card msg-list', role: 'listbox', 'aria-label': '메시지 목록' },
        list.length ? list.map(m => h('button', { class: 'msg', role: 'option', 'aria-selected': String(m === S.msgSel),
          onclick: () => { if (narrow) return openMessage(m); S.msgSel = m; S._keepScroll = true; render(); } },
          m.unprocessed ? h('span', { class: 'new-dot', title: '미처리' }) : null,
          h('span', { class: 'route' }, av(m.sender, true), av(m.recipient, true)),
          h('span', { class: 'body' }, h('div', { class: 't clamp-2' }, m.title),
            h('div', { class: 's' }, h('span', null, fmtAbs(m.ts)), m.task_id ? h('span', { class: 'tag' }, m.task_id) : null,
              m.replies.length ? h('span', null, `답장 ${m.replies.length}`) : null))))
          : empty('해당 메시지가 없습니다.')),
      !narrow ? h('div', { class: 'card reader' }, S.msgSel ? messageDetail(S.msgSel) : empty('메시지를 선택하세요.')) : null),
  ];
}
function messageDetail(m) {
  const all = S.data.messages;
  const parent = m.in_reply_to ? all.find(x => x.id === m.in_reply_to) : null;
  const replies = m.replies.map(id => all.find(x => x.id === id)).filter(Boolean);
  const hdr = [['보낸이 → 받는이', `${person(m.sender).full} → ${person(m.recipient).full}`], ['시각', fmtAbs(m.ts)], ['message_id', m.id], ['kind', m.kind], ['task_id', m.task_id],
    ['in_reply_to', m.in_reply_to], ['파일', `${m.box}/${m.file}`], ...Object.entries(m.headers || {}).filter(([k]) => !['sender', 'recipient', 'kind', 'task_id', 'in_reply_to', 'route'].includes(k))];
  return [
    h('div', { class: 'row', style: { display: 'flex', gap: '6px', 'flex-wrap': 'wrap', 'margin-bottom': '8px' } },
      m.unprocessed ? h('span', { class: 'st progress' }, icon('inbox'), '미처리') : h('span', { class: 'st neutral' }, icon('check'), m.box === 'inbox-astra' ? '발신' : '처리됨'),
      priChip(m.priority), m.task_id ? h('button', { class: 'tag', style: { cursor: 'pointer' }, onclick: () => openTaskById(m.task_id) }, m.task_id) : null),
    h('h3', null, m.title),
    h('dl', { class: 'hdr-table' }, hdr.filter(([, v]) => v).map(([k, v]) => [h('dt', null, k), h('dd', null, v)])),
    h('pre', { class: 'pre' }, m.body || '(본문 없음)'),
    parent || replies.length ? h('div', { class: 'thread' }, h('h4', { class: 'eyebrow', style: { margin: '6px 0 2px' } }, '스레드'),
      parent ? threadRow(parent, '원문') : null, replies.map(r => threadRow(r, '답장'))) : null,
  ];
}
function threadRow(m, label) {
  return h('button', { class: 'msg', onclick: () => openMessage(m) },
    h('span', { class: 'route' }, av(m.sender, true), av(m.recipient, true)),
    h('span', { class: 'body' }, h('div', { class: 't clamp-2' }, m.title), h('div', { class: 's' }, label, ' · ', fmtAbs(m.ts))));
}

// ------------------------------------------------------------ 검증
function vVerify() {
  const data = S.data, f = S.f.ledger;
  const ledger = data.ledger.filter(e => f === 'all' || e.status === f);
  const counts = Object.fromEntries(Object.keys(LEDGER_ST).map(k => [k, data.ledger.filter(e => e.status === k).length]));
  return [
    head('VERIFY', '검증과 기록', null),
    card('QA 검증 결과', { big: data.validations.length, unit: '건' },
      data.validations.length ? h('div', { class: 'tbl-wrap' }, h('table', { class: 'tbl' },
        h('thead', null, h('tr', null, ['시각', '결과', '검증', '검토자', '실게임', '원인'].map(x => h('th', null, x)))),
        h('tbody', null, data.validations.map(v => h('tr', { class: 'click', tabindex: '0', onclick: () => openValidation(v), onkeydown: e => e.key === 'Enter' && openValidation(v) },
          h('td', { class: 'num', style: { 'white-space': 'nowrap' } }, fmtAbs(v.ts)),
          h('td', null, h('span', { class: `st ${v.result === 'pass' ? 'done' : v.result === 'fail' ? 'blocked' : 'neutral'}` }, icon(v.result === 'fail' ? 'alert' : 'done'), v.result === 'pass' ? '통과' : v.result === 'fail' ? '실패' : '불명')),
          h('td', null, h('b', null, v.id), h('div', { class: 'muted mono' }, v.job || '')),
          h('td', null, v.reviewer || '—'),
          h('td', null, v.live === 'pending' ? h('span', { class: 'st user_test' }, icon('flask'), '미실행') : '—'),
          h('td', null, v.root_cause || '—')))))) : empty('QA 결과가 없습니다.')),
    h('div', { class: 'section-gap' }, card('감사 원장', { big: ledger.length, unit: '건',
      right: chips([['all', '전체'], ['pending', `대기 ${counts.pending}`], ['fail', `실패 ${counts.fail}`], ['reverted', `되돌림 ${counts.reverted}`], ['pass', `통과 ${counts.pass}`]], f, v => { S.f.ledger = v; render(); }, '원장 필터') },
      h('div', { class: 'list' }, ledger.map(e => h('button', { class: 'item', onclick: () => openLedger(e) },
        h('span', { class: `lead-ico ${e.status === 'fail' || e.status === 'reverted' ? 'bad' : e.status === 'pending' ? 'warn' : e.status === 'pass' ? 'good' : ''}` }, icon(LEDGER_ST[e.status].icon)),
        h('span', { class: 'body' }, h('div', { class: 't' }, e.title), h('div', { class: 's clamp-2' }, e.body.replace(/^.*?\n/, '').slice(0, 260) || e.body.slice(0, 260))),
        h('span', { class: 'when' }, e.has_time ? fmtAbs(e.ts) : fmtAbs(e.ts, true))))),
      h('p', { class: 'hint' }, '원장의 대문자 상태어(PASS·PENDING·FAILED·REVERTED)로 분류했습니다. 분류는 참고용이며 원문이 기준입니다.'))),
  ];
}

// ------------------------------------------------------------ 세컨드 브레인
function corpus() {
  const data = S.data, c = [];
  for (const x of data.decisions) c.push({ kind: '결정', title: x.title, text: [x.decision, x.reason, (x.rejected || []).join(' '), x.source].join('\n'), when: x.date, open: () => openDecision(x) });
  for (const x of data.memory) c.push({ kind: '메모리', title: x.id, text: x.description + '\n' + x.body, when: x.ts, open: () => openMemory(x) });
  for (const x of S.d.tasks) c.push({ kind: '작업', title: x.title, text: [x.id, x.summary, x.next_action, x.state, JSON.stringify(x.fields || {})].join('\n'), when: x.updated_at, open: () => openTask(x) });
  for (const x of S.d.topics) c.push({ kind: '주제', title: x.title, text: [x.body, ...(x.notes || []).map(n => n.body)].join('\n'), when: x.created_at, open: () => openTopic(x) });
  for (const x of data.ledger) c.push({ kind: '원장', title: x.title, text: x.body, when: x.ts, open: () => openLedger(x) });
  for (const x of data.messages) c.push({ kind: '메시지', title: x.title, text: [x.id, x.kind, x.task_id, x.body].join('\n'), when: x.ts, open: () => openMessage(x) });
  for (const x of data.validations) c.push({ kind: 'QA', title: x.id, text: JSON.stringify(x.summary), when: x.ts, open: () => openValidation(x) });
  return c;
}
function highlight(text, terms) {
  if (!terms.length) return text;
  const re = new RegExp('(' + terms.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|') + ')', 'gi');
  return text.split(re).map((part, i) => (i % 2 ? h('mark', null, part) : part));
}
function snippet(text, terms) {
  const low = text.toLowerCase();
  let at = -1;
  for (const t of terms) { const i = low.indexOf(t); if (i >= 0 && (at < 0 || i < at)) at = i; }
  const start = Math.max(0, at - 60);
  return (start ? '…' : '') + text.slice(start, start + 220).replace(/\s+/g, ' ') + (text.length > start + 220 ? '…' : '');
}
function vBrain() {
  const terms = S.q.toLowerCase().split(/\s+/).filter(Boolean);
  const input = h('input', { type: 'search', value: S.q, placeholder: '무엇을, 왜 결정했는지 찾기 (예: 웹토큰, 오버레이, P0)', 'aria-label': '세컨드 브레인 검색',
    oninput: e => { clearTimeout(S._qt); S._qt = setTimeout(() => { S.q = e.target.value; history.replaceState(null, '', '#/brain' + (S.q ? '?q=' + encodeURIComponent(S.q) : '')); render(); const i = $('.searchbox input'); if (i) { i.focus(); i.setSelectionRange(i.value.length, i.value.length); } }, 180); } });
  let results = null;
  if (terms.length) {
    results = corpus().map(x => {
      const tl = x.title.toLowerCase(), bl = x.text.toLowerCase();
      let score = 0;
      for (const t of terms) { if (!tl.includes(t) && !bl.includes(t)) return null; score += (tl.includes(t) ? 5 : 0) + Math.min(5, bl.split(t).length - 1); }
      return { ...x, score };
    }).filter(Boolean).sort((a, b) => b.score - a.score || toMs(b.when) - toMs(a.when)).slice(0, 60);
  }
  return [
    head('SECOND BRAIN', '세컨드 브레인', null),
    h('label', { class: 'searchbox' }, icon('search'), input),
    results ? h('div', { class: 'section-gap' }, card('검색 결과', { big: results.length, unit: '건' },
      results.length ? h('div', { class: 'list' }, results.map(r => h('button', { class: 'item', onclick: r.open },
        h('span', { class: 'tag', style: { 'margin-top': '2px' } }, r.kind),
        h('span', { class: 'body' }, h('div', { class: 't' }, highlight(r.title, terms)), h('div', { class: 's' }, highlight(snippet(r.text, terms), terms))),
        h('span', { class: 'when' }, fmtAbs(r.when, true))))) : empty('일치하는 기록이 없습니다.'))) : null,
    h('div', { class: 'grid g-2 section-gap' },
      card('결정 기록', { big: S.data.decisions.length, unit: '건' },
        h('div', { style: { display: 'grid', gap: '10px' } }, [...S.data.decisions].sort((a, b) => toMs(b.date) - toMs(a.date)).map(decisionCard))),
      card('Claude 메모리', { big: S.data.memory.length, unit: '건' },
        h('div', { class: 'list' }, S.data.memory.map(m => h('button', { class: 'item', onclick: () => openMemory(m) },
          h('span', { class: 'tag', style: { 'margin-top': '2px' } }, ({ feedback: '지침', project: '프로젝트', user: '사용자', reference: '참조' })[m.type] || m.type),
          h('span', { class: 'body' }, h('div', { class: 't' }, m.id), h('div', { class: 's clamp-2' }, m.description)),
          h('span', { class: 'when' }, fmtRel(m.ts))))))),
  ];
}
function decisionCard(x) {
  return h('button', { class: 'decision', onclick: () => openDecision(x) },
    h('div', { style: { display: 'flex', gap: '8px', 'align-items': 'center', 'flex-wrap': 'wrap' } },
      h('span', { class: 'tag' }, fmtAbs(x.date, true)), h('span', { class: 'wait' }, av(x.by, true), person(x.by).name), x.task_id ? h('span', { class: 'tag' }, x.task_id) : null),
    h('div', { class: 'ttl' }, x.title),
    h('dl', null, h('dt', null, '결정'), h('dd', null, x.decision), h('dt', null, '이유'), h('dd', null, x.reason),
      (x.rejected || []).length ? [h('dt', null, '버린 안'), h('dd', { class: 'rej' }, x.rejected.join(' · '))] : null));
}

// ------------------------------------------------------------ 연결
function vSources() {
  const data = S.data, m = data.meta;
  return [
    head('SOURCES', '연결된 출처', null),
    card('수집 상태', { big: data.sources.length, unit: '곳' }, h('div', { class: 'tbl-wrap' }, h('table', { class: 'tbl' },
      h('thead', null, h('tr', null, ['상태', '출처', '건수', '최근 변경', '경로·메모'].map(x => h('th', null, x)))),
      h('tbody', null, data.sources.map(s => {
        const stale = s.last_modified && hoursSince(s.last_modified) > 48, optional = /선택/.test(s.error || '');
        return h('tr', null,
          h('td', null, h('span', { class: `st ${!s.ok ? (optional ? 'neutral' : 'blocked') : stale ? 'user_test' : 'done'}` }, icon(!s.ok ? 'alert' : stale ? 'clock' : 'done'), !s.ok ? (optional ? '없음' : '오류') : stale ? '오래됨' : '정상')),
          h('td', null, h('b', null, s.name)),
          h('td', { class: 'num' }, s.count),
          h('td', { class: 'num', style: { 'white-space': 'nowrap' } }, s.last_modified ? fmtAbs(s.last_modified) : '—'),
          h('td', null, h('div', { class: 'mono muted' }, s.path), s.error ? h('div', { style: { color: optional ? 'var(--ink-3)' : 'var(--st-blocked)' } }, s.error) : null, s.note ? h('div', { class: 'muted' }, s.note) : null));
      }))))),
    h('div', { class: 'grid g-2 section-gap' },
      card('생성 정보', null, h('dl', { class: 'fields' },
        h('dt', null, '생성 시각'), h('dd', null, fmtAbs(m.generated_at) + ' · ' + fmtRel(m.generated_at)),
        h('dt', null, '게시 시각'), h('dd', null, fmtAbs(S.env.published_at)),
        h('dt', null, '사령탑'), h('dd', null, m.coordination?.lead || '—'),
        h('dt', null, 'Astra 역할'), h('dd', null, m.coordination?.astra_role || '—'),
        h('dt', null, '작업표 기록자'), h('dd', null, m.coordination?.writer || '—'),
        h('dt', null, '가린 정보'), h('dd', null, Object.entries(m.masked || {}).map(([k, v]) => `${({ ip: '공인 IP', email: '이메일', secret: '비밀값', token: '토큰' })[k] || k} ${v}`).join(' · ')),
        h('dt', null, '기록 충돌'), h('dd', null, (m.conflicts || []).length ? m.conflicts.map(c => c.id).join(', ') : '없음'),
        h('dt', null, '저장소'), h('dd', null, m.repo || '미연결'))),
      card('갱신과 협업', null, h('div', { class: 'hint', style: { display: 'grid', gap: '8px' } },
        h('div', null, h('b', null, '갱신: '), 'PC에서 ', h('span', { class: 'mono' }, 'publish.ps1'), ' 실행 → 수집·암호화·push. 이 화면은 5분마다 새 게시본을 확인합니다.'),
        h('div', null, h('b', null, 'Claude: '), h('span', { class: 'mono' }, 'data/claude.json'), ', ', h('span', { class: 'mono' }, 'topics/<id>/claude.json'), '에만 씁니다.'),
        h('div', null, h('b', null, 'Astra: '), h('span', { class: 'mono' }, 'data/astra.json'), ', ', h('span', { class: 'mono' }, 'topics/<id>/astra.json'), '에만 씁니다.'),
        h('div', null, h('b', null, '자동 수집: '), 'tasks.json · inbox-claude · inbox-astra · qa · handoffs · 감사 원장 · Claude 메모리.')))),
  ];
}

// ------------------------------------------------------------ 서랍(상세)
function drawer(eyebrow, ...content) {
  closeDrawer(true);
  const scrim = h('div', { class: 'scrim', onclick: () => closeDrawer() });
  const panel = h('aside', { class: 'drawer', role: 'dialog', 'aria-modal': 'true', 'aria-label': eyebrow },
    h('div', { class: 'drawer-h' }, h('span', { class: 'eyebrow' }, eyebrow), h('button', { class: 'icon-btn', 'aria-label': '닫기', onclick: () => closeDrawer() }, icon('x'))),
    h('div', { class: 'drawer-b' }, content));
  document.body.append(scrim, panel);
  S._lastFocus = document.activeElement;
  requestAnimationFrame(() => { scrim.classList.add('on'); panel.classList.add('on'); panel.querySelector('.drawer-h button').focus(); });
}
function closeDrawer(instant) {
  const els = document.querySelectorAll('.scrim, .drawer');
  if (!els.length) return;
  if (instant) { els.forEach(e => e.remove()); return; }
  els.forEach(e => e.classList.remove('on'));
  setTimeout(() => els.forEach(e => e.remove()), 250);
  S._lastFocus?.focus?.();
}
function fieldList(obj) {
  const rows = Object.entries(obj || {}).filter(([, v]) => v != null && v !== '' && !(Array.isArray(v) && !v.length));
  if (!rows.length) return null;
  return h('dl', { class: 'fields' }, rows.map(([k, v]) => [h('dt', null, k), h('dd', { class: typeof v === 'string' && v.length < 90 && !/\s/.test(v) ? 'mono' : '' },
    Array.isArray(v) ? v.map(x => typeof x === 'object' ? JSON.stringify(x) : x).join(' · ') : typeof v === 'object' ? JSON.stringify(v) : String(v))]));
}
function openTaskById(id) { const t = S.d.tasks.find(x => x.id === id); if (t) openTask(t); else toast('작업 기록을 찾지 못했습니다: ' + id); }
function openTask(t) {
  const msgs = S.data.messages.filter(m => m.task_id === t.id).slice(0, 20);
  const blob = JSON.stringify(t.fields || {});
  const vals = S.data.validations.filter(v => (v.job && blob.includes(v.job)) || blob.includes(v.id));
  const decs = S.data.decisions.filter(x => x.task_id === t.id);
  const topics = S.d.topics.filter(x => x.linked_task_id === t.id);
  drawer('작업 상세',
    h('div', { style: { display: 'flex', gap: '6px', 'flex-wrap': 'wrap' } }, priChip(t.priority), stChip(t.stage), t.area ? h('span', { class: 'tag' }, t.area) : null, t._stale ? h('span', { class: 'st blocked' }, icon('clock'), `${Math.round(t._age)}시간 멈춤`) : null),
    h('h3', null, t.title),
    h('dl', { class: 'fields' }, h('dt', null, '작업 ID'), h('dd', { class: 'mono' }, t.id), h('dt', null, '담당'), h('dd', null, person(t.owner).full),
      t.waiting_on ? [h('dt', null, '지금 차례'), h('dd', null, person(t.waiting_on).full)] : null,
      h('dt', null, '상태 원문'), h('dd', { class: 'mono' }, t.state || '—'), h('dt', null, '갱신'), h('dd', null, `${fmtAbs(t.updated_at)} · ${fmtRel(t.updated_at)}`),
      h('dt', null, '기록 출처'), h('dd', null, (t.authors || []).join(', '))),
    t.summary ? [h('h4', null, '현황'), h('p', { style: { margin: 0 } }, t.summary)] : null,
    t.next_action ? [h('h4', null, '다음 행동'), h('div', { class: 'callout' }, t.next_action)] : null,
    t.live_test ? [h('h4', null, '실게임'), h('p', { style: { margin: 0 } }, t.live_test)] : null,
    (t.evidence || []).length ? [h('h4', null, '근거'), h('ul', { style: { margin: 0, 'padding-left': '18px' } }, [].concat(t.evidence).map(e => h('li', { class: 'mono' }, e)))] : null,
    decs.length ? [h('h4', null, '관련 결정'), decs.map(decisionCard)] : null,
    topics.length ? [h('h4', null, '연결된 주제'), topics.map(topicCard)] : null,
    msgs.length ? [h('h4', null, `관련 메시지 ${msgs.length}`), h('div', { class: 'thread' }, msgs.map(m => threadRow(m, `${person(m.sender).name} → ${person(m.recipient).name}`)))] : null,
    vals.length ? [h('h4', null, '관련 QA'), h('div', { class: 'list' }, vals.map(v => h('button', { class: 'item', onclick: () => openValidation(v) }, h('span', { class: 'body' }, h('div', { class: 't' }, v.id), h('div', { class: 's' }, fmtAbs(v.ts) + ' · ' + (v.reviewer || '')))))) ] : null,
    t.fields && Object.keys(t.fields).length ? [h('h4', null, 'tasks.json 원본 필드'), fieldList(t.fields)] : null);
}
function openMessage(m) { drawer('메시지', messageDetail(m)); }
function openLedger(e) {
  drawer('감사 원장', h('div', { style: { display: 'flex', gap: '6px' } }, h('span', { class: `st ${LEDGER_ST[e.status].cls}` }, icon(LEDGER_ST[e.status].icon), LEDGER_ST[e.status].label), h('span', { class: 'tag' }, e.has_time ? fmtAbs(e.ts) : e.date)),
    h('h3', null, e.title), h('pre', { class: 'pre' }, e.body));
}
function openValidation(v) {
  drawer('QA 검증', h('div', { style: { display: 'flex', gap: '6px' } }, h('span', { class: `st ${v.result === 'pass' ? 'done' : v.result === 'fail' ? 'blocked' : 'neutral'}` }, icon('verify'), v.result === 'pass' ? '통과' : v.result === 'fail' ? '실패' : '불명'), v.live === 'pending' ? h('span', { class: 'st user_test' }, icon('flask'), '실게임 미실행') : null),
    h('h3', null, v.id), fieldList({ 시각: fmtAbs(v.ts), 파일: v.path, '해시 기록 파일 수': v.file_count, ...v.summary }));
}
function openMemory(m) {
  drawer('Claude 메모리', h('div', { style: { display: 'flex', gap: '6px', 'flex-wrap': 'wrap' } }, h('span', { class: 'tag' }, m.type), h('span', { class: 'tag' }, fmtAbs(m.ts))),
    h('h3', null, m.id), h('p', { class: 'muted', style: { margin: 0 } }, m.description), h('pre', { class: 'pre' }, m.body),
    m.links?.length ? [h('h4', null, '연결된 기억'), h('div', { style: { display: 'flex', gap: '6px', 'flex-wrap': 'wrap' } }, m.links.map(l => {
      const t = S.data.memory.find(x => x.id === l);
      return h('button', { class: 'tag', style: { cursor: t ? 'pointer' : 'default' }, onclick: () => t && openMemory(t) }, l + (t ? '' : ' (없음)'));
    }))] : null);
}
function openDecision(x) {
  drawer('결정 기록', decisionCard(x), fieldList({ 출처: x.source, 기록자: x._author, ID: x.id }));
}
function openTopic(t) {
  const plan = t.plan || {};
  const planRows = [['goal', '목표'], ['scope', '범위'], ['inputs', '필요한 입력'], ['first_steps', '첫 단계'], ['risks', '위험·확인'], ['done_when', '완료 기준']]
    .filter(([k]) => plan[k] && (!Array.isArray(plan[k]) || plan[k].length));
  drawer('주제',
    h('div', { style: { display: 'flex', gap: '6px', 'flex-wrap': 'wrap' } }, topicChip(t.status), priChip(t.priority), t.kind ? h('span', { class: 'tag' }, t.kind) : null,
      h('span', { class: 'tag' }, t.id), t.linked_task_id ? h('button', { class: 'tag', style: { cursor: 'pointer' }, onclick: () => openTaskById(t.linked_task_id) }, '작업 ' + t.linked_task_id) : null),
    h('h3', null, t.title),
    h('dl', { class: 'fields' }, h('dt', null, '담당'), h('dd', null, t.assignee ? person(t.assignee).full : '미배정'),
      h('dt', null, '지금 차례'), h('dd', null, t.turn ? `${person(t.turn).full} · ${t.status === 'new' ? '분배' : !t.plan ? '진행 베이스 작성' : t.turn !== t.assignee ? '교차 검토' : '진행'}` : '—'),
      h('dt', null, '선호'), h('dd', null, ({ auto: '자동 분배', claude: 'Claude 우선', astra: 'Astra 우선' })[t.prefer] || '—'),
      h('dt', null, '받은 시각'), h('dd', null, fmtAbs(t.created_at)), h('dt', null, '경로'), h('dd', null, t.source || '—')),
    t.body ? [h('h4', null, '원래 메모'), h('pre', { class: 'pre' }, t.body)] : null,
    planRows.length ? [h('h4', null, `진행 베이스 · ${person(t.plan_by).name}`), h('div', { class: 'plan callout' }, planRows.map(([k, l]) => h('div', null, h('h4', null, l),
      Array.isArray(plan[k]) ? h('ul', null, plan[k].map(x => h('li', null, x))) : h('div', null, plan[k]))))] : null,
    [h('h4', null, `메모·검토 ${(t.notes || []).length}`), (t.notes || []).length ? h('div', { class: 'note-thread' }, t.notes.map(n => h('div', { class: 'note' }, av(n.by, false),
      h('div', { class: 'bubble' }, h('div', { class: 'h' }, h('b', null, person(n.by).name), h('span', { class: 'tag' }, NOTE_KIND[n.kind] || n.kind || '메모'), h('span', null, fmtAbs(n.ts))), h('p', null, n.body)))))
      : empty('아직 메모가 없습니다. PC에서 topics.py로 분배·메모를 남깁니다.')]);
}

// ------------------------------------------------------------ 기타
function toast(text) {
  let t = $('.toast');
  if (!t) { t = h('div', { class: 'toast', role: 'status', 'aria-live': 'polite' }); document.body.append(t); }
  t.textContent = text; t.classList.add('on');
  clearTimeout(S._toast); S._toast = setTimeout(() => t.classList.remove('on'), 2600);
}
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') { closeDrawer(); $('.side')?.classList.remove('on'); }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k' && S.data) { e.preventDefault(); const i = $('.top-search input'); i?.focus(); }
});
window.addEventListener('hashchange', () => { if (S.data) { readHash(); render(); } });
let resizeT;
window.addEventListener('resize', () => { clearTimeout(resizeT); resizeT = setTimeout(() => { if (S.data && S.view === 'messages') render(); }, 200); });
document.addEventListener('visibilitychange', () => { if (!document.hidden && S.data && hoursSince(S.env?.published_at) > 0.08) refresh(); });
boot();
