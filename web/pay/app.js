import * as api from './api.js';
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const esc = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money = v => `${Number(v).toLocaleString('ko-KR')}원`;
const digits = v => Number(v).toLocaleString('ko-KR');
const time = v => new Date(v).toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit',hour12:false,timeZone:'Asia/Seoul'});
const openedAt = Date.now();
const kstDay = v => new Date(new Date(v).getTime()+9*3600000).toISOString().slice(0,10);
const receiptTime = v => new Date(v).toLocaleString('ko-KR',{timeZone:'Asia/Seoul',month:'long',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false});
const dateText = (weekday=false) => new Date(`${trip.date}T00:00:00+09:00`).toLocaleDateString('ko-KR',{month:'long',day:'numeric',...(weekday?{weekday:'short'}:{})});
const chip = s => `<span class="pill">${esc(s)}</span>`;
const icon = name => `<svg viewBox="0 0 24 24" aria-hidden="true">${({
  check:'<path d="m5 12 4 4L19 6"/>', arrow:'<path d="M5 12h14M13 6l6 6-6 6"/>',
  lock:'<rect x="5" y="10" width="14" height="11" rx="3"/><path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3"/>',
  exhibit:'<rect x="3.5" y="5" width="17" height="14" rx="3"/><path d="m3.5 15.5 4.5-4.5 4 4 2.5-2.5 6 5"/><circle cx="15.5" cy="9.5" r="1.6"/>',
  activity:'<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z"/>',
  shop:'<path d="M5 8h14l1 13H4zM8 8V6a4 4 0 0 1 8 0v2"/>',
  stop:'<path d="m7 7 10 10M7 17 17 7"/><circle cx="12" cy="12" r="10"/>'
})[name]??'<circle cx="12" cy="12" r="9"/>'}</svg>`;
const number = (amount,cls='') => `<strong class="num ${cls}">${digits(amount)}<em>원</em></strong>`;
const labels=['일정 확인','결제 맡기기','예약 확인','결제 전 확인','결제 완료'];
const titles=['우리의 합의 일정','정한 만큼만,<br>결제를 맡겨요','예약 확인은<br>에이전트가 대신','이대로 승인해도<br>되는 이유','맡긴 만큼,<br>같이 결제했어요'];
let input,trip,plan,world,mandates=[],quote,checked,tokens,confirmed,stage=1,epoch=0,recheckController;
let reapproving=false,cancelHolds=[],expiryTimer,chainRun=0,paying=false;
if(new URLSearchParams(location.search).get('embed')==='1') document.body.classList.add('embed');

