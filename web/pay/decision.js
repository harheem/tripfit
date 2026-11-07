export const choices=['결제 진행','결제 멈추고 다시 묻기'];
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const percent=v=>`${Math.round(v*100)}%`;
const score=v=>typeof v==='number'&&Number.isFinite(v)&&v>=0&&v<=1;
export function rulesDecision(data){
  const over=data.lines.find(l=>l.mandate_max!==null&&l.amount>l.mandate_max);
  const failed=data.checks.find(c=>!c.ok);
  const ready=!failed&&data.lines.every(l=>l.mandate_max!==null&&l.amount<=l.mandate_max)&&data.merchant.expected===data.merchant.actual;
  const reason=over?`방금 조회한 가격 ${over.amount.toLocaleString('ko-KR')}원이 맡긴 ${over.mandate_max.toLocaleString('ko-KR')}원을 넘었어요`:
    data.merchant.expected!==data.merchant.actual?'결제 요청이 맡긴 곳이 아닌 다른 판매처에서 왔어요':failed?.detail??'모든 검사가 맞고 맡긴 범위 안이에요';
  return {provider:'rules',value:choices[ready?0:1],status:'answered',final:ready?'proceed':'stop',reason,override_reason:null,fallback_reason:'서버 연결 실패',ms:0};
}
export function validDecision(data){
  return data&&['rules','articul8-bivia'].includes(data.provider)&&['proceed','stop'].includes(data.final)
    &&((data.status==='answered'&&choices.includes(data.value))||(data.status==='abstained'&&data.value===null&&data.final==='stop'))
    &&(data.final!=='proceed'||data.value===choices[0])&&typeof data.reason==='string';
}
export function decisionLog(d){
  const name=d.provider==='articul8-bivia'?'ARTICUL8 Bivia':'규칙';
  const outcome=d.override_reason?'진행 제안, 엔진이 결제 멈춤':d.status==='abstained'?'판단 보류':d.final==='proceed'?'결제 진행':'결제 멈춤';
  return `${name} 판단: ${outcome}${d.provider==='articul8-bivia'&&score(d.probability)?` ${percent(d.probability)}`:''}, ${Number(d.ms)||0}ms`;
}
export function decisionMarkup(d){
  if(!d)return '<section class="b decision decision-loading" role="status"><span class="label">마지막 판단</span><h3><i class="decision-pulse" aria-hidden="true"></i>Articul8 Bivia가 마지막으로 판단하는 중</h3></section>';
  const abstained=d.status==='abstained',stop=d.final!=='proceed';
  const title=abstained?'확신이 없어서 결정하지 않았어요':stop?'결제를 막았어요':'결제해도 돼요';
  const source=d.provider==='articul8-bivia'?`Articul8 Bivia ${d.model}, ${Number(d.ms)||0}ms`:'규칙 판단';
  const distribution=d.provider==='articul8-bivia'&&d.distribution;
  const bars=distribution&&choices.every(c=>score(distribution[c]))?`<div class="decision-bars">${choices.map(c=>`<div class="decision-bar"><div><span>${esc(c)}</span><b>${percent(distribution[c])}</b></div><div class="decision-track" role="meter" aria-label="${esc(c)}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(distribution[c]*100)}"><i style="--fill:${distribution[c]*100}%"></i></div></div>`).join('')}</div>`:'';
  return `<section class="b decision ${abstained?'butter decision-abstained':stop?'red decision-stop':'decision-pass'}" role="${stop?'alert':'status'}"><span class="label">마지막 판단</span>${stop&&!abstained?'<span class="stop-stamp" aria-hidden="true">STOP</span>':''}<h3>${title}</h3><p>${esc(d.reason)}</p>${d.override_reason?'<p class="decision-override">Bivia의 진행 제안보다 엔진의 범위 검사를 먼저 적용했어요</p>':''}${d.provider==='articul8-bivia'&&score(d.probability)?`<strong class="decision-confidence">${percent(d.probability)}<small>${abstained?'제공자 응답 확률':d.value===choices[0]?'진행 선택 확률':'멈춤 선택 확률'}</small></strong>`:''}${bars}<span class="pill">${esc(source)}</span>${d.provider==='rules'?`<small class="decision-fallback">${esc(d.fallback_reason??'규칙으로 확인했어요')}</small>`:''}</section>`;
}
