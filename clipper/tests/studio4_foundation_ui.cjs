/* Real browser + Studio API fixture; heavy render completion is simulated. */
let playwright;try{playwright=require('playwright')}catch{playwright=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright')}
const fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{
 const browser=await playwright.chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,args:['--no-sandbox','--disable-dev-shm-usage']});
 const out=process.argv[3];fs.mkdirSync(out,{recursive:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1080}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  const url=process.argv[2];await page.goto(url);
  await page.waitForFunction(()=>document.querySelector('#projects').options.length>1);
  await page.locator('#projects').selectOption(await page.locator('#projects option').nth(1).getAttribute('value'));
  await page.locator('[data-step="story"]').click();await page.getByRole('button',{name:'Edit klip ini →',exact:true}).first().click();
  const box=page.locator('#export-actions');await box.getByRole('button',{name:'Buat paket CapCut + DaVinci',exact:true}).waitFor();
  assert.equal(await box.getByRole('button',{name:'Buat paket CapCut + DaVinci',exact:true}).isDisabled(),true);
  assert.ok((await box.innerText()).includes('Render final revisi aktif dahulu'));
  await page.screenshot({path:out+'/stale-final.png',fullPage:true});
  await page.getByRole('button',{name:'Render final',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#jobs').textContent.includes('Render final · menunggu'));
  await page.request.post(url+'__test/complete-render');
  await page.locator('.toolbar').getByRole('button',{name:'Muat revisi terbaru',exact:true}).click();
  await page.waitForFunction(()=>!document.querySelector('#export-actions button:last-child')?.disabled);
  assert.equal(await box.getByRole('button',{name:'Buat paket CapCut + DaVinci',exact:true}).isEnabled(),true);
  await box.getByRole('button',{name:'Buat paket CapCut + DaVinci',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#jobs').textContent.includes('Paket editor · menunggu'));
  await page.locator('[data-step="results"]').click();await page.getByRole('link',{name:'Unduh MP4',exact:true}).first().waitFor();
  assert.equal(await page.getByRole('link',{name:'Unduh MP4',exact:true}).count(),2);
  const text=await page.locator('main').innerText();assert.ok(text.includes('9:16')&&text.includes('16:9'));
  assert.ok(text.includes('CapCut: gagal dibuat · struktur perlu diperiksa · impor di editor belum diuji'));
  assert.ok(text.includes('DaVinci Resolve: dibuat · struktur lolos · impor di editor belum diuji'));
  await page.screenshot({path:out+'/editor-results.png',fullPage:true});
  assert.deepEqual(errors,[]);
  const report={passed:true,fixture:'Real Studio API/SQLite + FFmpeg synthetic media; heavy worker completion simulated',
   checks:['stale_export_disabled','actionable_final_refresh','render_then_export_queue','two_independent_clips_and_ratios','separate_editor_failure_status','native_import_pending'],page_errors:errors};
  fs.writeFileSync(out+'/browser-report.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
