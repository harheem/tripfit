import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {
  createWorld, fromTripFit, loadTrip, createMandate, approveMandate, revokeMandate, recheck, buildQuote,
  approveQuote, executeSplit, simulateMalfunction, supplierView, auditLog, verifyChain,
} from '../../web/pay/engine/engine.js';
import { canonicalJSON, sha256 } from '../../web/pay/engine/hash.js';
import { TRIP, NORMAL_RECHECK, PRICE_INCREASE, UNAVAILABLE } from '../../web/pay/engine/fixtures.js';

const NOW = '2026-11-07T04:00:00Z';
const EXPIRES = '2026-11-07T10:00:00Z';
function setup() {
  const world = createWorld({ now: NOW, idSeed: 'test' });
  return { world, trip: loadTrip(world, TRIP) };
}
async function delegate(world, trip, person_id, max_per_person = 35000, expires_at = EXPIRES) {
  const mandate = createMandate(world, trip, person_id, { max_per_person, expires_at });
  return approveMandate(world, mandate, { approval_ms: 1000 });
}
async function ready() {
  const { world, trip } = setup();
  const mandates = [];
  for (const person of trip.people) mandates.push(await delegate(world, trip, person.id));
  await recheck(world, trip, NORMAL_RECHECK);
  const quote = buildQuote(world, trip);
  const approval = await approveQuote(world, quote, { approver_id: 'jimin', approval_ms: 1000 });
  return { world, trip, mandates, quote, ...approval };
}

function tripfitInput() {
  const context = { window: {} };
  vm.runInNewContext(fs.readFileSync(new URL('../../web/demo_data.js', import.meta.url), 'utf8'), context);
  const demo = JSON.parse(JSON.stringify(context.window.DEMO));
  return { pay: demo.pay, plan: demo.whatif.chosen.plan, people: demo.people,
    snapshot: JSON.parse(fs.readFileSync(new URL('../../data/mrt_snapshot.json', import.meta.url), 'utf8')) };
}

test('fromTripFit reads the actual sibling data and produces PRD §2 exactly', () => {
  assert.deepEqual(fromTripFit(tripfitInput()), TRIP);
});

test('adapter maps unknown names and reads the chosen snapshot option, not product availability', () => {
  const input = tripfitInput();
  input.people = [{ name: '민수' }, { name: '유나' }];
  const option = input.snapshot.picked.find(p => p.gid === '3828508').options.find(o => o.start === '15:00');
  Object.assign(option, { available: false, price: 38000 });
  const trip = fromTripFit(input);
  assert.deepEqual(trip.people.map(p => p.id), ['p1', 'p2']);
  assert.equal(trip.snapshot.available, false);
  assert.equal(trip.snapshot.price, 38000);
  input.snapshot.picked[0].options = [];
  assert.throws(() => fromTripFit(input), /INVALID_TRIPFIT_INPUT/);
});

test('normal split: two mandates, READY 70,000, two approvals and one supplier request', async () => {
  const { world, mandates, quote, tokens, quote_hash } = await ready();
  assert.equal(quote.status, 'READY');
  assert.equal(quote.total, 70000);
  assert.ok(quote.lines.every(line => line.within));
  assert.equal(quote.price_source, 'test');
  assert.equal(tokens.length, 2);
  assert.deepEqual(tokens.map(t => t.amount_max), [35000, 35000]);
  const result = await executeSplit(world, quote, tokens);
  assert.equal(result.ok, true);
  assert.equal(result.confirmed.total, 70000);
  assert.equal(new Set(result.confirmed.payments.map(p => p.approval_no)).size, 2);
  assert.equal(result.confirmed.quote_hash, quote_hash);
  const [row] = supplierView(world);
  assert.equal(supplierView(world).length, 1);
  assert.equal(row.people_count, 2);
  assert.deepEqual(row.payments, result.confirmed.payments);
  assert.equal(row.quote_hash, quote_hash);
  assert.deepEqual(row.mandate_hashes, mandates.map(m => m.mandate_hash));
  assert.equal(row.booking_request_id, result.confirmed.booking_request_id);
  assert.equal(row.status, 'REQUESTED');
  assert.ok(world.pay.payments.every(p => p.status === 'CONFIRMED'));
});

