/* Progressive enhancement: state is submitted to the same validated service as JSON fallback. */
const $ = s => document.querySelector(s);
$('#print-brief')?.addEventListener('click',()=>window.print());
$('#fill-statement')?.addEventListener('click',()=>{$('#statement-text').value=$('#worked-text').textContent;$('#statement-text').focus();});
$('#download-draft')?.addEventListener('click',()=>{
  const url=URL.createObjectURL(new Blob([$('#clarification-draft').value],{type:'text/plain;charset=utf-8'}));
  const a=document.createElement('a');a.href=url;a.download='scopedesk-clarification-DRAFT.txt';a.click();URL.revokeObjectURL(url);
});
const host=$('#structured-editor');
if(host){
  let state=JSON.parse($('#scope-state').value);
  const inventory=JSON.parse(host.dataset.rows), references=JSON.parse(host.dataset.references);
  const rowOptions=inventory.map(r=>r.id);
  const layouts={
    allocations:{title:'Equipment allocations',help:'Split quantity-list rows across sites or outcomes. The total must equal each included parent count.',fields:{row_id:rowOptions,quantity:'number',site:'text',outcome:['reuse','recycle','destroy','undecided'],refs:'refs'},blank:()=>({row_id:rowOptions[0]||'',quantity:null,site:'',outcome:'undecided',refs:[]})},
    requirements:{title:'Confirmed customer requirements',help:'Record overall and site counts separately. “embedded” counts media within equipment; “onsite” records a restriction.',fields:{kind:['equipment','media','embedded','onsite'],item:'text',quantity:'number',site:'text',precision:['exact','approximate'],acknowledged:'boolean',basis:'text',refs:'refs'},blank:()=>({kind:'equipment',item:'',quantity:null,site:'',precision:'exact',acknowledged:false,basis:'',refs:[]})},
    media_actions:{title:'Media actions',help:'For embedded media, select its equipment row and enter the media count independently. Location describes the data work; collection “after” means after this work.',fields:{row_id:rowOptions,quantity:'number',site:'text',action:['wipe','destroy','retain','undecided'],location:['onsite','offsite','unknown'],collection:['after','before','none'],refs:'refs'},blank:()=>({row_id:rowOptions[0]||'',quantity:null,site:'',action:'undecided',location:'unknown',collection:'none',refs:[]})},
    assumptions:{title:'Visible assumptions',help:'Acceptable uncertainty remains in the brief. Logical contradictions must be corrected.',fields:{text:'text',refs:'refs'},blank:()=>({text:'',refs:[]})},
    followups:{title:'Outstanding actions',help:'These become part of the reviewed brief and LoopDesk next action.',fields:{text:'text',refs:'refs'},blank:()=>({text:'',refs:[]})}
  };
  function el(tag,text,cls){const e=document.createElement(tag);if(text)e.textContent=text;if(cls)e.className=cls;return e;}
  function sync(){ $('#scope-state').value=JSON.stringify(state,null,2); }
  function field(parent,label,value,type,onchange){
    const wrap=el('label',label),input=el(Array.isArray(type)?'select':'input');
    if(Array.isArray(type)) for(const option of type){const o=el('option',option);o.value=option;input.append(o);}
    else input.type=type==='number'?'number':type==='boolean'?'checkbox':'text';
    if(type==='boolean')input.checked=Boolean(value);else input.value=type==='refs'?(value||[]).join('; '):value??'';
    if(type==='number'){input.min='0';input.max='9999999';input.step='1';input.placeholder='Unknown';}
    if(type==='refs'){wrap.className='wide';input.placeholder='S1:L1; S2:R1:quantity';input.setAttribute('list','reference-options');}
    input.addEventListener('change',()=>{onchange(type==='number'?(input.value===''?null:Number(input.value)):type==='boolean'?input.checked:type==='refs'?input.value.split(';').map(x=>x.trim()).filter(Boolean):input.value);sync();});
    wrap.append(input);parent.append(wrap);return input;
  }
  function render(){
    host.replaceChildren();
    const data=el('datalist');data.id='reference-options';for(const r of references){const o=el('option');o.value=r;data.append(o);}host.append(data);
    for(const [key,config] of Object.entries(layouts)){
      const section=el('details',null,'editor-section');section.open=key==='allocations';
      section.append(el('summary',`${config.title} (${state[key].length})`),el('p',config.help,'small muted'));
      state[key].forEach((row,i)=>{
        const holder=el('details',null,'editor-item');holder.open=!row.refs.length;
        holder.append(el('summary',`${i+1}. ${row.row_id||row.kind||row.text||'New detail'} · ${row.quantity??''} ${row.site||''} ${row.outcome||row.action||''}`));
        const block=el('div',null,'editor-row');
        for(const [name,type] of Object.entries(config.fields))field(block,name==='refs'?'Source references (separate with ;)':name.replaceAll('_',' '),row[name],type,value=>row[name]=value);
        const remove=el('button','Remove row','secondary danger');remove.type='button';remove.addEventListener('click',()=>{state[key].splice(i,1);sync();render();});block.append(remove);holder.append(block);section.append(holder);
      });
      const add=el('button',`+ Add ${key==='allocations'?'equipment allocation':key==='requirements'?'requirement':key==='media_actions'?'media action':key==='assumptions'?'assumption':'follow-up'}`,'secondary');add.type='button';add.addEventListener('click',()=>{state[key].push(config.blank());sync();render();});section.append(add);host.append(section);
    }
    const corrections=el('details',null,'editor-section');corrections.append(el('summary',`Source-row corrections / exclusions (${Object.keys(state.overrides).length})`),el('p','Use an immutable customer clarification, reviewer statement or assumption as the source. An exclusion requires a reason; remove its allocations explicitly.','small muted'));
    for(const [rid,row] of Object.entries(state.overrides)){
      const block=el('div',null,'editor-row');block.append(el('span',rid,'row-title'));
      for(const [name,type] of Object.entries({quantity:'number',category:['equipment','media','unknown'],site:'text',item:'text',unit:'text',excluded:'boolean',reason:'text',refs:'refs'})){
        if(name in row)field(block,name,row[name],type,value=>row[name]=value);
      }
      const remove=el('button','Remove correction','secondary');remove.type='button';remove.addEventListener('click',()=>{delete state.overrides[rid];sync();render();});block.append(remove);corrections.append(block);
    }
    const picker=el('div',null,'editor-row');let selected=rowOptions[0];field(picker,'Source row',selected,rowOptions,value=>selected=value);
    const addCorrection=el('button','+ Correct selected row','secondary');addCorrection.type='button';addCorrection.addEventListener('click',()=>{const r=inventory.find(x=>x.id===selected);if(!r)return;state.overrides[selected]={quantity:r.quantity,category:r.category,site:r.site,item:r.item,unit:r.unit,excluded:false,reason:'',refs:[]};sync();render();});picker.append(addCorrection);corrections.append(picker);host.append(corrections);
    const duplicates=el('details',null,'editor-section');duplicates.append(el('summary','Duplicate identifier decisions'),el('p','Keep suspected duplicates until a reviewer decides. Explain why repeated identifiers refer to separate items, or exclude the duplicate row with evidence.','small muted'));
    for(const [identifier,row] of Object.entries(state.duplicate_decisions)){
      const block=el('div',null,'editor-row');block.append(el('span',identifier,'row-title'));field(block,'Reason',row.text,'text',v=>row.text=v);field(block,'Source references',row.refs,'refs',v=>row.refs=v);duplicates.append(block);
    }
    const block=el('div',null,'editor-row');let identifier='';field(block,'Identifier to review','', 'text',v=>identifier=v);
    const add=el('button','+ Record duplicate decision','secondary');add.type='button';add.addEventListener('click',()=>{if(!identifier.trim())return;Object.defineProperty(state.duplicate_decisions,identifier.trim().toLowerCase(),{value:{text:'',refs:[]},enumerable:true,writable:true,configurable:true});sync();render();});block.append(add);duplicates.append(block);host.append(duplicates);
  }
  $('#scope-state').addEventListener('change',()=>{try{state=JSON.parse($('#scope-state').value);render();}catch{/* Server returns the validation error on submission. */}});
  $('#scope-form').addEventListener('submit',()=>{document.activeElement?.blur();});
  $('#worked-correction')?.addEventListener('click',()=>{
    const sid=$('#worked-correction').dataset.source;
    state.allocations=[{row_id:'S2-1',quantity:80,site:'Dubai',outcome:'reuse',refs:[`${sid}:L1`,`${sid}:L2`]},{row_id:'S2-2',quantity:40,site:'Sharjah',outcome:'reuse',refs:[`${sid}:L1`,`${sid}:L2`]}];
    for(const [rid,q]of [['S2-1',80],['S2-2',40]])state.overrides[rid]={quantity:q,reason:'Customer corrected the site quantities.',refs:[`${sid}:L1`]};
    state.media_actions[0].location='onsite';state.media_actions[0].refs=[`${sid}:L3`];
    $('#decision').value='Applied customer clarification: site counts corrected, equipment overlap removed, loose-drive work on-site.';sync();render();$('#scope-editor').scrollIntoView();
  });
  render();
}
