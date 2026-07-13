const { test, expect } = require("playwright/test");

const base = process.env.LIVE_PROGRESS_BASE_URL || "http://127.0.0.1:8149";
const sizes = [
  [1440, 1000],
  [1024, 900],
  [768, 900],
  [390, 844],
];

test("active control room polls through a delayed role and stops at terminal", async ({ browser }) => {
  const errors = [];
  const noJavaScriptContext = await browser.newContext({
    javaScriptEnabled: false,
    viewport: { width: 390, height: 844 },
  });
  const noJavaScriptPage = await noJavaScriptContext.newPage();
  noJavaScriptPage.on("console", (message) => errors.push(message.text()));
  noJavaScriptPage.on("pageerror", (error) => errors.push(error.message));
  await noJavaScriptPage.goto(base);
  await expect(noJavaScriptPage.locator("#live-pipeline")).toBeVisible();
  await expect(noJavaScriptPage.locator("[data-live-current]")).toContainText("05 공시 분석");
  expect(await noJavaScriptPage.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  await noJavaScriptPage.screenshot({ path: ".omo/evidence/live-progress/task-4-390-no-js.png", fullPage: true });
  await noJavaScriptContext.close();

  const contexts = await Promise.all(sizes.map(([width, height]) => browser.newContext({ viewport: { width, height } })));
  const pages = await Promise.all(contexts.map((context) => context.newPage()));
  const requests = [];
  for (const page of pages) {
    page.on("console", (message) => errors.push(message.text()));
    page.on("pageerror", (error) => errors.push(error.message));
  }
  pages[0].on("request", (request) => {
    if (request.url() === `${base}/api/runs`) requests.push(request.url());
  });
  await Promise.all(pages.map((page) => page.goto(base)));
  for (let index = 0; index < pages.length; index += 1) {
    const page = pages[index];
    const [width] = sizes[index];
    await expect(page.locator("#live-pipeline")).toBeVisible();
    await expect(page.locator("[data-live-current]")).toContainText("05 공시 분석");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
    await page.screenshot({ path: `.omo/evidence/live-progress/task-4-${width}-active.png`, fullPage: true });
  }
  await expect(pages[0].locator("#live-pipeline")).toHaveCount(0, { timeout: 35000 });
  await expect(pages[0].locator(".summary-primary")).toContainText("completed");
  const terminalRequestCount = requests.length;
  await pages[0].waitForTimeout(1800);
  expect(requests).toHaveLength(terminalRequestCount);
  await pages[0].screenshot({ path: ".omo/evidence/live-progress/task-4-1440-terminal.png", fullPage: true });
  expect(errors).toEqual([]);
  await Promise.all(contexts.map((context) => context.close()));
});