// The same sampled spring and complete-number fitting used by TripFit.
function makeSpring(k,c){
  const w0=Math.sqrt(k),z=c/(2*w0),wd=w0*Math.sqrt(Math.max(1e-6,1-z*z));
  const x=t=>z<1?1-Math.exp(-z*w0*t)*(Math.cos(wd*t)+(z*w0/wd)*Math.sin(wd*t)):1-Math.exp(-w0*t)*(1+w0*t);
  let T=.25;for(let t=0;t<4;t+=1/120)if(Math.abs(1-x(t))>.003)T=t+1/120;
  const pts=Array.from({length:49},(_,i)=>+x(T*i/48).toFixed(4));pts[48]=1;
  return {easing:CSS.supports('transition-timing-function','linear(0, 1)')?`linear(${pts.join(',')})`:'cubic-bezier(.34,1.4,.64,1)',duration:Math.round(T*1000)};
}
const spring=makeSpring(320,15);
document.documentElement.style.setProperty('--spring',spring.easing);
document.documentElement.style.setProperty('--spring-ms',`${spring.duration}ms`);
function fitNumber(el){
  if(!el?.isConnected||!el.clientWidth)return;
  el.style.fontSize='';const base=parseFloat(getComputedStyle(el).fontSize);
  for(let i=0;i<4;i++){const overflow=el.scrollWidth;if(overflow<=el.clientWidth)break;
    const size=parseFloat(getComputedStyle(el).fontSize);el.style.fontSize=Math.min(base,size*(el.clientWidth-2)/overflow)+'px';}
}
let numberFrame=0;
function fitNumbers(){cancelAnimationFrame(numberFrame);numberFrame=requestAnimationFrame(()=>$$('.num').forEach(fitNumber));}
document.fonts?.ready.then(fitNumbers);addEventListener('resize',fitNumbers);
new ResizeObserver(fitNumbers).observe($('.phone'));
function clearHolds(){cancelHolds.forEach(f=>f());cancelHolds=[];}
function progress(){return labels.map((_,i)=>`<i class="${i+1===stage?'on':i+1<stage?'done':''}"></i>`).join('');}
async function audit(){
  const run=++chainRun,currentWorld=world;
  await currentWorld.audit.flush();if(currentWorld!==world||run!==chainRun)return;
  const rows=api.auditLog(world);$('#log-count').textContent=`${rows.length}건`;
  const actors={user:'사용자',agent:'에이전트',network:'결제사',merchant:'판매자'};
  $('#logs').innerHTML=rows.map(r=>`<li><time>${esc(time(r.at))}</time><span>${esc(actors[r.actor]??r.actor)} · ${esc(r.action)}</span><code>${esc(r.prev_hash)} → ${esc(r.hash)}</code></li>`).join('');
  const valid=await api.verifyChain(rows);if(currentWorld!==world||run!==chainRun)return;
  $('#chain-status').textContent=valid?'해시 체인 검증 통과 · 기록의 연결이 일치해요':'해시 체인 검증 실패 · 기록을 확인해 주세요';
}
function frame(body){
  clearHolds();clearTimeout(expiryTimer);paying=false;
  $('#caption-step').textContent=`0${stage} / 05`;$('#caption-progress').innerHTML=progress();
  $('#flow').innerHTML=`<header class="b lime hero cut"><div class="eyebrow"><span>TripFit · 같이 결제</span><span class="stage-counter">0${stage} / 05</span></div><h2 id="active-title" tabindex="-1"><span class="label">${esc(labels[stage-1])}</span>${titles[stage-1]}</h2><div class="row between"><p>${stage===1?`${dateText(true)} · 성수 · 서울숲`:stage===2?'판매처·상품·상한을 정하고 각자 승인해요':stage===3?'예약 가능 여부와 가격을 다시 확인해요':stage===4?'맡긴 범위와 조회 결과를 대조했어요':'모의 결제 완료 · 실제 돈은 나가지 않아요'}</p>${stage===1?`<div class="avatars">${trip.people.map(p=>`<span class="avatar">${esc(p.name[0])}</span>`).join('')}</div>`:''}</div><nav class="cap-prog" aria-label="${stage}/5단계 · ${labels[stage-1]}">${progress()}</nav></header>${body}<p id="message" role="alert"></p>`;
  $('#test-price').disabled=stage<3||stage===5;$('#test-merchant').disabled=!confirmed;
  $('#technical').open=false;$('.shell').scrollTop=0;if(document.body.classList.contains('embed')||innerWidth<=650)scrollTo(0,0);
  fitNumbers();void audit();
}
function focusTitle(){ $('#active-title')?.focus({preventScroll:true}); }
function nextButton(text){return `<div class="action"><button id="next" class="primary">${esc(text)}${icon('arrow')}</button></div>`;}
function holdMarkup(label){return `<button class="primary hold" type="button" aria-label="${esc(label)} · 1초 동안 길게 누르기"><svg viewBox="0 0 24 24" aria-hidden="true"><circle class="track" cx="12" cy="12" r="10"/><circle class="progress" cx="12" cy="12" r="10"/></svg><span>${esc(label)}<small class="hold-label"> · 1초</small></span></button>`;}
function bindHold(button,drawnAt,action){
  let start=null,raf,done=false,heldKey=null,pointer=null;
  function cancel(){start=null;heldKey=null;pointer=null;cancelAnimationFrame(raf);button.classList.remove('holding');button.querySelector('.progress')?.setAttribute('style','stroke-dashoffset:63');}
  cancelHolds.push(cancel);
  function tick(now){
    if(start===null||done)return;
    const elapsed=now-start;
    button.querySelector('.progress').style.strokeDashoffset=String(63*(1-Math.min(1,elapsed/1000)));
    if(elapsed>=1000){done=true;const approval_ms=Math.max(1000,Math.round(now-drawnAt));cancel();button.disabled=true;Promise.resolve(action(approval_ms)).catch(showError);return;}
    raf=requestAnimationFrame(tick);
  }
  function begin(){if(done||button.disabled||start!==null)return;start=performance.now();button.classList.add('holding');raf=requestAnimationFrame(tick);}
  button.addEventListener('pointerdown',e=>{if(e.button!==0||!e.isPrimary)return;e.preventDefault();pointer=e.pointerId;button.setPointerCapture(e.pointerId);begin();});
  button.addEventListener('pointermove',e=>{if(pointer!==e.pointerId)return;const r=button.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)cancel();});
  ['pointerup','pointercancel','lostpointercapture','blur'].forEach(type=>button.addEventListener(type,cancel));
  button.addEventListener('keydown',e=>{if(![' ','Enter'].includes(e.key))return;e.preventDefault();if(!e.repeat&&heldKey===null){heldKey=e.key;begin();}});
  button.addEventListener('keyup',e=>{if(e.key===heldKey){e.preventDefault();cancel();}});
  const onHidden=()=>{if(document.hidden)cancel();}; document.addEventListener('visibilitychange',onHidden);
  cancelHolds.push(()=>document.removeEventListener('visibilitychange',onHidden));
}

