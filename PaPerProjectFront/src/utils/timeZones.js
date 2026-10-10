/**
 * Time zones for a picker.
 *
 * A time zone used to be typed into a free-text box, and a name typed wrongly
 * was silently read as UTC. The list comes from the browser, so every name in
 * it is one the server accepts too.
 */

// For a browser too old to list its zones (Intl.supportedValuesOf).
const FALLBACK = [
  'UTC', 'Africa/Cairo', 'Africa/Johannesburg', 'Africa/Lagos', 'America/Chicago', 'America/Denver',
  'America/Los_Angeles', 'America/New_York', 'America/Sao_Paulo', 'America/Toronto', 'Asia/Dhaka', 'Asia/Dubai',
  'Asia/Hong_Kong', 'Asia/Karachi', 'Asia/Kolkata', 'Asia/Riyadh', 'Asia/Singapore', 'Asia/Tokyo',
  'Australia/Sydney', 'Europe/Berlin', 'Europe/Istanbul', 'Europe/London', 'Europe/Paris', 'Pacific/Auckland',
];

/** The zone this browser is set to, e.g. "Asia/Karachi". */
export const browserTimeZone = () => {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
};

/** Every zone to offer, in order. `also` adds values already saved, so a saved one is never missing. */
export const timeZones = (also = []) => {
  let names = [];
  try {
    names = Intl.supportedValuesOf('timeZone');
  } catch {
    names = [];
  }
  if (!names.length) names = FALLBACK;
  return [...new Set([...names, 'UTC', ...also.filter(Boolean)])].sort();
};
