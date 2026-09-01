// 사진 속 개인정보(타인 얼굴·차량 번호판·전화번호 등) 모자이크 처리.
// 원본은 절대 덮어쓰지 않는다 — 처리본은 input/photos/_mosaic/ 에 생성.
//
// 사용법: node scripts/mosaic.js drafts/xxx.mosaic-spec.json
// 스펙 포맷: [{ "file": "input/photos/xxx.jpg", "regions": [{ "top":0.1,"left":0.2,"width":0.15,"height":0.15 }] }]
// 좌표는 0~1 상대값, 15% 여유는 이 스크립트가 자동으로 더한다.

import fs from 'node:fs';
import path from 'node:path';
import sharp from 'sharp';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const OUT_DIR = path.join(ROOT, 'input', 'photos', '_mosaic');

async function mosaicOne(specEntry) {
  const srcPath = path.resolve(ROOT, specEntry.file);

  // EXIF 회전 보정 후(=화면에 보이는 대로) 좌표를 잡기 위해 먼저 정규화된 버퍼를 만든다.
  const normalizedBuffer = await sharp(srcPath).rotate().toBuffer();
  const { width, height } = await sharp(normalizedBuffer).metadata();

  let pipeline = sharp(normalizedBuffer);

  for (const region of specEntry.regions) {
    const padX = region.width * 0.15;
    const padY = region.height * 0.15;
    const left = Math.max(0, Math.round((region.left - padX) * width));
    const top = Math.max(0, Math.round((region.top - padY) * height));
    const w = Math.min(width - left, Math.round((region.width + padX * 2) * width));
    const h = Math.min(height - top, Math.round((region.height + padY * 2) * height));
    if (w <= 0 || h <= 0) continue;

    const regionBuffer = await sharp(normalizedBuffer)
      .extract({ left, top, width: w, height: h })
      .toBuffer();

    // sharp는 한 파이프라인에 resize를 1회만 적용하므로 축소→버퍼→확대(nearest) 2단계로 분리한다.
    const small = await sharp(regionBuffer)
      .resize({ width: Math.max(1, Math.round(w / 16)), height: Math.max(1, Math.round(h / 16)) })
      .toBuffer();
    const pixelated = await sharp(small)
      .resize({ width: w, height: h, kernel: 'nearest' })
      .toBuffer();

    pipeline = sharp(await pipeline.toBuffer()).composite([{ input: pixelated, left, top }]);
  }

  fs.mkdirSync(OUT_DIR, { recursive: true });
  const outPath = path.join(OUT_DIR, path.basename(specEntry.file));
  await pipeline.toFile(outPath);
  console.log(`모자이크 처리 완료: ${outPath} (영역 ${specEntry.regions.length}개) — 처리본을 Read로 열어 가려졌는지 확인하세요.`);
  return outPath;
}

async function main() {
  const specPath = process.argv[2];
  if (!specPath) {
    console.error('사용법: node scripts/mosaic.js drafts/xxx.mosaic-spec.json');
    process.exit(1);
  }
  const spec = JSON.parse(fs.readFileSync(path.resolve(ROOT, specPath), 'utf-8'));
  for (const entry of spec) {
    await mosaicOne(entry);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
