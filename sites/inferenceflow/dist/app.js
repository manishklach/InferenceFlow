const $ = (selector) => document.querySelector(selector);
const money = value => '$' + (value / 1000000).toFixed(6);
let evidence = null;
let preset = 'single';
let replaying = false;
let stageTimer = null;
let language = 'python';

const scenes = [
  ['01-sign-in.jpg','Sign in','Start with a workspace.','Sign in with a synthetic development account. In production, managed OIDC handles identity.'],
  ['02-funded-workspace.jpg','Fund','Credits, ready for work.','The workspace starts with $10 of seeded development credit, zero reservations and no jobs. No payment was made.'],
  ['03-queued-reservation.jpg','Queue','A job ID starts the flow.','The API queues the request and reserves 54 microUSD. Available credit becomes $9.999946. The worker is paused for this capture.'],
  ['04-worker-running.jpg','Execute','The worker takes it from here.','A matching model identity and an available slot turn a leased request into running work. The mock adapter waits ten seconds for recording.'],
  ['05-completed-billing.jpg','Settle','Done. And accounted for.','The job completes with 150 synthetic input units and 69 output units. Capture: 36 microUSD. Unused release: 18 microUSD. Reserved balance: zero.'],
  ['06-result-retrieval.jpg','Results','Your results, in order.','The authenticated Results action returns output, usage and the charge. MOCK output is explicit. The later capture also includes the SDK jobs.'],
  ['07-ledger-and-sdk.jpg','Verify','A complete, reconciled story.','Three SDK requests cost another 88 microUSD. Idempotent replay returns the same job; a separate canceled request costs zero. Final credit: $9.999876. No drift.']
];
let scene = 0;

const examples = {
  python: `import os\nfrom packages.python_sdk import InferenceFlowClient\n\nwith InferenceFlowClient(\n    os.environ["INFERENCEFLOW_API_KEY"],\n    "http://localhost:8080",\n) as client:\n    job = client.create_job(\n        requests=[{\n            "custom_id": "document-001",\n            "messages": [{\n                "role": "user",\n                "content": "Summarize this document...",\n            }],\n            "max_output_tokens": 128,\n        }],\n        idempotency_key="import-2026-001",\n    )\n    completed = client.wait_for_job(job["id"])\n    results = client.get_results(job["id"])`,
  curl: `curl http://localhost:8080/v1/jobs \\\n  -H "Authorization: Bearer $INFERENCEFLOW_API_KEY" \\\n  -H "Content-Type: application/json" \\\n  -H "Idempotency-Key: import-2026-001" \\\n  -d '{\n    "model": "qwen3-4b",\n    "tier": "standard",\n    "requests": [{\n      "custom_id": "document-001",\n      "messages": [{\n        "role": "user",\n        "content": "Summarize this document..."\n      }],\n      "max_output_tokens": 128\n    }]\n  }'\n\n# Poll the returned job ID, then retrieve results:\n# GET /v1/jobs/{id}\n# GET /v1/jobs/{id}/results`
};

$('.menu-toggle').addEventListener('click', () => {
  const expanded = $('.menu-toggle').getAttribute('aria-expanded') !== 'true';
  $('.menu-toggle').setAttribute('aria-expanded', String(expanded));
  $('#navigation').classList.toggle('open', expanded);
});
$('#navigation').querySelectorAll('a').forEach(a => a.addEventListener('click', () => {
  $('.menu-toggle').setAttribute('aria-expanded', 'false');
  $('#navigation').classList.remove('open');
}));

