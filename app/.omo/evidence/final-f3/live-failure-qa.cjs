const fs = require("node:fs/promises");
const { chromium } = require("playwright");

const baseUrl = "http://127.0.0.1:18011";
const evidenceDir = ".omo/evidence/final-f3";
const viewports = [
  [1440, 1000],
  [390, 844],
];

async function main() {
  const browser = await chromium.launch({ headless: true });
  const results = [];
  try {
    for (const [width, height] of viewports) {
      const context = await browser.newContext({ viewport: { width, height } });
      const page = await context.newPage();
      await page.goto(baseUrl, { waitUntil: "networkidle" });
      await page.getByText("timed_out", { exact: true }).waitFor();
      await page.getByText("ROLE_TIMEOUT", { exact: true }).waitFor();
      const state = await page.evaluate(() => ({
        horizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
        failedStages: [...document.querySelectorAll(".stage-record.stage-failed")].length,
        rawPayloadVisible: document.body.textContent?.includes("qa-only raw provider payload") ?? false,
        timedOutVisible: document.body.textContent?.includes("timed_out") ?? false,
        failureCodeVisible: document.body.textContent?.includes("ROLE_TIMEOUT") ?? false,
      }));
      if (state.horizontalOverflow || state.failedStages !== 1 || state.rawPayloadVisible) {
        throw new Error(`failure state regression at ${width}`);
      }
      const screenshot = `${evidenceDir}/live-timed-out-${width}x${height}.png`;
      await page.screenshot({ path: screenshot, fullPage: true });
      results.push({ width, height, screenshot, ...state });
      await context.close();
    }
  } finally {
    await browser.close();
  }
  await fs.writeFile(`${evidenceDir}/live-failure-results.json`, `${JSON.stringify(results, null, 2)}\n`);
  process.stdout.write(`${JSON.stringify(results, null, 2)}\n`);
}

main().catch((error) => {
  process.stderr.write(`${error.stack}\n`);
  process.exitCode = 1;
});
