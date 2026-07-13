const { test, expect } = require('playwright/test');

const completedBase = 'http://127.0.0.1:8015';
const blockedBase = 'http://127.0.0.1:8016';
const viewports = [[1440, 1000], [1024, 1000], [768, 1000], [390, 844]];

function assertNoOverflow(page) {
  return page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth);
}

for (const [width, height] of viewports) {
  test(`completed detail brief ${width}px`, async ({ page }) => {
    const consoleErrors = [];
    page.on('console', message => {
      if (message.type() === 'error') consoleErrors.push(message.text());
    });
    page.on('pageerror', error => consoleErrors.push(error.message));
    await page.setViewportSize({ width, height });
    await page.goto(completedBase);
    await page.locator('#ticker').fill('NVDA');
    await page.getByRole('button', { name: '파이프라인 실행' }).click();
    await expect(page.locator('.brief-panel')).toBeVisible();
    await expect(page.getByText('수집부터 비평까지')).toBeVisible();
    await expect(page.locator('.source-link')).toHaveAttribute('href', 'https://example.invalid/fixture-news');
    await expect(page.locator('.source-reference code')).toContainText('sec://filing/fixture-filing');
    await expect(page.locator('.source-reference code')).toHaveCount(1);
    await page.locator('.critic-record summary').click();
    await expect(page.getByText('강한 반증과 하드 블로커 없음')).toBeVisible();
    expect(await assertNoOverflow(page)).toBe(true);
    expect(consoleErrors).toEqual([]);
    await page.locator('#ticker').focus();
    await page.screenshot({ path: `.omo/evidence/control-room-detail/task-5-completed-${width}x${height}.png`, fullPage: true });
  });
}

for (const [width, height] of viewports) {
  test(`blocked detail brief ${width}px`, async ({ page }) => {
    const consoleErrors = [];
    page.on('console', message => {
      if (message.type() === 'error') consoleErrors.push(message.text());
    });
    page.on('pageerror', error => consoleErrors.push(error.message));
    await page.setViewportSize({ width, height });
    await page.goto(blockedBase);
    await expect(page.locator('.status-blocked').first()).toContainText('blocked');
    await expect(page.locator('.brief-empty-state')).toContainText('표시 가능한 수집·판단 정보가 없습니다');
    expect(await assertNoOverflow(page)).toBe(true);
    expect(await page.locator('body').textContent()).not.toContain('raw provider response');
    expect(consoleErrors).toEqual([]);
    await page.screenshot({ path: `.omo/evidence/control-room-detail/task-5-blocked-${width}x${height}.png`, fullPage: true });
  });
}
