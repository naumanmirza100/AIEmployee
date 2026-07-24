// Documents panel (AI document generator + saved docs) — extracted from
// ExecMeetingDashboard.jsx. Stateless: all state + handlers via props.

import React from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Loader2, FileText, RefreshCw, Trash2, MoreHorizontal,
} from 'lucide-react';
import { CARD_STYLE, ROW_STYLE, EmptyState, fmtUtc, BulkSelectBar, SelectCheckbox, FilterBar, Pagination } from '../shared';

const DOC_TYPE_LABELS = { agenda: 'Agenda', minutes: 'Minutes', briefing: 'Briefing', report: 'Report', other: 'Other' };
const DOC_TYPE_FILTER_OPTIONS = [
  { value: 'agenda', label: 'Agenda' },
  { value: 'minutes', label: 'Minutes' },
  { value: 'briefing', label: 'Briefing' },
  { value: 'report', label: 'Report' },
  { value: 'other', label: 'Other' },
];
const DOC_TYPE_COLORS = {
  agenda:   'bg-violet-500/20 text-violet-300 border-violet-500/30',
  minutes:  'bg-sky-500/20 text-sky-300 border-sky-500/30',
  briefing: 'bg-amber-500/20 text-amber-300 border-amber-500/30',
  report:   'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
  other:    'bg-white/10 text-white/50 border-white/10',
};

