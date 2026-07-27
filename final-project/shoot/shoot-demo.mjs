// 본 촬영 드라이버.
//
// 설계 이유 두 가지:
//  1) **마스터 연속 녹화 + 마크**. 각본이 시간축을 타므로(사건 ~1분, 방어선 ~5분)
//     장면마다 녹화를 끊었다 붙이면 한 번 놓친 순간을 되돌릴 수 없다. 통으로
//     찍고 마크를 남겨 나중에 잘라낸다.
//  2) **시간이 아니라 원장을 기다린다**. "1분쯤"에 카메라를 들이대는 대신
//     화면에 그 종목이 실제로 나타날 때까지 폴링한다. 각본 타이밍이 몇십 초
//     흔들려도 장면이 비지 않는다.
//
// 각본 티커가 어느 패널에 뜨는지는 실측으로 확정했다(추정 금지):
//   NVEX → #allocation(집행된 매수)  ·  HLXM/VRDN → #protection(방어선 발동)
// "판단과 반박"(#judgements)은 cycle_ts=자정인 일일 슬롯만 그린다 — 장중
// 재판단을 일부러 뺀 불변식이라(관제실 숫자 = 잡 원장 숫자) 각본 티커는
// 거기 안 뜬다. 그래서 "근거가 남는다"는 주장은 이어받은 실제 운영 판단
// 카드로 보여주고, 각본 사건은 원장에 남은 결과로 보여준다.
import { execFileSync } from 'node:child_process';
import { writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { attach, evaluate, navigate, slowScrollTo, slowScrollToSelector, sleep } from './cdp.mjs';
import { startCapture, writeConcatList } from './capture.mjs';
import { WORK, ensureChrome, login, setViewport } from './session.mjs';

const BASE = process.env.SHOOT_BASE ?? 'http://127.0.0.1:8022';
const OUT = process.env.SHOOT_OUT ?? 'master.mp4';
const USER = process.env.SHOOT_USER ?? 'admin';
const PASS = process.env.SHOOT_PASS ?? 'quantinue-admin';
const FRAMEDIR = join(WORK, 'frames');

await ensureChrome();
const page = await attach();
await setViewport(page);
const marks = [];
let t0 = 0;
const now = () => Date.now() - t0;
const mark = (scene, phase) => {
  const at = now();
  marks.push({ scene, phase, at });
  console.log(`[${(at / 1000).toFixed(1).padStart(6)}s] ${scene} ${phase}`);
};

/** 관제실을 다시 읽어온다 — 원장이 갱신됐는지 보는 유일한 방법. */
async function reloadAdmin(settle = 1500) {
  await navigate(page, `${BASE}/admin`, settle);
}

/** 해당 섹션에 티커가 나타날 때까지 새로고침하며 기다린다. */
async function waitForTicker(section, ticker, { timeoutMs = 420000, everyMs = 12000 } = {}) {
  const deadline = Date.now() + timeoutMs;
  let tries = 0;
  while (Date.now() < deadline) {
    const found = await evaluate(page, `
      (() => { const s = document.querySelector(${JSON.stringify(section)});
        return !!s && s.innerText.includes(${JSON.stringify(ticker)}); })()
    `);
    if (found) return true;
    tries += 1;
    if (tries % 2 === 0) console.log(`   … ${section} ${ticker} 대기 ${(now() / 1000).toFixed(0)}s`);
    await sleep(everyMs);
    await reloadAdmin(900);
  }
  return false;
}

/** 선택자 목록 중 텍스트에 ticker가 든 첫 요소로 천천히 이동. */
async function scrollToRow(containerSel, rowSel, ticker, { durationMs = 2200, offset = 240 } = {}) {
  const y = await evaluate(page, `
    (() => {
      const rows = [...document.querySelectorAll(${JSON.stringify(`${containerSel} ${rowSel}`)})];
      const el = rows.find((n) => n.innerText.includes(${JSON.stringify(ticker)}));
      if (!el) return null;
      return el.getBoundingClientRect().top + window.scrollY - ${offset};
    })()
  `);
  if (y === null) return false;
  await slowScrollTo(page, y, durationMs);
  return true;
}

/**
 * 크리틱이 실제로 반박한 판단 카드로 이동한다.
 * "LLM을 쓰되 통제한다"는 주장을 화면으로 증명하는 유일한 자리라, 반박문이
 * 실제로 붙어 있는 카드를 골라야 한다 — 아무 카드나 잡으면 근거만 있고
 * 반박이 비어 그 주장이 화면에서 사라진다.
 */
async function scrollToJudgementWithObjection(skip = 0, durationMs = 2600) {
  const info = await evaluate(page, `
    (() => {
      const items = [...document.querySelectorAll('#judgements .judgement-item')]
        .filter((n) => n.querySelector('.judgement-objection'));
      const el = items[${skip}];
      if (!el) return null;
      return {
        y: el.getBoundingClientRect().top + window.scrollY - 180,
        ticker: (el.querySelector('.judgement-ticker') || {}).textContent?.trim(),
        count: items.length,
      };
    })()
  `);
  if (!info) return null;
  await slowScrollTo(page, info.y, durationMs);
  return info;
}

// reset은 앱을 재기동한다. 세션 키가 고정이라 보통 로그인이 살아 있지만,
// 풀렸는데 그대로 찍으면 마스터 첫 장면이 로그인 화면이 된다 — 녹화 전에 확인.
await reloadAdmin(1000);
if ((await evaluate(page, 'location.pathname')) !== '/admin') {
  console.log('세션 풀림 → 재로그인:', await login(page, BASE, USER, PASS));
  await reloadAdmin(1200);
}

// ── 녹화 시작 ────────────────────────────────────────────────────────────────
await reloadAdmin(1200);
const rec = startCapture(page, FRAMEDIR, { fps: 25, quality: 84 });
await sleep(600);
t0 = Date.now();
mark('REC', 'start');

// 장면 도중 무엇이 터지든 녹화는 끝까지 마무리하고 마크를 남긴다.
// (앞 테이크는 스크롤 한 번이 멈춘 것 때문에 통째로 날아갔다)
try {

// ── S1a: 관제실 첫 화면 (사건 전 ~1분 창을 이걸로 채운다) ───────────────────
mark('S1a', 'in');
await slowScrollTo(page, 0, 300);
await sleep(5000);                                       // 배지·헤더를 읽을 시간
await slowScrollToSelector(page, '#report', { durationMs: 1500, offset: 110 });
await sleep(6000);                                       // 일일 리포트 수치
await slowScrollToSelector(page, '#watch', { durationMs: 2200, offset: 110 });
await sleep(4500);                                       // 장중 감시 — 살아 있다는 증거
await slowScrollToSelector(page, '#chain', { durationMs: 2200, offset: 110 });
await sleep(6000);                                       // 잡 14개 체인
mark('S1a', 'out');

// ── S3: NVEX 호재 매수 — 배분(집행된 매수)에 남는다 ─────────────────────────
mark('S3', 'wait');
await reloadAdmin(1200);
const nvex = await waitForTicker('#allocation', 'NVEX');
mark('S3', nvex ? 'in' : 'missing');
if (nvex) {
  await slowScrollToSelector(page, '#allocation', { durationMs: 2500, offset: 110 });
  await sleep(3000);
  await scrollToRow('#allocation', 'tr', 'NVEX', { durationMs: 1800, offset: 300 });
  await sleep(7000);                                     // 1090주 @ $55.00
  mark('S3', 'out');
}

// ── S4: HLXM 악재 반전 매도 — 방어선 "판단 반전"으로 남는다 ────────────────
mark('S4', 'wait');
const hlxm = await waitForTicker('#protection', 'HLXM');
mark('S4', hlxm ? 'in' : 'missing');
if (hlxm) {
  await slowScrollToSelector(page, '#protection', { durationMs: 2500, offset: 110 });
  await sleep(3000);
  await scrollToRow('#protection', '.event-record', 'HLXM', { durationMs: 1800, offset: 300 });
  await sleep(7000);                                     // 200주 @ $80.00 · 판단 반전
  mark('S4', 'out');
}

// ── S1b: 판단과 반박 — 근거가 남는다는 주장을 화면으로 증명하는 자리 ────────
// (각본 사건이 아니라 이어받은 실제 운영 판단이다. 손절 대기 시간을 여기 쓴다)
mark('S1b', 'in');
await slowScrollToSelector(page, '#judgements', { durationMs: 3000, offset: 110 });
await sleep(4000);
for (const i of [0, 1, 2]) {
  const info = await scrollToJudgementWithObjection(i, 2400);
  if (!info) break;
  if (i === 0) console.log(`   반박 붙은 판단 ${info.count}건`);
  await sleep(6500);                                     // 근거·리스크·크리틱 반박
}
await slowScrollToSelector(page, '#accounts', { durationMs: 3000, offset: 110 });
await sleep(5000);                                       // 계좌 곡선
await slowScrollToSelector(page, '#ledger', { durationMs: 2500, offset: 110 });
await sleep(6000);                                       // 계좌 총람
mark('S1b', 'out');

// ── S1c: 계좌 관리·슬롯 화면 (손절까지 남은 ~2분을 이걸로 채운다) ───────────
mark('S1c', 'in');
await navigate(page, `${BASE}/admin/accounts`, 2000);
await sleep(5000);
await slowScrollTo(page, 700, 2500);
await sleep(5000);
await navigate(page, `${BASE}/admin/schedule`, 2000);
await sleep(6000);
await slowScrollTo(page, 650, 2500);
await sleep(5000);
mark('S1c', 'out');
await reloadAdmin(1500);

// ── S2: VRDN 손절 (~5분) — 방어선 발동이 화면에 뜰 때까지 기다린다 ──────────
mark('S2', 'wait');
await slowScrollToSelector(page, '#watch', { durationMs: 2500, offset: 110 });
const vrdn = await waitForTicker('#protection', 'VRDN', { timeoutMs: 480000, everyMs: 10000 });
mark('S2', vrdn ? 'in' : 'missing');
if (vrdn) {
  await slowScrollToSelector(page, '#protection', { durationMs: 2500, offset: 110 });
  await sleep(3000);
  await scrollToRow('#protection', '.event-record', 'VRDN', { durationMs: 1800, offset: 300 });
  await sleep(9000);                                     // 손절가 $139.50
  // 방어선 패널이 1건 → 2건으로 자란 것을 통째로 한 번 더 보여준다
  await slowScrollToSelector(page, '#protection', { durationMs: 2000, offset: 110 });
  await sleep(5000);
  mark('S2', 'out');
}

} catch (err) {
  mark('ERROR', String(err && err.message ? err.message : err));
  console.error('장면 중 오류 — 지금까지 찍은 것은 살린다:', err);
} finally {
  mark('REC', 'stop');
  await sleep(1200);
  const { frames, dropped } = await rec.stop();
  const span = frames.length ? frames[frames.length - 1].at / 1000 : 0;
  console.log(`\n프레임 ${frames.length}장 · ${span.toFixed(1)}s · 실효 ${(frames.length / span).toFixed(1)}fps · 실패 ${dropped}`);

  // 도착 시각 그대로 인코딩한다(§capture.mjs) — 프레임률이 흔들려도 속도가 안 밀린다.
  const list = writeConcatList(FRAMEDIR, frames, join(WORK, 'frames.txt'));
  execFileSync('ffmpeg', [
    '-hide_banner', '-loglevel', 'error', '-y',
    '-f', 'concat', '-safe', '0', '-i', list,
    '-vsync', 'cfr', '-r', '30',
    '-c:v', 'libx264', '-preset', 'medium', '-crf', '20',
    '-pix_fmt', 'yuv420p', '-movflags', '+faststart', join(WORK, OUT),
  ], { stdio: 'inherit' });

  writeFileSync(join(WORK, 'marks.json'), JSON.stringify({ out: OUT, marks }, null, 2));
  console.log('마크 저장:', join(WORK, 'marks.json'));
}
process.exit(0);
