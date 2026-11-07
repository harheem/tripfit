import { canonicalJSON, sha256 } from './hash.js';
import { createMerchant } from './merchant.js';
import { createPay } from './pay.js';
export { fromTripFit } from './tripfit.js';

const contexts = new WeakMap();
const GENESIS = '0'.repeat(64);
const clone = value => structuredClone(value);
const money = value => Number.isSafeInteger(value) && value >= 0;
function asDate(value) {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) throw new TypeError('INVALID_DATE');
  return date;
}
function text(value) {
  if (typeof value !== 'string' || !value.trim()) throw new TypeError('INVALID_TEXT');
  return value.trim().normalize('NFC');
}
function approvalDuration(value) {
  if (!Number.isFinite(value) || value < 0) throw new TypeError('INVALID_APPROVAL_MS');
}
function scopeOf(trip) {
  return { merchant_id: trip.item.merchant_id, item_gid: trip.item.gid,
    date: trip.date, option_start: trip.item.start };
}

export function createWorld({ now, idSeed = 'tripfit' } = {}) {
  let fixed = now !== undefined && typeof now !== 'function' ? asDate(now) : null;
  let sequence = 0;
  const clock = {
    now: () => asDate(fixed ?? (typeof now === 'function' ? now() : Date.now())),
    set(value) { fixed = asDate(value); },
    advance(milliseconds) {
      if (!Number.isFinite(milliseconds)) throw new TypeError('Invalid clock increment');
      fixed = asDate(clock.now().getTime() + milliseconds);
    },
  };
  const nextId = kind => `${kind}-${String(idSeed)}-${String(++sequence).padStart(4, '0')}`;
  const entries = [];
  let queued = Promise.resolve();
  let auditSequence = 0;
  function record(actor, action, detail) {
    const content = { seq: ++auditSequence, at: clock.now().toISOString(), actor, action, detail: clone(detail) };
    queued = queued.then(async () => {
      const prev_hash = entries.at(-1)?.hash ?? GENESIS;
      const hash = await sha256(prev_hash + canonicalJSON(content));
      entries.push({ ...content, prev_hash, hash });
    });
  }
  async function flush() {
    let pending;
    do { pending = queued; await pending; } while (pending !== queued);
  }
  const mandates = new Map();
  const merchant = createMerchant({ nextId, record });
  const pay = createPay({ clock, merchant, nextId, record, flush,
    getMandate: id => clone(mandates.get(id)?.value ?? null) });
  // Synchronous operations queue their log; await audit.flush() to inspect immediately.
  const audit = { flush, get entries() { return clone(entries); } };
  const world = { clock, merchant, pay, audit };
  contexts.set(world, { record, flush, nextId, mandates, trips: new Map(), quotes: new Map() });
  return world;
}

function normalizeCheck(result, previousPrice) {
  if (!result || typeof result.available !== 'boolean' || !['live', 'snapshot', 'test'].includes(result.source)
    || typeof result.checked_at !== 'string' || !Number.isFinite(Date.parse(result.checked_at))) {
    throw new TypeError('INVALID_RECHECK');
  }
  // A sold-out option can have no advertised price. Keep its last known integer amount.
  const price = !result.available && result.price == null ? previousPrice : result.price;
  if (!money(price)) throw new TypeError('INVALID_PRICE');
  return { available: result.available, price, checked_at: result.checked_at, source: result.source };
}

export function loadTrip(world, trip) {
  const context = contexts.get(world);
  const item = trip?.item;
  const normalized = { plan_id: text(trip?.plan_id), date: text(trip?.date),
    people: trip?.people?.map(person => ({ id: text(person.id), name: text(person.name) })),
    item: { gid: text(item?.gid), url: text(item?.url), name: text(item?.name), short_name: text(item?.short_name),
      start: text(item?.start), price: item?.price, merchant_id: text(item?.merchant_id), merchant_label: text(item?.merchant_label) },
    snapshot: normalizeCheck(trip?.snapshot, item?.price) };
  if (!/^\d{4}-\d{2}-\d{2}$/.test(normalized.date)
    || !Number.isFinite(Date.parse(normalized.date)) || asDate(normalized.date).toISOString().slice(0, 10) !== normalized.date
    || !/^([01]\d|2[0-3]):[0-5]\d$/.test(normalized.item.start) || !money(item.price)
    || !normalized.people?.length || new Set(normalized.people.map(p => p.id)).size !== normalized.people.length
    || !['https:', 'http:'].includes(new URL(normalized.item.url).protocol)) throw new TypeError('INVALID_TRIP');
  context.trips.set(canonicalJSON(normalized), clone(normalized));
  world.merchant.register(normalized);
  context.record('agent', 'TRIP_LOADED', normalized);
  return normalized;
}

