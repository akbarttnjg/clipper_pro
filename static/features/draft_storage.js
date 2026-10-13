// A tab owns its draft namespace. Reload restores it; another tab cannot overwrite it.
const draftKey = key => /^(clipper4-drafts|clipper-stage3-drafts|clipper-analysis-drafts)$/.test(key) ||
 /^(clipper5-style\||clipper4-visual-draft\||clipper4-visual-fields\||clipper6-evaluation\||clipper-m1-fields\|)/.test(key);
let tabId;
if(typeof window!=='undefined'){
 if(!window.name.startsWith('clipper-m1:'))window.name='clipper-m1:'+crypto.randomUUID();
 tabId=window.name.slice('clipper-m1:'.length);
}else tabId='test-tab';
export const currentDraftTab=tabId;
const prefix='clipper-m1-tab:'+tabId+'|';
export function scopedDraftStorage(native){
 const keys=()=>{const result=[];for(let i=0;i<native.length;i++){const key=native.key(i);if(key?.startsWith(prefix))result.push(key.slice(prefix.length));else if(key&&!key.startsWith('clipper-m1-tab:')&&!draftKey(key))result.push(key)}return result};
 // Claim old unscoped drafts once, preserving their exact bytes and revision.
 for(let i=native.length-1;i>=0;i--){const key=native.key(i);if(!key||!draftKey(key))continue;
  const physical=prefix+key;const value=native.getItem(key);
  if(native.getItem(physical)===null){try{native.setItem(physical,value);if(native.getItem(physical)===value)native.removeItem(key)}catch{/* Original bytes remain exportable. */}}
 }
 return {get length(){return keys().length},key(i){return keys()[i]??null},
  getItem(key){return native.getItem(draftKey(key)?prefix+key:key)},
  setItem(key,value){native.setItem(draftKey(key)?prefix+key:key,value)},
  removeItem(key){native.removeItem(draftKey(key)?prefix+key:key)},
  physicalKey(key){return draftKey(key)?prefix+key:key}};
}
export const localDrafts=scopedDraftStorage(globalThis.localStorage);
export const sessionDrafts=scopedDraftStorage(globalThis.sessionStorage);
export function otherTabDrafts(projectId,native=globalThis.localStorage){
 const result=[];
 for(let i=0;i<native.length;i++){const key=native.key(i);if(!key?.startsWith('clipper-m1-tab:')||key.startsWith(prefix))continue;
  const raw=native.getItem(key);if(!key.includes('|'+projectId+'|')&&!raw?.includes(projectId))continue;
  result.push({key,raw,tab:key.split('|')[0],blocksProcess:false,panel:'Draf tab lain'});
 }
 return result;
}