function selectedJob() {
  if (preset === 'batch') return { initial:9999964, reserve:142, charge:88, released:54, requests:3,
    input:235, output:207, id:evidence?.sdk_job?.id || 'job_1d7e3d9ab09f4e2eafcd38a34dc89bba',
    text:'Process a three-request batch: summarize a document, extract its topic, and classify a billing statement.',
    result:evidence?.sdk_results?.items?.[0]?.output_text || 'MOCK · recorded batch output' };
  return { initial:10000000, reserve:54, charge:36, released:18, requests:1, input:150, output:69,
    id:evidence?.dashboard_jobs?.[0]?.id || 'job_26f77ad9b956483983bb530818dbeba9',
    text:'Summarize: InferenceFlow queues customer work, executes a pinned model on a worker, and captures credits for measured completed usage.',
    result:'MOCK 7b1f43710ba3f7b0e73647c73473c00652c0b570b5ed4f4c8c3fe260dd01c5fb' };
}
function resetReplay() {
  clearTimeout(stageTimer); const job=selectedJob();
  $('#request-copy').textContent=job.text;
  $('#request-count').textContent=job.requests+' REQUEST'+(job.requests===1?'':'S');
  $('#wallet-available').textContent=money(job.initial);$('#wallet-reserved').textContent=money(0);
  $('#ledger-reservation').textContent='—';$('#ledger-capture').textContent='—';$('#ledger-release').textContent='—';
  $('#job-charge').textContent=money(0);$('#job-state').textContent='READY';
  $('#response-label').textContent='WAITING FOR REPLAY';
  $('#response-content').textContent='A job ID starts the flow. Follow it through to settlement.';
  $('#wallet-note').replaceChildren(Object.assign(document.createElement('span'),{textContent:'↳'}),document.createTextNode(' Every movement, accounted for.'));
  document.querySelectorAll('.timeline li').forEach(li=>{li.classList.remove('active','done');li.querySelector('.stage-result').textContent='';});
}
document.querySelectorAll('.preset').forEach(button => button.addEventListener('click', () => {
  if(replaying)return;
  preset=button.dataset.preset;
  document.querySelectorAll('.preset').forEach(b=>{b.classList.toggle('active',b===button);b.setAttribute('aria-pressed',String(b===button));});
  resetReplay();
}));
function runReplay() {
  if(replaying)return;
  resetReplay();replaying=true;const job=selectedJob();
  $('#run-replay').disabled=true;$('#run-replay').textContent='Following the flow…';
  document.querySelectorAll('.preset').forEach(b=>b.disabled=true);
  const stages=[
    ()=>{$('#job-state').textContent='QUEUED';$('#wallet-available').textContent=money(job.initial-job.reserve);$('#wallet-reserved').textContent=money(job.reserve);$('#ledger-reservation').textContent=money(job.reserve);$('#response-label').textContent='202 ACCEPTED · RECORDED RESPONSE';$('#response-content').textContent='job_id: '+job.id;},
    ()=>{$('#job-state').textContent='LEASED';$('#response-label').textContent='MODEL IDENTITY MATCHED';$('#response-content').textContent='qwen3-4b · mock-v1 · worker generation fenced · lease epoch 1';},
    ()=>{$('#job-state').textContent='RUNNING';$('#response-label').textContent='WORKER EXECUTION';$('#response-content').textContent='Active request epochs are renewed while the engine processes the job.';},
    ()=>{$('#job-state').textContent='SUCCEEDED';$('#wallet-available').textContent=money(job.initial-job.charge);$('#wallet-reserved').textContent=money(0);$('#ledger-capture').textContent=money(job.charge);$('#ledger-release').textContent=money(job.released);$('#job-charge').textContent=money(job.charge);$('#response-label').textContent=job.input+' INPUT / '+job.output+' OUTPUT · SYNTHETIC UNITS';$('#response-content').textContent=job.result;$('#wallet-note').replaceChildren(Object.assign(document.createElement('span'),{textContent:'✓'}),document.createTextNode(' Settled. No reconciliation drift.'));}
  ];
  let index=0;
  function next(){const li=document.querySelectorAll('.timeline li');li.forEach((row,i)=>{row.classList.toggle('done',i<index);row.classList.toggle('active',i===index);row.querySelector('.stage-result').textContent=i<index?'✓':'';});stages[index]();if(index<3){index++;stageTimer=setTimeout(next,1050);}else{stageTimer=setTimeout(()=>{li.forEach(row=>{row.classList.remove('active');row.classList.add('done');row.querySelector('.stage-result').textContent='✓';});replaying=false;$('#run-replay').disabled=false;$('#run-replay').textContent='Replay again ↗';document.querySelectorAll('.preset').forEach(b=>b.disabled=false);},550);}}
  next();
}
$('#run-replay').addEventListener('click',runReplay);

scenes.forEach((item,i)=>{const b=document.createElement('button');b.type='button';const number=document.createElement('span');number.textContent=String(i+1).padStart(2,'0');b.append(number,document.createTextNode(item[1]));b.addEventListener('click',()=>showScene(i));$('#capture-steps').append(b);});
function showScene(index){scene=index;const item=scenes[index];$('#capture-index').textContent=String(index+1).padStart(2,'0')+' / 07';$('#capture-title').textContent=item[2];$('#capture-description').textContent=item[3];$('#capture-image').src='assets/walkthrough/'+item[0];$('#capture-image').alt=item[2];$('#capture-prev').disabled=index===0;$('#capture-next').disabled=index===6;document.querySelectorAll('#capture-steps button').forEach((b,i)=>{b.classList.toggle('active',i===index);b.setAttribute('aria-current',String(i===index));});}
$('#capture-prev').addEventListener('click',()=>showScene(Math.max(0,scene-1)));
$('#capture-next').addEventListener('click',()=>showScene(Math.min(6,scene+1)));
function enlarge(){const item=scenes[scene];$('#dialog-image').src='assets/walkthrough/'+item[0];$('#dialog-image').alt=item[2];$('#dialog-caption').textContent=item[3];$('#image-dialog').showModal();}
$('#capture-expand').addEventListener('click',enlarge);$('#capture-image-button').addEventListener('click',enlarge);
$('#close-dialog').addEventListener('click',()=>$('#image-dialog').close());
$('#image-dialog').addEventListener('click',event=>{if(event.target===$('#image-dialog'))$('#image-dialog').close();});

function setLanguage(value){language=value;$('#code-content').textContent=examples[value];$('#code-panel').setAttribute('aria-labelledby',value+'-tab');document.querySelectorAll('[data-language]').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.language===value)));$('#copy-code').textContent='Copy ⧉';}
document.querySelectorAll('[data-language]').forEach(b=>{b.addEventListener('click',()=>setLanguage(b.dataset.language));b.addEventListener('keydown',event=>{if(event.key==='ArrowLeft'||event.key==='ArrowRight'){event.preventDefault();const next=language==='python'?'curl':'python';setLanguage(next);$('#'+next+'-tab').focus();}});});
$('#copy-code').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(examples[language]);$('#copy-code').textContent='Copied ✓';}catch{$('#copy-code').textContent='Select code to copy';const range=document.createRange();range.selectNodeContents($('#code-content'));const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range);}});

fetch('assets/walkthrough/execution-evidence.json').then(response=>{if(!response.ok)throw new Error('Evidence unavailable');return response.json();}).then(data=>{evidence=data;}).catch(()=>{ /* Recorded fallback values remain available offline. */ });
resetReplay();showScene(0);setLanguage('python');