function getTrip(world, trip) {
  const key = canonicalJSON(trip);
  const stored = contexts.get(world).trips.get(key);
  if (!stored) throw new Error('TRIP_NOT_LOADED');
  return { key, trip: stored, scope: scopeOf(stored) };
}

export function createMandate(world, trip, person_id, { max_per_person, expires_at }) {
  const context = contexts.get(world);
  const state = getTrip(world, trip);
  if (!state.trip.people.some(p => p.id === person_id)) throw new Error('INVALID_PERSON');
  if (!money(max_per_person)) throw new TypeError('INVALID_AMOUNT');
  const expiry = asDate(expires_at).toISOString();
  if (Date.parse(expiry) <= world.clock.now().getTime()) throw new Error('EXPIRED');
  const mandate = { id: context.nextId('mandate'), person_id, merchant_id: state.scope.merchant_id,
    item_gid: state.scope.item_gid, option_start: state.scope.option_start,
    max_amount: max_per_person, expires_at: expiry, uses: 1, status: 'DRAFT' };
  context.mandates.set(mandate.id, { value: clone(mandate), tripKey: state.key, refs: [mandate], approving: false });
  context.record('user', 'MANDATE_CREATED', mandate);
  return mandate;
}

export async function approveMandate(world, mandate, { approval_ms }) {
  const context = contexts.get(world);
  try {
    const state = context.mandates.get(mandate?.id);
    if (!state || state.approving || state.value.status !== 'DRAFT'
      || canonicalJSON(mandate) !== canonicalJSON(state.value)) throw new Error('INVALID_MANDATE');
    approvalDuration(approval_ms);
    if (world.clock.now().getTime() >= Date.parse(state.value.expires_at)) throw new Error('EXPIRED');
    state.approving = true;
    try {
      const approved_at = world.clock.now().toISOString();
      const mandate_hash = await sha256(canonicalJSON({ mandate: state.value, approval_ms, approved_at }));
      if (world.clock.now().getTime() >= Date.parse(state.value.expires_at)) throw new Error('EXPIRED');
      for (const previous of context.mandates.values()) {
        if (previous.tripKey === state.tripKey && previous.value.person_id === state.value.person_id
          && previous.value.status === 'APPROVED') {
          previous.value.status = 'SUPERSEDED';
          for (const ref of previous.refs) Object.assign(ref, clone(previous.value));
          context.record('user', 'MANDATE_SUPERSEDED', { mandate_id: previous.value.id, replacement_id: state.value.id });
        }
      }
      Object.assign(state.value, { status: 'APPROVED', approved_at, mandate_hash });
      Object.assign(mandate, clone(state.value));
      if (!state.refs.includes(mandate)) state.refs.push(mandate);
      context.record('user', 'MANDATE_APPROVED', { ...state.value, approval_ms });
      return cloneApproved(state);
    } finally { state.approving = false; }
  } finally { await context.flush(); }
}

function cloneApproved(state) {
  const result = clone(state.value);
  state.refs.push(result); // Keep callers' earlier approval objects visibly SUPERSEDED.
  return result;
}

export async function recheck(world, trip, result) {
  const context = contexts.get(world);
  try {
    const { scope } = getTrip(world, trip);
    if (result?.option_start !== undefined && result.option_start !== scope.option_start) throw new Error('ITEM_UNAVAILABLE');
    const checked = normalizeCheck(result, world.merchant.lookup(scope)?.price);
    context.record('agent', 'RECHECK', { ...scope, ...checked });
    return world.merchant.update(scope, checked);
  } finally { await context.flush(); }
}

