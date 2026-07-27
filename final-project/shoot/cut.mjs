// 마스터에서 장면별 원본을 잘라낸다.
//
// 마크는 드라이버가 실제로 카메라를 움직인 시각이라, 사건을 기다린 구간
// (…wait → …in)은 자동으로 빠진다. 잘라낸 파일이 곧 "장면별 원본"이다.
import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { FOOTAGE, WORK } from './session.mjs';

const DEST = process.argv[2] ?? FOOTAGE;
const { out, marks } = JSON.parse(readFileSync(join(WORK, 'marks.json'), 'utf8'));
const master = join(WORK, out);

// 장면 정의: [파일명, 시작마크, 끝마크]. 앞뒤로 조금 물려 잘라 컷이 급하지 않게.
const PAD_IN = 0.6;
const PAD_OUT = 1.0;
// 이름은 `presentation-plan.md` §4-2의 샷 기호를 그대로 쓴다. 편집에서 어떤
// 파일이 어느 샷인지 되짚을 때 문서와 파일명이 같아야 헷갈리지 않는다.
const SCENES = [
  ['a-control-room', 'A', 'in', 'A', 'out'],
  ['b-me-stoploss-preset', 'B', 'in', 'B', 'out'],
  ['c-protection-before', 'C', 'in', 'C', 'out'],
  ['f-nvex-buy', 'F', 'in', 'F', 'out'],
  ['g-hlxm-reversal', 'G', 'in', 'G', 'out'],
  ['h-judgements', 'H', 'in', 'H', 'out'],
  // D만 시작을 앞으로 당긴다. 'seen'은 배지가 바뀐 것을 확인한 순간이라,
  // 그 직전 새로고침(= 아직 1건이던 화면)까지 물려야 "자라는 것"이 보인다.
  ['d-protection-grows', 'D', 'seen', 'D', 'out', 14],
  ['e-me-after-exit', 'E', 'in', 'E', 'out'],
];

const at = (scene, phase) => {
  const m = marks.find((k) => k.scene === scene && k.phase === phase);
  return m ? m.at / 1000 : null;
};

if (!existsSync(master)) throw new Error(`마스터 없음: ${master}`);
mkdirSync(DEST, { recursive: true });

const made = [];
for (const [name, s1, p1, s2, p2, lookback = 0] of SCENES) {
  const a = at(s1, p1);
  const b = at(s2, p2);
  if (a === null || b === null) {
    console.log(`건너뜀 ${name} — 마크 없음 (${s1}.${p1}=${a} ${s2}.${p2}=${b})`);
    continue;
  }
  const start = Math.max(0, a - PAD_IN - lookback);
  const dur = (b - start) + PAD_OUT;
  const dest = join(DEST, `${name}.mp4`);
  // 프레임 정확도가 필요하므로 재인코딩한다(-c copy는 키프레임에 붙어 앞이 얼어붙는다).
  execFileSync('ffmpeg', [
    '-hide_banner', '-loglevel', 'error', '-y',
    '-ss', start.toFixed(2), '-i', master, '-t', dur.toFixed(2),
    '-c:v', 'libx264', '-preset', 'medium', '-crf', '20',
    '-pix_fmt', 'yuv420p', '-movflags', '+faststart', dest,
  ], { stdio: 'inherit' });
  made.push({ name, dest, start: +start.toFixed(2), dur: +dur.toFixed(2) });
  console.log(`${name.padEnd(20)} ${start.toFixed(1)}s +${dur.toFixed(1)}s -> ${dest}`);
}

console.log('\n총', made.length, '장면');
