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
  if (attrs && attrs['data-draft']) attachDraft(el, attrs['data-draft']);
  return el;
}
// ------------------------------------------------------------ 쓰던 글 보존(자동 갱신·다시 그리기·앱 재시작에도 남게)
function saveDraft(key, v) { if (v && v.trim()) store.set('draft:' + key, v); else store.del('draft:' + key); }
function clearDraft(...keys) { for (const k of keys) store.del('draft:' + k); }
function attachDraft(el, key) {
  const v = store.get('draft:' + key);
  if (typeof v === 'string' && v) el.value = v;
  el.addEventListener('input', () => { clearTimeout(el._draftT); el._draftT = setTimeout(() => saveDraft(key, el.value), 300); });
}
function snapshotDrafts(root) {
  root.querySelectorAll('[data-draft]').forEach(el => saveDraft(el.dataset.draft, el.value));
  const a = document.activeElement;
  return a && root.contains(a) && a.dataset && a.dataset.draft ? { key: a.dataset.draft, s: a.selectionStart, e: a.selectionEnd } : null;
}
function restoreFocus(root, f) {
  if (!f) return;
  const el = [...root.querySelectorAll('[data-draft]')].find(x => x.dataset.draft === f.key);
  if (!el) return;
  el.focus({ preventScroll: true });
  try { el.setSelectionRange(f.s, f.e); } catch { /* 선택 범위를 못 쓰는 칸 */ }
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
  install: '<path d="M12 4v11M7.5 10.5L12 15l4.5-4.5"/><path d="M5 19.5h14"/>',
  agents: '<circle cx="9" cy="8.5" r="3"/><path d="M3.5 19a5.5 5.5 0 0 1 11 0"/><circle cx="17" cy="9.5" r="2.5"/><path d="M15.5 14.2a4.5 4.5 0 0 1 5 4.8"/>',
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
// 작업자(PC + AI) 표시. 예: dev-claude → "개발컴 · Claude"
const LEGACY = { claude: 'dev-claude', astra: 'dev-astra' };
function agentOf(id) {
  const ag = S.data?.agents || [];
  return ag.find(a => a.id === id) || ag.find(a => a.id === LEGACY[id]) || null;
}
function person(id) {
  if (PEOPLE[id] && !agentOf(id)) return PEOPLE[id];
  const a = agentOf(id);
  if (a) {
    const short = (a.label || a.id).replace(/\s*\(.*\)$/, '');
    return { name: `${a.pc_label} ${short}`, full: `${a.pc_label} · ${a.label || a.id}`, role: a.ai === 'gpt' ? 'GPT 계열' : 'Claude 계열',
      ini: a.ai === 'gpt' ? 'G' : 'C', ai: a.ai, pc: a.pc };
  }
  if (PEOPLE[id]) return PEOPLE[id];
  return { name: id || '?', full: id || '?', role: '', ini: (id || '?').slice(0, 1).toUpperCase() };
}
function av(id, small) {
  const p = person(id);
  const a = agentOf(id);
  const cls = a ? (a.ai === 'gpt' ? 'astra' : 'claude') : PEOPLE[id] ? id : 'cli';
  const pcTag = a && a.pc !== S.data?.meta?.hub ? h('i', { class: 'pc-dot', 'aria-hidden': 'true' }) : null;
  return h('span', { class: `av ${cls}${small ? ' sm' : ''}`, title: p.full, 'aria-label': p.full }, p.ini, pcTag);
}
const agentState = a => {
  const seen = a?.last_seen || a?.pc_synced;
  const stale = S.data?.meta?.routing?.stale_minutes || 120;
  if (!seen) return { cls: 'neutral', label: '신호 없음', icon: 'clock' };
  const m = (Date.now() - toMs(seen)) / 6e4;
  if (m > stale) return { cls: 'blocked', label: '끊김', icon: 'alert' };
  const hl = a.health;
  if (hl && hl.state && hl.state !== 'ok' && hl.needs_user) return { cls: 'blocked', label: HEALTH[hl.state] || '실행 오류', icon: 'alert' };
  if ((S.data?.runs || []).some(r => r.agent === a.id && isRunning(r))) return { cls: 'progress', label: '실행 중', icon: 'play' };
  if (!a.current) return { cls: 'neutral', label: '쉬는 중', icon: 'pause' };
  return { cls: 'done', label: '작업 중', icon: 'play' };
};

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
  { id: 'backlog', label: '미처리', cls: 'neutral', icon: 'inbox' },
  { id: 'new', label: '새 주제', cls: 'request', icon: 'topics' },
  { id: 'triage', label: '검토 중', cls: 'validating', icon: 'eye' },
  { id: 'ready', label: '준비됨', cls: 'done', icon: 'file' },
  { id: 'active', label: '진행 중', cls: 'progress', icon: 'play' },
  { id: 'done', label: '완료', cls: 'done', icon: 'done' },
  { id: 'parked', label: '보류', cls: 'neutral', icon: 'pause' },
  { id: 'dropped', label: '삭제됨', cls: 'blocked', icon: 'x', hidden: true },
];
const TOPIC = Object.fromEntries(TOPIC_STATES.map(s => [s.id, s]));
function topicChip(state) {
  const s = TOPIC[state] || TOPIC.new;
  return h('span', { class: `st ${s.cls}` }, icon(s.icon), s.label);
}
const NOTE_KIND = { triage: '분배', memo: '메모', review: '검토', plan: '진행 베이스', question: '질문', answer: '답변', status: '상태', claim: '착수', handoff: '인계', work: '작업물' };
const HEALTH = { auth: '로그인 만료', tool: '실행 도구 없음', timeout: '시간 초과', encoding: '인코딩 오류', parse: '답 형식 오류', error: '실행 오류' };
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
// ------------------------------------------------------------ 보내기 (대시보드 → PC). 정적 사이트라 GitHub 이슈를 우체통으로 쓴다
const hex = n => [...crypto.getRandomValues(new Uint8Array(n))].map(b => b.toString(16).padStart(2, '0')).join('');
function newId(prefix, bytes = 4) { const d = new Date(); return `${prefix}-${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${hex(bytes)}`; }
const pending = {
  all() { return (store.get('pending', []) || []).filter(p => Date.now() - toMs(p.created_at) < 14 * 864e5); },
  add(p) { const l = pending.all(); l.push(p); store.set('pending', l); },
  remove(id) { store.set('pending', pending.all().filter(p => p.id !== id)); },
  prune(done) { const s = new Set(done || []); store.set('pending', pending.all().filter(p => !s.has(p.id))); },
};
async function tokenGet() {
  const s = store.get('ghtoken');
  if (!s || !S.key) return null;
  try { return new TextDecoder().decode(await crypto.subtle.decrypt({ name: 'AES-GCM', iv: b64.dec(s.iv) }, S.key, b64.dec(s.ct))); } catch { return null; }
}
async function tokenSet(tok) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, S.key, new TextEncoder().encode(tok)));
  store.set('ghtoken', { iv: b64.enc(iv), ct: b64.enc(ct), at: new Date().toISOString() });
}
async function sendBlob(kind, obj) {
  const repo = S.data.meta.repo;
  if (!repo) throw new Error('GitHub 저장소가 연결되지 않았습니다.');
  const blob = await sealTopic(obj);
  const title = `[${kind}] ${obj.id}`;
  const body = `REAL 운영체제 ${kind === 'topic' ? '주제' : '요청'} (암호화됨 · 대시보드 비밀번호로만 열립니다)\n\n아래 줄을 수정하지 마세요.\n\n${blob}\n`;
  const token = await tokenGet();
  if (token) {
    try {
      const r = await fetch(`https://api.github.com/repos/${repo}/issues`, {
        method: 'POST', headers: { Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json', 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, body }) });
      if (r.ok) return { via: 'api' };
      toast(`바로 보내기 실패 (${r.status}) — GitHub 창으로 보냅니다`);
    } catch { toast('바로 보내기 실패 — GitHub 창으로 보냅니다'); }
  }
  const url = `https://github.com/${repo}/issues/new?title=${encodeURIComponent(title)}&body=${encodeURIComponent(body)}`;
  const w = window.open(url, '_blank');
  if (w) w.opener = null;
  return { via: 'page', url, blocked: !w };
}
function afterSend(res) {
  if (res.via === 'api') return toast('보냈습니다 · PC 동기화 때 반영됩니다');
  if (!res.blocked) return toast('GitHub 창에서 "Submit new issue"를 눌러야 전송됩니다');
  drawer('보내기', h('h3', null, '팝업이 막혔습니다'),
    h('p', null, '아래 버튼으로 GitHub 창을 열고 "Submit new issue"를 눌러주세요. 내용은 암호문이라 그대로 보내면 됩니다.'),
    h('a', { class: 'btn primary', href: res.url, target: '_blank', rel: 'noopener noreferrer' }, icon('send'), 'GitHub에서 보내기'));
}
async function sendOps(type, fields, summary) {
  const action = { id: newId('A'), type, created_at: new Date().toISOString(), ...fields };
  const res = await sendBlob('ops', action);
  pending.add({ ...fields, id: action.id, type, created_at: action.created_at, summary, via: res.via });
  S.d = derive(S.data);
  afterSend(res);
  return res;
}
async function syncAcks(keys) {
  // 토큰이 있을 때만 조용히 공유한다. 없으면 이 기기에서만 확인 처리.
  if (!keys.length || !(await tokenGet())) return;
  try { await sendOps('ack', { messages: [], keys }, `놓친 항목 ${keys.length}건 확인`); } catch { /* 이 기기 확인은 이미 반영됨 */ }
}

async function fetchEnvelope() {
  // 조건부 요청: 바뀌지 않았으면 서버가 304로 답해 데이터를 다시 받지 않는다(1분마다 확인해도 가볍다)
  const r = await fetch('data.enc.json', { cache: 'no-cache' });
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
  // PC가 처리한 요청은 대기 목록에서 지우고, 아직 대기 중인 요청은 화면에 먼저 반영한다
  pending.prune(data.processed_actions);
  const pend = pending.all();
  const pendAckMsgs = new Set(pend.filter(p => p.type === 'ack').flatMap(p => p.messages || []));
  S.serverAcks = new Set([...(data.acks || []), ...pend.filter(p => p.type === 'ack').flatMap(p => p.keys || [])]);
  const pendStage = {};
  for (const p of pend.filter(p => p.type === 'task-state')) for (const id of p.ids || []) pendStage[id] = p.stage;
  const answers = {};
  for (const a of data.decisions_answered || []) answers[a.id] = { ...a, pending: false };
  for (const p of pend.filter(p => p.type === 'decide')) answers[p.decision_id] = { id: p.decision_id, choice: p.choice, note: p.note, ts: p.created_at, pending: true };
  const tasks = data.tasks.map(t => {
    const base = pendStage[t.id] ? { ...t, stage: pendStage[t.id], _pendingStage: true } : t;
    const age = hoursSince(base._pendingStage ? new Date().toISOString() : base.updated_at);
    return { ...base, _age: age, _stale: !['done', 'user_test'].includes(base.stage) && age > staleH, _waitLong: base.stage === 'user_test' && age > 72 };
  });
  const msgs = data.messages;
  const unprocessed = msgs.filter(m => m.unprocessed && !pendAckMsgs.has(m.id));
  const unanswered = msgs.filter(m => m.box === 'inbox-astra' && m.sender === 'claude' && !m.replies.length && !(m.followups || []).length
    && REQ_RE.test((m.kind || '') + ' ' + m.title) && hoursSince(m.ts) > unansH && hoursSince(m.ts) < 72);
  const pendAssign = {};
  for (const p of pend.filter(p => p.type === 'assign')) pendAssign[p.topic] = p.agent;
  const pendActivate = new Set(pend.filter(p => p.type === 'activate').map(p => p.topic));
  // 주제 수정·삭제·되살리기도 PC가 처리하기 전에 화면에 먼저 반영한다(마지막 요청이 이긴다)
  const pendEdit = {}, pendDrop = new Map();
  for (const p of pend.filter(p => p.type === 'topic-edit')) pendEdit[p.topic] = p;
  for (const p of pend.filter(p => p.type === 'topic-drop')) for (const id of p.topics || []) pendDrop.set(id, !p.restore);
  const topics = (data.topics || []).map(t => {
    let x = { ...t, _age: hoursSince(t.created_at),
      ...(t.status === 'backlog' && pendActivate.has(t.id) ? { status: 'new' } : {}),
      ...(pendAssign[t.id] && pendAssign[t.id] !== t.assignee ? { assignee: pendAssign[t.id], assign_by: 'user', dispatch_reason: '사용자 지정(반영 대기)', status: t.status === 'new' ? 'triage' : t.status } : {}) };
    const e = pendEdit[t.id];
    if (e) x = { ...x, title: e.title, body: e.body, priority: e.priority || x.priority, kind: e.kind || x.kind, _pendingEdit: true };
    if (pendDrop.get(t.id) === true && x.status !== 'dropped') x = { ...x, status: 'dropped', dropped_at: pend.find(p => p.type === 'topic-drop' && (p.topics || []).includes(t.id))?.created_at, _pendingDrop: true };
    if (pendDrop.get(t.id) === false && x.status === 'dropped') x = { ...x, status: t.backlog && !t.assignee ? 'backlog' : 'new', _pendingDrop: true };
    if (x.status === 'dropped') x.turn = null;
    return x;
  });

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
  for (const t of topics.filter(t => t.status === 'new' && !t.assignee && t._age > 1)) missed.push({ key: `topic:${t.id}`, level: 'warn', icon: 'topics',
    title: `배분되지 않은 주제: ${t.title}`, sub: `${Math.round(t._age)}시간 경과 · 허브 자동 동기화 확인`, go: () => openTopic(t) });
  for (const t of topics.filter(t => (t.conflict || []).length)) missed.push({ key: `conflict-topic:${t.id}:${t.conflict.join(',')}`, level: 'bad', icon: 'alert',
    title: `중복 착수: ${t.title}`, sub: `담당 ${t.assignee} · 추가 착수 ${t.conflict.join(', ')}`, go: () => openTopic(t) });
  const staleMin = data.meta.routing?.stale_minutes || 120;
  for (const a of data.agents || []) {
    const mine = topics.filter(t => t.assignee === a.id && !['done', 'parked', 'dropped'].includes(t.status));
    const seen = a.last_seen || a.pc_synced;
    if (mine.length && (!seen || (Date.now() - toMs(seen)) / 6e4 > staleMin)) missed.push({ key: `agent-off:${a.id}:${seen || 'none'}`, level: 'bad', icon: 'agents',
      title: `작업자 신호 끊김: ${a.pc_label} · ${a.label || a.id}`, sub: `맡은 주제 ${mine.length}건 · 마지막 신호 ${fmtRel(seen)}`, go: () => go('agents') });
  }

  const lastBy = who => msgs.find(m => m.sender === who)?.ts || null;
  return { tasks, unprocessed, unanswered, missed, topics, lastBy, answers, pend, pendAckMsgs };
}
const openMissed = () => S.d.missed.filter(m => !S.acks.has(m.key) && !S.serverAcks?.has(m.key));
function ack(keys, opts = {}) {
  keys = [].concat(keys);
  for (const k of keys) S.acks.add(k);
  store.set('acks', [...S.acks].slice(-1000));
  if (!opts.noSync) syncAcks(keys);
  S._keepScroll = true;
  render();
  if (opts.redraw) opts.redraw();
}
function filterTasks(list, owner) {
  if (!owner || owner === 'all') return list;
  if (owner === 'user') return list.filter(t => t.waiting_on === 'user' || t.owner === 'user');
  return list.filter(t => t.owner === owner || t.waiting_on === owner || (owner === 'cli' && /cli/i.test(t.implementer || '')));
}

// ------------------------------------------------------------ 앱 골격
const NAV = [
  { id: 'mine', label: '내 차례', icon: 'user' },
  { id: 'overview', label: '개요', icon: 'overview' },
  { id: 'agents', label: '작업자', icon: 'agents' },
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
  if (!S.timer) S.timer = setInterval(() => { if (!document.hidden) refresh(); }, 60 * 1000);
}
async function refresh(manual) {
  try {
    const env = await fetchEnvelope();
    // 바뀐 게 없으면 다시 그리지 않는다(쓰던 글·스크롤이 흔들리지 않게)
    if (env.published_at === S.env?.published_at) { if (manual) toast('이미 최신입니다 · 게시 ' + fmtRel(env.published_at)); return; }
    if (env.salt !== S.env.salt) { S.env = env; toast('비밀번호가 바뀌었습니다. 다시 열어주세요.'); return lockNow(); }
    S.env = env; S.data = await openEnvelope(env, S.key); S.d = derive(S.data);
    S._keepScroll = true; render(); toast('새 데이터를 반영했습니다');
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
  const focus = snapshotDrafts(app);
  const inner = [...app.querySelectorAll('.mine-list, .mine-detail .ms-main, .mine-detail .ms-side, .msg-list, .reader')].map(e => e.scrollTop);
  app.replaceChildren(sidebar(), h('div', { class: 'main' }, topbar(), page()));
  if (S._keepScroll) {
    window.scrollTo({ top: keepScroll });
    [...app.querySelectorAll('.mine-list, .mine-detail .ms-main, .mine-detail .ms-side, .msg-list, .reader')].forEach((e, i) => { if (inner[i] != null) e.scrollTop = inner[i]; });
  }
  restoreFocus(app, focus);
  S._keepScroll = false;
}

function sidebar() {
  const d = S.d, data = S.data;
  const badges = {
    mine: myQueue().total || null,
    topics: d.topics.filter(t => t.status === 'new').length || null,
    tasks: d.tasks.filter(t => t.stage !== 'done').length,
    messages: d.unprocessed.length || null,
    sources: data.sources.filter(s => !s.ok && !/선택/.test(s.error || '')).length || null,
  };
  const hot = { mine: true, topics: true, messages: true, sources: true };
  // 출처는 한 줄 요약만 두고, 문제가 있는 출처만 아래에 따로 보여 준다(목록이 길어 스크롤이 생기지 않게)
  const srcs = data.sources.filter(s => !/선택/.test(s.error || '') || s.count);
  const srcState = s => (!s.ok ? 'bad' : s.last_modified && hoursSince(s.last_modified) > 48 ? 'warn' : '');
  const bad = srcs.filter(s => srcState(s));
  const srcRows = [
    h('button', { class: 'src-row', title: '연결 화면에서 전체 보기', onclick: () => go('sources') },
      h('span', { class: 'src-name' }, `출처 ${srcs.length}곳 · 정상 ${srcs.length - bad.length}`),
      h('span', { class: `dot${bad.some(s => srcState(s) === 'bad') ? ' bad' : bad.length ? ' warn' : ''}` })),
    bad.slice(0, 3).map(s => h('button', { class: 'src-row', title: `${s.name} · ${s.error || '48시간 넘게 변화 없음'}`, onclick: () => go('sources') },
      h('span', { class: 'src-name muted' }, s.name), h('span', { class: `dot ${srcState(s)}` }))),
  ];
  return h('nav', { class: 'side', 'aria-label': '주 메뉴' },
    h('div', { class: 'side-brand' }, h('span', { class: 'brand-mark', 'aria-hidden': 'true' }), data.meta.project || 'REAL 운영체제'),
    NAV.map(n => h('button', { class: 'nav-btn', 'aria-current': S.view === n.id ? 'page' : null, onclick: () => go(n.id) },
      icon(n.icon), n.label, badges[n.id] ? h('span', { class: `badge${hot[n.id] ? ' hot' : ''}` }, badges[n.id]) : null)),
    h('div', { class: 'side-h' }, 'SOURCES'),
    srcRows,
    h('div', { class: 'side-h' }, 'TEAM'),
    h('div', { class: 'team-row' }, ['user', 'claude', 'astra', 'cli'].map(id => av(id))),
    h('div', { class: 'side-foot' },
      !matchMedia('(display-mode: standalone)').matches && !navigator.standalone
        ? h('button', { class: 'btn', onclick: installApp, title: '주소창 없이 앱처럼 열기' }, icon('install'), '앱으로 설치') : null,
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
    (() => { const n = myQueue().total; return h('button', { class: `btn mine-btn${n ? ' hot' : ''}`, onclick: () => go('mine'), title: '아키텍트가 답하거나 확인할 것' }, icon('user'), n ? `내 차례 ${n}` : '내 차례 없음'); })(),
    h('button', { class: 'icon-btn bell', title: `놓친 항목 ${missed}`, 'aria-label': `놓친 항목 ${missed}건 보기`, onclick: openMissedDrawer },
      icon('bell'), missed ? h('span', { class: 'count' }, missed) : null));
}
function openMissedDrawer() {
  const items = openMissed();
  drawer('놓친 항목',
    h('div', { style: { display: 'flex', gap: '8px', 'align-items': 'center', 'flex-wrap': 'wrap' } },
      h('h3', null, `놓친 항목 ${items.length}건`),
      items.length ? h('button', { class: 'btn', style: { 'margin-left': 'auto' }, onclick: () => ack(items.map(i => i.key), { redraw: openMissedDrawer }) }, icon('check'), '모두 확인') : null),
    items.length ? h('div', { class: 'list' }, items.map(i => missedItem(i, openMissedDrawer))) : empty('놓친 항목이 없습니다.'),
    S.d.unprocessed.length ? h('div', { class: 'callout' }, h('b', null, `미처리 메시지 ${S.d.unprocessed.length}건`), ' — 알림 확인과 별개로, 메시지를 실제로 처리(done 폴더로 이동)하려면 ',
      h('button', { class: 'linkish', onclick: () => { closeDrawer(true); go('messages', { msg: 'unprocessed' }); } }, '메시지 화면의 "모두 확인 처리"'), '를 쓰세요.') : null,
    h('p', { class: 'hint' }, '"확인"은 알림만 끕니다. GitHub 토큰이 연결돼 있으면 다른 기기에도 공유됩니다.'));
}

function page() {
  const views = { mine: vMine, overview: vOverview, agents: vAgents, topics: vTopics, tasks: vTasks, messages: vMessages, verify: vVerify, brain: vBrain, sources: vSources };
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
    mineBanner(),
    h('div', { class: 'grid g-4' },
      completionCard(pct, done, total - done, tasks),
      collectedCard(),
      pipelineCard(tasks),
      missedCard()),
    // 1920×1080: 둘째 줄은 할 일·결정·막힘/마감 3단, 셋째 줄은 프로젝트(넓게)+최근 활동(안에서 스크롤)
    h('div', { class: 'grid g-3 wide-3 section-gap' }, todayCard(), decisionsNeededCard(),
      h('div', { class: 'stack' }, blockedCard(tasks), weekCard(tasks))),
    h('div', { class: 'grid ov-main section-gap' },
      card('진행 중인 프로젝트', { big: tasks.filter(t => t.stage !== 'done').length, unit: '건' },
        projGrid(tasks.filter(t => t.stage !== 'done').sort(taskSort))),
      card('최근 활동', { cls: 'scroll-card', right: h('button', { class: 'btn', onclick: () => go('messages') }, '메시지 전체', icon('arrow')) }, timeline(40))),
    h('div', { class: 'section-gap' }, card('팀 현황', { right: h('button', { class: 'btn', onclick: () => go('agents') }, 'PC별 전체', icon('arrow')) }, teamCompact())),
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
function missedItem(i, redraw) {
  return h('div', { class: 'item' },
    h('span', { class: `lead-ico ${i.level}` }, icon(i.icon)),
    h('button', { class: 'body', style: { border: '0', background: 'none', 'text-align': 'left', padding: '0', color: 'inherit' }, onclick: () => { if (redraw) closeDrawer(true); i.go(); } },
      h('div', { class: 't clamp-2' }, i.title), i.sub ? h('div', { class: 's clamp-2' }, i.sub) : null),
    h('button', { class: 'icon-btn ack-btn', title: '확인함', 'aria-label': '확인함으로 표시', onclick: () => ack(i.key, { redraw }) }, icon('check')));
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
// ------------------------------------------------------------ 내 차례 (아키텍트가 답하거나 확인할 것을 한곳에)
function myQueue() {
  const d = S.d, data = S.data;
  const done = k => S.acks.has(k) || S.serverAcks?.has(k);
  const decisions = (data.decisions_needed || []).filter(q => !d.answers[q.id]);
  const tests = d.tasks.filter(t => t.stage !== 'done' && (t.stage === 'user_test' || t.waiting_on === 'user') && !done(`mine-test:${t.id}:${t.updated_at}`));
  const actions = (data.user_actions || []).filter(a => !done(`ua:${a.id}`));
  const questions = [];
  for (const t of d.topics) {
    const lastUser = Math.max(0, ...commentsFor({ kind: 'topic', id: t.id }).filter(c => c.by === 'user').map(c => toMs(c.ts) || 0));
    for (const n of t.notes || []) {
      if (n.kind === 'question' && n.by !== 'user' && toMs(n.ts) > lastUser && !done(`mine-q:${t.id}:${n.ts}`)) questions.push({ topic: t, note: n });
    }
  }
  const backlog = d.topics.filter(t => t.status === 'backlog');
  return { decisions, tests, actions, questions, backlog, total: decisions.length + tests.length + actions.length + questions.length };
}
function mineBanner() {
  const q = myQueue();
  if (!q.total) return null;
  const parts = [q.decisions.length && `결정·승인 ${q.decisions.length}`, q.questions.length && `AI 질문 ${q.questions.length}`,
    q.tests.length && `실게임·확인 ${q.tests.length}`, q.actions.length && `할 일 ${q.actions.length}`].filter(Boolean);
  return h('button', { class: 'mine-banner', onclick: () => go('mine') }, icon('user'),
    h('b', null, `아키텍트 차례 ${q.total}건`), h('span', null, parts.join(' · ')), h('span', { class: 'go' }, '바로 보기', icon('arrow')));
}
// 목록에서 주제 이름을 보여주고 누르면 주제 서랍을 연다
function topicTag(id) {
  if (!id) return null;
  const t = topicById(id);
  return h('button', { class: 'tag tag-btn', title: t ? t.title : id, onclick: () => { t ? openTopic(t) : openTaskById(id); } }, t ? t.title : id);
}
function histCount(topic, taskId) {
  const n = historyEvents(topic, !topic && taskId ? S.d.tasks.find(t => t.id === taskId) : null).length;
  return n ? h('span', { class: 'hist-count' }, icon('clock'), `기록 ${n}`) : null;
}
// 내 차례 소분류: [값, 이름, 아이콘, 강조]
const MINE_TYPES = [
  ['decision', '결정·승인', 'scale', 'warn'],
  ['question', 'AI 질문', 'messages', 'warn'],
  ['test', '실게임·확인', 'flask', 'warn'],
  ['action', '할 일', 'user', ''],
  ['backlog', '착수 고르기', 'inbox', ''],
];
const MINE_TYPE = Object.fromEntries(MINE_TYPES.map(([v, l, i, c]) => [v, { label: l, icon: i, cls: c }]));
function mineItems() {
  const q = myQueue(), items = [];
  for (const x of q.decisions) items.push({ key: `d:${x.id}`, type: 'decision', title: x.question, who: x._author || 'claude', when: x.since, topic: topicById(x.task_id), taskId: x.task_id, ref: x,
    sub: x.recommendation ? '권장 ' + x.recommendation : (x.options || []).length ? `선택지 ${x.options.length}개` : '' });
  for (const { topic, note } of q.questions) items.push({ key: `q:${topic.id}:${note.ts}`, type: 'question', title: note.body, who: note.by, when: note.ts, topic, ref: note });
  for (const t of q.tests) items.push({ key: `t:${t.id}`, type: 'test', title: t.title, sub: t.next_action || t.summary || '', who: t.owner, when: t.updated_at, topic: S.d.topics.find(x => x.linked_task_id === t.id) || null, taskId: t.id, ref: t });
  for (const a of q.actions) items.push({ key: `a:${a.id}`, type: 'action', title: a.title, sub: a.detail || '', who: 'user', when: a.since, topic: S.d.topics.find(x => a.task_id && x.linked_task_id === a.task_id) || null, taskId: a.task_id, ref: a });
  for (const t of q.backlog) items.push({ key: `b:${t.id}`, type: 'backlog', title: t.title, sub: t.body || '', who: t.proposed_by || 'user', when: t.created_at, topic: t, ref: t });
  return items;
}
function vMine() {
  const all = mineItems();
  const f = S.f.mine || 'all';
  const count = v => all.filter(i => i.type === v).length;
  const urgent = all.filter(i => i.type !== 'backlog');
  const list = f === 'all' ? all : all.filter(i => i.type === f);
  if (!list.some(i => i.key === S.mineSel)) S.mineSel = (f === 'all' ? urgent[0] || list[0] : list[0])?.key || null;
  const sel = list.find(i => i.key === S.mineSel) || null;
  const narrow = matchMedia('(max-width: 1100px)').matches;
  const pick = it => { if (narrow) return openMineItem(it); if (S.mineSel !== it.key) S.editTopic = null; S.mineSel = it.key; S._keepScroll = true; render(); };
  const tabs = h('div', { class: 'mine-tabs', role: 'tablist', 'aria-label': '내 차례 소분류' },
    [['all', '전체', 'user', '', urgent.length], ...MINE_TYPES.map(([v, l, i, c]) => [v, l, i, c, count(v)])].map(([v, l, i, c, n]) =>
      h('button', { role: 'tab', 'aria-selected': String(f === v), class: `mine-tab${n && c ? ' ' + c : ''}`, onclick: () => { S.f.mine = v; S.mineSel = null; S.mineSelecting = false; S.editTopic = null; render(); } },
        icon(i), h('span', null, l), h('b', null, n))));
  // 착수 고르기: 여러 개 골라 한 번에 지우기
  const checked = S.mineChecked || (S.mineChecked = new Set());
  const selecting = f === 'backlog' && S.mineSelecting;
  const toggle = it => { checked.has(it.topic.id) ? checked.delete(it.topic.id) : checked.add(it.topic.id); S._keepScroll = true; render(); };
  const row = it => {
    const ty = MINE_TYPE[it.type];
    const on = selecting && checked.has(it.topic?.id);
    return h('button', { class: `mine-row${on ? ' checked' : ''}`, role: 'option', 'aria-selected': String(selecting ? on : !narrow && it.key === S.mineSel), onclick: () => selecting ? toggle(it) : pick(it) },
      selecting ? h('span', { class: `check${on ? ' on' : ''}`, 'aria-hidden': 'true' }, on ? icon('check') : null) : h('span', { class: `lead-ico ${ty.cls}` }, icon(ty.icon)),
      h('span', { class: 'body' },
        h('span', { class: 'kind' }, h('b', null, ty.label), it.topic && it.type !== 'backlog' ? h('span', { class: 'topic' }, it.topic.title) : null),
        h('span', { class: 't clamp-2' }, it.title),
        it.sub && it.type !== 'backlog' ? h('span', { class: 's clamp-1' }, it.sub) : null,
        h('span', { class: 'meta' }, av(it.who, true), h('span', null, person(it.who).name), histCount(it.topic, it.taskId), h('span', { class: 'when' }, fmtRel(it.when)))));
  };
  const group = (title, items) => items.length ? [h('div', { class: 'mine-group' }, title, h('b', null, items.length)), items.map(row)] : null;
  const listBody = !list.length ? empty(f === 'all' ? '지금 대응할 것이 없습니다.' : `${MINE_TYPE[f].label} 항목이 없습니다.`)
    : f === 'all' ? [group('대응할 것', urgent), group('착수 고르기 · 미처리 주제', all.filter(i => i.type === 'backlog'))] : list.map(row);
  const ids = list.filter(i => checked.has(i.topic?.id)).map(i => i.topic.id);
  const dropped = S.d.topics.filter(t => t.status === 'dropped');
  const listTools = f !== 'backlog' ? null : h('div', { class: 'mine-list-tools' }, selecting
    ? [h('b', null, `${ids.length}건 선택`),
      h('button', { class: 'btn sm', onclick: () => { ids.length === list.length ? checked.clear() : list.forEach(i => checked.add(i.topic.id)); render(); } }, ids.length === list.length ? '모두 해제' : '모두 선택'),
      h('button', { class: 'btn sm danger', disabled: ids.length ? null : true, onclick: () => dropTopics(ids, false).then(() => { S.mineSelecting = false; render(); }) }, icon('x'), `${ids.length}건 삭제`),
      h('button', { class: 'btn sm', onclick: () => { S.mineSelecting = false; checked.clear(); render(); } }, '취소')]
    : [h('span', { class: 'hint' }, '누르면 오른쪽에서 내용을 보고 착수·담당·수정·삭제를 정합니다.'),
      list.length ? h('button', { class: 'btn sm', onclick: () => { S.mineSelecting = true; checked.clear(); render(); } }, icon('check'), '여러 개 골라 지우기') : null]);
  const droppedBox = f === 'backlog' && dropped.length ? h('details', { class: 'mine-dropped' },
    h('summary', null, `삭제한 주제 ${dropped.length}건 · 되살리기`),
    dropped.map(t => h('div', { class: 'dropped-row' }, h('span', { class: 'clamp-1' }, t.title), h('button', { class: 'btn sm', onclick: () => dropTopics(t.id, true) }, icon('refresh'), '되살리기')))) : null;
  const detail = sel ? mineDetail(sel, null) : null;
  return [
    head('MY TURN', '내 차례', urgent.length ? `대응할 것 ${urgent.length}건 · 미처리 주제 ${count('backlog')}건` : `지금 대응할 것 없음 · 미처리 주제 ${count('backlog')}건`),
    tabs,
    h('div', { class: `mine-split${narrow ? ' narrow' : ''}` },
      h('div', { class: 'card mine-list', role: 'listbox', 'aria-label': '내 차례 목록', 'aria-multiselectable': selecting ? 'true' : null }, listTools, listBody, droppedBox),
      narrow ? null : h('section', { class: 'card mine-detail', 'aria-label': '선택한 항목' },
        detail ? [h('div', { class: 'mine-detail-h' }, h('span', { class: 'eyebrow' }, detail.eyebrow),
            h('button', { class: 'btn sm', title: '크게 보기', onclick: () => openMineItem(sel) }, icon('arrow'), '크게 보기')),
          h('div', { class: 'mine-detail-b' }, h('div', { class: 'ms-main' }, detail.main), h('div', { class: 'ms-side' }, detail.side))]
          : h('div', { class: 'mine-detail-empty' }, empty('왼쪽에서 항목을 고르면 내용과 히스토리가 여기에 보입니다.')))),
  ];
}
// 좁은 화면·"크게 보기": 같은 내용을 가운데 모달로
function openMineItem(it) {
  const d = mineDetail(it, () => { const again = mineItems().find(x => x.key === it.key); again ? openMineItem(again) : closeDrawer(); });
  modalSplit(d.eyebrow, d.main, d.side);
}
function mineDetail(it, redraw) {
  if (it.type === 'decision') return { eyebrow: '결정·승인 요청', ...decisionParts(it.ref, redraw) };
  if (it.type === 'question') return { eyebrow: 'AI 질문', ...questionParts(it.topic, it.ref, redraw) };
  if (it.type === 'test') return { eyebrow: '실게임·확인 대기', ...testParts(it.ref, it.topic, redraw) };
  if (it.type === 'action') return { eyebrow: '할 일', ...actionParts(it.ref, it.topic, redraw) };
  return { eyebrow: '착수 고르기 · 미처리 주제', ...backlogParts(it.ref, redraw) };
}
function testParts(t, topic, redraw) {
  const after = () => { if (redraw) redraw(); };
  return {
    main: [
      h('div', { style: { display: 'flex', gap: '6px', 'flex-wrap': 'wrap', 'align-items': 'center' } }, priChip(t.priority), stChip(t.stage), t.area ? h('span', { class: 'tag' }, t.area) : null, h('span', { class: 'when' }, `${fmtAbs(t.updated_at)} · ${fmtRel(t.updated_at)}`)),
      h('h3', { class: 'd-title' }, t.title),
      t.next_action ? [h('h4', null, '확인할 것'), h('div', { class: 'callout warn' }, t.next_action)] : null,
      t.live_test ? [h('h4', null, '실게임'), h('p', { class: 'd-text' }, t.live_test)] : null,
      t.summary ? [h('h4', null, '현황'), h('p', { class: 'd-text' }, t.summary)] : null,
      (t.evidence || []).length ? [h('h4', null, '근거'), h('ul', { class: 'd-list' }, [].concat(t.evidence).map(e => h('li', { class: 'mono' }, e)))] : null,
      h('h4', null, '확인 결과'),
      h('div', { class: 'choice-row' },
        h('button', { class: 'btn primary', onclick: () => setStages([t.id], 'done', after) }, icon('check'), '확인 완료'),
        h('button', { class: 'btn', onclick: () => setStages([t.id], 'blocked', after) }, icon('alert'), '문제 있음'),
        h('button', { class: 'btn', onclick: () => { ack(`mine-test:${t.id}:${t.updated_at}`); after(); } }, icon('clock'), '나중에'),
        h('button', { class: 'btn', onclick: () => openTask(t) }, icon('tasks'), '작업 전체 보기')),
      thread({ kind: 'task', id: t.id, title: t.title }, redraw, { compose: true, title: '담당에게 전할 말', placeholder: '문제가 있었다면 어떤 화면·상황이었는지 적어 보내세요', to: t.owner === 'astra' ? 'dev-astra' : 'dev-claude' }),
    ],
    side: historyPanel(topic, t, null),
  };
}
function actionParts(a, topic, redraw) {
  const task = a.task_id ? S.d.tasks.find(t => t.id === a.task_id) : null;
  return {
    main: [
      h('div', { class: 'when' }, a.since ? `${fmtAbs(a.since)} · ${fmtRel(a.since)}` : ''),
      h('h3', { class: 'd-title' }, a.title),
      a.detail ? h('div', { class: 'callout' }, a.detail) : null,
      h('div', { class: 'choice-row' },
        h('button', { class: 'btn primary', onclick: () => { ack(`ua:${a.id}`); if (redraw) redraw(); } }, icon('check'), '했음'),
        task ? h('button', { class: 'btn', onclick: () => openTask(task) }, icon('tasks'), '관련 작업 보기') : null),
      task ? thread({ kind: 'task', id: task.id, title: task.title }, redraw, { compose: true, title: '담당에게 전할 말', placeholder: '해 본 결과나 막힌 점을 적어 보내세요', to: task.owner === 'astra' ? 'dev-astra' : 'dev-claude' }) : null,
    ],
    side: historyPanel(topic, task, null),
  };
}
// ------------------------------------------------------------ 주제 수정·삭제(목록에서 빼기)·되살리기
// 원본은 PC에 그대로 남고, 삭제한 주제는 '삭제한 주제'에서 언제든 되살릴 수 있다
async function dropTopics(ids, restore) {
  ids = [].concat(ids);
  if (!ids.length) return;
  try {
    await sendOps('topic-drop', { topics: ids, restore: !!restore, note: '' }, restore ? `주제 ${ids.length}건 되살리기` : `주제 ${ids.length}건 삭제`);
    S.mineChecked?.clear();
    toast(restore ? `${ids.length}건을 되살렸습니다` : `${ids.length}건을 목록에서 뺐습니다 · 주제 화면 아래 "삭제한 주제"에서 되살릴 수 있습니다`);
    S._keepScroll = true; render();
  } catch (e) { toast(e.message); }
}
function topicEditForm(t, done) {
  const title = h('input', { value: t.title || '', maxlength: '200', 'aria-label': '제목', 'data-draft': `edit:${t.id}:title` });
  const body = h('textarea', { rows: '10', 'aria-label': '내용', 'data-draft': `edit:${t.id}:body` }, t.body || '');
  const kind = h('select', { 'aria-label': '유형' }, ['기능·개선', '버그', '조사·분석', '디자인', '운영·도구', '기타'].map(k => h('option', { selected: k === t.kind ? true : null }, k)));
  const pri = h('select', { 'aria-label': '우선순위' }, [['P0', 'P0 긴급'], ['P1', 'P1 높음'], ['P2', 'P2 보통'], ['P3', 'P3 낮음']].map(([v, l]) => h('option', { value: v, selected: v === (t.priority || 'P2') ? true : null }, l)));
  const save = h('button', { class: 'btn primary', onclick: async () => {
    if (!title.value.trim()) { title.focus(); toast('제목을 적어주세요'); return; }
    save.disabled = true;
    try {
      await sendOps('topic-edit', { topic: t.id, title: title.value.trim(), body: body.value.trim(), kind: kind.value, priority: pri.value }, `주제 수정: ${title.value.trim()}`);
      clearDraft(`edit:${t.id}:title`, `edit:${t.id}:body`); toast('수정했습니다'); done(true);
    } catch (e) { toast(e.message); } finally { save.disabled = false; }
  } }, icon('check'), '저장');
  return h('div', { class: 'edit-form' },
    h('label', null, h('span', null, '제목'), title),
    h('div', { class: 'row' }, h('label', null, h('span', null, '유형'), kind), h('label', null, h('span', null, '우선순위'), pri)),
    h('label', null, h('span', null, '내용'), body),
    h('div', { class: 'choice-row' }, save, h('button', { class: 'btn', onclick: () => { clearDraft(`edit:${t.id}:title`, `edit:${t.id}:body`); done(false); } }, '취소')),
    h('div', { class: 'hint' }, '원래 메모는 PC에 그대로 남고, 수정본이 화면과 AI 작업 지시에 쓰입니다.'));
}
// 주제 머리 줄의 수정·삭제 버튼. 수정 중에는 그 자리에 입력칸이 열린다
function topicTools(t, again) {
  const dropped = t.status === 'dropped';
  return h('div', { class: 'topic-tools' },
    dropped ? null : h('button', { class: 'btn sm', onclick: () => { S.editTopic = t.id; again(); } }, icon('file'), '수정'),
    dropped ? h('button', { class: 'btn sm primary', onclick: () => dropTopics(t.id, true).then(again) }, icon('refresh'), '되살리기')
      : h('button', { class: 'btn sm danger', onclick: () => dropTopics(t.id, false).then(again) }, icon('x'), '삭제'));
}
function droppedCard() {
  const list = S.d.topics.filter(t => t.status === 'dropped').sort((a, b) => toMs(b.dropped_at) - toMs(a.dropped_at));
  if (!list.length) return null;
  return h('details', { class: 'card section-gap dropped-card' },
    h('summary', null, h('b', null, `삭제한 주제 ${list.length}건`), h('span', { class: 'hint' }, ' · 되살리면 원래 자리(미처리·새 주제)로 돌아갑니다')),
    h('div', { class: 'list' }, list.map(t => h('div', { class: 'item' },
      h('span', { class: 'lead-ico' }, icon('x')),
      h('div', { class: 'body' }, h('div', { class: 't' }, t.title), h('div', { class: 's' }, `${t.id} · 삭제 ${fmtRel(t.dropped_at)}${t._pendingDrop ? ' · 반영 대기' : ''}`)),
      h('button', { class: 'btn sm', onclick: () => dropTopics(t.id, true) }, icon('refresh'), '되살리기')))));
}

// 미처리 주제: 내용·히스토리를 보고 자동 배분 또는 담당을 골라 착수, 착수 전에 전할 말
function backlogParts(t, redraw) {
  const pendAct = pending.all().find(p => p.type === 'activate' && p.topic === t.id);
  const pendAsg = pending.all().find(p => p.type === 'assign' && p.topic === t.id);
  const sel = h('select', { 'aria-label': '담당 고르기' }, agentOptions(pendAsg ? pendAsg.agent : '', [h('option', { value: '' }, '담당 고르기')]));
  const busy = b => { b.disabled = true; return () => { b.disabled = false; }; };
  const auto = h('button', { class: 'btn primary', onclick: async () => {
    const done = busy(auto);
    try { await sendOps('activate', { topic: t.id }, `착수 지시: ${t.title}`); render(); if (redraw) redraw(); } catch (e) { toast(e.message); } finally { done(); }
  } }, icon('play'), '자동 배분으로 착수');
  const mine = h('button', { class: 'btn', onclick: async () => {
    if (!sel.value) { toast('담당을 먼저 고르세요'); sel.focus(); return; }
    const done = busy(mine);
    try {
      await sendOps('assign', { topic: t.id, agent: sel.value, note: '' }, `주제 담당 → ${person(sel.value).name}`);
      await sendOps('activate', { topic: t.id }, `착수 지시: ${t.title}`);
      render(); if (redraw) redraw();
    } catch (e) { toast(e.message); } finally { done(); }
  } }, icon('agents'), '이 담당으로 착수');
  const again = () => { if (redraw) redraw(); else { S._keepScroll = true; render(); } };
  const editing = S.editTopic === t.id;
  return {
    main: [
      h('div', { class: 'd-head' }, topicChip(t.status), priChip(t.priority), t.kind ? h('span', { class: 'tag' }, t.kind) : null,
        t._pendingEdit || t.edited_at ? h('span', { class: 'tag' }, t._pendingEdit ? '수정 반영 대기' : '수정됨') : null,
        h('span', { class: 'when' }, `등록 ${fmtAbs(t.created_at)}`), editing ? null : topicTools(t, again)),
      editing ? topicEditForm(t, () => { S.editTopic = null; again(); }) : [
        h('h3', { class: 'd-title' }, t.title),
        t.body ? [h('h4', null, t.edited_at || t._pendingEdit ? '내용' : '원래 메모'), longText(t.body)] : null],
      h('h4', null, '착수 정하기'),
      pendAct || pendAsg ? h('div', { class: 'callout' }, h('span', { class: 'st user_test' }, icon('clock'), '반영 대기'),
        ' ', pendAsg ? `${person(pendAsg.agent).full}에게 배정했습니다. ` : '', pendAct ? '착수 지시를 보냈습니다. 다음 동기화 때 진행됩니다.' : '') : null,
      h('div', { class: 'start-box' },
        h('div', { class: 'start-opt' }, h('b', null, '자동 배분'), h('span', { class: 'hint' }, '규칙(PC·AI 역할, 부하)에 따라 담당이 정해집니다.'), auto),
        h('div', { class: 'start-opt' }, h('b', null, '담당 직접 선정'), h('span', { class: 'hint' }, '고른 작업자에게 바로 배정하고 착수합니다.'), h('div', { class: 'row' }, sel, mine))),
      thread({ kind: 'topic', id: t.id, title: t.title }, redraw, { compose: true, title: '착수 전에 전할 말 (선택)', placeholder: '범위·우선순위·주의할 점을 적으면 담당에게 같이 전달됩니다' }),
    ],
    side: historyPanel(t, null, null),
  };
}

function decisionsNeededCard() {
  const list = S.data.decisions_needed;
  const open = list.filter(q => !S.d.answers[q.id]);
  return card('결정이 필요한 문제', { big: open.length, unit: '건' },
    list.length ? h('div', { class: 'list' }, list.map(q => {
      const ans = S.d.answers[q.id];
      return h('div', { class: 'item' },
        h('span', { class: `lead-ico ${ans ? 'good' : 'warn'}` }, icon(ans ? 'check' : 'scale')),
        h('div', { class: 'body' }, h('button', { class: 't clamp-3 linkless', onclick: () => openDecisionNeeded(q) }, q.question),
          q.recommendation && !ans ? h('div', { class: 's' }, h('b', null, '권장 '), q.recommendation) : null,
          ans ? h('div', { class: 's' }, h('b', null, '내 결정: '), ans.choice || '(메모)', ans.note ? ' — ' + ans.note : '', ' · ', ans.pending ? '반영 대기' : '전달됨')
            : h('div', { class: 'choice-row' }, h('button', { class: 'btn sm primary', onclick: () => openDecisionNeeded(q) }, icon('scale'), `열어서 결정${(q.options || []).length ? ` (선택지 ${q.options.length}개)` : ''}`)),
          h('div', { class: 'meta' }, h('span', { class: 'wait' }, av(q.owner || 'user', true), (person(q.owner || 'user').name) + ' 결정'),
            h('span', { class: 'tag' }, `${person(q._author || 'claude').name} 제기`), topicTag(q.task_id), histCount(topicById(q.task_id), q.task_id), h('span', { class: 'when' }, fmtRel(q.since)))));
    })) : empty('지금 결정할 문제가 없습니다.'));
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
function teamCompact() {
  const agents = S.data.agents || [];
  if (!agents.length) return teamGrid();
  return h('div', { class: 'team-rows' }, agents.map(a => {
    const st = agentState(a), s = agentStats(a.id);
    return h('button', { class: 'team-row-item', onclick: () => go('agents') },
      av(a.id), h('div', { class: 'body' }, h('div', { class: 't' }, `${a.pc_label} · ${a.label || a.id}`),
        h('div', { class: 's clamp-2' }, a.current ? a.current.project : '지금 하는 일을 알리지 않음')),
      h('span', { class: `st ${st.cls}` }, icon(st.icon), st.label),
      h('span', { class: 'tag' }, `주제 ${s.assigned.length}`), s.turn.length ? h('span', { class: 'tag' }, `차례 ${s.turn.length}`) : null);
  }));
}
function teamGrid() {
  const d = S.d, data = S.data;
  if ((data.agents || []).length) {
    return h('div', { style: { display: 'grid', gap: '12px' } },
      h('div', { class: 'agent-grid' }, data.agents.map(agentCard)),
      h('button', { class: 'btn', style: { 'justify-self': 'start' }, onclick: () => go('agents') }, icon('agents'), 'PC별 작업자 현황 전체 보기'));
  }
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

// ------------------------------------------------------------ 작업자 (PC별 AI 현황)
function agentStats(id) {
  const topics = S.d.topics.filter(t => !['done', 'parked', 'dropped'].includes(t.status));
  return {
    assigned: topics.filter(t => t.assignee === id),
    turn: topics.filter(t => t.turn === id),
    tasks: S.d.tasks.filter(t => t.stage !== 'done' && (t.owner === id || LEGACY[t.owner] === id || t.waiting_on === id || LEGACY[t.waiting_on] === id)),
  };
}
function agentCard(a) {
  const st = agentState(a), s = agentStats(a.id), cur = a.current;
  return h('div', { class: 'agent' },
    h('div', { class: 'hd' }, av(a.id), h('div', { style: { 'min-width': '0' } }, h('div', { class: 'nm' }, a.label || a.id), h('div', { class: 'rl' }, `${a.pc_label} · ${a.ai === 'gpt' ? 'GPT 계열' : 'Claude 계열'} · ${a.id}`)),
      h('span', { class: `st ${st.cls}`, style: { 'margin-left': 'auto' } }, icon(st.icon), st.label)),
    cur ? h('div', { class: 'now' }, h('b', null, cur.project), (cur.task || cur.topic) ? h('div', { class: 'muted', style: { 'font-size': '12px' } }, [cur.task, cur.topic].filter(Boolean).join(' · ')) : null,
      cur.note ? h('div', { class: 'muted', style: { 'font-size': '12px' } }, cur.note) : null,
      h('div', { class: 'muted', style: { 'font-size': '12px' } }, `${fmtRel(cur.since)}부터`))
      : h('div', { class: 'now idle' }, '지금 하는 일을 알리지 않았습니다.'),
    h('div', { class: 'stats' }, h('div', null, h('b', null, s.assigned.length), h('span', null, '맡은 주제')), h('div', null, h('b', null, s.turn.length), h('span', null, '내 차례')),
      h('div', null, h('b', null, s.tasks.length), h('span', null, '관련 작업'))),
    s.assigned.length ? h('div', { class: 'list' }, s.assigned.slice(0, 4).map(t => h('button', { class: 'item', onclick: () => openTopic(t) },
      h('span', { class: 'body' }, h('div', { class: 't clamp-2' }, t.title), h('div', { class: 'meta' }, topicChip(t.status), priChip(t.priority), t.turn === a.id ? h('span', { class: 'tag' }, '내 차례') : null))))) : null,
    a.health && a.health.state && a.health.state !== 'ok' ? h('div', { class: `callout ${a.health.needs_user ? 'warn' : ''}` }, h('b', null, `${HEALTH[a.health.state] || '실행 오류'} · ${fmtRel(a.health.since || a.health.at)}부터`), h('div', null, a.health.fix || a.health.message)) : null,
    (() => { const r = (S.data.runs || []).find(x => x.agent === a.id); return r ? h('div', { class: 'muted', style: { 'font-size': '12px' } }, `마지막 자동 실행 ${fmtRel(r.ended || r.started)} · ${RUN_RESULT[r.result] || r.result}${r.topic ? ' · ' + ((topicById(r.topic) || {}).title || r.topic) : ''}`) : null; })(),
    h('div', { class: 'muted', style: { 'font-size': '12px' } }, `마지막 신호 ${fmtRel(a.last_seen || a.pc_synced)}`));
}
// 허브 공지: 모든 PC 작업자에게 보낸 작업 방식 변경. 누가 확인했는지(대화 세션 확인 / 실행기 반영) 보인다
function noticesCard(agents) {
  const list = S.data.notices || [];
  if (!list.length) return null;
  const targets = n => agents.filter(a => (n.to || ['all']).includes('all') || (n.to || []).includes(a.id));
  return h('div', { class: 'section-gap' }, card('허브 공지', { big: list.length, unit: '건' },
    h('div', { class: 'list' }, list.slice(0, 6).map((n, i) => {
      const tg = targets(n), acked = tg.filter(a => (n.acks || {})[a.id]);
      return h('details', { class: 'notice', open: i === 0 ? true : null },
        h('summary', null, h('b', null, n.title), h('span', { class: `st ${acked.length === tg.length ? 'done' : 'user_test'}` }, `확인 ${acked.length}/${tg.length}`), h('span', { class: 'when' }, fmtRel(n.ts))),
        h('div', { class: 'notice-acks' }, tg.map(a => { const k = (n.acks || {})[a.id];
          return h('span', { class: `tag ${k ? '' : 'muted'}` }, av(a.id, true), `${a.pc_label} ${a.label || a.id}: `, k ? `${k.via === 'session' ? '확인' : '실행기 반영'} ${fmtRel(k.ts)}` : '미확인'); })),
        longText(n.body || ''));
    }))));
}
function runRow(r) {
  return h('div', { class: `run-row r-${r.result}` }, h('span', { class: 'st ' + ({ ok: 'done', partial: 'user_test', fail: 'blocked', running: 'progress' }[r.result] || 'neutral') }, RUN_RESULT[r.result] || r.result),
    h('div', { class: 'run-b' }, h('div', null, h('b', null, person(r.agent).name), ` · ${fmtAbs(r.started)}${r.ended ? ' → ' + fmtAbs(r.ended).slice(-5) : ''} · 이유: ${r.reason || '-'}`),
      r.summary ? h('div', { class: 'clamp-2' }, r.summary) : null,
      (r.failed || []).length ? h('div', { class: 'run-fail' }, '실패: ', r.failed.join('; ')) : null,
      r.error ? h('div', { class: 'run-fail' }, `원인: ${r.error}`, r.fix ? ` · 조치: ${r.fix}` : '') : null));
}
function vAgents() {
  const nodes = S.data.nodes || [], agents = S.data.agents || [];
  const r = S.data.meta.routing || {};
  if (!agents.length) return [head('AGENTS', '작업자', null), card('작업자 없음', null, empty('아직 등록된 작업자가 없습니다. 각 PC에서 node.py init으로 등록합니다.'))];
  const groups = nodes.map(n => ({ ...n, list: agents.filter(a => a.pc === n.pc) }));
  return [
    head('AGENTS', '작업자 현황', `${nodes.length}대 · ${agents.length}명`),
    h('div', { style: { display: 'grid', gap: '18px' } }, groups.map(g => h('section', { class: 'pc-group' },
      h('div', { class: 'pc-head' }, h('h3', null, g.label || g.pc), h('span', { class: 'tag' }, g.role === 'hub' ? '허브 · 배분 담당' : '작업 노드'),
        g.error ? h('span', { class: 'st blocked' }, icon('alert'), g.error) : h('span', { class: 'muted', style: { 'font-size': '12px' } }, `마지막 동기화 ${fmtRel(g.synced_at)}`)),
      g.list.length ? h('div', { class: 'agent-grid' }, g.list.map(agentCard)) : empty('이 PC의 작업자 정보가 없습니다.')))),
    noticesCard(agents),
    h('div', { class: 'grid g-2 section-gap' },
      card('자동 배분 규칙', { right: h('span', { class: `st ${r.auto === false ? 'neutral' : 'done'}` }, icon(r.auto === false ? 'pause' : 'check'), r.auto === false ? '꺼짐' : '켜짐') },
        h('div', { class: 'hint', style: { display: 'grid', gap: '6px' } },
          h('div', null, '새 주제는 허브(', h('b', null, (nodes.find(n => n.role === 'hub') || {}).label || '개발컴'), ')가 한 곳에서만 배분합니다. 같은 일이 두 곳에서 시작되지 않게 하는 핵심 규칙입니다.'),
          (r.rules || []).map(x => h('div', null, '• ', h('b', null, x['이름'] || '규칙'), ` — ${(x.match || []).slice(0, 6).join(', ')}${(x.match || []).length > 6 ? ' …' : ''} → `,
            x.prefer_pc ? `${(nodes.find(n => n.pc === x.prefer_pc) || {}).label || x.prefer_pc} ` : '', x.prefer_ai ? `${x.prefer_ai} ` : '', `+${x.weight}`)),
          h('div', null, `맡은 주제가 많으면 감점, ${Math.round((r.stale_minutes || 120) / 60)}시간 넘게 신호가 없으면 크게 감점합니다. 동점이면 사령탑이 맡습니다.`),
          h('div', null, '주제 상세에서 담당을 직접 바꾸면 그 지정이 우선합니다.'))),
      card('PC 연결', null, h('div', { class: 'hint', style: { display: 'grid', gap: '6px' } },
        h('div', null, '다른 PC를 연결하려면 그 PC에서 저장소를 받고, ', h('span', { class: 'mono' }, '서버컴-연결.md'), ' 안내를 그 PC의 AI에게 따르게 하면 됩니다.'),
        h('div', null, '각 PC는 자기 기록만 암호화해서 올리고(docs/nodes/<PC>.enc.json), 배분된 주제는 그 PC 작업자의 수신 폴더로 들어갑니다.'),
        h('div', null, '작업자는 일을 시작할 때 ', h('span', { class: 'mono' }, 'node.py status'), '로 지금 하는 일을 알려야 이 화면에 보입니다.')))),
  ];
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
    h('div', { class: 'section-gap board topics' }, TOPIC_STATES.filter(s => !s.hidden).map(s => {
      const list = d.topics.filter(t => (t.status || 'new') === s.id).sort((a, b) => toMs(b.updated_at || b.created_at) - toMs(a.updated_at || a.created_at));
      return h('div', { class: 'col' }, h('div', { class: 'col-h' }, topicChip(s.id), h('span', { class: 'badge' }, list.length)),
        list.length ? list.map(topicCard) : h('div', { class: 'empty' }, '없음'));
    })),
    droppedCard(),
  ];
}
function composerCard(repo) {
  const title = h('input', { id: 'tp-title', placeholder: '주제 (예: 거래소 검색 속도 개선)', maxlength: '120', required: true, 'data-draft': 'new-topic:title' });
  const body = h('textarea', { id: 'tp-body', placeholder: '대략적인 내용·배경·원하는 결과. 정리 안 된 메모여도 됩니다.', 'data-draft': 'new-topic:body' });
  const kind = h('select', { id: 'tp-kind', 'aria-label': '유형' }, ['기능·개선', '버그', '조사·분석', '디자인', '운영·도구', '기타'].map(k => h('option', null, k)));
  const pri = h('select', { id: 'tp-pri', 'aria-label': '우선순위' }, ['P2 보통', 'P1 높음', 'P0 긴급', 'P3 낮음'].map(k => h('option', { value: k.slice(0, 2) }, k)));
  const prefer = h('select', { id: 'tp-prefer', 'aria-label': '담당 선호' }, (S.data.agents || []).length
    ? agentOptions(null, [h('option', { value: 'auto' }, '자동 배분 (추천)')]).map(o => { if (o.value !== 'auto') o.textContent += ' 우선'; return o; })
    : [['auto', '자동 배분'], ['claude', 'Claude 우선'], ['astra', 'Astra 우선']].map(([v, l]) => h('option', { value: v }, l)));
  const status = h('div', { class: 'hint', role: 'status', 'aria-live': 'polite' });
  function make() {
    if (!title.value.trim()) { title.focus(); status.textContent = '주제를 적어주세요.'; return null; }
    const topic = { id: newId('T', 3), title: title.value.trim(), body: body.value.trim(), kind: kind.value, priority: pri.value, prefer: prefer.value, created_at: new Date().toISOString(), from: 'dashboard' };
    return { topic };
  }
  function remember(topic) {
    const list = store.get('pendingTopics', []) || [];
    list.push({ id: topic.id, title: topic.title, created_at: topic.created_at });
    store.set('pendingTopics', list);
    title.value = ''; body.value = ''; clearDraft('new-topic:title', 'new-topic:body');
  }
  const send = h('button', { class: 'btn primary', disabled: !repo, onclick: async () => {
    const r = make(); if (!r) return;
    send.disabled = true;
    try {
      const res = await sendBlob('topic', r.topic);
      remember(r.topic); afterSend(res);
      S._keepScroll = true; render();
    } catch (e) { status.textContent = e.message; } finally { send.disabled = false; }
  } }, icon('send'), '보내기');
  const copy = h('button', { class: 'btn', onclick: async () => {
    const r = make(); if (!r) return;
    try { await navigator.clipboard.writeText(`python topics.py add-blob ${await sealTopic(r.topic)}`); remember(r.topic); toast('복사했습니다. PC 터미널에 붙여넣으세요.'); S._keepScroll = true; render(); }
    catch { status.textContent = '클립보드 복사가 막혔습니다.'; }
  } }, icon('copy'), '암호문 복사 (PC용)');
  return card('주제 던지기', null,
    h('div', { class: 'composer' }, title, body, h('div', { class: 'row' }, kind, pri, prefer),
      h('div', { class: 'row' }, send, copy),
      !repo ? h('div', { class: 'callout warn' }, h('b', null, 'GitHub 저장소가 아직 연결되지 않았습니다. '), '연결 전에는 "암호문 복사"로 PC에서 넣을 수 있습니다.') : null,
      status, sendHint(),
      h('div', { class: 'hint' }, '내용은 이 브라우저에서 대시보드 비밀번호 키로 암호화됩니다. 이슈에는 암호문과 주제 번호만 남습니다.')));
}
function topicCard(t) {
  const last = (t.notes || []).at(-1);
  return h('button', { class: 'proj', onclick: () => openTopic(t) },
    h('div', { class: 'row' }, priChip(t.priority), t.kind ? h('span', { class: 'tag' }, t.kind) : null, t.linked_task_id ? h('span', { class: 'tag' }, '작업 연결') : null,
      (t.conflict || []).length ? h('span', { class: 'st blocked' }, icon('alert'), '중복 착수') : null),
    h('div', { class: 'ttl' }, t.title),
    phaseLine(t, true),
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
  S.sel = S.sel || new Set();
  const tasks = filterTasks(S.d.tasks, S.f.taskOwner);
  for (const id of [...S.sel]) if (!tasks.some(t => t.id === id)) S.sel.delete(id);
  const staleKeys = S.d.missed.filter(i => i.key.startsWith('stale:') && !S.acks.has(i.key) && !S.serverAcks.has(i.key)).map(i => i.key);
  const pick = (id, on) => { on ? S.sel.add(id) : S.sel.delete(id); S._keepScroll = true; render(); };
  const selCard = t => h('div', { class: `sel-wrap${S.sel.has(t.id) ? ' on' : ''}` },
    h('label', { class: 'sel-box', title: '선택' }, h('input', { type: 'checkbox', checked: S.sel.has(t.id), 'aria-label': `${t.title} 선택`, onchange: e => pick(t.id, e.target.checked) })),
    projCard(t), t._pendingStage ? h('span', { class: 'st user_test pend-tag' }, icon('clock'), '단계 반영 대기') : null);
  const ids = [...S.sel];
  return [
    head('TASKS', '업무 보드', null,
      chips([['all', '전체'], ['claude', 'Claude'], ['astra', 'Astra'], ['cli', 'CLI'], ['user', '나 대기']], S.f.taskOwner, v => { S.f.taskOwner = v; render(); }, '담당 필터'),
      staleKeys.length ? h('button', { class: 'btn', onclick: () => ack(staleKeys) }, icon('check'), `멈춤 알림 ${staleKeys.length}건 모두 끄기`) : null,
      h('button', { class: 'btn', onclick: () => { const all = tasks.filter(t => t.stage !== 'done').map(t => t.id); const every = all.every(id => S.sel.has(id)); all.forEach(id => every ? S.sel.delete(id) : S.sel.add(id)); render(); } }, icon('check'), '진행 중 전체 선택'),
      stageFocus ? h('button', { class: 'btn', onclick: () => { S.f.stage = null; render(); } }, icon('x'), STAGE[stageFocus].label + ' 강조 해제') : null),
    h('div', { class: 'board' }, STAGES.map(s => {
      const list = tasks.filter(t => t.stage === s.id).sort(taskSort);
      return h('div', { class: 'col', style: stageFocus && stageFocus !== s.id ? { opacity: '.45' } : null },
        h('div', { class: 'col-h' }, h('span', { style: { color: `var(--st-${s.id})`, display: 'grid' } }, icon(s.icon)), s.label, h('span', { class: 'badge' }, list.length)),
        list.length ? list.map(selCard) : h('div', { class: 'empty' }, '없음'));
    })),
    h('p', { class: 'hint section-gap' }, '카드 오른쪽 위 칸을 눌러 여러 개를 고르면 아래에서 한꺼번에 단계를 바꿀 수 있습니다. 바꾼 단계는 PC 동기화 때 작업표에 반영되고 Claude 수신함에도 알림이 갑니다. 24시간 넘게 갱신이 없으면 "멈춤"으로 표시합니다.'),
    ids.length ? h('div', { class: 'bulkbar', role: 'region', 'aria-label': '선택한 작업 일괄 처리' },
      h('b', null, `${ids.length}건 선택`),
      STAGES.map(s => h('button', { class: 'btn', onclick: () => setStages(ids, s.id) }, h('span', { style: { color: `var(--st-${s.id})`, display: 'grid' } }, icon(s.icon)), s.label)),
      h('button', { class: 'btn', onclick: () => { const keys = S.d.missed.filter(i => ids.some(id => i.key.startsWith(`stale:${id}:`) || i.key.startsWith(`usertest:${id}:`))).map(i => i.key); if (keys.length) ack(keys); else toast('선택한 작업에 켜진 알림이 없습니다'); } }, icon('bell'), '알림 끄기'),
      h('button', { class: 'btn', onclick: () => { S.sel.clear(); render(); } }, icon('x'), '선택 해제')) : null,
  ];
}

// ------------------------------------------------------------ 메시지
function vMessages() {
  const all = S.data.messages;
  const f = S.f.msg;
  const filt = {
    all: () => true, a2c: m => m.sender === 'astra', c2a: m => m.sender === 'claude',
    unprocessed: m => S.d.unprocessed.includes(m), unanswered: m => S.d.unanswered.includes(m),
  }[f] || (() => true);
  const unp = S.d.unprocessed;
  const list = all.filter(filt).slice(0, 300);
  if (!S.msgSel || !list.includes(S.msgSel)) S.msgSel = list[0] || null;
  const narrow = matchMedia('(max-width: 880px)').matches;
  return [
    head('MESSAGES', 'Claude ↔ Astra', `${all.length}건`,
      chips([['all', '전체'], ['a2c', 'Astra→Claude'], ['c2a', 'Claude→Astra'], ['unprocessed', `미처리 ${unp.length}`], ['unanswered', `답장 대기 ${S.d.unanswered.length}`]], f, v => { S.f.msg = v; S.msgSel = null; render(); }, '메시지 필터'),
      unp.length ? h('button', { class: 'btn primary', onclick: () => ackMessages(unp.map(m => m.id)) }, icon('check'), `미처리 ${unp.length}건 모두 확인 처리`) : null),
    h('div', { class: 'split' },
      h('div', { class: 'card msg-list', role: 'listbox', 'aria-label': '메시지 목록' },
        list.length ? list.map(m => h('button', { class: 'msg', role: 'option', 'aria-selected': String(m === S.msgSel),
          onclick: () => { if (narrow) return openMessage(m); S.msgSel = m; S._keepScroll = true; render(); } },
          unp.includes(m) ? h('span', { class: 'new-dot', title: '미처리' }) : null,
          h('span', { class: 'route' }, av(m.sender, true), av(m.recipient, true)),
          h('span', { class: 'body' }, h('div', { class: 't clamp-2' }, m.title),
            h('div', { class: 's' }, h('span', null, fmtAbs(m.ts)), m.task_id ? h('span', { class: 'tag' }, m.task_id) : null,
              m.replies.length ? h('span', null, `답장 ${m.replies.length}`) : null))))
          : empty('해당 메시지가 없습니다.')),
      !narrow ? h('div', { class: 'card reader' }, S.msgSel ? messageDetail(S.msgSel) : empty('메시지를 선택하세요.')) : null),
  ];
}
function messageDetail(m, redraw) {
  const all = S.data.messages;
  const waitingAck = S.d.pendAckMsgs.has(m.id);
  const isUnprocessed = m.unprocessed && !waitingAck;
  redraw = redraw || (() => { S._keepScroll = true; render(); });
  const parent = m.in_reply_to ? all.find(x => x.id === m.in_reply_to) : null;
  const replies = m.replies.map(id => all.find(x => x.id === id)).filter(Boolean);
  const hdr = [['보낸이 → 받는이', `${person(m.sender).full} → ${person(m.recipient).full}`], ['시각', fmtAbs(m.ts)], ['message_id', m.id], ['kind', m.kind], ['task_id', m.task_id],
    ['in_reply_to', m.in_reply_to], ['파일', `${m.box}/${m.file}`], ...Object.entries(m.headers || {}).filter(([k]) => !['sender', 'recipient', 'kind', 'task_id', 'in_reply_to', 'route'].includes(k))];
  return [
    h('div', { class: 'row', style: { display: 'flex', gap: '6px', 'flex-wrap': 'wrap', 'margin-bottom': '8px' } },
      isUnprocessed ? h('span', { class: 'st progress' }, icon('inbox'), '미처리') : waitingAck ? h('span', { class: 'st user_test' }, icon('clock'), '확인 반영 대기')
        : h('span', { class: 'st neutral' }, icon('check'), m.box === 'inbox-astra' ? '발신' : '처리됨'),
      priChip(m.priority), m.task_id ? h('button', { class: 'tag', style: { cursor: 'pointer' }, onclick: () => openTaskById(m.task_id) }, m.task_id) : null,
      isUnprocessed ? h('button', { class: 'btn', style: { 'margin-left': 'auto', height: '30px' }, onclick: () => ackMessages([m.id], redraw) }, icon('check'), '확인 처리') : null),
    h('h3', null, m.title),
    h('dl', { class: 'hdr-table' }, hdr.filter(([, v]) => v).map(([k, v]) => [h('dt', null, k), h('dd', null, v)])),
    h('pre', { class: 'pre' }, m.body || '(본문 없음)'),
    parent || replies.length ? h('div', { class: 'thread' }, h('h4', { class: 'eyebrow', style: { margin: '6px 0 2px' } }, '스레드'),
      parent ? threadRow(parent, '원문') : null, replies.map(r => threadRow(r, '답장'))) : null,
    h('div', { style: { 'margin-top': '16px' } }, thread({ kind: 'message', id: m.id, title: m.title }, redraw, { placeholder: '이 메시지에 대한 답을 적으세요' })),
  ];
}
async function ackMessages(ids, redraw) {
  if (!ids.length) return;
  if (ids.length > 1 && !confirm(`미처리 메시지 ${ids.length}건을 확인 처리할까요?\nPC에서 done 폴더로 옮겨집니다(삭제 아님).`)) return;
  const keys = S.d.missed.filter(i => i.key.startsWith('unprocessed:')).map(i => i.key);
  try {
    await sendOps('ack', { messages: ids, keys }, `메시지 ${ids.length}건 확인`);
    S._keepScroll = true; render(); if (redraw) redraw();
  } catch (e) { toast(e.message); }
}
async function setStages(ids, stage, redraw) {
  if (!ids.length) return;
  const label = STAGE[stage].label;
  if (ids.length > 1 && !confirm(`작업 ${ids.length}건을 "${label}" 단계로 바꿀까요?`)) return;
  try {
    await sendOps('task-state', { ids, stage, note: '' }, `작업 ${ids.length}건 → ${label}`);
    S.sel?.clear(); S._keepScroll = true; render(); if (redraw) redraw();
  } catch (e) { toast(e.message); }
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
    h('div', { class: 'grid wide-2' },
    card('QA 검증 결과', { big: data.validations.length, unit: '건', cls: 'scroll-card' },
      data.validations.length ? h('div', { class: 'tbl-wrap' }, h('table', { class: 'tbl' },
        h('thead', null, h('tr', null, ['시각', '결과', '검증', '검토자', '실게임', '원인'].map(x => h('th', null, x)))),
        h('tbody', null, data.validations.map(v => h('tr', { class: 'click', tabindex: '0', onclick: () => openValidation(v), onkeydown: e => e.key === 'Enter' && openValidation(v) },
          h('td', { class: 'num', style: { 'white-space': 'nowrap' } }, fmtAbs(v.ts)),
          h('td', null, h('span', { class: `st ${v.result === 'pass' ? 'done' : v.result === 'fail' ? 'blocked' : 'neutral'}` }, icon(v.result === 'fail' ? 'alert' : 'done'), v.result === 'pass' ? '통과' : v.result === 'fail' ? '실패' : '불명')),
          h('td', null, h('b', null, v.id), h('div', { class: 'muted mono' }, v.job || '')),
          h('td', null, v.reviewer || '—'),
          h('td', null, v.live === 'pending' ? h('span', { class: 'st user_test' }, icon('flask'), '미실행') : '—'),
          h('td', null, v.root_cause || '—')))))) : empty('QA 결과가 없습니다.')),
    card('감사 원장', { big: ledger.length, unit: '건', cls: 'scroll-card',
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
  const pend = pending.all();
  return [
    head('SOURCES', '연결과 설정', null),
    h('div', { class: 'grid g-2' }, tokenCard(),
      card('보낸 요청 · 반영 대기', { big: pend.length, unit: '건' },
        pend.length ? h('div', { class: 'list' }, [...pend].reverse().map(p => h('div', { class: 'item' },
          h('span', { class: 'lead-ico' }, icon(p.type === 'reply' ? 'messages' : p.type === 'decide' ? 'scale' : p.type === 'task-state' ? 'tasks' : 'check')),
          h('div', { class: 'body' }, h('div', { class: 't' }, p.summary || p.type), h('div', { class: 's' }, `${fmtRel(p.created_at)} · ${p.via === 'api' ? '바로 전송됨' : 'GitHub 창으로 보냄(Submit 필요)'} · PC 동기화 후 사라짐`)),
          h('button', { class: 'icon-btn', title: '목록에서 지우기', 'aria-label': '목록에서 지우기', onclick: () => { pending.remove(p.id); S.d = derive(S.data); render(); } }, icon('x')))))
          : empty('대기 중인 요청이 없습니다.'),
        h('p', { class: 'hint' }, 'PC가 GitHub에서 요청을 가져와 처리하면 자동으로 목록에서 빠집니다. GitHub 창에서 Submit을 안 눌렀다면 여기서 지우고 다시 보내면 됩니다.'))),
    h('div', { class: 'section-gap' }), card('수집 상태', { big: data.sources.length, unit: '곳' }, h('div', { class: 'tbl-wrap' }, h('table', { class: 'tbl' },
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
        h('dt', null, '보드에서 뺀 작업'), h('dd', null, (m.hidden_tasks || []).length ? m.hidden_tasks.map(t => `${t.title || t.id}`).join(', ') : '없음'),
        h('dt', null, '저장소'), h('dd', null, m.repo || '미연결'))),
      card('갱신과 협업', null, h('div', { class: 'hint', style: { display: 'grid', gap: '8px' } },
        h('div', null, h('b', null, '갱신: '), '자동 동기화를 켜두면 PC가 10분마다 보낸 요청을 가져와 처리하고 바뀐 내용만 게시합니다(수동: ', h('span', { class: 'mono' }, 'publish.ps1'), '). 이 화면은 5분마다 새 게시본을 확인합니다.'),
        h('div', null, h('b', null, '화면에서 보낸 것: '), '답은 Claude/Astra 수신함으로, 일괄 확인은 inbox-claude → done 이동으로, 단계 변경은 작업표 덮어쓰기로 처리됩니다(사용자 기록 파일 data/user.json).'),
        h('div', null, h('b', null, 'Claude: '), h('span', { class: 'mono' }, 'data/claude.json'), ', ', h('span', { class: 'mono' }, 'topics/<id>/claude.json'), '에만 씁니다.'),
        h('div', null, h('b', null, 'Astra: '), h('span', { class: 'mono' }, 'data/astra.json'), ', ', h('span', { class: 'mono' }, 'topics/<id>/astra.json'), '에만 씁니다.'),
        h('div', null, h('b', null, '자동 수집: '), 'tasks.json · inbox-claude · inbox-astra · qa · handoffs · 감사 원장 · Claude 메모리.')))),
  ];
}

// ------------------------------------------------------------ 대화창 (화면에서 바로 답하기)
function commentsFor(t) {
  const same = c => c.target && c.target.kind === t.kind && c.target.id === t.id;
  const list = (S.data.comments || []).filter(same).map(c => ({ ...c, by: c._author || c.by || 'user' }));
  for (const p of pending.all().filter(p => p.type === 'reply' && same(p))) list.push({ by: 'user', to: p.to, ts: p.created_at, body: p.body, pending: true });
  return list.sort((a, b) => toMs(a.ts) - toMs(b.ts));
}
function sendHint() {
  return h('div', { class: 'hint' }, store.get('ghtoken')
    ? 'GitHub 토큰 연결됨 · 버튼을 누르면 바로 전송되고, PC 동기화 때 Claude/Astra 수신함에 들어갑니다.'
    : ['보내면 GitHub 창이 열립니다. "Submit new issue"를 눌러야 전송됩니다. ',
      h('button', { class: 'linkish', onclick: () => { closeDrawer(true); go('sources'); } }, '버튼 하나로 보내기 설정')]);
}
function thread(target, redraw, opts = {}) {
  const items = commentsFor(target);
  const ta = h('textarea', { placeholder: opts.placeholder || '여기에 답을 적으면 Claude에게 전달됩니다', rows: '3', 'aria-label': '답 입력', 'data-draft': `reply:${target.kind}:${target.id}` });
  const to = h('select', { 'aria-label': '받는 사람' }, (S.data.agents || []).length
    ? agentOptions(LEGACY[opts.to] || opts.to || 'dev-claude').map(o => { o.textContent += '에게'; return o; })
    : [h('option', { value: 'dev-claude' }, 'Claude에게'), h('option', { value: 'dev-astra' }, 'Astra에게')]);
  if (opts.to) to.value = LEGACY[opts.to] || opts.to;
  const send = h('button', { class: 'btn primary', onclick: async () => {
    const body = ta.value.trim();
    if (!body) { ta.focus(); return; }
    send.disabled = true;
    try {
      await sendOps('reply', { target: { kind: target.kind, id: target.id, title: (target.title || '').slice(0, 200) }, to: to.value, body }, `답 → ${person(to.value).name}`);
      ta.value = ''; clearDraft(`reply:${target.kind}:${target.id}`);
      render(); if (redraw) redraw();
    } catch (e) { toast(e.message); } finally { send.disabled = false; }
  } }, icon('send'), '보내기');
  // compose: 지난 대화는 옆 히스토리에 있으므로 입력칸만 보인다
  if (opts.compose) return h('div', { class: 'reply-box' }, h('h4', null, opts.title || '답 보내기'), h('div', { class: 'composer' }, ta, h('div', { class: 'row' }, to, send)), sendHint());
  return h('div', { class: 'reply-box' },
    h('h4', null, `대화 ${items.length}`),
    items.length ? h('div', { class: 'note-thread' }, items.map(c => h('div', { class: 'note' }, av(c.by),
      h('div', { class: 'bubble' }, h('div', { class: 'h' }, h('b', null, person(c.by).name), c.to ? h('span', null, '→ ' + person(c.to).name) : null,
        h('span', null, fmtAbs(c.ts)), c.pending ? h('span', { class: 'st user_test' }, icon('clock'), '반영 대기') : null),
        h('p', null, c.body))))) : h('div', { class: 'empty' }, '아직 대화가 없습니다. 아래에 적어 보내면 됩니다.'),
    h('div', { class: 'composer' }, ta, h('div', { class: 'row' }, to, send)),
    sendHint());
}
async function decide(q, choice, note, redraw) {
  try {
    await sendOps('decide', { decision_id: q.id, choice, note: note || '' }, `결정: ${choice || '메모'}`);
    clearDraft(`decide:${q.id}`);
    render(); if (redraw) redraw();
  } catch (e) { toast(e.message); }
}
function agentOptions(selected, extra) {
  const list = S.data.agents || [];
  return [...(extra || []), ...list.map(a => h('option', { value: a.id, selected: a.id === selected ? true : null }, `${a.pc_label} · ${a.label || a.id}`))];
}
function activateControl(t) {
  const pend = pending.all().find(p => p.type === 'activate' && p.topic === t.id);
  if (pend) return h('div', { class: 'callout' }, h('b', null, '착수 지시 반영 대기 · '), '다음 PC 동기화 때 자동 배분으로 담당이 정해집니다.');
  const btn = h('button', { class: 'btn primary', onclick: async () => {
    btn.disabled = true;
    try { await sendOps('activate', { topic: t.id }, `착수 지시: ${t.title}`); render(); openTopic(S.d.topics.find(x => x.id === t.id) || t); }
    catch (e) { toast(e.message); } finally { btn.disabled = false; }
  } }, icon('play'), '착수하기 (자동 배분)');
  return h('div', { class: 'callout' }, h('div', { style: { 'margin-bottom': '8px' } }, h('b', null, '미처리 주제입니다. '), '착수를 지시하면 다음 동기화 때 규칙에 따라 담당이 정해집니다. 담당을 직접 고르려면 아래 "담당 바꾸기"를 쓰세요.'), btn);
}
function assignControl(t) {
  if (!(S.data.agents || []).length || t.status === 'done') return null;
  const pend = pending.all().find(p => p.type === 'assign' && p.topic === t.id);
  const sel = h('select', { 'aria-label': '담당 바꾸기' }, agentOptions(pend ? pend.agent : t.assignee, t.assignee ? [] : [h('option', { value: '' }, '담당 고르기')]));
  const btn = h('button', { class: 'btn', onclick: async () => {
    if (!sel.value || sel.value === t.assignee) { toast('바뀐 담당이 없습니다'); return; }
    btn.disabled = true;
    try { await sendOps('assign', { topic: t.id, agent: sel.value, note: '' }, `주제 담당 → ${person(sel.value).name}`); render(); openTopic(S.d.topics.find(x => x.id === t.id) || t); }
    catch (e) { toast(e.message); } finally { btn.disabled = false; }
  } }, icon('agents'), '담당 바꾸기');
  return h('div', { class: 'composer' }, h('div', { class: 'row' }, sel, btn),
    pend ? h('div', { class: 'hint' }, `담당 변경 반영 대기: ${person(pend.agent).full}`) : null);
}
function openDecisionNeeded(q) {
  const p = decisionParts(q, () => openDecisionNeeded(q));
  modalSplit('결정이 필요한 문제', p.main, p.side);
}
// 결정 화면 내용: 오른쪽 칸(내 차례)과 가운데 모달이 같이 쓴다
function decisionParts(q, redraw) {
  const ans = S.d.answers[q.id];
  const note = h('textarea', { placeholder: '선택지 말고 직접 적거나, 고른 선택지에 덧붙일 말 (선택)', rows: '3', 'aria-label': '결정 메모', 'data-draft': `decide:${q.id}` });
  const topic = topicById(q.task_id);
  const task = !topic && q.task_id ? S.d.tasks.find(t => t.id === q.task_id) : null;
  return {
    main: [
      h('div', { class: 'meta', style: { display: 'flex', gap: '8px', 'flex-wrap': 'wrap', 'align-items': 'center' } },
        h('span', { class: 'wait' }, av(q._author || 'claude', true), `${person(q._author || 'claude').full} 질문`),
        h('span', { class: 'when' }, `${fmtAbs(q.since)} · ${fmtRel(q.since)}`)),
      questionText(q.question),
      q.recommendation ? h('div', { class: 'callout' }, h('b', null, '권장 '), q.recommendation) : null,
      ans ? h('div', { class: 'callout' }, h('b', null, '내 결정: '), ans.choice || '(메모)', ans.note ? ' — ' + ans.note : '', ' ', ans.pending ? h('span', { class: 'st user_test' }, icon('clock'), '반영 대기') : h('span', { class: 'st done' }, icon('check'), '반영됨')) : null,
      (q.options || []).length ? [h('h4', null, '선택지 — 누르면 바로 결정됩니다'), optionList(q, o => decide(q, o, note.value.trim(), redraw))] : null,
      h('h4', null, '직접 적기'),
      h('div', { class: 'composer' }, note, h('div', { class: 'row' }, h('button', { class: 'btn primary', onclick: () => { if (!note.value.trim()) { note.focus(); return; } decide(q, '', note.value.trim(), redraw); } }, icon('send'), '메모로 결정 보내기'))),
      sendHint(),
    ],
    side: historyPanel(topic, task, `ask:${q.id}`),
  };
}
// AI 질문(주제 기록의 질문)을 가운데 모달로: 질문 본문 + 답 보내기 + 히스토리
function openQuestion(topic, n) {
  const p = questionParts(topic, n, () => openQuestion(topic, n));
  modalSplit('AI 질문', p.main, p.side);
}
function questionParts(topic, n, redraw) {
  const t = topicById(topic.id) || topic;
  const lastUser = Math.max(0, ...commentsFor({ kind: 'topic', id: t.id }).filter(c => c.by === 'user').map(c => toMs(c.ts) || 0));
  const answered = lastUser > (toMs(n.ts) || 0);
  const key = `mine-q:${t.id}:${n.ts}`;
  const acked = S.acks.has(key) || S.serverAcks?.has(key);
  return {
    main: [
      h('div', { class: 'meta', style: { display: 'flex', gap: '8px', 'flex-wrap': 'wrap', 'align-items': 'center' } },
        h('span', { class: 'wait' }, av(n.by, true), `${person(n.by).full} 질문`),
        h('span', { class: 'when' }, `${fmtAbs(n.ts)} · ${fmtRel(n.ts)}`)),
      questionText(n.body),
      answered ? h('div', { class: 'callout' }, h('span', { class: 'st done' }, icon('check'), '답함'), ' 이 질문 뒤에 아키텍트 답이 있습니다. 히스토리에서 확인하세요.')
        : acked ? h('div', { class: 'callout' }, h('span', { class: 'st done' }, icon('check'), '확인함'), ' 답 없이 확인 처리했습니다.') : null,
      thread({ kind: 'topic', id: t.id, title: t.title }, redraw,
        { compose: true, title: `${person(n.by).name}에게 답하기`, placeholder: '여기에 답을 적으면 질문한 AI에게 전달되고, 다음 동기화 때 그 답으로 이어서 진행합니다', to: n.by }),
      answered || acked ? null : h('div', { class: 'choice-row' },
        h('button', { class: 'btn', onclick: () => { ack(key); closeDrawer(); } }, icon('check'), '답 없이 확인함으로 처리')),
    ],
    side: historyPanel(t, null, `note:${n.ts}`),
  };
}
function topicById(id) { return id ? S.d.topics.find(t => t.id === id) || null : null; }

// ------------------------------------------------------------ 지금 단계 · 실행 이력 · 작업물 (주제가 어디서 멈췄는지 한눈에)
const runsFor = id => (S.data.runs || []).filter(r => r.topic === id);           // 최신이 앞
function isRunning(r) { return !!r && r.result === 'running' && Date.now() - toMs(r.started) < 30 * 60e3; }
const holdOf = id => (S.data.holds || []).find(x => x.topic === id && toMs(x.until) > Date.now());
const RUN_RESULT = { ok: '성공', partial: '일부 실패', fail: '실패', running: '실행 중', skipped: '건너뜀' };
function topicPhase(t) {
  const name = id => person(id).name;
  if (t.status === 'dropped') return { cls: 'neutral', icon: 'x', label: '삭제됨' };
  if (t.status === 'done') return { cls: 'done', icon: 'check', label: '완료' };
  if (t.status === 'parked') return { cls: 'neutral', icon: 'pause', label: '보류' };
  if (t.status === 'backlog') return { cls: 'neutral', icon: 'inbox', label: '미처리', next: '아키텍트 — 내 차례 → 착수 고르기에서 착수·담당 정하기' };
  const hold = holdOf(t.id);
  if (hold) return { cls: 'progress', icon: 'user', label: `대화 세션 작업 중 · ${name(hold.agent)}`, detail: `${hold.note || ''} (${fmtAbs(hold.until)}까지 자동 실행 멈춤)` };
  const run = runsFor(t.id)[0];
  if (isRunning(run)) return { cls: 'progress', icon: 'play', label: `실행 중 · ${name(run.agent)}`, detail: `${fmtRel(run.started)} 시작 · 이유: ${run.reason || '-'}` };
  const ask = (S.data.decisions_needed || []).find(q => q.task_id === t.id && !S.d.answers[q.id]);
  if (ask) return { cls: 'user_test', icon: 'scale', label: '아키텍트 답 대기', detail: ask.question, next: '아키텍트 — 내 차례에서 결정', ask };
  if (run && run.result === 'fail') return { cls: 'blocked', icon: 'alert', label: `실행 실패 · ${HEALTH[run.error_class] || '오류'}`,
    detail: `${run.fix || ''} (${fmtRel(run.ended || run.started)})`, next: run.needs_user ? `아키텍트 — ${run.fix || '확인 필요'}` : '자동으로 다시 시도' };
  const who = t.turn;
  const partial = run && run.result === 'partial' ? ` · 지난 실행 일부 실패: ${(run.failed || []).join('; ').slice(0, 160)}` : '';
  if (!t.assignee) return { cls: 'request', icon: 'topics', label: '배분 대기', next: `${name(who || 'dev-claude')} — 자동 배분` };
  if (t.handoff && t.handoff.to === t.assignee && who === t.assignee)
    return { cls: 'progress', icon: 'arrow', label: `인계받음 · ${name(who)}`, detail: `${name(t.handoff.from)} → ${name(t.handoff.to)}: ${t.handoff.reason || '-'}${partial}`, next: `${name(who)} — 이어서 처리` };
  if (who && who !== t.assignee) return { cls: 'validating', icon: 'eye', label: `교차 검토 대기 · ${name(who)}`, detail: partial.slice(3) || null, next: `${name(who)} — 진행 베이스 검토` };
  if (!t.plan) return { cls: 'request', icon: 'file', label: `진행 베이스 작성 · ${name(who)}`, detail: partial.slice(3) || null, next: `${name(who)} — 목표·범위·첫 단계 작성` };
  return { cls: 'progress', icon: 'play', label: `진행 중 · ${name(who)}`, detail: partial.slice(3) || null, next: `${name(who)} — 다음 동기화 때 이어서` };
}
function phaseLine(t, compact) {
  const p = topicPhase(t);
  return h('div', { class: `phase ${p.cls}${compact ? ' compact' : ''}` }, icon(p.icon),
    h('div', { class: 'phase-b' }, h('b', null, p.label),
      !compact && p.detail ? h('span', { class: 'clamp-2' }, p.detail) : null,
      !compact && p.next ? h('span', { class: 'phase-next' }, '다음: ', p.next) : null));
}
function runText(r) {
  const parts = [`${RUN_RESULT[r.result] || r.result}${r.kind === 'answer' ? ' (아키텍트 답 반영)' : ''}${r.mode === 'impl' ? ' · 작업 모드' : ''} · 이유: ${r.reason || '-'}`];
  if (r.summary) parts.push(r.summary);
  if ((r.actions || []).length) parts.push('적용: ' + r.actions.join(', '));
  if ((r.failed || []).length) parts.push('실패: ' + r.failed.join('; '));
  if (r.error) parts.push('원인: ' + r.error);
  if (r.fix) parts.push('조치: ' + r.fix);
  return parts.join('\n');
}
function workBox(t, open) {
  const w = t && t.work_id ? (S.data.works || {})[t.work_id] : null;
  if (!w) return null;
  const agents = Object.entries(w.agents || {});
  return h('details', { class: 'work-box', open: open ? true : null },
    h('summary', null, icon('file'), h('b', null, `작업물 ${w.id}`), h('span', { class: 'tag' }, w.state || '-'), h('span', { class: 'hint' }, `파일 ${w.file_count}개 · 담당 ${person(w.owner).name}`)),
    h('div', { class: 'work-b' },
      h('dl', { class: 'fields' }, h('dt', null, '제목'), h('dd', null, w.title), h('dt', null, '아키텍트 승인'), h('dd', null, w.approval || '없음'),
        h('dt', null, '참여'), h('dd', null, agents.map(([a, x]) => `${person(a).name}(파일 ${x.files} · 메모 ${x.notes_count})`).join(', ') || '-')),
      (w.files || []).length ? h('ul', { class: 'work-files' }, w.files.slice(0, 14).map(f => h('li', { class: 'mono' }, f.path, h('span', { class: 'hint' }, ` ${Math.max(1, Math.round(f.size / 1024))}KB`))),
        w.files.length > 14 ? h('li', { class: 'hint' }, `… 외 ${w.file_count - 14}개`) : null) : null,
      agents.filter(([, x]) => x.notes_tail).map(([a, x]) => h('div', { class: 'work-note' }, h('b', null, `${person(a).name} 최근 메모`, x.last_note_at ? ` · ${fmtAbs(x.last_note_at)}` : ''), longText(x.notes_tail))),
      h('a', { class: 'btn sm', href: w.url, target: '_blank', rel: 'noopener noreferrer' }, icon('link'), 'GitHub에서 열기 (real-work)')));
}

// ------------------------------------------------------------ 히스토리 (모달 오른쪽: 이 주제에서 지금까지 있었던 일)
const HIST_KIND = { ...NOTE_KIND, created: '등록', reply: '대화', ask: '결정 요청', decide: '결정', message: '메시지', run: '자동 실행' };
function historyEvents(topic, task) {
  const ev = [], seen = new Set();
  const push = e => {
    const body = String(e.body || '').trim();
    if (!body) return;
    const sig = `${e.by}|${body.slice(0, 120)}`;
    if (seen.has(sig)) return;   // 결정 요청이 질문 메모로도 남는 경우 한 번만 보인다
    seen.add(sig); ev.push({ ...e, body });
  };
  if (topic) {
    push({ key: 'created', ts: topic.created_at, by: 'user', kind: 'created', body: topic.body || topic.title });
    for (const n of topic.notes || []) push({ key: `note:${n.ts}`, ts: n.ts, by: n.by, kind: n.kind || 'memo', body: n.body });
    for (const c of commentsFor({ kind: 'topic', id: topic.id })) push({ ts: c.ts, by: c.by, to: c.to, kind: 'reply', body: c.body, pending: c.pending });
  }
  const taskId = task?.id || topic?.linked_task_id;
  if (taskId) {
    for (const c of commentsFor({ kind: 'task', id: taskId })) push({ ts: c.ts, by: c.by, to: c.to, kind: 'reply', body: c.body, pending: c.pending });
    for (const m of S.data.messages.filter(m => m.task_id === taskId).slice(0, 30)) push({ ts: m.ts, by: m.sender, to: m.recipient, kind: 'message', body: m.title, msg: m });
  }
  if (topic) for (const r of runsFor(topic.id)) {
    if (r.result === 'running' && !isRunning(r)) continue;
    push({ key: `run:${r.id}`, ts: r.ended || r.started, by: r.agent, kind: 'run', body: runText(r), cls: r.result });
  }
  const ids = new Set([topic?.id, taskId].filter(Boolean));
  for (const q of S.data.decisions_needed || []) {
    if (!ids.has(q.task_id)) continue;
    push({ key: `ask:${q.id}`, ts: q.since, by: q._author || 'claude', kind: 'ask', body: q.question });
    const a = S.d.answers[q.id];
    if (a) push({ ts: a.ts || q.since, by: 'user', kind: 'decide', body: [a.choice, a.note].filter(Boolean).join(' — ') || '(메모)', pending: a.pending });
  }
  return ev.sort((a, b) => (toMs(a.ts) || 0) - (toMs(b.ts) || 0));
}
function historyPanel(topic, task, focusKey) {
  const ev = historyEvents(topic, task);
  const plan = topic?.plan || {};
  const planRows = [['goal', '목표'], ['scope', '범위'], ['first_steps', '첫 단계'], ['risks', '위험·확인'], ['done_when', '완료 기준']]
    .filter(([k]) => plan[k] && (!Array.isArray(plan[k]) || plan[k].length));
  const head = topic ? [
    h('div', { style: { display: 'flex', gap: '6px', 'flex-wrap': 'wrap', 'align-items': 'center' } }, topicChip(topic.status), priChip(topic.priority), topic.kind ? h('span', { class: 'tag' }, topic.kind) : null, h('span', { class: 'tag mono' }, topic.id)),
    h('div', { class: 'hist-title' }, topic.title),
    h('dl', { class: 'fields' }, h('dt', null, '담당'), h('dd', null, topic.assignee ? person(topic.assignee).full : '미배정'),
      h('dt', null, '지금 차례'), h('dd', null, topic.turn ? person(topic.turn).full : '—'),
      topic.dispatch_reason ? [h('dt', null, topic.assign_by === 'user' ? '담당 지정' : topic.assign_by === 'handoff' ? '인계' : '배분 근거'), h('dd', null, topic.dispatch_reason)] : null),
    phaseLine(topic),
    workBox(topic),
    planRows.length ? h('details', { class: 'hist-plan' }, h('summary', null, `진행 베이스 · ${person(topic.plan_by).name}`),
      h('div', { class: 'plan' }, planRows.map(([k, l]) => h('div', null, h('h4', null, l), Array.isArray(plan[k]) ? h('ul', null, plan[k].map(x => h('li', null, x))) : h('div', null, plan[k]))))) : null,
    h('button', { class: 'btn sm', onclick: () => openTopic(topic) }, icon('topics'), '주제 전체 보기'),
  ] : task ? [
    h('div', { style: { display: 'flex', gap: '6px', 'flex-wrap': 'wrap' } }, priChip(task.priority), stChip(task.stage), h('span', { class: 'tag mono' }, task.id)),
    h('div', { class: 'hist-title' }, task.title),
    task.summary ? h('p', { class: 'muted', style: { margin: 0, 'font-size': '13px' } }, task.summary) : null,
    h('button', { class: 'btn sm', onclick: () => openTask(task) }, icon('tasks'), '작업 전체 보기'),
  ] : [h('div', { class: 'hint' }, '연결된 주제·작업이 없어 히스토리가 없습니다.')];
  const LIMIT = 12;
  const list = h('ol', { class: 'hist' });
  const row = e => h('li', { class: `hist-item k-${e.kind}${e.cls ? ' r-' + e.cls : ''}${e.by === 'user' ? ' me' : ''}${e.key && e.key === focusKey ? ' focus' : ''}` },
    h('span', { class: 'hist-dot' }, av(e.by, true)),
    h('div', { class: 'hist-body' },
      h('div', { class: 'h' }, h('b', null, person(e.by).name), e.to ? h('span', null, '→ ' + person(e.to).name) : null,
        h('span', { class: 'tag' }, HIST_KIND[e.kind] || e.kind), e.key && e.key === focusKey ? h('span', { class: 'st user_test' }, '지금 보는 항목') : null,
        e.pending ? h('span', { class: 'st user_test' }, icon('clock'), '반영 대기') : null,
        h('span', { class: 'when', title: fmtAbs(e.ts) }, fmtAbs(e.ts))),
      e.msg ? h('button', { class: 'linkish', onclick: () => openMessage(e.msg) }, e.body) : longText(e.body)));
  const fill = all => { list.replaceChildren(...(all ? ev : ev.slice(-LIMIT)).map(row)); };
  // 지금 보는 항목이 접힌 앞부분에 있으면 처음부터 전부 보여준다
  const focusAt = ev.findIndex(e => e.key && e.key === focusKey);
  const showAll = ev.length <= LIMIT || (focusAt >= 0 && focusAt < ev.length - LIMIT);
  fill(showAll);
  const more = showAll ? null : h('button', { class: 'btn sm', onclick: () => { fill(true); more.remove(); } }, `이전 기록 ${ev.length - LIMIT}건 더 보기`);
  // 넓은 화면에서는 히스토리 칸만 지금 항목으로 스크롤(좁은 화면은 질문부터 읽도록 그대로)
  if (matchMedia('(min-width: 881px)').matches) setTimeout(() => {
    const f = list.querySelector('.focus'), side = list.closest('.ms-side');
    if (f && side) side.scrollTop += f.getBoundingClientRect().top - side.getBoundingClientRect().top - side.clientHeight / 2 + f.offsetHeight / 2;
  }, 260);
  return [
    h('div', { class: 'hist-head' }, head),
    h('h4', null, `히스토리 ${ev.length}건 · 오래된 것부터`),
    more,
    ev.length ? list : empty('아직 기록이 없습니다.'),
  ];
}
// 긴 기록은 접어두고 "펼치기"로 본다
function longText(s) {
  const p = h('p', { class: 'hist-text' }, s);
  if (s.length < 360 && (s.match(/\n/g) || []).length < 6) return p;
  p.classList.add('folded');
  const b = h('button', { class: 'linkish', onclick: () => { const f = p.classList.toggle('folded'); b.textContent = f ? '펼치기' : '접기'; } }, '펼치기');
  return [p, b];
}
// AI 질문은 "(1) … (2) …"처럼 한 줄로 오는 경우가 많아 번호마다 줄을 나눠 읽기 쉽게 한다
function questionText(s) {
  const text = String(s || '').replace(/\s*\((\d{1,2})\)\s*/g, '\n\n($1) ').replace(/^\s+/, '');
  return h('div', { class: 'q-text' }, text);
}
function optionList(q, pick) {
  return h('div', { class: 'opt-list' }, (q.options || []).map(o => h('button', { class: 'opt', onclick: () => pick(o) }, o)));
}

function tokenCard() {
  const has = !!store.get('ghtoken'), repo = S.data.meta.repo || '';
  const input = h('input', { type: 'password', placeholder: 'github_pat_… 붙여넣기', autocomplete: 'off', spellcheck: 'false', 'aria-label': 'GitHub 토큰' });
  const status = h('div', { class: 'hint', role: 'status', 'aria-live': 'polite' });
  const save = h('button', { class: 'btn primary', onclick: async () => {
    const v = input.value.trim();
    if (!/^(github_pat_|ghp_)[A-Za-z0-9_]{20,}$/.test(v)) { status.textContent = '토큰 형식이 아닙니다. github_pat_로 시작하는 값을 붙여넣으세요.'; return; }
    save.disabled = true; status.textContent = 'GitHub에 확인하는 중…';
    try {
      const r = await fetch(`https://api.github.com/repos/${repo}/issues?per_page=1`, { headers: { Authorization: `Bearer ${v}`, Accept: 'application/vnd.github+json' } });
      if (!r.ok) { status.textContent = `GitHub가 거절했습니다 (${r.status}). 저장소와 Issues 권한을 확인하세요.`; return; }
      await tokenSet(v); input.value = ''; toast('토큰을 저장했습니다. 이제 버튼 하나로 보내집니다.'); render();
    } catch (e) { status.textContent = '확인 실패: ' + e.message; } finally { save.disabled = false; }
  } }, '확인 후 저장');
  return card('버튼 하나로 보내기', { right: has ? h('span', { class: 'st done' }, icon('check'), '연결됨') : h('span', { class: 'st neutral' }, '미연결') },
    h('div', { class: 'composer' },
      h('div', { class: 'hint' }, 'GitHub 토큰을 한 번 연결하면 주제·답·일괄 확인이 GitHub 창 없이 바로 전송됩니다. 토큰은 대시보드 키로 암호화해 이 기기에만 저장합니다.'),
      h('ol', { class: 'hint steps' },
        h('li', null, '아래 버튼으로 GitHub 토큰 만들기 페이지를 엽니다 (Fine-grained token).'),
        h('li', null, `Repository access → Only select repositories → ${repo || '이 저장소'}`),
        h('li', null, 'Permissions → Repository permissions → Issues: Read and write (다른 권한은 주지 않음)'),
        h('li', null, '만료 기간을 정하고 Generate → 나온 토큰을 아래에 붙여넣기')),
      h('a', { class: 'btn', href: 'https://github.com/settings/personal-access-tokens/new', target: '_blank', rel: 'noopener noreferrer' }, icon('link'), '토큰 만들기 페이지 열기'),
      h('div', { class: 'row' }, input, save),
      has ? h('button', { class: 'btn', onclick: () => { store.del('ghtoken'); toast('이 기기에서 토큰을 지웠습니다'); render(); } }, icon('x'), '이 기기에서 토큰 지우기') : null,
      status));
}

// ------------------------------------------------------------ 서랍(상세)
function drawer(eyebrow, ...content) { return openPanel('drawer', eyebrow, content); }
// 가운데 모달: 결정·승인처럼 읽고 고르는 화면. 내용이 길어도 잘리지 않고 안에서 스크롤된다
function modal(eyebrow, ...content) { return openPanel('drawer modal', eyebrow, content); }
// 넓은 가운데 모달: 왼쪽은 읽고 답하는 곳, 오른쪽은 히스토리. 두 칸이 따로 스크롤된다(좁은 화면은 위아래로)
function modalSplit(eyebrow, main, side) {
  return openPanel('drawer modal split', eyebrow, [h('div', { class: 'ms-main' }, main), h('div', { class: 'ms-side' }, side)]);
}
function openPanel(cls, eyebrow, content) {
  closeDrawer(true);
  const scrim = h('div', { class: 'scrim', onclick: () => closeDrawer() });
  const panel = h('aside', { class: cls, role: 'dialog', 'aria-modal': 'true', 'aria-label': eyebrow },
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
    thread({ kind: 'task', id: t.id, title: t.title }, () => openTaskById(t.id), { placeholder: '이 작업에 대한 답·지시를 적으면 담당에게 전달됩니다', to: t.owner === 'astra' ? 'astra' : 'claude' }),
    h('h4', null, '단계 바꾸기'),
    h('div', { style: { display: 'flex', gap: '6px', 'flex-wrap': 'wrap' } }, STAGES.filter(s => s.id !== t.stage).map(s =>
      h('button', { class: 'btn', onclick: () => setStages([t.id], s.id, () => openTaskById(t.id)) }, h('span', { style: { color: `var(--st-${s.id})`, display: 'grid' } }, icon(s.icon)), s.label))),
    t.fields && Object.keys(t.fields).length ? [h('h4', null, 'tasks.json 원본 필드'), fieldList(t.fields)] : null);
}
function openMessage(m) { drawer('메시지', messageDetail(m, () => openMessage(m))); }
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
  if (S.editTopic && S.editTopic !== t.id) S.editTopic = null;
  const plan = t.plan || {};
  const planRows = [['goal', '목표'], ['scope', '범위'], ['inputs', '필요한 입력'], ['first_steps', '첫 단계'], ['risks', '위험·확인'], ['done_when', '완료 기준']]
    .filter(([k]) => plan[k] && (!Array.isArray(plan[k]) || plan[k].length));
  drawer('주제',
    h('div', { style: { display: 'flex', gap: '6px', 'flex-wrap': 'wrap' } }, topicChip(t.status), priChip(t.priority), t.kind ? h('span', { class: 'tag' }, t.kind) : null,
      h('span', { class: 'tag' }, t.id), t.linked_task_id ? h('button', { class: 'tag', style: { cursor: 'pointer' }, onclick: () => openTaskById(t.linked_task_id) }, '작업 ' + t.linked_task_id) : null,
      S.editTopic === t.id ? null : topicTools(t, () => { const x = S.d.topics.find(y => y.id === t.id); x ? openTopic(x) : closeDrawer(); })),
    S.editTopic === t.id ? topicEditForm(t, () => { S.editTopic = null; openTopic(S.d.topics.find(y => y.id === t.id) || t); }) : null,
    h('h3', null, t.title),
    (t.conflict || []).length ? h('div', { class: 'callout warn' }, h('b', null, '중복 착수: '), `담당은 ${person(t.assignee).full}인데 ${t.conflict.map(c => person(c).full).join(', ')}도 착수했습니다. 한쪽을 멈추거나 담당을 바꿔주세요.`) : null,
    phaseLine(t),
    t.dispatch_reason ? h('div', { class: 'reason' }, h('b', null, t.assign_by === 'user' ? '담당 지정: ' : t.assign_by === 'handoff' ? '인계: ' : '배분 근거: '), t.dispatch_reason) : null,
    workBox(t, true),
    runsFor(t.id).length ? [h('h4', null, `자동 실행 이력 ${runsFor(t.id).length}`), h('div', { class: 'run-list' }, runsFor(t.id).slice(0, 8).map(runRow))] : null,
    t.status === 'backlog' ? activateControl(t) : null,
    assignControl(t),
    h('dl', { class: 'fields' }, h('dt', null, '담당'), h('dd', null, t.assignee ? person(t.assignee).full : '미배정'),
      h('dt', null, '지금 차례'), h('dd', null, t.turn ? `${person(t.turn).full} · ${t.status === 'new' ? '분배' : !t.plan ? '진행 베이스 작성' : t.turn !== t.assignee ? '교차 검토' : '진행'}` : '—'),
      h('dt', null, '선호'), h('dd', null, ({ auto: '자동 분배', claude: 'Claude 우선', astra: 'Astra 우선' })[t.prefer] || '—'),
      h('dt', null, '받은 시각'), h('dd', null, fmtAbs(t.created_at)), h('dt', null, '경로'), h('dd', null, t.source || '—')),
    t.body ? [h('h4', null, '원래 메모'), h('pre', { class: 'pre' }, t.body)] : null,
    planRows.length ? [h('h4', null, `진행 베이스 · ${person(t.plan_by).name}`), h('div', { class: 'plan callout' }, planRows.map(([k, l]) => h('div', null, h('h4', null, l),
      Array.isArray(plan[k]) ? h('ul', null, plan[k].map(x => h('li', null, x))) : h('div', null, plan[k]))))] : null,
    [h('h4', null, `메모·검토 ${(t.notes || []).length}`), (t.notes || []).length ? h('div', { class: 'note-thread' }, t.notes.map(n => h('div', { class: 'note' }, av(n.by, false),
      h('div', { class: 'bubble' }, h('div', { class: 'h' }, h('b', null, person(n.by).name), h('span', { class: 'tag' }, NOTE_KIND[n.kind] || n.kind || '메모'), h('span', null, fmtAbs(n.ts))), h('p', null, n.body)))))
      : empty('아직 메모가 없습니다. Claude가 분배하면 여기에 기록됩니다.')],
    thread({ kind: 'topic', id: t.id, title: t.title }, () => openTopic(S.d.topics.find(x => x.id === t.id) || t), { placeholder: '이 주제에 덧붙일 말이나 답을 적으세요', to: t.assignee === 'astra' ? 'astra' : 'claude' }));
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
// 앱 설치(PWA) 지원: 서비스 워커 등록과 설치 버튼
if ('serviceWorker' in navigator && window.isSecureContext) navigator.serviceWorker.register('sw.js').catch(() => {});
window.addEventListener('beforeinstallprompt', e => { e.preventDefault(); S.installPrompt = e; if (S.data) render(); });
window.addEventListener('appinstalled', () => { S.installPrompt = null; toast('앱으로 설치했습니다'); if (S.data) render(); });
async function installApp() {
  if (S.installPrompt) { S.installPrompt.prompt(); await S.installPrompt.userChoice; S.installPrompt = null; render(); return; }
  toast(/iPhone|iPad/.test(navigator.userAgent) ? 'Safari 공유 버튼 → "홈 화면에 추가"를 누르세요' : 'Chrome 메뉴(⋮) → "앱 설치" 또는 "전송, 저장, 공유 → 앱으로 설치"');
}
boot();
