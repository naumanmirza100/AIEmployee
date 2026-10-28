/**
 * A deadline's date as people write it: "2 Nov 2026". The server keeps it as "2026-11-02" (CO-277), and that is
 * how the summary page and Analytics showed it.
 */
export const formatDeadline = (iso) => {
  if (!iso) return '';
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso));
  if (!match) return String(iso);
  const when = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  return when.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
};

export default formatDeadline;
