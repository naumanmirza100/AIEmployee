import React, { useState, useMemo } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Loader2, Key, CheckCircle2, XCircle, ChevronRight, ChevronDown, RefreshCw, Inbox, Search, Pencil } from 'lucide-react';
import { CARD_CLASS, ROW_CLASS, REQUEST_STATUS_META } from './apiKeysShared';

const TimelineEntry = ({ r, isLast, onApprove, onAssignKey, onReject, onEdit, pricing, isCurrentAssignment = false, keyStatus }) => {
  const meta = REQUEST_STATUS_META[r.status] || REQUEST_STATUS_META.pending;
  const { Icon } = meta;
  const total = (r.key_cost_snapshot ?? 0) + (r.service_charge_snapshot ?? 0);
  const agentPricing = pricing?.find(p => p.agent_name === r.agent_name);
  // Only the CURRENT assignment can be active, and only while the key still is.
  // Reading linked_key_status per row marked every past assignment with the
  // shared key's latest state.
  const isActive = isCurrentAssignment && keyStatus !== 'expired' && keyStatus !== 'revoked';
  const isNegative = ['rejected', 'revoked'].includes(r.status);
  const isPending = ['pending', 'payment_pending', 'payment_received'].includes(r.status);
  // _ts is set on synthetic revocation nodes; otherwise use resolved_at or created_at
  const displayTime = r._ts || r.resolved_at || r.created_at;

  const dotColor = isActive
    ? 'bg-emerald-500 border-emerald-400 shadow-emerald-500/40'
    : isNegative
    ? 'bg-orange-500 border-orange-400 shadow-orange-500/40'
    : isPending
    ? 'bg-amber-500 border-amber-400 shadow-amber-500/40 animate-pulse'
    : 'bg-white/20 border-white/20';

  return (
    <div className="flex gap-3">
      {/* Dot + line */}
      <div className="flex flex-col items-center shrink-0">
        <div className={`w-3 h-3 rounded-full border-2 shadow-sm mt-1 ${dotColor}`} />
        {!isLast && <div className="w-px flex-1 bg-[#2d2342] mt-1 mb-0" />}
      </div>

      {/* Content */}
      <div className={`flex-1 pb-4 min-w-0 ${isLast ? '' : ''}`}>
        <div className="flex items-start justify-between gap-2 flex-wrap">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className={`flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full border font-medium ${meta.cls}`}>
                <Icon className="w-3 h-3" />{meta.label}
              </span>
              <span className="text-[10px] text-white/30 uppercase">{r.provider}</span>
              {isActive && <span className="text-[9px] text-emerald-400/70 font-medium">● ACTIVE</span>}
              {isCurrentAssignment && keyStatus === 'expired' && <span className="text-[9px] text-amber-400/70 font-medium">● EXPIRED</span>}
            </div>

            {r.note && <p className="text-xs text-white/50 mt-1 italic">User note: "{r.note}"</p>}
            {r.admin_note && <p className="text-xs text-violet-300 mt-1">Admin: "{r.admin_note}"</p>}

            {r.status === 'payment_pending' && total > 0 && (
              <p className="text-xs text-yellow-300 mt-1">
                Amount due: <span className="font-semibold">${total.toFixed(2)}</span>
                <span className="text-white/40 ml-1">(key ${(r.key_cost_snapshot ?? 0).toFixed(2)} + svc ${(r.service_charge_snapshot ?? 0).toFixed(2)})</span>
                {r.discount_pct_snapshot > 0 && (
                  <span className="ml-2 text-emerald-400 bg-emerald-500/15 px-1.5 py-0.5 rounded-full text-[10px]">{r.discount_pct_snapshot}% discount applied</span>
                )}
              </p>
            )}
            {r.status === 'payment_received' && r.amount_paid != null && (
              <p className="text-xs text-blue-300 mt-1">
                Paid: <span className="font-semibold">${r.amount_paid.toFixed(2)}</span>
                {r.paid_at && <span className="text-white/40 ml-1">• {new Date(r.paid_at).toLocaleString()}</span>}
              </p>
            )}

            <p className="text-[10px] text-white/25 mt-1">
              {r._synthetic && r.status === 'key_expired'
                ? <span className="text-amber-300/50">{displayTime ? new Date(displayTime).toLocaleString() : 'Key expired'}</span>
                : r._synthetic
                ? <><span className="italic text-orange-300/50">Key revoked</span>{' · '}{new Date(displayTime).toLocaleString()}</>
                : <>
                    {r.requested_by
                      ? <><span className="text-white/40">{r.requested_by}</span> requested</>
                      : <span className="italic">Direct admin assignment</span>
                    }
                    {r.resolved_by && <> · resolved by <span className="text-white/40">{r.resolved_by}</span></>}
                    {' · '}{new Date(displayTime).toLocaleString()}
                  </>
              }
            </p>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {!r._synthetic && r.status === 'pending' && (
              <>
                <Button size="sm" className="h-7 bg-emerald-600 hover:bg-emerald-700 text-white text-xs px-2" onClick={() => onApprove(r)}>
                  <CheckCircle2 className="w-3 h-3 mr-1" />Approve
                </Button>
                <Button size="sm" variant="outline" className="h-7 border-violet-500/40 text-violet-300 hover:bg-violet-500/10 text-xs px-2" onClick={() => onEdit(r)}>
                  <Pencil className="w-3 h-3 mr-1" />Edit
                </Button>
                <Button size="sm" variant="outline" className="h-7 border-red-500/40 text-red-300 hover:bg-red-500/10 text-xs px-2" onClick={() => onReject(r)}>
                  <XCircle className="w-3 h-3 mr-1" />Reject
                </Button>
              </>
            )}
            {!r._synthetic && r.status === 'payment_pending' && (
              <>
                <Button size="sm" variant="outline" className="h-7 border-violet-500/40 text-violet-300 hover:bg-violet-500/10 text-xs px-2" onClick={() => onEdit(r)}>
                  <Pencil className="w-3 h-3 mr-1" />Edit
                </Button>
                <span className="text-[10px] text-yellow-300/70 italic">Awaiting payment</span>
              </>
            )}
            {!r._synthetic && r.status === 'payment_received' && (
              <Button size="sm" className="h-7 bg-violet-600 hover:bg-violet-700 text-white text-xs px-2" onClick={() => onAssignKey(r)}>
                <Key className="w-3 h-3 mr-1" />Assign Key
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

// Build the timeline for one (company, agent): the requests, merged with the
// RECORDED key lifecycle events (KeyEventLog).
//
// This used to synthesise "Key Expired" nodes from the CURRENT key's status and
// valid_until. That row is overwritten on every re-issue, so only the latest
// expiry could ever show — stamped onto whichever requests referenced that key,
// losing every earlier one. The events are real rows, so each expiry/revocation
// appears once, at the time it actually happened.
function expandEntries(requests, keyEvents = []) {
  const entries = [];

  for (const r of [...requests].sort((a, b) => new Date(a.created_at) - new Date(b.created_at))) {
    if (r.was_assigned) {
      entries.push({ ...r, status: 'key_assigned', _ts: r.resolved_at });
      entries.push({
        ...r,
        _syntheticId: `${r.id}_revoked`,
        status: 'revoked',
        _ts: r.revoked_at,
        _synthetic: true,
      });
    } else {
      entries.push({ ...r, _ts: r.resolved_at || r.created_at });
    }
  }

  // Only expiries/revocations come from the log — assign and renew events are
  // already represented by the requests above.
  for (const e of keyEvents) {
    if (e.event !== 'expired' && e.event !== 'revoked') continue;
    entries.push({
      id: `evt_${e.id}`,
      _syntheticId: `evt_${e.id}`,
      _synthetic: true,
      _event: true,
      status: e.event === 'expired' ? 'key_expired' : 'revoked',
      _ts: e.occurred_at,
      provider: e.provider,
      preferred_duration: e.renewal_period,
      note: null,
      admin_note: null,
    });
  }

  entries.sort((a, b) => {
    const ta = new Date(a._ts || a.created_at).getTime();
    const tb = new Date(b._ts || b.created_at).getTime();
    return ta - tb;
  });
  return entries;
}

// Grouped card: one card per (company, agent) showing full timeline
const RequestGroupCard = ({ group, keyEvents = [], onApprove, onAssignKey, onReject, onEdit, pricing }) => {
  const [expanded, setExpanded] = useState(group.hasAction);

  // Requests plus the recorded lifecycle events (see expandEntries).
  const entries = React.useMemo(
    () => expandEntries(group.requests, keyEvents),
    [group.requests, keyEvents],
  );

  const latest = entries[entries.length - 1];
  const latestReal = [...entries].reverse().find(e => !e._synthetic) || latest;
  // The live key state comes from the LATEST request's linked_key_status (it is
  // read fresh from the key row on every load). Older requests point at the
  // same key, so reading it from any of them would mislabel history.
  const currentAssignmentId = [...entries]
    .reverse()
    .find((e) => !e._synthetic && ['key_assigned', 'approved'].includes(e.status))?.id;
  const currentAssignment = entries.find((e) => e.id === currentAssignmentId);
  const keyStatus = currentAssignment?.linked_key_status;
  const isKeyExpired = keyStatus === 'expired';
  const effectiveStatus = isKeyExpired ? 'key_expired' : latest.status;
  const latestMeta = REQUEST_STATUS_META[effectiveStatus] || REQUEST_STATUS_META.pending;
  const { Icon: LatestIcon } = latestMeta;
  const isCurrentlyActive = !!currentAssignment && !isKeyExpired && keyStatus !== 'revoked';

  return (
    <div className={`${ROW_CLASS} rounded-xl overflow-hidden`}>
      {/* Header */}
      <button
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-white/[0.02] transition-colors"
        onClick={() => setExpanded(e => !e)}
      >
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-white font-semibold text-sm">{group.company_name}</span>
            <span className="text-xs text-white/40">{group.agent_label}</span>
            <span className={`flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full border font-medium ${latestMeta.cls}`}>
              <LatestIcon className="w-3 h-3" />{latestMeta.label}
            </span>
            {isCurrentlyActive && (
              <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 font-medium">Active key</span>
            )}
            {latestReal.preferred_duration && latestReal.preferred_duration !== 'none' && (
              <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-violet-500/15 border border-violet-500/30 text-violet-300 font-medium capitalize">{latestReal.preferred_duration}</span>
            )}
            {(isCurrentlyActive || isKeyExpired) && (
              <>
                {(latestReal.amount_paid != null || latestReal.key_cost_snapshot > 0) && (
                  <>
                    <span className="text-white/15 text-sm">·</span>
                    <span className="text-[10px] text-white/40">
                      Paid <span className={`font-semibold ${isCurrentlyActive ? 'text-emerald-300' : 'text-amber-300'}`}>${(latestReal.amount_paid ?? (latestReal.key_cost_snapshot ?? 0) + (latestReal.service_charge_snapshot ?? 0)).toFixed(2)}</span>
                      <span className="text-white/25 ml-1">(${(latestReal.key_cost_snapshot ?? 0).toFixed(2)} + ${(latestReal.service_charge_snapshot ?? 0).toFixed(2)} svc)</span>
                    </span>
                  </>
                )}
                {/* {latestReal.preferred_duration && (
                  <>
                    <span className="text-white/15 text-sm">·</span>
                    <span className="text-[11px] text-white/40">
                      <span className="text-white/25">Plan: </span>
                      <span className="text-violet-300 font-medium capitalize">{latestReal.preferred_duration}</span>
                    </span>
                  </>
                )} */}
                {latestReal.linked_key_valid_until && (
                  <>
                    <span className="text-white/15 text-sm">·</span>
                    {(() => {
                      const expiry = new Date(latestReal.linked_key_valid_until);
                      const daysLeft = Math.ceil((expiry - new Date()) / (1000 * 60 * 60 * 24));
                      const expired = daysLeft < 0;
                      return (
                        <span className={`text-[11px] font-medium ${expired ? 'text-amber-400' : daysLeft <= 7 ? 'text-amber-400' : 'text-white/40'}`}>
                          <span className="text-white/25">{expired ? 'Expired: ' : 'Expires: '}</span>
                          {expiry.toLocaleDateString()}{expired ? ` ⚠ ${daysLeft}d` : daysLeft <= 7 ? ` ⚠ ${daysLeft}d` : ''}
                        </span>
                      );
                    })()}
                  </>
                )}
              </>
            )}
          </div>
          <p className="text-[10px] text-white/30 mt-0.5">
            {entries.length} event{entries.length > 1 ? 's' : ''} · Latest {new Date(latest._ts || latest.resolved_at || latest.created_at).toLocaleDateString()}
          </p>
        </div>
        <div className="shrink-0 text-white/30">
          {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        </div>
      </button>

      {/* Timeline */}
      {expanded && (
        <div className="px-4 pb-2 pt-1 border-t border-[#2d2342]">
          {entries.map((r, i) => (
            <TimelineEntry
              key={r._syntheticId || r.id}
              r={r}
              isLast={i === entries.length - 1}
              onApprove={onApprove}
              onAssignKey={onAssignKey}
              onReject={onReject}
              onEdit={onEdit}
              pricing={pricing}
              isCurrentAssignment={r.id === currentAssignmentId}
              keyStatus={keyStatus}
            />
          ))}
        </div>
      )}
    </div>
  );
};

export const RequestsTab = ({ requests, keyEvents = [], onApprove, onAssignKey, onReject, onEdit, filter, setFilter, onRefresh, loading, pricing }) => {
  // Group by (company_id + agent_name), sorted oldest→newest within each group
  const groups = React.useMemo(() => {
    const map = {};
    requests.forEach(r => {
      const key = `${r.company_id}__${r.agent_name}`;
      if (!map[key]) map[key] = {
        key,
        company_id: r.company_id,
        company_name: r.company_name,
        agent_name: r.agent_name,
        agent_label: r.agent_label,
        requests: [],
        hasAction: false,
      };
      map[key].requests.push(r);
      if (['pending', 'payment_received'].includes(r.status)) map[key].hasAction = true;
    });
    // Sort each group oldest→newest so timeline reads top-to-bottom
    Object.values(map).forEach(g => g.requests.sort((a, b) => new Date(a.created_at) - new Date(b.created_at)));
    // Sort groups: action-needed first, then by latest event desc
    return Object.values(map).sort((a, b) => {
      if (a.hasAction !== b.hasAction) return a.hasAction ? -1 : 1;
      const aLatest = new Date(a.requests[a.requests.length - 1].created_at);
      const bLatest = new Date(b.requests[b.requests.length - 1].created_at);
      return bLatest - aLatest;
    });
  }, [requests]);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 flex-wrap">
        <Select value={filter.status || 'all'} onValueChange={(v) => setFilter({ ...filter, status: v === 'all' ? '' : v })}>
          <SelectTrigger className="w-48 bg-[#1a1333] border-[#3a295a] text-white"><SelectValue placeholder="All statuses" /></SelectTrigger>
          <SelectContent className="bg-[#1a1333] border-[#3a295a] text-white">
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="pending">Pending</SelectItem>
            <SelectItem value="payment_pending">Payment Required</SelectItem>
            <SelectItem value="payment_received">Payment Received</SelectItem>
            <SelectItem value="key_assigned">Key Assigned</SelectItem>
            <SelectItem value="approved">Approved (legacy)</SelectItem>
            <SelectItem value="rejected">Rejected</SelectItem>
            <SelectItem value="revoked">Revoked</SelectItem>
          </SelectContent>
        </Select>
        <Input
          placeholder="Search company..."
          value={filter.search || ''}
          onChange={(e) => setFilter({ ...filter, search: e.target.value })}
          className="bg-[#1a1333] border-[#3a295a] text-white w-60 placeholder:text-white/30"
        />
        <Button variant="outline" className="border-white/15 text-white/80 hover:bg-white/5 hover:text-white" onClick={onRefresh} disabled={loading}>
          {loading ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <RefreshCw className="w-4 h-4 mr-1" />} Refresh
        </Button>
        {groups.length > 0 && (
          <span className="text-xs text-white/30 ml-1">{groups.length} company{groups.length > 1 ? '/agent pairs' : '/agent pair'} · {requests.length} total events</span>
        )}
      </div>
      {groups.length === 0 ? (
        <Card className={CARD_CLASS}>
          <CardContent className="p-12 text-center text-white/50">
            <Inbox className="w-10 h-10 text-white/20 mx-auto mb-2" /> No requests.
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {groups.map(g => (
            <RequestGroupCard
              key={g.key}
              group={g}
              keyEvents={keyEvents.filter(
                (e) => e.company_id === g.company_id && e.agent_name === g.agent_name,
              )}
              onApprove={onApprove}
              onAssignKey={onAssignKey}
              onReject={onReject}
              onEdit={onEdit}
              pricing={pricing}
            />
          ))}
        </div>
      )}
    </div>
  );
};

// -------------------- Company Picker (searchable) --------------------

export default RequestsTab;