test('one approval stays WAITING_MANDATES and cannot approve a quote', async () => {
  const { world, trip } = setup();
  await delegate(world, trip, 'jimin');
  await recheck(world, trip, NORMAL_RECHECK);
  const quote = buildQuote(world, trip);
  assert.equal(quote.status, 'WAITING_MANDATES');
  assert.equal(quote.lines[1].within, false);
  await assert.rejects(approveQuote(world, quote, { approver_id: 'jimin', approval_ms: 1000 }), /READY_REQUIRED/);
  assert.equal(world.pay.tokens.length, 0);
});

test('38,000 stops both lines; renewed mandates supersede the originals and yield 76,000', async () => {
  const { world, trip, mandates } = await ready();
  await recheck(world, trip, PRICE_INCREASE);
  const blocked = buildQuote(world, trip);
  assert.equal(blocked.status, 'NEEDS_REAPPROVAL');
  assert.deepEqual(blocked.lines.map(l => l.within), [false, false]);
  assert.ok(blocked.reasons.includes('가격이 1인 38,000원으로 바뀌었어요. 맡긴 금액보다 3,000원 많아 결제를 멈췄어요'));
  for (const person of trip.people) await delegate(world, trip, person.id, 38000);
  assert.deepEqual(mandates.map(m => m.status), ['SUPERSEDED', 'SUPERSEDED']);
  const quote = buildQuote(world, trip);
  assert.equal(quote.status, 'READY');
  assert.equal(quote.total, 76000);
  const { tokens } = await approveQuote(world, quote, { approver_id: 'jimin', approval_ms: 1000 });
  assert.equal((await executeSplit(world, quote, tokens)).ok, true);
});

test('unavailable recheck, including sold-out null price, stops payment', async () => {
  const { world, trip } = await ready();
  for (const result of [UNAVAILABLE, { ...UNAVAILABLE, price: null }]) {
    await recheck(world, trip, result);
    const quote = buildQuote(world, trip);
    assert.equal(quote.status, 'UNAVAILABLE');
    assert.equal(quote.total, 70000);
    await assert.rejects(approveQuote(world, quote, { approver_id: 'jimin', approval_ms: 1000 }), /READY_REQUIRED/);
  }
});

test('malfunction bypasses agent and network merchant/amount errors precede USED after payment', async () => {
  const { world, quote, tokens } = await ready();
  await executeSplit(world, quote, tokens);
  for (const [merchant_id, amount, error_code] of [
    ['other:merchant', 99999, 'MERCHANT_MISMATCH'], ['mrt:3828508', 35001, 'AMOUNT_OVER_LIMIT'],
    ['mrt:3828508', 35000, 'USED'],
  ]) {
    assert.deepEqual(await simulateMalfunction(world, tokens[0], { merchant_id, amount }), { ok: false, layer: 'network', error_code });
  }
  assert.equal(supplierView(world).length, 1);
});

for (const [field, value, code] of [['merchant_id', 'evil', 'MERCHANT_MISMATCH'], ['amount_max', 999999, 'AMOUNT_OVER_LIMIT'],
  ['expires_at', '2099-01-01T00:00:00Z', 'EXPIRED'], ['person_id', 'seoyeon', 'USED'], ['id', 'invented', 'USED']]) {
  test(`forged token ${field} is blocked by agent`, async () => {
    const { world, quote, tokens } = await ready();
    tokens[0][field] = value;
    assert.deepEqual(await executeSplit(world, quote, tokens), { ok: false, layer: 'agent', error_code: code, person_id: 'jimin' });
    assert.equal(world.pay.payments.length, 0);
    assert.equal(supplierView(world).length, 0);
  });
}

test('second network rejection voids first authorization and never requests a booking', async () => {
  const { world, trip, quote, tokens } = await ready();
  const charge = world.pay.charge;
  let calls = 0;
  world.pay.charge = async (...args) => {
    if (++calls === 2) await recheck(world, trip, UNAVAILABLE);
    return charge(...args);
  };
  assert.deepEqual(await executeSplit(world, quote, tokens), {
    ok: false, layer: 'network', error_code: 'ITEM_UNAVAILABLE', person_id: 'seoyeon',
  });
  assert.equal(world.pay.payments.length, 1);
  assert.equal(world.pay.payments[0].status, 'VOIDED');
  assert.equal(supplierView(world).length, 0);
  assert.ok(auditLog(world).some(e => e.action === 'PAYMENT_VOIDED'));
});