function showError(error){
  const el=$('#message');if(el){el.textContent=error?.message??'진행하지 못했어요. 다시 확인해 주세요';el.scrollIntoView({block:'nearest'});}
}
function reset(){
  epoch++;recheckController?.abort();clearHolds();clearTimeout(expiryTimer);
  world=api.createWorld();trip=api.loadTrip(world,structuredClone(input));
  mandates=[];quote=checked=tokens=confirmed=null;reapproving=false;stage=1;$('#malfunction').innerHTML='';
  // Always render the externally supplied payment item, even when its name differs from the demo plan.
  const suppliedPlan=plan.map(s=>({...s}));
  const target=suppliedPlan.findIndex(s=>s.name===trip.item.short_name||s.catKo==='체험');
  if(target>=0)suppliedPlan[target]={...suppliedPlan[target],name:trip.item.short_name,start:trip.item.start};
  else suppliedPlan.push({name:trip.item.short_name,start:trip.item.start,end:'',catKo:'체험',paid:true});
  frame(`<section class="b mint tab plan-note"><span class="label">함께 정한 하루</span><h3>이번에 결제할 것 1개<br>현장 결제 ${suppliedPlan.length-1}곳</h3><p>체험만 지금 결제하고, 나머지는 현장에서 결제해요.</p></section><ol class="timeline">${suppliedPlan.map((s,i)=>{
    const selected=s.name===trip.item.short_name;
    return `<li class="b stop ${selected?'payment-target':i===0?'mint':'butter'}"><span class="ico">${icon(selected?'activity':s.catKo==='전시'?'exhibit':'shop')}</span><div class="stop-copy"><strong>${esc(s.name)}</strong><small>${esc(s.catKo)} · ${selected?`1인 ${money(trip.item.price)}`:'현장 결제'}</small>${selected?`<span class="pill">${icon('lock')}이번에 결제할 항목</span>`:''}</div><time>${esc(s.start)}${s.end?`<small>~ ${esc(s.end)}</small>`:''}</time></li>`;
  }).join('')}</ol><section class="b peach"><div class="row between"><span class="label">${esc(trip.item.merchant_label)}</span>${chip(`${trip.people.length}명`)}</div><h3>${esc(trip.item.short_name)}</h3><p class="body-copy">정해진 판매처·상품·시각에만 결제를 맡겨요.</p></section>${nextButton('이 체험 결제 맡기기')}`);
  $('#next').onclick=()=>mandateScreen(trip.item.price);
}
function expiry(opened=openedAt){
  const rounded=Math.ceil((opened+2*60*60*1000)/(10*60*1000))*(10*60*1000);
  return `${new Date(rounded+9*3600000).toISOString().slice(0,19)}+09:00`;
}
function expiryText(value,now=Date.now()){
  const day=kstDay(value)===kstDay(now)?'오늘':'내일';return `${day} ${time(value)}까지`;
}
function mandateScreen(amount){
  stage=2;const expiresAt=expiry(Math.max(openedAt,world.clock.now().getTime()));
  mandates=trip.people.map(p=>api.createMandate(world,trip,p.id,{max_per_person:amount,expires_at:expiresAt}));
  frame(`<div class="cards">${trip.people.map((p,i)=>`<article class="b person-card ${i===0?'pink tab':'sky'}" data-person="${esc(p.id)}"><div class="person-head"><div class="row"><span class="avatar">${esc(p.name[0])}</span><h3>${esc(p.name)}의 위임</h3></div></div><div class="limit"><span class="label">1인 결제 상한</span><strong class="num">${digits(amount)}<em>원까지</em></strong></div><dl class="scope"><div><dt>판매처</dt><dd>${esc(trip.item.merchant_label)}</dd></div><div><dt>상품</dt><dd>${esc(trip.item.short_name)}</dd></div><div><dt>옵션</dt><dd>${dateText()} · ${esc(trip.item.start)}</dd></div><div class="scope-pair"><dt>기한</dt><dd>${esc(expiryText(expiresAt))}</dd><dt>횟수</dt><dd>1회</dd></div></dl><div class="approval-area">${holdMarkup(`${p.name}이 결제 맡기기`)}</div></article>`).join('')}</div><div class="action"><p>1초 동안 눌러 승인해요. 중간에 놓으면 취소돼요.</p><button id="next" class="primary" disabled>두 사람 승인 후 예약 확인${icon('arrow')}</button></div>`);
  const run=epoch;
  $$('.person-card').forEach((card,i)=>{
    const drawnAt=performance.now();if(i>0)card.querySelector('button').disabled=true;
    bindHold(card.querySelector('button'),drawnAt,async approval_ms=>{
      const approved=await api.approveMandate(world,mandates[i],{approval_ms});if(run!==epoch)return;
      mandates[i]=approved;card.classList.add('approved');
      card.querySelector('.approval-area').innerHTML=`<div class="approval">${icon('check')}<span>맡겼어요 · ${esc(time(approved.approved_at))}</span></div>`;
      const nextCard=$$('.person-card')[i+1];if(nextCard)nextCard.querySelector('button').disabled=false;
      $('#next').disabled=!mandates.every(m=>m.status==='APPROVED');void audit();
    });
  });
  $('#next').onclick=()=>{if(!mandates.every(m=>m.status==='APPROVED'))return;if(reapproving)quoteScreen();else void reservation().catch(showError);};focusTitle();
}
function sourceChip(){return chip(`${checked.source==='live'?'실시간 조회':checked.source==='test'?'가격 인상 테스트':'저장된 조회 결과'} ${time(checked.checked_at)}`);}
function activityIsland(loading=false){return `<div class="island" role="status"><span class="ico">${loading?'<i class="spin"></i>':icon('check')}</span><div><b>${loading?`${esc(trip.item.merchant_label)}에 ${esc(trip.item.start)} 다시 조회 중`:'에이전트가 예약 확인을 마쳤어요'}</b><small>${loading?'두 사람의 위임 범위 안에서 확인해요':checked.source==='live'?'실시간 응답을 받았어요':'저장된 조회 결과로 확인했어요'}</small></div></div>`;}
function reservationBody(){return `${activityIsland()}<section class="b ${checked.available?'mint':'red'} result tab"><span class="label">${esc(trip.item.short_name)} · ${dateText()}</span><strong class="num result-time">${esc(trip.item.start)}</strong><h3>${checked.available?'예약 가능':'예약 불가'}</h3><span class="label body-copy">1인 가격</span>${number(checked.price,'result-price')}${sourceChip()}<ol class="activity"><li>${icon('check')}<span>두 사람 위임 확인</span></li><li>${icon('check')}<span>${esc(trip.item.merchant_label)}에 ${esc(trip.item.start)} 다시 조회</span></li><li>${icon(checked.available?'check':'stop')}<span>${checked.available?'예약 가능 여부·가격 확인 완료':'선택한 시각은 예약할 수 없어요'}</span></li></ol></section><details class="b pink draft"><summary>판매자 문의 초안 <span class="pill">보내지 않음</span></summary><p>안녕하세요. ${dateText()} ${esc(trip.item.start)} ${esc(trip.item.short_name)} ${trip.people.length}명 예약하려고 합니다. 지금 예약 가능한지, 비가 오면 진행하는지 알려 주세요.</p></details>${nextButton('결제 전 확인하기')}`;}
async function reservation(){
  stage=3;const run=++epoch;
  frame(activityIsland(true)+`<section class="b mint"><span class="label">에이전트가 대신 확인 중</span><h3>${esc(trip.item.merchant_label)}에서<br>${esc(trip.item.start)} 옵션을 다시 조회해요</h3><p class="body-copy">예약 가능 여부와 지금 가격을 확인해요.<br>연결되지 않으면 저장된 조회 결과를 사용해요.</p></section>`);focusTitle();
  recheckController=new AbortController();const timeout=setTimeout(()=>recheckController.abort(),2500);
  let result;
  try{
    const {gid,url,start}=trip.item;
    const response=await fetch('/api/pay/recheck',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({gid,url,date:trip.date,start}),signal:recheckController.signal});
    if(!response.ok)throw new Error('조회 실패');
    result=await response.json();
    if(typeof result.available!=='boolean'||!Number.isFinite(result.price)||result.price<0||!Number.isFinite(Date.parse(result.checked_at)))throw new Error('조회 결과 확인');
    result={...result,source:'live'};
  }catch{result={...trip.snapshot,source:'snapshot'};}finally{clearTimeout(timeout);}
  if(run!==epoch)return;
  await api.recheck(world,trip,result);if(run!==epoch)return;checked=result;
  frame(reservationBody());$('#next').onclick=quoteScreen;
}

