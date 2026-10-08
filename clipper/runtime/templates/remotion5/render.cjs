const fs=require('node:fs');const path=require('node:path');
const {bundle}=require('@remotion/bundler');
const {selectComposition,renderMedia}=require('@remotion/renderer');
(async()=>{
 const input=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
 if(!input.browser||!fs.existsSync(input.browser))throw Error('A local browser executable is required');
 const serveUrl=await bundle({entryPoint:path.join(__dirname,'index.jsx'),outDir:path.join(path.dirname(input.output),'remotion-bundle')});
 const options={serveUrl,inputProps:input,browserExecutable:input.browser,logLevel:'warn',onBrowserDownload:()=>{throw Error('Offline rendering cannot download a browser')}};
 const composition=await selectComposition({...options,id:'ClipperCaptions'});
 await renderMedia({...options,composition,codec:'vp9',imageFormat:'png',pixelFormat:'yuva420p',outputLocation:input.output,concurrency:1,overwrite:true});
})().catch(e=>{console.error(e.message);process.exitCode=1});
