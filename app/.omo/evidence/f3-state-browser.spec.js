const { test, expect } = require('playwright/test');
const state = process.env.F3_STATE;
const base = process.env.F3_BASE_URL;

for (const [width, height] of [[1440, 1000], [390, 844]]) {
  test(`${state} store-backed UI ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await page.goto(base);
    const runs = await (await page.request.get(`${base}/api/runs`)).json();
    expect(runs[0].status).toBe(state);
    await expect(page.locator(`.status-${state}`).first()).toContainText(state);
    await expect(page.locator('.stage-record')).toHaveCount(1);
    expect(await page.locator('body').textContent()).not.toContain('raw provider response');
    if (state !== 'running') await expect(page.getByText('ProviderTimeout', { exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
    await page.screenshot({ path: `.omo/evidence/f3-${state}-${width}x${height}.png`, fullPage: true });
  });
}
