export function importRows(rows,{prepare,commit,concurrency}) {
  if(!Number.isInteger(concurrency)||concurrency<1)return Promise.reject(new RangeError('concurrency'));
  let resolve,reject;
  const result=new Promise((yes,no)=>{resolve=yes;reject=no;});
  const states=Array(rows.length);
  const values=Array(rows.length);
  const outputs=[];
  let nextPrepare=0,active=0,nextCommit=0,committing=false,stopped=false;
  let failureIndex=Infinity,failure;
  const fail=(index,error)=>{stopped=true;if(index<failureIndex){failureIndex=index;failure=error;}};
  function finish(){
    if(active||committing)return;
    if(failureIndex!==Infinity){if(nextCommit>=failureIndex)reject(failure);}
    else if(nextCommit===rows.length)resolve(outputs);
  }
  function commitNext(){
    if(committing||nextCommit>=failureIndex||states[nextCommit]!=='ready'){finish();return;}
    const index=nextCommit;
    committing=true;
    let operation;
    try{operation=commit(values[index],index);}catch(error){operation=Promise.reject(error);}
    Promise.resolve(operation).then(value=>{
      outputs.push(value);nextCommit++;committing=false;commitNext();finish();
    },error=>{committing=false;fail(index,error);finish();});
  }
  function pump(){
    while(!stopped&&active<concurrency&&nextPrepare<rows.length){
      const index=nextPrepare++;active++;states[index]='preparing';
      let operation;
      try{operation=prepare(rows[index],index);}catch(error){operation=Promise.reject(error);}
      Promise.resolve(operation).then(value=>{
        active--;states[index]='ready';values[index]=value;pump();commitNext();finish();
      },error=>{active--;states[index]='failed';fail(index,error);commitNext();finish();});
    }
    finish();
  }
  pump();return result;
}