function quoteContent(world, trip, tripKey) {
  const context = contexts.get(world);
  const item = world.merchant.lookup(scopeOf(trip));
  const mandates = trip.people.map(person => [...context.mandates.values()].find(m =>
    m.tripKey === tripKey && m.value.person_id === person.id && m.value.status === 'APPROVED')?.value ?? null);
  const reasons = [];
  const lines = trip.people.map((person, index) => {
    const mandate = mandates[index];
    const within = Boolean(mandate && item.price <= mandate.max_amount
      && world.clock.now().getTime() < Date.parse(mandate.expires_at) && !world.pay.isMandateUsed(mandate.id));
    if (mandate && item.price > mandate.max_amount) {
      reasons.push(`가격이 1인 ${item.price.toLocaleString('ko-KR')}원으로 바뀌었어요. 맡긴 금액보다 ${(item.price - mandate.max_amount).toLocaleString('ko-KR')}원 많아 결제를 멈췄어요`);
    } else if (mandate && !within) {
      reasons.push(`${person.name} 님의 위임 기한이 지났거나 이미 사용했어요. 다시 맡겨 주세요`);
    }
    return { person_id: person.id, name: person.name, amount: item.price, mandate_max: mandate?.max_amount ?? null, within };
  });
  const missing = mandates.some(m => !m);
  if (missing) reasons.push('두 분 모두 결제를 맡겨야 진행할 수 있어요');
  if (!item.available) reasons.unshift('선택한 시각에 예약할 수 없어 결제를 멈췄어요');
  const status = !item.available ? 'UNAVAILABLE'
    : lines.some((line, i) => mandates[i] && !line.within) ? 'NEEDS_REAPPROVAL'
      : missing ? 'WAITING_MANDATES' : 'READY';
  const total = lines.reduce((sum, line) => sum + line.amount, 0);
  if (!money(total)) throw new TypeError('INVALID_TOTAL');
  return { content: { status, lines, total, price_source: item.source, reasons: [...new Set(reasons)] },
    mandateIds: mandates.map(m => m?.id ?? null) };
}

export function buildQuote(world, trip) {
  const context = contexts.get(world);
  const { trip: stored, key, scope } = getTrip(world, trip);
  const { content, mandateIds } = quoteContent(world, stored, key);
  const quote = { id: context.nextId('quote'), ...content };
  context.quotes.set(quote.id, { snapshot: canonicalJSON(quote), trip: stored, tripKey: key, scope,
    mandateIds, status: 'PREVIEW', approval: null });
  context.record('agent', 'QUOTE_CREATED', quote);
  return quote;
}

function quoteIsCurrent(world, quote, state) {
  if (canonicalJSON(quote) !== state.snapshot) return false;
  const current = quoteContent(world, state.trip, state.tripKey);
  return canonicalJSON({ id: quote.id, ...current.content }) === state.snapshot
    && canonicalJSON(current.mandateIds) === canonicalJSON(state.mandateIds);
}

export async function approveQuote(world, quote, { approver_id, approval_ms }) {
  const context = contexts.get(world);
  try {
    const state = context.quotes.get(quote?.id);
    if (!state || quote.status !== 'READY') throw new Error('READY_REQUIRED');
    if (state.status !== 'PREVIEW') throw new Error('QUOTE_ALREADY_APPROVED');
    if (!state.trip.people.some(p => p.id === approver_id)) throw new Error('INVALID_APPROVER');
    approvalDuration(approval_ms);
    if (!quoteIsCurrent(world, quote, state)) throw new Error('STALE_QUOTE');
    state.status = 'APPROVING';
    try {
      const approved_at = world.clock.now().toISOString();
      const quote_hash = await sha256(canonicalJSON({ quote, approver_id, approval_ms, approved_at }));
      if (!quoteIsCurrent(world, quote, state)) throw new Error('STALE_QUOTE');
      context.record('user', 'QUOTE_APPROVED', { quote_id: quote.id, approver_id, approval_ms, approved_at, quote_hash });
      const tokens = quote.lines.map((line, index) => {
        const mandate = context.mandates.get(state.mandateIds[index]).value;
        return world.pay.issue({ person_id: line.person_id, merchant_id: mandate.merchant_id, amount_max: line.amount,
          expires_at: new Date(Math.min(Date.parse(mandate.expires_at), Date.parse(approved_at) + 30 * 60 * 1000)).toISOString(),
          mandate_id: mandate.id, mandate_hash: mandate.mandate_hash, quote_hash, scope: state.scope });
      });
      state.approval = { quote_hash, tokens: clone(tokens) };
      state.status = 'APPROVED';
      return { quote_hash, tokens };
    } catch (error) { state.status = 'PREVIEW'; throw error; }
  } finally { await context.flush(); }
}

