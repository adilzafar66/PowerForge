/* PowerForge UX-9.1: progressive enhancement for HTML design prototypes.
 * Native <select> remains the state/form source of truth; combobox is a themed, accessible facade.
 * Production should use a proven accessible Select primitive (e.g. Radix Select) with backend behavior unchanged.
 */
(function(){
 'use strict';
 let seed=0, openControl=null;
 const chevron='<svg aria-hidden="true" class="pf-select-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>';
 const safeText=(v)=>String(v||'').trim();
 function enhanced(select){
   if(select.dataset.pfEnhanced==='true'||select.closest('.pf-select-host'))return;
   if(select.multiple||select.size>1)return; // keep specialized controls native
   const host=document.createElement('span');host.className='pf-select-host';
   if(select.style.width){host.style.width=select.style.width;}
   else if(select.style.minWidth)host.style.minWidth=select.style.minWidth;
   if(select.classList.contains('invalid'))host.classList.add('invalid');
   select.insertAdjacentElement('beforebegin',host);host.appendChild(select);
   select.classList.add('pf-select-native');select.dataset.pfEnhanced='true';select.tabIndex=-1;select.setAttribute('aria-hidden','true');
   const trigger=document.createElement('button');trigger.type='button';trigger.className='pf-select-trigger';trigger.setAttribute('role','combobox');trigger.setAttribute('aria-haspopup','listbox');trigger.setAttribute('aria-expanded','false');
   const label=document.createElement('span');label.className='pf-select-value';trigger.append(label);trigger.insertAdjacentHTML('beforeend',chevron);host.appendChild(trigger);
   const id='pf-listbox-'+(++seed);trigger.setAttribute('aria-controls',id);
   const described=select.getAttribute('aria-describedby');if(described)trigger.setAttribute('aria-describedby',described);
   let sourceName=select.getAttribute('aria-label')||'';
   const ownLabels=select.id?Array.from(document.querySelectorAll('label[for]')).filter(l=>l.htmlFor===select.id):[];
   if(!sourceName)sourceName=safeText(ownLabels.map(l=>l.textContent).join(' '));
   if(!sourceName){const outer=select.closest('label');if(outer)sourceName=safeText(outer.textContent);}
   if(!sourceName)sourceName='Choose an option';
   const list=document.createElement('div');list.className='pf-select-menu';list.id=id;list.setAttribute('role','listbox');list.setAttribute('aria-label',sourceName);list.hidden=true;list.style.display='none';document.body.appendChild(list);
   const obj={select,host,trigger,list,label,name:sourceName,active:0,items:[],typeBuffer:'',bufferTime:0};
   function sync(){
     const selected=select.options[select.selectedIndex];label.textContent=selected?selected.text:'Choose…';trigger.setAttribute('aria-label',sourceName+': '+(selected?selected.text:'Choose an option'));
     trigger.disabled=select.disabled;host.classList.toggle('invalid',select.classList.contains('invalid'));
     if(openControl===obj){obj.items.forEach((item,i)=>{item.setAttribute('aria-selected',String(i===select.selectedIndex));});}
   }
   function moveCursor(i,direction=1,shouldScroll=true){const opts=Array.from(select.options);if(!opts.length)return;for(let k=0;k<opts.length;k++){const idx=(i+k*direction+opts.length*2)%opts.length;if(!opts[idx].disabled){obj.active=idx;break;}}
     obj.items.forEach((el,j)=>el.dataset.active=String(j===obj.active));const opt=obj.items[obj.active];if(opt){trigger.setAttribute('aria-activedescendant',opt.id);if(shouldScroll)opt.scrollIntoView({block:'nearest'});}}
   function position(){const r=trigger.getBoundingClientRect();const width=Math.max(r.width,Math.min(280,innerWidth-24));list.style.width=width+'px';list.style.left=Math.max(8,Math.min(r.left,innerWidth-width-8))+'px';list.style.visibility='hidden';list.hidden=false;list.style.display='block';const h=list.getBoundingClientRect().height;const down=innerHeight-r.bottom-10;const placeAbove=down<Math.min(h,230)&&r.top>h+12;list.style.top=(placeAbove?Math.max(8,r.top-h-5):Math.min(innerHeight-h-8,r.bottom+5))+'px';list.style.visibility='visible';}
   function close(focus=false){if(openControl!==obj)return;openControl=null;list.hidden=true;list.style.display='none';trigger.setAttribute('aria-expanded','false');trigger.removeAttribute('aria-activedescendant');if(focus)trigger.focus();}
   function commit(index){const opt=select.options[index];if(!opt||opt.disabled)return;const changed=select.selectedIndex!==index;select.selectedIndex=index;sync();close(true);if(changed){select.dispatchEvent(new Event('input',{bubbles:true}));select.dispatchEvent(new Event('change',{bubbles:true}));}}
   function show(){if(trigger.disabled)return;if(openControl)openControl.close();list.replaceChildren();obj.items=[];for(let i=0;i<select.options.length;i++){const opt=select.options[i];const el=document.createElement('div');el.className='pf-select-option';el.id=id+'-option-'+i;el.setAttribute('role','option');el.dataset.index=i;el.setAttribute('aria-selected',String(select.selectedIndex===i));if(opt.disabled)el.setAttribute('aria-disabled','true');el.textContent=opt.text;el.addEventListener('pointerdown',e=>e.preventDefault());if(!opt.disabled)el.addEventListener('pointerenter',()=>moveCursor(i,1,false));el.addEventListener('click',()=>commit(i));list.appendChild(el);obj.items.push(el);}
     obj.active=Math.max(0,select.selectedIndex);openControl=obj;obj.close=close;trigger.setAttribute('aria-expanded','true');position();moveCursor(obj.active);trigger.focus();}
   trigger.addEventListener('click',()=>{if(openControl===obj)close();else show()});
   trigger.addEventListener('keydown',e=>{
     if(e.key==='Tab'){close();return;}
     if(e.key==='Escape'){if(openControl===obj){e.preventDefault();e.stopPropagation();close(true);}return;}
     if(['ArrowDown','ArrowUp','Home','End'].includes(e.key)){
       e.preventDefault();if(openControl!==obj)show();
       if(e.key==='Home')moveCursor(0);else if(e.key==='End')moveCursor(select.options.length-1);else moveCursor((obj.active+(e.key==='ArrowDown'?1:-1)+select.options.length)%select.options.length,e.key==='ArrowDown'?1:-1);return;
     }
     if(e.key==='Enter'||e.key===' '){e.preventDefault();if(openControl===obj)commit(obj.active);else show();return;}
     if(openControl===obj&&e.key.length===1&&!e.ctrlKey&&!e.altKey&&!e.metaKey){
       const now=Date.now();obj.typeBuffer=now-obj.bufferTime>600?e.key.toLowerCase():obj.typeBuffer+e.key.toLowerCase();obj.bufferTime=now;
       let idx=Array.from(select.options).findIndex(x=>!x.disabled&&x.text.trim().toLowerCase().startsWith(obj.typeBuffer));if(idx>=0)moveCursor(idx);
     }
   });
   select.addEventListener('change',sync);select.addEventListener('input',sync);trigger.addEventListener('focus',sync);
   ownLabels.forEach(l=>l.addEventListener('click',e=>{e.preventDefault();trigger.focus();}));
   obj.close=close;
   sync();
 }
 function scan(root){if(root.nodeType!==1&&root.nodeType!==9)return;if(root.matches?.('select'))enhanced(root);root.querySelectorAll?.('select').forEach(enhanced);}
 document.addEventListener('pointerdown',e=>{if(openControl&&!openControl.host.contains(e.target)&&!openControl.list.contains(e.target))openControl.close();});
 window.addEventListener('resize',()=>{if(openControl)openControl.close();});
 window.addEventListener('scroll',e=>{if(openControl&&!openControl.list.contains(e.target))openControl.close();},true);
 const init=()=>{scan(document);let batch=false;const observer=new MutationObserver(records=>{if(batch)return;batch=true;queueMicrotask(()=>{batch=false;for(const record of records){for(const n of record.addedNodes)scan(n);}});});observer.observe(document.body,{childList:true,subtree:true});
   const mixed=document.getElementById('pf-demo-mixed');if(mixed){mixed.indeterminate=true;mixed.addEventListener('change',()=>{mixed.indeterminate=false;});}
   const choice=document.getElementById('pf-controls-choice');if(choice)choice.addEventListener('change',()=>{const t=document.getElementById('pf-controls-current');if(t)t.textContent='Selected: '+choice.options[choice.selectedIndex].text;});
 };
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
