import { chromium } from 'playwright';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
export const ROOT = path.resolve(__dirname, '..', '..');
export const PROFILE_DIR = path.join(ROOT, 'naver-profile');

// 절대 규칙 2: 발행은 항상 사람이. 이 셀렉터로 진짜 발행 버튼 클릭을 캡처 단계에서 원천 차단한다.
const PUBLISH_BUTTON_SELECTOR = 'button[data-testid="seOnePublishBtn"]';

export async function launchNaverContext({ headless = false } = {}) {
  const context = await chromium.launchPersistentContext(PROFILE_DIR, {
    headless,
    viewport: { width: 1600, height: 1000 },
    locale: 'ko-KR',
  });
  return { context };
}

// 어떤 경우에도 이 함수를 제거하거나 호출을 생략하지 않는다 (CLAUDE.md 절대 규칙 2).
export async function installPublishGuard(page) {
  await page.addInitScript((selector) => {
    document.addEventListener(
      'click',
      (e) => {
        const target = e.target instanceof Element ? e.target.closest(selector) : null;
        if (target) {
          e.preventDefault();
          e.stopPropagation();
          e.stopImmediatePropagation();
          // eslint-disable-next-line no-console
          console.warn('[publish-guard] 발행 버튼 클릭이 차단되었습니다. 이 툴은 임시저장까지만 자동화합니다.');
        }
      },
      true,
    );
  }, PUBLISH_BUTTON_SELECTOR);
}

export async function getEditorFrame(page) {
  const frameHandle = await page.waitForSelector('iframe#mainFrame', { timeout: 30000 });
  const frame = await frameHandle.contentFrame();
  if (!frame) {
    throw new Error('mainFrame iframe을 찾을 수 없습니다. node scripts/probe_selectors.js 로 실측하세요.');
  }
  await frame.waitForSelector('.se-title-text, .se-section-text', { timeout: 30000 }).catch(() => {});
  return frame;
}

export async function dismissContinuePopup(frame) {
  const cancelBtn = frame.locator('.se-popup-button-cancel');
  if (await cancelBtn.count()) {
    try {
      await cancelBtn.first().click({ timeout: 3000 });
    } catch {
      // 팝업이 없으면 조용히 넘어간다
    }
  }
}

export async function closeLeftoverDim(page, frame) {
  // 반드시 :visible 로 한정한다 — class="se-dim" 요소는 이미 닫힌(display:none) 다른 위젯이나
  // 아직 열지도 않은 위젯에도 구조적으로 남아있을 수 있어, count()만 보면 엉뚱한 요소까지 강제 제거하게 된다.
  const dim = frame.locator('.se-dim:visible, [class*="dimLayer"]:visible');
  if (!(await dim.count())) return;

  const closeBtn = frame.locator('[class*="se-popup-button-close"]:visible').first();
  if (await closeBtn.count()) {
    await closeBtn.click({ timeout: 3000 }).catch(() => {});
  }

  // 닫기 버튼이 없거나, 다른 위젯의 버튼을 잘못 짚었거나, 클릭이 실패한 경우까지 전부 커버하기 위해
  // 닫기 시도 후에도 "보이는" dim이 남아있으면 그것만 강제 제거한다.
  if (await dim.count()) {
    await dim.evaluateAll((els) => els.forEach((el) => el.remove())).catch(() => {});
  }
}

const EMOJI_RE = /(\p{Extended_Pictographic}️?)/gu;

// 한글은 keyboard.type()이 아니라 반드시 insertText() — IME 조합 꼬임 방지.
// 이모지는 별도 호출로 분리 삽입 — 함께 넣으면 이모지 뒤 텍스트가 유실된다.
export async function insertTextWithEmoji(page, text) {
  const parts = text.split(EMOJI_RE).filter(Boolean);
  for (const part of parts) {
    await page.keyboard.insertText(part);
  }
}

export async function clickToolbarButton(frame, partialClass) {
  const btn = frame.locator(`button[class*="${partialClass}"]`).first();
  await btn.click();
}
