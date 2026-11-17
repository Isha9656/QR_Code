/**
 * Asia/Kolkata (IST, UTC+05:30) Date & Time Formatting Utilities
 */

const IST_TIMEZONE = 'Asia/Kolkata';

export function toDate(val) {
  if (!val) return null;
  if (val instanceof Date) return val;
  // If string doesn't end with Z and has no timezone offset, assume UTC from backend
  if (typeof val === 'string' && !val.endsWith('Z') && !val.includes('+')) {
    val = val + 'Z';
  }
  const d = new Date(val);
  return isNaN(d.getTime()) ? null : d;
}

export function formatIST(dateVal, includeSeconds = false) {
  const d = toDate(dateVal);
  if (!d) return '—';

  const options = {
    timeZone: IST_TIMEZONE,
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: true,
  };

  if (includeSeconds) {
    options.second = '2-digit';
  }

  const formatted = new Intl.DateTimeFormat('en-IN', options).format(d);
  return `${formatted} IST`;
}

export function formatISTDate(dateVal) {
  const d = toDate(dateVal);
  if (!d) return '—';

  return new Intl.DateTimeFormat('en-IN', {
    timeZone: IST_TIMEZONE,
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  }).format(d);
}

export function formatISTTime(dateVal) {
  const d = toDate(dateVal);
  if (!d) return '—';

  return new Intl.DateTimeFormat('en-IN', {
    timeZone: IST_TIMEZONE,
    hour: '2-digit',
    minute: '2-digit',
    hour12: true,
  }).format(d);
}
