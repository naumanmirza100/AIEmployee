// Meetings panel — list + a meeting detail card pop-up whose People and Notes
// each open in their own separate modal. Stateless w.r.t. data: all data state +
// handlers come via props; only the two sub-modal open flags are local.

import React, { useState, useEffect, useRef } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent } from '@/components/ui/dialog';
import {
  Loader2, CalendarClock, FileText, Plus, Pencil, RefreshCw, ChevronRight, Trash2, Check, X, Wand2, Users,
} from 'lucide-react';
import { CARD_STYLE, ROW_STYLE, statusBadge, EmptyState, fmtUtc, FilterBar, Pagination } from '../shared';
import HoverTip from '@/components/common/HoverTip';
import { AllMembersPanel } from '../AllMembersPanel';

const MEETING_STATUS_OPTIONS = [
  { value: 'scheduled', label: 'Scheduled' },
  { value: 'in_progress', label: 'In Progress' },
  { value: 'completed', label: 'Completed' },
  { value: 'cancelled', label: 'Cancelled' },
  { value: 'pending_confirmation', label: 'Pending Confirmation' },
];

export const MeetingsPanel = ({
  meetings, meetingsLoading, notesOpenId, participantsOpenId, meetingNotes,
  participantsMap, pendingAddMap, confirmRemoveMap,
  userSearchQ, userSearchLoading, userSearchResults, transcriptInput, notesLoading,
  loadMeetings, setShowMeetingDialog, onCreateWithAI, setEditingMeeting, openParticipants,
  openMeetingId, openMeetingCard, closeMeetingCard,
  openNotes, removeParticipant, setConfirmRemoveMap, addParticipant, setPendingAddMap,
  setUserSearchQ, setUserSearchResults, searchUsers, submitTranscript, setTranscriptInput,
  convertActionItem, convertedActionItemIds, clearMeetingNotes, removeMeetingAgenda,
  focusMeetingId, setFocusMeetingId,
  filters = {}, setFilters = () => {}, filterUsers = [],
  pageMeta = null, onPageChange = () => {},
}) => {
  const filtersActive = !!(filters.search || filters.status || filters.date || filters.participant);
  // People / Notes open in their own modals, layered over the meeting card.
  const [peopleOpen, setPeopleOpen] = useState(false);
  const [notesModalOpen, setNotesModalOpen] = useState(false);
  // "View all members" list inside the People modal.
  const [showAllMembers, setShowAllMembers] = useState(false);

  // When a notification navigates here, scroll the target meeting into view and
  // briefly highlight it, then clear the focus so it doesn't stick.
  const rowRefs = useRef({});
  useEffect(() => {
    if (focusMeetingId && rowRefs.current[focusMeetingId]) {
      rowRefs.current[focusMeetingId].scrollIntoView({ behavior: 'smooth', block: 'center' });
      const t = setTimeout(() => setFocusMeetingId && setFocusMeetingId(null), 2500);
      return () => clearTimeout(t);
    }
  }, [focusMeetingId, meetings]);

  // Closing the meeting card also closes its sub-modals.
  const closeAll = () => { setPeopleOpen(false); setNotesModalOpen(false); setShowAllMembers(false); closeMeetingCard(); };

  // Open a meeting straight into its People or Notes modal from the list row.
  // openMeetingCard loads participants + notes so the sub-modal has data.
  const openMeetingSub = (meetingId, which) => {
    openMeetingCard(meetingId);
    if (which === 'people') { setNotesModalOpen(false); setPeopleOpen(true); }
    else { setPeopleOpen(false); setNotesModalOpen(true); }
  };

  const openMeeting = Array.isArray(meetings) ? meetings.find(x => x.id === openMeetingId) : null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-white font-semibold flex items-center gap-2">
          <CalendarClock className="h-4 w-4 text-violet-400" />
          Meetings
        </h3>
        <div className="flex items-center gap-2">
          <HoverTip tip="Refresh the meetings list">
            <Button size="sm" variant="ghost" onClick={loadMeetings} disabled={meetingsLoading} className="text-white/40 hover:text-white">
              <RefreshCw className={`h-3.5 w-3.5 ${meetingsLoading ? 'animate-spin' : ''}`} />
            </Button>
          </HoverTip>
          {onCreateWithAI && (
            <HoverTip tip="Describe a meeting in plain language and let AI draft it">
              <Button size="sm" variant="outline" onClick={onCreateWithAI} className="border-violet-400/40 bg-violet-400/10 text-violet-200 hover:bg-violet-400/20 hover:text-violet-100">
                <Wand2 className="h-4 w-4 mr-1" /> Create with AI
              </Button>
            </HoverTip>
          )}
          <HoverTip tip="Schedule a new meeting">
            <Button size="sm" onClick={() => setShowMeetingDialog(true)} style={{ background: 'linear-gradient(90deg, #a259ff 0%, #7c3aed 100%)' }} className="text-white border-0 hover:opacity-90">
              <Plus className="h-4 w-4 mr-1" /> Schedule
            </Button>
          </HoverTip>
        </div>
      </div>

      <FilterBar
        search={filters.search || ''}
        onSearchChange={v => setFilters(f => ({ ...f, search: v }))}
        searchPlaceholder="Search meetings…"
        selects={[
          {
            value: filters.status,
            onChange: v => setFilters(f => ({ ...f, status: v })),
            placeholder: 'All statuses', allLabel: 'All statuses',
            options: MEETING_STATUS_OPTIONS,
          },
          {
            value: filters.participant,
            onChange: v => setFilters(f => ({ ...f, participant: v })),
            placeholder: 'Any participant', allLabel: 'Any participant',
            options: filterUsers,
          },
        ]}
        date={filters.date}
        onDateChange={v => setFilters(f => ({ ...f, date: v }))}
        active={filtersActive}
        onClear={() => setFilters({ search: '', status: '', date: '', participant: '' })}
      />

      {meetingsLoading ? (
        <div className="flex justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-violet-400" /></div>
      ) : !Array.isArray(meetings) || meetings.length === 0 ? (
        <EmptyState icon={CalendarClock} label={filtersActive ? 'No meetings match these filters' : 'No meetings scheduled yet'} />
      ) : (
        <div className="rounded-2xl" style={CARD_STYLE}>
          {meetings.map(m => {
            const isFocused = String(focusMeetingId) === String(m.id);
            return (
              <div
                key={m.id}
                ref={el => { rowRefs.current[m.id] = el; }}
                style={ROW_STYLE}
                className={isFocused ? 'ring-2 ring-inset ring-violet-500/70 bg-violet-500/[0.06] transition-all' : 'transition-all'}
              >
                {/* Meeting row — click to open the detail card pop-up */}
                <div
                  className="flex items-center gap-4 px-4 py-3 cursor-pointer hover:bg-white/[0.04] transition-colors"
                  onClick={() => openMeetingCard(m.id)}
                >
                  <div className="rounded-lg p-2 bg-violet-500/20 flex-shrink-0">
                    <CalendarClock className="h-4 w-4 text-violet-400" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-white text-sm font-medium truncate">{m.title}</p>
                    <p className="text-white/40 text-xs">
                      {fmtUtc(m.scheduled_at)}
                      {m.duration_minutes ? ` · ${m.duration_minutes}min` : ''}
                    </p>
                    {m.description && (
                      <p className="text-white/50 text-xs mt-1 truncate">{m.description}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    {statusBadge(m.status)}
                    <HoverTip tip="Manage participants">
                      <Button size="sm" variant="ghost"
                        onClick={e => { e.stopPropagation(); openMeetingSub(m.id, 'people'); }}
                        className="text-white/40 hover:text-violet-300 text-xs gap-1 px-2">
                        <Users className="h-3.5 w-3.5" /> People
                      </Button>
                    </HoverTip>
                    <HoverTip tip="View or add AI meeting notes">
                      <Button size="sm" variant="ghost"
                        onClick={e => { e.stopPropagation(); openMeetingSub(m.id, 'notes'); }}
                        className="text-white/40 hover:text-sky-300 text-xs gap-1 px-2">
                        <FileText className="h-3.5 w-3.5" /> Notes
                      </Button>
                    </HoverTip>
                    <HoverTip tip="Edit this meeting">
                      <Button size="sm" variant="ghost"
                        onClick={e => { e.stopPropagation(); setEditingMeeting(m); }}
                        className="text-white/40 hover:text-violet-300 p-1">
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                    </HoverTip>
                    <ChevronRight className="h-4 w-4 text-white/30" />
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
      <Pagination meta={pageMeta} onChange={onPageChange} itemLabel="meeting" />

      {/* ── Meeting detail card pop-up (details + People/Notes buttons) ── */}
      <Dialog open={!!openMeeting} onOpenChange={open => { if (!open) closeAll(); }}>
        <DialogContent
          className="max-w-xl w-full bg-[#0d0b1f] border-white/10 text-white p-0 gap-0"
          style={{ maxHeight: '90vh', display: 'flex', flexDirection: 'column' }}
        >
          {openMeeting && (() => {
            const m = openMeeting;
            const parts = participantsMap[m.id] || [];
            const notes = meetingNotes[m.id];
            const actionCount = Array.isArray(notes?.action_items) ? notes.action_items.length : 0;
            return (
              <>
                {/* Header */}
                <div className="flex items-start justify-between px-6 py-4 pr-14 border-b border-white/10 flex-shrink-0">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className="text-white font-semibold text-sm">{m.title}</h3>
                      {statusBadge(m.status)}
                    </div>
                    <p className="text-white/40 text-xs mt-0.5">
                      {fmtUtc(m.scheduled_at)}{m.duration_minutes ? ` · ${m.duration_minutes}min` : ''}
                    </p>
                    {m.meeting_link && (
                      <a href={m.meeting_link} target="_blank" rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-xs text-violet-400 hover:text-violet-300 mt-1">
                        <span>🔗</span> Join Meeting
                      </a>
                    )}
                  </div>
                  <HoverTip tip="Edit this meeting">
                    <Button size="sm" variant="ghost" onClick={() => setEditingMeeting(m)}
                      className="text-white/40 hover:text-violet-300 p-1.5 flex-shrink-0 ml-3">
                      <Pencil className="h-4 w-4" />
                    </Button>
                  </HoverTip>
                </div>

                {/* Body */}
                <div className="flex-1 overflow-y-auto no-scrollbar px-6 py-5 space-y-5">
                  {/* Description */}
                  {m.description && (
                    <div>
                      <p className="text-white/40 text-xs uppercase tracking-wide mb-1">Description</p>
                      <p className="text-white/70 text-sm whitespace-pre-wrap">{m.description}</p>
                    </div>
                  )}

                  {/* Agenda */}
                  {Array.isArray(m.agenda) && m.agenda.length > 0 && (
                    <div>
                      <div className="flex items-center gap-2 mb-1">
                        <p className="text-white/40 text-xs uppercase tracking-wide">Agenda</p>
                        <HoverTip tip="Remove this agenda">
                          <button type="button" onClick={() => removeMeetingAgenda(m.id)}
                            className="text-[10px] text-white/25 hover:text-red-400 inline-flex items-center gap-0.5 transition-colors">
                            <X className="h-2.5 w-2.5" /> remove
                          </button>
                        </HoverTip>
                      </div>
                      <ul className="space-y-0.5">
                        {m.agenda.map((item, i) => (
                          <li key={i} className="text-xs text-white/60 flex gap-1.5">
                            <span className="text-violet-400/70">•</span>{item}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* People / Notes — open their own modals */}
                  <div className="grid grid-cols-2 gap-3">
                    <button
                      type="button"
                      onClick={() => setPeopleOpen(true)}
                      className="flex items-center gap-3 rounded-xl border border-white/10 bg-white/[0.03] hover:bg-white/[0.06] hover:border-violet-400/40 px-4 py-3 text-left transition-colors"
                    >
                      <div className="rounded-lg p-2 bg-violet-500/20 flex-shrink-0">
                        <Users className="h-4 w-4 text-violet-300" />
                      </div>
                      <div className="min-w-0">
                        <p className="text-white text-sm font-medium">People</p>
                        <p className="text-white/40 text-xs">{parts.length ? `${parts.length} participant${parts.length === 1 ? '' : 's'}` : 'Add participants'}</p>
                      </div>
                    </button>
                    <button
                      type="button"
                      onClick={() => setNotesModalOpen(true)}
                      className="flex items-center gap-3 rounded-xl border border-white/10 bg-white/[0.03] hover:bg-white/[0.06] hover:border-violet-400/40 px-4 py-3 text-left transition-colors"
                    >
                      <div className="rounded-lg p-2 bg-sky-500/20 flex-shrink-0">
                        <FileText className="h-4 w-4 text-sky-300" />
                      </div>
                      <div className="min-w-0">
                        <p className="text-white text-sm font-medium">Notes</p>
                        <p className="text-white/40 text-xs">
                          {notes ? `AI notes${actionCount ? ` · ${actionCount} action item${actionCount === 1 ? '' : 's'}` : ''}` : 'Add / generate notes'}
                        </p>
                      </div>
                    </button>
                  </div>
                </div>
              </>
            );
          })()}
        </DialogContent>
      </Dialog>

      {/* ── People modal ── */}
      <Dialog open={peopleOpen && !!openMeeting} onOpenChange={o => { setPeopleOpen(o); if (!o) setShowAllMembers(false); }}>
        <DialogContent className="max-w-md w-full bg-[#0d0b1f] border-white/10 text-white max-h-[85vh] overflow-y-auto no-scrollbar">
          {openMeeting && (() => {
            const m = openMeeting;
            const parts = participantsMap[m.id] || [];
            const pendingUser = pendingAddMap[m.id] || null;
            const confirmRemoveId = confirmRemoveMap[m.id] || null;
            return (
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <Users className="h-4 w-4 text-violet-300" />
                  <h3 className="text-white font-semibold text-sm">Participants{parts.length ? ` (${parts.length})` : ''}</h3>
                </div>
                <p className="text-white/40 text-xs -mt-1">{m.title}</p>

                {parts.length > 0 && (
                  <div className="space-y-1 max-h-64 overflow-y-auto pr-1">
                    {parts.map(p => (
                      <div key={p.user_id}>
                        <div className="flex items-center justify-between rounded-lg px-3 py-2 bg-white/5">
                          <div>
                            <span className="text-white text-xs font-medium">{p.full_name}</span>
                            <span className="text-white/40 text-xs ml-2">{p.email}</span>
                          </div>
                          <div className="flex items-center gap-2">
                            {p.response && p.response !== 'pending' && (
                              <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                                p.response === 'accepted' ? 'bg-emerald-500/20 text-emerald-400' :
                                p.response === 'rejected' ? 'bg-red-500/20 text-red-400' :
                                p.response === 'tentative' ? 'bg-yellow-500/20 text-yellow-400' :
                                'bg-white/10 text-white/40'
                              }`}>{p.response}</span>
                            )}
                            {!p.id ? (
                              <span className="text-white/20 text-[10px]">syncing…</span>
                            ) : confirmRemoveId === p.id ? (
                              <div className="flex items-center gap-1">
                                <span className="text-white/50 text-[10px]">Remove?</span>
                                <button
                                  onClick={() => { removeParticipant(m.id, p.id, p.user_id, p.full_name); setConfirmRemoveMap(prev => ({ ...prev, [m.id]: null })); }}
                                  className="px-2 py-0.5 rounded text-[10px] bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-colors">
                                  Yes
                                </button>
                                <button
                                  onClick={() => setConfirmRemoveMap(prev => ({ ...prev, [m.id]: null }))}
                                  className="px-2 py-0.5 rounded text-[10px] bg-white/10 text-white/50 hover:bg-white/20 transition-colors">
                                  No
                                </button>
                              </div>
                            ) : (
                              <HoverTip tip="Remove this participant">
                                <button
                                  onClick={() => setConfirmRemoveMap(prev => ({ ...prev, [m.id]: p.id }))}
                                  className="text-white/30 hover:text-red-400 text-xs transition-colors">✕</button>
                              </HoverTip>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Pending add confirmation bar */}
                {pendingUser && (
                  <div className="flex items-center justify-between rounded-lg px-3 py-2 bg-violet-500/10 border border-violet-500/30">
                    <div className="flex items-center gap-2">
                      <div className="h-6 w-6 rounded-full bg-violet-500/30 flex items-center justify-center text-violet-300 text-xs font-bold flex-shrink-0">
                        {pendingUser.full_name?.[0]?.toUpperCase() || '?'}
                      </div>
                      <div>
                        <p className="text-violet-200 text-xs font-medium">{pendingUser.full_name}</p>
                        <p className="text-white/40 text-[10px]">{pendingUser.email}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-violet-300/60 text-[10px]">An email will be sent</span>
                      <button
                        onClick={() => { addParticipant(m.id, pendingUser); setPendingAddMap(prev => ({ ...prev, [m.id]: null })); setUserSearchQ(''); setUserSearchResults([]); }}
                        className="px-2.5 py-1 rounded text-[11px] bg-violet-600 text-white hover:bg-violet-700 transition-colors font-medium">
                        Confirm
                      </button>
                      <button
                        onClick={() => { setPendingAddMap(prev => ({ ...prev, [m.id]: null })); setUserSearchQ(''); setUserSearchResults([]); }}
                        className="text-white/30 hover:text-white/60 text-xs transition-colors">✕</button>
                    </div>
                  </div>
                )}

                {/* Search + add */}
                {!pendingUser && (
                  <div className="relative">
                    <Input
                      value={participantsOpenId === m.id ? userSearchQ : ''}
                      onChange={e => searchUsers(e.target.value, m.id)}
                      placeholder="Type a name or email to add…"
                      autoComplete="off"
                      className="bg-white/5 border-white/10 text-white text-xs h-8"
                    />
                    {userSearchLoading && (
                      <Loader2 className="absolute right-2 top-2 h-4 w-4 animate-spin text-white/40" />
                    )}
                    {userSearchResults.length > 0 && (
                      <div className="absolute z-50 w-full mt-1 rounded-xl border border-white/10 bg-[#1a1333] shadow-xl max-h-56 overflow-y-auto">
                        {userSearchResults.map(u => (
                          <button key={u.id}
                            onClick={() => { setPendingAddMap(prev => ({ ...prev, [m.id]: u })); setUserSearchResults([]); }}
                            className="w-full flex items-center gap-3 px-3 py-2 hover:bg-violet-500/20 transition-colors text-left">
                            <div className="h-7 w-7 rounded-full bg-violet-500/30 flex items-center justify-center text-violet-300 text-xs font-bold flex-shrink-0">
                              {u.full_name?.[0]?.toUpperCase() || '?'}
                            </div>
                            <div>
                              <p className="text-white text-xs font-medium">{u.full_name}</p>
                              <p className="text-white/40 text-[10px]">{u.email} · {u.role}</p>
                            </div>
                          </button>
                        ))}
                      </div>
                    )}
                    {userSearchQ.length >= 2 && !userSearchLoading && userSearchResults.length === 0 && (
                      <p className="text-white/30 text-xs mt-1 px-1">No users found</p>
                    )}
                  </div>
                )}

                {/* View all members — pick from the full roster instead of typing */}
                {!pendingUser && (
                  <div className="space-y-2">
                    <button
                      type="button"
                      onClick={() => setShowAllMembers(v => !v)}
                      className="inline-flex items-center gap-1.5 text-xs text-violet-300 hover:text-violet-200 transition-colors"
                    >
                      <Users className="h-3.5 w-3.5" />
                      {showAllMembers ? 'Hide all members' : 'View all members'}
                    </button>
                    <AllMembersPanel
                      open={showAllMembers}
                      onClose={() => setShowAllMembers(false)}
                      fullWidth
                      selected={parts.map(p => ({ id: p.user_id, user_type: p.user_type || 'company_user' }))}
                      onToggle={(u) => {
                        const existing = parts.find(p => String(p.user_id) === String(u.id));
                        if (existing) {
                          if (existing.id) removeParticipant(m.id, existing.id, existing.user_id, existing.full_name);
                        } else {
                          addParticipant(m.id, u);
                        }
                      }}
                    />
                  </div>
                )}
              </div>
            );
          })()}
        </DialogContent>
      </Dialog>

      {/* ── Notes modal ── */}
      <Dialog open={notesModalOpen && !!openMeeting} onOpenChange={setNotesModalOpen}>
        <DialogContent
          className="max-w-lg w-full bg-[#0d0b1f] border-white/10 text-white p-0 gap-0"
          style={{ maxHeight: '90vh', display: 'flex', flexDirection: 'column' }}
        >
          {openMeeting && (() => {
            const m = openMeeting;
            const notes = meetingNotes[m.id];
            return (
              <>
                <div className="flex items-center justify-between px-6 py-4 pr-14 border-b border-white/10 flex-shrink-0">
                  <div className="flex items-center gap-2 min-w-0">
                    <FileText className="h-4 w-4 text-sky-300 flex-shrink-0" />
                    <h3 className="text-white font-semibold text-sm truncate">Notes — {m.title}</h3>
                  </div>
                  {notes && (
                    <HoverTip tip="Clear all notes, decisions and action items">
                      <button type="button" onClick={() => clearMeetingNotes(m.id)}
                        className="text-[10px] text-white/30 hover:text-red-400 inline-flex items-center gap-1 transition-colors flex-shrink-0 ml-3">
                        <Trash2 className="h-3 w-3" /> Clear
                      </button>
                    </HoverTip>
                  )}
                </div>

                <div className="flex-1 overflow-y-auto no-scrollbar px-6 py-5 space-y-3">
                  {notes && (
                    <div className="space-y-2">
                      {notes.ai_summary && (
                        <div className="rounded-xl p-3 bg-violet-500/10 border-b border-violet-500/20">
                          <p className="text-violet-300 text-xs font-semibold mb-1">AI Summary</p>
                          <p className="text-white/80 text-xs whitespace-pre-wrap">{notes.ai_summary}</p>
                        </div>
                      )}
                      {Array.isArray(notes.key_decisions) && notes.key_decisions.length > 0 && (
                        <div className="rounded-xl p-3 border-b border-white/10">
                          <p className="text-white/60 text-xs font-semibold mb-1">Key Decisions</p>
                          {notes.key_decisions.map((d, i) => (
                            <p key={i} className="text-white/70 text-xs">• {d}</p>
                          ))}
                        </div>
                      )}
                      {Array.isArray(notes.action_items) && notes.action_items.length > 0 && (
                        <div className="rounded-xl p-3 border-b border-white/10">
                          <p className="text-white/60 text-xs font-semibold mb-2">Action Items ({notes.action_items.length})</p>
                          <div className="space-y-1.5">
                            {notes.action_items.map((a, i) => {
                              const titleMatch = Array.isArray(notes.converted_titles)
                                && notes.converted_titles.includes((a.title || '').trim().toLowerCase());
                              const converted = (a.id && convertedActionItemIds?.has(a.id)) || titleMatch;
                              return (
                                <div key={a.id ?? i} className="flex items-center gap-2">
                                  <div className="flex-1 min-w-0">
                                    <p className="text-xs text-white/75">
                                      • {a.title}
                                      {a.due_date ? <span className="text-white/40"> · {a.due_date}</span> : ''}
                                    </p>
                                  </div>
                                  {a.id && (converted ? (
                                    <span className="text-[10px] text-violet-300/80 flex-shrink-0 flex items-center gap-1"><Check className="h-3 w-3" /> Task created</span>
                                  ) : (
                                    <HoverTip tip="Create a task from this action item">
                                      <button type="button" onClick={() => convertActionItem(m.id, a.id)}
                                        className="flex items-center gap-1 text-[10px] text-violet-300 hover:text-violet-200 border border-violet-500/40 hover:bg-violet-500/10 rounded px-1.5 py-0.5 flex-shrink-0 transition-colors">
                                        <Plus className="h-3 w-3" /> Convert to task
                                      </button>
                                    </HoverTip>
                                  ))}
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Transcript input */}
                  <div className="space-y-2">
                    <Label className="text-white/60 text-xs">
                      {notes ? 'Update Transcript (re-generate notes)' : 'Paste Meeting Transcript'}
                    </Label>
                    <textarea
                      value={notesOpenId === m.id ? transcriptInput : ''}
                      onChange={e => setTranscriptInput(e.target.value)}
                      rows={4}
                      placeholder="Paste the meeting transcript or key discussion notes here…"
                      className="w-full rounded-md px-3 py-2 text-xs text-white placeholder:text-white/25 bg-white/5 border border-white/10 resize-none focus:outline-none focus:ring-1 focus:ring-violet-500"
                    />
                    <HoverTip tip="after adding a transcript, extract summary and action items with AI">
                      <Button size="sm" onClick={() => submitTranscript(m.id)} disabled={notesLoading}
                        className="bg-violet-600 hover:bg-violet-700 text-white">
                        {notesLoading ? <><Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />Processing…</> : <><FileText className="h-3.5 w-3.5 mr-1.5" />Generate Notes with AI</>}
                      </Button>
                    </HoverTip>
                  </div>
                </div>
              </>
            );
          })()}
        </DialogContent>
      </Dialog>
    </div>
  );
};
