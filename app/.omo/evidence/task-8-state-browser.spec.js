const { test, expect } = require('playwright/test');

const state = process.env.EXPECTED_STATE;

for (const width of [1440, 390]) {
  test(`${state} control room ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
    await page.goto('http://127.0.0.1:8765/');
    await expect(page.getByText(/계정 없이 전체 계약을 검증합니다/)).toBeVisible();
    const apiResponse = await page.request.get('http://127.0.0.1:8765/api/runs');
    const apiRuns = await apiResponse.json();
    expect(apiRuns[0].status).toBe(state);
    await expect(page.locator(`.status-${state}`).first()).toContainText(state);
    await expect(page.locator('.stage-record')).toHaveCount(1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
    expect(await page.locator('body').textContent()).not.toContain('raw provider response');
    if (state === 'retrying' || state === 'failed') {
      await expect(page.getByText('ProviderTimeout', { exact: true })).toBeVisible();
    } else {
      await expect(page.getByText('ProviderTimeout', { exact: true })).toHaveCount(0);
    }
    const badgeWidth = await page.locator(`.status-${state}`).first().evaluate((element) => element.getBoundingClientRect().width);
    const badgeParentWidth = await page.locator(`.status-${state}`).first().evaluate((element) => element.parentElement.getBoundingClientRect().width);
    expect(badgeWidth).toBeLessThan(badgeParentWidth / 2);
    await page.keyboard.press('Tab');
    await expect(page.locator('.skip-link')).toBeFocused();
    await page.keyboard.press('Enter');
    await page.keyboard.press('Tab');
    await expect(page.locator('#ticker')).toBeFocused();
    await page.keyboard.press('Tab');
    await expect(page.getByRole('button', { name: '파이프라인 실행' })).toBeFocused();
    await page.emulateMedia({ reducedMotion: 'reduce' });
    expect(await page.locator('button').evaluate((element) => getComputedStyle(element).transitionDuration)).toBe('0s');
  });
}
