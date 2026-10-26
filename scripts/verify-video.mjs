import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
const require=createRequire(process.env.SCOPEDESK_BROWSER_PACKAGE||'D:/codex/rx-market-pulse/dashboard/package.json');
const {chromium}=require('playwright');
const b=await chromium.launch({headless:true});
const p=await b.newPage();
try{
  await p.goto('file:///'+path.resolve('artifacts/ScopeDesk-Demo.webm').replaceAll('\\','/'));
  await p.locator('video').waitFor();
  const metadata=await p.locator('video').evaluate(async v=>{
    v.pause();if(v.readyState<1)await new Promise(resolve=>v.addEventListener('loadedmetadata',resolve,{once:true}));
    if(!Number.isFinite(v.duration)){v.currentTime=1e10;await new Promise(resolve=>v.addEventListener('seeked',resolve,{once:true}));}
    return {seconds:v.duration,width:v.videoWidth,height:v.videoHeight};
  });
  assert.ok(metadata.seconds>=60&&metadata.seconds<=90,JSON.stringify(metadata));
  for(const seconds of [10,35,55,68]){
    await p.locator('video').evaluate(async(v,t)=>{v.currentTime=t;await new Promise(resolve=>v.addEventListener('seeked',resolve,{once:true}));},seconds);
    await p.screenshot({path:`artifacts/video-frame-${seconds}.png`});
  }
  const result={verifiedAt:new Date().toISOString(),...metadata,file:'ScopeDesk-Demo.webm',bytes:(await fs.stat('artifacts/ScopeDesk-Demo.webm')).size,framesChecked:[10,35,55,68],playable:true};
  await fs.writeFile('artifacts/video-verification.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));
}finally{await b.close();}
