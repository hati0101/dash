// 대시보드 데이터 암호화/복호화 (Node 내장 crypto만 사용).
// 형식은 브라우저 WebCrypto와 같다: PBKDF2-SHA256 → AES-256-GCM, 암호문 뒤에 16바이트 태그.
//   node encrypt.mjs encrypt <출력.json> [--new-salt]   (평문 JSON은 stdin)
//   node encrypt.mjs decrypt <입력.json>                (평문 JSON을 stdout)
//   node encrypt.mjs open-topic -                       (대시보드가 만든 REALTOPIC1 암호문을 stdin으로 받아 평문 JSON을 stdout)
// 비밀번호는 환경변수 REAL_OPS_PASSWORD로만 받는다.
import { pbkdf2Sync, randomBytes, createCipheriv, createDecipheriv } from 'node:crypto';
import { gzipSync, gunzipSync } from 'node:zlib';
import { readFileSync, writeFileSync, existsSync, renameSync } from 'node:fs';

const ITER = 600000;
const [mode, file, ...rest] = process.argv.slice(2);
const password = process.env.REAL_OPS_PASSWORD || '';
if (!password) { console.error('REAL_OPS_PASSWORD가 비어 있습니다.'); process.exit(2); }
if (!['encrypt', 'decrypt', 'open-topic'].includes(mode) || !file) {
  console.error('사용법: node encrypt.mjs encrypt|decrypt|open-topic <파일|->'); process.exit(2);
}

const deriveKey = (salt, iter) => pbkdf2Sync(Buffer.from(password, 'utf8'), salt, iter, 32, 'sha256');
const fromB64url = s => Buffer.from(s.replace(/-/g, '+').replace(/_/g, '/'), 'base64');

if (mode === 'open-topic') {
  const blob = readFileSync(0, 'utf8').trim();
  const parts = blob.split('.');
  if (parts.length !== 4 || parts[0] !== 'REALTOPIC1') { console.error('REALTOPIC1 형식이 아닙니다.'); process.exit(3); }
  const [, salt, iv, data] = parts.map((p, i) => (i ? fromB64url(p) : p));
  if (salt.length !== 16 || iv.length !== 12 || data.length < 17) { console.error('암호문 길이가 맞지 않습니다.'); process.exit(3); }
  try {
    const d = createDecipheriv('aes-256-gcm', deriveKey(salt, ITER), iv);
    d.setAuthTag(data.subarray(data.length - 16));
    const plain = Buffer.concat([d.update(data.subarray(0, data.length - 16)), d.final()]);
    JSON.parse(plain.toString('utf8'));
    process.stdout.write(plain);
  } catch {
    console.error('복호화 실패: 비밀번호가 다르거나 변조된 암호문입니다.'); process.exit(4);
  }
} else if (mode === 'encrypt') {
  const plain = readFileSync(0);
  JSON.parse(plain.toString('utf8')); // 유효한 JSON인지 확인
  let salt = null;
  // --salt-from <파일>: 다른 암호문(메인 게시본)과 같은 salt를 써서 대시보드가 한 키로 모두 열 수 있게 한다
  const sf = rest.indexOf('--salt-from');
  const saltSource = sf >= 0 ? rest[sf + 1] : (!rest.includes('--new-salt') && existsSync(file) ? file : null);
  if (saltSource) {
    try { salt = Buffer.from(JSON.parse(readFileSync(saltSource, 'utf8')).salt, 'base64'); } catch { salt = null; }
    if (sf >= 0 && (!salt || salt.length !== 16)) { console.error('salt를 읽지 못했습니다: ' + saltSource); process.exit(5); }
  }
  if (!salt || salt.length !== 16) salt = randomBytes(16);
  const iv = randomBytes(12);
  const cipher = createCipheriv('aes-256-gcm', deriveKey(salt, ITER), iv);
  const body = Buffer.concat([cipher.update(gzipSync(plain, { level: 9 })), cipher.final(), cipher.getAuthTag()]);
  const out = {
    v: 1, alg: 'AES-256-GCM', kdf: 'PBKDF2-SHA256', iter: ITER, gzip: true,
    salt: salt.toString('base64'), iv: iv.toString('base64'), data: body.toString('base64'),
    published_at: new Date().toISOString(),
  };
  const tmp = file + '.tmp';
  writeFileSync(tmp, JSON.stringify(out));
  renameSync(tmp, file);
  console.log(`암호문 ${body.length.toLocaleString()} bytes, salt ${rest.includes('--new-salt') ? '새로 생성' : '유지/생성'}`);
} else {
  const env = JSON.parse(readFileSync(file, 'utf8'));
  const body = Buffer.from(env.data, 'base64');
  const decipher = createDecipheriv('aes-256-gcm', deriveKey(Buffer.from(env.salt, 'base64'), env.iter), Buffer.from(env.iv, 'base64'));
  decipher.setAuthTag(body.subarray(body.length - 16));
  const plain = Buffer.concat([decipher.update(body.subarray(0, body.length - 16)), decipher.final()]);
  process.stdout.write(env.gzip ? gunzipSync(plain) : plain);
}
