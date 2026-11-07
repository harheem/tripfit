// Pure adapter: callers supply TripFit data; this module never reads files or fetches.
export function fromTripFit({ pay, plan, people, snapshot }) {
  const stop = plan?.stops?.find(s => s.id === 'mrt_3828508_1500' && s.mrt)
    ?? plan?.stops?.find(s => s.mrt?.name === pay?.item);
  const product = stop?.mrt;
  const picked = snapshot?.picked?.find(p => String(p.gid) === String(product?.gid));
  const option = picked?.options?.find(o => o.start === product?.start);
  if (!product || !option || !Array.isArray(people) || people.length !== pay?.people
    || people.length === 0 || pay.item !== product.name || !Number.isSafeInteger(pay.price) || pay.price < 0
    || typeof option.available !== 'boolean' || !Number.isFinite(Date.parse(snapshot.fetchedAt))
    || !(option.available === false && option.price == null)
      && (!Number.isSafeInteger(option.price) || option.price < 0)
    || people.some(p => typeof p?.name !== 'string' || !p.name.trim())) {
    throw new TypeError('INVALID_TRIPFIT_INPUT');
  }
  let unknown = 0;
  const names = new Map([['지민', 'jimin'], ['서연', 'seoyeon']]);
  return {
    plan_id: plan.id, date: snapshot.date,
    people: people.map(({ name }) => ({ id: names.get(name) ?? `p${++unknown}`, name })),
    item: { gid: String(product.gid), url: product.url, name: product.name,
      short_name: product.name.replace(/^\[[^\]]+\]\s*/, '').split(' / ')[0],
      start: option.start, price: pay.price, merchant_id: `mrt:${product.gid}`, merchant_label: '마이리얼트립' },
    snapshot: { available: option.available, price: option.price ?? pay.price,
      checked_at: new Date(snapshot.fetchedAt).toISOString().replace(/\.\d{3}Z$/, 'Z'), source: 'snapshot' },
  };
}
