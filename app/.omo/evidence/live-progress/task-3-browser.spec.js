const { test, expect } = require('playwright/test');

const base = process.env.LIVE_PROGRESS_BASE_URL || 'http://127.0.0.1:8143';
const sizes = [
  [1440, 1000],
  [1024, 900],
  [768, 900],
  [390, 844],
];

test('active control room progresses safely and remains responsive', async ({ browser }) => {
  const noJavaScriptContext = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 390, height: 844 } });
  const noJavaScriptPage = await noJavaScriptContext.newPage();
  await noJavaScriptPage.goto(base);
  await expect(noJavaScriptPage.locator('#live-pipeline')).toBeVisible();
  await expect(noJavaScriptPage.locator('[data-live-current]')).toContainText('05 공시 분석');
  await expect(noJavaScriptPage.locator('[data-live-announcement]')).toContainText('NVDA 실행');
  expect(await noJavaScriptPage.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  await noJavaScriptContext.close();
  const contexts = await Promise.all(sizes.map(([width, height]) => browser.newContext({ viewport: { width, height } })));
  const pages = await Promise.all(contexts.map((context) => context.newPage()));
  const requests = [];
  pages[0].on('request', (request) => {
    if (request.url() === `${base}/api/runs`) requests.push(request.url());
  });

  await Promise.all(pages.map((page) => page.goto(base)));
  for (const page of pages) {
    await expect(page.locator('#live-pipeline')).toBeVisible();
    await expect(page.locator('[data-live-current]')).toContainText('05 공시 분석');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  }
  await expect(pages[0].locator('[data-live-status]')).toHaveText('완료', { timeout: 10000 });
  const terminalRequestCount = requests.length;
  await pages[0].waitForTimeout(1800);
  expect(requests).toHaveLength(terminalRequestCount);
  await pages[3].screenshot({ path: '.omo/evidence/live-progress/task-3-390.png', fullPage: true });
  await Promise.all(contexts.map((context) => context.close()));
});
