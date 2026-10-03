'use strict';
/* REAL 작업실 대시보드 — 브라우저에서 복호화 후 렌더링. 외부 요청 없음. */

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
  // data-focus: 초안으로 저장하지는 않지만 다시 그려도 입력 중인 자리를 지킬 칸(검색칸 등)
  const k = a && root.contains(a) && a.dataset ? a.dataset.draft || a.dataset.focus : null;
  return k ? { key: k, s: a.selectionStart, e: a.selectionEnd } : null;
}
function restoreFocus(root, f) {
  if (!f) return;
  const el = [...root.querySelectorAll('[data-draft],[data-focus]')].find(x => (x.dataset.draft || x.dataset.focus) === f.key);
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
  claude: { name: 'Claude', full: 'Claude', role: '개발 · 구현·검증', ini: 'C' },
  astra: { name: 'Astra', full: 'Astra (Codex)', role: '검토 · 검증', ini: 'A' },
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
    return { name: `${a.pc_label} ${short}`, full: `${a.pc_label} · ${a.label || a.id}`, role: a.id === 'server-astra' ? '최종 사령탑 · 분배·검수·배포' : '실행 작업자',
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
  const lastRun = (S.data?.runs || []).find(r => r.agent === a?.id);
  const seen = [a?.last_seen, a?.pc_synced, lastRun && (lastRun.ended || lastRun.started)].filter(Boolean).sort((x, y) => toMs(y) - toMs(x))[0];
  const stale = S.data?.meta?.routing?.stale_minutes || 120;
  if (!seen) return { cls: 'neutral', label: '신호 없음', icon: 'clock' };
  const m = (Date.now() - toMs(seen)) / 6e4;
  if (m > stale) return { cls: 'blocked', label: '끊김', icon: 'alert' };
  const lk = lockOf(a.id);
  if (lk && lk.mode === 'all') return { cls: 'neutral', label: '자동 실행 멈춤', icon: 'pause' };
  const hl = a.health;
  if (hl && hl.state && hl.state !== 'ok' && hl.needs_user) return { cls: 'blocked', label: HEALTH[hl.state] || '실행 오류', icon: 'alert' };
  if ((S.data?.runs || []).some(r => r.agent === a.id && isRunning(r))) return { cls: 'progress', label: '자동 실행 중', icon: 'play' };
  if (a.current) return { cls: 'done', label: '작업 중', icon: 'play' };
  const q = a.queue;
  if (q && (q.runnable || q.answers)) return { cls: 'progress', label: '곧 실행', icon: 'clock' };
  if (q && q.total) return { cls: 'neutral', label: q.waiting_answer ? '답 기다림' : '변화 기다림', icon: 'clock' };
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
  { id: 'review_user', label: '아키텍트 관문', cls: 'user_test', icon: 'scale' },
  { id: 'done', label: '완료', cls: 'done', icon: 'done', hidden: true },  // 완료는 '완료' 메뉴에서(보드에서 뺌)
  { id: 'parked', label: '보류', cls: 'neutral', icon: 'pause' },
  { id: 'dropped', label: '삭제됨', cls: 'blocked', icon: 'x', hidden: true },
];
const TOPIC = Object.fromEntries(TOPIC_STATES.map(s => [s.id, s]));
function topicChip(state) {
  const s = TOPIC[state] || TOPIC.new;
  return h('span', { class: `st ${s.cls}` }, icon(s.icon), s.label);
}
const NOTE_KIND = { triage: '분배', memo: '메모', review: '검토', plan: '진행 베이스', question: '질문', answer: '답변', status: '상태', claim: '착수', handoff: '인계', work: '작업물', request: '요청', reply: '요청 답' };
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
  view: 'progress', q: '',
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
  const body = `REAL 작업실 ${kind === 'topic' ? '주제' : '요청'} (암호화됨 · 대시보드 비밀번호로만 열립니다)\n\n아래 줄을 수정하지 마세요.\n\n${blob}\n`;
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
const UNDO_MS = 10000;
const outbox = { all() { return store.get('outbox', []) || []; }, set(l) { store.set('outbox', l); } };
// 10초 뒤 보내기는 토큰 API로만 보낸다(사용자 동작 없이 GitHub 창을 열면 막히므로). 실패하면 대기열에 남겨 1분 뒤 다시,
// 세 번 실패하면 '보내지 못한 결정' 창을 띄워 직접 눌러 GitHub 창으로 보내게 한다(결정이 조용히 사라지지 않게)
async function sendApi(obj) {
  const repo = S.data.meta.repo, token = await tokenGet();
  if (!repo || !token) throw new Error('토큰 없음');
  const blob = await sealTopic(obj);
  const r = await fetch(`https://api.github.com/repos/${repo}/issues`, {
    method: 'POST', headers: { Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json', 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: `[ops] ${obj.id}`, body: `REAL 작업실 요청 (암호화됨 · 대시보드 비밀번호로만 열립니다)\n\n아래 줄을 수정하지 마세요.\n\n${blob}\n` }) });
  if (!r.ok) throw new Error(`GitHub ${r.status}`);
}
async function flushOutbox() {
  if (S._flushing || !S.data) return;
  S._flushing = true;
  try {
    const answered = new Map((S.data.decisions_answered || []).map(a => [a.id, a]));
    for (const it of outbox.all().filter(x => x.due <= Date.now() && !x.manual)) {
      const a = it.action, prev = a.type === 'decide' ? answered.get(a.decision_id) : null;
      if (prev && toMs(prev.ts) > toMs(a.created_at)) {  // 다른 기기에서 더 나중에 답했다 — 늦게 보내 덮어쓰지 않는다
        outbox.set(outbox.all().filter(x => x.action.id !== a.id)); pending.remove(a.id); continue;
      }
      try {
        await sendApi(a);
        outbox.set(outbox.all().filter(x => x.action.id !== a.id));
        pending.all().filter(p => p.id === a.id).forEach(p => { pending.remove(p.id); pending.add({ ...p, via: 'api' }); });
        toast('보냈습니다 · PC 동기화 때 반영됩니다');
      } catch (e) {
        const tries = (it.tries || 0) + 1;
        outbox.set(outbox.all().map(x => x.action.id === a.id ? { ...x, tries, due: Date.now() + 60000, manual: tries >= 3 } : x));
        if (tries >= 3) showUnsent(); else toast(`보내기 실패(${e.message}) — 1분 뒤 다시 보냅니다`);
      }
    }
  } finally { S._flushing = false; }
}
function showUnsent() {
  const list = outbox.all().filter(x => x.manual);
  if (!list.length) return;
  drawer('보내지 못한 결정', h('p', null, `바로 보내기가 ${list.length}건 실패했습니다. 아래 버튼을 눌러 GitHub 창에서 "Submit new issue"를 눌러 주세요.`),
    list.map(x => h('div', { class: 'row', style: { 'margin-top': '8px' } }, h('span', { class: 'grow' }, (pending.all().find(p => p.id === x.action.id) || {}).summary || x.action.id),
      h('button', { class: 'btn primary', onclick: async () => {
        outbox.set(outbox.all().filter(y => y.action.id !== x.action.id));
        const res = await sendBlob('ops', x.action); afterSend(res);
        pending.all().filter(p => p.id === x.action.id).forEach(p => { pending.remove(p.id); pending.add({ ...p, via: res.via }); });
      } }, icon('send'), 'GitHub에서 보내기'))));
}
function cancelQueued(id, quiet) {
  const it = outbox.all().find(x => x.action.id === id);
  if (!it) { if (!quiet) toast('이미 보냈습니다'); return; }
  outbox.set(outbox.all().filter(x => x.action.id !== id));
  pending.remove(id);
  // ★4 통과를 취소하면 바로 띄워 둔 ★5(이 기기 임시본)도 지운다
  const a = it.action;
  if (a.type === 'decide' && /^G4-/.test(a.decision_id || '')) {
    const g5 = 'G5-' + a.decision_id.slice(3);
    store.set('localGates', (store.get('localGates') || []).filter(x => x.id !== g5));
    S.data.decisions_needed = (S.data.decisions_needed || []).filter(x => !(x.id === g5 && x._local));
  }
  S.d = derive(S.data); render();
  document.querySelector(`.undo-bar[data-id="${id}"]`)?.remove();
  if (!quiet) toast('취소했습니다 — 보내지 않았습니다');
}
// 취소 띠는 결정마다 하나씩(연달아 결정해도 앞 결정을 취소할 수 있게)
function undoBar(id, summary) {
  let stack = document.querySelector('.undo-stack');
  if (!stack) { stack = h('div', { class: 'undo-stack' }); document.body.append(stack); }
  const bar = h('div', { class: 'undo-bar', role: 'status', 'data-id': id }, h('span', null, `${summary} · 10초 뒤 보냅니다`), h('button', { class: 'btn sm', onclick: () => cancelQueued(id) }, '취소'));
  stack.append(bar);
  setTimeout(() => bar.remove(), UNDO_MS);
}
async function sendOps(type, fields, summary, opts = {}) {
  const action = { id: newId('A'), type, created_at: new Date().toISOString(), ...fields };
  if (opts.undo && await tokenGet()) {  // 결정은 10초 뒤에 보낸다 — 그 사이 취소할 수 있게(보고서 4번)
    pending.add({ ...fields, id: action.id, type, created_at: action.created_at, summary, via: 'queued' });
    outbox.set([...outbox.all(), { action, due: Date.now() + UNDO_MS }]);
    S.d = derive(S.data);
    undoBar(action.id, summary);
    setTimeout(flushOutbox, UNDO_MS + 300);
    return { via: 'queued' };
  }
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
  removePanels(); screenHistory.clear(); screenId = null;
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
  const pendAssign = {}, pendResolve = {};
  // 같은 주제는 마지막 담당 요청이 이긴다. 해결 요청이 아직 반영 안 됐어도 6시간이 지나면 경고를 다시 보인다(GitHub 창에서 제출 안 한 경우)
  for (const p of pend.filter(p => p.type === 'assign').sort((a, b) => toMs(a.created_at) - toMs(b.created_at))) {
    pendAssign[p.topic] = p.agent;
    if (((p.drop || []).length || p.confirm) && hoursSince(p.created_at) < 6) pendResolve[p.topic] = p; else delete pendResolve[p.topic];
  }
  const pendActivate = new Set(pend.filter(p => p.type === 'activate').map(p => p.topic));
  const pendResume = new Set(pend.filter(p => p.type === 'topic-resume').map(p => p.topic));
  // 주제 수정·삭제·되살리기도 PC가 처리하기 전에 화면에 먼저 반영한다(마지막 요청이 이긴다)
  const pendEdit = {}, pendDrop = new Map();
  for (const p of pend.filter(p => p.type === 'topic-edit')) pendEdit[p.topic] = p;
  for (const p of pend.filter(p => p.type === 'topic-drop')) for (const id of p.topics || []) pendDrop.set(id, !p.restore);
  const topics = (data.topics || []).map(t => {
    let x = { ...t, _age: hoursSince(t.created_at),
      ...(t.status === 'backlog' && pendActivate.has(t.id) ? { status: 'new' } : {}),
      ...(pendAssign[t.id] && pendAssign[t.id] !== t.assignee ? { assignee: pendAssign[t.id], assign_by: 'user', dispatch_reason: '사용자 지정(반영 대기)', status: t.status === 'new' ? 'triage' : t.status } : {}) };
    if (pendResume.has(t.id) && x.status === 'parked') {  // 관문에서 보류했으면 그 관문 대기로, 진행 중 보류면 진행 중으로 돌아간다
      const gp = (x.gate_history || []).at(-1);
      x = { ...x, status: gp && gp.act === 'park' && !gp.resumed_at ? 'review_user' : 'active', _pendingResume: true };
    }
    if (pendResolve[t.id] && (x.conflict || []).length) x = { ...x, conflict: [], _pendingResolve: pendResolve[t.id] };
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
  // ★ 관문이 하루 넘게 답을 기다리면 놓친 항목으로(대기 목록이 바뀌면 확인했어도 다시 올라온다)
  const lateGates = (data.decisions_needed || []).filter(q => q.kind === 'gate' && !answers[q.id] && (q.options || []).length && hoursSince(q.since) >= GATE_LATE_H)
    .sort((a, b) => toMs(a.since) - toMs(b.since));
  if (lateGates.length) missed.push({ key: `gate-late:${lateGates.map(q => q.id).sort().join(',')}`, level: 'warn', icon: 'scale',
    title: `★ 관문 ${lateGates.length}건이 ${GATE_LATE_H}시간 넘게 대기`, sub: `가장 오래: ${(topics.find(t => t.id === lateGates[0].task_id) || {}).title || lateGates[0].task_id} · ${waitText(lateGates[0].since)}`,
    go: () => { S.f.mine = 'gate'; S.mineSel = null; go('mine'); } });
  // 실행기 멈춤: AI 차례인데 실행기가 같은 사유로 계속 건너뛰거나, 처리한 뒤 한 시간 넘게 변화가 없는 주제(2026-10-03)
  for (const a of data.agents || []) for (const s of (a.queue || {}).stalled || []) {
    const t = topics.find(x => x.id === s.topic);
    if (t) missed.push({ key: `stall:${s.topic}:${s.since || ''}`, level: 'bad', icon: 'alert', title: `실행기 멈춤: ${t.title}`,
      sub: `${person(a.id).name} · ${s.reason || '원인 미상'}`, go: () => openTopic(t) });
  }
  // 보내지 못한 결정(바로 보내기 세 번 실패): 직접 보낼 때까지 놓친 항목에 남긴다
  const unsent = outbox.all().filter(x => x.manual);
  if (unsent.length) missed.push({ key: `unsent:${unsent.map(x => x.action.id).join(',')}`, level: 'bad', icon: 'send', title: `보내지 못한 결정 ${unsent.length}건`,
    sub: '바로 보내기가 실패했습니다 — 눌러서 GitHub 창으로 보내기', go: () => showUnsent() });
  // 헛도는 중: 같은 주제가 진척 없이 3번 넘게 돌았다(멈추지 않고 간격을 두고 계속 깨움) — 결정이 아니라 알림. 진척이 생기면 실행기가 목록에서 빼 사라진다.
  // 번호는 헛돎이 시작된 시각으로 고정(같은 헛돎이 이어지는 동안 새 알림으로 다시 뜨지 않게, 2026-10-03 아키텍트 결정)
  for (const a of data.agents || []) for (const s of (a.queue || {}).idle || []) {
    const t = topics.find(x => x.id === s.topic);
    if (t) missed.push({ key: `idle:${s.topic}:${s.since || ''}`, level: 'warn', icon: 'clock', title: `헛도는 중: ${t.title}`,
      sub: `${person(a.id).name} ${s.runs}회 연속 진척 없음${s.last ? ` · 마지막: ${s.last}` : ''} · ${s.every >= 120 ? '2시간' : '30분'}마다 계속 다시 깨우는 중`, go: () => openTopic(t) });
  }
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
  { id: 'mine', label: '결재함', icon: 'user' },
  { id: 'progress', label: '진행 현황', icon: 'topics' },
  { id: 'agents', label: '작업자', icon: 'agents' },  // 누가 무엇을 하는지(아키텍트 10-03: 관리 메뉴에 숨기지 말 것)
  { id: 'deploy', label: '배포', icon: 'calendar' },
  { id: 'history', label: '기록', icon: 'done' },
];
const ADMIN_NAV = [
  { id: 'sources', label: '연결 상태', icon: 'sources' },
];
const DETAIL_NAV = [
  { id: 'overview', label: '전체 요약' }, { id: 'topics', label: '이전 주제 보드' },
  { id: 'tasks', label: '이전 업무표' }, { id: 'done', label: '완료 기록' },
  { id: 'parked', label: '보류 기록' }, { id: 'messages', label: '작업자 메시지' },
  { id: 'verify', label: '검증 기록' }, { id: 'brain', label: '통합 검색' },
];

// 새로 도착한 ★ 관문: 이 기기에서 아직 내 차례를 열어 보지 않은 관문을 위쪽 띠·알림으로 알린다
function checkNewGates() {
  const ids = gateQueue().map(x => x.q.id);
  const seen = store.get('seenGates');
  if (!Array.isArray(seen)) { store.set('seenGates', ids); store.set('newGates', []); return; }  // 처음 연 기기는 지금 것을 본 것으로
  const fresh = ids.filter(id => !seen.includes(id));
  const pending = [...new Set([...(store.get('newGates') || []), ...fresh])].filter(id => ids.includes(id));
  store.set('newGates', pending);
  store.set('seenGates', [...new Set([...seen.filter(id => ids.includes(id)), ...ids])]);
  if (fresh.length && 'Notification' in window && Notification.permission === 'granted') {
    const key = x => String(x.topic?.gate?.summary || '').split('\n').map(l => l.trim()).find(Boolean) || '';
    const names = gateQueue().filter(x => fresh.includes(x.q.id)).map(x => `${x.label} · ${x.topic ? x.topic.title : x.q.task_id}${key(x) ? ' — ' + key(x).slice(0, 80) : ''}`);
    try {
      const n = new Notification(`★ 관문 ${fresh.length}건 도착`, { body: names.slice(0, 4).join('\n') + (names.length > 4 ? `\n외 ${names.length - 4}건` : ''), icon: 'icon-192.png', tag: 'real-gates' });
      n.onclick = () => { window.focus(); S.f.mine = 'gate'; S.mineSel = `d:${fresh[0]}`; go('mine'); n.close(); };
    } catch { /* 알림을 못 띄우는 환경 */ }
  }
}
const newGates = () => (store.get('newGates') || []).filter(id => gateQueue().some(x => x.q.id === id));
function enterApp() {
  mergeLocalGates();
  S.d = derive(S.data);
  $('#lock').hidden = true;
  $('#app').hidden = false;
  readHash();
  checkNewGates();
  const deepTopic = new URLSearchParams(location.hash.split("?")[1] || "").get("topic");
  const compose = S._composeOnOpen; S._composeOnOpen = false;
  if (deepTopic || compose) history.replaceState(null, "", routeUrl(S.view));
  clearDraft('progress-search');  // 예전 판이 검색어를 초안으로 남겨 새로 고친 뒤 칸과 목록이 어긋나던 값 정리
  render();
  if (deepTopic && topicById(deepTopic)) openTopic(topicById(deepTopic));
  else if (compose) openComposer();
  flushOutbox();  // 지난번에 10초 안에 창을 닫아 못 보낸 결정이 있으면 마저 보낸다
  // 보고 있을 때는 1분마다, 창을 내려 두었을 때도 5분마다 확인한다(새 관문 알림이 늦지 않게)
  if (!S.timer) { let tick = 0; S.timer = setInterval(() => { tick++; flushOutbox(); if (!document.hidden || tick % 5 === 0) refresh(); }, 60 * 1000); }
}
// 새 화면 판 알아채기: 게시 서버가 시작 파일을 10분까지 캐시해서 열린 창이 예전 화면에 머무르는 문제(2026-10-03).
// 1분마다 시작 파일의 화면 파일 버전 표시를 캐시 없이 읽어, 바뀌었으면 안전할 때 스스로 새로 고친다
const myVer = () => ($('script[src*="app.js?v="]')?.getAttribute('src') || '').split('v=')[1] || '';
async function checkAppVersion() {
  try {
    const html = await (await fetch(`./index.html?r=${Date.now()}`, { cache: 'no-store' })).text();
    const live = (html.match(/app\.js\?v=([0-9a-zA-Z]+)/) || [])[1];
    if (!live || !myVer() || live === myVer()) return;
    const typing = document.activeElement?.matches?.('input, textarea, select');
    const busy = typing || document.querySelector('.drawer') || !store.get('key');
    if (!busy) { location.reload(); return; }
    if (!S.newVersion) { S.newVersion = live; S._keepScroll = true; render(); }
  } catch { /* 오프라인 등 */ }
}
async function refresh(manual) {
  checkAppVersion();
  try {
    const env = await fetchEnvelope();
    // 바뀐 게 없으면 다시 그리지 않는다(쓰던 글·스크롤이 흔들리지 않게)
    if (env.published_at === S.env?.published_at) { if (manual) toast('이미 최신입니다 · 게시 ' + fmtRel(env.published_at)); return; }
    if (env.salt !== S.env.salt) { S.env = env; toast('비밀번호가 바뀌었습니다. 다시 열어주세요.'); return lockNow(); }
    S.env = env; S.data = await openEnvelope(env, S.key); mergeLocalGates(); S.d = derive(S.data);
    checkNewGates();
    S._keepScroll = true; render(); toast('새 데이터를 반영했습니다');
  } catch (e) { if (manual) toast('갱신 실패: ' + e.message); }
}
// 메뉴·상세를 브라우저 방문 이력에 기록한다. 데이터/토큰은 history에 넣지 않는다.
// history.state = { realops: 화면 식별값, depth: 앱 안에서 몇 번째 화면인지(0 = 이 앱의 첫 화면) }
const screenHistory = new Map();
let screenId = null, restoringScreen = false, lastRestoredHref = null;
const screenKey = () => `${Date.now()}-${Math.random().toString(36).slice(2)}`;
let curDepth = 0, closingPanel = false;
const histDepth = () => (history.state?.realops ? Number(history.state.depth) || 0 : curDepth);
function pushScreen(url) { curDepth = histDepth() + 1; history.pushState({ realops: screenId, depth: curDepth }, '', url); }
function replaceScreen(url) { curDepth = histDepth(); history.replaceState({ realops: screenId, depth: curDepth }, '', url); }
function saveScreen() {
  if (!screenId) {
    screenId = history.state?.realops || screenKey();
    replaceScreen(location.href);
  }
  snapshotDrafts(document.body);
  const old = screenHistory.get(screenId) || {};
  const panel = document.querySelector('.drawer');
  screenHistory.set(screenId, { ...old, view: S.view, f: { ...S.f }, q: S.q, mineSel: S.mineSel,
    scroll: window.scrollY, inner: [...document.querySelectorAll('.mine-list,.mine-detail .ms-main,.mine-detail .ms-side,.msg-list,.reader')].map(e => e.scrollTop),
    panelScroll: panel?.querySelector('.drawer-b')?.scrollTop || 0 });
}
// 기록 메뉴 안의 화면(완료·보류·전체 요약)은 '기록' 한 화면에서 칩으로 오간다. 예전 주소(#/done 등)도 그대로 열린다
const RECORD_KINDS = [['done', '완료'], ['parked', '보류'], ['overview', '전체 요약'], ['restart', '재시작 전']];
const RECORD_ALIAS = { done: 'done', parked: 'parked', overview: 'overview' };
function routeUrl(view, topic) {
  const params = new URLSearchParams();
  if (view === 'brain' && S.q) params.set('q', S.q);
  if (view === 'history' && S.f.recordKind && S.f.recordKind !== 'done') params.set('k', S.f.recordKind);
  if (topic) params.set('topic', topic);
  const qs = params.toString();  // URLSearchParams.size는 iOS 16 이하에 없다
  return '#/' + view + (qs ? '?' + qs : '');
}
function readHash() {
  const [v, qs] = location.hash.replace(/^#\/?/, '').split('?');
  const p = new URLSearchParams(qs || '');
  if (RECORD_ALIAS[v]) { S.view = 'history'; S.f.recordKind = RECORD_ALIAS[v]; }
  else if ([...NAV,...ADMIN_NAV,...DETAIL_NAV].some(n => n.id === v)) S.view = v;
  if (S.view === 'history' && RECORD_KINDS.some(([k]) => k === p.get('k'))) S.f.recordKind = p.get('k');
  if (p.get('q') != null) S.q = p.get('q');
  // 바로가기 '주제 던지기'(#/progress?new=1): 진행 현황에서 새 주제 작성창을 연다
  S._composeOnOpen = S.view === 'progress' && p.get('new') === '1';
}
function go(view, opts = {}) {
  saveScreen();
  removePanels();
  if (RECORD_ALIAS[view]) { S.f.recordKind = RECORD_ALIAS[view]; view = 'history'; }
  const same = S.view === view && !screenHistory.get(screenId)?.panel;
  S.view = view;
  if (view === 'mine') { S.freshGates = new Set([...(S.freshGates || []), ...newGates()]); store.set('newGates', []); }
  if (opts.msg) S.f.msg = opts.msg;
  if (opts.stage) S.f.stage = opts.stage;
  if (opts.q != null) S.q = opts.q;
  if (!same) { screenId = screenKey(); pushScreen(routeUrl(view)); } else replaceScreen(routeUrl(view));
  $('.side')?.classList.remove('on');
  render(); window.scrollTo({ top: 0 }); saveScreen();
}
function restoreScreen() {
  if (!S.data) return;
  closingPanel = false;
  lastRestoredHref = location.href;
  // popstate 시 브라우저는 이미 이전 엔트리를 가리키므로 현재 화면은 Map에만 보존한다.
  saveScreen();
  if (history.state?.realops) { screenId = history.state.realops; curDepth = histDepth(); }
  else {  // 주소창에서 해시를 바꾼 방문: 화면 식별값을 이 기록에 써 둔다(hashchange가 다시 그리지 않게)
    screenId = screenKey(); curDepth += 1;
    history.replaceState({ realops: screenId, depth: curDepth }, '', location.href);
  }
  const saved = screenHistory.get(screenId);
  restoringScreen = true;
  removePanels();
  if (saved) { S.view = saved.view; S.f = { ...saved.f }; S.q = saved.q; S.mineSel = saved.mineSel; }
  else readHash();
  render();
  // 상세는 저장해 둔 화면 조각을 다시 붙이지 않고 지금 데이터로 새로 그린다.
  // 다시 그릴 방법이 없는 확인·입력 창(묶음 완료 확정·묶음 만들기·작성창 등)은 닫힌 상태로 복원한다(같은 결정을 다시 보내지 않게)
  if (saved?.panel) {
    if (saved.panel.topic && topicById(saved.panel.topic)) openTopic(topicById(saved.panel.topic));
    else if (typeof saved.panel.rebuild === 'function') { try { saved.panel.rebuild(); } catch { removePanels(); } }
  } else if (!saved) {
    const id = new URLSearchParams(location.hash.split('?')[1] || '').get('topic');
    if (id && topicById(id)) openTopic(topicById(id));
    else if (S._composeOnOpen) openComposer();
  }
  S._composeOnOpen = false;
  restoringScreen = false;
  requestAnimationFrame(() => {
    window.scrollTo(0, saved?.scroll || 0);
    [...document.querySelectorAll('.mine-list,.mine-detail .ms-main,.mine-detail .ms-side,.msg-list,.reader')].forEach((e,i) => { e.scrollTop = saved?.inner?.[i] || 0; });
    const body = document.querySelector('.drawer-b'); if (body) body.scrollTop = saved?.panelScroll || 0;
  });
}
window.addEventListener('popstate', restoreScreen);
history.scrollRestoration = 'manual';

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
    mine: approvals().total || null,
    topics: d.topics.filter(t => t.status === 'new').length || null,
    tasks: d.tasks.filter(t => t.stage !== 'done').length,
    messages: d.unprocessed.length || null,
    sources: data.sources.filter(s => !s.ok && !/선택/.test(s.error || '')).length || null,
  };
  const hot = { mine: true, topics: true, messages: true, sources: true };
  // 접힌 '관리'에도 연결 이상·미처리 메시지·새 주제 합계를 보인다(펼치면 같은 자리에 바로 가는 버튼)
  const adminParts = [['sources', '연결 이상', badges.sources], ['messages', '미처리 메시지', badges.messages], ['topics', '새 주제', badges.topics]].filter(([, , n]) => n);
  const adminSum = adminParts.reduce((a, [, , n]) => a + n, 0);
  // 기록 메뉴에서 들어가는 화면들은 '기록'을 현재 메뉴로 표시
  const navOn = id => S.view === id || (id === 'history' && DETAIL_NAV.some(n => n.id === S.view));
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
    h('button', { class: 'side-brand', title: '진행 현황으로', 'aria-label': '진행 현황으로 가기', onclick: () => { $('.side')?.classList.remove('on'); go('progress'); } },
      h('span', { class: 'brand-mark', 'aria-hidden': 'true' }), data.meta.project || 'REAL 작업실'),
    NAV.map(n => h('button', { class: 'nav-btn', 'aria-current': navOn(n.id) ? 'page' : null, onclick: () => go(n.id) },
      icon(n.icon), n.label, badges[n.id] ? h('span', { class: `badge${hot[n.id] ? ' hot' : ''}` }, badges[n.id]) : null)),
    h('details', { class: 'side-admin', open: S.adminOpen ? true : null, ontoggle: e => { S.adminOpen = e.target.open; } },
      h('summary', { title: adminParts.map(([, l, n]) => `${l} ${n}`).join(' · ') || '작업자·연결 상태' }, '관리',
        adminSum ? h('span', { class: 'badge hot', 'aria-label': `확인할 것 ${adminSum}건` }, adminSum) : null),
      ADMIN_NAV.map(n => h('button', { class: 'nav-btn', 'aria-current': S.view === n.id ? 'page' : null, onclick: () => go(n.id) }, icon(n.icon), n.label,
        badges[n.id] ? h('span', { class: 'badge hot' }, badges[n.id]) : null)),
      badges.messages ? h('button', { class: 'nav-btn', 'aria-current': S.view === 'messages' ? 'page' : null, onclick: () => go('messages', { msg: 'unprocessed' }) }, icon('messages'), '미처리 메시지', h('span', { class: 'badge hot' }, badges.messages)) : null,
      badges.topics ? h('button', { class: 'nav-btn', 'aria-current': S.view === 'topics' ? 'page' : null, onclick: () => go('topics') }, icon('topics'), '새 주제', h('span', { class: 'badge hot' }, badges.topics)) : null),
    h('div', { class: 'side-src' }, srcRows),
    h('div', { class: 'side-command' }, h('b', null, '서버컴 Astra'), h('span', null, '작업 분배 · 검수 · 배포 총괄')),
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
  const nav = [...NAV, ...ADMIN_NAV, ...DETAIL_NAV].find(n => n.id === S.view);
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
    S.newVersion ? h('button', { class: 'btn mine-btn hot', title: '대시보드 화면이 새로 게시됐습니다. 쓰던 글은 저장되어 있습니다.', onclick: () => location.reload() }, icon('refresh'), '새 화면 반영') : null,
    (() => { const n = newGates().length; return n ? h('button', { class: 'btn mine-btn hot gate-new', title: '새로 도착한 ★ 관문 — 누르면 결재함 관문 목록', onclick: () => { S.f.mine = 'gate'; S.mineSel = null; go('mine'); } }, icon('scale'), `새 관문 ${n}`) : null; })(),
    (() => { const a = approvals(), n = a.total; return h('button', { class: `btn mine-btn${n ? ' hot' : ''}`, 'data-approvals': String(n), onclick: () => go('mine'),
      title: `아키텍트가 답할 것 ${n}건${a.waiting.length ? ` · 답 보냄·반영 대기 ${a.waiting.length}건` : ''}` }, icon('user'), n ? `결재 ${n}` : '결재할 일 없음'); })(),
    h('button', { class: 'icon-btn bell', title: `놓친 항목 ${missed}`, 'aria-label': `놓친 항목 ${missed}건 보기`, onclick: openMissedDrawer },
      icon('bell'), missed ? h('span', { class: 'count' }, missed) : null));
}
function openMissedDrawer() {
  const items = openMissed();
  reopenWith(openMissedDrawer);
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
  const views = { progress: vProgress, history: vHistory, mine: vMine, overview: vOverview, agents: vAgents, topics: vTopics, tasks: vTasks, done: vDone, parked: vParked, deploy: vDeploy, messages: vMessages, verify: vVerify, brain: vBrain, sources: vSources };
  return h('div', { class: 'page' }, (views[S.view] || vProgress)());
}
function head(eyebrow, title, small, ...tools) {
  return h('div', { class: 'page-head' },
    h('div', null, h('h1', null, title, small ? h('small', null, small) : null)),  // 영어 머리글(eyebrow)은 쓰지 않는다
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
// 목록 카드 공통 원칙: 최대 3건, 각 건은 제목 1~2줄 + 메타 한 줄. 긴 설명은 눌러서 상세에서 본다. 머리줄 오른쪽 '더보기 +N'
function moreBtn(n, go) { return go ? h('button', { class: 'more-btn', onclick: go }, n > 0 ? `더보기 +${n}` : '더보기', icon('arrow')) : null; }
function listCard(title, rows, opts = {}) {
  const shown = rows.slice(0, opts.max || 3), rest = rows.length - shown.length;
  return card(title, { big: rows.length, unit: '건', cls: `list-card ${opts.cls || ''}`, right: [opts.right || null, moreBtn(rest, opts.more)] },
    shown.length ? h('div', { class: 'list' }, shown.map(r => h('button', { class: 'item c-row', onclick: r.go },
      h('span', { class: `lead-ico ${r.lv || ''}` }, icon(r.ico || 'file')),
      h('span', { class: 'body' }, h('span', { class: 't clamp-2' }, r.t), r.s ? h('span', { class: 's clamp-1' }, r.s) : null,
        h('span', { class: 'meta one-line' }, (r.meta || []).filter(Boolean)))))) : empty(opts.empty || '없습니다.'),
    opts.foot || null);
}

// ------------------------------------------------------------ 개요
function vOverview(embedded) {
  const d = S.d, data = S.data, now = new Date();
  // 완료율은 주제 기준: 완료 확정 ÷ 착수한 주제(새 주제·검토·준비·진행·관문 대기·완료). 미처리·보류·삭제는 뺀다
  const aiOf = id => ((data.agents || []).find(a => a.id === id) || {}).ai || (/claude/.test(id || '') ? 'claude' : /astra|gpt/.test(id || '') ? 'gpt' : '');
  const started = d.topics.filter(t => ['new', 'triage', 'ready', 'active', 'review_user', 'done'].includes(t.status) && !t.followed)  // 줄기 단위: 원래+후속을 1건으로
    .filter(t => S.f.owner === 'claude' ? aiOf(t.assignee) === 'claude' : S.f.owner === 'astra' ? aiOf(t.assignee) === 'gpt' : true);
  const total = started.length, done = started.filter(t => t.status === 'done').length;
  const pct = total ? Math.round(done / total * 100) : 0;
  const ownerChips = chips([['all', '전체'], ['claude', 'Claude', av('claude', true)], ['astra', 'Astra', av('astra', true)], ['user', '나', av('user', true)]],
    S.f.owner, v => { S.f.owner = v; render(); }, '담당 필터');

  // 넓고 높은 화면(1500×860 이상)에서는 한 화면에 스크롤 없이: 윗줄 요약 5칸 + 아랫줄 4칸(칸마다 최대 3건)
  const body = h('div', { class: 'ov-fit' },
    h('div', { class: 'ov-top' }, completionCard(pct, started, S.f.owner), collectedCard(), pipelineCard(), missedCard()),
    h('div', { class: 'ov-bottom' }, todayCard(), decisionsNeededCard(), projectsCard(), activityCard()),
    teamStrip());
  const day = `${pad(now.getMonth() + 1)}.${pad(now.getDate())} (${DAY[now.getDay()]})`;
  if (embedded) return { small: `${day} · 완료율 ${pct}%`, tools: ownerChips, body: [body] };
  return [head('OVERVIEW', '전체 현황', day, ownerChips), body];
}
// 개요 아랫줄: 진행 중 프로젝트(막힘·이번 주 마감을 먼저)
// 개요 아랫줄: 진행 중인 업무 = 업무 보드 흐름(막힘 → 검증 → 진행 → 요청 순, 아키텍트 대기는 '오늘 확인할 일'에 있으므로 뺌)
function projectsCard() {
  const ORDER = { blocked: 0, validating: 1, progress: 2, request: 3 };
  const items = flowItems(S.f.owner || 'all', 'all').filter(i => i.col in ORDER)
    .sort((a, b) => ORDER[a.col] - ORDER[b.col] || (PRI_ORDER[a.t.priority] ?? 9) - (PRI_ORDER[b.t.priority] ?? 9) || toMs(b.ts) - toMs(a.ts));
  const LV = { blocked: ['bad', 'alert'], validating: ['', 'eye'], progress: ['', 'play'], request: ['', 'inbox'] };
  const rows = items.map(it => {
    const t = it.t, who = it.kind === 'topic' ? (t.turn || t.assignee) : (LEGACY[t.owner] || t.owner);
    const label = (FLOW.find(c => c.id === it.col) || {}).label;
    return { lv: LV[it.col][0], ico: LV[it.col][1], t: t.title, s: it.kind === 'topic' ? topicPhase(t).label : (t.next_action || t.summary || ''),
      go: () => it.kind === 'topic' ? openTopic(t) : openTask(t),
      meta: [h('span', { class: `st ${it.col}` }, it.why.length ? it.why.join(' · ') : label), it.kind === 'task' ? h('span', { class: 'tag' }, '옛 작업표') : null,
        h('span', { class: 'wait' }, av(who || 'user', true), person(who || 'user').name), h('span', { class: 'when' }, fmtRel(it.ts))] };
  });
  const blocked = items.filter(i => i.col === 'blocked').length;
  return listCard('진행 중인 업무', rows, { more: () => go('tasks'), empty: '진행 중인 업무가 없습니다.',
    foot: blocked ? h('div', { class: 'card-foot' }, `막힘·멈춤 ${blocked}`) : null });
}
function activityCard() {
  const rows = timelineEvents().slice(0, 40).map(e => ({ ico: 'clock', t: e.t, s: e.s || '', go: e.go, meta: [h('span', { class: 'when' }, e.dateOnly ? fmtAbs(e.ts, true) : fmtRel(e.ts))] }));
  return listCard('최근 활동', rows, { more: () => go('messages') });
}
// 개요 맨 아래: 팀 현황 띠(작업자 한 줄씩 가로로). 자세한 건 작업자 화면
function teamStrip() {
  const agents = S.data.agents || [];
  return card('팀 현황', { cls: 'team-strip', right: h('button', { class: 'more-btn', onclick: () => go('agents') }, 'PC별 전체', icon('arrow')) },
    agents.length ? h('div', { class: 'team-rows' }, agents.map(a => {
      const st = agentState(a), s = agentStats(a.id);
      const run = (S.data.runs || []).find(r => r.agent === a.id);
      const tt = r => (topicById(r.topic) || {}).title || r.topic || '질문 답 반영';
      const now = run && isRunning(run) ? `자동 실행 중 · ${tt(run)}` : a.current ? a.current.project : run ? `마지막 자동 실행 · ${tt(run)} · ${fmtRel(run.ended || run.started)}` : '아직 실행 기록 없음';
      return h('button', { class: `team-row-item pc-${a.pc}`, onclick: () => go('agents') },
        av(a.id), h('div', { class: 'body' }, h('div', { class: 't' }, h('span', { class: 'pc-chip' }, a.pc_label), a.label || a.id), h('div', { class: 's clamp-2' }, now)),
        h('div', { class: 'tr-side' }, h('span', { class: `st ${st.cls}` }, icon(st.icon), st.label),
          h('span', { class: 'cnt' }, `주제 ${s.assigned.length}${s.turn.length ? ` · 차례 ${s.turn.length}` : ''}${a.usage && a.usage.seven_day ? ` · 주간 남음 ${100 - a.usage.seven_day.pct}%` : ''}`)));
    })) : empty('작업자 정보가 없습니다.'));
}
const PRI_ORDER = { P0: 0, P1: 1, P2: 2, P3: 3 };
const STAGE_ORDER = { blocked: 0, progress: 1, request: 2, validating: 3, user_test: 4, done: 5 };
function taskSort(a, b) {
  return (PRI_ORDER[a.priority] ?? 9) - (PRI_ORDER[b.priority] ?? 9) || STAGE_ORDER[a.stage] - STAGE_ORDER[b.stage] || toMs(b.updated_at) - toMs(a.updated_at);
}

// 완료율: 옆 수집·진행 단계 칸과 같은 막대 6줄(완료·남음 + 남은 주제가 어디 있는지)
function completionCard(pct, started, owner) {
  const n = (...st) => started.filter(t => st.includes(t.status)).length;
  const rows = [
    { label: '완료 확정', n: n('done'), c: 'st-done', ico: 'check' },
    { label: '남음', n: started.length - n('done'), c: 'ink-3', ico: 'clock' },
    { label: 'AI 끝남·★확인 대기', n: n('review_user'), c: 'st-user_test', ico: 'user' },
    { label: '진행 중', n: n('active'), c: 'st-progress', ico: 'tasks' },
    { label: '검토·준비', n: n('triage', 'ready'), c: 'st-validating', ico: 'eye' },
    { label: '새 주제', n: n('new'), c: 'st-request', ico: 'inbox' },
  ];
  const max = Math.max(1, ...rows.map(r => r.n));
  return card('완료율', { big: pct, unit: `% · 착수 ${started.length}건`, cls: 'sum-card', right: moreBtn(0, () => go('topics')) },
    h('div', { class: 'bars', title: `${owner === 'user' ? '아키텍트 담당 주제는 없어서 전체 기준으로 보여 줍니다.\n' : ''}착수한 주제 기준(미처리·보류·삭제 제외). 원래 주제와 후속 주제는 한 줄기로 1건(줄기 끝이 완료 확정돼야 완료). 완료는 ★9 완료 확정(조사·기획은 ★결과 확인)에서만 셉니다. AI가 끝낸 주제는 'AI 끝남·★확인 대기'에 있습니다.` },
      rows.map(r => h('button', { class: 'bar-row', onclick: () => go(r.label === '완료 확정' ? 'done' : 'topics'), 'aria-label': `${r.label} ${r.n}건` },
        h('span', { style: { color: `var(--${r.c})`, display: 'grid' } }, icon(r.ico)),
        h('span', { class: 'lbl' }, r.label),
        h('span', { class: 'track-bar' }, h('i', { style: { width: (r.n / max * 100) + '%', background: `var(--${r.c})` } })),
        h('span', { class: 'n' }, r.n)))));
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
  return card('수집', { big: total, unit: '건', cls: 'sum-card', right: chips([['24h', '24시간'], ['7d', '7일']], S.f.window, v => { S.f.window = v; render(); }, '수집 기간') },
    h('div', { class: 'bars' }, rows.map(r => h('button', { class: 'bar-row', onclick: r.go, 'aria-label': `${r.label} ${r.n}건` },
      h('span', { class: 'ico-dot', style: { background: `var(--${r.c})` } }, r.ini),
      h('span', { class: 'lbl' }, r.label),
      h('span', { class: 'track-bar' }, h('i', { style: { width: (r.n / max * 100) + '%', background: `var(--${r.c})` } })),
      h('span', { class: 'n' }, r.n)))));
}
// 업무 보드(진행 흐름)와 같은 칸·같은 건수
function pipelineCard() {
  const items = flowItems(S.f.owner || 'all', 'all');
  const cnt = id => items.filter(i => i.col === id).length;
  const max = Math.max(1, ...FLOW.map(c => cnt(c.id)));
  return card('진행 흐름', { big: items.filter(i => i.col !== 'done').length, accent: true, unit: '진행 중', cls: 'sum-card', right: moreBtn(0, () => go('tasks')) },
    h('div', { class: 'bars' }, FLOW.map(c => {
      const n = cnt(c.id);
      return h('button', { class: 'bar-row', onclick: () => go('tasks'), 'aria-label': `${c.label} ${n}건` },
        h('span', { style: { color: `var(--st-${c.id})`, display: 'grid' } }, icon(c.icon)),
        h('span', { class: 'lbl' }, c.label),
        h('span', { class: 'track-bar' }, h('i', { style: { width: (n / max * 100) + '%', background: `var(--st-${c.id})` } })),
        h('span', { class: 'n' }, n));
    })));
}
function missedCard() {
  const items = openMissed();
  return card('놓친 항목', { id: 'missed', big: items.length, unit: '건', cls: 'sum-card',
    right: [items.length ? h('button', { class: 'icon-btn', title: '모두 확인', 'aria-label': '놓친 항목 모두 확인', onclick: () => ack(items.map(i => i.key)) }, icon('check')) : null,
      moreBtn(items.length - 2, items.length > 2 ? openMissedDrawer : null)] },
    items.length ? h('div', { class: 'list' }, items.slice(0, 2).map(i => missedItem(i))) : empty('놓친 항목이 없습니다.'));
}
function missedItem(i, redraw) {
  return h('div', { class: 'item' },
    h('span', { class: `lead-ico ${i.level}` }, icon(i.icon)),
    h('button', { class: 'body', style: { border: '0', background: 'none', 'text-align': 'left', padding: '0', color: 'inherit' }, onclick: () => { if (redraw) closeDrawer(true); i.go(); } },
      h('div', { class: 't clamp-1' }, i.title), i.sub ? h('div', { class: 's clamp-1' }, i.sub) : null),
    h('button', { class: 'icon-btn ack-btn', title: '확인함', 'aria-label': '확인함으로 표시', onclick: () => ack(i.key, { redraw }) }, icon('check')));
}

function todayCard() {
  const d = S.d, data = S.data;
  const items = [];
  // ★ 관문(실게임 시험·배포본 결정·운영 반영 승인·완료 확정·결과 확인)은 한 줄로 묶어 맨 위에
  const gates = (data.decisions_needed || []).filter(q => (q.kind === 'gate' || q.kind === 'stall') && !d.answers[q.id] && (q.options || []).length);
  if (gates.length) {
    const by = {}; for (const q of gates) { const k = q.kind === 'stall' ? '멈춤' : q.gate === 40 ? '결과 확인' : (q.question.match(/^\[\d+\/9 ([^\]]+)\]/) || [])[1] || '관문'; by[k] = (by[k] || 0) + 1; }
    items.push({ ico: 'scale', lv: 'warn', t: `★ 관문 결정 ${gates.length}건`, s: Object.entries(by).map(([k, n]) => `${k} ${n}`).join(' · '), who: 'user',
      when: gates.map(q => q.since).sort()[0], go: () => { S.f.mine = 'decision'; S.mineSel = null; go('mine'); } });
  }
  for (const a of data.user_actions) items.push({ ico: 'user', lv: 'warn', t: a.title, s: a.detail, who: 'user', when: a.since, go: () => a.task_id && openTaskById(a.task_id) });
  for (const t of d.tasks.filter(t => t.priority === 'P0' && t.stage !== 'done')) items.push({ ico: 'alert', lv: 'bad', t: `P0 · ${t.title}`, s: t.next_action, who: t.waiting_on || t.owner, when: t.updated_at, go: () => openTask(t) });
  for (const t of d.topics.filter(t => t.status === 'new')) items.push({ ico: 'topics', lv: '', t: `새 주제 · ${t.title}`, s: '분배 대기', who: 'claude', when: t.created_at, go: () => openTopic(t) });
  const fresh = d.unprocessed.filter(m => hoursSince(m.ts) < 24);
  if (fresh.length) items.push({ ico: 'inbox', lv: '', t: `Astra 보고 ${fresh.length}건 확인`, s: fresh[0].title, who: 'claude', when: fresh[0].ts, go: () => go('messages', { msg: 'unprocessed' }) });
  return listCard('오늘 확인할 일', items.map(i => ({ ico: i.ico, lv: i.lv, t: i.t, s: i.s, go: i.go,
    meta: [h('span', { class: 'wait' }, av(i.who, true), person(i.who).name), h('span', { class: 'when' }, fmtRel(i.when))] })),
    { more: () => go('mine'), empty: '오늘 확인할 일이 없습니다.' });
}
// ------------------------------------------------------------ 내 차례 (아키텍트가 답하거나 확인할 것을 한곳에)
function myQueue() {
  const d = S.d, data = S.data;
  const done = k => S.acks.has(k) || S.serverAcks?.has(k);
  const decisions = (data.decisions_needed || []).filter(q => !d.answers[q.id]);
  const tests = (data.meta.command_epoch ? [] : d.tasks).filter(t => t.stage !== 'done' && (t.stage === 'user_test' || t.waiting_on === 'user') && !done(`mine-test:${t.id}:${t.updated_at}`));
  const actions = (data.user_actions || []).filter(a => !done(`ua:${a.id}`) && (!data.meta.command_epoch || a.kind === 'health' || d.topics.some(t => !t.archived && t.id === a.task_id)));
  const questions = [];
  for (const t of d.topics) {
    const lastUser = Math.max(0, ...commentsFor({ kind: 'topic', id: t.id }).filter(c => c.by === 'user').map(c => toMs(c.ts) || 0));
    for (const n of t.notes || []) {
      if (!t.command_mode && !t.archived && n.kind === 'question' && n.by !== 'user' && toMs(n.ts) > lastUser && !done(`mine-q:${t.id}:${n.ts}`)) questions.push({ topic: t, note: n });
    }
  }
  const backlog = d.topics.filter(t => t.status === 'backlog');
  return { decisions, tests, actions, questions, backlog, total: decisions.length + tests.length + actions.length + questions.length };
}
// 결재 건수의 단일 기준(위쪽 버튼·사이드바 배지·결재함·진행 현황이 모두 이 값을 쓴다).
// open = 아직 답을 보내지 않은 관문·결정·질문·할 일(결재함 목록 그대로, 착수 고르기 제외)
// waiting = 답은 보냈고 허브 반영(다음 동기화)을 기다리는 결정 — 건수에 넣지 않고 따로 표시
function approvals() {
  const open = mineItems().filter(i => i.type !== 'backlog');
  const waiting = (S.data.decisions_needed || []).filter(q => {
    const a = S.d.answers[q.id];
    if (!a) return false;
    if (a.pending) return true;  // 이 기기에서 보냄 · PC 반영 전
    const t = topicById(q.task_id);
    return q.kind === 'gate' ? !!(t && t.status === 'review_user' && t.gate && t.gate.id === q.id) : (q.options || []).length > 0 && !['done', 'neutral'].includes(decisionReflect(q, a).cls);
  }).map(q => ({ q, topic: topicById(q.task_id), ans: S.d.answers[q.id] }));
  return { open, waiting, total: open.length };
}
// 아키텍트 관문 대기열: 주제가 관문에 도착하면 여기서 끝까지 추적한다(답할 때까지 내 차례·개요·새 도착 알림에 남음)
const GATE_ORDER = { 9: 0, 7: 1, 5: 2, 40: 3, 4: 4 };  // 읽고 고르기만 하면 되는 것부터, 실게임 시험이 필요한 ★4는 맨 뒤 묶음(보고서 6번)
const GATE_LATE_H = 24;  // 이보다 오래 기다리면 '오래 대기'로 강조하고 놓친 항목에 올린다
function waitText(ts) {
  const hh = hoursSince(ts);
  return isNaN(hh) ? '대기' : hh < 1 ? `${Math.max(1, Math.round(hh * 60))}분째 대기` : hh < 48 ? `${Math.round(hh)}시간째 대기` : `${Math.round(hh / 24)}일째 대기`;
}
const STALL_LABEL = { park: 'AI 보류 제안', live: '실게임 수정 대화 필요', locked: '담당 잠김', offline: 'PC 신호 없음', health: '실행 오류', stalled: '실행기 멈춤', limit: '하루 실행 한도' };
function gateQueue() {
  return (S.data.decisions_needed || []).filter(q => (q.kind === 'gate' || q.kind === 'stall') && !S.d.answers[q.id] && (q.options || []).length)
    .map(q => {
      if (q.kind === 'stall') return { q, n: -1, label: `멈춤 · ${STALL_LABEL[q.stall] || '확인 필요'}`, topic: topicById(q.task_id), late: true };
      const m = (q.question || '').match(/^\[(\d+)\/9 ([^\]]+)\]/) || [];
      const n = q.gate || Number(m[1]);
      return { q, n, label: gateName(n, m[2] || '관문'), topic: topicById(q.task_id), late: hoursSince(q.since) >= GATE_LATE_H };
    })
    .sort((a, b) => (a.n === -1 ? -1 : GATE_ORDER[a.n] ?? 9) - (b.n === -1 ? -1 : GATE_ORDER[b.n] ?? 9) || toMs(a.q.since) - toMs(b.q.since));
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
  ['gate', '검토·결재', 'scale', 'warn'],
  ['decision', '판단 요청', 'scale', 'warn'],
  ['question', 'AI 질문', 'messages', 'warn'],
  ['action', '직접 조치', 'user', ''],
  ['backlog', '미착수', 'inbox', ''],
];
// 옛 작업표의 실게임·확인 대기(test)는 탭 없이 ★ 관문 '실게임 시험 필요' 묶음에 같이 보인다(보고서 5번)
const MINE_TYPE = Object.fromEntries([...MINE_TYPES, ['test', '실게임·확인', 'flask', 'warn']].map(([v, l, i, c]) => [v, { label: l, icon: i, cls: c }]));
function mineItems() {
  const q = myQueue(), items = [];
  // ★ 관문: 단계 순(실게임 시험 → 결과 확인 → 배포본 → 운영 반영 → 완료 확정), 같은 단계는 오래 기다린 것부터
  for (const x of gateQueue()) items.push({ key: `d:${x.q.id}`, type: 'gate', gn: x.n, title: x.topic ? x.topic.title : x.q.question.split('\n')[0], who: x.q._author || 'claude', when: x.q.since,
    topic: x.topic, taskId: x.q.task_id, ref: x.q, sub: `${x.label} · ${waitText(x.q.since)}${rollbacks(x.topic) ? ` · 되돌림 ${rollbacks(x.topic)}회` : ''}`, late: x.late });
  for (const x of q.decisions.filter(d => d.kind !== 'gate' && d.kind !== 'stall')) items.push({ key: `d:${x.id}`, type: 'decision', title: x.question, who: x._author || 'claude', when: x.since, topic: topicById(x.task_id), taskId: x.task_id, ref: x,
    sub: x.recommendation ? '권장 ' + x.recommendation : (x.options || []).length ? `선택지 ${x.options.length}개` : '' });
  for (const { topic, note } of q.questions) items.push({ key: `q:${topic.id}:${note.ts}`, type: 'question', title: note.body, who: note.by, when: note.ts, topic, ref: note });
  for (const t of q.tests) items.push({ key: `t:${t.id}`, type: 'test', title: t.title, sub: t.next_action || t.summary || '', who: t.owner, when: t.updated_at, topic: S.d.topics.find(x => x.linked_task_id === t.id) || null, taskId: t.id, ref: t });
  for (const a of q.actions) items.push({ key: `a:${a.id}`, type: 'action', title: a.title, sub: a.detail || '', who: 'user', when: a.since, topic: topicById(a.task_id) || S.d.topics.find(x => a.task_id && x.linked_task_id === a.task_id) || null, taskId: a.task_id, ref: a });
  for (const t of S.d.topics.filter(t => (t.conflict || []).length && !['done', 'dropped'].includes(t.status)))
    items.push({ key: `c:${t.id}:${t.conflict.join(',')}`, type: 'action', title: `중복 착수: ${t.title}`, sub: `담당 ${person(t.assignee).name} · 추가 착수 ${t.conflict.map(c => person(c).name).join(', ')} — 누가 계속할지 고르기`,
      who: t.assignee, when: t.updated_at, topic: t, taskId: null, ref: { kind: 'conflict', id: `conflict:${t.id}` } });
  for (const t of (S.data.meta.command_epoch ? [] : q.backlog)) items.push({ key: `b:${t.id}`, type: 'backlog', title: t.title, sub: t.body || '', who: t.proposed_by || 'user', when: t.created_at, topic: t, ref: t });
  return items;
}
// 화면에 보이는 순서 그대로(전체 탭: 관문 → 대응할 것 → 착수 고르기). 키보드 이동도 이 순서를 쓴다
function mineList(f = S.f.mine || 'all', all = mineItems()) {
  const quick = i => i.type === 'gate' && i.gn !== 4, live = i => (i.type === 'gate' && i.gn === 4) || i.type === 'test';
  return f === 'all' ? [...all.filter(quick), ...all.filter(live), ...all.filter(i => !['gate', 'test', 'backlog'].includes(i.type)), ...all.filter(i => i.type === 'backlog')]
    : f === 'gate' ? [...all.filter(quick), ...all.filter(live)] : all.filter(i => i.type === f);
}
function vMine() {
  const all = mineItems();
  const f = S.f.mine || 'all';
  const count = v => all.filter(i => i.type === v || (v === 'gate' && i.type === 'test')).length;
  const urgent = all.filter(i => i.type !== 'backlog');
  // 검색: 제목·내용·주제 이름·주제 ID·질문한 작업자로 찾는다(띄어 쓴 낱말은 모두 들어 있어야 함)
  const words = String(S.f.mineQ || '').trim().toLowerCase().split(/\s+/).filter(Boolean);
  const hay = i => [i.title, i.sub, i.topic?.title, i.topic?.id, i.taskId, person(i.who).name].join(' ').toLowerCase();
  const list = mineList(f, all).filter(i => !words.length || words.every(w => hay(i).includes(w)));
  if (!list.some(i => i.key === S.mineSel)) {
    // 키보드로 보낸 뒤에는 같은 자리(=다음 항목)로, 아니면 맨 위
    S.mineSel = (S.kbNextIdx != null && list.length ? list[Math.min(S.kbNextIdx, list.length - 1)] : f === 'all' ? urgent[0] || list[0] : list[0])?.key || null;
  }
  S.kbNextIdx = null;
  const sel = list.find(i => i.key === S.mineSel) || null;
  const narrow = matchMedia('(max-width: 1100px)').matches;
  const pick = it => { if (narrow) return openMineItem(it); if (S.mineSel !== it.key) S.editTopic = null; S.mineSel = it.key; S._keepScroll = true; render(); };
  const tabs = h('div', { class: 'mine-tabs', role: 'tablist', 'aria-label': '결재함 소분류' },
    [['all', '전체', 'user', '', urgent.length], ...MINE_TYPES.map(([v, l, i, c]) => [v, l, i, c, count(v)])].map(([v, l, i, c, n]) =>
      h('button', { role: 'tab', 'aria-selected': String(f === v), class: `mine-tab${n && c ? ' ' + c : ''}`, onclick: () => { S.f.mine = v; S.mineSel = null; S.mineSelecting = false; S.editTopic = null; render(); } },
        icon(i), h('span', null, l), h('b', null, n))),
    h('label', { class: 'mine-search' }, icon('search'),
      h('input', { type: 'search', placeholder: '결재함에서 찾기', 'aria-label': '결재함에서 찾기', value: S.f.mineQ || '', 'data-draft': 'mine-search',
        oninput: e => { S.f.mineQ = e.target.value; S.mineSel = null; S._keepScroll = true; render(); } })));
  // 착수 고르기: 여러 개 골라 한 번에 지우기
  const checked = S.mineChecked || (S.mineChecked = new Set());
  const selecting = f === 'backlog' && S.mineSelecting;
  const toggle = it => { checked.has(it.topic.id) ? checked.delete(it.topic.id) : checked.add(it.topic.id); S._keepScroll = true; render(); };
  const row = it => {
    const ty = MINE_TYPE[it.type];
    const on = selecting && checked.has(it.topic?.id);
    return h('button', { class: `mine-row${on ? ' checked' : ''}${it.late ? ' late' : ''}`, role: 'option', 'data-key': it.key, 'aria-selected': String(selecting ? on : !narrow && it.key === S.mineSel), onclick: () => selecting ? toggle(it) : pick(it) },
      selecting ? h('span', { class: `check${on ? ' on' : ''}`, 'aria-hidden': 'true' }, on ? icon('check') : null) : h('span', { class: `lead-ico ${ty.cls}` }, icon(ty.icon)),
      h('span', { class: 'body' },
        h('span', { class: 'kind' }, h('b', null, ty.label), it.topic && !['backlog', 'gate'].includes(it.type) ? h('span', { class: 'topic' }, it.topic.title) : null,
          it.type === 'gate' && S.freshGates?.has(it.ref.id) ? h('span', { class: 'st progress' }, '새') : null,
          it.late ? h('span', { class: 'st blocked' }, '오래 대기') : null),
        h('span', { class: 't clamp-2' }, it.title),
        it.sub && it.type !== 'backlog' ? h('span', { class: 's clamp-1' }, it.sub) : null,
        h('span', { class: 'meta' }, av(it.who, true), h('span', null, person(it.who).name), histCount(it.topic, it.taskId), h('span', { class: 'when' }, fmtRel(it.when)))));
  };
  const group = (title, items, extra) => items.length ? [h('div', { class: 'mine-group' }, title, h('b', null, items.length), extra || null), items.map(row)] : null;
  const listBody = !list.length ? empty(f === 'all' ? '지금 대응할 것이 없습니다.' : `${MINE_TYPE[f].label} 항목이 없습니다.`)
    : f === 'all' || f === 'gate' ? [group('★ 관문 · 읽고 고르기(빨리 끝남)', list.filter(i => i.type === 'gate' && i.gn !== 4)),
      group('★ 관문 · 실게임 시험 필요', list.filter(i => (i.type === 'gate' && i.gn === 4) || i.type === 'test'), liveBatchButton(list)),
      f === 'all' ? group('대응할 것', urgent.filter(i => !['gate', 'test'].includes(i.type))) : null,
      f === 'all' ? group('착수 고르기 · 미처리 주제', all.filter(i => i.type === 'backlog')) : null] : list.map(row);
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
    head('MY TURN', '결재함', urgent.length ? `대응할 것 ${urgent.length}건 · 미처리 주제 ${count('backlog')}건` : `지금 대응할 것 없음 · 미처리 주제 ${count('backlog')}건`,
      !('Notification' in window) ? null : Notification.permission === 'default'
        ? h('button', { class: 'btn', title: '대시보드 창이 열려 있으면(내려 두어도) 새 ★ 관문이 도착할 때 바탕화면 알림을 띄웁니다', onclick: () => Notification.requestPermission().then(() => render()) }, icon('bell'), '새 관문 알림 켜기')
        : Notification.permission === 'granted' ? h('span', { class: 'hint' }, '새 관문 바탕화면 알림 켜짐') : h('span', { class: 'hint' }, '알림이 브라우저에서 막혀 있음(사이트 설정에서 허용)')),
    mineSummary(all),
    tabs,
    h('div', { class: `mine-split fit-page${narrow ? ' narrow' : ''}` },
      h('div', { class: 'card mine-list', role: 'listbox', 'aria-label': '결재함 목록', 'aria-multiselectable': selecting ? 'true' : null }, listTools, listBody, droppedBox),
      narrow ? null : h('section', { class: 'card mine-detail', 'aria-label': '선택한 항목' },
        detail ? [h('div', { class: 'mine-detail-h' }, h('span', { class: 'eyebrow' }, detail.eyebrow),
            h('button', { class: 'btn sm', title: '크게 보기', onclick: () => openMineItem(sel) }, icon('arrow'), '크게 보기')),
          h('div', { class: 'mine-detail-b' }, h('div', { class: 'ms-main' }, detail.main), h('div', { class: 'ms-side' }, detail.side)),
          kbHint()]
          : h('div', { class: 'mine-detail-empty' }, empty('왼쪽에서 항목을 고르면 내용과 히스토리가 여기에 보입니다.')))),
  ];
}
// 내 차례 한 줄 요약(보고서 5번): 지금 쌓인 것을 한눈에, 누르면 그 목록으로
function mineSummary(all) {
  const n = f => all.filter(f).length;
  const parts = [
    ['읽고 고르기', n(i => i.type === 'gate' && i.gn !== 4), () => { S.f.mine = 'gate'; }],
    ['실게임 시험', n(i => (i.type === 'gate' && i.gn === 4) || i.type === 'test'), () => { S.f.mine = 'gate'; }],
    ['결정·승인', n(i => i.type === 'decision'), () => { S.f.mine = 'decision'; }],
    ['AI 질문', n(i => i.type === 'question'), () => { S.f.mine = 'question'; }],
    ['할 일', n(i => i.type === 'action'), () => { S.f.mine = 'action'; }],
    ['착수 고르기', n(i => i.type === 'backlog'), () => { S.f.mine = 'backlog'; }],
    ['보류', S.d.topics.filter(t => t.status === 'parked' && !t.archived).length, () => go('parked')],
    ['배포 대기열', S.d.topics.filter(t => t.status === 'active' && t.stage === 'queue').length, () => go('deploy')],
    ['배포 대화 대기(묶음)', new Set(S.d.topics.filter(t => t.status === 'active' && t.deploy_session && t.deploy_batch).map(t => t.deploy_batch.id)).size, () => go('deploy')],
    ['헛도는 중', S.d.missed.filter(m => m.key.startsWith('idle:')).length, null],
  ];
  return h('div', { class: 'mine-summary' }, parts.map(([l, c, act]) => h(act && c ? 'button' : 'span', {
    class: `ms-chip${c ? ' on' : ''}`, onclick: act && c ? () => { S.mineSel = null; act(); render(); } : null }, l, ' ', h('b', null, c))));
}
// ★4 시험 묶음(보고서 6번): 여러 ★4 주제를 대화 한 번에 반영·빌드·시험한다
// 빌드 성공 기록이 있을 때만 '빌드 있음'(파일 SHA256만 적힌 요약이나 '아직 빌드 안 함'은 반영·빌드 필요)
function liveReady(t) {
  const s = [t?.gate?.summary || '', ...(t?.notes || []).filter(n => /^\[실행기 dev_run\]/.test(n.body || '')).map(n => n.body)].join('\n');
  return /빌드 결과물|빌드 (PASS|통과|성공)/.test(s) && !/빌드(는|를|도)? ?(아직|하지 않|안 ?함|전)/.test(s);
}
function liveBatchButton(list) {
  const lives = list.filter(i => i.type === 'gate' && i.gn === 4 && i.topic);
  return lives.length > 1 ? h('button', { class: 'btn sm', style: { 'margin-left': 'auto' }, onclick: e => { e.stopPropagation(); openLiveBatch(lives.map(i => i.topic)); } }, icon('flask'), '시험 묶음 만들기') : null;
}
function liveBatchText(ts) {
  return `실게임 시험 묶음 — 주제 ${ts.length}개를 이 대화에서 한 번에 반영·빌드·시험합니다.\n` +
    `1) 대시보드 도구 폴더(node.py가 있는 곳)에서 주제마다 python node.py brief <주제ID> 로 내용·작업물·체크리스트를 불러오세요.\n` +
    `2) 격리 서버(server-dev)에 모두 반영하고 한 번에 빌드합니다. 같은 파일을 고치는 주제가 있으면 먼저 알려 주세요.\n` +
    `3) 아키텍트가 한 번 접속해 주제별 체크리스트를 차례로 확인합니다. 체크리스트를 주제별로 묶어 보여 주세요.\n` +
    `4) 시험 중 고친 주제는 python node.py state <주제ID> --agent dev-claude --status done --note "무엇을 고쳤나·시험 방법" 으로 남기세요(★4로 다시 옵니다). 통과 여부는 아키텍트가 대시보드 ★4에서 고릅니다.\n` +
    `운영 서버 반영은 ★7 승인 뒤 서버컴에서만 합니다.\n\n주제:\n` +
    ts.map(t => `- ${t.id} "${t.title}" (${liveReady(t) ? '빌드 있음' : '반영·빌드 필요'})`).join('\n');
}
function openLiveBatch(ts) {
  const on = new Set(ts.map(t => t.id));
  const box = h('div');
  const draw = () => {
    box.replaceChildren(
      h('p', { class: 'hint' }, '시험할 주제를 고르고 문구를 복사해 개발컴 Claude 대화에 붙여 넣으세요. 결과는 주제마다 ★4에서 고르시면 됩니다.'),
      h('div', { class: 'opt-list' }, ts.map(t => h('label', { class: 'opt' }, h('input', { type: 'checkbox', checked: on.has(t.id) ? true : null, onchange: e => { e.target.checked ? on.add(t.id) : on.delete(t.id); draw(); } }),
        h('span', null, t.title, h('span', { class: 'opt-hint' }, liveReady(t) ? '빌드 있음 — 바로 시험 가능' : '반영·빌드 먼저 필요'))))),
      h('div', { class: 'row', style: { 'margin-top': '10px' } }, h('button', { class: 'btn primary', disabled: on.size ? null : true, onclick: async () => {
        const text = liveBatchText(ts.filter(t => on.has(t.id)));
        try { await navigator.clipboard.writeText(text); toast(`${on.size}개 묶음 문구를 복사했습니다. 개발컴 Claude 대화에 붙여 넣으세요.`); } catch { modal('시험 묶음 문구', h('pre', { class: 'pre' }, text)); }
      } }, icon('send'), `${on.size}개 묶음 문구 복사`)));
  };
  draw();
  modal('★4 실게임 시험 묶음', box);
}
// 좁은 화면·"크게 보기": 같은 내용을 가운데 모달로
function openMineItem(it) {
  const d = mineDetail(it, () => { const again = mineItems().find(x => x.key === it.key); again ? openMineItem(again) : closeDrawer(); });
  // 뒤로/앞으로 복원 때는 지금 데이터로 다시 연다(이미 답한 항목이면 목록에서 빠져 닫힌 채로)
  reopenWith(() => { const x = mineItems().find(i => i.key === it.key); if (x) openMineItem(x); });
  modalSplit(d.eyebrow, [d.main, kbHint()], d.side);
  const panel = [...document.querySelectorAll('.drawer.modal.split')].pop();
  if (panel) { panel.dataset.kb = 'mine'; panel.dataset.key = it.key; }
}
function mineDetail(it, redraw) {
  if (it.type === 'gate') return { eyebrow: `★ 관문 · ${it.sub}`, ...decisionParts(it.ref, redraw) };
  if (it.type === 'decision') return { eyebrow: '결정·승인 요청', ...decisionParts(it.ref, redraw) };
  if (it.type === 'question') return { eyebrow: 'AI 질문', ...questionParts(it.topic, it.ref, redraw) };
  if (it.type === 'test') return { eyebrow: '실게임·확인 대기', ...testParts(it.ref, it.topic, redraw) };
  if (it.type === 'action' && it.ref.kind === 'conflict') return { eyebrow: '할 일 · 중복 착수', ...conflictParts(it.topic, redraw) };
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
        h('button', { class: 'btn primary', 'data-kb-key': 'y', onclick: () => setStages([t.id], 'done', after) }, icon('check'), '확인 완료', kbd('Y')),
        h('button', { class: 'btn', 'data-kb-key': 'n', 'data-kb-problem': '1', onclick: () => setStages([t.id], 'blocked', after) }, icon('alert'), '문제 있음', kbd('N')),
        h('button', { class: 'btn', 'data-kb-key': 'l', onclick: () => { ack(`mine-test:${t.id}:${t.updated_at}`); after(); } }, icon('clock'), '나중에', kbd('L')),
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
        h('button', { class: 'btn primary', 'data-kb-key': 'x', onclick: () => { ack(`ua:${a.id}`); if (redraw) redraw(); } }, icon('check'), '했음', kbd('X')),
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
  return h('div', { class: 'dropped-card' },
    h('p', { class: 'hint', style: { margin: 0 } }, `삭제한 주제 ${list.length}건 · 되살리면 원래 자리(미처리·새 주제)로 돌아갑니다`),
    h('div', { class: 'list' }, list.map(t => h('div', { class: 'item' },
      h('span', { class: 'lead-ico' }, icon('x')),
      h('div', { class: 'body' }, h('div', { class: 't' }, t.title), h('div', { class: 's' }, `${t.id} · 삭제 ${fmtRel(t.dropped_at)}${t._pendingDrop ? ' · 반영 대기' : ''}`)),
      h('button', { class: 'btn sm', onclick: () => dropTopics(t.id, true) }, icon('refresh'), '되살리기')))));
}

// 미처리 주제: 내용·히스토리를 보고 자동 배분 또는 담당을 골라 착수, 착수 전에 전할 말
function backlogParts(t, redraw) {
  const pendAct = pending.all().find(p => p.type === 'activate' && p.topic === t.id);
  const pendAsg = pending.all().find(p => p.type === 'assign' && p.topic === t.id);
  const kbAgent = S.kbPick && S.kbPick.id === t.id ? S.kbPick.agent : '';
  const sel = h('select', { 'aria-label': '담당 고르기', 'data-kb-agent': '1', class: kbAgent ? 'kb-picked' : '' },
    agentOptions(kbAgent || (pendAsg ? pendAsg.agent : ''), [h('option', { value: '' }, '담당 고르기')]).map((o, i) => { if (i > 0 && i < 10) o.textContent = `${i}. ${o.textContent}`; return o; }));
  const busy = b => { b.disabled = true; return () => { b.disabled = false; }; };
  const auto = h('button', { class: 'btn primary', 'data-kb-key': 'a' }, icon('play'), '자동 배분으로 착수', kbd('A'));
  auto._kb = async (opt = {}) => {
    const done = busy(auto);
    try { await sendOps('activate', { topic: t.id }, `착수 지시: ${t.title}`); if (!opt.quiet) { render(); if (redraw) redraw(); } return true; } catch (e) { toast(e.message); return false; } finally { done(); }
  };
  auto.onclick = () => auto._kb();
  const mine = h('button', { class: 'btn', 'data-kb-assign': '1' }, icon('agents'), '이 담당으로 착수', kbd('Enter'));
  mine._kb = async (opt = {}) => {
    if (!sel.value) { toast('담당을 먼저 고르세요(1~9)'); sel.focus(); return false; }
    const done = busy(mine);
    try {
      await sendOps('assign', { topic: t.id, agent: sel.value, note: '' }, `주제 담당 → ${person(sel.value).name}`);
      await sendOps('activate', { topic: t.id }, `착수 지시: ${t.title}`);
      if (!opt.quiet) { render(); if (redraw) redraw(); }
      return true;
    } catch (e) { toast(e.message); return false; } finally { done(); }
  };
  mine.onclick = () => mine._kb();
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
  const list = S.data.decisions_needed || [];
  const open = list.filter(q => !S.d.answers[q.id]);
  const waiting = list.filter(q => S.d.answers[q.id]).filter(q => { const r = decisionReflect(q, S.d.answers[q.id]); return r.cls !== 'done' && r.cls !== 'neutral'; });
  const rows = open.map(q => ({ ico: 'scale', lv: 'warn', t: q.question, s: q.recommendation ? '권장: ' + q.recommendation : (q.options || []).length ? `선택지 ${q.options.length}개` : '', go: () => openDecisionNeeded(q),
    meta: [h('span', { class: 'wait' }, av(q._author || 'claude', true), person(q._author || 'claude').name), q.task_id ? h('span', { class: 'tag one-line-s' }, (topicById(q.task_id) || {}).title || q.task_id) : null, h('span', { class: 'when' }, fmtRel(q.since))] }));
  return listCard('결정이 필요한 문제', rows, { more: () => { S.f.mine = 'decision'; S.mineSel = null; go('mine'); }, empty: '지금 결정할 문제가 없습니다.',
    foot: waiting.length ? h('button', { class: 'card-foot linkless', onclick: () => { S.f.mine = 'all'; go('mine'); } }, `답했지만 아직 반영 전 ${waiting.length}건`) : null });
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
  const work = agentWork(id).map(w => w.t);
  const assigned = [...work, ...topics.filter(t => !t.command_mode && t.assignee === id && !work.includes(t))], turn = topics.filter(t => t.turn === id);
  const works = [...new Set([...assigned, ...turn].map(t => t.work_id).filter(Boolean))].map(w => (S.data.works || {})[w]).filter(Boolean);
  const legacy = S.d.tasks.filter(t => t.stage !== 'done' && (t.owner === id || LEGACY[t.owner] === id || t.waiting_on === id || LEGACY[t.waiting_on] === id));
  return { assigned, turn, works, legacy, tasks: [...works, ...legacy] };
}
// 왜 이 작업자 차례인가(작업자 카드 'AI 차례' 목록)
function turnWhy(t, id) {
  if (t.live_session) return '실게임 대화';
  if ((t.open_request || {}).to === id) return '요청 받음';
  if (t.stage === 'pack' && t.stage_owner === id) return '배포본 작성';
  if (t.stage === 'prep' && t.stage_owner === id) return '배포 준비';
  if (t.stage === 'deploy' && t.stage_owner === id) return '배포(대화)';
  if (t.stage === 'test' && t.stage_owner === id) return '자체 시험';
  if (t.reviewer === id && t.assignee !== id) return '교차 검토';
  if ((t.handoff || {}).to === id) return '인계 받음';
  return t.assignee === id ? '담당 진행' : '차례';
}
// 실행기 판정(작업자 기록 queue.items) — 사람이 읽는 말로
function runnerVerdict(t, id) {
  const q = ((S.data.agents || []).find(a => a.id === id) || {}).queue || {};
  if (lockOf(id)) return '잠김';
  if ((q.idle || []).some(x => x.topic === t.id)) return '헛도는 중';
  return ({ runnable: '곧 실행', retry: '간격 두고 다시 깨움', waiting_answer: '아키텍트 답 대기', waiting_change: '변화 기다림', held: '대화 세션이 잡음', stalled: '건너뛰는 중' })[(q.items || {})[t.id]] || '—';
}
// 구독 한도 사용률(계정 전체: 대화 세션 + 자동 실행). 실행기가 Claude 실행 출력·Codex 기록에서 읽어 온다
function usageBox(a) {
  const u = a.usage || {};
  const row = (lbl, w) => {
    if (!w) return h('div', { class: 'u-row' }, h('span', { class: 'lbl' }, lbl), h('span', { class: 'track-bar' }), h('span', { class: 'n muted' }, '정보 없음'));
    const pct = Math.max(0, Math.min(100, Number(w.pct) || 0)), lv = pct >= 90 ? 'bad' : pct >= 75 ? 'warn' : 'ok';
    return h('div', { class: `u-row ${lv}`, title: w.resets_at ? `${lbl} 한도 ${pct}% 사용 · ${fmtAbs(w.resets_at)} 초기화` : '' },
      h('span', { class: 'lbl' }, lbl), h('span', { class: 'track-bar' }, h('i', { style: { width: pct + '%' } })),
      h('span', { class: 'n' }, h('b', null, `남음 ${100 - pct}%`), w.resets_at ? h('small', null, ` · ${fmtAbs(w.resets_at)} 초기화`) : null));
  };
  return h('div', { class: 'usage' },
    h('div', { class: 'u-hd' }, h('b', null, '사용량'), a.plan ? h('span', { class: 'tag' }, `${a.plan} 요금제`) : null,
      u.overage ? h('span', { class: 'st blocked' }, '초과 사용 중') : null,
      u.credits ? h('span', { class: 'tag', title: '주간 한도를 넘으면 쓰는 추가 크레딧 잔액' }, `크레딧 ${Number(u.credits.balance).toLocaleString()}`) : null,
      h('span', { class: 'muted', style: { 'margin-left': 'auto' } }, u.seen_at ? `${fmtRel(u.seen_at)} 확인` : '다음 자동 실행 때 수집')),
    row('5시간', u.five_hour), row('주간', u.seven_day));
}
function agentCard(a) {
  const st = agentState(a), s = agentStats(a.id), cur = a.current;
  return h('div', { class: `agent pc-${a.pc}` },
    h('div', { class: 'hd' }, av(a.id), h('div', { style: { 'min-width': '0' } },
      h('div', { class: 'nm' }, h('span', { class: 'pc-chip' }, a.pc_label), a.label || a.id), h('div', { class: 'rl' }, `${a.ai === 'gpt' ? 'GPT 계열' : 'Claude 계열'} · ${a.id}`)),
      h('span', { class: `st ${st.cls}`, style: { 'margin-left': 'auto' } }, icon(st.icon), st.label)),
    lockControls(a),
    usageBox(a),
    agentWorkBox(a),
    cur ? h('div', { class: 'now' }, h('b', null, cur.project), (cur.task || cur.topic) ? h('div', { class: 'muted', style: { 'font-size': '12px' } }, [cur.task, cur.topic].filter(Boolean).join(' · ')) : null,
      cur.note ? h('div', { class: 'muted', style: { 'font-size': '12px' } }, cur.note) : null,
      h('div', { class: 'muted', style: { 'font-size': '12px' } }, `${fmtRel(cur.since)}부터`))
      : null,
    runnerBox(a) || (cur ? null : h('div', { class: 'now idle' }, '자동 실행 기록도, 대화 세션 작업 알림도 아직 없습니다.')),
    agentLists(a, s),
    a.health && a.health.state && a.health.state !== 'ok' ? h('div', { class: `callout ${a.health.needs_user ? 'warn' : ''}` }, h('b', null, `${HEALTH[a.health.state] || '실행 오류'} · ${fmtRel(a.health.since || a.health.at)}부터`), h('div', null, a.health.fix || a.health.message)) : null,
    h('div', { class: 'muted', style: { 'font-size': '12px' } }, `마지막 신호 ${fmtRel(a.last_seen || a.pc_synced)}`));
}
// 배정·착수 상태(서버컴 DISPATCH-UI-REQUEST, 아키텍트 10-03): 실제 근거로만 — 사령탑 연결은 착수가 아니고, ready·계획 기록은 실행 중이 아니다
//   배정 대기: 사령탑이 아직 작업을 나누지 않음 · 착수 대기: 차례가 왔지만 실행 기록 없음 · 순서 대기: 앞 작업이 끝나야 함
//   실행 중: 지금 자동 실행 기록이 있음 · 진행함: 이 작업자가 이 주제를 실행한 기록이 있음(지금은 쉬는 중) · 검수 대기 · 막힘
const runOf = (agentId, topicId) => runsFor(topicId).find(r => r.agent === agentId) || null;
function workOf(t, agentId) {
  if (t.archived || ['done', 'dropped', 'parked', 'backlog'].includes(t.status)) return null;
  if (t.command_mode && t.assignee === agentId && !(t.command?.tasks || []).length) return null;  // 사령탑 연결만(작업 나누기 전) = 배정 대기 — 맡은 일로 세지 않음(commandOf)
  const items = [];
  for (const x of (t.command?.tasks || [])) if (x.assignee === agentId && ['ready', 'review', 'blocked'].includes(x.state)) items.push({ kind: '작업', x });
  if (t.stage === 'test') for (const x of (t.command?.tests || [])) if (x.assignee === agentId && ['running', 'pending', 'failed', 'blocked'].includes(x.state)) items.push({ kind: '시험', x });
  const myTurn = t.turn === agentId;
  if (!items.length && !myTurn) return null;
  const run = runOf(agentId, t.id);
  let state;
  if (isRunning(run)) state = { key: 'running', label: '실행 중', cls: 'progress' };
  else if (items.some(i => i.x.state === 'blocked')) state = { key: 'blocked', label: '막힘 · Astra 조정', cls: 'blocked' };
  else if (items.length && items.every(i => i.x.state === 'review')) state = { key: 'review', label: 'Astra 검수 대기', cls: 'user_test' };
  else if (myTurn) state = run ? { key: 'started', label: `진행함 · 마지막 실행 ${fmtRel(run.ended || run.started)}`, cls: 'progress' } : { key: 'waiting', label: '착수 대기', cls: 'neutral' };
  else state = { key: 'queued', label: '순서 대기(앞 작업 뒤)', cls: 'neutral' };
  const n = k => items.filter(i => i.kind === k).length;
  const what = [n('작업') ? `작업 ${n('작업')}` : null, n('시험') ? `시험 ${n('시험')}` : null].filter(Boolean).join(' · ') || turnWhy(t, agentId);
  return { t, items, state, what };
}
function agentWork(agentId) {
  return S.d.topics.map(t => workOf(t, agentId)).filter(Boolean)
    .sort((a, b) => ['running', 'blocked', 'review', 'waiting', 'started', 'queued'].indexOf(a.state.key) - ['running', 'blocked', 'review', 'waiting', 'started', 'queued'].indexOf(b.state.key));
}
// 사령탑(총괄) 현황: 총괄 주제 중 아직 작업을 나누지 않은(배정 대기) 수
function commandOf(agentId) {
  const own = S.d.topics.filter(t => t.command_mode && !t.archived && t.assignee === agentId && !['done', 'dropped', 'parked', 'backlog'].includes(t.status));
  const un = own.filter(t => !(t.command?.tasks || []).length);
  return own.length ? { total: own.length, unassigned: un.length, planning: un.filter(t => isRunning(runOf(agentId, t.id))) } : null;
}
// 작업자 카드 '맡은 일': 주제당 한 줄(아키텍트 10-03 '같은 거 막 섞여 있고') — 제목 · 무엇 · 상태
function agentWorkBox(a) {
  const rows = agentWork(a.id), cmd = commandOf(a.id);
  if (!rows.length && !cmd) return null;
  S.workOpen = S.workOpen || {};
  const open = !!S.workOpen[a.id];
  const count = k => rows.filter(r => r.state.key === k).length;
  const sum = [['running', '실행 중'], ['waiting', '착수 대기'], ['review', '검수 대기'], ['blocked', '막힘'], ['queued', '순서 대기']].map(([k, l]) => count(k) ? `${l} ${count(k)}` : null).filter(Boolean).join(' · ');
  return h('div', { class: 'now agent-work' },
    cmd ? h('div', null, h('b', null, `총괄 ${cmd.total}건`), h('span', { class: 'muted' }, ` · 배정 대기 ${cmd.unassigned} · 작업 나눔 ${cmd.total - cmd.unassigned}`),
      cmd.planning.map(t => h('button', { class: 'work-row', onclick: () => openTopic(t) }, h('span', { class: 'clamp-1' }, t.title), h('small', { class: 'muted' }, '작업 나누기'), h('span', { class: 'st progress' }, '실행 중')))) : null,
    rows.length ? [h('div', null, h('b', null, `맡은 주제 ${rows.length}건`), sum ? h('span', { class: 'muted' }, ` · ${sum}`) : null),
      (open ? rows : rows.slice(0, 3)).map(r => h('button', { class: 'work-row', onclick: () => openTopic(r.t) },
        h('span', { class: 'clamp-1' }, r.t.title), h('small', { class: 'muted' }, r.what), h('span', { class: `st ${r.state.cls}` }, r.state.label))),
      rows.length > 3 ? h('button', { class: 'more-btn', onclick: () => { S.workOpen[a.id] = !open; S._keepScroll = true; render(); } }, open ? '접기' : `${rows.length - 3}건 더 보기`) : null] : null);
}
// 작업자 카드 숫자 칸: 눌러서 아래 목록을 그 기준으로(아키텍트 2026-10-03). 목록은 카드 안에서 스크롤
function agentLists(a, s) {
  S.agentTab = S.agentTab || {};
  const tab = S.agentTab[a.id] || 'assigned';
  const pick = v => () => { S.agentTab[a.id] = v; S._keepScroll = true; render(); };
  const cell = (v, n, l) => h('button', { class: `stat-btn${tab === v ? ' on' : ''}`, 'aria-pressed': String(tab === v), onclick: pick(v) }, h('b', null, n), h('span', null, l));
  const topicRow = (t, extra) => h('button', { class: 'item', onclick: () => openTopic(t) },
    h('span', { class: 'body' }, h('div', { class: 't clamp-1' }, t.title), h('div', { class: 'meta' }, extra || [topicChip(t.status), priChip(t.priority), t.turn === a.id ? h('span', { class: 'tag' }, 'AI 차례') : null])));
  const lastRun = t => (runsFor(t.id).find(r => r.agent === a.id) || {}).started;
  let body;
  if (tab === 'turn') body = s.turn.length ? s.turn.map(t => topicRow(t, [h('span', { class: 'tag' }, turnWhy(t, a.id)), h('span', { class: 'tag' }, runnerVerdict(t, a.id)),
    h('span', { class: 'muted' }, lastRun(t) ? `실행 ${fmtRel(lastRun(t))}` : '실행 기록 없음')])) : [empty('지금 이 작업자 차례인 주제가 없습니다.')];
  else if (tab === 'tasks') body = s.tasks.length ? [
    ...s.works.map(w => h('a', { class: 'item', href: w.main_url || w.url, target: '_blank', rel: 'noopener noreferrer' },
      h('span', { class: 'body' }, h('div', { class: 't clamp-1' }, w.title || w.id), h('div', { class: 'meta' }, h('span', { class: 'tag' }, `작업물 ${w.id}`), h('span', { class: 'muted' }, `파일 ${w.file_count} · ${w.state || '-'}`))))),
    ...s.legacy.map(t => h('button', { class: 'item', onclick: () => openTask(t) }, h('span', { class: 'body' }, h('div', { class: 't clamp-1' }, t.title), h('div', { class: 'meta' }, h('span', { class: 'tag' }, '옛 작업표')))))]
    : [empty('관련 작업물이 없습니다.')];
  else body = s.assigned.length ? s.assigned.map(t => topicRow(t)) : [empty('맡은 주제가 없습니다.')];
  return [h('div', { class: 'stats' }, cell('assigned', s.assigned.length, '맡은 주제'), cell('turn', s.turn.length, 'AI 차례'), cell('tasks', s.tasks.length, '관련 작업')),
    h('div', { class: 'list agent-topics' }, body)];
}
// 작업자 카드: 자동 실행기가 지금 무엇을 하는지, 차례인 일이 왜 멈춰 있는지
function runnerBox(a) {
  const run = (S.data.runs || []).find(r => r.agent === a.id);
  const q = a.queue;
  if (!run && !(q && q.total)) return null;
  const title = r => ((topicById(r.topic) || {}).title || r.topic || '질문 답 반영');
  const parts = q ? [['곧 실행', (q.runnable || 0) + (q.answers || 0)], ['아키텍트 답 대기', q.waiting_answer], ['다른 쪽 변화 기다림', q.waiting_change],
    ['재시도 대기', q.retry], ['대화 세션이 잡음', q.held]].filter(([, n]) => n) : [];
  return h('div', { class: `now runner-now${isRunning(run) ? '' : ' idle'}` },
    run ? (isRunning(run)
      ? [h('b', null, `자동 실행 중 · ${title(run)}`), h('div', { class: 'muted', style: { 'font-size': '12px' } }, `${fmtRel(run.started)} 시작 · 이유: ${run.reason || '-'}`)]
      : [h('b', null, `마지막 자동 실행 · ${title(run)}`), h('div', { class: 'muted', style: { 'font-size': '12px' } }, `${fmtRel(run.ended || run.started)} · ${RUN_RESULT[run.result] || run.result}`),
        run.summary ? h('div', { class: 'muted clamp-2', style: { 'font-size': '12px' } }, run.summary) : null]) : null,
    q && q.total ? h('div', { class: 'queue-line' }, `차례 ${q.total}건 — `, parts.map(([l, n]) => `${l} ${n}`).join(' · ') || '정리 중') : null);
}
// 아키텍트 결정이 실제로 반영됐는지: 질문한 작업자가 결정 뒤에 남긴 기록·실행 이력을 찾는다
function decisionReflect(q, ans) {
  if (ans.pending) return { cls: 'user_test', text: '전달 대기 — 다음 동기화 때 작업자에게 갑니다' };
  const who = q._author, at = toMs(ans.ts) || 0;
  const t = topicById(q.task_id);
  if (!t) return { cls: 'neutral', text: '연결된 주제가 없어 반영 기록을 찾을 수 없습니다' };
  const run = (S.data.runs || []).find(r => r.agent === who && r.topic === t.id && toMs(r.started) >= at);
  const note = (t.notes || []).filter(n => n.by === who && toMs(n.ts) > at).at(-1);
  if (run && isRunning(run)) return { cls: 'progress', text: `${person(who).name}가 지금 반영 중 (${fmtRel(run.started)} 시작)` };
  if (note) return { cls: 'done', text: `반영됨 · ${fmtAbs(note.ts)} ${person(who).name} ${NOTE_KIND[note.kind] || note.kind}: ${String(note.body || '').slice(0, 90)}` };
  if (run) return { cls: run.result === 'fail' ? 'blocked' : 'done', text: `${person(who).name} 실행 ${RUN_RESULT[run.result] || run.result} · ${fmtRel(run.ended || run.started)}${run.summary ? ' · ' + run.summary.slice(0, 80) : ''}` };
  if (t.status === 'done') return { cls: 'done', text: '주제 완료' };
  return { cls: 'user_test', text: `아직 반영 전 — ${person(who).name} 실행기 차례 대기` };
}

// 허브 공지: 모든 PC 작업자에게 보낸 작업 방식 변경. 누가 확인했는지(대화 세션 확인 / 실행기 반영) 보인다
function noticesCard(agents) {
  const list = S.data.notices || [];
  if (!list.length) return null;
  const targets = n => agents.filter(a => (n.to || ['all']).includes('all') || (n.to || []).includes(a.id));
  return card('허브 공지', { big: list.length, unit: '건' },
    h('div', { class: 'list' }, list.slice(0, 3).map((n, i) => {
      const tg = targets(n), acked = tg.filter(a => (n.acks || {})[a.id]);
      return h('details', { class: 'notice' },
        h('summary', null, h('b', null, n.title), h('span', { class: `st ${acked.length === tg.length ? 'done' : 'user_test'}` }, `확인 ${acked.length}/${tg.length}`), h('span', { class: 'when' }, fmtRel(n.ts))),
        h('div', { class: 'notice-acks' }, tg.map(a => { const k = (n.acks || {})[a.id];
          return h('span', { class: `tag ${k ? '' : 'muted'}` }, av(a.id, true), `${a.pc_label} ${a.label || a.id}: `, k ? `${k.via === 'session' ? '확인' : '실행기 반영'} ${fmtRel(k.ts)}` : '미확인'); })),
        longText(n.body || ''));
    })));
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
    h('div', { class: 'pc-groups' }, groups.map(g => h('section', { class: `pc-group pc-${g.pc}` },
      h('div', { class: 'pc-head' }, h('h3', null, g.label || g.pc),
        h('span', { class: 'pc-role' }, (r.pcs?.[g.pc]?.['역할'] || '').split(/[.(]/)[0] || (g.role === 'hub' ? '허브 · 배분 담당' : '작업 노드')),
        g.error ? h('span', { class: 'st blocked' }, icon('alert'), g.error) : h('span', { class: 'pc-sync' }, `마지막 동기화 ${fmtRel(g.synced_at)}`)),
      g.list.length ? h('div', { class: 'agent-grid' }, g.list.map(agentCard)) : empty('이 PC의 작업자 정보가 없습니다.')))),
    h('div', { class: 'grid g-2 section-gap agents-foot' }, noticesCard(agents),
    h('details', { class: 'card rules-fold' }, h('summary', null, h('b', null, '자동 배분 규칙 · PC 연결 안내'), h('span', { class: 'hint' }, ' 펼쳐 보기')),
     h('div', { class: 'grid g-2', style: { 'margin-top': '12px' } },
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
        h('div', null, '작업자는 일을 시작할 때 ', h('span', { class: 'mono' }, 'node.py status'), '로 지금 하는 일을 알려야 이 화면에 보입니다.')))))),
  ];
}

// ------------------------------------------------------------ 주제
function vTopics() {
  const d = S.d, repo = S.data.meta.repo;
  const pending = (store.get('pendingTopics', []) || []).filter(p => !d.topics.some(t => t.id === p.id));
  store.set('pendingTopics', pending);
  const dropped = d.topics.filter(t => t.status === 'dropped');
  return [
    head('TOPICS', '주제 보드', `${d.topics.filter(t => !['dropped'].includes(t.status)).length}건`,
      h('button', { class: 'btn primary', onclick: openComposer }, icon('send'), '새 주제'),
      pending.length ? h('button', { class: 'btn', onclick: () => drawer('가져오기 대기', h('div', { class: 'list' }, pending.map(p => h('div', { class: 'item' },
        h('span', { class: 'lead-ico' }, icon('send')),
        h('div', { class: 'body' }, h('div', { class: 't' }, p.title), h('div', { class: 's' }, `${p.id} · ${fmtRel(p.created_at)} · PC가 가져가면 보드에 나타납니다`)),
        h('button', { class: 'icon-btn', title: '목록에서 지우기', 'aria-label': '목록에서 지우기', onclick: () => { store.set('pendingTopics', pending.filter(x => x.id !== p.id)); closeDrawer(true); render(); } }, icon('x')))))) }, icon('clock'), `가져오기 대기 ${pending.length}`) : null,
      dropped.length ? h('button', { class: 'btn', onclick: () => drawer('삭제한 주제', droppedCard()) }, icon('x'), `삭제한 주제 ${dropped.length}`) : null),
    h('div', { class: 'board topics fit-page' }, TOPIC_STATES.filter(s => !s.hidden).map(s => {
      const list = d.topics.filter(t => (t.status || 'new') === s.id).sort((a, b) => toMs(b.updated_at || b.created_at) - toMs(a.updated_at || a.created_at));
      return h('div', { class: 'col' }, h('div', { class: 'col-h' }, topicChip(s.id), h('span', { class: 'badge' }, list.length)),
        list.length ? list.map(topicCard) : h('div', { class: 'empty' }, '없음'));
    })),
  ];
}
// 새 주제 작성창(진행 현황·이전 주제 보드·바로가기 #/progress?new=1 공용). 입력용 창이라 뒤로/앞으로 때 되살리지 않는다(쓰던 글은 초안으로 남음)
function openComposer() { modal('새 주제', composerCard(S.data.meta.repo), topicFlowHint()); }
function topicFlowHint() {
  return h('ol', { class: 'hint steps' },
    h('li', null, h('b', null, '보내기'), ' — 주제를 적고 보내면 암호문만 GitHub 이슈로 올라갑니다.'),
    h('li', null, h('b', null, '분배'), ' — 서버컴 Astra가 목표·완료 기준을 정리하고 작업을 나눕니다.'),
    h('li', null, h('b', null, '진행'), ' — 작업자가 실행하고 Astra가 검수합니다. 아키텍트는 필요한 결정만 결재합니다.'));
}
function composerCard(repo) {
  const title = h('input', { id: 'tp-title', placeholder: '주제 (예: 거래소 검색 속도 개선)', maxlength: '120', required: true, 'data-draft': 'new-topic:title' });
  const body = h('textarea', { id: 'tp-body', placeholder: '대략적인 내용·배경·원하는 결과. 정리 안 된 메모여도 됩니다.', 'data-draft': 'new-topic:body' });
  const kind = h('select', { id: 'tp-kind', 'aria-label': '유형' }, ['기능·개선', '버그', '조사·분석', '디자인', '운영·도구', '기타'].map(k => h('option', null, k)));
  const pri = h('select', { id: 'tp-pri', 'aria-label': '우선순위' }, ['P2 보통', 'P1 높음', 'P0 긴급', 'P3 낮음'].map(k => h('option', { value: k.slice(0, 2) }, k)));
  // 담당은 서버컴 Astra가 정한다(예전 '담당 선호' 칸은 보내지 않던 값이라 뺐다)
  const start = h('select', { 'aria-label': '시작 시점', 'data-draft': 'new-topic:start', onchange: () => setSendLabel() }, h('option', {value:'later'}, '주제만 저장 · 나중에 시작'), h('option', {value:'now'}, '지금 시작 · Astra에게 맡기기'));
  const sendLabel = h('span');
  const setSendLabel = () => { sendLabel.textContent = start.value === 'now' ? '보내고 바로 시작' : '주제 저장(나중에 시작)'; };
  const status = h('div', { class: 'hint', role: 'status', 'aria-live': 'polite' });
  function make() {
    if (!title.value.trim()) { title.focus(); status.textContent = '주제를 적어주세요.'; return null; }
    const topic = { id: newId('T', 3), title: title.value.trim(), body: body.value.trim(), kind: kind.value, priority: pri.value, prefer: 'auto', backlog: start.value !== 'now', created_at: new Date().toISOString(), from: 'dashboard' };
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
  } }, icon('send'), sendLabel);
  setSendLabel();
  const copy = h('button', { class: 'btn', onclick: async () => {
    const r = make(); if (!r) return;
    try { await navigator.clipboard.writeText(`python topics.py add-blob ${await sealTopic(r.topic)}`); remember(r.topic); toast('복사했습니다. PC 터미널에 붙여넣으세요.'); S._keepScroll = true; render(); }
    catch { status.textContent = '클립보드 복사가 막혔습니다.'; }
  } }, icon('copy'), '암호문 복사 (PC용)');
  return card('주제 던지기', null,
    h('div', { class: 'composer' }, title, body, h('div', { class: 'row' }, kind, pri, start),
      h('div', { class: 'row' }, send, copy),
      !repo ? h('div', { class: 'callout warn' }, h('b', null, 'GitHub 저장소가 아직 연결되지 않았습니다. '), '연결 전에는 "암호문 복사"로 PC에서 넣을 수 있습니다.') : null,
      status, sendHint(),
      h('div', { class: 'hint' }, '내용은 이 브라우저에서 대시보드 비밀번호 키로 암호화됩니다. 이슈에는 암호문과 주제 번호만 남습니다.')));
}
function topicCard(t) {
  return h('button', { class: 'proj', onclick: () => openTopic(t) },
    h('div', { class: 'row' }, priChip(t.priority), t.kind ? h('span', { class: 'tag' }, t.kind) : null, t.linked_task_id ? h('span', { class: 'tag' }, '작업 연결') : null,
      (t.conflict || []).length ? h('span', { class: 'st blocked' }, icon('alert'), '중복 착수') : null,
      t.status === 'review_user' && t.gate && hoursSince(t.gate.opened_at) >= GATE_LATE_H ? h('span', { class: 'st blocked' }, '오래 대기') : null),
    h('div', { class: 'ttl clamp-2' }, t.title),
    phaseLine(t, true),
    t.status === 'review_user' && t.gate ? h('div', { class: 'gate-wait' }, waitText(t.gate.opened_at), ' · 결재함에서 결정') : null,
    h('div', { class: 'foot' }, t.assignee ? h('span', { class: 'wait' }, av(t.assignee, true), person(t.assignee).name) : h('span', { class: 'wait' }, '미배정'),
      t.turn ? h('span', { class: 'tag' }, `차례: ${person(t.turn).name}`) : null,
      (t.notes || []).length ? h('span', null, `메모 ${(t.notes || []).length}`) : null,
      h('span', { style: { 'margin-left': 'auto' } }, fmtRel(t.updated_at || t.created_at))));
}

