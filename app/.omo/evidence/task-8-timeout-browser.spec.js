const { test, expect } = require('playwright/test');

for (const width of [1440, 390]) {
  test(`timed-out projection ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
    await page.goto('http://127.0.0.1:8765/');
    await expect(page.locator('.status-failed').first()).toContainText('failed');
    await expect(page.getByText('ROLE_TIMEOUT', { exact: true })).toBeVisible();
    expect(await page.locator('body').textContent()).not.toContain('raw provider response');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
    const response = await page.request.get('http://127.0.0.1:8765/api/runs/harness-timed_out');
    expect(response.status()).toBe(200);
    const detail = await response.json();
    expect(detail.stages[0].status).toBe('failed');
  });
}
