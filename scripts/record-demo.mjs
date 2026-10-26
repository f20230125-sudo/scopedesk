import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
const require=createRequire(process.env.SCOPEDESK_BROWSER_PACKAGE||'D:/codex/rx-market-pulse/dashboard/package.json');
const {chromium}=require('playwright');
const scope=process.env.SCOPEDESK_URL||'http://127.0.0.1:5058',loop=process.env.LOOPDESK_URL||'http://127.0.0.1:5055';
await fs.mkdir('artifacts/recording-raw',{recursive:true});
const browser=await chromium.launch({headless:true});
const context=await browser.newContext({viewport:{width:1440,height:960},recordVideo:{dir:'artifacts/recording-raw',size:{width:1440,height:960}}});
const p=await context.newPage(),chapters=[],start=Date.now();
async function chapter(title,body,seconds){
  chapters.push({seconds:Number(((Date.now()-start)/1000).toFixed(2)),title,body});
  await p.evaluate(({title,body})=>{document.querySelector('#demo-caption')?.remove();const box=document.createElement('div');box.id='demo-caption';box.style.cssText='position:fixed;bottom:18px;left:50px;right:50px;background:#163e31f5;color:#fff;padding:17px 24px;border:1px solid #90aa69;border-radius:8px;z-index:1000;font:15px/1.5 Segoe UI,sans-serif;pointer-events:none';const h=document.createElement('strong');h.style.cssText='display:block;font-size:19px;color:#e5f5af;margin-bottom:4px';h.textContent=title;const b=document.createElement('div');b.textContent=body;box.append(h,b);document.body.append(box);},{title,body});
  await p.waitForTimeout(seconds*1000);
}
try{
  await p.goto(scope);await chapter('ScopeDesk / Scope before sales','Independent ITAD qualification prototype. Every enquiry, inventory row and correction remains traceable. Fictional data throughout.',7);
  await p.getByRole('button',{name:'Open demo workspace'}).click();await p.locator('.case-card').filter({hasText:'Two-site laptop refresh'}).click();
  await chapter('01 / Find the contradictions before replying','The enquiry asks for 120 laptops and 20 loose drives. Wrong site allocations, overlapping equipment outcomes and off-site data work block review.',9);
  await p.locator('.finding a.ref').filter({hasText:'S1:L4'}).first().click();await chapter('02 / Follow the evidence','Each finding links to original enquiry lines or CSV cells. Identifiers such as 0001 remain text. No drive count is inferred from laptops.',7);
  await p.getByText('Fictional customer clarification for this demonstration',{exact:true}).click();await p.getByRole('button',{name:'Use fictional clarification text'}).click();await p.getByRole('button',{name:'Record source statement'}).click();
  await p.locator('#ref-S3\\:L1').scrollIntoViewIfNeeded();await chapter('03 / Record the customer clarification','The response becomes a new immutable source: 80 laptops Dubai, 40 Sharjah; reuse equipment and destroy the media on-site before collection.',7);
  await p.getByRole('button',{name:'Load worked correction'}).click();await p.getByRole('button',{name:'Save scope & recalculate'}).click();await p.locator('#findings').scrollIntoViewIfNeeded();
  await chapter('04 / Reconcile equipment and media independently','Source-linked corrections conserve the included quantities and clear the blockers. Laptop reuse and embedded-drive destruction coexist.',8);
  await p.getByRole('button',{name:'Review & create revision'}).click();
  await chapter('05 / Freeze an immutable reviewed revision','The printable brief separates equipment, embedded media and loose drives. It retains requirements, source references and outstanding access-window actions.',8);
  const [download]=await Promise.all([p.waitForEvent('download'),p.getByRole('link',{name:'Download reviewed JSON'}).click()]);await download.saveAs('artifacts/demo-reviewed-handoff.json');
  await p.goto(loop);await p.getByRole('button',{name:'Try demo'}).click();await p.goto(loop+'/scope-import');await p.getByLabel('Reviewed ScopeDesk JSON').setInputFiles(path.resolve('artifacts/demo-reviewed-handoff.json'));await p.getByRole('button',{name:'Preview scope import'}).click();
  await p.getByLabel('Organisation',{exact:true}).selectOption({label:'Cedar Circuit'});await p.getByLabel('Contact',{exact:true}).selectOption({label:'Alex Example 01 · Cedar Circuit'});await p.locator('main').scrollIntoViewIfNeeded();
  const preview=p.url();await chapter('06 / Preview the LoopDesk handoff','The bounded JSON omits original documents and serial registers. The salesperson chooses existing CRM records and an owner before confirmation.',8);
  await p.getByRole('button',{name:'Confirm reviewed scope import'}).click();const opportunity=p.url();
  await chapter('07 / One case, one linked opportunity','LoopDesk creates an IT asset disposition opportunity at New, with an unknown estimate and a next action from the scope. Repeating the import creates no duplicate.',7);
  await p.goto(preview);await p.getByRole('button',{name:'Confirm reviewed scope import'}).click();assert.equal(p.url(),opportunity);await p.getByRole('link',{name:'Reviewed ScopeDesk history'}).click();
  await chapter('Reviewed history / ready for the next conversation','Later revisions attach to the same opportunity and preserve CRM fields. Local SQLite flow verified; PostgreSQL and HTTPS remain unverified.',6);
}finally{
  const video=p.video();await context.close();await video.saveAs(path.resolve('artifacts/ScopeDesk-Demo.webm'));
  const result={recordedAt:new Date().toISOString(),captureWallSeconds:Number(((Date.now()-start)/1000).toFixed(2)),captions:'Presentation captions added over the real local application. Business responses and downloads are real; all data is synthetic.',chapters};
  await fs.writeFile('artifacts/demo-chapters.json',JSON.stringify(result,null,2));await browser.close();console.log(JSON.stringify(result,null,2));
}
