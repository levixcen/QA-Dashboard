const JAKARTA = 'Asia/Jakarta';

function toDate(value) {
  if (value == null || value === '') return null;
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value;
  if (typeof value === 'number') {
    const ms = value > 1e12 ? value : value * 1000;
    const d = new Date(ms);
    return Number.isNaN(d.getTime()) ? null : d;
  }
  const s = String(value).trim();
  if (!s) return null;
  // Bare YYYY-MM-DD → treat as Jakarta calendar day (no TZ shift)
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) {
    const d = new Date(`${s}T12:00:00+07:00`);
    return Number.isNaN(d.getTime()) ? null : d;
  }
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** Short date for cards: "Oct 5" */
export function formatDate(iso) {
  const d = toDate(iso);
  if (!d) return '—';
  return d.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    timeZone: JAKARTA,
  });
}

/** Date + time: "Oct 5, 14:30" */
export function formatDateTime(iso) {
  const d = toDate(iso);
  if (!d) return '—';
  const date = d.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    timeZone: JAKARTA,
  });
  const time = d.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: JAKARTA,
  });
  return `${date}, ${time}`;
}

/** YYYY-MM-DD in Jakarta */
export function formatISODate(iso) {
  const d = toDate(iso);
  if (!d) return null;
  return d.toLocaleDateString('en-CA', { timeZone: JAKARTA });
}