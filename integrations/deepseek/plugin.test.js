import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync, readFileSync, rmSync} from 'node:fs';
import {join,resolve,sep} from 'node:path';
import {tmpdir} from 'node:os';
import {apply} from './index.js';

test('session catalog reaches the pet without subagents or blank drafts', async () => {
  const dir=mkdtempSync(join(tmpdir(),'shorekeeper-catalog-'));
  const previous=process.env.DSH_HOME; process.env.DSH_HOME=dir;
  const cleanups=[];
  const items=[
    {sessionId:'s1',running:true,updatedAt:1700000000000,projections:{values:{title:'真实会话'}}},
    {sessionId:'sub1',running:false,updatedAt:1700000001000,parentSessionId:'s1',projections:{values:{title:'子代理'}}},
    {sessionId:'blank1',running:false,updatedAt:1700000002000,blank:true,projections:{values:{title:'空草稿'}}},
    {sessionId:'s2',running:false,updatedAt:1690000000000,projections:{values:{title:'稍旧会话'}}},
    {sessionId:'s3',title:'扁平标题',running:false,updatedAt:1680000000000},
  ];
  try {
    apply({sessions:{},sessionController:{async list(){return {items};}},
      deepseekAccount:{async getBalance(){return {status:'ready',value:[],bonusWallets:[]};}},
      on:()=>{},effect:run=>cleanups.push(run())});
    await new Promise(resolve=>setTimeout(resolve,60));
    const state=JSON.parse(readFileSync(join(dir,'shorekeeper-pet/desktop.json'),'utf8'));
    assert.deepEqual(state.sessions.map(row=>row.thread_id),['s1','s2','s3']);
    assert.equal(state.sessions[0].title,'真实会话');
    assert.equal(state.sessions[2].title,'扁平标题');
    assert.equal(state.sessions[0].state,'working');
    assert.equal(state.sessions[0].active,true);
    assert.equal(state.sessions[1].state,'idle');
  } finally {
    for(const cleanup of cleanups)cleanup();
    if(previous===undefined)delete process.env.DSH_HOME;else process.env.DSH_HOME=previous;
    rmSync(dir,{recursive:true,force:true});
  }
});

test('archived conversations are filtered from the catalog and from live rows', async () => {
  const dir=mkdtempSync(join(tmpdir(),'shorekeeper-archive-'));
  const previous=process.env.DSH_HOME; process.env.DSH_HOME=dir;
  const listeners={},cleanups=[],archived=[];
  const items=[
    {sessionId:'keep',title:'保留的会话',running:false,updatedAt:1700000000000},
    {sessionId:'gone',title:'归档的会话',running:false,updatedAt:1700000100000},
  ];
  try {
    apply({sessions:{},sessionController:{async list(){return {items};}},
      workspaceRegistry:{archivedSessionIds:archived},
      deepseekAccount:{async getBalance(){return {status:'ready',value:[],bonusWallets:[]};}},
      on:(type,handler)=>{listeners[type]=handler;},effect:run=>cleanups.push(run())});
    const read=()=>JSON.parse(readFileSync(join(dir,'shorekeeper-pet/desktop.json'),'utf8'));
    await new Promise(resolve=>setTimeout(resolve,60));
    assert.deepEqual(read().sessions.map(row=>row.thread_id),['gone','keep']);
    // 归档后，目录里的那条要消失
    archived.push('gone');
    await new Promise(resolve=>setTimeout(resolve,3000));
    assert.deepEqual(read().sessions.map(row=>row.thread_id),['keep']);
    // 已经产生过实时事件的行，归档后同样要消失
    listeners['session/event']({id:'live',header:{}},{type:'turn/start',data:{turn:1}});
    await new Promise(resolve=>setTimeout(resolve,700));
    assert.deepEqual(read().sessions.map(row=>row.thread_id),['live','keep']);
    archived.push('live');
    await new Promise(resolve=>setTimeout(resolve,700));
    assert.deepEqual(read().sessions.map(row=>row.thread_id),['keep']);
    // 取不到 workspaceRegistry 时不应报错，也不应过滤掉任何会话
    assert.equal(read().connected,true);
  } finally {
    for(const cleanup of cleanups)cleanup();
    if(previous===undefined)delete process.env.DSH_HOME;else process.env.DSH_HOME=previous;
    rmSync(dir,{recursive:true,force:true});
  }
});

test('a late balance response cannot resurrect a signed-out account', async () => {
  const dir=mkdtempSync(join(tmpdir(),'shorekeeper-account-'));
  const previous=process.env.DSH_HOME; process.env.DSH_HOME=dir;
  const listeners={},cleanups=[]; let finish;
  try {
    apply({sessions:{},deepseekAccount:{getBalance:()=>new Promise(r=>{finish=r;})},
      on:(type,handler)=>{listeners[type]=handler;},effect:run=>cleanups.push(run())});
    listeners['deepseek-account/signed-out']();
    finish({status:'ready',value:[{currency:'CNY',balance:'9'}]});
    await new Promise(resolve=>setTimeout(resolve,10));
    const state=JSON.parse(readFileSync(join(dir,'shorekeeper-pet/desktop.json'),'utf8'));
    assert.equal(state.balance.status,'signed-out'); assert.deepEqual(state.balance.wallets,[]);
  } finally {
    for(const cleanup of cleanups)cleanup();
    if(previous===undefined)delete process.env.DSH_HOME;else process.env.DSH_HOME=previous;
    assert.ok(resolve(dir).startsWith(resolve(tmpdir())+sep));rmSync(dir,{recursive:true,force:true});
  }
});

test('plugin lifecycle safely projects balance and real event shapes, disposes heartbeat', async () => {
  const dir=mkdtempSync(join(tmpdir(),'shorekeeper-host-'));
  const previous=process.env.DSH_HOME; process.env.DSH_HOME=dir;
  const listeners={},cleanups=[];
  let balanceCalls=0;
  try {
    apply({sessions:{},deepseekAccount:{async getBalance() {
      balanceCalls++;return {status:'ready',value:[{currency:'CNY',balance:'0E-16',token:'SECRET'}],bonusWallets:[{currency:'CNY',balance:'1e+1'}]};
    }},on:(type,handler)=>{listeners[type]=handler;},effect:run=>cleanups.push(run())});
    await new Promise(resolve=>setTimeout(resolve,10));
    const read=()=>JSON.parse(readFileSync(join(dir,'shorekeeper-pet/desktop.json'),'utf8'));
    assert.equal(read().balance.wallets[0].balance,'0E-16');
    assert.ok(!JSON.stringify(read()).includes('SECRET'));
    listeners['session/event']({id:'one',header:{}},{type:'turn/start',data:{turn:1}});
    listeners['session/event']({id:'one',header:{}},{type:'turn/end',data:{turn:1,reason:{kind:'completed'}}});
    await new Promise(resolve=>setTimeout(resolve,510));
    assert.equal(read().events[0].state,'done');assert.equal(balanceCalls,1);
    listeners['deepseek-account/signed-out']();assert.equal(read().balance.status,'signed-out');
    cleanups.pop()();assert.equal(read().connected,false);
  } finally {
    for(const cleanup of cleanups)cleanup();
    if(previous===undefined)delete process.env.DSH_HOME;else process.env.DSH_HOME=previous;
    assert.ok(resolve(dir).startsWith(resolve(tmpdir())+sep));
    rmSync(dir,{recursive:true,force:true});
  }
});
