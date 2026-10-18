const { chromium } = require('playwright');
const path = require('path');

const BASE = 'D:/WorkBuddy workspace/2026-10-19-00-57-29';
const T = 'C:/Users/Administrator.DESKTOP-U1GRA70/AppData/Local/Temp';

function fileUrl(p) {
  return 'file:///' + p.replace(/\\/g, '/').replace(/ /g, '%20');
}

(async () => {
  const browser = await chromium.launch({ args: ['--no-sandbox', '--disable-gpu'] });
  const ctx = await browser.newContext({ deviceScaleFactor: 1.21 });

  // ── 1) 博客 PDF ──
  {
    const page = await ctx.newPage();
    await page.goto(fileUrl(BASE + '/wuwa-bot-blog.html'), { waitUntil: 'networkidle' });
    await page.waitForTimeout(1200);
    await page.pdf({
      path: BASE + '/wuwa-bot-blog.pdf',
      format: 'A4',
      printBackground: true,
      preferCSSPageSize: true,
    });
    const h = await page.evaluate(() => document.body.scrollHeight);
    console.log('blog pdf ok, page height =', h);
    await page.close();
  }

  // ── 2) 一图流 PDF ──
  {
    const page = await ctx.newPage();
    await page.goto(fileUrl(BASE + '/wuwa-bot-onepager.html'), { waitUntil: 'networkidle' });
    await page.waitForTimeout(1000);
    await page.emulateMedia({ media: 'screen' });
    await page.pdf({
      path: BASE + '/wuwa-bot-onepager.pdf',
      printBackground: true,
      preferCSSPageSize: true,
    });
    console.log('onepager pdf ok');
    await page.close();
  }

  // ── 3) 一图流 PNG（整页，按 poster 宽度）──
  {
    const page = await ctx.newPage();
    await page.setViewportSize({ width: 1080, height: 1200 });
    await page.goto(fileUrl(BASE + '/wuwa-bot-onepager.html'), { waitUntil: 'networkidle' });
    await page.waitForTimeout(1200);
    await page.emulateMedia({ media: 'screen' });
    const box = await page.evaluate(() => {
      const el = document.querySelector('.poster') || document.body;
      const r = el.getBoundingClientRect();
      return { w: Math.ceil(r.width), h: Math.ceil(el.scrollHeight) };
    });
    console.log('poster size =', box.w, 'x', box.h);
    await page.setViewportSize({ width: box.w, height: Math.min(box.h, 20000) });
    await page.waitForTimeout(400);
    await page.screenshot({
      path: BASE + '/wuwa-bot-onepager.png',
      fullPage: true,
      type: 'png',
    });
    console.log('onepager png ok');
    await page.close();
  }

  await browser.close();
  console.log('ALL_DONE');
})().catch((e) => { console.error('FAIL:', e.message); process.exit(1); });
