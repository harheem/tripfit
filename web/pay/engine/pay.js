// Mock payment network: all grants, mandate usage and settlements live here.
// Caller-supplied token fields can restrict a grant, but cannot enlarge it.
export function createPay({ clock, merchant, getMandate, nextId, record, flush }) {
  const grants = new Map();
  const usedMandates = new Set();
  const payments = new Map();

  function issue({ person_id, merchant_id, amount_max, expires_at, mandate_id, mandate_hash, quote_hash, scope }) {
    const token = { id: nextId('token'), person_id, merchant_id, amount_max, expires_at, uses_left: 1 };
    grants.set(token.id, { token: structuredClone(token), mandate_id, mandate_hash, quote_hash,
      scope: structuredClone(scope) });
    record('network', 'TOKEN_ISSUED', { ...token, mandate_id, mandate_hash, quote_hash });
    return structuredClone(token);
  }

  function check(token, { merchant_id, amount }) {
    const grant = grants.get(token?.id);
    const stored = grant?.token;
    const mandate = grant ? getMandate(grant.mandate_id) : null;
    const item = grant ? merchant.lookup(grant.scope) : null;
    const now = clock.now().getTime();
    // Deliberate precedence, including already-spent and forged tokens.
    if (merchant_id !== token?.merchant_id || (stored && merchant_id !== stored.merchant_id)
      || (mandate && merchant_id !== mandate.merchant_id) || (item && merchant_id !== item.merchant_id)) {
      return 'MERCHANT_MISMATCH';
    }
    if (!Number.isSafeInteger(amount) || amount < 0 || !Number.isSafeInteger(token?.amount_max)
      || amount > token.amount_max || (stored && amount > stored.amount_max)
      || (mandate && amount > mandate.max_amount) || (item && amount !== item.price)) {
      return 'AMOUNT_OVER_LIMIT';
    }
    if (!Number.isFinite(Date.parse(token?.expires_at)) || now >= Date.parse(token.expires_at)
      || (stored && now >= Date.parse(stored.expires_at)) || (mandate && now >= Date.parse(mandate.expires_at))) {
      return 'EXPIRED';
    }
    if (!stored || token.uses_left !== 1 || stored.uses_left !== 1 || usedMandates.has(grant.mandate_id)
      || !mandate || mandate.status !== 'APPROVED' || mandate.uses !== 1
      || mandate.mandate_hash !== grant.mandate_hash || token.person_id !== stored.person_id) {
      return 'USED';
    }
    if (!item?.available || mandate.item_gid !== grant.scope.item_gid
      || mandate.option_start !== grant.scope.option_start || mandate.person_id !== stored.person_id) {
      return 'ITEM_UNAVAILABLE';
    }
    return null;
  }

  async function charge(token, { merchant_id, amount }) {
    record('network', 'PAYMENT_ATTEMPT', { token_id: token?.id ?? null, merchant_id, amount });
    const error_code = check(token, { merchant_id, amount });
    let result;
    if (error_code) {
      result = { ok: false, layer: 'network', error_code };
    } else {
      // Validation and consumption are synchronous, so concurrent calls cannot reuse a mandate.
      const grant = grants.get(token.id);
      grant.token.uses_left = 0;
      usedMandates.add(grant.mandate_id);
      const payment = { person_id: grant.token.person_id, approval_no: nextId('approval'), amount,
        token_id: token.id, mandate_id: grant.mandate_id, quote_hash: grant.quote_hash,
        paid_at: clock.now().toISOString(), status: 'AUTHORIZED' };
      payments.set(payment.approval_no, payment);
      result = { ok: true, confirmed: structuredClone(payment) };
    }
    record('network', 'PAYMENT_RESULT', result);
    await flush();
    return result;
  }

  function voidPayment(approval_no) {
    const payment = payments.get(approval_no);
    if (payment && payment.status !== 'VOIDED') {
      payment.status = 'VOIDED';
      record('network', 'PAYMENT_VOIDED', payment);
    }
  }

  function confirm(approval_nos) {
    for (const no of approval_nos) {
      const payment = payments.get(no);
      if (payment?.status !== 'AUTHORIZED') throw new Error('USED');
    }
    for (const no of approval_nos) {
      const payment = payments.get(no);
      payment.status = 'CONFIRMED';
      record('network', 'PAYMENT_CONFIRMED', payment);
    }
  }

  return { issue, charge, void: voidPayment, confirm,
    isMandateUsed: id => usedMandates.has(id),
    get tokens() { return Array.from(grants.values(), grant => structuredClone(grant.token)); },
    get payments() { return structuredClone([...payments.values()]); },
  };
}
