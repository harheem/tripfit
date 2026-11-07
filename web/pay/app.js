import * as api from './api.js';
const $ = s => document.querySelector(s);
const esc = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money = v => `${Number(v).toLocaleString('ko-KR')}원`;
const time = v => new Date(v).toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit',hour12:false,timeZone:'Asia/Seoul'});
const openedAt = Date.now();
const kstDay = v => new Date(new Date(v).getTime()+9*3600000).toISOString().slice(0,10);
const receiptTime = v => {
  const parts = Object.fromEntries(new Intl.DateTimeFormat('ko-KR',{timeZone:'Asia/Seoul',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date(v)).map(p=>[p.type,p.value]));
  return `${parts.month}월 ${parts.day}일 ${parts.hour}:${parts.minute}`;
};
const approvalNumber = v => String(v ?? '').match(/(\d+)$/)?.[1] ?? '—';
const dateText = (weekday=false) => new Date(`${trip.date}T00:00:00+09:00`).toLocaleDateString('ko-KR',{month:'long',day:'numeric',...(weekday?{weekday:'short'}:{})}).replace(/\. /g,' ').replace(' (','(');
const chip = s => `<span class="chip">${esc(s)}</span>`;
const labels=['일정 확인','결제 맡기기','예약 확인','결제 전 확인','결제 완료'];
const numbers=['①','②','③','④','⑤'];
let input,trip,plan,world,mandates=[],quote,checked,tokens,confirmed,stage=1,epoch=0,recheckController;
let reapproving=false,approvedTimes=new Map(),cancelHolds=[];
if(new URLSearchParams(location.search).get('embed')==='1') document.body.classList.add('embed');
function clearHolds(){cancelHolds.forEach(f=>f());cancelHolds=[];}
function audit(){
  const rows=api.auditLog(world); $('#log-count').textContent=`${rows.length}건`;
  const actions={
    ITEM_REGISTERED:'상품 등록',TRIP_LOADED:'일정 확인',MANDATE_CREATED:'위임 작성',
    MANDATE_APPROVED:'결제 맡기기 승인',MANDATE_SUPERSEDED:'이전 위임 교체',
    RECHECK:'예약 가능 여부·가격 재조회',ITEM_RECHECKED:'예약 가능 여부·가격 확인',
    QUOTE_CREATED:'결제 내역 작성',QUOTE_APPROVED:'결제 전 승인',TOKEN_ISSUED:'결제 승인 기록 발급',
    PAYMENT_ATTEMPT:'결제 범위 확인',PAYMENT_RESULT:'결제 확인 결과',
    PAYMENT_VOIDED:'결제 취소',PAYMENT_CONFIRMED:'결제 승인',SPLIT_RESULT:'나눠 결제 결과',
    BOOKING_REQUESTED:'예약 요청 전달',MALFUNCTION_ATTEMPT:'테스트: 다른 판매처 결제 시도'
  };
  const actors={user:'사용자',agent:'에이전트',network:'결제사',merchant:'판매자'};
  $('#logs').innerHTML=rows.map(r=>`<li><time>${esc(time(r.at??r.timestamp??r.created_at))}</time><code>${esc((r.hash??'').slice(0,6))}</code><span>${esc(actors[r.actor]??r.actor)} · ${esc(actions[r.action]??(/[A-Z_]/.test(r.action)?'승인 기록 추가':r.action))}</span></li>`).join('');
  const suppliers=api.supplierView(world);
  $('#supplier').innerHTML=suppliers.length?suppliers.map(r=>`<p>상품·옵션<br><strong>${esc(trip.item.short_name)} ${esc(r.option_start)}</strong></p><p>인원 ${r.people_count}명</p><p>결제 ${r.payments.length}건 ${money(r.payments.reduce((s,p)=>s+p.amount,0))}</p><p>두 분 모두 승인 · 기록 <code>${esc(r.quote_hash.slice(0,8))}</code></p>${chip('모의 결제 · 실제 결제 없음')}`).join(''):'아직 전달된 내용이 없어요';
}
function frame(body){
  clearHolds();
  $('#steps').innerHTML=labels.map((l,i)=>`<li class="${i+1===stage?'current':i+1<stage?'done':''}" ${i+1===stage?'aria-current="step"':''} aria-label="${i+1} ${l}"><span class="step-no">${numbers[i]}</span><span class="step-label">${l}</span></li>`).join('');
  $('#flow').innerHTML=labels.slice(0,stage-1).map((l,i)=>`<details class="history"><summary class="collapsed">${numbers[i]} ${l}<span>확인했어요</span></summary><p class="panel muted">${esc(historyText(i+1))}</p></details>`).join('')+`<section class="panel" aria-labelledby="active-title"><div class="panel-top"><h2 id="active-title" tabindex="-1">${numbers[stage-1]} ${labels[stage-1]}</h2></div>${body}<p id="message" role="alert"></p></section>`;
  $('#test-price').disabled=stage<3||stage===5;
  $('#test-merchant').disabled=!confirmed;
  audit();
}
function historyText(step){
  if(step===1)return `${dateText(true)} ${trip.item.short_name} ${trip.item.start} · ${trip.people.length}명`;
  if(step===2)return `${trip.people.map(p=>p.name).join(' · ')} 승인했어요`;
  if(step===3)return resultText();
  return `합계 ${money(quote?.total??0)} · 결제 전 확인했어요`;
}
function focusTitle(){ $('#active-title')?.focus({preventScroll:true}); }
function holdMarkup(label){return `<button class="primary hold" type="button"><svg viewBox="0 0 24 24" aria-hidden="true"><circle class="track" cx="12" cy="12" r="10"/><circle class="progress" cx="12" cy="12" r="10"/></svg><span>${esc(label)}</span></button>`;}
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
function showError(error){const el=$('#message');if(el)el.textContent=error?.message??'진행하지 못했어요. 처음부터 다시 확인해 주세요';}
function reset(){
  epoch++;recheckController?.abort();clearHolds();world=api.createWorld();trip=api.loadTrip(world,structuredClone(input));
  mandates=[];quote=checked=tokens=confirmed=null;reapproving=false;approvedTimes.clear();stage=1;$('#malfunction').innerHTML='';
  frame(`<p>이 일정에서 결제할 항목이 1개 있어요</p>${chip('샘플 일정')}<ol class="timeline">${plan.map(s=>`<li class="${s.name===trip.item.short_name?'payment-target':''}"><time>${esc(s.start)}<br>– ${esc(s.end)}</time><div><strong>${esc(s.name)}</strong><small>${esc(s.catKo)}${s.paid?' · 유료':''}${s.name===trip.item.short_name?' · 이번 결제 대상':s.paid?' · 현장 결제':''}</small></div></li>`).join('')}</ol><div class="item"><h3>${esc(trip.item.short_name)}</h3><p>${dateText(true)} ${esc(trip.item.start)} · ${trip.people.length}명 · 1인 ${money(trip.item.price)}</p><small>${esc(trip.item.merchant_label)}</small></div><button id="next" class="primary">다음</button>`);
  $('#next').onclick=()=>mandateScreen(trip.item.price);
}
function expiry(opened=openedAt){
  const rounded=Math.ceil((opened+2*60*60*1000)/(10*60*1000))*(10*60*1000);
  return `${new Date(rounded+9*3600000).toISOString().slice(0,19)}+09:00`;
}
function expiryText(value,now=Date.now()){
  const day=kstDay(value)===kstDay(now)?'오늘':'내일';
  return `${day} ${time(value)}까지`;
}
function mandateScreen(amount){
  stage=2;
  const expiresAt=expiry();
  mandates=trip.people.map(p=>api.createMandate(world,trip,p.id,{max_per_person:amount,expires_at:expiresAt}));
  frame(`<p>아래 범위 안에서만 결제해요. 범위가 바뀌면 다시 여쭤볼게요</p><div class="cards">${trip.people.map((p,i)=>`<article class="person-card" style="--person:${i===0?'#F2643D':'#2E8FD8'}" data-person="${esc(p.id)}"><h3>${esc(p.name)}</h3><dl><div><dt>결제처</dt><dd>${esc(trip.item.merchant_label)} · ${esc(trip.item.short_name)} ${esc(trip.item.start)}</dd></div><div><dt>최대 금액</dt><dd>1인 ${money(amount)}</dd></div><div><dt>기한</dt><dd>${esc(expiryText(expiresAt))}</dd></div><div><dt>횟수</dt><dd>1회</dd></div></dl><div class="approval-area">${holdMarkup(`${p.name} 님 승인 (1초 누르기)`)}</div></article>`).join('')}</div><small class="hold-help">1초 동안 눌러 주세요. 중간에 놓으면 취소돼요</small><button id="next" class="primary" disabled style="margin-top:24px">다음</button>`);
  const run=epoch;
  document.querySelectorAll('.person-card').forEach((card,i)=>{
    const drawnAt=performance.now();
    // Only the next approval is lime; the second stays neutral until the first completes.
    if(i>0)card.querySelector('button').disabled=true;
    bindHold(card.querySelector('button'),drawnAt,async approval_ms=>{
      const approved=await api.approveMandate(world,mandates[i],{approval_ms});if(run!==epoch)return;
      mandates[i]=approved;approvedTimes.set(approved.id,approval_ms);
      card.querySelector('.approval-area').innerHTML=`<div class="approval">승인했어요 · ${esc(time(approved.approved_at))}<small>${(approval_ms/1000).toFixed(1)}초 만에 승인</small></div>`;
      const nextCard=document.querySelectorAll('.person-card')[i+1];if(nextCard)nextCard.querySelector('button').disabled=false;
      $('#next').disabled=!mandates.every(m=>m.status==='APPROVED');audit();
    });
  });
  $('#next').onclick=()=>{if(!mandates.every(m=>m.status==='APPROVED'))return;if(reapproving)quoteScreen();else reservation();};focusTitle();
}
function resultText(){
  if(!checked)return '';
  if(!checked.available)return `${dateText()} ${trip.item.start} 예약 불가`;
  return `${dateText()} ${trip.item.start} 예약 가능 · 1인 ${money(checked.price)} · ${checked.price===trip.item.price?'가격 변동 없음':`가격 ${money(checked.price-trip.item.price)} ${checked.price>trip.item.price?'인상':'인하'}`}`;
}
function sourceChip(){return chip(`${checked.source==='live'?'실시간 조회':checked.source==='test'?'테스트용':'저장된 조회 결과'} · ${time(checked.checked_at)}`);}
function reservationBody(){return `<div class="result"><p>${esc(resultText())}</p>${sourceChip()}</div><div class="draft"><h3>판매자에게 보낼 문의 (초안 · 보내지 않음)</h3><p>안녕하세요. ${dateText()} ${esc(trip.item.start)} ${esc(trip.item.short_name)} ${trip.people.length}명 예약하려고 합니다. 지금 예약 가능한지, 비가 오면 진행하는지 알려 주세요.</p></div><button id="next" class="primary">다음</button>`;}
async function reservation(){
  stage=3;const run=++epoch;
  frame('<p class="loading" role="status">예약 가능 여부를 확인하고 있어요</p>');focusTitle();
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
function receiptHead(){return `<div class="receipt-head">${chip('모의 결제 · 실제 결제 없음')}<strong>${esc(trip.item.short_name)}</strong><small>${dateText(true)} ${esc(trip.item.start)} · ${trip.people.length}명<br>${esc(trip.item.merchant_label)}</small></div>`;}
function quoteScreen(){
  stage=4;quote=api.buildQuote(world,trip);
  const ready=quote.status==='READY';const over=quote.status==='NEEDS_REAPPROVAL';
  frame(`<div class="receipt">${receiptHead()}${quote.lines.map(l=>`<div class="receipt-line ${l.within?'':'over'}"><div>${esc(l.name)}<small>맡긴 상한 ${money(l.mandate_max)}</small></div><div><strong class="num">${money(l.amount)}</strong><small>${l.within?'맡긴 범위 안':'맡긴 범위 밖'}</small></div></div>`).join('')}<div class="total"><span>합계</span><strong class="num">${money(quote.total)}</strong></div>${ready?'<p class="muted">두 분이 맡긴 범위와 다른 항목이 없어요</p>':''}<div class="receipt-meta">${sourceChip()}</div></div>${ready?holdMarkup(`${money(quote.total)} 결제하기 (1초 누르기)`):over?`<p class="stop">${checked.price===38000&&quote.lines.some(l=>l.mandate_max===35000)?'가격이 1인 38,000원으로 바뀌었어요. 맡긴 금액보다 3,000원 많아 결제를 멈췄어요':'맡긴 범위를 벗어나 결제를 멈췄어요. 새 범위로 다시 승인해 주세요'}</p><button id="reapprove" class="primary">${money(checked.price)}으로 다시 맡기기</button><button id="cancel" class="secondary">결제 취소</button>`:`<p class="stop">${esc(quote.reasons.join(' · '))}</p><button id="cancel" class="secondary">결제 취소</button>`}`);
  if(ready){const drawnAt=performance.now(),run=epoch;bindHold($('.hold'),drawnAt,async approval_ms=>{
    $('#test-price').disabled=true;
    const approval=await api.approveQuote(world,quote,{approver_id:trip.people[0].id,approval_ms});if(run!==epoch)return;
    tokens=approval.tokens;const result=await api.executeSplit(world,quote,tokens);if(run!==epoch)return;
    if(!result.ok){audit();throw new Error(`결제를 멈췄어요 (${result.error_code})`);}confirmed=result.confirmed;complete();
  });}
  if($('#reapprove'))$('#reapprove').onclick=()=>{reapproving=true;mandateScreen(checked.price);};
  if($('#cancel'))$('#cancel').onclick=reset;focusTitle();
}
function complete(){
  stage=5;const name=id=>trip.people.find(p=>p.id===id)?.name??id;
  const url=new URL(trip.item.url,location.href);const safeUrl=url.protocol==='https:'?url.href:'#';
  frame(`<div class="receipt">${receiptHead()}${confirmed.payments.map(p=>`<div class="receipt-line"><div>${esc(name(p.person_id))}<small>승인번호 ${esc(approvalNumber(p.approval_no))}</small></div><strong class="num">${money(p.amount)}</strong></div>`).join('')}<div class="total"><span>합계</span><strong class="num">${money(confirmed.total)}</strong></div><div class="receipt-meta"><span>기록 <code>${esc(confirmed.quote_hash.slice(0,8))}</code></span><span>시각 <time>${esc(receiptTime(confirmed.paid_at))}</time></span></div></div><a class="link-button" href="${esc(safeUrl)}" target="_blank" rel="noopener noreferrer">마이리얼트립에서 예약 마무리하기</a><p class="muted">마이리얼트립은 외부 예약 기능을 열어 두지 않아서, 예약 확정은 링크에서 진행해요</p>`);focusTitle();
}
$('#reset').onclick=()=>{try{reset();}catch(e){showError(e);}};
$('#test-price').onclick=async()=>{
  if(stage<3||stage===5)return;const run=++epoch;recheckController?.abort();clearHolds();
  const result={available:true,price:38000,source:'test',checked_at:new Date().toISOString()};
  try{await api.recheck(world,trip,result);if(run!==epoch)return;checked=result;quoteScreen();}catch(e){showError(e);}
};
$('#test-merchant').onclick=async()=>{
  if(!confirmed)return;const run=epoch;
  try{const result=await api.simulateMalfunction(world,tokens[0],{merchant_id:'other:merchant',amount:confirmed.payments[0].amount});if(run!==epoch)return;
    $('#malfunction').innerHTML=result.error_code==='MERCHANT_MISMATCH'?'<p class="error">결제사가 거절했어요. 맡긴 판매처가 아니에요 (MERCHANT_MISMATCH)</p>':`<p class="error">${esc(result.error_code??'결과를 확인해 주세요')}</p>`;audit();
  }catch(e){showError(e);}
};
try{
  const [loadedTrip,loadedPlan]=await Promise.all([window.TRIPFIT_PAY_INPUT?Promise.resolve(structuredClone(window.TRIPFIT_PAY_INPUT)):fetch('./data/trip.json').then(r=>{if(!r.ok)throw new Error('일정을 불러오지 못했어요');return r.json();}),fetch('./data/plan_summary.json').then(r=>{if(!r.ok)throw new Error('일정을 불러오지 못했어요');return r.json();})]);
  input=loadedTrip;plan=loadedPlan;reset();
}catch(e){$('#flow').innerHTML=`<section class="panel"><p role="alert">${esc(e.message)}</p></section>`;}
