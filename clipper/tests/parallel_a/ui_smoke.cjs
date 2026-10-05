// Run a local HTTP server at the workspace root, then pass the fixture URL.
let playwright;try{playwright=require('playwright')}catch{playwright=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright')}
const {chromium}=playwright;
const assert=require('node:assert/strict');
const fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE||undefined,args:['--no-sandbox','--disable-dev-shm-usage']});
 try{
  const page=await browser.newPage({viewport:{width:1100,height:1000}});const errors=[];
  page.on('pageerror',e=>errors.push(e.message));await page.goto(process.argv[2]);await page.waitForFunction(()=>!!window.fixture);
  await page.getByText('Revisi 1 · initial / vertical',{exact:true}).waitFor();
  const field=page.getByLabel('Ejaan yang Anda setujui');await field.fill('XAUUSD manual');
  await page.getByRole('button',{name:'Simpan koreksi',exact:true}).click();
  await page.getByText('Ada perubahan dari tab lain.',{exact:false}).waitFor();
  assert.equal(await field.inputValue(),'XAUUSD manual');
  await page.getByRole('button',{name:'Muat revisi terbaru',exact:true}).click();await page.getByText('Revisi 2 · initial / vertical',{exact:true}).waitFor();
  assert.equal(await field.inputValue(),'XAUUSD manual');
  await page.getByRole('button',{name:'Simpan koreksi',exact:true}).click();await page.getByText('Revisi 3 · initial / vertical',{exact:true}).waitFor();
  const payloads=await page.evaluate(()=>window.fixture.calls);
  assert.equal(payloads[0].expected_revision,1);assert.equal(payloads[1].expected_revision,2);assert.ok(payloads[0].operation_id);
  await page.evaluate(()=>{window.fixture.component.update({target:window.fixture.target('slow'),revision:1});window.fixture.component.update({target:window.fixture.target('new-clip'),revision:1})});
  await page.getByText('Revisi 1 · new-clip / vertical',{exact:true}).waitFor();await page.evaluate(()=>window.fixture.resolveLate());
  assert.equal(await page.locator('.analysis-message').textContent(),'Revisi 1 · new-clip / vertical');
  await page.waitForFunction(()=>document.querySelector('.analysis-card video').readyState>=1);
  assert.ok((await page.locator('.analysis-card video').getAttribute('poster')).includes('synthetic-source.png'));
  assert.equal(await page.getByRole('button',{name:'Coba muat lagi',exact:true}).isVisible(),false);
  await page.screenshot({path:process.argv[3],fullPage:true});
  assert.deepEqual(errors,[]);const report={passed:true,fixture:true,checks:['revision_payload','conflict_preserves_draft','refresh_preserves_draft','late_snapshot_ignored','poster','video_metadata','retry_hidden_when_loaded'],page_errors:errors};fs.writeFileSync(process.argv[3]+'.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
