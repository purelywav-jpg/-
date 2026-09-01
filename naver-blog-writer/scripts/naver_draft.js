// 초안 JSON을 받아 네이버 블로그 SmartEditor에 입력하고 임시저장까지 자동화한다.
// 발행은 절대 하지 않는다 — lib/browser.js의 installPublishGuard가 발행 버튼 클릭을 코드로 원천 차단한다.
//
// 사용법: node scripts/naver_draft.js --draft drafts/xxx.draft.json [--dry-run]

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  launchNaverContext,
  installPublishGuard,
  getEditorFrame,
  dismissContinuePopup,
  closeLeftoverDim,
  insertTextWithEmoji,
  clickToolbarButton,
  ROOT,
} from './lib/browser.js';

export function parseArgs(argv) {
  const args = { dryRun: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--dry-run') args.dryRun = true;
    else if (a === '--draft') args.draftPath = argv[++i];
    // 디버깅용: 실제 blog.naver.com 대신 다른 URL(로컬 목업 등)을 대상으로 실행
    else if (a === '--url') args.url = argv[++i];
  }
  return args;
}

export function firstTextOf(blocks) {
  const t = blocks.find((b) => b.type === 'text');
  return t ? t.text : '';
}

export function makeResult(draft) {
  return {
    tags: { attempted: !!draft.tags?.length, ok: false, detail: '' },
    place: { attempted: !!draft.place, ok: false, detail: '' },
    video: { attempted: !!draft.video, ok: false, detail: '' },
    subtitles: { attempted: false, ok: true, detail: '', total: 0, failed: 0 },
    titleMatch: false,
    bodyMatch: false,
  };
}

export async function readTitleText(frame) {
  return frame.locator('.se-title-text').first().innerText();
}

export async function readBodyParagraphs(frame) {
  return frame.locator('.se-section-text p.se-text-paragraph').allInnerTexts();
}

export async function writeTitle(frame, title) {
  const page = frame.page();
  const titleEl = frame.locator('.se-title-text').first();
  await titleEl.click();
  await page.keyboard.press('Control+A').catch(() => {});
  await page.keyboard.press('Delete').catch(() => {});
  await insertTextWithEmoji(page, title);
}

export async function fixTitle(frame, title) {
  await writeTitle(frame, title);
}

export async function prependMissingFirstLine(frame, firstLine) {
  const page = frame.page();
  const firstP = frame.locator('.se-section-text p.se-text-paragraph').first();
  if (!(await firstP.count())) return;
  await firstP.click();
  await page.keyboard.press('Home');
  await insertTextWithEmoji(page, firstLine.slice(0, 10));
}

export async function insertTextBlock(frame, text) {
  const page = frame.page();
  const paragraphs = frame.locator('.se-section-text p.se-text-paragraph');
  if (await paragraphs.count()) {
    await paragraphs.last().click();
    await page.keyboard.press('End');
  }
  await insertTextWithEmoji(page, text);
}

export async function insertSubtitleBlock(frame, text, result) {
  const page = frame.page();
  result.subtitles.attempted = true;
  result.subtitles.total += 1;
  try {
    // 서식 드롭다운은 "캐럿이 놓인 문단"에 적용되므로, 이 블록이 초안의 첫 블록이라 아직
    // 아무 곳도 클릭된 적이 없을 수 있다 — 먼저 캐럿을 마지막 문단에 놓는다.
    const paragraphs = frame.locator('.se-section-text p.se-text-paragraph');
    if (await paragraphs.count()) {
      const last = paragraphs.last();
      await last.click();
      await page.keyboard.press('End');
      // 직전 블록이 text였다면 마지막 문단에 이미 내용이 차 있다 — 그 위에 소제목 서식을 덮어씌우면
      // 이전 문단과 같은 줄에 이어 붙는다. 새 빈 문단을 만들어 소제목 전용으로 확보한다.
      const lastText = await last.innerText();
      if (lastText.trim().length > 0) {
        await page.keyboard.press('Enter');
      }
    }

    // 순서가 핵심: 서식(소제목) → 크기(19) → 텍스트 입력. 입력 후 바꾸면 이미 쓴 글자엔 적용 안 됨.
    await clickToolbarButton(frame, 'se-text-format-toolbar-button');
    await frame.getByText('소제목', { exact: true }).first().click();

    await clickToolbarButton(frame, 'se-font-size-code-toolbar-button').catch(() => {});
    await frame
      .getByText('19', { exact: false })
      .first()
      .click({ timeout: 3000 })
      .catch(async () => {
        await frame.locator('[class*="fs19"]').first().click({ timeout: 3000 }).catch(() => {});
      });

    await insertTextWithEmoji(page, text);
    await page.keyboard.press('Enter');

    // 다음 문단은 "본문"으로 명시 복귀
    await clickToolbarButton(frame, 'se-text-format-toolbar-button');
    await frame.getByText('본문', { exact: true }).first().click();

    const label = await frame
      .locator('[class*="se-text-format-toolbar-button"]')
      .first()
      .innerText()
      .catch(() => '');
    if (label && !label.includes('본문')) {
      result.subtitles.detail += `"${text.slice(0, 15)}" 소제목 이후 본문 복귀 확인 실패(현재:${label}); `;
    }
  } catch (err) {
    result.subtitles.ok = false;
    result.subtitles.failed += 1;
    result.subtitles.detail += `"${text.slice(0, 15)}" 소제목 서식 적용 실패: ${err.message}; `;
  }
}