test('31 minutes expires both agent and network grants, before USED or unavailable', async () => {
  const { world, trip, quote, tokens } = await ready();
  world.clock.advance(31 * 60 * 1000);
  await recheck(world, trip, UNAVAILABLE);
  assert.equal((await executeSplit(world, quote, tokens)).error_code, 'EXPIRED');
  assert.deepEqual(await simulateMalfunction(world, tokens[0], { merchant_id: 'mrt:3828508', amount: 35000 }), {
    ok: false, layer: 'network', error_code: 'EXPIRED',
  });
});

test('shorter mandate deadline wins over token 30-minute lifetime', async () => {
  const { world, trip } = setup();
  const expires = '2026-11-07T04:10:00.000Z';
  for (const p of trip.people) await delegate(world, trip, p.id, 35000, expires);
  const quote = buildQuote(world, trip);
  const { tokens } = await approveQuote(world, quote, { approver_id: 'jimin', approval_ms: 1000 });
  assert.ok(tokens.every(t => t.expires_at === expires));
  world.clock.advance(10 * 60 * 1000);
  assert.equal((await executeSplit(world, quote, tokens)).error_code, 'EXPIRED');
});

test('audit chain covers every stage and detects tampering', async () => {
  const { world, trip, quote, tokens } = await ready();
  await executeSplit(world, quote, tokens);
  await simulateMalfunction(world, tokens[0], { merchant_id: 'evil', amount: 35000 });
  await delegate(world, trip, 'jimin', 38000);
  const entries = auditLog(world);
  assert.equal(await verifyChain(entries), true);
  for (const action of ['TRIP_LOADED', 'MANDATE_CREATED', 'MANDATE_APPROVED', 'MANDATE_SUPERSEDED', 'RECHECK',
    'QUOTE_CREATED', 'QUOTE_APPROVED', 'TOKEN_ISSUED', 'PAYMENT_ATTEMPT', 'PAYMENT_RESULT', 'BOOKING_REQUESTED', 'MALFUNCTION_ATTEMPT']) {
    assert.ok(entries.some(e => e.action === action), action);
  }
  assert.equal(entries.find(e => e.action === 'RECHECK').detail.source, 'test');
  assert.deepEqual(new Set(entries.map(e => e.actor)), new Set(['user', 'agent', 'network', 'merchant']));
  entries[2].detail.person_id = 'tampered';
  assert.equal(await verifyChain(entries), false);
  assert.equal(await verifyChain(auditLog(world)), true);
});

test('synchronous logs can be flushed, and clocks/IDs are injectable', async () => {
  const a = setup(), b = setup();
  assert.deepEqual(createMandate(a.world, a.trip, 'jimin', { max_per_person: 35000, expires_at: EXPIRES }),
    createMandate(b.world, b.trip, 'jimin', { max_per_person: 35000, expires_at: EXPIRES }));
  await a.world.audit.flush();
  assert.equal(auditLog(a.world).at(-1).action, 'MANDATE_CREATED');
  assert.equal(await verifyChain(auditLog(a.world)), true);
  let now = Date.parse(NOW);
  const world = createWorld({ now: () => now });
  now += 1000;
  assert.equal(world.clock.now().getTime(), now);
});

test('hashes bind normalized mandate/quote, measured approval and approval time', async () => {
  const { world, trip } = setup();
  const draft = createMandate(world, trip, 'jimin', { max_per_person: 35000, expires_at: EXPIRES });
  const snapshot = structuredClone(draft);
  const approved_at = world.clock.now().toISOString();
  const approved = await approveMandate(world, draft, { approval_ms: 1000 });
  assert.equal(approved.mandate_hash, await sha256(canonicalJSON({ mandate: snapshot, approval_ms: 1000, approved_at })));
  await delegate(world, trip, 'seoyeon');
  const quote = buildQuote(world, trip);
  const approval = await approveQuote(world, quote, { approver_id: 'jimin', approval_ms: 1234 });
  assert.equal(approval.quote_hash, await sha256(canonicalJSON({ quote, approver_id: 'jimin', approval_ms: 1234, approved_at })));
});

