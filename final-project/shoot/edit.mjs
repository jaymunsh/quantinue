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

const W = 1920, H = 1080;

/**
 * 증거 영역만 남기고 나머지를 어둡게 깐다 + 테두리를 두른다.
 *
 * 왜 필요한가: 촬영본은 대시보드 전체 화면이라 한 프레임에 숫자가 수십 개다.
 * 자막이 "방어선 발동이 1건 → 2건이 됩니다"라고 주장해도, 그 `2건`은 KPI
 * 타일 안 200×90px짜리라 프로젝터에서는 못 찾는다. 말이 가리키는 곳을
 * 화면도 가리켜야 주장이 증거가 된다.
 *
 * drawbox 네 장으로 영역 바깥을 덮는다 — 이 ffmpeg 빌드에 alphamerge·
 * geq가 없어서 마스크를 만들 수 없다. 네 장이면 같은 그림이 나온다.
 */
function spotFilters(spot) {
  const { x, y, w, h, from, to, dim = 0.55 } = spot;
  const en = `:enable='between(t,${from},${to})'`;
  const dark = `black@${dim}`;
  return [
    `drawbox=x=0:y=0:w=${W}:h=${y}:color=${dark}:t=fill${en}`,
    `drawbox=x=0:y=${y + h}:w=${W}:h=${H - y - h}:color=${dark}:t=fill${en}`,
    `drawbox=x=0:y=${y}:w=${x}:h=${h}:color=${dark}:t=fill${en}`,
    `drawbox=x=${x + w}:y=${y}:w=${W - x - w}:h=${h}:color=${dark}:t=fill${en}`,
    // 강조 테두리 — 어둡게 깔기만 하면 "화면이 어두워졌네"로 읽힌다.
    `drawbox=x=${x - 4}:y=${y - 4}:w=${w + 8}:h=${h + 8}:color=0xE8590C:t=4${en}`,
  ].join(',');
}

/**
 * 클립 하나에 배지와 자막을 얹는다.
 * subs: [{ png, from, to }] — from/to는 클립 기준 초.
 * spots: [{ x, y, w, h, from, to }] — 그 구간에 강조할 증거 영역.
 * lift: 화면을 위로 끌어올리고 아래를 띠로 채운다(px).
 *   증거가 페이지 **맨 아래 행**에 있는 장면(`/me` 보유 종목의 VRDN)은
 *   자막 띠가 그 행을 정확히 덮는다. 예전엔 자막을 중단으로 올려서 피했지만
 *   (07-28 사용자 결정: 자막은 전부 하단), 이제 화면 쪽을 올려서 비운다.
 */
export function burn(src, dest, { badge, subs = [], spots = [], lift = 0, fadeIn = 0, fadeOut = 0 }) {
  const dur = probeDuration(src);
  const inputs = ['-i', src];
  const filters = [];
  let last = '0:v';

  if (lift > 0) {
    filters.push(`[${last}]crop=${W}:${H - lift}:0:${lift},pad=${W}:${H}:0:0:color=0x0B1220[lifted]`);
    last = 'lifted';
  }
  if (spots.length) {
    filters.push(`[${last}]${spots.map(spotFilters).join(',')}[spotted]`);
    last = 'spotted';
  }

  const overlayFiles = [];
  if (badge) overlayFiles.push({ png: badge, from: 0, to: dur });
  overlayFiles.push(...subs);

  overlayFiles.forEach((ov, i) => {
    inputs.push('-i', join(OVERLAYS, ov.png));
    const idx = i + 1;
    const out = `v${idx}`;
    // 자막 띠는 화면 아래, 배지는 위 — PNG 자체가 1920 폭 전체를 쓰므로
    // y만 지정하면 된다. 자막은 **예외 없이 하단**이다(07-28 사용자 결정).
    // 증거가 하단에 깔린 장면은 자막을 올리는 대신 `lift`로 화면을 올린다.
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
