// Post hoc regression for preserving arbitrary JavaScript rejection values.
import assert from 'node:assert/strict';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
const {importRows}=await import(pathToFileURL(resolve(process.argv[2] || new URL('./candidate.mjs',import.meta.url).pathname)));
let failed=0;
for(const reason of [undefined,null,false,0,'']){
 let rejected=false,actual;
 try {actual=await importRows([7],{concurrency:1,prepare:x=>x,commit:()=>{throw reason;}});}catch(e){rejected=true;actual=e;}
 try{assert.equal(rejected,true);assert.equal(actual,reason);console.log(JSON.stringify({reasonType:typeof reason,passed:true}));}
 catch{failed++;console.log(JSON.stringify({reasonType:typeof reason,passed:false,rejected}));}
}
console.log(JSON.stringify({summary:{total:5,passed:5-failed,failed}}));process.exitCode=failed?1:0;