test('forged mandate and forged or stale quote never issue tokens', async () => {
  const { world, trip } = setup();
  const draft = createMandate(world, trip, 'jimin', { max_per_person: 35000, expires_at: EXPIRES });
  draft.max_amount = 99999;
  await assert.rejects(approveMandate(world, draft, { approval_ms: 1000 }), /INVALID_MANDATE/);
  for (const p of trip.people) await delegate(world, trip, p.id);
  const forged = buildQuote(world, trip);
  forged.total = 1;
  await assert.rejects(approveQuote(world, forged, { approver_id: 'jimin', approval_ms: 1000 }), /STALE_QUOTE/);
  const stale = buildQuote(world, trip);
  await recheck(world, trip, PRICE_INCREASE);
  await assert.rejects(approveQuote(world, stale, { approver_id: 'jimin', approval_ms: 1000 }), /STALE_QUOTE/);
  assert.equal(world.pay.tokens.length, 0);
});

test('network checks fresh supplier price and superseded mandates independently', async () => {
  const { world, trip, tokens } = await ready();
  await recheck(world, trip, PRICE_INCREASE);
  assert.equal((await simulateMalfunction(world, { ...tokens[0], amount_max: 999999 }, {
    merchant_id: 'mrt:3828508', amount: 38000,
  })).error_code, 'AMOUNT_OVER_LIMIT');
  await recheck(world, trip, NORMAL_RECHECK);
  await delegate(world, trip, 'jimin');
  assert.equal((await simulateMalfunction(world, tokens[0], { merchant_id: 'mrt:3828508', amount: 35000 })).error_code, 'USED');
});

test('concurrent splits and approvals cannot double-spend or duplicate bookings', async () => {
  const { world, trip, quote, tokens } = await ready();
  const other = buildQuote(world, trip);
  const approvals = await Promise.allSettled([1, 2].map(() => approveQuote(world, other, { approver_id: 'jimin', approval_ms: 1000 })));
  assert.equal(approvals.filter(r => r.status === 'fulfilled').length, 1);
  const results = await Promise.all([executeSplit(world, quote, tokens), executeSplit(world, quote, tokens)]);
  assert.equal(results.filter(r => r.ok).length, 1);
  assert.equal(supplierView(world).length, 1);
  const second = await executeSplit(world, other, approvals.find(r => r.status === 'fulfilled').value.tokens);
  assert.equal(second.ok, false);
  assert.equal(second.layer, 'network');
  assert.equal(second.error_code, 'USED');
  assert.equal(supplierView(world).length, 1);
});

test('invalid fractional/negative amounts and mismatched option time are rejected', async () => {
  const { world, trip } = setup();
  for (const amount of [35000.1, -1, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1]) {
    assert.throws(() => createMandate(world, trip, 'jimin', { max_per_person: amount, expires_at: EXPIRES }), /INVALID_AMOUNT/);
    await assert.rejects(recheck(world, trip, { ...NORMAL_RECHECK, price: amount }), /INVALID_PRICE/);
  }
  await assert.rejects(recheck(world, trip, { ...NORMAL_RECHECK, option_start: '10:00' }), /ITEM_UNAVAILABLE/);
  const invalid = structuredClone(TRIP);
  invalid.people[1].id = 'jimin';
  assert.throws(() => loadTrip(world, invalid), /INVALID_TRIP/);
});

test('caller mutations during asynchronous settlement cannot change the approved receipt', async () => {
  const { world, quote, tokens, quote_hash } = await ready();
  const pending = executeSplit(world, quote, tokens);
  quote.total = 1;
  quote.lines[0].amount = 1;
  tokens[1].merchant_id = 'changed-after-call';
  const result = await pending;
  assert.equal(result.ok, true);
  assert.equal(result.confirmed.total, 70000);
  assert.deepEqual(result.confirmed.payments.map(p => p.amount), [35000, 35000]);
  assert.equal(result.confirmed.quote_hash, quote_hash);
});