export async function insertImageBlock(frame, block) {
  const page = frame.page();
  const [fileChooser] = await Promise.all([
    page.waitForEvent('filechooser'),
    clickToolbarButton(frame, 'se-image-toolbar-button'),
  ]);
  await fileChooser.setFiles(path.resolve(ROOT, block.path));
  await page.waitForTimeout(1500);
  if (block.caption) {
    const captionEl = frame.locator('.se-caption, [class*="se-image-caption"]').last();
    if (await captionEl.count()) {
      await captionEl.click();
      await insertTextWithEmoji(page, block.caption);
    }
  }
}

export async function writeBlock(frame, block, nextBlock, result) {
  const page = frame.page();
  switch (block.type) {
    case 'text':
      await insertTextBlock(frame, block.text);
      if (nextBlock && nextBlock.type === 'text') {
        await page.keyboard.press('Enter');
      }
      break;
    case 'subtitle':
      await insertSubtitleBlock(frame, block.text, result);
      break;
    case 'image':
      await insertImageBlock(frame, block);
      break;
    case 'quote':
      await clickToolbarButton(frame, 'se-insert-quotation-default-toolbar-button');
      await insertTextWithEmoji(page, block.text);
      break;
    case 'divider':
      await clickToolbarButton(frame, 'se-insert-horizontal-line-default-toolbar-button');
      break;
    default:
      throw new Error(`알 수 없는 블록 타입: ${block.type}`);
  }
}

export async function insertVideo(frame, draft, result) {
  const page = frame.page();
  result.video.attempted = true;
  try {
    const [fileChooser] = await Promise.all([
      page.waitForEvent('filechooser'),
      clickToolbarButton(frame, 'se-video-toolbar-button'),
    ]);
    await fileChooser.setFiles(path.resolve(ROOT, draft.video.path));

    const title = (draft.video.title || draft.title || '동영상').slice(0, 40);
    const titleInput = frame
      .locator('input[class*="se-video-title"], input[placeholder*="제목"]')
      .first();
    await titleInput.waitFor({ timeout: 20000 });
    await titleInput.click();
    await titleInput.fill('');
    await insertTextWithEmoji(page, title);

    const confirmBtn = frame.locator('button[class*="se-popup-button-confirm"]').first();
    await confirmBtn.click({ timeout: 5000 }).catch(() => {});
    await page.waitForTimeout(3000); // 업로드는 수 분 걸릴 수 있음 — 업로드 진행 UI는 팝업이 알아서 처리
    await closeLeftoverDim(page, frame);
    result.video.ok = true;
  } catch (err) {
    result.video.detail = err.message;
    await closeLeftoverDim(page, frame);
  }
}

