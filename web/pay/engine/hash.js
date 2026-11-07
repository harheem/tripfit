// JSON semantics, with object keys sorted at every depth. Arrays retain order.
export function canonicalJSON(value) {
  const json = JSON.stringify(value);
  if (json === undefined) throw new TypeError('Expected a JSON value');
  function encode(item) {
    if (item === null || typeof item !== 'object') return JSON.stringify(item);
    if (Array.isArray(item)) return `[${item.map(encode).join(',')}]`;
    return `{${Object.keys(item).sort().map(key => `${JSON.stringify(key)}:${encode(item[key])}`).join(',')}}`;
  }
  return encode(JSON.parse(json));
}

export async function sha256(text) {
  const digest = await globalThis.crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
}