export const DocumentsPanel = ({
  aiDocType, aiDocMeetingId, meetings, aiDocInput, aiDocTopics, aiDocSummary,
  aiDocContext, aiDocAudience, aiDocPeriod, aiDocLoading, docsLoading, savedDocs,
  setAiDocType, setAiDocTopics, setAiDocSummary, setAiDocContext, setAiDocAudience,
  setAiDocPeriod, setAiDocMeetingId, setAiDocInput,
  generateAiDoc, loadDocuments, applyMeetingNotesToDoc, setViewDoc, downloadDocPdf, deleteDoc,
  selectedDocIds, toggleSelected, setSelectedDocIds, bulkDeleteDocs, bulkDeleting,
  filters = {}, setFilters = () => {},
  pageMeta = null, onPageChange = () => {},
}) => {
  const filtersActive = !!(filters.search || filters.doc_type || filters.date);
  return (
    <div className="space-y-6">
      {/* ── PART 1: Generator (inputs) ─────────────────────────────────── */}
      <div data-tour-em="docs-create">
        <div className="flex items-center gap-2 mb-2 px-1">
          <span className="h-5 w-5 rounded-full bg-violet-500/20 border border-violet-500/40 flex items-center justify-center text-violet-300 text-[11px] font-bold">1</span>
          <p className="text-white/70 text-xs font-semibold uppercase tracking-wide">Create a document</p>
        </div>
        <div className="rounded-2xl p-5 space-y-4 border border-violet-500/20" style={{ ...CARD_STYLE, background: 'rgba(162,89,255,0.05)' }}>
          <h3 className="text-white font-semibold flex items-center gap-2">
            <FileText className="h-4 w-4 text-violet-400" />
            Generate Document with AI
          </h3>

        {/* Row 1: Doc type + meeting picker */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-1">
            <Label className="text-white/70 text-xs">Document Type</Label>
            <Select value={aiDocType} onValueChange={v => {
              setAiDocType(v); setAiDocTopics(''); setAiDocSummary(''); setAiDocContext(''); setAiDocAudience(''); setAiDocPeriod('');
              // If a meeting is already linked, re-apply its data to the field
              // that the newly-chosen doc type uses.
              if (aiDocMeetingId) {
                if (v === 'minutes') {
                  applyMeetingNotesToDoc(aiDocMeetingId, 'minutes');
                } else if (v === 'agenda') {
                  const m = meetings.find(x => String(x.id) === String(aiDocMeetingId));
                  if (m) {
                    if (Array.isArray(m.agenda) && m.agenda.length > 0) setAiDocTopics(m.agenda.join(', '));
                    else if (m.description) setAiDocTopics(m.description);
                  }
                }
              }
            }}>
              <SelectTrigger className="bg-white/5 border-white/10 text-white">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="agenda">Meeting Agenda</SelectItem>
                <SelectItem value="minutes">Meeting Minutes</SelectItem>
                <SelectItem value="briefing">Executive Briefing</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1">
            <Label className="text-white/70 text-xs">Link to Saved Meeting <span className="text-white/30">(optional)</span></Label>
            <Select value={aiDocMeetingId || 'none'} onValueChange={v => {
              const val = v === 'none' ? '' : v;
              setAiDocMeetingId(val);
              if (val) {
                setAiDocInput('');
                // Pre-fill agenda "Topics to cover" from the selected meeting's
                // agenda (a topic list) or, failing that, its description.
                const m = meetings.find(x => String(x.id) === String(val));
                if (m && aiDocType === 'agenda') {
                  if (Array.isArray(m.agenda) && m.agenda.length > 0) {
                    setAiDocTopics(m.agenda.join(', '));
                  } else if (m.description) {
                    setAiDocTopics(m.description);
                  }
                }
                // For a Minutes doc, pull the meeting's AI Notes (summary,
                // decisions, action items) into the discussion-summary box.
                if (aiDocType === 'minutes') {
                  applyMeetingNotesToDoc(val, 'minutes');
                }
              }
            }}>
              <SelectTrigger className="bg-white/5 border-white/10 text-white">
                <SelectValue placeholder="— Select a meeting —" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">— None / manual topic —</SelectItem>
                {Array.isArray(meetings) && meetings.map(m => (
                  <SelectItem key={m.id} value={String(m.id)}>
                    {m.title}{m.scheduled_at ? ` · ${fmtUtc(m.scheduled_at)}` : ''}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {aiDocMeetingId && (() => {
              const m = meetings.find(x => String(x.id) === String(aiDocMeetingId));
              return m ? (
                <p className="text-xs text-violet-300/70 mt-1">
                  {m.attendees?.length ? `Attendees: ${m.attendees.slice(0,3).join(', ')}${m.attendees.length > 3 ? ` +${m.attendees.length - 3}` : ''}` : ''}
                  {m.duration_minutes ? `  ·  ${m.duration_minutes} min` : ''}
                </p>
              ) : null;
            })()}
          </div>
        </div>

        {/* Manual topic — shown only when no meeting selected */}
        {!aiDocMeetingId && (
          <div className="space-y-1">
            <Label className="text-white/70 text-xs">Meeting / Topic Title</Label>
            <Input
              value={aiDocInput}
              onChange={e => setAiDocInput(e.target.value)}
              placeholder="e.g. Q3 Strategy Review"
              className="bg-white/5 border-white/10 text-white"
            />
          </div>
        )}

        {/* Topics — agenda only */}
        {aiDocType === 'agenda' && (
          <div className="space-y-1">
            <Label className="text-white/70 text-xs">
              Topics to Cover <span className="text-white/30">(comma-separated)</span>
            </Label>
            <p className="text-[11px] text-amber-400/80 leading-snug">
              ⚠ Use short topic names only (e.g. "UI Review, Budget Update"). Do not paste meeting notes or long sentences — these become agenda headings.
            </p>
            <Input
              value={aiDocTopics}
              onChange={e => setAiDocTopics(e.target.value)}
              placeholder="e.g. Q3 results, Budget review, Hiring plan"
              className="bg-white/5 border-white/10 text-white"
            />
          </div>
        )}

        {/* Summary — minutes only */}
        {aiDocType === 'minutes' && (
          <div className="space-y-1">
            <div className="flex items-center justify-between">
              <Label className="text-white/70 text-xs">Meeting Summary / Key Discussion Points</Label>
              <span className={`text-xs ${aiDocSummary.length > 800 ? 'text-red-400' : aiDocSummary.length > 600 ? 'text-yellow-400' : 'text-white/30'}`}>
                {aiDocSummary.length}/800
              </span>
            </div>
            <p className="text-[11px] text-amber-400/80 leading-snug">
              ⚠ This text appears directly in the document as the Discussion Summary. Write only what was discussed in the meeting — do not paste unrelated content.
            </p>
            <textarea
              value={aiDocSummary}
              onChange={e => { if (e.target.value.length <= 800) setAiDocSummary(e.target.value); }}
              rows={5}
              placeholder="Briefly describe what was discussed, decisions made, outcomes…"
              className="w-full rounded-md px-3 py-2 text-sm text-white placeholder:text-white/30 bg-white/5 border border-white/10 resize-none focus:outline-none focus:ring-1 focus:ring-violet-500 [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]"
            />
          </div>
        )}

        {/* Briefing fields */}
        {aiDocType === 'briefing' && (
          <>
            <div className="space-y-1">
              <Label className="text-white/70 text-xs">Audience <span className="text-white/30">(optional)</span></Label>
              <Input
                value={aiDocAudience}
                onChange={e => setAiDocAudience(e.target.value)}
                placeholder="e.g. Board of Directors, Executive Team"
                className="bg-white/5 border-white/10 text-white"
              />
            </div>
            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <Label className="text-white/70 text-xs">Background / Context <span className="text-white/30">(optional)</span></Label>
                <span className={`text-xs ${aiDocContext.length > 800 ? 'text-red-400' : aiDocContext.length > 600 ? 'text-yellow-400' : 'text-white/30'}`}>
                  {aiDocContext.length}/800
                </span>
              </div>
              <p className="text-[11px] text-amber-400/80 leading-snug">
                ⚠ This text appears directly in the document. Write only relevant facts — do not paste raw research, chat logs, or unrelated content.
              </p>
              <textarea
                value={aiDocContext}
                onChange={e => { if (e.target.value.length <= 800) setAiDocContext(e.target.value); }}
                rows={5}
                placeholder="Describe the situation, problem, or opportunity. Key facts, risks, or data points to include…"
                className="w-full rounded-md px-3 py-2 text-sm text-white placeholder:text-white/30 bg-white/5 border border-white/10 resize-none focus:outline-none focus:ring-1 focus:ring-violet-500 [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]"
              />
            </div>
          </>
        )}

          <div className="flex justify-end">
            <Button onClick={generateAiDoc} disabled={aiDocLoading} style={{ background: 'linear-gradient(90deg, #a259ff 0%, #7c3aed 100%)' }} className="text-white border-0 hover:opacity-90">
              {aiDocLoading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <FileText className="h-4 w-4 mr-2" />}
              {aiDocLoading ? 'Generating…' : 'Generate & Save'}
            </Button>
          </div>
        </div>
      </div>

      {/* ── PART 2: Saved documents ────────────────────────────────────── */}
      <div data-tour-em="docs-saved">
        <div className="flex items-center gap-2 mb-2 px-1">
          <span className="h-5 w-5 rounded-full bg-sky-500/20 border border-sky-500/40 flex items-center justify-center text-sky-300 text-[11px] font-bold">2</span>
          <p className="text-white/70 text-xs font-semibold uppercase tracking-wide">Saved documents</p>
        </div>
        <div className="rounded-2xl overflow-hidden" style={CARD_STYLE}>
          <div className="flex items-center justify-between px-5 py-3 border-b border-white/10">
            <h3 className="text-white font-semibold text-sm flex items-center gap-2">
              <FileText className="h-3.5 w-3.5 text-violet-400" />
              Saved Documents
            </h3>
            <Button size="sm" variant="ghost" onClick={() => loadDocuments()} disabled={docsLoading} className="text-white/40 hover:text-white">
              <RefreshCw className={`h-3.5 w-3.5 ${docsLoading ? 'animate-spin' : ''}`} />
            </Button>
          </div>

          <div className="px-4 pt-3">
            <FilterBar
              search={filters.search || ''}
              onSearchChange={v => setFilters(f => ({ ...f, search: v }))}
              searchPlaceholder="Search documents…"
              selects={[
                {
                  value: filters.doc_type,
                  onChange: v => setFilters(f => ({ ...f, doc_type: v })),
                  placeholder: 'All types', allLabel: 'All types',
                  options: DOC_TYPE_FILTER_OPTIONS,
                },
              ]}
              date={filters.date}
              onDateChange={v => setFilters(f => ({ ...f, date: v }))}
              active={filtersActive}
              onClear={() => setFilters({ search: '', doc_type: '', date: '' })}
            />
          </div>

        {docsLoading ? (
          <div className="flex justify-center py-10"><Loader2 className="h-5 w-5 animate-spin text-violet-400" /></div>
        ) : !Array.isArray(savedDocs) || savedDocs.length === 0 ? (
          <EmptyState icon={FileText} label={filtersActive ? 'No documents match these filters' : 'No documents yet — generate one above'} />
        ) : (
          <>
          <div className="px-4 pt-2">
            <BulkSelectBar
              allIds={savedDocs.map(d => d.id)}
              selected={selectedDocIds}
              onToggleAll={() => setSelectedDocIds(selectedDocIds.size === savedDocs.length ? new Set() : new Set(savedDocs.map(d => d.id)))}
              onDelete={bulkDeleteDocs}
              deleting={bulkDeleting}
              label="document"
            />
          </div>
          {savedDocs.map(doc => (
            <div key={doc.id} className="flex items-center gap-4 px-5 py-3 hover:bg-white/[0.03] transition-colors" style={ROW_STYLE}>
              <SelectCheckbox
                checked={selectedDocIds.has(doc.id)}
                onChange={() => toggleSelected(setSelectedDocIds, doc.id)}
              />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                  <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] border ${DOC_TYPE_COLORS[doc.doc_type] || DOC_TYPE_COLORS.other}`}>
                    {DOC_TYPE_LABELS[doc.doc_type] || doc.doc_type}
                  </span>
                  <p className="text-white text-sm font-medium truncate">{doc.title}</p>
                </div>
                <p className="text-white/30 text-xs">{new Date(doc.created_at).toLocaleString()}</p>
              </div>
              <div className="flex items-center gap-1 flex-shrink-0">
                <Button size="sm" variant="ghost" onClick={() => setViewDoc(doc)}
                  className="text-violet-400 hover:text-violet-300 text-xs gap-1">
                  <FileText className="h-3.5 w-3.5" /> Open
                </Button>
                <Button size="sm" variant="ghost" onClick={() => downloadDocPdf(doc)}
                  className="text-sky-400 hover:text-sky-300 text-xs">
                  ⬇ PDF
                </Button>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button size="icon" variant="ghost" className="h-7 w-7 text-white/30 hover:text-white">
                      <MoreHorizontal className="h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent>
                    <DropdownMenuItem className="text-red-400" onClick={() => deleteDoc(doc.id)}>
                      <Trash2 className="h-4 w-4 mr-2" /> Delete
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            </div>
          ))}
          </>
        )}
        </div>
        <Pagination meta={pageMeta} onChange={onPageChange} itemLabel="document" />
      </div>
    </div>
  );
};
