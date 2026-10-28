/**
 * Which of an employee's meetings they can answer, and which still wait for an answer. One rule for My Meetings'
 * header, the menu's badge and Home's "Pending invites" tile: they used three, and a finished meeting that was never
 * answered still counted in the badge ("2 awaiting response" beside a badge of 3, 29 Oct 2026).
 */

// The server decides (`can_respond`, on every kind of meeting); the fallback is the old PM-only rule.
export const canAnswer = (m) => (typeof m.can_respond === 'boolean'
  ? m.can_respond
  : (m.my_status === 'pending' || m.my_status === 'counter_proposed'
    || m.status === 'pending' || m.status === 'counter_proposed')
    && m.my_status !== 'accepted' && m.status !== 'withdrawn');

// An answered invitation can still be changed until the meeting is over, but it is no longer waiting.
export const isAnswered = (m) => m.my_status === 'accepted' || m.my_status === 'rejected';

export const awaitsAnswer = (m) => canAnswer(m) && !isAnswered(m);