// Read-only presentation of the engine's stored scope, quote and mandate state.
// No checks are persisted here; approveQuote / executeSplit remain the authority.
function inspection(){
  const scope={merchant_id:trip.item.merchant_id,item_gid:trip.item.gid,date:trip.date,option_start:trip.item.start};
  const item=world.merchant.lookup(scope),now=world.clock.now().getTime();
  const ms=trip.people.map(p=>mandates.find(m=>m.person_id===p.id&&m.status==='APPROVED'));
  const all=fn=>ms.length===trip.people.length&&ms.every(m=>m&&fn(m));
  const remaining=Math.min(...ms.map(m=>m?Date.parse(m.expires_at)-now:0));
  const merchant=Boolean(item&&item.merchant_id===scope.merchant_id&&all(m=>m.merchant_id===item.merchant_id));
  const product=Boolean(item&&item.item_gid===scope.item_gid&&item.date===trip.date&&item.option_start===trip.item.start&&all(m=>m.item_gid===item.item_gid&&m.option_start===item.option_start));
  const price=quote.lines.length===trip.people.length&&quote.lines.every(l=>l.mandate_max!==null&&l.amount<=l.mandate_max);
  const available=Boolean(item?.available);
  const inTime=all(m=>now<Date.parse(m.expires_at));
  const unused=all(m=>m.status==='APPROVED'&&m.uses===1&&!world.pay.isMandateUsed(m.id));
  const checks=[
    {key:'merchant',title:'판매처 일치',ok:merchant,evidence:merchant?`${trip.item.merchant_label} = 맡긴 판매처`:'판매처 또는 위임이 일치하지 않아요',repair:'맡긴 판매처로 다시 확인하기'},
    {key:'product',title:'상품·시각 일치',ok:product,evidence:product?`${trip.item.short_name} ${item.option_start} = 합의 일정`:'합의한 상품·시각 또는 위임을 확인해 주세요',repair:'합의 일정부터 다시 확인하기'},
    {key:'price',title:'가격 ≤ 상한',ok:price,evidence:quote.lines.map(l=>`${l.name} ${digits(l.amount)} ${l.amount<=(l.mandate_max??-1)?'≤':'>'} ${l.mandate_max===null?'위임 없음':digits(l.mandate_max)}`).join(' · '),repair:'새 금액으로 다시 맡기기'},
    {key:'available',title:'예약 가능',ok:available,evidence:`${item?.option_start??trip.item.start} ${available?'예약 가능':'예약 불가'} · ${item?time(item.checked_at):'조회 필요'} 조회`,repair:'일정에서 다른 시각 선택하기'},
    {key:'expiry',title:'기한 안',ok:inTime,evidence:inTime?`${Math.floor(remaining/60000)}분 ${Math.floor(remaining/1000)%60}초 남음 · ${time(ms.reduce((a,b)=>Date.parse(a.expires_at)<Date.parse(b.expires_at)?a:b).expires_at)}까지`:'위임 기한이 지났거나 위임이 없어요',repair:'기한을 확인하고 다시 맡기기'},
    {key:'unused',title:`${trip.people.length===2?'두 사람':`${trip.people.length}명`} 위임 완료`,ok:unused,evidence:unused?'각자 승인 · 1회 권한 모두 미사용':'승인 누락 또는 이미 사용한 권한이 있어요',repair:'각자 새 위임 승인하기'}
  ];
  return {checks,ready:quote.status==='READY'&&quote.lines.every(l=>l.within)&&checks.every(c=>c.ok),remaining};
}
function splitBlocks(){return `<div class="split">${quote.lines.map((l,i)=>`<section class="b ${i===0?'pink':'sky'}"><span class="label">${esc(l.name)} 카드</span>${number(l.amount)}<small>상한 ${l.mandate_max===null?'위임 없음':money(l.mandate_max)} · ${l.within?'범위 안':'범위 밖'}</small></section>`).join('')}</div><section class="b total"><span class="label">합계<br>${quote.lines.length}명 분담</span>${number(quote.total)}</section>`;}
function changes(){
  const changes=quote.lines.filter(l=>l.mandate_max!==null&&l.amount!==l.mandate_max);
  return `<section class="b ${changes.length?'peach':'cream'} change"><h3>맡길 때와 달라진 것</h3>${changes.length?`<div class="price-change"><strong class="num">${digits(changes[0].mandate_max)}</strong>${icon('arrow')}<strong class="num">${digits(changes[0].amount)}<em>원</em></strong></div><small>1인 가격 · ${changes.map(l=>esc(l.name)).join('·')}의 위임 상한과 달라요</small>`:'<p>달라진 것 없음</p>'}</section>`;
}
function quoteScreen(){
  stage=4;quote=api.buildQuote(world,trip);
  const {checks,ready,remaining}=inspection();
  const canReapprove=quote.status==='NEEDS_REAPPROVAL'||quote.status==='WAITING_MANDATES';
  frame(`<section class="b ${ready?'mint':'red'} tab checks-heading"><div class="row between"><h3>${ready?'맡긴 조건 모두 확인':'결제를 멈췄어요'}</h3><span class="pill fill">${checks.filter(c=>c.ok).length} / 6 통과</span></div><p>${esc(trip.item.merchant_label)} · ${esc(trip.item.start)} · ${dateText()}</p></section><div class="checks" aria-label="결제 범위 검사 6개">${checks.map(c=>`<section class="b check ${c.ok?'mint':'red'}" data-check="${c.key}" data-pass="${c.ok}"><div class="check-title">${icon(c.ok?'check':'stop')}<span>${esc(c.title)}</span></div><p>${esc(c.evidence)}${c.ok?'':`<span class="repair">${esc(c.repair)}</span>`}</p></section>`).join('')}</div>${changes()}${splitBlocks()}<section class="b cream consequences"><h3>누르면 일어나는 일</h3><ol><li>${quote.lines.map(l=>`${esc(l.name)} 카드 ${money(l.amount)}`).join(' · ')}을 각각 1회용 결제 권한으로 결제해요.</li><li>판매자도 같은 승인 기록을 받아요. 해시는 승인할 때 생성되며, 영수증에서 앞 8자를 확인해요.</li><li>모의 결제 — 실제 돈은 나가지 않아요.</li></ol></section>${!ready?`<section class="b red stop-reason"><h3>다시 확인하고 맡겨 주세요</h3><p>${esc(quote.reasons.join(' · ')||checks.filter(c=>!c.ok).map(c=>c.repair).join(' · '))}</p></section>`:''}<div class="action"><p>대표 ${esc(trip.people[0].name)}이 ${trip.people.length===2?'두 사람':`${trip.people.length}명`} 위임으로 결제</p>${holdMarkup(ready?`${money(quote.total)} 결제하기`:'조건 확인 전 결제 잠김')}${canReapprove?`<button id="reapprove" class="primary">${money(checked.price)}으로 다시 맡기기${icon('arrow')}</button>`:''}${!ready?'<button id="cancel" class="secondary">일정부터 다시 확인하기</button>':''}</div>`);
  const button=$('.hold');button.disabled=!ready;
  if(ready){const drawnAt=performance.now(),run=epoch;bindHold(button,drawnAt,async approval_ms=>{
    // Refresh the read-only inspection at the moment of approval; the engine revalidates again.
    if(!inspection().ready){quoteScreen();return;}
    paying=true;clearTimeout(expiryTimer);$('#test-price').disabled=true;
    try{
      const approval=await api.approveQuote(world,quote,{approver_id:trip.people[0].id,approval_ms});if(run!==epoch)return;
      tokens=approval.tokens;const result=await api.executeSplit(world,quote,tokens);if(run!==epoch)return;
      if(!result.ok){void audit();throw new Error(`결제를 멈췄어요 (${result.error_code})`);}confirmed=result.confirmed;complete();
    }catch(e){if(run===epoch){quoteScreen();showError(e);}}
  });}
  if($('#reapprove'))$('#reapprove').onclick=()=>{reapproving=true;mandateScreen(checked.price);};
  if($('#cancel'))$('#cancel').onclick=reset;
  if(ready){
    const refreshExpiry=()=>{
      if(stage!==4||paying)return;
      const current=inspection();
      if(!current.ready){quoteScreen();return;}
      const cell=$('[data-check="expiry"] p');if(cell)cell.textContent=current.checks.find(c=>c.key==='expiry').evidence;
      expiryTimer=setTimeout(refreshExpiry,Math.min(1000,Math.max(1,current.remaining)));
    };
    expiryTimer=setTimeout(refreshExpiry,Math.min(1000,Math.max(1,remaining)));
  }
  focusTitle();
}
function receiptHead(){return `<div class="receipt-head">${chip('모의 결제 영수증')}<strong>${esc(trip.item.short_name)}</strong><small>${dateText(true)} · ${esc(trip.item.start)} · ${trip.people.length}명<br>${esc(trip.item.merchant_label)}</small></div>`;}
function supplierMarkup(){return api.supplierView(world).map(r=>`<p>${esc(r.item.short_name)} ${esc(r.option_start)} · ${r.people_count}명</p><p>예약 요청 + ${r.payments.length}건 결제 내역 + 각자 위임 기록</p><p>같은 승인 기록 <code>${esc(r.quote_hash.slice(0,8))}</code></p><p>모의 판매자 기록에 전달 완료 · 실제 예약 확정은 아래 링크에서 진행해요.</p>`).join('');}
function complete(){
  stage=5;const name=id=>trip.people.find(p=>p.id===id)?.name??id;
  const url=new URL(trip.item.url,location.href),safeUrl=url.protocol==='https:'?url.href:'#';
  frame(`<section class="b cream receipt tab">${receiptHead()}${confirmed.payments.map(p=>`<div class="receipt-line"><div><strong>${esc(name(p.person_id))} 카드</strong><small>승인번호 ${esc(p.approval_no)}</small></div>${number(p.amount)}</div>`).join('')}<div class="receipt-total"><span>합계</span>${number(confirmed.total)}</div><div class="receipt-meta"><div class="hash-row"><div><span class="label">두 사람의 승인 기록</span><code>${esc(confirmed.quote_hash.slice(0,8))}</code></div><button id="copy-hash" class="copy">해시 복사</button></div><span>${esc(receiptTime(confirmed.paid_at))}</span><p id="copy-status" role="status"></p><span>모의 결제 · 실제 돈은 나가지 않았어요</span></div></section><section class="b mint supplier"><h3>판매자에게 전달된 내용</h3>${supplierMarkup()}<a class="link-button" href="${esc(safeUrl)}" target="_blank" rel="noopener noreferrer">마이리얼트립에서 예약 확정${icon('arrow')}</a><small>예약 확정은 상품 페이지에서 직접 마무리해요.</small></section>`);
  $('#copy-hash').onclick=async()=>{try{await navigator.clipboard.writeText(confirmed.quote_hash);$('#copy-status').textContent='전체 승인 기록 해시를 복사했어요';}catch{$('#copy-status').textContent=`복사할 해시: ${confirmed.quote_hash}`;}};
  focusTitle();
}
$('#reset').onclick=()=>{try{reset();}catch(e){showError(e);}};
$('#test-price').onclick=async()=>{
  if(stage<3||stage===5||paying)return;const run=++epoch;recheckController?.abort();clearHolds();clearTimeout(expiryTimer);
  const result={available:true,price:38000,source:'test',checked_at:new Date().toISOString()};
  try{await api.recheck(world,trip,result);if(run!==epoch)return;checked=result;quoteScreen();}catch(e){showError(e);}
};
$('#test-merchant').onclick=async()=>{
  if(!confirmed)return;const run=epoch;
  try{const result=await api.simulateMalfunction(world,tokens[0],{merchant_id:'other:merchant',amount:confirmed.payments[0].amount});if(run!==epoch)return;
    $('#malfunction').innerHTML=`<section class="b red blocked"><h3>${icon('lock')}에이전트가 막은 것</h3><p>다른 판매처 결제 시도 → ${result.ok?'결과 확인 필요':'거절'}</p><p>${result.error_code==='MERCHANT_MISMATCH'?'맡긴 판매처가 아니어서 결제사가 거절했어요. 추가 결제는 발생하지 않았어요.':'검사 결과를 확인해 주세요.'}</p><code>${esc(result.error_code??'UNKNOWN')}</code></section>`;
    $('#technical').open=false;$('#malfunction').scrollIntoView({block:'nearest'});void audit();
  }catch(e){showError(e);}
};
try{
  const [loadedTrip,loadedPlan]=await Promise.all([window.TRIPFIT_PAY_INPUT?Promise.resolve(structuredClone(window.TRIPFIT_PAY_INPUT)):fetch('./data/trip.json').then(r=>{if(!r.ok)throw new Error('일정을 불러오지 못했어요');return r.json();}),fetch('./data/plan_summary.json').then(r=>{if(!r.ok)throw new Error('일정을 불러오지 못했어요');return r.json();})]);
  input=loadedTrip;plan=loadedPlan;reset();
}catch(e){$('#flow').innerHTML=`<section class="b red"><p role="alert">${esc(e.message)}</p></section>`;}
