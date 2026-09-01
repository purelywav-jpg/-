// 셀렉터 진단용 DOM 덤프 스크립트 — 읽기 전용, 저장/발행을 절대 시도하지 않는다.
// 네이버가 SmartEditor 셀렉터를 바꿔 naver_draft.js 가 실패할 때 이 스크립트로 실측한 뒤 수정한다.

import fs from 'node:fs';
import path from 'node:path';
import {
  launchNaverContext,
  installPublishGuard,
  getEditorFrame,
  dismissContinuePopup,
  ROOT,
} from './lib/browser.js';

async function dumpArea(frame, selector) {
  const loc = frame.locator(selector);
  const count = await loc.count();
  const entry = { count };
  if (count) {
    entry.outerHTML = await loc
      .first()
      .evaluate((el) => el.outerHTML.slice(0, 3000))
      .catch((err) => `읽기 실패: ${err.message}`);
  }
  return entry;
}

async function main() {
  const configPath = path.join(ROOT, 'data', 'config.json');
  const config = JSON.parse(fs.readFileSync(configPath, 'utf-8'));
  if (!config.naverBlogId) {
    console.error('data/config.json 의 naverBlogId 를 먼저 채워주세요.');
    process.exit(1);
  }

  const { context } = await launchNaverContext({ headless: false });
  const page = await context.newPage();
  await installPublishGuard(page);
  await page.goto(`https://blog.naver.com/${config.naverBlogId}?Redirect=Write`, {
    waitUntil: 'domcontentloaded',
  });

  const frame = await getEditorFrame(page);
  await dismissContinuePopup(frame);

  const areas = [
    '.se-title-text',
    '.se-section-text',
    '.se-toolbar',
    'button[class*="se-image-toolbar-button"]',
    'button[class*="se-video-toolbar-button"]',
    'button[class*="se-place-toolbar-button"]',
    'button[class*="se-text-format-toolbar-button"]',
    'button[class*="se-insert-quotation-default-toolbar-button"]',
    'button[class*="se-insert-horizontal-line-default-toolbar-button"]',
    '[class*="publish"]',
    'button[data-testid="seOnePublishBtn"]',
  ];

  const dump = {};
  for (const selector of areas) {
    dump[selector] = await dumpArea(frame, selector);
  }

  const ts = new Date().toISOString().replace(/[:.]/g, '-');
  const outPath = path.join(ROOT, 'drafts', `_probe_${ts}.txt`);
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  fs.writeFileSync(outPath, JSON.stringify(dump, null, 2), 'utf-8');

  console.log(`DOM 덤프 저장됨: ${outPath}`);
  console.log('이 파일 내용을 Claude Code에게 보여주면 실측 기반으로 scripts/naver_draft.js 셀렉터를 수정합니다.');

  await context.close();
  process.exit(0);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