// ------------------------------------------------------------ 업무
// 업무 보드 = 주제 진행 흐름(아키텍트 결정 2026-10-02). 칸 판정은 위에서 먼저 걸리는 칸 하나에만 넣는다.
const FLOW = [
  { id: 'user_test', label: '아키텍트 대기', icon: 'user' },
  { id: 'blocked', label: '막힘', icon: 'alert' },
  { id: 'validating', label: '검증', icon: 'eye' },
  { id: 'progress', label: '진행', icon: 'play' },
  { id: 'request', label: '요청', icon: 'inbox' },
];  // 완료는 '완료' 메뉴에서 본다(보드가 길어지지 않게)
const aiOfAgent = id => ((S.data.agents || []).find(a => a.id === id) || {}).ai || (/claude/.test(id || '') ? 'claude' : /astra|gpt/.test(id || '') ? 'gpt' : '');
const pcOfAgent = id => ((S.data.agents || []).find(a => a.id === id) || {}).pc || String(id || '').split('-')[0];
function topicFlow(t, asking) {
  if (t.status === 'done') return { col: 'done', why: [] };
  if (t.live_session && t.status !== 'review_user') return { col: 'user_test', why: ['실게임 수정 · 대화 세션'] };
  if (t.status === 'active' && t.stage === 'queue') return { col: 'user_test', why: ['배포 대기열'] };
  if (t.deploy_session && t.status !== 'review_user') return { col: 'user_test', why: [`배포 묶음 ${(t.deploy_batch || {}).id || ''} · 서버컴 대화`] };
  if (t.status === 'review_user' || (S.data.decisions_needed || []).some(q => q.task_id === t.id && !S.d.answers[q.id]) || asking.has(t.id)) return { col: 'user_test', why: t.gate ? [gateName(t.gate.n, t.gate.label)] : [] };
  const why = [];
  const run = runsFor(t.id)[0];
  if (run && run.result === 'fail') why.push('실행 실패');
  if ((t.conflict || []).length) why.push('중복 착수');
  if (t.assignee && lockOf(t.assignee)) why.push('담당 멈춤');
  if (t.status === 'active' && hoursSince(t.updated_at) > 24) why.push('24시간 멈춤');
  if (queueCode(t) === 'stalled') why.push('실행기 멈춤');
  if (why.length) return { col: 'blocked', why };
  if (t.turn && t.assignee && t.turn !== t.assignee) return { col: 'validating', why: [] };
  if (t.plan && t.turn === t.assignee && ['ready', 'active'].includes(t.status)) return { col: 'progress', why: [] };
  return { col: 'request', why: [] };
}
// 업무 보드와 개요 '진행 단계' 칸이 같은 기준으로 세도록 한곳에서 만든다(주제 흐름 + 옛 작업표)
function flowItems(f = 'all', pcF = 'all') {
  // 아키텍트에게 물은 AI 질문(내 차례와 같은 기준)이 걸린 주제
  const asking = new Set(myQueue().questions.map(x => x.topic.id));
  const passOwner = (ai, pc) => (f === 'all' || f === 'user' || (f === 'claude' && ai === 'claude') || (f === 'astra' && ai === 'gpt')) && (pcF === 'all' || pc === pcF);
  const items = [];
  for (const t of S.d.topics) {
    if (['backlog', 'parked', 'dropped'].includes(t.status)) continue;
    if (!passOwner(aiOfAgent(t.assignee), pcOfAgent(t.assignee))) continue;
    const fl = topicFlow(t, asking);
    items.push({ kind: 'topic', t, col: fl.col, why: fl.why, ts: t.updated_at || t.created_at });
  }
  for (const t of S.d.tasks) {  // 옛 작업표(업무 보드 시절 기록)
    const owner = LEGACY[t.owner] || t.owner;
    if (!passOwner(aiOfAgent(owner) || (t.owner === 'astra' ? 'gpt' : t.owner === 'claude' ? 'claude' : ''), pcOfAgent(owner) || 'dev')) continue;
    const col = t.stage === 'done' ? 'done' : t.stage === 'user_test' || t.waiting_on === 'user' ? 'user_test' : (t.stage === 'blocked' || t._stale) ? 'blocked' : t.stage;
    items.push({ kind: 'task', t, col: FLOW.some(x => x.id === col) ? col : 'progress', why: col === 'blocked' ? [t._stale ? `${Math.round(t._age)}시간 멈춤` : '막힘'] : [], ts: t.updated_at });
  }
  return items;
}
// ------------------------------------------------------------ 완료(아키텍트 요청 2026-10-03: 보드에서 빼고 기록으로만 본다)
const GATE_SHORT = { 4: '실게임 시험', 5: '배포본 결정', 7: '운영 반영 승인', 9: '완료 확정', 40: '결과 확인' };
function vDone(embedded) {
  const win = S.f.doneWin || '30d';
  const days = { '7d': 7, '30d': 30, all: 1e5 }[win];
  const doneAt = t => t.status_at || t.updated_at;
  const all = S.d.topics.filter(t => t.status === 'done' && !t.followed).sort((a, b) => toMs(doneAt(b)) - toMs(doneAt(a)));  // 후속으로 이어진 원래 주제는 줄기 끝 줄에
  const list = all.filter(t => Date.now() - toMs(doneAt(t)) <= days * 864e5);
  const oldTasks = S.d.tasks.filter(t => t.stage === 'done');
  const how = t => {
    const last = (t.gate_history || []).at(-1);
    if (!last) return '관문 이전 방식으로 완료';
    if (/^즉시 완료/.test(last.choice || '')) return `배포 없이 완료(${gateName(last.n, GATE_SHORT[last.n] || '관문')}에서 즉시 완료)`;
    return `${gateName(last.n, GATE_SHORT[last.n] || '관문')} · ${String(last.choice || '메모').replace(/\(.*\)/, '')}`;
  };
  const row = t => h('details', { class: 'done-row' },
    h('summary', null,
      h('span', { class: 'lead-ico good' }, icon('check')),
      h('span', { class: 'body' }, h('b', { class: 'clamp-1' }, t.chain ? chainTitle(t) : t.title),
        h('span', { class: 'meta' }, t.kind ? h('span', { class: 'tag' }, t.kind) : null, t.chain ? h('span', { class: 'tag' }, `줄기 ${t.chain.members.length}단계`) : null, h('span', null, how(t)),
          t.assignee ? h('span', { class: 'wait' }, av(t.assignee, true), person(t.live_from || t.assignee).name) : null)),
      h('span', { class: 'when', title: fmtAbs(doneAt(t)) }, fmtAbs(doneAt(t)))),
    h('div', { class: 'done-log' },
      t.chain ? chainBox(t) : null,
      (t.gate_history || []).length ? h('ol', null, chainGates(t).map(x => h('li', null, x._topic && x._topic !== t.id ? h('span', { class: 'tag' }, (topicById(x._topic) || {}).title || x._topic) : null,
        h('b', null, `★${x.n === 40 ? 4 : x.n} ${GATE_SHORT[x.n] || ''}`), ` · ${x.choice || '메모'}`, x.note ? h('span', { class: 'muted' }, ` — ${x.note}`) : null,
        h('span', { class: 'when' }, ` ${fmtAbs(x.answered_at)}`))))
        : h('div', { class: 'hint' }, '관문 기록이 없습니다(9단계 흐름 이전에 끝난 주제).'),
      h('button', { class: 'btn sm', onclick: () => openTopic(t) }, icon('topics'), '주제 전체 보기')));
  const winChips = chips([['7d', '7일'], ['30d', '30일'], ['all', '전체']], win, v => { S.f.doneWin = v; S._keepScroll = true; render(); }, '완료 기간');
  const body = h('div', { class: 'done-fit fit-page' },
      card('완료한 주제', { big: list.length, unit: '건', cls: 'fill scroll-card' },
        list.length ? h('div', { class: 'done-list' }, list.map(row)) : empty('이 기간에 완료한 주제가 없습니다.'),
        oldTasks.length ? h('details', { class: 'done-old' }, h('summary', null, `옛 작업표 완료 ${oldTasks.length}건`),
          h('div', { class: 'list' }, oldTasks.map(t => h('button', { class: 'item', onclick: () => openTask(t) },
            h('span', { class: 'body' }, h('div', { class: 't clamp-1' }, t.title), h('div', { class: 's' }, fmtAbs(t.updated_at))))))) : null));
  if (embedded) return { small: `완료 ${all.length}건 · 줄기 단위`, tools: winChips, body: [body] };
  return [head('DONE', '완료', `완료 ${all.length}건`, winChips), body];
}
// 보류 메뉴(아키텍트 2026-10-03): 보류한 주제를 따로 모아 보고, 필요할 때 '다시 진행'으로 꺼내 쓴다.
// 관문에서 보류했으면 그 ★ 관문이 내 차례에 다시 열리고, 진행 중에 보류했으면 진행 중으로 돌아가 AI가 이어서 한다
// 원래 주제 ↔ 후속 주제 연결(보고서 2번): 어디서 왔고 어디로 이어졌는지 오갈 수 있게
function linkBox(t) {
  if (!t) return null;
  const go_ = x => () => { const y = topicById(x.id); if (y) openTopic(y); };
  const st = x => (TOPIC[x.status] || {}).label || x.status || '';
  const rows = [];
  if (t.origin) rows.push(h('div', null, h('b', null, '원래 주제 ← '), h('button', { class: 'tag tag-btn', onclick: go_(t.origin) }, t.origin.title || t.origin.id), h('span', { class: 'muted' }, ` ${st(t.origin)}`)));
  for (const f of t.followup_topics || []) rows.push(h('div', null, h('b', null, '후속 주제 → '), h('button', { class: 'tag tag-btn', onclick: go_(f) }, f.title || f.id), h('span', { class: 'muted' }, ` ${st(f)}`)));
  if (!rows.length) return null;
  return h('div', { class: 'callout' }, rows, (t.followups || []).length && t.gate && t.gate.n === 40
    ? h('div', { class: 'hint' }, '후속 주제가 이미 있어 이 결과 확인에서는 새로 만들지 않습니다. 이 주제는 완료 확정하시면 됩니다.') : null);
}
function parkInfo(t) {
  const last = (t.gate_history || []).at(-1);
  const h_ = last && last.act === 'park' && !last.resumed_at ? last : null;  // 마지막 관문 답이 보류이고 아직 재개 안 됐을 때만 관문 보류
  if (h_) return { where: `${gateName(h_.n, GATE_SHORT[h_.n] || '관문')}에서 보류`, note: h_.note || '', at: h_.answered_at,
    back: `${gateName(h_.n, GATE_SHORT[h_.n] || '관문')}이 결재함에 다시 열립니다(메모는 기록에 남고, 관문은 직접 고르시면 됩니다)` };
  // 진행 중 보류의 메모: 보류 시각(status_at)까지의 기록 중 아키텍트 보류 결정 → 보류 언급 순으로
  const upto = (t.notes || []).filter(x => !t.status_at || toMs(x.ts) <= toMs(t.status_at) + 1000);
  const n = upto.filter(x => /^\[아키텍트 보류 결정\]/.test(x.body || '')).at(-1) || upto.filter(x => /보류/.test(x.body || '')).at(-1);
  return { where: '진행 중 보류', back_note: true, note: n ? String(n.body || '').replace(/^\[아키텍트 보류 결정\]\s*/, '') : '', at: t.status_at, back: '진행 중으로 돌아가 담당 AI가 바로 이어서 합니다(메모는 담당 AI에게 전달)' };
}
async function resumeTopic(t, note) {
  try {
    await sendOps('topic-resume', { topic: t.id, note: note || '' }, `보류 주제 다시 진행: ${t.title}`);
    toast('다시 진행합니다 · 다음 동기화 때 반영');
    S._keepScroll = true; render();
    return true;
  } catch (e) { toast(e.message); return false; }
}
function resumeControl(t) {
  const note = h('input', { placeholder: '다시 진행하며 전할 말(선택)', 'aria-label': '다시 진행 메모', maxlength: '1000', 'data-draft': `resume:${t.id}`, style: { flex: '1', 'min-width': '0' } });
  return h('div', { class: 'row' }, note, h('button', { class: 'btn primary', onclick: () => resumeTopic(t, note.value.trim()) }, icon('play'), '다시 진행'));
}
function parkedBox(t) {
  if (t._pendingResume) return h('div', { class: 'callout' }, h('b', null, '다시 진행 반영 대기 · '), '다음 동기화 때 보류가 풀립니다.');
  if (t.status !== 'parked' || t.archived) return null;  // 재시작 보관은 '다시 진행' 대상이 아니다(새 주제로 이어짐)
  const p = parkInfo(t);
  return h('div', { class: 'callout' }, h('div', null, h('b', null, `보류 중 · ${p.where}`), p.at ? ` (${fmtAbs(p.at)})` : '', p.note ? h('div', { class: 'muted' }, p.note) : null,
    h('div', { class: 'hint' }, `다시 진행하면 ${p.back}`)), resumeControl(t));
}
function vParked(embedded) {
  const at = t => parkInfo(t).at || t.status_at || t.updated_at;
  const list = S.d.topics.filter(t => (t.status === 'parked' && !t.archived) || t._pendingResume).sort((a, b) => toMs(at(b)) - toMs(at(a)));
  const row = t => {
    const p = parkInfo(t);
    return h('details', { class: 'done-row' },
      h('summary', null,
        h('span', { class: 'lead-ico' }, icon('pause')),
        h('span', { class: 'body' }, h('b', { class: 'clamp-1' }, t.chain ? chainTitle(t) : t.title),
          h('span', { class: 'meta' }, t.kind ? h('span', { class: 'tag' }, t.kind) : null, h('span', null, t._pendingResume ? '다시 진행 반영 대기' : p.where),
            t.assignee ? h('span', { class: 'wait' }, av(t.live_from || t.assignee, true), person(t.live_from || t.assignee).name) : null)),
        h('span', { class: 'when', title: fmtAbs(at(t)) }, fmtAbs(at(t)))),
      h('div', { class: 'done-log' },
        p.note ? h('div', { class: 'callout' }, h('b', null, '보류 메모: '), p.note) : null,
        t._pendingResume ? h('div', { class: 'hint' }, '다음 동기화 때 보류가 풀립니다.') : [h('div', { class: 'hint' }, `다시 진행하면 ${p.back}`), resumeControl(t)],
        h('button', { class: 'btn sm', onclick: () => openTopic(t) }, icon('topics'), '주제 전체 보기')));
  };
  const body = h('div', { class: 'done-fit fit-page' },
    card('보류한 주제', { big: list.length, unit: '건', cls: 'fill scroll-card' },
      list.length ? h('div', { class: 'done-list' }, list.map(row)) : empty('보류한 주제가 없습니다.')));
  if (embedded) return { small: `보류 ${list.length}건`, tools: null, body: [body] };
  return [head('PARKED', '보류', `보류 ${list.length}건`), body];
}
// 배포 대기열(아키텍트 2026-10-03): 서버컴 반영은 바로 하지 않는다. ★7 → 서버컴 배포 준비(자동) → 대기열 →
// 날을 잡아 배포 묶음(R-YYYYMMDD) → 서버컴 Astra 대화에서 배포 → 주제마다 ★9(묶음 단위로 한 번에 완료 확정)
const kstDay = (d = new Date()) => new Date(d.getTime() + 9 * 3600e3).toISOString().slice(0, 10);
const batchNo = day => `R-${String(day || '').replace(/-/g, '')}`;
function deployGroups() {
  const live = S.d.topics.filter(t => !['done', 'dropped', 'parked'].includes(t.status));
  const prep = live.filter(t => t.status === 'active' && t.stage === 'prep');
  const queue = live.filter(t => t.status === 'active' && t.stage === 'queue');
  const batches = {};
  for (const t of live) {
    const b = t.deploy_batch || (t.gate && t.gate.n === 9 && t.gate.batch ? { id: t.gate.batch } : null);
    if (!b || !(t.stage === 'deploy' || (t.gate && t.gate.n === 9))) continue;
    const g = batches[b.id] || (batches[b.id] = { id: b.id, date: b.date, note: b.note, topics: [] });
    g.date = g.date || b.date; g.note = g.note || b.note;
    g.topics.push(t);
  }
  return { prep, queue, batches: Object.values(batches).sort((a, b) => String(a.date || a.id).localeCompare(String(b.date || b.id))) };
}
function prepFiles(t) { return ((t.deploy_prep || {}).files || []); }
function conflictTags(t) {
  return (t.deploy_conflicts || []).map(c => { const y = topicById(c.id); return h('button', { class: 'tag tag-btn st blocked', onclick: e => { e.stopPropagation(); if (y) openTopic(y); }, title: (c.files || []).join(', ') || '배포 준비에서 겹침으로 적음' },
    `겹침: ${y ? y.title : c.id}${(c.files || []).length ? ` (${c.files.slice(0, 2).join(', ')}${c.files.length > 2 ? ' 외' : ''})` : ''}`); });
}
function deployBatchText(b) {
  const lines = b.topics.map(t => {
    const p = t.deploy_prep || {};
    const w = t.work_id ? (S.data.works || {})[t.work_id] : null;
    return `- ${t.id} "${t.title}"${t.gate && t.gate.n === 9 ? ' (배포 끝남 · ★9 대기)' : ''}\n  대상 파일: ${prepFiles(t).join(', ') || '(준비 요약 확인)'}` +
      `${(t.deploy_conflicts || []).length ? `\n  겹침: ${t.deploy_conflicts.map(c => c.id + ((c.files || []).length ? `(${c.files.join(', ')})` : '')).join(', ')}` : ''}` +
      `${w ? `\n  작업물: ${w.url}` : ''}\n  배포 준비 요약: ${String(p.summary || '').split('\n').slice(0, 6).join(' / ').slice(0, 500)}`;
  });
  return `배포 묶음 ${b.id} — 배포 날짜 ${b.date || '미정'}${b.note ? ` (${b.note})` : ''} · 주제 ${b.topics.length}개\n` +
    `이 대화에서 아키텍트와 함께 실서버 diff·패치를 검토하고 배포합니다(서버컴 Astra). 운영 서버 적용·재시작·DB 변경은 이 대화에서 아키텍트가 그 자리에서 승인한 것만 합니다.\n` +
    `1) 대시보드 도구 폴더(node.py가 있는 곳)에서 주제마다 python node.py brief <주제ID> 로 배포본·배포 준비 문서(DEPLOY-PREP.md, 실서버 diff)를 불러오세요.\n` +
    `2) 지금 운영본이 배포 준비 때와 같은지 다시 확인하고(해시), 겹치는 파일은 합친 diff를 보여 주세요. 적용 순서·백업·되돌리기 절차를 아키텍트와 확정합니다.\n` +
    `3) 백업 → 적용 → 재시작(필요할 때만) → 적용 후 확인 항목을 차례로 진행하고 결과를 보여 주세요.\n` +
    `4) 주제마다 결과를 남깁니다: python node.py state <주제ID> --agent server-astra --status done --note "배포 완료(묶음 ${b.id}, 시각, 확인 결과)" ` +
    `또는 실패하면 --note "배포 실패·되돌림(이유, 되돌린 방법·확인)". 그러면 주제마다 ★9가 열리고, 아키텍트가 배포 대기열 메뉴에서 묶음 단위로 완료 확정합니다.\n\n주제:\n` + lines.join('\n');
}
async function batchOp(op, batch, ids, extra = {}) {
  try {
    await sendOps('deploy-batch', { op, batch, topics: ids, ...extra }, `배포 묶음 ${batch}: ${op === 'add' ? '넣기' : op === 'remove' ? '빼기' : '날짜'} ${ids.length}건`);
    toast('보냈습니다 · 다음 동기화(1~2분) 때 반영');
    S._keepScroll = true; render();
  } catch (e) { toast(e.message); }
}
function openBatchMaker(queue, preset, exclude) {
  const on = new Set(preset || queue.map(t => t.id));
  const day = h('input', { type: 'date', value: kstDay(new Date(Date.now() + 86400e3)), 'aria-label': '배포 날짜' });
  const no = h('input', { value: '', placeholder: '묶음 번호(비우면 날짜로)', 'aria-label': '묶음 번호', maxlength: '20' });
  const note = h('input', { placeholder: '메모(선택) — 예: 주말 점검 때', 'aria-label': '묶음 메모', maxlength: '1000', style: { flex: '1', 'min-width': '0' } });
  const box = h('div');
  const draw = () => {
    const picked = queue.filter(t => on.has(t.id));
    const clash = picked.filter(t => (t.deploy_conflicts || []).some(c => on.has(c.id)));
    box.replaceChildren(
      h('p', { class: 'hint' }, '이번 배포에 넣을 항목을 고르고 날짜를 정하세요. 묶음에 넣으면 그 주제들은 서버컴 Astra 대화 배포 단계가 됩니다(자동 실행기는 손대지 않음).'),
      h('div', { class: 'row' }, h('label', null, '배포 날짜 ', day), no),
      h('div', { class: 'opt-list' }, queue.map(t => h('label', { class: 'opt' }, h('input', { type: 'checkbox', checked: on.has(t.id) ? true : null, onchange: e => { e.target.checked ? on.add(t.id) : on.delete(t.id); draw(); } }),
        h('span', null, t.title, h('span', { class: 'opt-hint' }, `대상 파일 ${prepFiles(t).length}개${(t.deploy_conflicts || []).length ? ' · 겹침 있음' : ''}`))))),
      clash.length ? h('div', { class: 'callout' }, h('b', null, '같은 파일을 고치는 항목이 함께 들어갑니다: '), clash.map(t => t.title).join(', '), h('div', { class: 'hint' }, '서버컴 Astra 대화에서 합친 diff로 순서를 정하면 됩니다. 따로 하려면 체크를 빼세요.')) : null,
      h('div', { class: 'row', style: { 'margin-top': '10px' } }, note, h('button', { class: 'btn primary', disabled: picked.length && day.value ? null : true, onclick: async e => {
        const b = (no.value.trim() || batchNo(day.value));
        if (!/^R-\d{8}(-[0-9a-z]{1,8})?$/.test(b)) { toast('묶음 번호 형식: R-YYYYMMDD 또는 R-YYYYMMDD-2'); return; }
        if (exclude && b === exclude) { toast(`지금 묶음(${exclude})과 같은 번호입니다. 다른 날짜를 고르세요.`); return; }
        e.currentTarget.disabled = true;
        closeDrawer();
        await batchOp('add', b, picked.map(t => t.id), { date: day.value, note: note.value.trim() });
      } }, icon('calendar'), `${picked.length}건으로 배포 묶음 만들기`)));
  };
  draw();
  modal('배포 묶음 만들기', box);
}
function confirmBatch9(b) {
  const g9 = b.topics.filter(t => t.status === 'review_user' && t.gate && t.gate.n === 9 && !S.d.answers[t.gate.id]);
  if (!g9.length) return;
  const box = h('div', null,
    h('p', { class: 'hint' }, `묶음 ${b.id}에서 배포가 끝나 ★9 완료 확정을 기다리는 ${g9.length}건입니다. 서버컴 Astra가 남긴 배포 결과를 확인하고 한 번에 확정하세요. 실패한 항목은 체크를 빼고 주제에서 따로 고르시면 됩니다.`));
  const on = new Set(g9.filter(t => !/실패|되돌림/.test(t.gate.summary || '')).map(t => t.id));
  const list = h('div', { class: 'opt-list' }, g9.map(t => h('label', { class: 'opt' }, h('input', { type: 'checkbox', checked: on.has(t.id) ? true : null, onchange: e => { e.target.checked ? on.add(t.id) : on.delete(t.id); } }),
    h('span', null, t.title, h('span', { class: 'opt-hint' }, (String(t.gate.summary || '').split('\n').find(Boolean) || '(배포 결과 요약 없음)').slice(0, 160))))));
  box.append(list, h('div', { class: 'row', style: { 'margin-top': '10px' } }, h('button', { class: 'btn primary', onclick: async e => {
    // 보낼 때 다시 확인: 이미 답을 보낸 ★9는 빼고(연타·다른 창에서 보낸 것), 버튼은 한 번만
    const pick = g9.filter(t => on.has(t.id) && !S.d.answers[t.gate.id]);
    if (!pick.length) { toast('이미 보낸 완료 확정입니다'); closeDrawer(); return; }
    e.currentTarget.disabled = true;
    closeDrawer();
    try {
      for (const t of pick) await sendOps('decide', { decision_id: t.gate.id, choice: '완료 확정', note: `배포 묶음 ${b.id} 일괄 완료 확정` }, `★9 완료 확정: ${t.title}`);
      toast(`${pick.length}건 완료 확정을 보냈습니다 · 다음 동기화 때 반영`);
    } catch (e) { toast(e.message); }
    S._keepScroll = true; render();
  } }, icon('check'), '고른 항목 완료 확정')));
  modal(`★9 묶음 완료 확정 · ${b.id}`, box);
}
function vDeploy() {
  const { prep, queue, batches } = deployGroups();
  const pend = pending.all().filter(p => p.type === 'deploy-batch');
  const row = (t, tools) => h('div', { class: 'item' },
    h('span', { class: 'body' }, h('button', { class: 'link-btn', onclick: () => openTopic(t) }, h('b', { class: 'clamp-1' }, t.title)),
      h('div', { class: 'meta' }, prepFiles(t).length ? h('span', { class: 'muted' }, `대상 파일 ${prepFiles(t).slice(0, 3).join(', ')}${prepFiles(t).length > 3 ? ` 외 ${prepFiles(t).length - 3}개` : ''}`) : null,
        conflictTags(t), t.gate && t.gate.n === 9 ? h('span', { class: 'st user_test' }, S.d.answers[t.gate.id] ? '★9 답함 · 반영 대기' : '배포 끝남 · ★9 대기') : null)),
    tools || null);
  const queueCard = card('배포 준비 완료 — 대기열', { big: queue.length, unit: '건', cls: 'scroll-card' },
    queue.length ? [h('div', { class: 'row' }, h('button', { class: 'btn primary', onclick: () => openBatchMaker(queue) }, icon('calendar'), '배포 묶음 만들기')),
      h('div', { class: 'list' }, queue.map(t => row(t, h('button', { class: 'btn sm', onclick: () => openBatchMaker(queue, [t.id]) }, '이 항목만 묶기'))))]
      : empty('배포 준비가 끝난 항목이 없습니다. ★7에서 "배포 대기열에 넣기"를 고르면 서버컴이 준비해 여기로 옵니다.'));
  const prepCard = card('배포 준비 중(서버컴 자동)', { big: prep.length, unit: '건', cls: 'scroll-card' },
    prep.length ? h('div', { class: 'list' }, prep.map(t => row(t, h('span', { class: 'muted' }, `${person(t.stage_owner || 'server-astra').name} 준비 중`)))) : empty('없음'));
  const batchCards = batches.map(b => {
    const g9 = b.topics.filter(t => t.status === 'review_user' && t.gate && t.gate.n === 9 && !S.d.answers[t.gate.id]);
    const dep = b.topics.filter(t => t.stage === 'deploy' && t.status === 'active');
    const next = batches.find(x => x.id !== b.id && String(x.date || x.id) > String(b.date || b.id));
    return card(`배포 묶음 ${b.id}`, { big: b.topics.length, unit: '건', cls: 'scroll-card' },
      h('div', { class: 'row' }, h('span', null, `배포 날짜 ${b.date || '미정'}`), b.note ? h('span', { class: 'muted' }, b.note) : null,
        h('button', { class: 'btn primary sm', style: { 'margin-left': 'auto' }, onclick: async () => {
          const text = deployBatchText(b);
          try { await navigator.clipboard.writeText(text); toast('서버컴 Astra 대화 시작 문구를 복사했습니다. 서버컴 Astra 대화에 붙여 넣으세요.'); } catch { modal('서버컴 Astra 대화 시작 문구', h('pre', { class: 'pre' }, text)); }
        } }, icon('copy'), '서버컴 Astra 대화 시작 문구 복사'),
        g9.length ? h('button', { class: 'btn sm', onclick: () => confirmBatch9(b) }, icon('check'), `★9 묶음 완료 확정 ${g9.length}건`) : null),
      h('div', { class: 'list' }, b.topics.map(t => row(t, t.stage === 'deploy' && t.status === 'active' ? h('div', { class: 'row' },
        h('button', { class: 'btn sm', onclick: () => batchOp('remove', b.id, [t.id], { note: '묶음에서 뺌(대기열로)' }) }, '빼기(대기열로)'),
        h('button', { class: 'btn sm', onclick: () => next ? batchOp('add', next.id, [t.id], { note: `${b.id}에서 미룸` }) : openBatchMaker([t], [t.id], b.id) }, next ? `다음 묶음(${next.id})으로` : '다른 날로 미루기')) : null))),
      dep.length ? h('p', { class: 'hint' }, `배포 중 ${dep.length}건 — 서버컴 Astra 대화에서 배포하고 주제마다 결과를 남기면 ★9로 옵니다(실패·되돌림도 ★9에서 다시 대기열로).`) : null);
  });
  return [
    head('DEPLOY', '배포 대기열', `준비 중 ${prep.length} · 대기 ${queue.length} · 묶음 ${batches.length}`),
    pend.length ? h('div', { class: 'callout' }, `보낸 묶음 조작 ${pend.length}건 — 다음 동기화(1~2분) 때 반영됩니다.`) : null,
    h('div', { class: 'grid2' }, queueCard, prepCard),
    batchCards.length ? h('div', { class: 'grid2' }, batchCards) : null,
    h('p', { class: 'hint fit-hint' }, '묶음을 만든 뒤 "서버컴 Astra 대화 시작 문구 복사"를 눌러 서버컴 Astra 대화에 붙여 넣으세요. 운영 반영은 그 대화에서 승인한 것만 합니다.'),
  ];
}
function vTasks() {
  const f = S.f.taskOwner || 'all', pcF = S.f.taskPc || 'all';
  const items = flowItems(f, pcF);
  const staleKeys = S.d.missed.filter(i => i.key.startsWith('stale:') && !S.acks.has(i.key) && !S.serverAcks.has(i.key)).map(i => i.key);
  const card = it => {
    const t = it.t, who = it.kind === 'topic' ? t.assignee : (LEGACY[t.owner] || t.owner);
    const ag = (S.data.agents || []).find(a => a.id === who);
    return h('button', { class: `proj flow-card${ag ? ' pc-' + ag.pc : ''}`, onclick: () => it.kind === 'topic' ? openTopic(t) : openTask(t) },
      h('div', { class: 'row' }, priChip(t.priority), it.kind === 'task' ? h('span', { class: 'tag' }, '옛 작업표') : null,
        it.why.map(w => h('span', { class: 'st blocked' }, w))),
      h('div', { class: 'ttl clamp-2' }, t.title),
      it.kind === 'topic' && t.chain && t.chain.root !== t.id ? h('div', { class: 'muted clamp-1', style: { 'font-size': '12px' } }, `원래 주제: ${(topicById(t.chain.root) || {}).title || t.chain.root}`) : null,
      h('div', { class: 'foot' }, ag ? h('span', { class: 'pc-chip' }, ag.pc_label) : null, h('span', { class: 'wait' }, av(who || 'user', true), person(who || 'user').name),
        it.kind === 'topic' && t.turn && t.turn !== t.assignee ? h('span', { class: 'tag' }, `차례: ${person(t.turn).name}`) : null,
        h('span', { style: { 'margin-left': 'auto' } }, fmtRel(it.ts))));
  };
  const total = items.filter(i => i.col !== 'done').length;
  return [
    head('TASKS', '업무 보드', `진행 흐름 · 진행 중 ${total}건`,
      chips([['all', '전체'], ['claude', 'Claude'], ['astra', 'Astra'], ['user', '나 대기']], f, v => { S.f.taskOwner = v; render(); }, '담당 필터'),
      chips([['all', '모든 PC'], ['dev', '개발컴'], ['server', '서버컴']], pcF, v => { S.f.taskPc = v; render(); }, 'PC 필터'),
      staleKeys.length ? h('button', { class: 'btn', onclick: () => ack(staleKeys) }, icon('check'), `멈춤 알림 ${staleKeys.length}건 끄기`) : null),
    h('div', { class: 'board flow fit-page' }, FLOW.map(c => {
      const list = items.filter(i => i.col === c.id).sort((x, y) => toMs(y.ts) - toMs(x.ts));
      return h('div', { class: 'col', style: f === 'user' && c.id !== 'user_test' ? { opacity: '.45' } : null },
        h('div', { class: 'col-h' }, h('span', { style: { color: `var(--st-${c.id})`, display: 'grid' } }, icon(c.icon)), c.label, h('span', { class: 'badge' }, list.length)),
        list.length ? list.map(card) : h('div', { class: 'empty' }, '없음'));
    })),
    h('p', { class: 'hint fit-hint' }, '주제 진행 흐름입니다(미처리·보류·삭제는 주제 화면에서). 누르면 상세가 열립니다. "옛 작업표"는 예전 업무 기록입니다.'),
  ];
}

