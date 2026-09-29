const base=process.env.DECIP_E2E_URL||'http://127.0.0.1:8767',cdp=process.env.DECIP_CDP_URL||'http://127.0.0.1:9232';
const targets=await(await fetch(`${cdp}/json/list`)).json(),target=targets.find(t=>t.type==='page');
if(!target)throw new Error('Página do Chrome não encontrada.');
const ws=new WebSocket(target.webSocketDebuggerUrl);await new Promise((ok,bad)=>{ws.onopen=ok;ws.onerror=bad});
let seq=0;const pending=new Map();ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id&&pending.has(m.id)){pending.get(m.id)(m);pending.delete(m.id)}};
function command(method,params={}){const id=++seq;ws.send(JSON.stringify({id,method,params}));return new Promise(ok=>pending.set(id,ok))}
async function evaluate(expression){const o=await command('Runtime.evaluate',{expression,returnByValue:true});if(o.result?.exceptionDetails)throw new Error(o.result.exceptionDetails.text);return o.result?.result?.value}
const wait=ms=>new Promise(r=>setTimeout(r,ms));async function until(x,msg){for(let i=0;i<100;i++){if(await evaluate(x))return;await wait(100)}throw new Error(msg)}
await command('Runtime.enable');await command('Page.enable');
const expected=await evaluate("({name:sessionStorage.getItem('e2eExpectedName'),batch:Number(sessionStorage.getItem('e2eExpectedBatch')),history:Number(sessionStorage.getItem('e2eExpectedHistory'))})");
await command('Page.navigate',{url:base});await wait(500);await until("document.readyState==='complete'&&typeof state!=='undefined'&&state.batch",'Interface não recuperou o estado após reiniciar o servidor');
const result=await evaluate(`({sameBatch:state.batch.id===${expected.batch},registration:state.registrations.some(p=>p.name===${JSON.stringify(expected.name)}),history:state.history.length===${expected.history},emptyBatch:state.participants.length===0,activityEmpty:Object.keys(state.activity).length===0})`);
if(!Object.values(result).every(Boolean))throw new Error(`Recuperação após reinício falhou: ${JSON.stringify(result)}`);
console.log(JSON.stringify({ok:true,checks:result},null,2));ws.close();
