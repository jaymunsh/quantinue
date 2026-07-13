const { test, expect } = require('playwright/test');

const base = process.env.F3_BASE_URL || 'http://127.0.0.1:18765';

for (const [width, height] of [[1440, 1000], [1024, 1000], [768, 1000], [390, 844]]) {
  test(`offline completed pipeline ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await page.goto(base);
    await expect(page.locator('.stage-record')).toHaveCount(11);
    await expect(page.locator('.evidence-list > li')).toHaveCount(11);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
    const apiRuns = await (await page.request.get(`${base}/api/runs`)).json();
    expect(await page.locator('.safety-list code').nth(1).textContent()).toBe(apiRuns[0].order.client_order_id);
    await page.screenshot({ path: `.omo/evidence/f3-completed-${width}x${height}.png`, fullPage: true });
  });
}

test('keyboard and reduced motion', async ({ page }) => {
  await page.goto(base);
  await page.keyboard.press('Tab');
  await expect(page.locator('.skip-link')).toBeFocused();
  await page.keyboard.press('Enter');
  await page.keyboard.press('Tab');
  await expect(page.locator('#ticker')).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(page.getByRole('button', { name: '파이프라인 실행' })).toBeFocused();
  await page.emulateMedia({ reducedMotion: 'reduce' });
  expect(await page.locator('button').evaluate(e => getComputedStyle(e).transitionDuration)).toBe('0s');
});
