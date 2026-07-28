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

  // 막 0 — 무대를 세운다
  { id: 'sub-intro',    text: '자동으로 도는 잡이 오늘 무엇을 했고,<br>무엇을 사지 않았는지 한 화면에서 봅니다' },

  // 막 1 — 이 영상의 축. 손절선은 사후 변명이 아니라 **사전 약속**이다.
  { id: 'sub-preset',   text: '이 계좌는 VRDN을 100주 갖고 있습니다', kind: 'det' },
  { id: 'sub-stop',     text: '손절선은 <b>살 때 이미</b> 정해져 있습니다<br>자동 청산 · 손절 $139.50', kind: 'det' },

  // 막 2 — 결과가 아니라 사건이 일어나는 것을 보여준다
  { id: 'sub-before',   text: '지금 방어선 발동은 1건입니다<br>VRDN은 아직 없습니다', kind: 'det' },
  { id: 'sub-det',      text: '이 경로는 AI를 부르지 않습니다', kind: 'det' },
  { id: 'sub-grow',     text: '1분마다 도는 감시가 그 선에 닿자<br>방어선 발동이 <b>1건 → 2건</b>이 됩니다', kind: 'det' },
  { id: 'sub-vrdn',     text: '살 때 적어둔 그 숫자로 청산됐습니다<br>VRDN 100주 · $139.50', kind: 'det' },
  { id: 'sub-gone',     text: '보유 목록에서 VRDN이 사라졌습니다', kind: 'det' },
  { id: 'sub-rule',     text: '원장에 남은 청산 사유:<br>“모델 판단 없이 손절 조건으로 체결됐습니다”', kind: 'det' },

  // 막 3 — 반대로 여기가 AI를 부르는 자리다
  { id: 'sub-llm',      text: '여기서만 AI가 다시 판단합니다', kind: 'llm' },
  { id: 'sub-nvex',     text: '호재 사건 → 재판단 → 매수 체결<br>NVEX 1,090주 @ $55.00', kind: 'llm' },
  { id: 'sub-hlxm',     text: '악재로 보유 논거가 무너지자 반전 매도<br>HLXM 200주 @ $80.00', kind: 'llm' },

  // 막 4 — 그 판단에는 근거와 반박이 남는다
  { id: 'sub-evidence', text: '모든 매수·매도에 근거가 남습니다' },
  { id: 'sub-critic',   text: '크리틱이 반박한 내용까지 원장에 남습니다' },
  { id: 'sub-verify',   text: '재실행해도 주문은 늘지 않습니다 — 중복 0', kind: 'det' },
  // 각본 → 실운영 전환. 이 한 장이 "이거 진짜예요?"에 답하는 자리다.
  { id: 'sub-switch',   text: '여기까지는 각본입니다.<br>지금부터는 실제로 돌고 있는 서버입니다', kind: 'live' },
  { id: 'sub-live',     text: '실물 시세 · 실제 AI 판단 · 모의 체결<br>화면 좌하단이 <span style="color:#ffd77a">LLM openai</span>로 바뀐 것을 봐 주세요', kind: 'live' },
];

// 장면별 자막 배치. from/to는 장면 시작 기준 초.
// 값은 장면 길이에 맞춰 clamp되므로, 길이가 몇 초 흔들려도 자막이 밖으로
// 새지 않는다.
//
// 순서는 촬영 순서가 아니라 **이야기 순서**다(presentation-plan §4-1의 5막).
// 사실을 나열하지 않고 한 계좌의 하루를 따라간다:
//   막0 무대 → 막1 사전 약속 → 막2 그 약속이 지켜지는 사건 →
//   막3 반대로 AI를 부르는 자리 → 막4 근거 → 막5 실운영
// 막 2가 심장이다. **결과를 보여주지 말고 사건이 일어나는 것을 보여준다.**
const PLAN = [
  // 막 0
  { file: 'a-control-room.mp4', subs: [
    { png: 'sub-intro.png', from: 1.0, to: 9.0 },
  ], fadeIn: 0.8 },
  // 막 1 — 축. VRDN 행이 페이지 맨 아래라 자막을 올려서 피한다(edit.mjs `up`).
  { file: 'b-me-stoploss-preset.mp4', subs: [
    { png: 'sub-preset.png', from: 1.0, to: 8.0 },
    { png: 'sub-stop.png', from: 9.5, to: 22.0, up: 400 },
  ] },
  // 막 2 — 대조군 → 사건 → 결말
  { file: 'c-protection-before.mp4', subs: [
    { png: 'sub-before.png', from: 0.8, to: 9.0 },
  ] },
  { file: 'd-protection-grows.mp4', subs: [
    { png: 'sub-det.png', from: 0.5, to: 7.0 },
    { png: 'sub-grow.png', from: 8.0, to: 18.0 },
    { png: 'sub-vrdn.png', from: 19.0, to: 30.0 },
  ] },
  { file: 'e-me-after-exit.mp4', subs: [
    { png: 'sub-gone.png', from: 1.0, to: 8.0 },
    { png: 'sub-rule.png', from: 10.0, to: 22.0 },
  ] },
  // 막 3 — 여기서만 AI
  { file: 'f-nvex-buy.mp4', subs: [
    { png: 'sub-llm.png', from: 0.5, to: 5.5 },
    { png: 'sub-nvex.png', from: 6.2, to: 15.0 },
  ] },
  { file: 'g-hlxm-reversal.mp4', subs: [
    { png: 'sub-hlxm.png', from: 1.0, to: 13.0 },
  ] },
  // 막 4 — 근거와 반박
  { file: 'h-judgements.mp4', subs: [
    { png: 'sub-evidence.png', from: 1.5, to: 10.0 },
    { png: 'sub-critic.png', from: 12.0, to: 22.0 },
  ] },
  // S5는 페이지 자체에 배지가 박혀 있어 오버레이 배지를 겹치지 않는다.
  { file: 's5-verify.mp4', badge: null, subs: [
    { png: 'sub-verify.png', from: 1.5, to: 11.0 },
  ] },
  // 막 5 — 운영 실증거. 배지 색이 바뀌는 것 자체가 장치다.
  //
  // 원본 테이크(`s6-live-ops.mp4`)는 1:48이라 요약본 3:00 안에 못 들어간다.
  // 증거는 **꼬리 20초**에 다 있다 — `최근 폴링 시도`가 갱신된 운영 기준
  // 화면. 헤더의 3중 시계는 어차피 모든 프레임에서 돌고 있다.
  { file: 's6-live-ops-tail.mp4', badge: 'badge-live.png', subs: [
    { png: 'sub-switch.png', from: 0.5, to: 8.0 },
    { png: 'sub-live.png', from: 9.0, to: 18.5 },
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
  // 07-28 사용자 결정: 데모 구간의 상시 배지는 뺀다 — 발표 멘트와 슬라이드가
  // 이미 "각본 재현"을 선언한다. 단 s6의 '실제 운영 기록' 배지(badge-live)는
  // 남긴다: 각본→실서버 전환을 배지 등장으로 보여주는 장치라서다.
  const badge = step.badge ?? null;
  burn(src, dest, { badge, subs, fadeIn: step.fadeIn ?? 0, fadeOut: step.fadeOut ?? 0 });
  built.push(dest);
  console.log(`  ${step.file.padEnd(26)} ${dur.toFixed(1)}s · 자막 ${subs.length}`);
}

const out = join(FOOTAGE, 'roughcut-demo.mp4');
concat(built, out);
console.log('\n러프컷:', out, `${probeDuration(out).toFixed(1)}s`);
process.exit(0);
