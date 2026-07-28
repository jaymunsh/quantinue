// 발표용 요약본. 러프컷의 구운 클립(자막·배지 포함)을 잘라 이어붙인다.
//
// presentation-plan §4-1의 5막 3:00 구성을 따르되, 실제 장면 길이에 맞춰
// 배분을 조정했다.
//
// **막 1(사전 약속)과 막 2(그 약속이 지켜지는 사건)를 자르지 않는다.**
// 이 영상이 증명하는 한 문장이 그 둘에 걸려 있어서, 여기를 줄이면 나머지를
// 아무리 붙여도 영상의 값이 없다(§4-0). 시간이 넘치면 막 3·4를 줄인다.
//
// S6(운영 라이브)는 정규장에만 찍을 수 있어, 있으면 붙이고 없으면 그 자리를
// 비운 채 나머지를 확정한다.
import { execFileSync } from 'node:child_process';
import { existsSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

import { FOOTAGE, WORK } from './session.mjs';
const CUT = join(WORK, 'cutwork');
const TRIM = join(WORK, 'trims');
execFileSync('mkdir', ['-p', TRIM]);

const dur = (f) => parseFloat(execFileSync('ffprobe',
  ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', f]).toString().trim());

// [클립, 앞에서 자를 초, 쓸 길이(초) | null = 끝까지, 배속]
//
// 배속(07-28 사용자 결정: "지금보다 빠르게"): 심장인 막 1·2도 1.3배까지 올렸다.
// 예전엔 1.2배가 상한이었는데, 그건 **어디를 봐야 하는지 표시가 없어서**
// 시청자가 화면을 훑을 시간이 필요했기 때문이다. 이제 증거 영역에
// 스포트라이트가 들어가 눈이 바로 그리로 가므로 조금 더 당겨도 읽힌다.
//
// 컷 길이는 **각 클립의 마지막 자막이 끝나는 시점 + 여유 1초**로 잡는다.
// 예전 e·h는 자막이 끝나기 전에 잘려서 문장이 화면에서 사라졌다.
// 자막은 구운 채로 함께 빨라지므로 동기화는 그대로다.
const SEQ = [
  ['a-control-room.mp4', 0, 10, 1.5],       // 막0 무대 — 관제실은 4초면 선다
  ['b-me-stoploss-preset.mp4', 0, 23, 1.3], // 막1 사전 약속 (자막 ~22s)
  ['c-protection-before.mp4', 0, 8, 1.4],   // 막2 대조군
  ['d-protection-grows.mp4', 0, 31, 1.3],   // 막2 심장 (자막·강조 ~30s)
  ['e-me-after-exit.mp4', 0, 23, 1.5],      // 막2 결말 (자막 ~22s)
  ['f-nvex-buy.mp4', 0, 12, 1.45],          // 막3
  ['g-hlxm-reversal.mp4', 0, 12, 1.45],
  ['h-judgements.mp4', 0, 18, 1.6],         // 막4 — 본문은 어차피 안 읽힌다
  ['s5-verify.mp4', 0, 10, 1.5],
];

const parts = [];
function addPart(file, from, want, speed) {
  const src = join(CUT, file);
  if (!existsSync(src)) { console.log('건너뜀(없음):', file); return; }
  const have = dur(src);
  const take = want === null ? have - from : Math.min(want, have - from);
  const dest = join(TRIM, file);
  execFileSync('ffmpeg', [
    '-hide_banner', '-loglevel', 'error', '-y',
    // -t는 -i 앞(입력 옵션)이어야 한다 — 출력 옵션 자리에 두면 배속 후
    // 출력이 take초를 채울 때까지 입력을 더 읽어 계획한 컷이 늘어난다.
    '-ss', String(from), '-t', take.toFixed(2), '-i', src,
    '-filter:v', `setpts=PTS/${speed}`,
    '-c:v', 'libx264', '-preset', 'medium', '-crf', '20',
    '-pix_fmt', 'yuv420p', '-r', '30', dest,
  ], { stdio: 'inherit' });
  parts.push(dest);
  console.log(`  ${file.padEnd(26)} ${take.toFixed(1)}s → ${(take / speed).toFixed(1)}s (${speed}x)`);
}
for (const [file, from, want, speed] of SEQ) addPart(file, from, want, speed);

// S6이 준비돼 있으면 마지막에 붙인다. 운영 실증거라 1.25배까지만.
if (existsSync(join(CUT, 's6-live-ops-tail.mp4'))) addPart('s6-live-ops-tail.mp4', 0, null, 1.25);
else console.log('  s6-live-ops.mp4            — 아직 없음(정규장 개장 후 촬영)');

const list = join(WORK, 'summary-list.txt');
writeFileSync(list, parts.map((p) => `file '${p}'`).join('\n'));
const hasS6 = existsSync(join(CUT, 's6-live-ops-tail.mp4'));
const out = join(FOOTAGE, hasS6 ? 'summary-3min.mp4' : 'summary-3min-pending-s6.mp4');
execFileSync('ffmpeg', [
  '-hide_banner', '-loglevel', 'error', '-y',
  '-f', 'concat', '-safe', '0', '-i', list,
  '-c', 'copy', '-movflags', '+faststart', out,
], { stdio: 'inherit' });

const total = dur(out);
console.log(`\n요약본: ${out}`);
console.log(`길이 ${Math.floor(total / 60)}:${String(Math.round(total % 60)).padStart(2, '0')}`);
