// 러프컷 조립기.
//
// 이 ffmpeg 빌드에는 drawtext도 subtitles 필터도 없어서(옵션 17개짜리 슬림
// 빌드) 자막을 Chrome으로 그린 알파 PNG를 overlay로 얹는다. 대신 얻는 게
// 있다 — 한글 자간·굵기를 CSS로 통제할 수 있어 결과가 더 낫다.
//
// 배지는 클립 전체에 깔고(신뢰성 선언), 자막은 구간별로 켠다.
import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

import { WORK } from './session.mjs';
const OVERLAYS = join(WORK, 'overlays');

const probeDuration = (file) =>
  parseFloat(execFileSync('ffprobe', [
    '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', file,
  ]).toString().trim());

/**
 * 클립 하나에 배지와 자막을 얹는다.
 * subs: [{ png, from, to }] — from/to는 클립 기준 초.
 */
export function burn(src, dest, { badge, subs = [], fadeIn = 0, fadeOut = 0 }) {
  const dur = probeDuration(src);
  const inputs = ['-i', src];
  const filters = [];
  let last = '0:v';

  const overlayFiles = [];
  if (badge) overlayFiles.push({ png: badge, from: 0, to: dur });
  overlayFiles.push(...subs);

  overlayFiles.forEach((ov, i) => {
    inputs.push('-i', join(OVERLAYS, ov.png));
    const idx = i + 1;
    const out = `v${idx}`;
    // 자막 띠는 화면 아래, 배지는 위 — PNG 자체가 1920 폭 전체를 쓰므로
    // y만 지정하면 된다.
    const y = ov.png.startsWith('badge') ? 0 : 'H-h';
    filters.push(
      `[${last}][${idx}:v]overlay=0:${y}:enable='between(t,${ov.from},${ov.to})'[${out}]`,
    );
    last = out;
  });

  if (fadeIn > 0) { filters.push(`[${last}]fade=t=in:st=0:d=${fadeIn}[fi]`); last = 'fi'; }
  if (fadeOut > 0) {
    filters.push(`[${last}]fade=t=out:st=${(dur - fadeOut).toFixed(2)}:d=${fadeOut}[fo]`);
    last = 'fo';
  }

  const args = ['-hide_banner', '-loglevel', 'error', '-y', ...inputs];
  if (filters.length) args.push('-filter_complex', filters.join(';'), '-map', `[${last}]`);
  args.push('-c:v', 'libx264', '-preset', 'medium', '-crf', '20',
    '-pix_fmt', 'yuv420p', '-r', '30', '-movflags', '+faststart', dest);
  execFileSync('ffmpeg', args, { stdio: 'inherit' });
  return dur;
}

/** 클립들을 이어 붙인다. 전부 같은 규격(1920x1080/30fps/yuv420p)이라 concat이 안전하다. */
export function concat(files, dest) {
  const listFile = join(WORK, 'concat-list.txt');
  writeFileSync(listFile, files.map((f) => `file '${f}'`).join('\n'));
  execFileSync('ffmpeg', [
    '-hide_banner', '-loglevel', 'error', '-y',
    '-f', 'concat', '-safe', '0', '-i', listFile,
    '-c', 'copy', '-movflags', '+faststart', dest,
  ], { stdio: 'inherit' });
}

export { probeDuration };
if (!existsSync(OVERLAYS)) mkdirSync(OVERLAYS, { recursive: true });