// ------------------------------------------------------------ 메시지
function vMessages() {
  const all = S.data.messages;
  const f = S.f.msg;
  const filt = {
    all: () => true, a2c: m => m.sender === 'astra', c2a: m => m.sender === 'claude',
    unprocessed: m => S.d.unprocessed.includes(m), unanswered: m => S.d.unanswered.includes(m), auto: m => m.auto,
  }[f] || (() => true);
  const unp = S.d.unprocessed;
  const list = all.filter(filt).slice(0, 300);
  if (!S.msgSel || !list.includes(S.msgSel)) S.msgSel = list[0] || null;
  const narrow = matchMedia('(max-width: 880px)').matches;
  return [
    head('MESSAGES', 'Claude ↔ Astra', `${all.length}건`,
      chips([['all', '전체'], ['a2c', 'Astra→Claude'], ['c2a', 'Claude→Astra'], ['unprocessed', `미처리 ${unp.length}`], ['unanswered', `답장 대기 ${S.d.unanswered.length}`], ['auto', `자동 알림·사본 ${all.filter(m => m.auto).length}`]], f, v => { S.f.msg = v; S.msgSel = null; render(); }, '메시지 필터'),
      unp.length ? h('button', { class: 'btn primary', onclick: () => ackMessages(unp.map(m => m.id)) }, icon('check'), `미처리 ${unp.length}건 모두 확인 처리`) : null),
    h('p', { class: 'hint', style: { margin: '-6px 0 12px' } }, '여기는 AI 사이 기록입니다. 아키텍트가 답하거나 확인할 것은 "결재함"에 모입니다. ',
      '아키텍트 결정·답의 사본과 대시보드 자동 알림은 "미처리"에서 빠지고, 작업자가 반영하면 수신함에서 자동으로 정리됩니다.'),
    h('div', { class: 'split fit-page' },
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
    h('div', { class: 'grid wide-2 fit-page' },
    card('QA 검증 결과', { big: data.validations.length, unit: '건', cls: 'scroll-card fill' },
      data.validations.length ? h('div', { class: 'tbl-wrap' }, h('table', { class: 'tbl' },
        h('thead', null, h('tr', null, ['시각', '결과', '검증', '검토자', '실게임', '원인'].map(x => h('th', null, x)))),
        h('tbody', null, data.validations.map(v => h('tr', { class: 'click', tabindex: '0', onclick: () => openValidation(v), onkeydown: e => e.key === 'Enter' && openValidation(v) },
          h('td', { class: 'num', style: { 'white-space': 'nowrap' } }, fmtAbs(v.ts)),
          h('td', null, h('span', { class: `st ${v.result === 'pass' ? 'done' : v.result === 'fail' ? 'blocked' : 'neutral'}` }, icon(v.result === 'fail' ? 'alert' : 'done'), v.result === 'pass' ? '통과' : v.result === 'fail' ? '실패' : '불명')),
          h('td', null, h('b', null, v.id), h('div', { class: 'muted mono' }, v.job || '')),
          h('td', null, v.reviewer || '—'),
          h('td', null, v.live === 'pending' ? h('span', { class: 'st user_test' }, icon('flask'), '미실행') : '—'),
          h('td', null, v.root_cause || '—')))))) : empty('QA 결과가 없습니다.')),
    card('감사 원장', { big: ledger.length, unit: '건', cls: 'scroll-card fill',
      right: chips([['all', '전체'], ['pending', `대기 ${counts.pending}`], ['fail', `실패 ${counts.fail}`], ['reverted', `되돌림 ${counts.reverted}`], ['pass', `통과 ${counts.pass}`]], f, v => { S.f.ledger = v; render(); }, '원장 필터') },
      h('div', { class: 'list' }, ledger.map(e => h('button', { class: 'item', onclick: () => openLedger(e) },
        h('span', { class: `lead-ico ${e.status === 'fail' || e.status === 'reverted' ? 'bad' : e.status === 'pending' ? 'warn' : e.status === 'pass' ? 'good' : ''}` }, icon(LEDGER_ST[e.status].icon)),
        h('span', { class: 'body' }, h('div', { class: 't clamp-1' }, e.title), h('div', { class: 's clamp-1' }, e.body.replace(/^.*?\n/, '').slice(0, 200) || e.body.slice(0, 200))),
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
    oninput: e => { clearTimeout(S._qt); S._qt = setTimeout(() => { S.q = e.target.value; replaceScreen(routeUrl('brain')); render(); const i = $('.searchbox input'); if (i) { i.focus(); i.setSelectionRange(i.value.length, i.value.length); } }, 180); } });
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
    results ? h('div', { class: 'section-gap fit-page' }, card('검색 결과', { big: results.length, unit: '건', cls: 'fill' },
      results.length ? h('div', { class: 'list' }, results.map(r => h('button', { class: 'item', onclick: r.open },
        h('span', { class: 'tag', style: { 'margin-top': '2px' } }, r.kind),
        h('span', { class: 'body' }, h('div', { class: 't' }, highlight(r.title, terms)), h('div', { class: 's' }, highlight(snippet(r.text, terms), terms))),
        h('span', { class: 'when' }, fmtAbs(r.when, true))))) : empty('일치하는 기록이 없습니다.'))) : null,
    results ? null : h('div', { class: 'grid g-2 section-gap fit-page' },
      card('결정 기록', { big: S.data.decisions.length, unit: '건', cls: 'fill' },
        h('div', { class: 'list' }, [...S.data.decisions].sort((a, b) => toMs(b.date) - toMs(a.date)).map(x => h('button', { class: 'item', onclick: () => openDecision(x) },
          h('span', { class: 'tag', style: { 'margin-top': '2px' } }, fmtAbs(x.date, true)),
          h('span', { class: 'body' }, h('div', { class: 't clamp-1' }, x.title), h('div', { class: 's clamp-1' }, x.decision)),
          h('span', { class: 'wait' }, av(x.by, true), person(x.by).name))))),
      card('Claude 메모리', { big: S.data.memory.length, unit: '건', cls: 'fill' },
        h('div', { class: 'list' }, S.data.memory.map(m => h('button', { class: 'item', onclick: () => openMemory(m) },
          h('span', { class: 'tag', style: { 'margin-top': '2px' } }, ({ feedback: '지침', project: '프로젝트', user: '사용자', reference: '참조' })[m.type] || m.type),
          h('span', { class: 'body' }, h('div', { class: 't clamp-1' }, m.id), h('div', { class: 's clamp-1' }, m.description)),
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
    head('SOURCES', '연결과 설정', null,
      !matchMedia('(display-mode: standalone)').matches && !navigator.standalone
        ? h('button', { class: 'btn', onclick: installApp, title: '주소창 없이 앱처럼 열기' }, icon('install'), '앱으로 설치') : null),
    h('div', { class: 'src-fit fit-page' }, tokenCard(),
      card('보낸 요청 · 반영 대기', { big: pend.length, unit: '건', cls: 'fill' },
        pend.length ? h('div', { class: 'list' }, [...pend].reverse().map(p => h('div', { class: 'item' },
          h('span', { class: 'lead-ico' }, icon(p.type === 'reply' ? 'messages' : p.type === 'decide' ? 'scale' : p.type === 'task-state' ? 'tasks' : 'check')),
          h('div', { class: 'body' }, h('div', { class: 't' }, p.summary || p.type), h('div', { class: 's' }, `${fmtRel(p.created_at)} · ${p.via === 'api' ? '바로 전송됨' : p.via === 'queued' ? (outbox.all().some(x => x.action.id === p.id && x.manual) ? '보내지 못함 — 직접 보내기 필요' : '10초 뒤 전송 대기') : 'GitHub 창으로 보냄(Submit 필요)'} · PC 동기화 후 사라짐`)),
          h('button', { class: 'icon-btn', title: '목록에서 지우기', 'aria-label': '목록에서 지우기', onclick: () => { cancelQueued(p.id, true); pending.remove(p.id); S.d = derive(S.data); render(); } }, icon('x')))))
          : empty('대기 중인 요청이 없습니다.'),
        h('p', { class: 'hint' }, 'PC가 GitHub에서 요청을 가져와 처리하면 자동으로 목록에서 빠집니다. GitHub 창에서 Submit을 안 눌렀다면 여기서 지우고 다시 보내면 됩니다.')),
    card('수집 상태', { big: data.sources.length, unit: '곳', cls: 'fill src-table' }, h('div', { class: 'tbl-wrap' }, h('table', { class: 'tbl' },
      h('thead', null, h('tr', null, ['상태', '출처', '건수', '최근 변경', '경로·메모'].map(x => h('th', null, x)))),
      h('tbody', null, data.sources.map(s => {
        const stale = s.last_modified && hoursSince(s.last_modified) > 48, optional = /선택/.test(s.error || '');
        return h('tr', null,
          h('td', null, h('span', { class: `st ${!s.ok ? (optional ? 'neutral' : 'blocked') : stale ? 'user_test' : 'done'}` }, icon(!s.ok ? 'alert' : stale ? 'clock' : 'done'), !s.ok ? (optional ? '없음' : '오류') : stale ? '오래됨' : '정상')),
          h('td', null, h('b', null, s.name)),
          h('td', { class: 'num' }, s.count),
          h('td', { class: 'num', style: { 'white-space': 'nowrap' } }, s.last_modified ? fmtAbs(s.last_modified) : '—'),
          h('td', null, h('div', { class: 'mono muted clamp-1' }, s.path), s.error ? h('div', { class: 'clamp-1', style: { color: optional ? 'var(--ink-3)' : 'var(--st-blocked)' } }, s.error) : null, s.note ? h('div', { class: 'muted clamp-1' }, s.note) : null));
      })))),
      card('생성 정보', { cls: 'fill' }, h('dl', { class: 'fields' },
        h('dt', null, '생성 시각'), h('dd', null, fmtAbs(m.generated_at) + ' · ' + fmtRel(m.generated_at)),
        h('dt', null, '게시 시각'), h('dd', null, fmtAbs(S.env.published_at)),
        h('dt', null, '사령탑'), h('dd', null, m.coordination?.lead || '—'),
        h('dt', null, 'Astra 역할'), h('dd', null, m.coordination?.astra_role || '—'),
        h('dt', null, '작업표 기록자'), h('dd', null, m.coordination?.writer || '—'),
        h('dt', null, '가린 정보'), h('dd', null, Object.entries(m.masked || {}).map(([k, v]) => `${({ ip: '공인 IP', email: '이메일', secret: '비밀값', token: '토큰' })[k] || k} ${v}`).join(' · ')),
        h('dt', null, '기록 충돌'), h('dd', null, (m.conflicts || []).length ? m.conflicts.map(c => c.id).join(', ') : '없음'),
        h('dt', null, '보드에서 뺀 작업'), h('dd', null, (m.hidden_tasks || []).length ? m.hidden_tasks.map(t => `${t.title || t.id}`).join(', ') : '없음'),
        h('dt', null, '저장소'), h('dd', null, m.repo || '미연결'))),
      card('갱신과 협업', { cls: 'fill' }, h('div', { class: 'hint', style: { display: 'grid', gap: '8px' } },
        h('div', null, h('b', null, '갱신: '), '자동 동기화를 켜두면 PC가 10분마다 보낸 요청을 가져와 처리하고 바뀐 내용만 게시합니다(수동: ', h('span', { class: 'mono' }, 'publish.ps1'), '). 이 화면은 5분마다 새 게시본을 확인합니다.'),
        h('div', null, h('b', null, '화면에서 보낸 것: '), '답은 Claude/Astra 수신함으로, 일괄 확인은 inbox-claude → done 이동으로, 단계 변경은 작업표 덮어쓰기로 처리됩니다(사용자 기록 파일 data/user.json).'),
        h('div', null, h('b', null, 'Claude: '), h('span', { class: 'mono' }, 'data/claude.json'), ', ', h('span', { class: 'mono' }, 'topics/<id>/claude.json'), '에만 씁니다.'),
        h('div', null, h('b', null, 'Astra: '), h('span', { class: 'mono' }, 'data/astra.json'), ', ', h('span', { class: 'mono' }, 'topics/<id>/astra.json'), '에만 씁니다.'),
        h('div', null, h('b', null, '자동 수집: '), 'tasks.json · inbox-claude · inbox-astra · qa · handoffs · 감사 원장 · Claude 메모리.'))))),
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
  const ta = h('textarea', { placeholder: opts.placeholder || '여기에 의견을 적으면 서버컴 Astra에게 전달됩니다', rows: '3', 'aria-label': '답 입력', 'data-draft': `reply:${target.kind}:${target.id}`, 'data-kb-reply': '1' });
  const to = h('select', { 'aria-label': '받는 사람' }, (S.data.agents || []).length
    ? agentOptions(LEGACY[opts.to] || opts.to || 'server-astra').map(o => { o.textContent += '에게'; return o; })
    : [h('option', { value: 'dev-claude' }, 'Claude에게'), h('option', { value: 'dev-astra' }, 'Astra에게')]);
  if (opts.to) to.value = LEGACY[opts.to] || opts.to;
  // 키보드(내 차례)에서도 같은 보내기를 쓴다: 성공하면 true
  ta._send = async (opt = {}) => {
    const body = ta.value.trim();
    if (!body) { ta.focus(); return false; }
    send.disabled = true;
    try {
      await sendOps('reply', { target: { kind: target.kind, id: target.id, title: (target.title || '').slice(0, 200) }, to: to.value, body }, `답 → ${person(to.value).name}`);
      ta.value = ''; clearDraft(`reply:${target.kind}:${target.id}`);
      if (!opt.quiet) { render(); if (redraw) redraw(); }
      return true;
    } catch (e) { toast(e.message); return false; } finally { send.disabled = false; }
  };
  const send = h('button', { class: 'btn primary', 'data-kb-send': '1', onclick: () => ta._send() }, icon('send'), '보내기', kbd('Ctrl+Enter'));
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
  if (S.d.answers[q.id]) { toast('이미 보낸 결정입니다'); return false; }  // 되살아난 창·연타로 같은 결정을 두 번 보내지 않게
  try {
    await sendOps('decide', { decision_id: q.id, choice, note: note || '' }, `결정: ${choice || '메모'}`, { undo: q.kind !== 'stall' });
    clearDraft(`decide:${q.id}`);
    // 멈춤 결정의 화면 쪽 처리: 담당 바꾸기는 담당 지정도 보내고, 대화로 처리는 대화 시작 문구를 띄운다
    if (q.kind === 'stall') {
      const to = (String(choice || '').match(/^담당 바꾸기 → .*\(([a-z0-9-]+)\)$/) || [])[1];
      if (to) await sendOps('assign', { topic: q.task_id, agent: to, note: '멈춤 결정에서 담당 바꾸기' }, `주제 담당 → ${person(to).name}`);
      if (/^개발컴 Claude 대화로 처리/.test(choice || '')) { const t = topicById(q.task_id); if (t) setTimeout(() => openChatStarter(t), 50); }
    }
    const next = chainNextGate(q, choice);
    if (next) { S.mineSel = `d:${next}`; S.kbChained = S.mineSel; toast('★5 배포본 결정이 바로 이어집니다'); }
    render(); if (redraw) redraw();
    return true;
  } catch (e) { toast(e.message); return false; }
}
// ★4 통과 직후: 같은 주제의 ★5(배포본 결정)를 바로 띄워 이어서 답하게 한다.
// 번호는 허브와 같은 규칙(G4-… → G5-…)이라 허브 게시 전에 답해도 그대로 반영된다. 허브 게시본에 생기면 임시본은 지운다
function chainNextGate(q, choice) {
  if (!q || q.kind !== 'gate' || !/^G4-/.test(q.id) || !/^통과/.test(choice || '')) return null;
  if (topicById(q.task_id)?.command_mode) return;
  const id = 'G5-' + q.id.slice(3);
  const list = S.data.decisions_needed || (S.data.decisions_needed = []);
  if (!list.some(x => x.id === id)) {
    const title = (topicById(q.task_id) || {}).title || q.task_id;
    const body = (q.question || '').replace(/^\[[^\]]*\][^\n]*\n*/, '');
    const nq = { id, kind: 'gate', gate: 5, owner: 'user', task_id: q.task_id, since: new Date().toISOString(), _author: q._author, _local: true,
      question: `[5/9 배포본 결정] ${title}\n\n${body}`, options: ['배포본 만들기', '보류', '수정', '즉시 완료 확정(남은 단계 건너뜀)'] };
    list.push(nq);
    store.set('localGates', [...(store.get('localGates') || []).filter(x => x.id !== id), nq].slice(-50));
  }
  S.d = derive(S.data);
  return id;
}
// 데이터를 새로 받을 때: 아직 허브 게시본에 없는 임시 ★5만 다시 붙인다(6시간 지나면 버림)
function mergeLocalGates() {
  const list = S.data.decisions_needed || (S.data.decisions_needed = []);
  const keep = (store.get('localGates') || []).filter(x => !list.some(y => y.id === x.id) && hoursSince(x.since) < 6);
  store.set('localGates', keep);
  list.push(...keep);
}
// 주제 화면에서도 지금 관문을 바로 고를 수 있게(내 차례까지 가지 않아도 됨)
function gateBox(t) {
  if (!t || t.status !== 'review_user' || !t.gate) return null;
  const q = (S.data.decisions_needed || []).find(x => x.id === t.gate.id && !S.d.answers[x.id]);
  if (!q || !(q.options || []).length) return null;
  const again = () => { const x = S.d.topics.find(y => y.id === t.id); x ? openTopic(x) : closeDrawer(); };
  return h('div', { class: 'callout warn gate-box' }, h('b', null, `${gateName(t.gate.n, t.gate.label)} — 여기서 바로 결정`),
    optionList(q, o => decide(q, o, '', again)));
}
function lockOf(id) {
  let l = (S.data.agent_locks || {})[id] || null;
  for (const p of pending.all().filter(p => p.type === 'agent-lock' && p.agent === id)) l = p.lock ? { mode: p.mode, ts: p.created_at, pending: true } : null;
  return l;
}
function agentOptions(selected, extra) {
  const list = S.data.agents || [];
  // 배정 잠금한 작업자는 고를 수 없다(지금 담당인 경우는 그대로 보이게)
  return [...(extra || []), ...list.map(a => { const lk = lockOf(a.id) && a.id !== selected;
    return h('option', { value: a.id, selected: a.id === selected ? true : null, disabled: lk ? true : null }, `${a.pc_label} · ${a.label || a.id}${lk ? ' (배정 잠금)' : ''}`); })];
}
async function setLock(a, lock, mode) {
  try {
    await sendOps('agent-lock', { agent: a.id, lock, mode: mode || 'assign' }, lock ? `${a.pc_label} ${a.label || a.id} ${mode === 'all' ? '자동 실행 멈춤' : '배정 잠금'}` : `${a.pc_label} ${a.label || a.id} 잠금 풀기`);
    S._keepScroll = true; render();
  } catch (e) { toast(e.message); }
}
function lockControls(a) {
  const l = lockOf(a.id);
  if (!l) return h('div', { class: 'lock-row' },
    h('button', { class: 'btn sm', title: '새 주제 배정·재분배·다른 AI의 인계·요청을 받지 않습니다. 맡은 일은 계속합니다.', onclick: () => setLock(a, true, 'assign') }, icon('lock'), '추가 배정 잠금'),
    h('button', { class: 'btn sm', title: '자동 실행도 멈춥니다(토큰을 쓰지 않음).', onclick: () => setLock(a, true, 'all') }, icon('pause'), '자동 실행까지 멈춤'));
  return h('div', { class: 'lock-row locked' },
    h('span', { class: 'st blocked' }, icon('lock'), l.mode === 'all' ? '배정 잠금 · 자동 실행 멈춤' : '추가 배정 잠금'),
    l.pending ? h('span', { class: 'hint' }, '반영 대기') : h('span', { class: 'hint' }, fmtRel(l.ts)),
    l.mode === 'assign' ? h('button', { class: 'btn sm', onclick: () => setLock(a, true, 'all') }, icon('pause'), '실행도 멈춤') : null,
    h('button', { class: 'btn sm primary', onclick: () => setLock(a, false) }, icon('check'), '잠금 풀기'));
}
function activateControl(t) {
  const pend = pending.all().find(p => p.type === 'activate' && p.topic === t.id);
  if (pend) return h('div', { class: 'callout' }, h('b', null, '착수 지시 반영 대기 · '), '다음 PC 동기화 때 자동 배분으로 담당이 정해집니다.');
  const btn = h('button', { class: 'btn primary', onclick: async () => {
    btn.disabled = true;
    try { await sendOps('activate', { topic: t.id }, `착수 지시: ${t.title}`); render(); openTopic(S.d.topics.find(x => x.id === t.id) || t); }
    catch (e) { toast(e.message); } finally { btn.disabled = false; }
  } }, icon('play'), '시작하기 · Astra에게 맡기기');
  return h('div', { class: 'callout' }, h('div', { style: { 'margin-bottom': '8px' } }, h('b', null, '보관 중인 주제입니다. '), '시작하면 서버컴 Astra가 원래 목표부터 정리하고 실행 작업을 나눕니다.'), btn);
}
function assignControl(t) {
  if (!(S.data.agents || []).length || t.status === 'done') return null;
  const pend = pending.all().find(p => p.type === 'assign' && p.topic === t.id);
  const sel = h('select', { 'aria-label': '담당 바꾸기' }, agentOptions(pend ? pend.agent : t.assignee, t.assignee ? [] : [h('option', { value: '' }, '담당 고르기')]));
  const btn = h('button', { class: 'btn', onclick: async () => {
    if (!sel.value) { toast('담당을 고르세요'); return; }
    if (sel.value === t.assignee && (t.conflict || []).length) return resolveConflict(t, sel.value).then(() => openTopic(S.d.topics.find(x => x.id === t.id) || t));
    btn.disabled = true;
    // 지금 담당을 다시 고르면 '담당 확정'(새 시각으로 지정 — 그 앞의 다른 작업자 착수는 충돌에서 빠지고 재분배도 하지 않는다)
    const same = sel.value === t.assignee;
    try { await sendOps('assign', { topic: t.id, agent: sel.value, note: same ? '담당 확정' : '', ...(same ? { confirm: true } : {}) }, same ? `주제 담당 확정: ${person(sel.value).name}` : `주제 담당 → ${person(sel.value).name}`); render(); openTopic(S.d.topics.find(x => x.id === t.id) || t); }
    catch (e) { toast(e.message); } finally { btn.disabled = false; }
  } }, icon('agents'), '담당 바꾸기 · 같은 담당이면 확정');
  return h('div', { class: 'composer' }, h('div', { class: 'row' }, sel, btn),
    pend ? h('div', { class: 'hint' }, `담당 변경 반영 대기: ${person(pend.agent).full}`) : null);
}
// 중복 착수 해결(2026-10-03 아키텍트): 경고가 '한쪽을 멈추거나 담당을 바꿔 달라'고 하면 그 행동 버튼이 같은 자리에 있어야 한다.
// 고른 작업자를 담당으로 확정(지금 담당과 같아도 새 시각으로 지정)하고 나머지의 착수는 치운다 — 치운 쪽 수신함에 '담당에서 빠짐'.
// 실게임 시험 단계에는 담당이 개발컴 Claude로 옮겨져 있으므로 원래 담당(live_from)도 고를 수 있게 넣는다
function conflictWho(t) { return [...new Set([t.assignee, t.live_from, ...(t.conflict || [])].filter(Boolean))]; }
async function resolveConflict(t, agent) {
  const drop = conflictWho(t).filter(a => a !== agent);
  try {
    await sendOps('assign', { topic: t.id, agent, drop, note: `중복 착수 해결: ${person(agent).full}가 계속, ${drop.map(a => person(a).full).join(', ')} 착수 치움` },
      `중복 착수 해결: ${person(agent).name} 계속`);
    toast(`${person(agent).name}가 계속합니다 · 다음 동기화 때 반영`);
    S._keepScroll = true; render();
    return true;
  } catch (e) { toast(e.message); return false; }
}
function conflictButtons(t, kb) {
  const who = conflictWho(t), picked = S.kbPick && S.kbPick.id === `conflict:${t.id}` ? S.kbPick.idx : -1;
  return h('div', { class: 'choice-row' }, who.map((a, i) => {
    const others = who.filter(x => x !== a).map(x => person(x).name).join(', ');
    return h('button', { class: `btn${a === (t.live_from || t.assignee) ? ' primary' : ''}${i === picked ? ' kb-picked' : ''}`, 'data-kb-opt': String(i), onclick: () => resolveConflict(t, a) },
      kb ? kbd(String(i + 1)) : null, `${person(a).full}가 계속`, h('span', { class: 'hint' }, ` (${others} 착수 치움${a !== t.assignee ? ` · 담당을 ${person(a).name}로` : ''})`));
  }));
}
function conflictBox(t) {
  if (t._pendingResolve) return h('div', { class: 'callout' }, h('b', null, '중복 착수 해결 반영 대기: '), `${person(t._pendingResolve.agent).full}가 계속 · 다음 동기화 때 반영`);
  if (!(t.conflict || []).length) return null;
  return h('div', { class: 'callout warn' }, h('div', null, h('b', null, '중복 착수: '), `담당은 ${person(t.assignee).full}인데 ${t.conflict.map(c => person(c).full).join(', ')}도 착수했습니다. 누가 이어서 할지 고르세요.`),
    conflictButtons(t, false));
}
function conflictParts(t, redraw) {
  return {
    main: [
      h('div', { class: 'when' }, t.updated_at ? `${fmtAbs(t.updated_at)} · ${fmtRel(t.updated_at)}` : ''),
      h('h3', { class: 'd-title' }, `중복 착수: ${t.title}`),
      h('div', { class: 'callout warn' }, `담당은 ${person(t.assignee).full}인데 ${t.conflict.map(c => person(c).full).join(', ')}도 착수했습니다. 누가 이어서 할지 고르세요. 고른 작업자가 담당으로 확정되고, 나머지의 착수는 치워지며 그 작업자에게 '담당에서 빠짐'을 알립니다.`),
      h('h4', null, '누가 계속 — 누르면 바로 반영 · 키보드는 숫자로 고르고 Enter'),
      conflictButtons(t, true),
      h('div', { class: 'choice-row' }, h('button', { class: 'btn', onclick: () => openTopic(t) }, icon('topics'), '주제 보기')),
    ],
    side: historyPanel(t, null, null),
  };
}
function openDecisionNeeded(q) {
  const p = decisionParts(q, () => openDecisionNeeded(q));
  reopenWith(() => { const x = (S.data.decisions_needed || []).find(y => y.id === q.id); if (x) openDecisionNeeded(x); });
  modalSplit('결정이 필요한 문제', p.main, p.side);
}
// 결정 화면 내용: 오른쪽 칸(내 차례)과 가운데 모달이 같이 쓴다
function decisionParts(q, redraw) {
  const ans = S.d.answers[q.id];
  const note = h('textarea', { placeholder: '선택지 말고 직접 적거나, 고른 선택지에 덧붙일 말 (선택)', rows: '3', 'aria-label': '결정 메모', 'data-draft': `decide:${q.id}`, 'data-kb-reply': '1' });
  const topic = topicById(q.task_id);
  const task = !topic && q.task_id ? S.d.tasks.find(t => t.id === q.task_id) : null;
  return {
    main: [
      h('div', { class: 'meta', style: { display: 'flex', gap: '8px', 'flex-wrap': 'wrap', 'align-items': 'center' } },
        h('span', { class: 'wait' }, av(q._author || 'claude', true), `${person(q._author || 'claude').full} 질문`),
        h('span', { class: 'when' }, `${fmtAbs(q.since)} · ${fmtRel(q.since)}`),
        rollbacks(topic) ? h('span', { class: 'st blocked' }, `되돌림 ${rollbacks(topic)}회`) : null),
      questionText(q.question),
      liveBox(topic),
      linkBox(topic),
      resultBox(topic, gateNOf(q)),
      q.recommendation ? h('div', { class: 'callout' }, h('b', null, '권장 '), q.recommendation) : null,
      ans ? h('div', { class: 'callout' }, h('b', null, '내 결정: '), ans.choice || '(메모)', ans.note ? ' — ' + ans.note : '',
        (() => { const r = decisionReflect(q, ans); return h('div', { class: `reflect ${r.cls}` }, icon(r.cls === 'done' ? 'check' : 'clock'), h('span', null, r.text)); })()) : null,
      // 이미 보낸 결정은 다시 보낼 수 없다(바꾸려면 10초 안에 취소 띠에서 취소)
      ans ? null : [
        (q.options || []).length ? [h('h4', null, '선택지 — 누르면 바로 결정 · 키보드는 숫자로 고르고 Enter'), optionList(q, o => decide(q, o, note.value.trim(), redraw))] : null,
        h('h4', null, '직접 적기'),
        MEMO_HINT[gateNOf(q)] ? h('div', { class: 'hint' }, MEMO_HINT[gateNOf(q)]) : null,
        h('div', { class: 'composer' }, note, h('div', { class: 'row' }, h('button', { class: 'btn primary', onclick: () => { if (!note.value.trim()) { note.focus(); return; } decide(q, '', note.value.trim(), redraw); } }, icon('send'), '메모로 결정 보내기', kbd('Ctrl+Enter')))),
        sendHint()],
    ],
    side: historyPanel(topic, task, `ask:${q.id}`),
  };
}
// AI 질문(주제 기록의 질문)을 가운데 모달로: 질문 본문 + 답 보내기 + 히스토리
function openQuestion(topic, n) {
  const p = questionParts(topic, n, () => openQuestion(topic, n));
  reopenWith(() => openQuestion(topicById(topic.id) || topic, n));
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
        h('button', { class: 'btn', 'data-kb-key': 'x', onclick: () => { ack(key); closeDrawer(); } }, icon('check'), '답 없이 확인함으로 처리', kbd('X'))),
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
  if (t.status === 'done' && t.followed) return { cls: t.chain && t.chain.state === 'done' ? 'done' : 'progress', icon: 'arrow', label: t.chain && t.chain.state === 'done' ? '줄기 완료(후속까지 완료 확정)' : `후속으로 이어짐 · ${t.chain ? t.chain.label : ''}`,
    detail: t.chain ? t.chain.head : null, next: t.chain && t.chain.state !== 'done' ? '후속 주제에서 계속 — 후속이 완료 확정되면 이 주제도 완료로 셉니다' : null };
  if (t.status === 'done') return { cls: 'done', icon: 'check', label: t.confirmed ? '완료 확정' : '완료' };
  if (t.archived) return { cls: 'neutral', icon: 'arrow', label: `재시작 전 기록 → ${t.restarted_as || ''}`.trim() };  // 사령탑 전환 재시작 보관(보류 아님)
  if (t.status === 'parked') return { cls: 'neutral', icon: 'pause', label: '보류' };
  // 9단계 관문: 아키텍트 결정 차례(★4 실게임 시험 · ★5 배포본 결정 · ★7 운영 반영 승인 · ★9 완료 확정 · 조사·분석은 결과 확인)
  if (t.status === 'review_user' && t.gate && S.d.answers[t.gate.id]) {  // 답은 보냈고 허브 반영(1~2분)을 기다리는 중
    const a = S.d.answers[t.gate.id];
    return { cls: 'progress', icon: 'clock', label: `${gateName(t.gate.n, '')} 답함 · 반영 대기`, detail: `내 결정: ${a.choice || '메모'}${a.note ? ' — ' + a.note : ''}`,
      next: '허브가 다음 동기화(1~2분) 때 반영합니다' };
  }
  if (t.status === 'review_user' && t.gate) {
    const open =(S.data.decisions_needed || []).filter(q => !S.d.answers[q.id]);
    const ask = open.find(q => q.id === t.gate.id) || open.find(q => q.task_id === t.id);
    return { cls: 'user_test', icon: 'scale', label: `${gateName(t.gate.n, t.gate.label)}${t.live_session ? ' · 개발컴 Claude 대화' : ''}`, detail: (t.gate.summary || '').slice(0, 300) || null,
      next: `아키텍트 — ${t.live_session ? '개발컴 Claude 대화를 열어 시험·수정, 그다음 ' : ''}결재함에서 고르기: ${(t.gate.options || []).map(o => o.replace(/\(.*\)/, '')).join(' · ')}`, ask };
  }
  if (t.live_session) return { cls: 'user_test', icon: 'user', label: '실게임 시험 수정 · 개발컴 Claude 대화',
    detail: '실게임 시험에서 나온 문제를 대화 세션에서 고치는 중입니다(자동 실행기는 손대지 않음).', next: '개발컴 Claude 대화 — 고치고 끝냄을 남기면 바로 ★4 실게임 시험으로' };
  if (t.park_proposed) return { cls: 'user_test', icon: 'pause', label: `AI 보류 제안 · ${name(t.park_proposed.by)}`, detail: t.park_proposed.body || null, next: '아키텍트 — 결재함 ★ 관문에서 보류 승인·다시 진행·즉시 완료 중 고르기' };
  if (t.status === 'backlog') return { cls: 'neutral', icon: 'inbox', label: '주제 보관 · 시작 전', next: '아키텍트 — 이 주제의 시작 버튼으로 Astra에게 맡기기' };
  const hold = holdOf(t.id);
  if (hold) return { cls: 'progress', icon: 'user', label: `대화 세션 작업 중 · ${name(hold.agent)}`, detail: `${hold.note || ''} (${fmtAbs(hold.until)}까지 자동 실행 멈춤)` };
  const run = runsFor(t.id)[0];
  const rq = t.open_request;
  if (rq) return { cls: 'progress', icon: 'arrow', label: `요청 처리 중 · ${name(rq.to)}${isRunning(run) && run.agent === rq.to ? ' (실행 중)' : ''}`,
    detail: `${name(rq.from)} → ${name(rq.to)}: ${rq.body || '-'}`, next: `${name(rq.to)} — 답하면 ${name(rq.from)}에게 자동으로 돌아감` };
  if (isRunning(run)) return { cls: 'progress', icon: 'play', label: `실행 중 · ${name(run.agent)}`, detail: `${fmtRel(run.started)} 시작 · 이유: ${run.reason || '-'}` };
  const ask = (S.data.decisions_needed || []).find(q => q.task_id === t.id && !S.d.answers[q.id]);
  if (ask) return { cls: 'user_test', icon: 'scale', label: '아키텍트 답 대기', detail: ask.question, next: '아키텍트 — 결재함에서 결정', ask };
  if (run && run.result === 'fail') return { cls: 'blocked', icon: 'alert', label: `실행 실패 · ${HEALTH[run.error_class] || '오류'}`,
    detail: `${run.fix || ''} (${fmtRel(run.ended || run.started)})`, next: run.needs_user ? `아키텍트 — ${run.fix || '확인 필요'}` : '자동으로 다시 시도' };
  if (t.command_mode) {
    const stage=flowStage(t), label=FLOW_STAGES.find(x=>x[0]===stage)?.[1]||stage;
    return {cls:stage==='decision'?'user_test':'progress',icon:stage==='test'?'check':'play',label,
      detail:testHeadline(t)||`현재 담당: ${t.turn?person(t.turn).full:'배포 큐 대기'}`,
      next:stage==='deploy'?'서버컴 Astra가 묶음을 준비합니다. 최종 대화에서는 묶음 번호로 검토·배포합니다.':
        stage==='queue'?'아키텍트 — 배포 메뉴에서 준비된 주제를 묶음으로 선택':
        stage==='test'?'세부 시험 결과·막힌 이유·재시험 이력을 아래에서 확인하세요.':'Astra가 분배·검수하고 다음 단계로 이어갑니다.'};
  }
  const who = t.turn;
  const partial = run && run.result === 'partial' ? ` · 지난 실행 일부 실패: ${(run.failed || []).join('; ').slice(0, 160)}` : '';
  if (!t.assignee) return { cls: 'request', icon: 'topics', label: '배분 대기', next: `${name(who || 'dev-claude')} — 자동 배분` };
  if (t.stage === 'queue') return { cls: 'neutral', icon: 'calendar', label: '배포 대기열 · 배포 준비 완료', detail: ((t.deploy_prep || {}).summary || '').slice(0, 300) || null,
    next: '아키텍트 — 배포 대기열 메뉴에서 날을 잡아 배포 묶음에 넣기' };
  if (t.stage === 'deploy' && t.deploy_session) return { cls: 'user_test', icon: 'user', label: `8b 배포 · 묶음 ${(t.deploy_batch || {}).id || '-'} · 서버컴 Astra 대화`,
    detail: `배포 날짜 ${(t.deploy_batch || {}).date || '미정'} · 자동 실행기는 손대지 않음`, next: '아키텍트 — 배포 대기열 메뉴에서 묶음 대화 문구를 복사해 서버컴 Astra와 배포' };
  const STAGE_NEXT = { test: '정적 검증·시험 절차 작성 → ★4 실게임 시험으로', pack: '배포본(파일 목록·SHA256·백업·복구 절차) → ★7 운영 반영 승인으로',
    prep: '배포 준비(실서버 diff·겹침·순서·백업·복구, 운영 서버에는 쓰지 않음) → 배포 대기열로', deploy: '서버컴 배포·확인 → ★9 완료 확정으로' };
  if (t.step && STAGE_NEXT[t.stage]) return { cls: 'progress', icon: 'play', label: `${t.step.n}/9 ${t.step.label} · ${name(who)}`, detail: partial.slice(3) || null, next: `${name(who)} — ${STAGE_NEXT[t.stage]}` };
  if (t.handoff && t.handoff.to === t.assignee && who === t.assignee)
    return { cls: 'progress', icon: 'arrow', label: `인계받음 · ${name(who)}`, detail: `${name(t.handoff.from)} → ${name(t.handoff.to)}: ${t.handoff.reason || '-'}${partial}`, next: `${name(who)} — 이어서 처리` };
  if (who && who !== t.assignee) return { cls: 'validating', icon: 'eye', label: `교차 검토 대기 · ${name(who)}`, detail: partial.slice(3) || null, next: `${name(who)} — 진행 베이스 검토` };
  if (!t.plan) return { cls: 'request', icon: 'file', label: `진행 베이스 작성 · ${name(who)}`, detail: partial.slice(3) || null, next: `${name(who)} — 목표·범위·첫 단계 작성` };
  const qc = queueCode(t);
  if (qc === 'stalled') { const s = stallOf(t); return { cls: 'blocked', icon: 'alert', label: `실행기 멈춤 · ${name(who)}`, detail: `${s?.reason || '원인 미상'}${s?.since ? ` (${fmtRel(s.since)}부터)` : ''}`, next: '조치 없음 — 같은 사유로 세 번 건너뛴 뒤에는 허브 판정대로 다음 실행에서 다시 깨움' }; }
  return { cls: 'progress', icon: 'play', label: `${t.step ? '2/9 ' : ''}진행 중 · ${name(who)}`, detail: partial.slice(3) || null, next: `${name(who)} — ${QUEUE_NEXT[qc] || '다음 동기화 때 이어서'}` };
}
// 실행기가 올린 주제별 판정(작업자 기록 queue.items). '다음' 문구를 실행기 실제 판정과 같게 한다
const QUEUE_NEXT = { runnable: '다음 동기화 때 이어서', retry: '간격을 두고 다시 깨움(실패 뒤 10~30분 · 진척 없으면 30분~2시간)',
  waiting_answer: '아키텍트 답을 기다림', waiting_change: '이 단계는 처리함 — 변화가 없으면 30분(반복 시 2시간) 뒤 자동으로 다시 깨움', held: '대화 세션이 처리 중' };
function queueOf(t) { return ((S.data.agents || []).find(a => a.id === t.turn) || {}).queue || null; }
function queueCode(t) { const q = queueOf(t); return q && q.items ? q.items[t.id] || null : null; }
function stallOf(t) { const q = queueOf(t); return q && (q.stalled || []).find(x => x.topic === t.id) || null; }
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
      (w.files || []).length ? h('ul', { class: 'work-files' }, w.files.slice(0, 14).map(f => h('li', { class: 'mono' }, docLink(w, f), h('span', { class: 'hint' }, ` ${Math.max(1, Math.round(f.size / 1024))}KB`))),
        w.files.length > 14 ? h('li', { class: 'hint' }, `… 외 ${w.file_count - 14}개`) : null) : null,
      agents.filter(([, x]) => x.notes_tail).map(([a, x]) => h('div', { class: 'work-note' }, h('b', null, `${person(a).name} 최근 메모`, x.last_note_at ? ` · ${fmtAbs(x.last_note_at)}` : ''), longText(x.notes_tail))),
      h('a', { class: 'btn sm', href: w.main_url || w.url, target: '_blank', rel: 'noopener noreferrer' }, icon('link'), w.main_url ? '핵심 문서 GitHub에서 열기' : 'GitHub에서 열기 (real-work)')));
}
// 결과물 파일: 문서는 눌러서 바로 보고(내용이 데이터에 있음), 코드·diff·큰 파일은 비공개 real-work 저장소에서 연다
function docLink(w, f) {
  const text = (w.docs || {})[f.path];
  if (text != null) return h('button', { class: 'linkless doc-link', onclick: () => openDoc(w, f.path, text) }, f.path);
  return f.url ? h('a', { href: f.url, target: '_blank', rel: 'noopener noreferrer' }, f.path) : f.path;
}
function openDoc(w, path, text) {
  const f = (w.files || []).find(x => x.path === path);
  reopenWith(() => openDoc(w, path, text));
  modal(`${w.id} · ${path}`, f && f.url ? h('a', { class: 'btn sm', href: f.url, target: '_blank', rel: 'noopener noreferrer' }, icon('link'), 'GitHub에서 열기') : null,
    h('pre', { class: 'pre doc-pre' }, text));
}
// 관문·결과 화면의 '결과물 보기': 핵심 문서(SUMMARY·DESIGN·NOTES 순)를 바로 펼친다
const GATE_DOCS = {
  40: [/SUMMARY/i, /DESIGN|기획|설계/i, /NOTES/i, /REVIEW/i],
  4: [/CHECK|체크|시험|TEST/i, /DESIGN/i, /NOTES/i, /SUMMARY/i],
  5: [/PATCH|패치|CHANGE|변경/i, /DESIGN/i, /SUMMARY/i, /NOTES/i],
  7: [/DEPLOY|배포|APPLY|적용|ROLLBACK|복구|백업/i, /README/i, /DESIGN/i, /NOTES/i],
  9: [/APPLY|반영|VERIFY|확인|LOG|EVIDENCE/i, /NOTES/i, /SUMMARY/i],
};
const docLabel = p => p.includes('/') ? `${p.split('/')[0]} · ${p.split('/').pop()}` : p;
function prevWorks(t) {  // 줄기에서 이 주제 앞의 주제들 작업물(원래 주제의 기획 결과 등)
  if (!t || !t.chain) return [];
  const ids = t.chain.members.map(m => m.id), i = ids.indexOf(t.id);
  return ids.slice(0, Math.max(0, i)).map(id => topicById(id)).filter(x => x && x.work_id && (S.data.works || {})[x.work_id]).map(x => ({ t: x, w: S.data.works[x.work_id] }));
}
function chainTitle(t) {
  const r = topicById(t.chain.root);
  return r && r.id !== t.id ? `${r.title} → ${t.title}` : t.title;
}
function chainGates(t) {  // 줄기 전체의 관문 기록(완료 메뉴 펼치기)
  if (!t.chain) return t.gate_history || [];
  return t.chain.members.flatMap(m => ((topicById(m.id) || {}).gate_history || []).map(x => ({ ...x, _topic: m.id }))).sort((a, b) => toMs(a.answered_at) - toMs(b.answered_at));
}
function chainBox(t) {
  const c = t.chain;
  if (!c) return null;
  return h('div', { class: 'callout chain-box' },
    h('div', null, h('b', null, '줄기 · '), c.head, h('span', { class: `st ${c.state === 'done' ? 'done' : c.state === 'parked' ? 'neutral' : 'progress'}`, style: { 'margin-left': '6px' } }, c.label)),
    h('div', { class: 'chain-steps' }, c.members.map((m, i) => [i ? h('span', { class: 'muted' }, ' → ') : null,
      h('button', { class: `tag tag-btn${m.id === t.id ? ' on' : ''}`, title: m.id, onclick: () => { const y = topicById(m.id); if (y && y.id !== t.id) openTopic(y); } },
        `${m.title} · ${m.where}`)])));
}
function resultBox(t, n) {
  const w = t && t.work_id ? (S.data.works || {})[t.work_id] : null;
  if (!w && !prevWorks(t).length) return null;
  if (!w) return h('div', { class: 'result-box' }, prevWorks(t).map(p => h('div', { class: 'hint' }, `앞 단계 결과 · ${p.t.title}: `, h('a', { href: p.w.url, target: '_blank', rel: 'noopener noreferrer' }, '작업물 열기'))));
  const pats = GATE_DOCS[n] || GATE_DOCS[40];
  const rank = p => { const i = pats.findIndex(re => re.test(p)); return i < 0 ? 99 : i; };
  const docs = Object.keys(w.docs || {}).sort((a, b) => rank(a) - rank(b));
  const fold = (p, open) => h('details', { class: 'doc-fold', open: open ? true : null }, h('summary', null, open ? h('b', null, `검토할 결과물 · ${docLabel(p)}`) : docLabel(p)),
    h('pre', { class: 'pre doc-pre doc-inline' }, w.docs[p]));
  const prev = prevWorks(t);
  return h('div', { class: 'result-box' },
    prev.length ? h('details', { class: 'doc-fold' }, h('summary', null, h('b', null, `앞 단계 결과 · ${prev.map(p => p.t.title).join(' → ')}`)),
      prev.map(p => { const k = Object.keys(p.w.docs || {}).sort((a, b) => (/SUMMARY|DESIGN|기획/i.test(a) ? 0 : 1) - (/SUMMARY|DESIGN|기획/i.test(b) ? 0 : 1))[0];
        return k ? h('details', { class: 'doc-fold' }, h('summary', null, `${p.t.title} · ${docLabel(k)}`), h('pre', { class: 'pre doc-pre doc-inline' }, p.w.docs[k]))
          : h('div', { class: 'hint' }, `${p.t.title}: 펼칠 문서 없음 — `, h('a', { href: p.w.url, target: '_blank', rel: 'noopener noreferrer' }, '작업물 열기')); })) : null,
    n === 4 ? h('div', { class: `callout ${liveReady(t) ? '' : 'warn'}` }, liveReady(t) ? '빌드 있음 — 바로 실게임 시험할 수 있습니다' : '반영·빌드가 먼저 필요합니다 — 개발컴 Claude 대화(또는 시험 묶음)에서 반영·빌드 뒤 시험') : null,
    docs.length ? [fold(docs[0], true), docs.slice(1, 6).map(p => fold(p, false))] : h('div', { class: 'hint' }, '펼칠 문서가 없습니다(코드·diff만 있음) — 아래 원본 파일에서 엽니다'),
    h('details', { class: 'doc-fold' }, h('summary', null, `원본 파일 ${w.file_count}개 · 작업물 ${w.id}`),
      h('ul', { class: 'work-files' }, (w.files || []).slice(0, 30).map(f => h('li', { class: 'mono' }, docLink(w, f)))),
      h('a', { class: 'btn sm', href: w.main_url || w.url, target: '_blank', rel: 'noopener noreferrer' }, icon('link'), 'GitHub에서 열기')));
}

// ------------------------------------------------------------ 히스토리 (모달 오른쪽: 이 주제에서 지금까지 있었던 일)
const HIST_KIND = { ...NOTE_KIND, created: '등록', reply: '대화', ask: '결정 요청', decide: '결정', message: '메시지', run: '자동 실행' };
// 줄기(아키텍트 2026-10-03 '원래와 후속이 한 라인으로'): 원래 주제 기록 뒤에 후속 주제 기록을 시간순으로 잇고, 주제가 바뀌는 곳에 구분선
function historyEvents(topic, task) {
  if (!topic || !topic.chain) return historyEventsOne(topic, task);
  const ev = [];
  for (const m of topic.chain.members) {
    const x = topicById(m.id);
    if (!x) continue;
    if (m.id !== topic.chain.root) ev.push({ key: `chain:${m.id}`, ts: x.created_at, by: 'user', kind: 'chain', body: `→ 후속 주제 시작 · ${x.title}`, chainTopic: m.id, other: m.id !== topic.id, sep: true });
    for (const e of historyEventsOne(x, x.id === topic.id ? task : null)) ev.push({ ...e, chainTopic: m.id, other: m.id !== topic.id, key: e.key && m.id !== topic.id ? `${m.id}:${e.key}` : e.key });
  }
  return ev.sort((a, b) => (toMs(a.ts) || 0) - (toMs(b.ts) || 0) || (a.sep ? -1 : b.sep ? 1 : 0));
}
function historyEventsOne(topic, task) {
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
    for (const q of topic.requests || []) {  // 요청은 받는 사람까지 보이게(같은 내용의 기록 메모는 한 번만)
      push({ ts: q.ts, by: q.from, to: q.to, kind: 'request', body: q.body });
      if (q.status === 'answered') push({ ts: q.reply_ts, by: q.reply_by, to: q.from, kind: 'reply', body: q.reply });
    }
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
    topic.chain ? chainBox(topic) : null,
    h('div', { style: { display: 'flex', gap: '6px', 'flex-wrap': 'wrap', 'align-items': 'center' } }, topicChip(topic.status), priChip(topic.priority), topic.kind ? h('span', { class: 'tag' }, topic.kind) : null, h('span', { class: 'tag mono' }, topic.id)),
    h('div', { class: 'hist-title' }, topic.title),
    h('dl', { class: 'fields' }, h('dt', null, '담당'), h('dd', null, topic.assignee ? person(topic.assignee).full : '미배정'),
      h('dt', null, '지금 차례'), h('dd', null, topic.turn ? person(topic.turn).full : '—'),
      topic.dispatch_reason ? [h('dt', null, topic.assign_by === 'user' ? '담당 지정' : topic.assign_by === 'handoff' ? '인계' : '배분 근거'), h('dd', null, topic.dispatch_reason)] : null),
    priorContextBox(topic),
    flowRibbon(topic),
    commandBox(topic),
    testBox(topic),
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
  const row = e => e.sep ? h('li', { class: 'hist-sep' }, h('button', { class: 'linkish', onclick: () => { const y = topicById(e.chainTopic); if (y) openTopic(y); } }, e.body), h('span', { class: 'when' }, fmtAbs(e.ts))) :
    h('li', { class: `hist-item k-${e.kind}${e.cls ? ' r-' + e.cls : ''}${e.by === 'user' ? ' me' : ''}${e.other ? ' other' : ''}${e.key && e.key === focusKey ? ' focus' : ''}` },
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
    h('h4', null, topic && topic.chain ? `줄기 히스토리 ${ev.filter(e => !e.sep).length}건 · 원래 주제부터 한 라인(지금 주제 강조)` : `히스토리 ${ev.length}건 · 오래된 것부터`),
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
  // 번호 항목 '(1) …'만 줄을 나눈다: 줄 머리나 빈칸 뒤에 오고 뒤에 빈칸이 있는 것(문장 중간 'reject(1),'은 그대로, 교차 검수 P3)
  const text = String(s || '').replace(/(^|\s)\((\d{1,2})\)\s+/g, (m, pre, n) => `\n\n(${n}) `).replace(/^\s+/, '');
  return h('div', { class: 'q-text' }, text);
}
// 선택지: 마우스로 누르면 바로 결정, 키보드 1~9는 고른 표시만(Enter로 보냄)
// 선택지마다 '누르면 → 다음 일'(보고서 3번). 짧고 쉬운 말로
const GATE_HINT = {
  4: [[/^통과/, '다음: ★5 배포본 결정이 바로 열립니다'], [/^문제 있음/, '다음: 개발컴 Claude 대화에서 고친 뒤 ★4로 다시 옵니다']],
  5: [[/^배포본/, '다음: AI가 배포본을 만들고 ★7 운영 반영 승인으로'], [/^수정/, '다음: 진행으로 돌아가 다시 만들고 ★4 실게임부터 다시']],
  7: [[/^배포 대기열|^서버컴/, '다음: 서버컴 Astra가 배포 준비(실서버 diff·겹침·순서·백업)만 하고 배포 대기열로 — 운영 반영은 아직 아님. 날을 잡아 배포 묶음으로'], [/^배포본 수정/, '다음: 메모가 배포본 담당에게 가고, 고친 배포본으로 ★7이 다시 옵니다']],
  9: [[/^완료 확정/, '끝: 완료 메뉴로 갑니다'], [/^배포 실패/, '다음: 배포본 그대로 배포 대기열로 — 다음 묶음에 다시'], [/운영 반영만|배포본 고침/, '다음: 배포본만 고쳐 ★7 → 배포 준비 → 대기열 → ★9 (실게임 생략)'], [/실게임부터|진행으로/, '다음: 진행 → 자체 시험 → ★4부터 모두 다시']],
  40: [[/^후속 구현/, '다음: 이 주제는 끝내고, 만드는 주제를 새로 만들어 배분합니다'], [/^완료 확정/, '끝: 완료 메뉴로 갑니다']],
};
const COMMON_HINT = [[/^보류/, '다음: 보류 메뉴로 · 다시 진행하면 이 관문이 다시 열립니다'], [/^즉시 완료/, '끝: 남은 단계 없이 바로 완료(되돌릴 수 없음)']];
const MEMO_HINT = { 4: '메모만 보내면: 개발컴 Claude 대화에서 고치는 단계로 갑니다(메모 = 문제 내용)', 5: '메모만 보내면: 수정과 같습니다 — 진행으로 돌아갑니다',
  7: '메모만 보내면: 배포본 수정과 같습니다 — 메모가 배포본 담당에게 갑니다', 9: '메모만 보내면: 진행으로 돌아가 실게임부터 다시 합니다', 40: '메모만 보내면: 진행으로 돌아가 메모대로 다시 합니다' };
function gateNOf(q) { return q && q.kind === 'gate' ? (q.gate || Number(((q.question || '').match(/^\[(\d+)\/9/) || [])[1]) || null) : null; }
function optHint(q, o) {
  const n = gateNOf(q);
  if (!n) return null;
  const hit = [...(GATE_HINT[n] || []), ...COMMON_HINT].find(([re]) => re.test(o));
  return hit ? hit[1] : null;
}
// '보류'·'즉시 완료'는 마우스로 눌러도 한 번 더 묻는다(키보드는 숫자 → Enter 두 단계라 그대로)
function riskyOk(o) { return !/^보류|^즉시 완료/.test(o || '') || confirm(`'${o}'을(를) 보낼까요?`); }
function optionList(q, pick) {
  const picked = S.kbPick && S.kbPick.id === q.id ? S.kbPick.idx : -1;
  return h('div', { class: 'opt-list' }, (q.options || []).map((o, i) => h('button', { class: `opt${i === picked ? ' kb-picked' : ''}`, 'data-kb-opt': String(i), onclick: () => { if (riskyOk(o)) pick(o); } },
    i < 9 ? h('span', { class: 'kb-num', 'aria-hidden': 'true' }, i + 1) : null, h('span', null, o, optHint(q, o) ? h('span', { class: 'opt-hint' }, optHint(q, o)) : null))));
}
// 되돌림 횟수(관문에서 진행으로 돌려보낸 횟수)
function rollbacks(t) { return t ? (t.gate_history || []).filter(x => x.act === 'work' || (x.act === 'pack' && x.n !== 5)).length : 0; }
// 관문 이름: 결과 확인(조사·기획)은 ★4 실게임 시험과 번호가 겹치지 않게 따로 부른다(보고서 5번)
function gateName(n, label) { return Number(n) === 40 ? '결과 확인(조사·기획)' : `★${n}/9 ${label || ''}`.trim(); }
// 버튼 옆 작은 키 표시(휴대폰에서는 숨김)
function kbd(k) { return h('span', { class: 'kb', 'aria-hidden': 'true' }, k); }

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
function removePanels() {
  snapshotDrafts(document.body);
  document.querySelectorAll('.scrim, .drawer').forEach(e => e.remove());
}
// 다음에 여는 창을 뒤로/앞으로 때 어떻게 다시 열지 정한다(지금 데이터로 새로 그리는 함수).
// 정하지 않은 창(확인·입력용: 묶음 완료 확정·묶음 만들기·작성창 등)은 복원 때 닫힌 상태로 둔다
function reopenWith(fn) { S._reopen = fn; }
function openPanel(cls, eyebrow, content) {
  const topic = S._openingTopic || null; S._openingTopic = null;
  const rebuild = S._reopen || null; S._reopen = null;
  const panelKey = topic ? 'topic:' + topic : cls + ':' + eyebrow;
  closingPanel = false;
  if (!restoringScreen) {
    saveScreen();
    const same = screenHistory.get(screenId)?.panel?.key === panelKey;
    if (!same) { screenId = screenKey(); pushScreen(routeUrl(S.view, topic)); } else replaceScreen(routeUrl(S.view, topic));
    // 화면 조각(DOM)은 저장하지 않는다 — 되살아난 확인창에서 같은 결정을 다시 보내는 일을 막는다
    screenHistory.set(screenId, { view: S.view, f: { ...S.f }, q: S.q, mineSel: S.mineSel, scroll: window.scrollY,
      panel: { key: panelKey, topic, cls, title: eyebrow, rebuild } });
  }
  removePanels();
  const scrim = h('div', { class: 'scrim', onclick: () => closeDrawer() });
  const panel = h('aside', { class: cls, role: 'dialog', 'aria-modal': 'true', 'aria-label': eyebrow },
    h('div', { class: 'drawer-h' }, h('span', { class: 'eyebrow' }, eyebrow), h('button', { class: 'icon-btn', 'aria-label': '이전 화면', onclick: () => closeDrawer() }, icon('arrow'))),
    h('div', { class: 'drawer-b' }, content));
  document.body.append(scrim, panel);
  S._lastFocus = document.activeElement;
  requestAnimationFrame(() => { scrim.classList.add('on'); panel.classList.add('on'); panel.querySelector('.drawer-h button').focus(); });
}
// 닫기: 창을 열 때 쌓은 방문 기록 한 칸만 되돌린다. 닫기·Esc를 연달아 눌러도 한 번만 처리하고(되돌아가는 중 표시),
// 이 앱의 첫 화면이면 사이트 밖으로 나가지 않게 back 대신 같은 자리 기록을 창 없는 화면으로 바꾼다
function closeDrawer(instant) {
  if (instant) { removePanels(); return; }
  if (!document.querySelector('.drawer')) return;  // 열린 창이 없으면 아무것도 하지 않는다
  if (closingPanel) return;
  const entry = screenHistory.get(screenId);
  if (entry?.panel && !restoringScreen) {
    saveScreen();
    if (histDepth() > 0) {
      closingPanel = true;
      document.querySelectorAll('.drawer, .scrim').forEach(e => e.classList.remove('on'));
      history.back();
      setTimeout(() => { if (closingPanel) { closingPanel = false; removePanels(); } }, 1500);  // popstate가 오지 않는 환경 대비
      return;
    }
    removePanels();
    screenId = screenKey();
    replaceScreen(routeUrl(S.view));
    screenHistory.set(screenId, { ...entry, panel: null });
    saveScreen();
    S._lastFocus?.focus?.();
    return;
  }
  removePanels(); S._lastFocus?.focus?.();
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
  reopenWith(() => openTaskById(t.id));
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
function openMessage(m) { reopenWith(() => { const x = S.data.messages.find(y => y.id === m.id); if (x) openMessage(x); }); drawer('메시지', messageDetail(m, () => openMessage(m))); }
function openLedger(e) {
  reopenWith(() => openLedger(e));
  drawer('감사 원장', h('div', { style: { display: 'flex', gap: '6px' } }, h('span', { class: `st ${LEDGER_ST[e.status].cls}` }, icon(LEDGER_ST[e.status].icon), LEDGER_ST[e.status].label), h('span', { class: 'tag' }, e.has_time ? fmtAbs(e.ts) : e.date)),
    h('h3', null, e.title), h('pre', { class: 'pre' }, e.body));
}
function openValidation(v) {
  reopenWith(() => openValidation(v));
  drawer('QA 검증', h('div', { style: { display: 'flex', gap: '6px' } }, h('span', { class: `st ${v.result === 'pass' ? 'done' : v.result === 'fail' ? 'blocked' : 'neutral'}` }, icon('verify'), v.result === 'pass' ? '통과' : v.result === 'fail' ? '실패' : '불명'), v.live === 'pending' ? h('span', { class: 'st user_test' }, icon('flask'), '실게임 미실행') : null),
    h('h3', null, v.id), fieldList({ 시각: fmtAbs(v.ts), 파일: v.path, '해시 기록 파일 수': v.file_count, ...v.summary }));
}
function openMemory(m) {
  reopenWith(() => openMemory(m));
  drawer('Claude 메모리', h('div', { style: { display: 'flex', gap: '6px', 'flex-wrap': 'wrap' } }, h('span', { class: 'tag' }, m.type), h('span', { class: 'tag' }, fmtAbs(m.ts))),
    h('h3', null, m.id), h('p', { class: 'muted', style: { margin: 0 } }, m.description), h('pre', { class: 'pre' }, m.body),
    m.links?.length ? [h('h4', null, '연결된 기억'), h('div', { style: { display: 'flex', gap: '6px', 'flex-wrap': 'wrap' } }, m.links.map(l => {
      const t = S.data.memory.find(x => x.id === l);
      return h('button', { class: 'tag', style: { cursor: t ? 'pointer' : 'default' }, onclick: () => t && openMemory(t) }, l + (t ? '' : ' (없음)'));
    }))] : null);
}
function openDecision(x) {
  reopenWith(() => openDecision(x));
  drawer('결정 기록', decisionCard(x), fieldList({ 출처: x.source, 기록자: x._author, ID: x.id }));
}
// 개발컴 Claude 대화 시작 문구(실게임 시험 단계·멈춤 결정 '대화로 처리' 공용)
function chatStarterText(t) {
  return t.live_session
    ? `주제 ${t.id} "${t.title}"의 실게임(격리 서버) 시험을 이 대화에서 진행합니다.\n` +
      `먼저 대시보드 도구 폴더(node.py가 있는 곳)에서 python node.py brief ${t.id} 로 내용·작업물·체크리스트를 불러오세요.\n` +
      `시험 중 나온 문제는 이 대화에서 바로 고치고, 고친 뒤에는 python node.py state ${t.id} --agent dev-claude --status done --note "무엇을 고쳤나·시험 방법" 으로 끝냄을 남겨 주세요(자동으로 ★4 실게임 시험으로 돌아옵니다).\n` +
      `격리 서버(server-dev)만 씁니다. 운영 서버 반영은 ★7 승인 뒤 서버컴에서만 합니다.`
    : `주제 ${t.id} "${t.title}"이(가) 자동 실행에서 멈춰서 이 대화에서 처리합니다.\n` +
      `먼저 대시보드 도구 폴더(node.py가 있는 곳)에서 python node.py hold ${t.id} --agent dev-claude --minutes 120 --note "대화 세션 처리" 로 자동 실행기를 멈추고, python node.py brief ${t.id} 로 내용·기록·작업물을 불러오세요.\n` +
      `이 단계 일을 끝내면 python node.py state ${t.id} --agent dev-claude --status done --note "무엇을 했나·작업물 위치·시험 방법" 으로 끝냄을 남기고 python node.py release ${t.id} 로 풀어 주세요.`;
}
function openChatStarter(t) {
  const text = chatStarterText(t);
  modal('개발컴 Claude 대화 시작 문구', h('p', { class: 'hint' }, '개발컴에서 Claude 대화를 열고 아래 문구를 붙여 넣으세요.'), h('pre', { class: 'pre' }, text),
    h('button', { class: 'btn primary', onclick: async () => { try { await navigator.clipboard.writeText(text); toast('복사했습니다'); } catch { toast('복사하지 못했습니다 — 위 글을 직접 선택해 복사하세요'); } } }, icon('send'), '복사'));
}
// 실게임(격리 서버) 시험 단계: 개발컴 Claude 대화를 열어 바로 시험·수정한다(자동 실행기는 손대지 않음)
function liveBox(t) {
  if (!t || !t.live_session) return null;
  const text = chatStarterText(t);
  return h('div', { class: 'callout warn live-box' },
    h('b', null, '실게임 시험 단계 · 개발컴 Claude 대화에서 진행'),
    h('div', null, `이 단계는 자동 실행기가 손대지 않습니다${t.live_from ? ` (원래 담당 ${person(t.live_from).name} → 개발컴 Claude로 이관)` : ''}. 개발컴에서 Claude 대화를 열고 아래 문구를 붙여 넣으면 바로 시험·수정할 수 있습니다. 개발컴 Claude 수신함에도 같은 안내가 갑니다.`),
    h('div', { class: 'row', style: { 'margin-top': '8px' } }, h('button', { class: 'btn primary', onclick: async () => {
      try { await navigator.clipboard.writeText(text); toast('대화 시작 문구를 복사했습니다. 개발컴 Claude 대화에 붙여 넣으세요.'); } catch { modal('대화 시작 문구', h('pre', { class: 'pre' }, text)); }
    } }, icon('send'), '대화 시작 문구 복사')));
}
function openTopic(t) {
  S._openingTopic = t.id;
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
    conflictBox(t),
    parkedBox(t),
    t.chain ? chainBox(t) : linkBox(t),
    priorContextBox(t),
    flowRibbon(t),
    commandBox(t),
    testBox(t),
    phaseLine(t),
    gateBox(t),
    liveBox(t),
    t.dispatch_reason ? h('div', { class: 'reason' }, h('b', null, t.assign_by === 'user' ? '담당 지정: ' : t.assign_by === 'handoff' ? '인계: ' : '배분 근거: '), t.dispatch_reason) : null,
    workBox(t, true),
    runsFor(t.id).length ? [h('h4', null, `자동 실행 이력 ${runsFor(t.id).length}`), h('div', { class: 'run-list' }, runsFor(t.id).slice(0, 8).map(runRow))] : null,
    t.status === 'backlog' ? activateControl(t) : null,
    t.command_mode || S.data.meta.command_epoch ? null : assignControl(t),
    h('dl', { class: 'fields' }, h('dt', null, '담당'), h('dd', null, t.assignee ? person(t.assignee).full : '미배정'),
      h('dt', null, '지금 차례'), h('dd', null, t.turn ? `${person(t.turn).full} · ${t.status === 'new' ? '분배' : !t.plan ? '진행 베이스 작성' : t.turn !== t.assignee ? '교차 검토' : '진행'}` : '—'),
      h('dt', null, '선호'), h('dd', null, ({ auto: '자동 분배', claude: 'Claude 우선', astra: 'Astra 우선' })[t.prefer] || '—'),
      h('dt', null, '받은 시각'), h('dd', null, fmtAbs(t.created_at)), h('dt', null, '경로'), h('dd', null, t.source || '—')),
    t.body ? [h('h4', null, '원래 메모'), h('pre', { class: 'pre' }, t.body)] : null,
    planRows.length ? [h('h4', null, `진행 베이스 · ${person(t.plan_by).name}`), h('div', { class: 'plan callout' }, planRows.map(([k, l]) => h('div', null, h('h4', null, l),
      Array.isArray(plan[k]) ? h('ul', null, plan[k].map(x => h('li', null, x))) : h('div', null, plan[k]))))] : null,
    [h('h4', null, `메모·검토 ${(t.notes || []).length}`), (t.notes || []).length ? h('div', { class: 'note-thread' }, t.notes.map(n => h('div', { class: 'note' }, av(n.by, false),
      h('div', { class: 'bubble' }, h('div', { class: 'h' }, h('b', null, person(n.by).name), h('span', { class: 'tag' }, NOTE_KIND[n.kind] || n.kind || '메모'), h('span', null, fmtAbs(n.ts))), h('p', null, n.body)))))
      : empty('아직 메모가 없습니다. 서버컴 Astra가 목표를 정리하고 작업을 배정합니다.')],
    t.chain ? h('details', { class: 'doc-fold' }, h('summary', null, h('b', null, `줄기 전체 히스토리 · ${t.chain.members.length}개 주제를 한 라인으로`)), historyPanel(t, null).slice(1)) : null,
    thread({ kind: 'topic', id: t.id, title: t.title }, () => openTopic(S.d.topics.find(x => x.id === t.id) || t), { placeholder: 'Astra에게 목표 수정·검토 의견을 남기세요', to: t.commander || t.assignee || 'server-astra' }));
}

// ------------------------------------------------------------ 기타
function toast(text) {
  let t = $('.toast');
  if (!t) { t = h('div', { class: 'toast', role: 'status', 'aria-live': 'polite' }); document.body.append(t); }
  t.textContent = text; t.classList.add('on');
  clearTimeout(S._toast); S._toast = setTimeout(() => t.classList.remove('on'), 2600);
}
// ------------------------------------------------------------ 내 차례 키보드 조작(아키텍트 요청 2026-10-03 · 텐키리스 기준)
// 물리 키(e.code)로 판정해 한글 입력 상태에서도 글자 키가 동작한다. 입력칸 안에서는 Ctrl+Enter(보내기)·Esc(빠져나오기)만 받는다.
// 내 차례 화면과 그 '크게 보기' 창에서만 동작하고, 다른 창이 열려 있거나 휴대폰 폭이면 아무것도 하지 않는다.
function kbHint() {
  return h('div', { class: 'kb-hint' }, '↑↓ 항목 · ←→ 탭 · 1-9 선택 · R 답 쓰기 · Enter 보내기 · PgUp/PgDn 히스토리 · ? 도움말');
}
const KB_HELP = [
  ['목록·탭', [['↑ / ↓', '이전·다음 항목(오른쪽 상세가 바로 바뀜)'], ['Home / End', '첫·마지막 항목'], ['← / →', '탭 이동'], ['O', '크게 보기(가운데 창)'], ['Esc', '창 닫기 · 입력칸 빠져나오기(쓰던 글 유지)']]],
  ['선택·답하기', [['1 ~ 9', '선택지 고르기(같은 번호 다시 누르면 해제) · 착수 고르기에서는 담당 고르기'], ['R', '답 입력칸으로'],
    ['Enter', '보내기(고른 선택지 + 덧붙일 말). 아무것도 없으면 입력칸으로'], ['입력칸 안: Enter · Ctrl+Enter · Esc', '줄바꿈 · 보내기 · 빠져나오기'],
    ['Y · N · L', '실게임·확인: 확인 완료 · 문제 있음(내용 적고 Ctrl+Enter) · 나중에'], ['X', 'AI 질문·할 일: 답 없이 확인함 · 했음'], ['A', '착수 고르기: 자동 배분으로 착수'],
    ['보낸 뒤', '자동으로 다음 항목']]],
  ['히스토리(오른쪽 칸)', [['PgUp / PgDn', '한 화면씩 위·아래'], ['Shift+↑ / Shift+↓', '이전·다음 기록 하나씩(강조)'], ['E', '강조한 기록 펼치기·접기'],
    ['Shift+Home / Shift+End', '맨 처음 · 마지막'], ['Space / Shift+Space', '가운데 본문 아래·위로']]],
  ['도움말', [['? 또는 F1', '이 표 열기·닫기']]],
];
function kbHelp() {
  if (document.querySelector('.drawer.on[data-kb="help"]')) return closeDrawer();
  modal('키보드 단축키 · 결재함', h('div', { class: 'kb-help' }, KB_HELP.map(([title, rows]) => [h('h4', null, title),
    h('table', { class: 'kb-table' }, h('tbody', null, rows.map(([k, d]) => h('tr', null, h('th', null, k), h('td', null, d)))))])),
    h('p', { class: 'hint' }, '한글 입력 상태에서도 글자 키가 그대로 동작합니다. 입력칸 안에서는 단축키가 꺼집니다.'));
  const p = [...document.querySelectorAll('.drawer.modal')].pop();
  if (p) p.dataset.kb = 'help';
}
// 지금 키보드가 조작하는 곳: 맨 위 '크게 보기' 창 또는 내 차례 오른쪽 상세
function kbScope() {
  const top = [...document.querySelectorAll('.drawer.on')].pop();  // 닫히는 중인 창(on 빠짐)은 제외
  if (top) return top.dataset.kb === 'mine' ? { el: top, key: top.dataset.key, modal: true } : top.dataset.kb === 'help' ? { help: true } : null;
  if (!S.data || S.view !== 'mine') return null;
  return { el: document.querySelector('.mine-detail'), key: S.mineSel, modal: false };
}
const kbItem = key => mineItems().find(i => i.key === key) || null;
function kbShowRow(key) {
  const r = [...document.querySelectorAll('.mine-row')].find(x => x.dataset.key === key);
  r?.scrollIntoView({ block: 'nearest' });
}
function kbSelect(sc, item) {
  if (!item) return;
  S.mineSel = item.key; S.kbPick = null; S.kbIntent = null; S.editTopic = null;
  if (sc.modal) { closeDrawer(true); openMineItem(item); }
  S._keepScroll = true; render(); kbShowRow(item.key);
}
function kbMove(sc, d) {
  const list = mineList();
  if (!list.length) return toast('이 탭에는 항목이 없습니다');
  const i = list.findIndex(x => x.key === sc.key);
  const n = d === 'first' ? 0 : d === 'last' ? list.length - 1 : Math.max(0, Math.min(list.length - 1, (i < 0 ? (d > 0 ? -1 : list.length) : i) + d));
  kbSelect(sc, list[n]);
}
function kbTab(sc, d) {
  const tabs = ['all', ...MINE_TYPES.map(x => x[0])];
  const i = tabs.indexOf(S.f.mine || 'all');
  if (sc.modal) closeDrawer(true);
  S.f.mine = tabs[(i + d + tabs.length) % tabs.length]; S.mineSel = null; S.kbPick = null; S.kbIntent = null; S.mineSelecting = false; S.editTopic = null;
  render();
}
// 보내기 → 성공하면 다음 항목으로(보낸 항목이 목록에 남아 있으면 그 다음, 빠졌으면 같은 자리)
async function kbSend(sc, fn) {
  const before = mineList(), at = before.findIndex(x => x.key === sc.key), topicId = before[at]?.topic?.id;
  const ok = await fn();
  if (!ok) return;
  S.kbPick = null; S.kbIntent = null;
  const now = mineList(), still = now.findIndex(x => x.key === sc.key);
  // 다음 항목: 이어지는 ★5 → 같은 주제에 남은 것 → 목록의 다음
  const chained = S.kbChained && now.find(x => x.key === S.kbChained); S.kbChained = null;
  const same = topicId && now.find(x => x.key !== sc.key && x.topic?.id === topicId && x.type !== 'backlog');
  const next = chained || same || (still >= 0 ? now[still + 1] || null : now[Math.min(Math.max(at, 0), now.length - 1)] || null);
  S.mineSel = next ? next.key : null;
  if (sc.modal) { closeDrawer(true); if (next) openMineItem(next); }
  S._keepScroll = true; render(); if (next) kbShowRow(next.key);
  toast(chained ? '보냄 · 이어서 ★5 배포본 결정' : same ? '보냄 · 같은 주제의 다음 결정' : next ? '보냄 · 다음 항목' : '보냄 · 남은 항목 없음');
}
function kbEnter(sc) {
  const it = kbItem(sc.key);
  if (!it || !sc.el) return;
  const ta = sc.el.querySelector('[data-kb-reply]');
  const text = ta ? ta.value.trim() : '';
  if (it.type === 'gate' || it.type === 'decision') {
    const q = it.ref, pick = S.kbPick && S.kbPick.id === q.id ? (q.options || [])[S.kbPick.idx] : '';
    if (!pick && !text) return ta?.focus();
    return kbSend(sc, () => decide(q, pick || '', text, null));
  }
  if (it.type === 'action' && it.ref.kind === 'conflict') {
    const who = conflictWho(it.topic);
    if (!S.kbPick || S.kbPick.id !== it.ref.id) return toast('숫자로 누가 계속할지 먼저 고르세요');
    return kbSend(sc, () => resolveConflict(it.topic, who[S.kbPick.idx]));
  }
  if (it.type === 'backlog') {
    const b = sc.el.querySelector('[data-kb-assign]');
    if (b && S.kbPick && S.kbPick.id === it.topic.id) return kbSend(sc, () => b._kb({ quiet: true }));
    if (text && ta._send) return kbSend(sc, () => ta._send({ quiet: true }));
    return ta?.focus();
  }
  if (!ta || !ta._send) return;
  if (!text) return ta.focus();
  if (it.type === 'test' && S.kbIntent === it.key) {  // N(문제 있음): 내용을 담당에게 보내고 문제 있음으로
    const pb = sc.el.querySelector('[data-kb-problem]');
    return kbSend(sc, async () => { const ok = await ta._send({ quiet: true }); if (ok && pb) pb.click(); return ok; });
  }
  return kbSend(sc, () => ta._send({ quiet: true }));
}
function kbDigit(sc, n) {
  const it = kbItem(sc.key);
  if (!it || !sc.el) return;
  if (it.type === 'gate' || it.type === 'decision') {
    const opts = it.ref.options || [];
    if (n >= opts.length) return toast(opts.length ? `선택지는 ${opts.length}개입니다` : '선택지가 없습니다 · R로 직접 적기');
    S.kbPick = S.kbPick && S.kbPick.id === it.ref.id && S.kbPick.idx === n ? null : { id: it.ref.id, idx: n };
    sc.el.querySelectorAll('[data-kb-opt]').forEach(b => b.classList.toggle('kb-picked', !!S.kbPick && Number(b.dataset.kbOpt) === S.kbPick.idx));
    return toast(S.kbPick ? `${n + 1}번 고름 · Enter로 보내기(R로 덧붙일 말)` : '선택 해제');
  }
  if (it.type === 'action' && it.ref.kind === 'conflict') {
    const who = conflictWho(it.topic);
    if (n >= who.length) return toast(`고를 작업자는 ${who.length}명입니다`);
    S.kbPick = S.kbPick && S.kbPick.id === it.ref.id && S.kbPick.idx === n ? null : { id: it.ref.id, idx: n };
    sc.el.querySelectorAll('[data-kb-opt]').forEach(b => b.classList.toggle('kb-picked', !!S.kbPick && Number(b.dataset.kbOpt) === S.kbPick.idx));
    return toast(S.kbPick ? `${person(who[n]).name}가 계속 · Enter로 보내기` : '선택 해제');
  }
  if (it.type === 'backlog') {
    const sel = sc.el.querySelector('[data-kb-agent]'), o = sel?.options[n + 1];
    if (!o) return toast('그 번호의 담당이 없습니다');
    if (o.disabled) return toast('배정 잠금한 작업자입니다');
    const same = S.kbPick && S.kbPick.id === it.topic.id && S.kbPick.agent === o.value;
    S.kbPick = same ? null : { id: it.topic.id, agent: o.value };
    sel.value = same ? '' : o.value; sel.classList.toggle('kb-picked', !same);
    return toast(same ? '선택 해제' : `${o.textContent} · Enter로 이 담당 착수`);
  }
}
function kbHist(sc, d) {
  const side = sc.el?.querySelector('.ms-side');
  if (!side) return;
  const items = [...side.querySelectorAll('.hist-item')];
  if (!items.length) return;
  const cur = side.querySelector('.hist-item.kb-hl'), i = cur ? items.indexOf(cur) : (d > 0 ? -1 : items.length);
  const next = items[Math.max(0, Math.min(items.length - 1, i + d))];
  cur?.classList.remove('kb-hl'); next.classList.add('kb-hl');
  side.scrollTop += next.getBoundingClientRect().top - side.getBoundingClientRect().top - side.clientHeight / 2 + next.offsetHeight / 2;
}
document.addEventListener('keydown', e => {
  if (e.isComposing || e.keyCode === 229) return;  // 한글 조합 중
  const sc = kbScope();
  if (!sc) return;
  const isHelpKey = e.code === 'F1' || (e.code === 'Slash' && e.shiftKey) || e.key === '?';
  if (sc.help) { if (isHelpKey) { e.preventDefault(); closeDrawer(); } return; }
  if (matchMedia('(max-width: 880px)').matches) return;  // 휴대폰·좁은 화면은 그대로
  const tgt = e.target;
  if (tgt && tgt.matches && tgt.matches('input, textarea, select, [contenteditable="true"]')) {
    if (e.code === 'Enter' && (e.ctrlKey || e.metaKey) && tgt.matches('[data-kb-reply]')) { e.preventDefault(); kbEnter(sc); }
    return;  // Esc는 아래 공통 처리(빠져나오기)
  }
  if (e.altKey || ((e.ctrlKey || e.metaKey) && e.code !== 'Enter')) return;  // 브라우저·운영체제 단축키는 그대로
  const c = e.code, sh = e.shiftKey, act = fn => { e.preventDefault(); fn(); };
  const side = sc.el?.querySelector('.ms-side'), main = sc.el?.querySelector('.ms-main');
  if (isHelpKey) return act(kbHelp);
  if (sh && c === 'ArrowUp') return act(() => kbHist(sc, -1));
  if (sh && c === 'ArrowDown') return act(() => kbHist(sc, 1));
  if (sh && c === 'Home') return act(() => { if (side) side.scrollTop = 0; });
  if (sh && c === 'End') return act(() => { if (side) side.scrollTop = side.scrollHeight; });
  if (c === 'ArrowUp') return act(() => kbMove(sc, -1));
  if (c === 'ArrowDown') return act(() => kbMove(sc, 1));
  if (c === 'Home') return act(() => kbMove(sc, 'first'));
  if (c === 'End') return act(() => kbMove(sc, 'last'));
  if (c === 'ArrowLeft') return act(() => kbTab(sc, -1));
  if (c === 'ArrowRight') return act(() => kbTab(sc, 1));
  if (c === 'PageUp' || c === 'PageDown') return act(() => side?.scrollBy({ top: (c === 'PageUp' ? -1 : 1) * side.clientHeight * 0.9 }));
  if (c === 'Space') return act(() => main?.scrollBy({ top: (sh ? -1 : 1) * main.clientHeight * 0.8 }));
  if (c === 'Enter' || c === 'NumpadEnter') return act(() => kbEnter(sc));
  const dm = /^Digit([1-9])$/.exec(c);
  if (dm && !sh) return act(() => kbDigit(sc, Number(dm[1]) - 1));
  if (sh) return;
  if (c === 'KeyO') return act(() => { const it = kbItem(sc.key); if (it && !sc.modal) openMineItem(it); });
  if (c === 'KeyR') return act(() => { const ta = sc.el?.querySelector('[data-kb-reply]'); if (ta) { ta.focus(); ta.scrollIntoView({ block: 'nearest' }); } else toast('이 항목에는 입력칸이 없습니다'); });
  if (c === 'KeyE') return act(() => side?.querySelector('.hist-item.kb-hl .linkish')?.click());
  const km = /^Key([YNLXA])$/.exec(c);
  if (km) {
    const b = sc.el?.querySelector(`[data-kb-key="${km[1].toLowerCase()}"]`);
    if (!b) return;
    e.preventDefault();
    if (km[1] === 'N') {  // 문제 있음: 먼저 무엇이 문제인지 적게 한다
      S.kbIntent = sc.key;
      const ta = sc.el.querySelector('[data-kb-reply]');
      if (ta) { ta.focus(); ta.scrollIntoView({ block: 'nearest' }); toast('문제 내용을 적고 Ctrl+Enter — 담당에게 보내고 문제 있음으로 표시합니다'); } else b.click();
      return;
    }
    kbSend(sc, async () => (b._kb ? b._kb({ quiet: true }) : (b.click(), true)));
  }
});
document.addEventListener('keydown', e => {
  // Esc: 입력칸 안이면 빠져나오기만(쓰던 글 유지), 아니면 창 닫기
  if (e.key === 'Escape' && e.target?.matches?.('input, textarea, select')) { e.target.blur(); return; }
  if (e.key === 'Escape') { closeDrawer(); $('.side')?.classList.remove('on'); }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k' && S.data) { e.preventDefault(); const i = $('.top-search input'); i?.focus(); }
});
// 해시 이동은 popstate가 먼저 처리한다(restoreScreen이 이 기록에 화면 식별값을 써 둠). popstate가 오지 않은 경우에만 여기서 한 번 그린다
window.addEventListener('hashchange', () => { if (S.data && location.href !== lastRestoredHref) restoreScreen(); });
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


// 사령탑 작업실: 주제 하나에서 목표·하위 작업·근거·결재·배포를 추적한다.
function commandBox(t) {
  if (!t.command_mode && !t.archived) return null;
  if (t.archived) return h('section', { class: 'callout' }, h('b', null, '재시작 전 기록'),
    h('p', null, '이전 이력과 결과물은 보존했습니다. 이전 결재는 새 작업을 진행시키지 않습니다.'),
    topicTag(t.restarted_as));
  const rows = t.command?.tasks || [], labels = { ready: '실행 대기', review: 'Astra 검수', accepted: '검수 통과', blocked: 'Astra 조정 중' };
  return h('section', { class: 'command-box card' }, h('h3', null, '서버컴 Astra가 총괄합니다'),
    h('p', { class: 'muted' }, rows.length ? `작업 ${rows.filter(x => x.state === 'accepted').length}/${rows.length} 검수 통과 · 현재 ${t.turn ? person(t.turn).full : '결재·배포 대기'}` : '원래 목표와 완료 기준을 정리한 뒤 실행 작업자에게 배정합니다.'),
    t.restart_of ? h('div', { class: 'row' }, h('span', null, '이전 기록'), topicTag(t.restart_of)) : null,
    rows.map(x => h('details', { class: 'command-task', open: x.state === 'review' || x.state === 'blocked' },
      h('summary', null, h('b', null, x.title), h('span', { class: 'tag' }, labels[x.state] || x.state), h('span', { class: 'muted' }, person(x.assignee).full)),
      h('dl', { class: 'fields' }, h('dt', null, '맡은 범위'), h('dd', null, x.scope), h('dt', null, '완료 기준'), h('dd', null, x.done_when),
        h('dt', null, '선행 작업'), h('dd', null, (x.depends_on || []).join(', ') || '없음')),
      x.feedback ? h('p', null, (x.accepted_acting_for ? '개발컴 대행 검수: ' : 'Astra 검토: ') + x.feedback) : null,
      x.result ? [h('p', null, x.result.summary), h('details', null, h('summary', null, `검증 근거 ${(x.result.evidence || []).length}개`),
        (x.result.evidence || []).map(e => h('p', { class: 'mono' }, e.path + ' · SHA256 ' + e.sha256)))] : null)),
    t.command?.rejected?.length ? h('p', { class: 'hint' }, '낡거나 중복된 응답은 적용하지 않았습니다. 전체 기록에서 확인할 수 있습니다.') : null);
}
// 진행 9단계 + 보관·완료. 세 번째 값은 짧은 툴팁(화면 본문에는 쓰지 않는다)
const FLOW_STAGES = [
  ['saved','주제 보관','시작 전 · 자동 착수 안 함'],
  ['goal','목표 정리','Astra · 목표·완료 기준·작업 나누기'],
  ['execute','실행','작업자 · 조사·구현'],
  ['review','Astra 검수','Astra · 수락 또는 재작업'],
  ['test','자동 시험','개발컴 · 빌드·격리 시험'],
  ['decision','아키텍트 검토','결재함 · ★4 실게임 시험 등'],
  ['pack','배포본 작성','개발컴 · 변경 파일·적용·복구 절차'],
  ['prep','서버 준비','서버컴 · 수신·해시 확인'],
  ['queue','배포 대기','배포 메뉴 · 묶음 고르기'],
  ['deploy','묶음 배포','서버컴 Astra 대화 · ★7 승인 범위만'],
  ['done','완료','★9 완료 확정'],
];
function flowStage(t) {
  if (t.status === 'backlog') return 'saved';
  if (t.status === 'done') return 'done';
  if (t.status === 'review_user' || (S.data.decisions_needed || []).some(q => q.task_id === t.id && !S.d.answers[q.id])) return 'decision';
  if (['test','pack','prep','queue','deploy'].includes(t.stage)) return t.stage;
  const tasks = t.command?.tasks || [];
  if (!tasks.length) return 'goal';
  if (tasks.some(x => ['review','blocked'].includes(x.state)) || tasks.every(x => x.state === 'accepted')) return 'review';
  return 'execute';
}
function flowRibbon(t) {
  if (!t.command_mode || t.archived) return null;
  const at = flowStage(t);
  return h('ol', { class: 'topic-flow', 'aria-label': '전체 단계와 현재 위치' }, FLOW_STAGES.map(([id,label],i) =>
    h('li', { class: id === at ? 'current' : '', 'aria-current': id === at ? 'step' : null }, `${id === 'saved' || id === 'done' ? '' : i + '. '}${label}`, id === at ? ' · 현재' : '')));
}
// 진행 현황(아키텍트 원칙: 데스크톱 한 화면 · 목록 카드는 3건 + 더보기 · 가로 배치 · 경고 옆 같은 자리 행동 버튼)
// 구성: 머리줄(검색·보류·새 주제) → 요약 4칸(결재할 일 · 막힘 · 자동 시험 · 전체 상태) → 단계 막대(필터 하나) → 단계 보드
function vProgress() {
  const all = S.d.topics.filter(t => !['parked', 'dropped'].includes(t.status) && !t.followed);
  const q = S.f.progressQ || '', selected = S.f.flowStage || 'all';
  const list = all.filter(t => (t.title + ' ' + t.id + ' ' + (t.body || '')).toLowerCase().includes(q.toLowerCase()));
  const groups = FLOW_STAGES.filter(([id]) => selected === 'all' || id === selected);
  const running = all.filter(t => !['done','backlog'].includes(t.status)).length;
  const parkedN = S.d.topics.filter(t => t.status === 'parked' && !t.archived).length;
  const one = selected !== 'all';
  return [head('', '진행 현황', `진행 ${running}건`,
      h('input', { type: 'search', class: 'progress-search', 'aria-label': '진행 중인 주제 검색', 'data-focus': 'progress-search', placeholder: '주제·내용 검색', value: q,
        oninput: e => { S.f.progressQ = e.target.value; S._keepScroll = true; render(); } }),
      h('button', { class: 'btn', onclick: () => go('parked') }, icon('pause'), `보류 ${parkedN}건`),
      h('button', { class: 'btn primary', onclick: openComposer }, icon('send'), '새 주제')),
    S.data.meta.command_version && !S.data.meta.command_epoch ? h('div',{class:'callout warn'},h('b',null,'사령탑 전환 준비 중'),h('p',null,(S.data.meta.command_pending||['PC 동기화 확인 중']).join(' · '))) : null,
    progressSummary(all),
    stageStrip(list, selected),
    h('div', { class: `command-board full-flow${one ? ' one' : ''}`, 'data-selected': selected }, groups.map(([id,label,desc]) => {
      const rows = list.filter(t=>flowStage(t)===id).sort((a,b)=>(a.priority||'P2').localeCompare(b.priority||'P2')||toMs(b.updated_at)-toMs(a.updated_at));
      const number = id === 'saved' ? '·' : id === 'done' ? '✓' : FLOW_STAGES.findIndex(x=>x[0]===id);
      const open = one || S.f['expand:' + id];
      return h('section', { class: 'card flow-lane', 'data-stage': id, 'aria-label': label },
        h('h2', { title: desc }, h('span', { class: 'flow-number' }, number), label, h('span', { class: 'badge' }, rows.length)),
        rows.length ? h('div', { class: 'lane-cards' }, rows.slice(0, open ? rows.length : 3).map(t => laneCard(t, id, label))) : h('div', { class: 'lane-empty' }, '없음'),
        !one && rows.length > 3 ? h('button', { class: 'more-btn lane-more', onclick: () => { S.f['expand:' + id] = !S.f['expand:' + id]; S._keepScroll = true; render(); } },
          S.f['expand:' + id] ? '접기' : `${rows.length - 3}건 더 보기`) : null);
    }))];
}
// 단계 보드 카드 두 줄: 제목 / 지금 상태 · 담당 · 시간(하위 작업 수 등은 툴팁)
function laneCard(t, id, label) {
  const ans = t.gate && S.d.answers[t.gate.id];
  const state = id === 'decision' ? `${t.gate?.label || '아키텍트 결정'} · ${ans ? '답 보냄 · 반영 대기' : '결재함에서 결정'}`
    : testHeadline(t) || (id === 'queue' ? '배포 메뉴에서 묶음 고르기' : id === 'done' ? '완료 확정' : t.gate?.label || label);
  const tasks = t.command?.tasks || [];
  const cur = t.turn ? workOf(t, t.turn) : null;
  const astraRun = isRunning(runOf(t.assignee, t.id));
  const now = id === 'goal' && t.command_mode ? (astraRun ? 'Astra가 작업 나누는 중' : '배정 대기 · Astra 작업 나누기 전')
    : cur && ['execute', 'test', 'review'].includes(id) ? `${person(t.turn).name} ${cur.state.label}` : null;
  const who = now || (t.turn ? person(t.turn).name : id === 'decision' ? '아키텍트' : null);
  const meta = [tasks.some(x => x.attempt > 1) ? '검토 의견 반영 중' : null, who, fmtRel(t.updated_at)].filter(Boolean).join(' · ');
  return h('button', { class: `command-card${id === 'decision' && !ans ? ' need' : ''}`, onclick: () => openTopic(t),
    title: [t.title, state, tasks.length ? `하위 작업 ${tasks.filter(x => x.state === 'accepted').length}/${tasks.length} 검수 통과` : null, meta].filter(Boolean).join('\n') },
    h('b', { class: 'clamp-1' }, t.title),
    h('span', { class: `clamp-1${testHeadline(t) ? ' test-headline' : ''}` }, state, h('small', null, ' · ', meta)));
}
// 단계 막대 = 필터 하나(예전 '단계별 주제 분포' 그래프와 단계 버튼을 합침). 막대 높이는 주제 수
function stageStrip(list, selected) {
  const counts = Object.fromEntries(FLOW_STAGES.map(([id]) => [id, list.filter(t => flowStage(t) === id).length]));
  const max = Math.max(1, ...Object.values(counts));
  const pick = id => { S.f.flowStage = id; S._keepScroll = true; render(); };
  return h('nav', { class: 'flow-overview', 'aria-label': '단계별 주제 수 · 눌러서 그 단계만 보기' },
    h('button', { class: `stage-all${selected === 'all' ? ' selected' : ''}`, 'aria-label': '전체 단계', 'aria-pressed': String(selected === 'all'), onclick: () => pick('all') }, h('b', null, '전체 단계'), h('span', { class: 'n' }, list.length)),
    FLOW_STAGES.map(([id, label, desc], i) => h('button', { class: selected === id ? 'selected' : '', 'aria-pressed': String(selected === id), title: desc,
      'aria-label': `${label} ${counts[id]}건 보기`, onclick: () => pick(selected === id ? 'all' : id) },
      h('small', null, id === 'saved' ? '보관' : id === 'done' ? '완료' : String(i)), h('b', null, label),
      h('span', { class: 'stage-meter', 'aria-hidden': 'true' }, h('i', { style: { width: `${counts[id] / max * 100}%` } })),
      h('span', { class: 'n' }, counts[id]))));
}

const TEST_STATES = {pending:'대기',running:'실행 중',review:'통과 · Astra 검수 대기',passed:'통과',failed:'실패 · 수정/재시험',blocked:'환경·의존 문제',skipped:'Astra 판단으로 제외'};
// 서버컴 화면 계약(10-03): passed라도 사령탑 수락(accepted_by)이 없으면 '검수 대기' — 최종 통과로 세지 않는다
const testState = x => x.state === 'passed' && !x.accepted_by ? 'review' : x.state;
function testHeadline(t) {
  const rows = t.command?.tests || [];
  if (!rows.length || t.stage !== 'test') return '';
  const at = rows.find(x=>!['passed','skipped'].includes(testState(x)));
  return `시험 ${rows.filter(x=>testState(x)==='passed').length}/${rows.length} 통과` + (at ? ` · ${at.title}: ${TEST_STATES[testState(at)]}` : ' · 결과 정리');
}
function testBox(t) {
  const rows = t?.command?.tests || [];
  if (!rows.length || t.archived) return null;
  const byId = Object.fromEntries(rows.map(x=>[x.id,x.title]));
  return h('section', {class:'card test-box'}, h('h3', null, '시험 과정과 결과'),
    t.test_reset_needed ? h('p', {class:'callout warn'}, '아키텍트 검토 의견을 반영하여 Astra가 재시험을 준비합니다.') : null,
    rows.map((x,i)=>h('details', {class:`test-item ${testState(x)}`,open:['running','failed','blocked','review'].includes(testState(x))},
      h('summary', null,h('b',null,`${i+1}. ${x.title}`),h('span',{class:'tag'},TEST_STATES[testState(x)]||x.state)),
      h('dl',{class:'fields'},h('dt',null,'담당'),h('dd',null,person(x.assignee).full),
        h('dt',null,'선행 시험'),h('dd',null,(x.depends_on||[]).map(id=>byId[id]||id).join(' → ')||'없음'),
        h('dt',null,'방법·환경'),h('dd',null,x.method),h('dt',null,'통과 기준'),h('dd',null,x.expected),
        h('dt',null,'시작 / 마지막 기록'),h('dd',null,`${fmtAbs(x.started_at)} / ${fmtAbs(x.updated_at)}`),
        h('dt',null,'시도'),h('dd',null,`${x.attempt}회`)),
      x.accepted_acting_for ? h('p',{class:'tag'},'개발컴 대행 검수 · '+person(x.accepted_by).full) : null,
      x.summary ? h('p',null,x.summary) : h('p',{class:'muted'},'실행 결과가 아직 없습니다.'),
      x.evidence?.length ? h('details',null,h('summary',null,`실제 로그 근거 ${x.evidence.length}개`),x.evidence.map(e=>h('p',{class:'mono'},`${e.path} · SHA256 ${e.sha256}`))) : null,
      x.history?.length ? h('details',null,h('summary',null,`이전 시도·진행 기록 ${x.history.length}건`),x.history.map(e=>h('p',null,`${fmtAbs(e.ts)} · ${person(e.agent).full} · ${e.op}: ${e.body}`))) : null)));
}
// 진행 현황 위쪽 4칸: 결재할 일(결재함과 같은 기준) · 막힘(행동 버튼) · 자동 시험 · 전체 상태
function progressSummary(all) {
  const active = all.filter(t=>!['done','backlog'].includes(t.status));
  const ap = approvals();
  const blocked = active.map(t=>{
    const check=t.stage === 'test' ? (t.command?.tests||[]).find(x=>['failed','blocked'].includes(x.state)) : null;
    const task=(t.command?.tasks||[]).find(x=>x.state==='blocked');
    const who=(S.data.agents||[]).find(a=>a.id===t.turn);
    const offline=who?.last_seen && hoursSince(who.last_seen)>1;
    const why=check ? `${check.title} · ${TEST_STATES[check.state]}` : task ? (task.feedback || `${task.title} · Astra 조정 중`) : t.open_request ? `작업자 응답 대기 · ${person(t.open_request.to).full}` : offline ? `${person(t.turn).name} 신호 1시간 넘게 없음` : null;
    if (!why) return null;
    const act = check ? ['시험 결과 보기', () => { openTopic(t); requestAnimationFrame(() => document.querySelector('.drawer .test-item.failed, .drawer .test-item.blocked')?.scrollIntoView({ block: 'center' })); }]
      : offline ? ['작업자 상태', () => go('agents')] : ['주제 열기', () => openTopic(t)];
    return {t,why,act,at:check?.updated_at||t.open_request?.ts||t.updated_at};
  }).filter(Boolean);
  const showAllBlocked = !!S.f.blockedAll;
  const tested = all.filter(t=>t.stage==='test' && t.command?.tests?.length);
  const openMine = it => { S.f.mine = 'all'; S.mineSel = it.key; go('mine'); };
  const n = st => all.filter(t => st.includes(t.status)).length;
  const stat = (label, val, fn) => h(fn ? 'button' : 'div', { class: 'ps-stat', onclick: fn || null }, h('b', null, val), h('span', null, label));
  return h('section',{class:'progress-summary','aria-label':'결재와 병목 요약'},
    h('div',{class:'card ps-card'},
      h('div', { class: 'card-h' }, h('h2',null,`결재할 일 ${ap.total}건`), moreBtn(ap.total - 3, () => go('mine'))),
      ap.open.length ? ap.open.slice(0, 3).map(it => h('button', { class: 'summary-topic', onclick: () => openMine(it) },
        h('b', { class: 'clamp-1' }, it.topic ? it.topic.title : it.title), h('span', { class: 'clamp-1' }, it.type === 'gate' ? it.sub : MINE_TYPE[it.type]?.label || ''))) : h('p',{class:'muted'},'지금 결재할 일이 없습니다.'),
      ap.waiting.length ? h('div', { class: 'ps-wait', title: ap.waiting.map(x => x.topic ? x.topic.title : x.q.id).join('\n') }, icon('clock'), `답 보냄 · 반영 대기 ${ap.waiting.length}건`) : null),
    h('div',{class:'card ps-card'},
      h('div', { class: 'card-h' }, h('h2',null,`막힘·응답 대기 ${blocked.length}건`),
        blocked.length > 3 ? h('button', { class: 'more-btn', onclick: () => { S.f.blockedAll = !showAllBlocked; S._keepScroll = true; render(); } }, showAllBlocked ? '접기' : `더보기 +${blocked.length - 3}`) : null),
      blocked.length ? blocked.slice(0, showAllBlocked ? blocked.length : 3).map(x => h('div', { class: 'summary-topic blocked-row' },
        h('div', { class: 'grow' }, h('b', { class: 'clamp-1' }, x.t.title), h('span', { class: 'clamp-1' }, x.why)),
        h('button', { class: 'btn sm', onclick: x.act[1] }, x.act[0]))) : h('p',{class:'muted'},'막힌 주제가 없습니다.')),
    h('div',{class:'card ps-card'},
      h('div', { class: 'card-h' }, h('h2',null,`자동 시험 ${tested.length}건`), tested.length > 3 ? moreBtn(tested.length - 3, () => { S.f.flowStage = 'test'; S._keepScroll = true; render(); }) : null),
      tested.length ? tested.slice(0, 3).map(t=>h('button',{class:'test-chart-row',onclick:()=>{openTopic(t);requestAnimationFrame(()=>document.querySelector('.drawer .test-box')?.scrollIntoView({block:'start'}));}},
        h('b',{class:'clamp-1'},t.title),h('span',{class:'test-segments','aria-label':testHeadline(t)},(t.command.tests||[]).map(x=>h('span',{class:`test-segment ${testState(x)}`,title:`${x.title}: ${TEST_STATES[testState(x)]}`},h('span',{class:'sr-only'},`${x.title} ${TEST_STATES[testState(x)]}`)))),
        h('small',{class:'clamp-1'},testHeadline(t)))) : h('p',{class:'muted'},'자동 시험 중인 주제가 없습니다.'),
      tested.length ? h('div',{class:'test-legend'},Object.entries(TEST_STATES).map(([state,label])=>h('span',{title:label},h('i',{class:`test-segment ${state}`}),({pending:'대기',running:'실행',review:'검수 대기',passed:'통과',failed:'실패',blocked:'환경',skipped:'제외'})[state]))) : null),
    h('div',{class:'card ps-card'},
      h('div', { class: 'card-h' }, h('h2',null,'전체 상태')),
      h('div', { class: 'ps-stats' },
        stat('보관', n(['backlog']), () => { S.f.flowStage = 'saved'; S._keepScroll = true; render(); }),
        stat('진행', active.length, null),
        stat('완료', n(['done']), () => go('done')),
        stat('자동 시험', active.filter(t=>t.stage==='test').length, () => { S.f.flowStage = 'test'; S._keepScroll = true; render(); }),
        stat('배포 대기', active.filter(t=>t.stage==='queue').length, () => go('deploy')),
        stat('보류', S.d.topics.filter(t => t.status === 'parked' && !t.archived).length, () => go('parked'))),
      h('p',{class:'hint'},`마지막 동기화 ${fmtRel(S.data.meta.generated_at)}`)));
}
// 기록: 완료(줄기 단위·관문 이력·기간) · 보류(다시 진행) · 전체 요약(줄기 완료율·팀 현황) · 재시작 전 — 한 화면에서 칩으로 오간다
function vHistory() {
  const f = RECORD_KINDS.some(([k]) => k === S.f.recordKind) ? S.f.recordKind : 'done';
  const pick = v => { saveScreen(); S.f.recordKind = v; replaceScreen(routeUrl('history')); render(); window.scrollTo({ top: 0 }); saveScreen(); };
  let sub;
  if (f === 'done') sub = vDone(true);
  else if (f === 'parked') sub = vParked(true);
  else if (f === 'overview') sub = vOverview(true);
  else {
    const rows = S.d.topics.filter(t => t.archived).sort((a, b) => toMs(b.updated_at) - toMs(a.updated_at));
    sub = { small: `재시작 전 ${rows.length}건`, tools: null, body: [h('div', { class: 'done-fit fit-page' }, card('재시작 전 기록', { big: rows.length, unit: '건', cls: 'fill scroll-card' },
      rows.length ? h('div', { class: 'list' }, rows.map(t => h('button', { class: 'item', onclick: () => openTopic(t) },
        h('span', { class: 'body' }, h('b', { class: 'clamp-1' }, t.title), h('span', { class: 's clamp-1' }, `${t.id}${t.restarted_as ? ` → 새 주제 ${(topicById(t.restarted_as) || {}).title || t.restarted_as}` : ''}`))))) : empty('기록이 없습니다.')))] };
  }
  const more = h('details', { class: 'rec-more' }, h('summary', null, '상세 기록'),
    h('div', { class: 'rec-more-b' }, [['messages','작업자 메시지'],['verify','검증 기록'],['brain','통합 검색'],['tasks','이전 업무표'],['topics','이전 주제 보드']].map(([id,label]) => h('button', { class: 'btn sm', onclick: () => go(id) }, label))));
  return [head('', '기록', sub.small, sub.tools),
    h('div', { class: 'rec-bar' }, chips(RECORD_KINDS, f, pick, '기록 종류'), more),
    ...sub.body];
}

function priorContextBox(t) {
  const rows=t?.prior_context||[];
  if (!rows.length) return null;
  return h('section',{class:'card prior-context'},h('h3',null,'이 주제가 이어진 과정'),
    h('ol',{class:'lineage-graph','aria-label':'이전 주제에서 현재까지의 연결'},[...rows,t].map(p=>h('li',null,
      h('button',{class:p.id===t.id?'current':'',onclick:()=>{const x=topicById(p.id);if(x && p.id!==t.id)openTopic(x);}},p.title||p.id),
      h('small',null,p.id===t.id?'현재 주제':(p.decisions||[]).at(-1)?.choice||'이전 기록')))),
    rows.map(p=>h('details',{open:true},h('summary',null,p.title||p.id,p.missing?' · 이전 기록 미수신':''),
      p.missing?null:[h('p',null,p.goal||'원래 목표 기록 없음'),
        (p.decisions||[]).map(d=>h('div',{class:'callout'},h('b',null,`아키텍트 선택: ${d.choice||'메모로 결정'}`),
          h('p',null,d.note||'별도 사유 메모 없음'),h('small',null,fmtAbs(d.answered_at)),
          h('details',null,h('summary',null,'결정 당시 작업 결과'),h('pre',{class:'pre'},d.summary||'결과 요약 없음')))),
        (p.results||[]).map(r=>h('p',null,r.summary)),
        p.tests?.length?h('p',null,`이전 시험: 통과 ${p.tests.filter(x=>testState(x)==='passed').length} / 실패 ${p.tests.filter(x=>x.state==='failed').length} / 제외 ${p.tests.filter(x=>x.state==='skipped').length}`):null,
        p.work_id?h('p',{class:'mono'},`이전 작업물: ${p.work_id}`):null,
        h('button',{class:'btn',onclick:()=>{const x=topicById(p.id);if(x)openTopic(x);else toast('이전 주제 기록이 아직 수신되지 않았습니다.');}},'이전 주제·시험 근거·전체 기록 열기')])),
    h('div',{class:'callout'},h('b',null,'이번 주제의 범위'),h('p',null,t.body||t.title)));
}
