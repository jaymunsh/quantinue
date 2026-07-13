import { rename, writeFile } from 'node:fs/promises';
import { writeSync } from 'node:fs';
import { resolve } from 'node:path';

import lighthouse from 'lighthouse';
import { chromium } from 'playwright';

const url = 'http://127.0.0.1:8765/';
const artifact = resolve('.omo/evidence/task-8-lighthouse.json');
const temporaryArtifact = `${artifact}.${process.pid}.tmp`;
const output = [];

try {
  let sequence = 0;
  for (const preset of ['mobile', 'desktop']) {
    for (let run = 1; run <= 3; run += 1) {
      sequence += 1;
      const port = 9332 + sequence;
      const chrome = await chromium.launch({
        channel: 'chrome',
        headless: true,
        ignoreDefaultArgs: ['--disable-back-forward-cache'],
        args: [`--remote-debugging-port=${port}`],
      });
      try {
        const result = await lighthouse(url, { port, logLevel: 'error' }, {
          extends: 'lighthouse:default',
          settings: {
            formFactor: preset,
            throttling: preset === 'desktop'
              ? { rttMs: 40, throughputKbps: 10240, cpuSlowdownMultiplier: 1 }
              : undefined,
            screenEmulation: preset === 'desktop'
              ? { mobile: false, width: 1350, height: 940, deviceScaleFactor: 1, disabled: false }
              : undefined,
            onlyCategories: ['performance', 'accessibility', 'best-practices', 'seo'],
          },
        });
        const scores = Object.fromEntries(
          Object.entries(result.lhr.categories).map(([key, value]) => [key, Math.round(value.score * 100)]),
        );
        const subAudits = Object.values(result.lhr.audits)
          .filter((audit) => audit.score !== null && audit.score < 1 && audit.scoreDisplayMode !== 'notApplicable')
          .map((audit) => ({
            id: audit.id,
            title: audit.title,
            score: audit.score,
            displayValue: audit.displayValue ?? null,
            details: audit.details?.items ?? null,
          }));
        output.push({ preset, run, scores, subAudits });
      } finally {
        await chrome.close();
      }
    }
  }
  await writeFile(temporaryArtifact, `${JSON.stringify(output, null, 2)}\n`, 'utf8');
  await rename(temporaryArtifact, artifact);
  const all100 = output.every((entry) => Object.values(entry.scores).every((score) => score === 100));
  const summary = { artifact, runs: output.length, allCategories100: all100 };
  writeSync(process.stdout.fd, `${JSON.stringify(summary)}\n`);
  process.exit(all100 ? 0 : 1);
} catch (error) {
  writeSync(process.stderr.fd, `${error instanceof Error ? error.stack : String(error)}\n`);
  process.exit(1);
}
