// Added after inspecting the recorded run. Exercises rollback using disposable files only.
import assert from 'node:assert/strict';
import {mkdtemp,writeFile,readFile,readdir,rm,rename} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
const {renameBatch}=await import(pathToFileURL(resolve(process.argv[2] || new URL('./candidate.mjs',import.meta.url).pathname)));
const root=await mkdtemp(join(tmpdir(),'jev-swap-rollback-'));
const initial={'a.txt':'A','b.txt':'B','c.txt':'C'};
const moves=[{from:'a.txt',to:'b.txt'},{from:'b.txt',to:'a.txt'},{from:'c.txt',to:'d.txt'}];
const originalError=new Error('simulated one-time rename failure');
let calls=0, injected=false, caught;
async function snapshot(){const out={};for(const name of(await readdir(root)).sort())out[name]=await readFile(join(root,name),'utf8');return out;}
try {
  for(const [name,value]of Object.entries(initial))await writeFile(join(root,name),value);
  try {await renameBatch(root,moves,{rename:async(from,to)=>{
    calls++;
    // Fail publication of the third original, independent of temporary filenames.
    if(!injected && resolve(to)===resolve(root,'d.txt') && await readFile(from,'utf8')==='C'){
      injected=true;throw originalError;
    }
    return rename(from,to);
  }});} catch(e){caught=e;}
  const after=await snapshot();
  const record={case:'completed-swap-then-failure',before:initial,after,injected,sameError:caught===originalError,calls};
  console.log(JSON.stringify(record));
  assert.equal(injected,true);assert.equal(caught,originalError);assert.deepEqual(after,initial);
  console.log(JSON.stringify({summary:{total:1,passed:1,failed:0}}));
}catch(e){console.log(JSON.stringify({summary:{total:1,passed:0,failed:1},reason:e.message}));process.exitCode=1;}
finally {await rm(root,{recursive:true,force:true});}
