import {localDrafts,sessionDrafts} from './draft_storage.js?v=4.0.17-m6';
// Shared editor state. Local drafts belong to a project, never to a render job.
export function settingsDelta(values,baseline={}){
 const normalized=(key,value)=>key.endsWith('_hex')&&typeof value==='string'&&/^#[0-9a-f]{6}$/i.test(value)?value.toLowerCase():value;
 return Object.fromEntries(Object.entries(values).filter(([key,value])=>JSON.stringify(normalized(key,value))!==JSON.stringify(normalized(key,baseline[key]))));
}
export function selectedStyleTargets(project,variantId,both=false){
 return Object.entries(project.clips||{}).filter(([,clip])=>clip.included!==false)
  .flatMap(([clip_id,clip])=>(both?Object.keys(clip.variants):[variantId]).filter(variant_id=>clip.variants[variant_id]).map(variant_id=>({clip_id,variant_id})));
}
export function projectDrafts(projectId,local=localDrafts,session=sessionDrafts){
 if(!projectId)return [];
 const found=[];
 const pairs=(storage,key,label)=>{
  let raw;try{raw=storage.getItem(key);const value=JSON.parse(raw||'[]');if(!Array.isArray(value)||value.some(pair=>!Array.isArray(pair)||pair.length!==2))throw Error('Format draf tidak valid');
   for(const [id,data] of value){if(typeof id!=='string'||!id.startsWith(projectId+'|')||id.endsWith('|base')||id.endsWith('|__baseRevision'))continue;found.push({key,id,data,panel:label});}
  }catch{found.push({key,raw,panel:label,error:'Draf tidak dapat dibaca. Ekspor atau pulihkan sebelum render.'});}
 };
 pairs(local,'clipper4-drafts','Kolom editor');pairs(local,'clipper-stage3-drafts','Transkrip & timing');pairs(session,'clipper-analysis-drafts','Ilustrasi & analisis');
 for(const [prefix,label] of [['clipper5-style|','Gaya Tahap 5'],['clipper4-visual-draft|','Area aman'],['clipper4-visual-fields|','Kamera & pembicara'],['clipper-m1-fields|','Editor M1'],['clipper-m2-fields|','Transkrip M2'],['clipper-m3-fields|','Seleksi M3'],['clipper-m4-fields|','Kamera M4'],['clipper-m5-fields|','Finishing M5'],['clipper-m6-fields|','Audio M6'],['clipper6-evaluation|','Evaluasi']]){
  const blocksProcess=!['clipper6-evaluation|','clipper-m3-fields|'].includes(prefix);
  try{for(let i=0;i<(local?.length||0);i++){const key=local.key(i);if(!key?.startsWith(prefix+projectId+'|'))continue;let raw;try{raw=local.getItem(key);const data=JSON.parse(raw||'null');if(data&&Object.keys(['clipper-m2-fields|','clipper-m3-fields|','clipper-m4-fields|','clipper-m5-fields|','clipper-m6-fields|'].includes(prefix)?(data.fields||{}):(data.values||data)).some(key=>prefix!=='clipper-m2-fields|'||!['correction_scope','subtitle_format'].includes(key)))found.push({key,data,panel:label,blocksProcess});}catch{found.push({key,raw,panel:label,blocksProcess,error:'Draf tidak dapat dibaca. Salin isi penyimpanan sebelum membuangnya.'});}}}
  catch{found.push({key:prefix+projectId,panel:label,blocksProcess,error:'Penyimpanan draf tidak dapat dibaca.'});}
 }
 return found;
}
export function draftMessage(drafts){
 const labels=[...new Set(drafts.map(d=>d.panel))];
 return labels.length?'Simpan atau buang draf sebelum menjalankan proses: '+labels.join(', ')+'.':'';
}
