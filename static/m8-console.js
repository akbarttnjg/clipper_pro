import {mountM8} from './features/distribution8.js?v=4.0.19-m8';
const host=document.querySelector('#m8-root'),status=document.querySelector('#m8-status'),select=document.querySelector('#m8-project');
let mounted=null,generation=0;
const headers=()=>{const token=sessionStorage.getItem('clipper-m8-session');return token?{Authorization:'Bearer '+token}:{};};
async function api(path,body){const options={headers:headers()};if(body!==undefined){options.method='POST';options.headers['Content-Type']='application/json';options.body=JSON.stringify(body)}const response=await fetch('/api/studio'+path,options);const value=await response.json();if(!response.ok)throw Error(value.message||value.detail||'Permintaan gagal');return value;}
async function download(url){const response=await fetch(url,{headers:headers()});if(!response.ok)throw Error('Berkas tidak dapat diunduh oleh sesi ini.');const blob=await response.blob(),object=URL.createObjectURL(blob),a=document.createElement('a');a.href=object;a.download=response.headers.get('content-disposition')?.match(/filename="([^"]+)"/)?.[1]||'clipper-download';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(object),1000);}
async function show(){const active=++generation;mounted?.destroy();mounted=null;host.replaceChildren();try{const result=await api('/m8/v1/command',{schema_version:1,action:'project.list',args:{}});if(active!==generation)return;
 const chosen=select.value;select.replaceChildren();const all=document.createElement('option');all.value='';all.textContent='Semua proyek';select.append(all);for(const item of result.projects){const option=document.createElement('option');option.value=item.project_id;option.textContent=item.name;select.append(option)}select.value=chosen;
 const project=select.value?await api('/m8/v1/command',{schema_version:1,action:'project.get',args:{project_id:select.value}}):null;if(active!==generation)return;
 mounted=mountM8(host,{project,api,download,onChange:show,isActive:()=>active===generation});status.textContent='';
 }catch(error){if(active===generation)status.textContent=error.message;}}
document.querySelector('#login').onsubmit=event=>{event.preventDefault();const token=document.querySelector('#token');sessionStorage.setItem('clipper-m8-session',token.value.trim());token.value='';show()};
document.querySelector('#logout').onclick=()=>{sessionStorage.removeItem('clipper-m8-session');show()};select.onchange=show;show();
