import { launchNaverContext, installPublishGuard } from './lib/browser.js';

function waitForEnter() {
  return new Promise((resolve) => {
    process.stdin.resume();
    process.stdin.once('data', () => resolve());
  });
}

async function main() {
  console.log('네이버 로그인 브라우저를 엽니다.');
  console.log('로그인(비밀번호/2단계 인증/패스키 모두 가능) 후 블로그 화면이 정상적으로 보이면,');
  console.log('이 터미널로 돌아와 Enter 키를 눌러 종료하세요.\n');

  const { context } = await launchNaverContext({ headless: false });
  const page = await context.newPage();
  await installPublishGuard(page);
  await page.goto('https://nid.naver.com/nidlogin.login', { waitUntil: 'domcontentloaded' });

  await waitForEnter();
  await context.close();

  console.log('\n로그인 세션이 naver-profile/ 폴더에 저장되었습니다.');
  console.log('이 폴더에는 로그인 쿠키가 들어있으니 외부에 공유하거나 커밋하지 마세요 (.gitignore에 이미 포함됨).');
  process.exit(0);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