export async function insertPlace(frame, place, result) {
  const page = frame.page();
  result.place.attempted = true;
  try {
    await clickToolbarButton(frame, 'se-place-toolbar-button');
    const searchInput = frame.locator('input[class*="search_input"], input[placeholder*="장소"]').first();
    await searchInput.waitFor({ timeout: 10000 });
    await searchInput.click();
    await insertTextWithEmoji(page, place.query);
    await page.keyboard.press('Enter');
    await page.waitForTimeout(1500);

    const items = frame.locator('[class*="search_item"], li[class*="item"]');
    const count = await items.count();
    if (count === 0) {
      result.place.detail = '검색 결과 0건 — 지도 수동 첨부 필요';
      await closeLeftoverDim(page, frame);
      return;
    }

    const normalize = (s) => s.replace(/\s+/g, '');
    let chosenIndex = 0;
    let found = false;
    if (place.name) {
      for (let i = 0; i < count; i++) {
        const text = normalize(await items.nth(i).innerText());
        if (text === normalize(place.name)) {
          chosenIndex = i;
          found = true;
          break;
        }
      }
      if (!found) {
        for (let i = 0; i < count; i++) {
          const text = normalize(await items.nth(i).innerText());
          if (text.includes(normalize(place.name))) {
            chosenIndex = i;
            found = true;
            break;
          }
        }
      }
    }

    const item = items.nth(chosenIndex);
    await item.hover();
    const addBtn = item.locator('button:has-text("추가"), a:has-text("추가")').first();
    try {
      await addBtn.click({ timeout: 3000 });
    } catch {
      await addBtn.evaluate((el) => el.click());
    }

    // :visible 로 한정 — "confirm"이 클래스명에 들어가는 다른(화면에 안 보이는) 위젯의 버튼과
    // 혼동되는 것을 막는다 (예: 방금 닫은 동영상 팝업의 확인 버튼).
    const confirmBtn = frame.locator('button[class*="confirm"]:not([disabled]):visible').first();
    await confirmBtn.waitFor({ timeout: 10000 });
    await confirmBtn.click();

    // 장소 팝업은 Escape로 안 닫힌다 — 반드시 팝업 닫기 버튼 사용 (안 닫으면 dim 레이어가 이후 모든 클릭을 막는다)
    // :visible 로 한정 — 다른 위젯(동영상 팝업 등)이 남겨둔, 이미 화면에서 사라진 닫기 버튼을 잘못 짚지 않기 위함.
    const closeBtn = frame
      .locator('[class*="se-popup-button-close"]:visible, [class*="place_layer"] [class*="close"]:visible')
      .first();
    if (await closeBtn.count()) {
      await closeBtn.click({ timeout: 3000 }).catch(() => {});
    }
    await closeLeftoverDim(page, frame);
    result.place.ok = true;
  } catch (err) {
    result.place.detail = err.message;
    await closeLeftoverDim(page, frame);
  }
}

