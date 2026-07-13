const fs = require("node:fs/promises");
const { chromium } = require("playwright");

const baseUrl = "http://127.0.0.1:18011";
const evidenceDir = ".omo/evidence/final-f3";
const viewports = [
  [1440, 1000],
  [1024, 1000],
  [768, 1000],
  [390, 844],
];

async function main() {
  const browser = await chromium.launch({ headless: true });
  const results = [];
  try {
    for (const [width, height] of viewports) {
      const context = await browser.newContext({ viewport: { width, height } });
      const page = await context.newPage();
      const consoleErrors = [];
      page.on("console", (message) => {
        if (message.type() === "error") consoleErrors.push(message.text());
      });
      await page.goto(baseUrl, { waitUntil: "networkidle" });
      if (width === 1440) {
        await page.locator("#ticker").fill("NVDA");
        await page.getByRole("button", { name: "파이프라인 실행" }).click();
        await page.waitForURL(`${baseUrl}/`);
      }
      await page.getByRole("heading", { name: "파이프라인 운영실" }).waitFor();
      await page.getByRole("heading", { name: "역할별 결과" }).waitFor();
      await page.getByRole("heading", { name: "근거 계보" }).waitFor();
      await page.getByRole("heading", { name: "주문·리뷰" }).waitFor();
      const state = await page.evaluate(() => ({
        horizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
        stageCount: document.querySelectorAll(".stage-record").length,
        evidenceCount: document.querySelectorAll(".evidence-list > li").length,
        statusBadges: [...document.querySelectorAll(".status-badge")].map((node) => node.textContent?.trim()),
      }));
      if (state.horizontalOverflow) throw new Error(`horizontal overflow at ${width}`);
      if (state.stageCount !== 11 || state.evidenceCount !== 11) throw new Error(`unexpected dashboard content at ${width}`);
      await page.keyboard.press("Tab");
      const skipFocused = await page.locator(".skip-link").evaluate((node) => node === document.activeElement);
      if (!skipFocused) throw new Error(`skip link focus failed at ${width}`);
      await page.emulateMedia({ reducedMotion: "reduce" });
      const reducedMotion = await page.getByRole("button", { name: "파이프라인 실행" }).evaluate((node) => getComputedStyle(node).transitionDuration);
      if (reducedMotion !== "0s") throw new Error(`reduced-motion failed at ${width}`);
      const screenshot = `${evidenceDir}/live-completed-${width}x${height}.png`;
      await page.screenshot({ path: screenshot, fullPage: true });
      results.push({ width, height, screenshot, ...state, skipFocused, reducedMotion, consoleErrors });
      await context.close();
    }
  } finally {
    await browser.close();
  }
  await fs.writeFile(`${evidenceDir}/live-browser-results.json`, `${JSON.stringify(results, null, 2)}\n`);
  process.stdout.write(`${JSON.stringify(results, null, 2)}\n`);
}

main().catch((error) => {
  process.stderr.write(`${error.stack}\n`);
  process.exitCode = 1;
});
