// Module-scoped DOM adapter loader. Dependencies execute their shipped code.
// This transpiles only static ES import/export syntax; it is not browser QA.
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const caches=new WeakMap();
function loadModule(file,context){
 file=path.resolve(file);let cache=caches.get(context);if(!cache){cache=new Map();caches.set(context,cache)}if(cache.has(file))return cache.get(file);
 const namespaces={},exports=[];let source=fs.readFileSync(file,'utf8');let number=0;
 source=source.replace(/^import\s+\{([^}]+)\}\s+from\s+['"]([^'"]+)['"];?\s*$/gm,(_,names,url)=>{
  const key='m'+number++;namespaces[key]=loadModule(path.resolve(path.dirname(file),url.split('?')[0]),context);
  return 'const {'+names+'}=imports.'+key+';';
 });
 source=source.replace(/export\s+(async\s+)?function\s+(\w+)/g,(_,async,name)=>{exports.push(name);return (async||'')+'function '+name});
 source=source.replace(/export\s+(const|let|class)\s+(\w+)/g,(_,type,name)=>{exports.push(name);return type+' '+name});
 context.__uiImports=namespaces;
 const namespace=vm.runInContext('(function(imports){'+source+'\nreturn {'+exports.join(',')+'};})(__uiImports)',context,{filename:file});
 cache.set(file,namespace);delete context.__uiImports;return namespace;
}
function storageAdapter(storage){
 const keys=new Set();return {getItem(key){return storage.getItem(key)??null},setItem(key,value){keys.add(key);storage.setItem(key,value)},removeItem(key){keys.delete(key);storage.removeItem?.(key)},key(i){return [...keys][i]??null},get length(){return keys.size}};
}
module.exports={loadModule,storageAdapter};