test('second agent rejection also voids the first payment', async () => {
  const { world, quote, tokens } = await ready();
  tokens[1].amount_max = 99999;
  const result = await executeSplit(world, quote, tokens);
  assert.deepEqual(result, { ok: false, layer: 'agent', error_code: 'AMOUNT_OVER_LIMIT', person_id: 'seoyeon' });
  assert.equal(world.pay.payments[0].status, 'VOIDED');
  assert.equal(supplierView(world).length, 0);
});

test('network exception during second charge voids first payment', async () => {
  const { world, quote, tokens } = await ready();
  const charge = world.pay.charge;
  let calls = 0;
  world.pay.charge = (...args) => {
    if (++calls === 2) throw new Error('mock transport failure');
    return charge(...args);
  };
  const result = await executeSplit(world, quote, tokens);
  assert.equal(result.ok, false);
  assert.equal(result.layer, 'network');
  assert.equal(result.person_id, 'seoyeon');
  assert.equal(world.pay.payments[0].status, 'VOIDED');
  assert.equal(supplierView(world).length, 0);
});


test('revocation records the owner, updates references and blocks quote approval', async () => {
  const { world, trip, mandates } = await ready();
  const preview = buildQuote(world, trip);
  await revokeMandate(world, mandates[0].id, 'jimin');
  assert.equal(mandates[0].status, 'REVOKED');
  assert.equal(buildQuote(world, trip).status, 'WAITING_MANDATES');
  await assert.rejects(approveQuote(world, preview, { approver_id: 'jimin', approval_ms: 1000 }), /MANDATE_REVOKED/);
  assert.ok(auditLog(world).some(e => e.action === 'MANDATE_REVOKED' && e.detail.by === 'jimin'));
  assert.equal(await verifyChain(auditLog(world)), true);
});

test('revocation after token issuance blocks agent and independent network charges', async () => {
  const { world, mandates, quote, tokens } = await ready();
  await revokeMandate(world, mandates[0].id, 'jimin');
  assert.equal((await executeSplit(world, quote, tokens)).error_code, 'MANDATE_REVOKED');
  assert.equal((await simulateMalfunction(world, tokens[0], { merchant_id: 'mrt:3828508', amount: 35000 })).error_code, 'MANDATE_REVOKED');
  assert.throws(() => world.pay.issue({ mandate_id: mandates[0].id }), /MANDATE_REVOKED/);
  assert.equal(world.pay.payments.length, 0);
});

test('only the owner may revoke, and fresh human approval restores payment', async () => {
  const { world, trip, mandates } = await ready();
  await assert.rejects(revokeMandate(world, mandates[0].id, 'seoyeon'), /INVALID_PERSON/);
  assert.equal(mandates[0].status, 'APPROVED');
  await revokeMandate(world, mandates[0].id, 'jimin');
  await delegate(world, trip, 'jimin');
  const quote = buildQuote(world, trip);
  const { tokens } = await approveQuote(world, quote, { approver_id: 'jimin', approval_ms: 1000 });
  assert.equal((await executeSplit(world, quote, tokens)).ok, true);
});

test('revocation while mandate approval hashes cannot resurrect it', async () => {
  const { world, trip } = setup();
  const draft = createMandate(world, trip, 'jimin', { max_per_person: 35000, expires_at: EXPIRES });
  const pending = approveMandate(world, draft, { approval_ms: 1000 });
  await revokeMandate(world, draft.id, 'jimin');
  await assert.rejects(pending, /MANDATE_REVOKED/);
  assert.equal(draft.status, 'REVOKED');
});

test('second owner revoking during split voids the first authorization', async () => {
  const { world, mandates, quote, tokens } = await ready();
  const charge = world.pay.charge;
  let calls = 0;
  world.pay.charge = async (...args) => {
    if (++calls === 2) await revokeMandate(world, mandates[1].id, 'seoyeon');
    return charge(...args);
  };
  assert.equal((await executeSplit(world, quote, tokens)).error_code, 'MANDATE_REVOKED');
  assert.equal(world.pay.payments[0].status, 'VOIDED');
  assert.equal(supplierView(world).length, 0);
});
