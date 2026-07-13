import { writeFile } from 'node:fs/promises';
import lighthouse from 'lighthouse';
import { chromium } from 'playwright';
const url = process.env.F3_BASE_URL || 'http://127.0.0.1:18765/';
const output = [];
for (const preset of ['mobile', 'desktop']) {
  for (let run = 1; run <= 3; run++) {
    const port = 19330 + output.length;
    const chrome = await chromium.launch({channel:'chrome', headless:true,
      ignoreDefaultArgs:['--disable-back-forward-cache'], args:[`--remote-debugging-port=${port}`]});
    try {
      const result = await lighthouse(url, {port, logLevel:'error'}, {extends:'lighthouse:default', settings:{
        formFactor:preset,
        throttling:preset === 'desktop' ? {rttMs:40, throughputKbps:10240, cpuSlowdownMultiplier:1} : undefined,
        screenEmulation:preset === 'desktop' ? {mobile:false,width:1350,height:940,deviceScaleFactor:1,disabled:false}:undefined,
        onlyCategories:['performance','accessibility','best-practices','seo']}});
      output.push({preset,run,scores:Object.fromEntries(Object.entries(result.lhr.categories).map(([k,v])=>[k,Math.round(v.score*100)]))});
    } finally { await chrome.close(); }
  }
}
await writeFile('.omo/evidence/f3-lighthouse.json', JSON.stringify(output,null,2)+'\n');
if (!output.every(x => Object.values(x.scores).every(v => v === 100))) process.exitCode=1;
