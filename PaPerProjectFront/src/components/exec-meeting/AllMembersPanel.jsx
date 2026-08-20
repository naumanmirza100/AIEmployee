// "View all members" side panel for the Schedule Meeting / Add Task dialogs.
//
// Instead of typing to search, the user clicks "View all members" and this
// panel slides in ATTACHED TO THE RIGHT of the open dialog (not stacked on
// top of it) and lists every member of the company vertically. Clicking a
// member toggles them in/out of the selection; the panel stays open so
// several can be added in a row. Already-selected members show a check.
//
// It is deliberately self-contained: it fetches its own member list via
// execMeetingService.listAllUsers() and reports selection changes back to the
// parent dialog through `onToggle`. The parent owns the actual participant
// state, so meeting/task creation logic is unchanged.

import React, { useState, useEffect, useMemo } from 'react';
import { Loader2, Check, Search, Users } from 'lucide-react';
import execMeetingService from '@/services/execMeetingService';

// Stable key for a member across the two backing user types (CompanyUser vs
// UserProfile) — mirrors how the dialogs key participants.
const memberKey = (u) => `${u?.user_type || 'company_user'}-${u?.id}`;

// `fullWidth` makes the panel fill its container (used inline below a field
// in the narrow task dialogs) instead of the fixed 288px side panel used
// beside the wide Schedule Meeting dialog.
export const AllMembersPanel = ({ open, onClose, selected = [], onToggle, fullWidth = false }) => {
  const [members, setMembers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');

  // Fetch the full company roster once each time the panel opens.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setError('');
    (async () => {
      try {
        const res = await execMeetingService.listAllUsers();
        if (cancelled) return;
        setMembers(Array.isArray(res?.users) ? res.users : []);
      } catch (e) {
        if (cancelled) return;
        setError(e?.message || 'Could not load members.');
        setMembers([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [open]);

  // Reset the local filter whenever the panel is closed so it opens fresh.
  useEffect(() => { if (!open) setQuery(''); }, [open]);

  const selectedKeys = useMemo(
    () => new Set((selected || []).map(memberKey)),
    [selected]
  );

  // Client-side filter over the already-loaded roster (the list is capped
  // server-side, so this stays cheap).
  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return members;
    return members.filter((u) =>
      [u.full_name, u.email, u.role].some((v) => (v || '').toLowerCase().includes(q))
    );
  }, [members, query]);

  if (!open) return null;

  return (
    // Attached to the right edge of the dialog. It's a sibling of the dialog
    // content (rendered by the parent inside the same portal), sitting flush
    // against it rather than overlaying it.
    <div className={`flex flex-col rounded-2xl border border-white/10 bg-[#0d0b1f] text-white overflow-hidden ${fullWidth ? 'w-full h-full max-h-full' : 'w-72 shrink-0 max-h-[80vh]'}`}>
      {/* No close ✕ here — the panel is toggled from its parent ("View all
          members" / "Hide all members"), and its own ✕ used to overlap the host
          dialog's built-in close button. */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-white/10">
        <Users className="h-4 w-4 text-violet-300 shrink-0" />
        <span className="text-sm font-semibold truncate">All members</span>
        {members.length > 0 && (
          <span className="text-[11px] text-white/40">({members.length})</span>
        )}
      </div>

      {/* Filter */}
      <div className="px-3 py-2 border-b border-white/10">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-white/30" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter members…"
            className="w-full bg-white/5 border border-white/10 rounded-lg pl-8 pr-2 py-1.5 text-xs text-white placeholder-white/30 focus:outline-none focus:border-violet-500/50"
          />
        </div>
      </div>

      {/* Vertical member list */}
      <div className="flex-1 overflow-y-auto custom-sidebar-scroll">
        {loading ? (
          <div className="flex items-center gap-2 justify-center py-10 text-white/40 text-xs">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading members…
          </div>
        ) : error ? (
          <div className="px-4 py-8 text-center text-xs text-rose-300">{error}</div>
        ) : visible.length === 0 ? (
          <div className="px-4 py-8 text-center text-xs text-white/30">
            {query ? 'No members match your filter.' : 'No members found.'}
          </div>
        ) : (
          visible.map((u) => {
            const isSelected = selectedKeys.has(memberKey(u));
            return (
              <button
                key={memberKey(u)}
                type="button"
                onClick={() => onToggle(u)}
                className={`w-full flex items-center gap-3 px-3 py-2 text-left border-b border-white/5 transition-colors ${
                  isSelected ? 'bg-violet-500/15 hover:bg-violet-500/25' : 'hover:bg-white/5'
                }`}
              >
                <div className="h-7 w-7 rounded-full bg-violet-500/30 flex items-center justify-center text-violet-200 text-xs font-bold shrink-0">
                  {u.full_name?.[0]?.toUpperCase() || '?'}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-medium text-white truncate">{u.full_name}</p>
                  <p className="text-[10px] text-white/40 truncate">{u.email}{u.role ? ` · ${u.role}` : ''}</p>
                </div>
                {/* Checkmark for selected members; empty ring otherwise. */}
                <span
                  className={`h-5 w-5 rounded-full flex items-center justify-center shrink-0 transition ${
                    isSelected
                      ? 'bg-violet-500 text-white'
                      : 'border border-white/20 text-transparent'
                  }`}
                >
                  <Check className="h-3 w-3" />
                </span>
              </button>
            );
          })
        )}
      </div>
    </div>
  );
};

export default AllMembersPanel;
