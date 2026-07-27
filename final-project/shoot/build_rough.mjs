// 러프컷 빌드: 장면 원본 + 배지 + 자막 → 이어붙인 한 편.
//
// 자막 문안은 slides-content.md §5의 확정 문구를 따른다. "LLM"이 아니라
// "AI"로 적는 것도 원고 결정이다 — 청중이 발표에서 듣는 말과 화면의 말이
// 달라지면 그 순간 설명이 두 번 필요해진다.
import { execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { burn, concat, probeDuration } from './edit.mjs';
import { FOOTAGE, WORK } from './session.mjs';
import { renderAll } from './subs.mjs';

const CUT = join(WORK, 'cutwork');   // 자막·배지를 구운 중간 클립
execFileSync('mkdir', ['-p', CUT]);

const BADGE_DEMO = '데모 환경 · 모의 AI · 모의 체결';

// 오버레이 자산 — id가 곧 파일명(overlays/<id>.png)이 된다.
const OVERLAY_ITEMS = [
  { id: 'badge-demo', type: 'badge', tone: 'demo', text: BADGE_DEMO },
  { id: 'badge-live', type: 'badge', tone: 'live', text: '실제 운영 기록 (읽기 전용)' },

  { id: 'sub-intro',    text: '자동으로 도는 잡이 오늘 무엇을 했고,<br>무엇을 사지 않았는지 한 화면에서 봅니다' },
  { id: 'sub-ledger',   text: '잡 14개 · 판단 50건 · 방어선 2건<br>전부 원장에 남은 값입니다' },
  { id: 'sub-llm',      text: '여기서만 AI가 다시 판단합니다', kind: 'llm' },
  { id: 'sub-nvex',     text: '호재 사건 → 재판단 → 매수 체결<br>NVEX 1,090주 @ $55.00', kind: 'llm' },
  { id: 'sub-hlxm',     text: '악재로 보유 논거가 무너지자 반전 매도<br>HLXM 200주 @ $80.00', kind: 'llm' },
  { id: 'sub-evidence', text: '모든 매수·매도에 근거가 남습니다' },
  { id: 'sub-critic',   text: '크리틱이 반박한 내용까지 원장에 남습니다' },
  { id: 'sub-accounts', text: '계좌 6개가 성향별로 다르게 굴러갑니다' },
  { id: 'sub-det',      text: '이 경로는 AI를 부르지 않습니다', kind: 'det' },
  { id: 'sub-vrdn',     text: '급락 → 1분 감시 tick → 손절 체결<br>VRDN $139.50', kind: 'det' },
  { id: 'sub-verify',   text: '재실행해도 주문은 늘지 않습니다 — 중복 0', kind: 'det' },
  // 각본 → 실운영 전환. 이 한 장이 "이거 진짜예요?"에 답하는 자리다.
  { id: 'sub-switch',   text: '여기까지는 각본입니다.<br>지금부터는 실제로 돌고 있는 서버입니다', kind: 'live' },
  { id: 'sub-live',     text: '실물 시세 · 실제 AI 판단 · 모의 체결<br>화면 좌하단이 <span style="color:#ffd77a">LLM openai</span>로 바뀐 것을 봐 주세요', kind: 'live' },
];

// 장면별 자막 배치. from/to는 장면 시작 기준 초.
// 값은 장면 길이에 맞춰 clamp되므로, 길이가 몇 초 흔들려도 자막이 밖으로
// 새지 않는다.
// 순서는 촬영 순서가 아니라 **이야기 순서**다(presentation-plan §4-2):
// 소개 → AI를 안 부르는 방어 → AI가 다시 판단하는 자리 → 근거가 남는다
// → 계좌·운영 기준 → 무결 검증.
const PLAN = [
  { file: 's1a-control-room.mp4', subs: [
    { png: 'sub-intro.png', from: 1.0, to: 8.5 },
    { png: 'sub-ledger.png', from: 10.0, to: 18.0 },
  ], fadeIn: 0.8 },
  { file: 's2-vrdn-stoploss.mp4', subs: [
    { png: 'sub-det.png', from: 0.8, to: 7.0 },
    { png: 'sub-vrdn.png', from: 8.0, to: 18.0 },
  ] },
  { file: 's3-nvex-buy.mp4', subs: [
    { png: 'sub-llm.png', from: 0.5, to: 5.5 },
    { png: 'sub-nvex.png', from: 6.2, to: 15.0 },
  ] },
  { file: 's4-hlxm-reversal.mp4', subs: [
    { png: 'sub-hlxm.png', from: 1.0, to: 13.0 },
  ] },
  { file: 's1b-judgements.mp4', subs: [
    { png: 'sub-evidence.png', from: 1.5, to: 10.0 },
    { png: 'sub-critic.png', from: 12.0, to: 22.0 },
  ] },
  { file: 's1c-accounts.mp4', subs: [
    { png: 'sub-accounts.png', from: 1.0, to: 9.0 },
  ] },
  // S5는 페이지 자체에 배지가 박혀 있어 오버레이 배지를 겹치지 않는다.
  { file: 's5-verify.mp4', badge: null, subs: [
    { png: 'sub-verify.png', from: 1.5, to: 11.0 },
  ] },
  // S6은 운영 실증거 — 배지 색이 바뀌는 것 자체가 장치다.
  { file: 's6-live-ops.mp4', badge: 'badge-live.png', subs: [
    { png: 'sub-switch.png', from: 0.5, to: 8.0 },
    { png: 'sub-live.png', from: 9.5, to: 19.0 },
  ], fadeIn: 0.6, fadeOut: 1.0 },
];

console.log('오버레이 렌더링…');
await renderAll(OVERLAY_ITEMS);

console.log('\n장면 굽기…');
const built = [];
for (const step of PLAN) {
  const src = join(FOOTAGE, step.file);
  if (!existsSync(src)) { console.log('  건너뜀(없음):', step.file); continue; }
  const dur = probeDuration(src);
  // 장면이 짧게 끝났을 때 자막이 클립 밖으로 나가지 않도록 자른다.
  const subs = step.subs
    .filter((s) => s.from < dur - 0.4)
    .map((s) => ({ ...s, to: Math.min(s.to, dur - 0.2) }));
  const dest = join(CUT, step.file);
  // badge: null = 배지 없음(S5는 페이지에 이미 박혀 있다), 문자열 = 그 배지, 미지정 = DEMO
  const badge = step.badge === null ? null : (step.badge ?? 'badge-demo.png');
  burn(src, dest, { badge, subs, fadeIn: step.fadeIn ?? 0, fadeOut: step.fadeOut ?? 0 });
  built.push(dest);
  console.log(`  ${step.file.padEnd(26)} ${dur.toFixed(1)}s · 자막 ${subs.length}`);
}

const out = join(FOOTAGE, 'roughcut-demo.mp4');
concat(built, out);
console.log('\n러프컷:', out, `${probeDuration(out).toFixed(1)}s`);
process.exit(0);
