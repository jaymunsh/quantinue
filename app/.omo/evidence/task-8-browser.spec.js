const { test, expect } = require('playwright/test');

const widths = [1440, 1024, 768, 390];

for (const width of widths) {
  test(`completed control room ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
    await page.goto('http://127.0.0.1:8765/');
    await expect(page.getByText(/계정 없이 전체 계약을 검증합니다/)).toBeVisible();
    const clientId = await page.locator('.safety-list code').nth(1).textContent();
    const response = await page.request.get('http://127.0.0.1:8765/api/runs');
    const runs = await response.json();
    expect(clientId).toBe(runs[0].order.client_order_id);
    expect(await page.locator('.stage-record').count()).toBe(11);
    expect(await page.locator('.evidence-list > li').count()).toBe(11);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
    await page.keyboard.press('Tab');
    await expect(page.locator('.skip-link')).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(page.locator('#main')).toBeInViewport();
    await page.keyboard.press('Tab');
    await expect(page.locator('#ticker')).toBeFocused();
    await page.keyboard.press('Tab');
    await expect(page.getByRole('button', { name: '파이프라인 실행' })).toBeFocused();
    await page.emulateMedia({ reducedMotion: 'reduce' });
    expect(await page.locator('button').evaluate((element) => getComputedStyle(element).transitionDuration)).toBe('0s');
  });
}
