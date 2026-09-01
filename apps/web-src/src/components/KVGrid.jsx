/**
 * Reusable key-value grid for displaying structured data.
 */

export function fmt(value) {
  if (Array.isArray(value)) {
    return value.length ? value.map(String).join(', ') : '—';
  }
  if (typeof value === 'boolean') return value ? 'yes' : 'no';
  if (typeof value === 'number' && Number.isFinite(value)) {
    return Number.isInteger(value) ? String(value) : String(Math.round(value * 100) / 100);
  }
  return value == null || value === '' ? '—' : String(value);
}

export default function KVGrid({ data, order = null, labels = null }) {
  if (!data || typeof data !== 'object') return null;

  const keys = order
    ? [...order.filter((k) => k in data), ...Object.keys(data).filter((k) => !order.includes(k))]
    : Object.keys(data);

  return (
    <div className="kv-grid">
      {keys.map((k) => (
        <div className="kv" key={k}>
          <div className="k">{(labels && labels[k]) || k}</div>
          <div className="v">{fmt(data[k])}</div>
        </div>
      ))}
    </div>
  );
}
