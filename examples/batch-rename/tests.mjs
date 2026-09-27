import assert from 'node:assert/strict';
import {mkdtemp,writeFile,readFile,readdir,rm,rename} from 'node:fs/promises';
import {tmpdir} from 'node:os';import {join,resolve} from 'node:path';import {pathToFileURL} from 'node:url';
const {renameBatch}=await import(process.argv[2]?pathToFileURL(resolve(process.argv[2])):new URL('./reference.mjs',import.meta.url));
const tests=[];const test=(name,fn)=>tests.push({name,fn});
const initial={'a.txt':Buffer.from([0,1,255,23]),'b.txt':Buffer.from('second'),'c.txt':Buffer.from('third'),'untouched.txt':Buffer.from('keep')};
async function snapshot(root){const result={};for(const name of(await readdir(root)).sort())result[name]=(await readFile(join(root,name))).toString('hex');return result;}
async function fixture(fn){const root=await mkdtemp(join(tmpdir(),'rename-fixture-'));try{for(const[name,bytes]of Object.entries(initial))await writeFile(join(root,name),bytes);await fn(root);}finally{await rm(root,{recursive:true,force:true});}}
const moves=[{from:'a.txt',to:'b.txt'},{from:'b.txt',to:'c.txt'},{from:'c.txt',to:'a.txt'}];
test('simultaneous three-way cycle preserves binary contents and unrelated file',()=>fixture(async root=>{
  const before=structuredClone(moves);const result=await renameBatch(root,moves);assert.equal(result,undefined);assert.deepEqual(moves,before);
  const expected={'a.txt':initial['c.txt'].toString('hex'),'b.txt':initial['a.txt'].toString('hex'),'c.txt':initial['b.txt'].toString('hex'),'untouched.txt':initial['untouched.txt'].toString('hex')};assert.deepEqual(await snapshot(root),expected);
}));
test('chain into previously unused filename works',()=>fixture(async root=>{
  await renameBatch(root,[{from:'a.txt',to:'b.txt'},{from:'b.txt',to:'new.txt'}]);
  const expected={'b.txt':initial['a.txt'].toString('hex'),'new.txt':initial['b.txt'].toString('hex'),'c.txt':initial['c.txt'].toString('hex'),'untouched.txt':initial['untouched.txt'].toString('hex')};assert.deepEqual(await snapshot(root),expected);
}));
test('empty and same-name plans preserve folder exactly',()=>fixture(async root=>{
  const before=await snapshot(root);await renameBatch(root,[]);await renameBatch(root,[{from:'a.txt',to:'a.txt'}]);assert.deepEqual(await snapshot(root),before);
}));
for(const [label,plan]of [
  ['duplicate sources',[{from:'a.txt',to:'x'},{from:'a.txt',to:'y'}]],
  ['duplicate destinations',[{from:'a.txt',to:'x'},{from:'b.txt',to:'x'}]],
  ['missing source',[{from:'a.txt',to:'x'},{from:'missing',to:'y'}]],
  ['occupied unrelated destination',[{from:'a.txt',to:'untouched.txt'}]],
])test(`preflight rejects ${label} before any rename`,()=>fixture(async root=>{
  const before=await snapshot(root);let calls=0;await assert.rejects(renameBatch(root,plan,{rename:async(a,b)=>{calls++;return rename(a,b);}}));assert.equal(calls,0);assert.deepEqual(await snapshot(root),before);
}));
// Fail when the Nth original file is published at its final destination. This is
// independent of staging names, directory layout or how many stage renames occur.
for(const publishNumber of [1,2,3])test(`publication failure ${publishNumber} restores all original names and bytes`,()=>fixture(async root=>{
  const before=await snapshot(root);const originalContents=new Map(Object.entries(initial).map(([name,bytes])=>[bytes.toString('hex'),name]));
  const requested=new Map(moves.map(m=>[m.from,m.to]));const originalError=new Error('simulated disk rename failure');let publications=0,failed=false;
  const failingRename=async(a,b)=>{
    const bytes=(await readFile(a)).toString('hex');const original=originalContents.get(bytes);
    if(!failed&&original&&resolve(b)===resolve(root,requested.get(original)??'__not_a_destination__')){
      publications++;if(publications===publishNumber){failed=true;throw originalError;}
    }
    return rename(a,b);
  };
  let caught;try{await renameBatch(root,moves,{rename:failingRename});}catch(error){caught=error;}
  assert.equal(failed,true,'The supplied rename override must perform publication');assert.equal(caught,originalError);assert.deepEqual(await snapshot(root),before);
}));
test('early staging failure restores the whole folder',()=>fixture(async root=>{
  const before=await snapshot(root);let calls=0;const error=new Error('stage failure');let caught;
  try{await renameBatch(root,moves,{rename:async(a,b)=>{if(++calls===2)throw error;return rename(a,b);}});}catch(e){caught=e;}
  assert.equal(caught,error);assert.deepEqual(await snapshot(root),before);
}));
let failed=0;for(const{name,fn}of tests){try{await fn();console.log(JSON.stringify({name,passed:true}));}catch(error){failed++;console.log(JSON.stringify({name,passed:false,error:error.stack}));}}
console.log(JSON.stringify({summary:{total:tests.length,passed:tests.length-failed,failed}}));process.exitCode=failed?1:0;
