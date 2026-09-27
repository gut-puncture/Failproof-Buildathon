import {readdir,mkdtemp,rmdir,rename as fsRename} from 'node:fs/promises';
import {join} from 'node:path';
export async function renameBatch(root,moves,options={}) {
  const rename=options.rename??fsRename;
  const names=new Set(await readdir(root));
  const sources=new Set(),destinations=new Set();
  for(const {from,to} of moves){
    if(sources.has(from)||destinations.has(to))throw new Error('Duplicate name');
    sources.add(from);destinations.add(to);
  }
  for(const {from,to}of moves){
    if(!names.has(from))throw new Error('Missing source');
    if(names.has(to)&&!sources.has(to))throw new Error('Occupied destination');
  }
  const work=moves.filter(({from,to})=>from!==to).map(move=>({...move,location:'source'}));
  if(!work.length)return;
  const temporary=await mkdtemp(join(root,'.batch-'));
  work.forEach((item,index)=>{item.temp=join(temporary,String(index));});
  try{
    for(const item of work){await rename(join(root,item.from),item.temp);item.location='temp';}
    for(const item of work){await rename(item.temp,join(root,item.to));item.location='destination';}
  }catch(error){
    // Collect published files out of the original namespace before restoring sources.
    for(const item of work){if(item.location==='destination'){await rename(join(root,item.to),item.temp);item.location='temp';}}
    for(const item of work){if(item.location==='temp'){await rename(item.temp,join(root,item.from));item.location='source';}}
    await rmdir(temporary);
    throw error;
  }
  await rmdir(temporary);
}
