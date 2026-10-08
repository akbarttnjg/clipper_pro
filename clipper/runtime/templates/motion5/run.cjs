const fs=require('node:fs');const path=require('node:path');
(async()=>{
 const input=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));process.chdir(__dirname);
 if(!fs.existsSync(input.browser))throw Error('A local browser is required');
 const {createServer}=await import('vite');const {chromium}=require('playwright-core');
 const server=await createServer({configFile:path.join(__dirname,'vite.config.mjs')});let browser;
 try{
  await server.listen();const port=server.httpServer.address().port;
  browser=await chromium.launch({executablePath:input.browser,headless:true});const page=await browser.newPage();
  await page.route('**/*',route=>{const url=new URL(route.request().url());return url.hostname==='127.0.0.1'?route.continue():route.abort()});
  await page.goto(`http://127.0.0.1:${port}/runner.html`);await page.waitForFunction(()=>window.clipperReady,{},{timeout:90000});
  fs.mkdirSync(input.frames,{recursive:true});
  for(let f=0;f<Math.ceil(input.duration*input.fps);f++){
   const png=await page.evaluate(f=>window.clipperFrame(f),f);
   fs.writeFileSync(path.join(input.frames,String(f).padStart(6,'0')+'.png'),Buffer.from(png,'base64'));
  }
 }finally{if(browser)await browser.close();await server.close()}
})().catch(err=>{console.error(err);process.exitCode=1});