export async function openPublishPanelAndSetTags(frame, tags, tagLimit, result) {
  if (!tags.length) return;
  const page = frame.page();
  try {
    const publishOpenBtn = frame.locator('button[class*="publish_btn"], button:has-text("발행")').first();
    await publishOpenBtn.click();
    const tagInput = frame.locator('input#tag-input');
    await tagInput.waitFor({ timeout: 10000 });
    for (const raw of tags.slice(0, tagLimit)) {
      const tag = raw.replace(/^#/, '').trim();
      if (!tag) continue;
      await tagInput.click();
      await insertTextWithEmoji(page, tag);
      await page.keyboard.press('Enter');
    }
    const tagAreaText = await frame
      .locator('[class*="tag_list"], [class*="TagList"]')
      .first()
      .innerText()
      .catch(() => '');
    const savedCount = tagAreaText.split('#').filter((s) => s.trim()).length;
    result.tags.ok = savedCount >= Math.min(tags.length, tagLimit);
    result.tags.detail = `${savedCount}/${Math.min(tags.length, tagLimit)}개 태그 확인`;
  } catch (err) {
    result.tags.detail = err.message;
  }
}

export async function closePanelKeepClosed(page) {
  await page.keyboard.press('Escape');
  await page.waitForTimeout(300);
}

export async function saveAsDraft(page) {
  await page.keyboard.press('Control+s');
  await page.waitForTimeout(2000);
}

export function printResultBlock(result, dryRun) {
  const line = (label, r) => {
    if (!r.attempted) return `- ${label}: 대상 없음`;
    return `- ${label}: ${r.ok ? '✅ 성공' : '❗수동 필요'}${r.detail ? ` (${r.detail})` : ''}`;
  };
  console.log('\n===== 자동 처리 결과 =====');
  console.log(line('태그', result.tags));
  console.log(line('지도', result.place));
  console.log(line('동영상', result.video));
  console.log(
    `- 소제목: ${
      result.subtitles.total === 0
        ? '대상 없음'
        : result.subtitles.failed === 0
          ? '✅ 성공'
          : `❗수동 필요 (${result.subtitles.failed}/${result.subtitles.total}건 실패: ${result.subtitles.detail})`
    }`,
  );
  console.log(`- 제목 일치: ${result.titleMatch ? '✅' : '❗재확인 필요'}`);
  console.log(`- 본문 첫 줄 일치: ${result.bodyMatch ? '✅' : '❗재확인 필요'}`);
  console.log(dryRun ? '- 저장: --dry-run (생략됨)' : '- 저장: 임시저장 완료 (Ctrl+S)');
  console.log('==========================\n');
}

export async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.draftPath) {
    console.error('사용법: node scripts/naver_draft.js --draft drafts/xxx.draft.json [--dry-run]');
    process.exit(1);
  }

  const draft = JSON.parse(fs.readFileSync(path.resolve(ROOT, args.draftPath), 'utf-8'));
  const config = JSON.parse(fs.readFileSync(path.join(ROOT, 'data', 'config.json'), 'utf-8'));
  const targetUrl = args.url || `https://blog.naver.com/${config.naverBlogId}?Redirect=Write`;
  if (!args.url && !config.naverBlogId) {
    console.error('data/config.json 의 naverBlogId 를 먼저 채워주세요.');
    process.exit(1);
  }

  const result = makeResult(draft);

  const { context } = await launchNaverContext({ headless: false });
  const page = await context.newPage();
  await installPublishGuard(page);

  await page.goto(targetUrl, { waitUntil: 'domcontentloaded' });

  const frame = await getEditorFrame(page);
  await dismissContinuePopup(frame);

  // 본문 전체 먼저 → 제목은 맨 마지막 (레이스 컨디션으로 섞임 방지)
  let videoInserted = false;
  for (let i = 0; i < draft.blocks.length; i++) {
    const block = draft.blocks[i];
    const next = draft.blocks[i + 1];
    await writeBlock(frame, block, next, result);
    if (!videoInserted && draft.video && block.type === 'text') {
      await insertVideo(frame, draft, result);
      videoInserted = true;
    }
  }

  if (draft.place) {
    await insertPlace(frame, draft.place, result);
  }

  await writeTitle(frame, draft.title);
  let titleActual = await readTitleText(frame);
  result.titleMatch = titleActual.trim() === draft.title.trim();
  if (!result.titleMatch) {
    await fixTitle(frame, draft.title);
    titleActual = await readTitleText(frame);
    result.titleMatch = titleActual.trim() === draft.title.trim();
  }

  let bodyActual = await readBodyParagraphs(frame);
  const expectedFirstLine = firstTextOf(draft.blocks);
  result.bodyMatch = bodyActual.join('\n').includes(expectedFirstLine.slice(0, 10));
  if (!result.bodyMatch && expectedFirstLine) {
    await prependMissingFirstLine(frame, expectedFirstLine);
    bodyActual = await readBodyParagraphs(frame);
    result.bodyMatch = bodyActual.join('\n').includes(expectedFirstLine.slice(0, 10));
  }

  if (!args.dryRun) {
    await openPublishPanelAndSetTags(frame, draft.tags || [], config.tagLimit || 30, result);
    await closePanelKeepClosed(page);
    await saveAsDraft(page);
  }

  const ts = new Date().toISOString().replace(/[:.]/g, '-');
  const draftsDir = path.join(ROOT, 'drafts');
  fs.mkdirSync(draftsDir, { recursive: true });

  if (!args.dryRun) {
    await page.screenshot({ path: path.join(draftsDir, `_verify_${ts}.png`), fullPage: true }).catch(() => {});
  }

  const finalTitle = await readTitleText(frame);
  const finalBody = await readBodyParagraphs(frame);
  const dumpText = [`TITLE: ${finalTitle}`, '', ...finalBody].join('\n');
  fs.writeFileSync(path.join(draftsDir, `_verify_${ts}.txt`), dumpText, 'utf-8');

  printResultBlock(result, args.dryRun);
  console.log(`검증용 텍스트 덤프: drafts/_verify_${ts}.txt — 초안 원문과 반드시 전문 대조하세요.`);

  if (args.dryRun) {
    console.log('\n[--dry-run] 저장을 생략했습니다. 브라우저를 열어둔 채 확인하세요 (Ctrl+C로 종료).');
  } else {
    await context.close();
  }
}

const isDirectRun = process.argv[1] && import.meta.url === `file://${process.argv[1]}`;
if (isDirectRun) {
  main().catch((err) => {
    console.error(err);
    process.exit(1);
  });
}
