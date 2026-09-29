import fs from 'node:fs';

const cdp='http://127.0.0.1:9233', base='http://127.0.0.1:8768';
const targets=await(await fetch(`${cdp}/json/list`)).json();
const target=targets.find(t=>t.type==='page');
if(!target)throw new Error('A página da demonstração não foi encontrada.');
const ws=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject});
let seq=0;const pending=new Map();
ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id&&pending.has(m.id)){pending.get(m.id)(m);pending.delete(m.id)}};
function cmd(method,params={}){const id=++seq;ws.send(JSON.stringify({id,method,params}));return new Promise(resolve=>pending.set(id,resolve))}
async function evaluate(expression){const out=await cmd('Runtime.evaluate',{expression,returnByValue:true});if(out.result?.exceptionDetails)throw new Error(out.result.exceptionDetails.text);return out.result?.result?.value}
const wait=ms=>new Promise(r=>setTimeout(r,ms));
async function until(expression,message){for(let i=0;i<100;i++){if(await evaluate(expression))return;await wait(100)}throw new Error(message)}
async function screenshot(name){const result=await cmd('Page.captureScreenshot',{format:'png',captureBeyondViewport:false,fromSurface:true});fs.writeFileSync(`docs/images/${name}.png`,Buffer.from(result.result.data,'base64'))}
await cmd('Runtime.enable');await cmd('Page.enable');await cmd('Emulation.setDeviceMetricsOverride',{width:1600,height:1400,deviceScaleFactor:1,mobile:false});
await cmd('Page.navigate',{url:base});await wait(500);await until("typeof state!=='undefined'&&state.batch&&state.participants.length===3",'Os três participantes fictícios não carregaram.');
await screenshot('participantes-lote');
await evaluate("document.querySelector('[data-next=\"2\"]').click()");await until("document.querySelector('[data-panel=\"2\"]').classList.contains('active')",'Etapa Atividade não abriu.');
await screenshot('dados-atividade');
await evaluate("document.querySelector('#save-activity').click()");await until("document.querySelector('[data-panel=\"3\"]').classList.contains('active')",'Dados da atividade não passaram pela validação.');
await evaluate("document.querySelector('#make-preview').click()");await until("document.querySelector('#pdf-frame').src.startsWith('blob:')",'A prévia real do certificado não carregou.');await wait(1000);
await cmd('Input.dispatchMouseEvent',{type:'mousePressed',x:830,y:414,button:'left',clickCount:1});await cmd('Input.dispatchMouseEvent',{type:'mouseReleased',x:830,y:414,button:'left',clickCount:1});await wait(250);
await screenshot('previa-certificado');
await evaluate("document.querySelector('#generate').click()");await until("document.querySelector('[data-panel=\"4\"]').classList.contains('active')&&generated.length===3",'Os três PDFs não foram gerados.');
await evaluate("document.querySelector('#show-email').click();scrollTo(0,0)");await wait(250);
await screenshot('resultado-certificados');
console.log(JSON.stringify({ok:true,shots:['participantes-lote.png','dados-atividade.png','previa-certificado.png','resultado-certificados.png'],participants:3,generated:3,history:await evaluate('state.history.length'),demoBase:base},null,2));
ws.close();
