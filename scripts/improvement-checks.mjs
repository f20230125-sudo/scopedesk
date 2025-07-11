import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
const require=createRequire(process.env.SCOPEDESK_BROWSER_PACKAGE||'D:/codex/rx-market-pulse/dashboard/package.json');
const {default:AxeBuilder}=require('@axe-core/playwright');

export async function verifyImprovements(browser,scope,root){
  const checks=[],scans=[];
  const context=await browser.newContext({viewport:{width:1440,height:900}});
  const p=await context.newPage();
  const errors=[],serverErrors=[];p.on('pageerror',e=>errors.push(e.message));p.on('response',r=>{if(r.status()>=500)serverErrors.push({url:r.url(),status:r.status()});});
  const check=(name,value=true)=>{assert.ok(value,name);checks.push(name);};
  async function captures(name){
    for(const [width,height] of [[1440,900],[390,844]]){
      await p.setViewportSize({width,height});
      check(`${name} fits ${width}px`,await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
      await p.screenshot({path:path.join(root,`improved-${name}-${width}.png`),fullPage:true});
      const result=await new AxeBuilder({page:p}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();
      await fs.writeFile(path.join(root,`improved-${name}-${width}-axe.json`),JSON.stringify(result.violations,null,2));
      assert.deepEqual(result.violations,[],`${name} ${width} accessibility`);scans.push(`${name}-${width}`);
    }
  }
  async function saveState(state,reason){
    await p.locator('#raw-editor').evaluate(e=>e.open=true);
    await p.getByLabel('Scope state',{exact:true}).fill(JSON.stringify(state));
    await p.getByLabel('Correction or review decision',{exact:true}).fill(reason);
    await p.getByRole('button',{name:'Save scope & recalculate'}).click();
  }
  try{
    await p.goto(scope);await captures('landing');
    check('Landing metadata is specific',await p.title()==='Enquiry and inventory scope review · ScopeDesk');
    await p.getByRole('button',{name:'Open demo workspace'}).click();await captures('cases');
    check('Three optional example cards',await p.locator('.example-card').count()===3);
    await p.locator('.case-card').filter({hasText:'Two-site laptop refresh'}).click();const original=p.url();
    await captures('case');
    for(const width of [1440,1024,390]){
      await p.setViewportSize({width,height:width===390?844:900});
      const region=p.getByRole('region',{name:'S2 original CSV records'});
      check(`Original CSV has horizontal scrolling at ${width}`,await region.evaluate(e=>e.scrollWidth>e.clientWidth));
      check(`Record header stays on one line at ${width}`,await region.locator('thead th').first().evaluate(e=>getComputedStyle(e).whiteSpace==='nowrap'&&e.getBoundingClientRect().width>=80));
      await region.focus();await p.keyboard.press('End');await region.evaluate(e=>e.scrollLeft=e.scrollWidth);
      check(`Unit column reachable at ${width}`,await region.locator('thead th').last().evaluate(e=>{const box=e.getBoundingClientRect(),parent=e.closest('.table-wrap').getBoundingClientRect();return box.right<=parent.right+1&&box.left>=parent.left;}));
      check(`First column stays visible at ${width}`,await region.locator('tbody th').first().evaluate(e=>{const x=e.getBoundingClientRect().left,parent=e.closest('.table-wrap').getBoundingClientRect().left;return Math.abs(x-parent)<3;}));
      await p.screenshot({path:path.join(root,`improved-source-scrolled-${width}.png`),fullPage:true});
    }
    check('Findings grouped with count',await p.locator('#finding-count_mismatch').innerText().then(t=>t.includes('Counts do not agree')&&t.includes('(3)')));
    const finding=p.locator('.finding').first();
    check('Exact references initially collapsed',!(await finding.locator('details').getAttribute('open')));
    const exact=await finding.locator('.exact-references a.ref').evaluateAll(links=>links.map(a=>a.hash.slice(1)));
    await finding.locator('summary').click();
    check('All exact finding references retained and resolvable',await finding.locator('.exact-references a.ref').evaluateAll(links=>links.every(a=>Boolean(document.getElementById(decodeURIComponent(a.hash.slice(1)))))));
    check('Clarification draft retains exact reference labels',await p.locator('#clarification-draft').inputValue().then(t=>exact.every(ref=>t.includes(decodeURIComponent(ref).replace(/^ref-/,'')))));
    await finding.locator('.exact-references a.ref').last().click();
    check('Expanded reference navigates to exact source cell',await p.evaluate(()=>!!document.getElementById(decodeURIComponent(location.hash.slice(1)))));
    await p.goto(original+'/brief');await captures('brief');
    await p.setViewportSize({width:1440,height:900});await p.emulateMedia({media:'print'});
    check('Printed brief fits the page',await p.locator('.brief table').evaluate(e=>e.getBoundingClientRect().right<=document.documentElement.clientWidth));
    await p.screenshot({path:path.join(root,'improved-brief-print.png'),fullPage:true});await p.pdf({path:path.join(root,'improved-brief-print.pdf'),format:'A4',margin:{top:'12mm',bottom:'12mm',left:'12mm',right:'12mm'}});await p.emulateMedia({media:'screen'});
    await p.goto(scope+'/cases');await p.locator('.example-card').filter({hasText:'Approximate monitor count'}).getByRole('button').click();const approximate=p.url();
    check('Approximate example has only its intended blocker',await p.locator('.finding').count()===1&&await p.locator('.finding code').innerText()==='approximate_difference');
    check('Summary offers resolution first',await p.getByRole('region',{name:'Case summary'}).getByRole('link',{name:'Resolve 1 blocking finding'}).count()===1);
    let state=JSON.parse(await p.locator('#scope-state').inputValue());state.requirements[0].acknowledged=true;state.requirements[0].basis='Use the 192 listed monitors pending final count.';
    await saveState(state,'Record the approximate count acknowledgement and inventory basis.');
    check('Summary counts acknowledged count basis',await p.locator('.case-summary').innerText().then(t=>t.includes('Acknowledged assumptions\n1')));
    await p.getByRole('button',{name:'Review & create revision',exact:true}).click();
    check('Approximate basis appears in reviewed brief',await p.locator('.brief').innerText().then(t=>t.includes('Reviewed with assumptions')&&t.includes('192 listed monitors')));
    await p.goto(approximate);check('Summary links latest reviewed revision',await p.locator('.case-summary a').innerText()==='Open reviewed revision 1');
    await p.goto(scope+'/cases');await p.locator('.example-card').filter({hasText:'Repeated identifiers'}).getByRole('button').click();
    check('Register example retains leading zeros',await p.locator('#sources').innerText().then(t=>t.includes('000042')&&t.includes('000007')));
    check('Duplicate findings grouped with count two',await p.locator('#finding-duplicate_identifier').innerText().then(t=>t.includes('(2)')));
    await p.goto(scope+'/cases');await p.locator('.example-card').filter({hasText:'Monitor list supplied in boxes'}).getByRole('button').click();
    check('Unsupported unit blocks review',await p.locator('.finding code').innerText()==='unsupported_unit'&&await p.getByRole('button',{name:'Review & create revision',exact:true}).isDisabled());
    await p.goto(scope+'/cases');check('Loaded examples use five total case slots',await p.locator('.case-card').count()===5&&await p.locator('.example-card button').count()===0);
    await p.goto(scope+'/cases/new');await captures('new');
    await p.getByLabel('Client display name').fill('Fictional Example');await p.getByLabel('Case title').fill('Mapping example');await p.getByLabel('Original enquiry').fill('Please scope two monitors at Dubai.');await p.getByRole('button',{name:'Create case'}).click();
    await p.getByText('Import another inventory',{exact:true}).click();await p.getByLabel('UTF-8 CSV',{exact:true}).setInputFiles({name:'example.csv',mimeType:'text/csv',buffer:Buffer.from('item,quantity,category\nMonitor,2,equipment\n')});await p.getByLabel('Import mode').selectOption('quantity');await p.getByLabel('Delimiter',{exact:true}).selectOption(',');await p.getByRole('button',{name:'Map inventory columns'}).click();await captures('mapping');
    const missing=await p.goto(scope+'/missing-page');check('Missing page returns 404 with cases recovery',missing.status()===404&&await p.getByRole('link',{name:'Return to cases'}).count()===1);await captures('error');
    const nojs=await browser.newContext({javaScriptEnabled:false,viewport:{width:390,height:844}});
    try{
      const n=await nojs.newPage();await n.goto(scope);await n.getByRole('button',{name:'Open demo workspace'}).click();
      await n.locator('.example-card').filter({hasText:'Approximate monitor count'}).getByRole('button').click();
      check('Example loading and summary work without JavaScript',await n.locator('.finding').count()===1&&await n.locator('.case-summary a').getAttribute('href')==='#findings');
      await n.locator('.finding summary').click();await n.locator('.finding .exact-references a').last().click();
      check('Native reference disclosure and exact links work without JavaScript',await n.evaluate(()=>!!document.getElementById(decodeURIComponent(location.hash.slice(1)))));
      await n.locator('#raw-editor summary').click();state=JSON.parse(await n.locator('#scope-state').inputValue());state.requirements[0].acknowledged=true;state.requirements[0].basis='Use the 192 listed monitors pending final count.';
      await n.locator('#scope-state').fill(JSON.stringify(state));await n.getByLabel('Correction or review decision',{exact:true}).fill('Acknowledge the listed count without JavaScript.');await n.getByRole('button',{name:'Save scope & recalculate'}).click();
      await n.getByRole('button',{name:'Review & create revision',exact:true}).click();check('Example can be reviewed through JSON fallback without JavaScript',await n.locator('.brief').innerText().then(t=>t.includes('Reviewed with assumptions')));
      await n.screenshot({path:path.join(root,'improved-nojs-reviewed-390.png'),fullPage:true});
    }finally{await nojs.close();}
    assert.deepEqual(errors,[],'Improvement browser errors');assert.deepEqual(serverErrors,[],'Improvement server errors');return {checks,scans};
  }finally{await context.close();}
}