function agentCheck(world, quote, state, token, index) {
  const stored = state.approval.tokens[index];
  const line = quote.lines[index];
  if (token?.merchant_id !== state.scope.merchant_id || token?.merchant_id !== stored.merchant_id) return 'MERCHANT_MISMATCH';
  if (!money(token?.amount_max) || line.amount > token.amount_max || token.amount_max !== stored.amount_max) return 'AMOUNT_OVER_LIMIT';
  if (!Number.isFinite(Date.parse(token?.expires_at)) || token.expires_at !== stored.expires_at
    || world.clock.now().getTime() >= Date.parse(stored.expires_at)) return 'EXPIRED';
  if (token?.id !== stored.id || token?.person_id !== line.person_id || token?.uses_left !== 1
    || canonicalJSON(token) !== canonicalJSON(stored)) return 'USED';
  if (state.snapshot !== canonicalJSON(quote)) return 'ITEM_UNAVAILABLE';
  return null;
}

export async function executeSplit(world, quote, tokens) {
  const context = contexts.get(world);
  const state = context.quotes.get(quote?.id);
  const payments = [];
  const fail = async (layer, error_code, person_id) => {
    for (const payment of payments) world.pay.void(payment.approval_no);
    const result = { ok: false, layer, error_code, person_id: person_id ?? null };
    context.record('agent', 'SPLIT_RESULT', result);
    await context.flush();
    return result;
  };
  if (!state?.approval || state.status !== 'APPROVED') return fail('agent', 'USED', quote?.lines?.[0]?.person_id);
  if (canonicalJSON(quote) !== state.snapshot) return fail('agent', 'ITEM_UNAVAILABLE', state.trip.people[0].id);
  if (!Array.isArray(tokens) || tokens.length !== quote.lines.length) return fail('agent', 'USED', state.trip.people[0].id);
  // Retain exactly the checked input across asynchronous network/audit work.
  quote = clone(quote);
  tokens = clone(tokens);
  // Lock before the first await. A second split cannot void this split's authorizations.
  state.status = 'EXECUTING';
  let person_id = quote.lines[0].person_id;
  try {
    for (const [index, line] of quote.lines.entries()) {
      person_id = line.person_id;
      const token = tokens[index];
      context.record('agent', 'PAYMENT_ATTEMPT', { quote_id: quote.id, token_id: token?.id ?? null, person_id });
      const error_code = agentCheck(world, quote, state, token, index);
      if (error_code) {
        context.record('agent', 'PAYMENT_RESULT', { ok: false, layer: 'agent', error_code, person_id });
        return await fail('agent', error_code, person_id);
      }
      const result = await world.pay.charge(token, { merchant_id: state.scope.merchant_id, amount: line.amount });
      context.record('agent', 'PAYMENT_RESULT', { ...result, person_id });
      if (!result.ok) return await fail('network', result.error_code, person_id);
      payments.push({ person_id, approval_no: result.confirmed.approval_no, amount: line.amount });
    }
    const row = world.merchant.requestBooking({ scope: state.scope, payments,
      quote_hash: state.approval.quote_hash,
      mandate_hashes: state.mandateIds.map(id => context.mandates.get(id).value.mandate_hash) });
    world.pay.confirm(payments.map(p => p.approval_no));
    const result = { ok: true, confirmed: { payments, total: quote.total, quote_hash: state.approval.quote_hash,
      booking_request_id: row.booking_request_id, paid_at: world.clock.now().toISOString() } };
    state.status = 'PAID';
    context.record('agent', 'SPLIT_RESULT', result);
    await context.flush();
    return result;
  } catch (error) {
    return await fail('network', ['MERCHANT_MISMATCH', 'AMOUNT_OVER_LIMIT', 'EXPIRED', 'USED', 'ITEM_UNAVAILABLE'].includes(error.message)
      ? error.message : 'ITEM_UNAVAILABLE', person_id);
  } finally {
    if (state.status === 'EXECUTING') state.status = 'FAILED';
  }
}

export async function simulateMalfunction(world, token, { merchant_id, amount }) {
  const context = contexts.get(world);
  context.record('agent', 'MALFUNCTION_ATTEMPT', { token_id: token?.id ?? null, merchant_id, amount });
  try { return await world.pay.charge(token, { merchant_id, amount }); }
  finally { await context.flush(); }
}
export function supplierView(world) { return world.merchant.dashboard(); }
export function auditLog(world) { return world.audit.entries; }
export async function verifyChain(entries) {
  if (!Array.isArray(entries)) return false;
  let previous = GENESIS;
  try {
    for (let index = 0; index < entries.length; index++) {
      const { hash, prev_hash, ...content } = entries[index];
      if (content.seq !== index + 1 || prev_hash !== previous || !['user', 'agent', 'network', 'merchant'].includes(content.actor)) return false;
      if (await sha256(previous + canonicalJSON(content)) !== hash) return false;
      previous = hash;
    }
    return true;
  } catch { return false; }
}
