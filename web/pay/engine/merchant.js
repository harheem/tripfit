// In-memory supplier records. Registration never overwrites a later recheck.
const keyOf = ({ merchant_id, item_gid, date, option_start }) =>
  JSON.stringify([merchant_id, item_gid, date, option_start]);

export function createMerchant({ nextId, record }) {
  const items = new Map();
  const requests = [];
  return {
    register(trip) {
      const scope = { merchant_id: trip.item.merchant_id, item_gid: trip.item.gid,
        date: trip.date, option_start: trip.item.start };
      if (!items.has(keyOf(scope))) {
        items.set(keyOf(scope), { ...scope, item: structuredClone(trip.item), ...trip.snapshot });
        record('merchant', 'ITEM_REGISTERED', items.get(keyOf(scope)));
      }
    },
    lookup(scope) { return structuredClone(items.get(keyOf(scope)) ?? null); },
    update(scope, result) {
      const item = items.get(keyOf(scope));
      if (!item) throw new Error('ITEM_UNAVAILABLE');
      Object.assign(item, structuredClone(result));
      record('merchant', 'ITEM_RECHECKED', { ...scope, ...result });
      return structuredClone(item);
    },
    requestBooking({ scope, payments, quote_hash, mandate_hashes }) {
      const item = items.get(keyOf(scope));
      if (!item?.available || payments.some(p => p.amount !== item.price)) {
        throw new Error('ITEM_UNAVAILABLE');
      }
      if (requests.some(row => row.quote_hash === quote_hash)) throw new Error('USED');
      const row = { booking_request_id: nextId('booking'), item: structuredClone(item.item),
        option_start: scope.option_start, people_count: payments.length,
        payments: structuredClone(payments), quote_hash, mandate_hashes: [...mandate_hashes],
        status: 'REQUESTED' };
      row.item.price = item.price;
      requests.push(row);
      record('merchant', 'BOOKING_REQUESTED', row);
      return structuredClone(row);
    },
    dashboard() { return structuredClone(requests); },
  };
}
