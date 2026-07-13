const { test, expect } = require('playwright/test');

const normalBase = 'http://127.0.0.1:18094';
const timeoutBase = 'http://127.0.0.1:18093';
const viewports = [[1440, 1000], [1024, 1000], [768, 1000], [390, 844]];

async function assertCommonA11y(page) {
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
  expect(await page.locator('button').evaluate((node) => getComputedStyle(node).transitionDuration)).toBe('0s');
}

for (const [width, height] of viewports) {
  test(`no-key completed mock control room ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await page.goto(normalBase);
    const created = await (await page.request.post(`${normalBase}/api/runs`, { data: { ticker: 'NVDA' } })).json();
    await page.goto(normalBase);
    await expect(page.getByText('계정 없이 전체 계약을 검증합니다.')).toBeVisible();
    await expect(page.getByText('근거 계보')).toBeVisible();
    await expect(page.getByText('T+5 리뷰')).toBeVisible();
    await expect(page.getByText('deterministic-mock-v1').first()).toBeVisible();
    await expect(page.getByText('mock', { exact: true }).first()).toBeVisible();
    expect(await page.locator('.stage-record').count()).toBe(11);
    expect(await page.locator('.evidence-list > li').count()).toBe(11);
    const detail = await (await page.request.get(`${normalBase}/api/runs/${created.run_id}`)).json();
    expect(detail.evidence[4].model_provider).toBe('mock');
    expect(detail.evidence[4].model_name).toBe('deterministic-mock-v1');
    expect(detail.evidence[4].parent_evidence_ids.length).toBeGreaterThan(0);
    expect(detail.review).not.toBeNull();
    await assertCommonA11y(page);
    await page.screenshot({ path: `.omo/evidence/final-f3/mock-${width}x${height}.png`, fullPage: true });
  });

  test(`persisted timed_out control room ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await page.goto(timeoutBase);
    await expect(page.locator('.status-failed').first()).toContainText('failed');
    await expect(page.getByText('timed_out', { exact: true })).toBeVisible();
    await expect(page.getByText('ROLE_TIMEOUT', { exact: true })).toBeVisible();
    expect(await page.locator('body').textContent()).not.toContain('raw provider response');
    const detail = await (await page.request.get(`${timeoutBase}/api/runs/harness-timed_out`)).json();
    expect(detail.stages[0].status).toBe('failed');
    expect(detail.stages[0].attempts[0].status).toBe('timed_out');
    expect(JSON.stringify(detail)).not.toContain('raw provider response');
    await assertCommonA11y(page);
    await page.screenshot({ path: `.omo/evidence/final-f3/timed-out-${width}x${height}.png`, fullPage: true });
  });
}
