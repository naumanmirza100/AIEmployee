import React, { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import MacroPickerDialog from './MacroPickerDialog';
import { labelOf } from '@/utils/labels';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { useToast } from '@/components/ui/use-toast';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Loader2, Trash2, Headphones, CheckCircle2, Send, Plus, RefreshCw,
  Sparkles, User, BookOpen, Paperclip, RotateCcw,
} from 'lucide-react';
import { HINTS } from './frontlineTutorialSteps';
import InfoHint from './InfoHint';
import { trackRecentlyViewed } from './frontlineLocalStore';
import frontlineAgentService from '@/services/frontlineAgentService';

// ============================================================================
// Hand-off queue tab (Phase 3 Batch 4 — UI)
// Lists pending + accepted hand-offs, opens a drawer with the ticket thread,
// an LLM-drafted reply button, and "Send reply" / "Accept hand-off" actions.
// ============================================================================
export function HandoffQueueTab() {
  const { toast } = useToast();
  const [statusFilter, setStatusFilter] = useState('pending');
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [mine, setMine] = useState(false);
  // Drawer state for the currently-open hand-off.
  const [drawer, setDrawer] = useState({
    open: false, ticket: null, messages: [], loading: false,
    reply: '', sending: false, suggesting: false, accepting: false,
  });
  // Macro picker — opens when the agent wants a canned reply.
  const [macroOpen, setMacroOpen] = useState(false);
  // Ticket-link state for the open drawer: existing links + the in-progress
  // form for creating a new one. Reloaded each time the drawer opens.
  const [ticketLinks, setTicketLinks] = useState([]);
  const [ticketLinksLoading, setTicketLinksLoading] = useState(false);
  const [newLink, setNewLink] = useState({ relation: 'related', toTicketId: '' });
  const [creatingLink, setCreatingLink] = useState(false);

  // Customer-submitted widget attachments (images, PDFs, etc.) for the open
  // ticket. Loaded lazily when the drawer opens — the list endpoint walks
  // the per-company upload directory and returns rows shaped like
  // `{ name, size, stored_filename }`. The stored_filename is what the
  // download URL needs.
  const [widgetAttachments, setWidgetAttachments] = useState([]);
  const [widgetAttachmentsLoading, setWidgetAttachmentsLoading] = useState(false);

  const loadWidgetAttachments = async (ticketId) => {
    if (!ticketId) return;
    setWidgetAttachmentsLoading(true);
    try {
      const res = await frontlineAgentService.listWidgetAttachments(ticketId);
      setWidgetAttachments((res?.data) || []);
    } catch (e) {
      console.warn('Load widget attachments failed', e);
      setWidgetAttachments([]);
    } finally {
      setWidgetAttachmentsLoading(false);
    }
  };

  const formatAttachmentSize = (n) => {
    if (typeof n !== 'number' || n < 0) return '';
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / 1024 / 1024).toFixed(1)} MB`;
  };

  const loadTicketLinks = async (ticketId) => {
    if (!ticketId) return;
    setTicketLinksLoading(true);
    try {
      const res = await frontlineAgentService.listTicketLinks(ticketId);
      setTicketLinks((res?.data) || []);
    } catch (e) {
      console.warn('Load ticket links failed', e);
      setTicketLinks([]);
    } finally {
      setTicketLinksLoading(false);
    }
  };

  const handleCreateTicketLink = async () => {
    const toId = parseInt(String(newLink.toTicketId).trim(), 10);
    if (!drawer.ticket || !toId) {
      toast({ title: 'Pick a target ticket', description: 'Enter the ID of the ticket you want to link to.', variant: 'destructive' });
      return;
    }
    setCreatingLink(true);
    try {
      await frontlineAgentService.createTicketLink(drawer.ticket.id, {
        to_ticket_id: toId, relation: newLink.relation,
      });
      toast({ title: 'Linked' });
      setNewLink({ relation: 'related', toTicketId: '' });
      await loadTicketLinks(drawer.ticket.id);
    } catch (e) {
      toast({ title: 'Link failed', description: e?.response?.data?.message || e.message, variant: 'destructive' });
    } finally {
      setCreatingLink(false);
    }
  };

  const handleDeleteTicketLink = async (linkId) => {
    try {
      await frontlineAgentService.deleteTicketLink(linkId);
      setTicketLinks((rows) => rows.filter((l) => l.id !== linkId));
    } catch (e) {
      toast({ title: 'Delete failed', description: e.message, variant: 'destructive' });
    }
  };

  // Reassign / Release support — handoffs to colleagues.
  // We lazy-load the company-user list the first time the reassign popover opens.
  const [reassignPopover, setReassignPopover] = useState({ open: false, candidates: [], loading: false });
  const [releasingHandoff, setReleasingHandoff] = useState(false);
  const [reassigningHandoff, setReassigningHandoff] = useState(false);

  const openReassignPopover = async () => {
    setReassignPopover({ open: true, candidates: [], loading: true });
    try {
      const res = await frontlineAgentService.listWorkflowCompanyUsers();
      const data = (res?.data) || [];
      setReassignPopover({ open: true, candidates: data, loading: false });
    } catch (e) {
      setReassignPopover({ open: false, candidates: [], loading: false });
      toast({ title: 'Failed to load agents', description: e.message, variant: 'destructive' });
    }
  };

  const handleReleaseHandoff = async () => {
    if (!drawer.ticket) return;
    setReleasingHandoff(true);
    try {
      await frontlineAgentService.releaseHandoff(drawer.ticket.id);
      toast({ title: 'Released', description: 'Hand-off returned to the pending pool.' });
      setDrawer((prev) => ({ ...prev, open: false }));
      load();
    } catch (e) {
      toast({ title: 'Release failed', description: e?.response?.data?.message || e.message, variant: 'destructive' });
    } finally {
      setReleasingHandoff(false);
    }
  };

  const handleReassignHandoff = async (cu) => {
    if (!drawer.ticket || !cu) return;
    setReassigningHandoff(true);
    try {
      await frontlineAgentService.reassignHandoff(drawer.ticket.id, cu.id);
      toast({ title: 'Reassigned', description: `Hand-off transferred to ${cu.full_name || cu.username || cu.email}.` });
      setReassignPopover({ open: false, candidates: [], loading: false });
      setDrawer((prev) => ({ ...prev, open: false }));
      load();
    } catch (e) {
      toast({ title: 'Reassign failed', description: e?.response?.data?.message || e.message, variant: 'destructive' });
    } finally {
      setReassigningHandoff(false);
    }
  };
  // One-click assign to the suggested colleague (see Frontline_agent/routing.py).
  const [assigningId, setAssigningId] = useState(null);
  const assignSuggested = async (t) => {
    const who = t.suggested_assignee;
    if (!who) return;
    setAssigningId(t.id);
    try {
      await frontlineAgentService.reassignHandoff(t.id, who.id);
      toast({ title: 'Assigned', description: `${who.name} has the hand-off.` });
      load();
    } catch (e) {
      toast({ title: 'Assign failed', description: e?.response?.data?.message || e.message, variant: 'destructive' });
    } finally {
      setAssigningId(null);
    }
  };
  const handleMacroInsert = (body) => {
    setDrawer((prev) => {
      const cur = prev.reply || '';
      // Append to existing draft when there is one, otherwise replace.
      const sep = cur.trim() ? '\n\n' : '';
      return { ...prev, reply: cur + sep + body };
    });
  };

  const load = async () => {
    setLoading(true);
    try {
      const res = await frontlineAgentService.listHandoffQueue({
        status: statusFilter,
        mine: mine,
      });
      setRows((res.status === 'success' && Array.isArray(res.data)) ? res.data : []);
    } catch (e) {
      toast({ title: 'Error', description: e.message || 'Failed to load hand-offs', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, [statusFilter, mine]);

  const openTicket = async (ticket) => {
    // Remember this hand-off for the "Recently viewed" strip in Quick Chat.
    trackRecentlyViewed({
      kind: 'ticket',
      id: ticket.id,
      title: ticket.title || `Ticket #${ticket.id}`,
      meta: ticket.priority || '',
    });
    setDrawer({
      open: true, ticket, messages: [], loading: true,
      reply: '', sending: false, suggesting: false, accepting: false,
    });
    setTicketLinks([]);
    setNewLink({ relation: 'related', toTicketId: '' });
    setWidgetAttachments([]);
    loadTicketLinks(ticket.id);
    loadWidgetAttachments(ticket.id);
    try {
      const res = await frontlineAgentService.listTicketMessages(ticket.id);
      setDrawer((prev) => ({
        ...prev,
        messages: (res?.data) || [],
        loading: false,
      }));
    } catch (e) {
      console.error('Load thread failed', e);
      setDrawer((prev) => ({ ...prev, loading: false }));
      toast({ title: 'Failed to load thread', variant: 'destructive' });
    }
  };

  const handleSuggest = async () => {
    if (!drawer.ticket) return;
    setDrawer((prev) => ({ ...prev, suggesting: true }));
    try {
      const res = await frontlineAgentService.suggestTicketReply(drawer.ticket.id);
      const draft = (res?.data?.draft || '').trim();
      if (!draft) {
        toast({ title: 'No draft returned', variant: 'destructive' });
      } else {
        setDrawer((prev) => ({ ...prev, reply: draft }));
      }
    } catch (e) {
      toast({ title: 'Draft failed', description: e.message || 'LLM error', variant: 'destructive' });
    } finally {
      setDrawer((prev) => ({ ...prev, suggesting: false }));
    }
  };

  const handleAccept = async () => {
    if (!drawer.ticket) return;
    setDrawer((prev) => ({ ...prev, accepting: true }));
    try {
      const res = await frontlineAgentService.acceptHandoff(drawer.ticket.id);
      if (res?.status === 'success' && res.data) {
        setDrawer((prev) => ({ ...prev, ticket: res.data }));
        setRows((list) => list.map((r) => (r.id === res.data.id ? res.data : r)));
        toast({ title: 'Hand-off accepted' });
      }
    } catch (e) {
      toast({ title: 'Accept failed', description: e.message || 'Error', variant: 'destructive' });
    } finally {
      setDrawer((prev) => ({ ...prev, accepting: false }));
    }
  };

  const handleSend = async () => {
    if (!drawer.ticket) return;
    const body = drawer.reply.trim();
    if (!body) {
      toast({ title: 'Reply is empty', variant: 'destructive' });
      return;
    }
    setDrawer((prev) => ({ ...prev, sending: true }));
    try {
      const res = await frontlineAgentService.replyToTicket(drawer.ticket.id, { body_text: body });
      if (res?.status === 'success' && res.data) {
        setDrawer((prev) => ({
          ...prev,
          messages: [...prev.messages, res.data],
          reply: '',
        }));
        toast({ title: 'Reply sent' });
      }
    } catch (e) {
      toast({ title: 'Send failed', description: e.message || 'Error', variant: 'destructive' });
    } finally {
      setDrawer((prev) => ({ ...prev, sending: false }));
    }
  };

  const reasonLabel = (r) => ({
    low_confidence: 'Low AI confidence',
    customer_requested: 'Customer asked for a human',
    manual_escalation: 'Manual escalation',
    sla_risk: 'SLA at risk',
  }[r] || r || '—');

  return (
    <div className="space-y-4">
      {/* Filter bar */}
      <div data-tour-handoffs="filters" className="flex flex-wrap items-center gap-2">
        <InfoHint {...HINTS.handoffsFilters} />
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-40">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="pending">Pending</SelectItem>
            <SelectItem value="accepted">Accepted</SelectItem>
            <SelectItem value="all">All</SelectItem>
          </SelectContent>
        </Select>
        <label className="flex items-center gap-2 text-sm select-none">
          <Checkbox
            checked={mine}
            onCheckedChange={(v) => setMine(Boolean(v))}
          />
          Only mine
        </label>
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          <span className="ml-2">Refresh</span>
        </Button>
        <span className="text-sm text-muted-foreground ml-auto">{rows.length} ticket{rows.length === 1 ? '' : 's'}</span>
      </div>

      {/* Queue table */}
      <div className="flex items-center gap-1.5">
        <span className="text-xs uppercase tracking-wider text-muted-foreground font-semibold">Queue</span>
        <InfoHint {...HINTS.handoffsQueue} />
      </div>
      <div data-tour-handoffs="queue" className="overflow-x-auto -mx-2 sm:mx-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Title</TableHead>
              <TableHead>Customer</TableHead>
              <TableHead>Reason</TableHead>
              <TableHead>Requested</TableHead>
              <TableHead>Priority</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={6} className="text-center py-8">
                  <Loader2 className="h-5 w-5 animate-spin inline-block text-muted-foreground" />
                </TableCell>
              </TableRow>
            ) : rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-sm text-muted-foreground py-10">
                  No {statusFilter === 'all' ? '' : statusFilter} hand-offs.
                </TableCell>
              </TableRow>
            ) : (
              rows.map((t) => (
                <TableRow key={t.id}>
                  <TableCell className="max-w-[28ch] truncate" title={t.title}>{t.title}</TableCell>
                  <TableCell>
                    {t.contact ? (
                      <span className="text-sm">
                        <span className="font-medium">{t.contact.name || t.contact.email}</span>
                        {t.contact.name && (
                          <span className="text-xs text-muted-foreground"> · {t.contact.email}</span>
                        )}
                      </span>
                    ) : <span className="text-muted-foreground">—</span>}
                  </TableCell>
                  <TableCell><Badge variant="secondary" className="text-xs">{reasonLabel(t.handoff_reason)}</Badge></TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {t.handoff_requested_at ? new Date(t.handoff_requested_at).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' }) : '—'}
                  </TableCell>
                  <TableCell><Badge variant="outline" className="text-xs">{labelOf(t.priority)}</Badge></TableCell>
                  <TableCell className="text-right">
                    <div className="flex flex-wrap items-center justify-end gap-2">
                      {/* Best placed to take it right now: free on the shared calendar,
                          on the Frontline team, fewest open tickets. One click assigns. */}
                      {t.handoff_status === 'pending' && t.suggested_assignee && (
                        <Button size="sm" variant="secondary" disabled={assigningId === t.id}
                          title={`Suggested: ${t.suggested_assignee.reason}`}
                          onClick={() => assignSuggested(t)}>
                          {assigningId === t.id ? 'Assigning…' : `Assign to ${t.suggested_assignee.name}`}
                        </Button>
                      )}
                      <Button size="sm" variant="outline" onClick={() => openTicket(t)}>
                        Open
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {/* Hand-off detail drawer (dialog) */}
      <Dialog open={drawer.open} onOpenChange={(open) => setDrawer((prev) => ({ ...prev, open }))}>
        <DialogContent className="max-w-3xl max-h-[90vh] flex flex-col">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Headphones className="h-5 w-5 text-violet-400" />
              <span className="truncate">{drawer.ticket?.title || 'Hand-off'}</span>
            </DialogTitle>
            <DialogDescription>
              {drawer.ticket ? (
                <span className="flex flex-wrap items-center gap-2 text-xs">
                  <Badge variant="secondary">{reasonLabel(drawer.ticket.handoff_reason)}</Badge>
                  <Badge variant="outline">{labelOf(drawer.ticket.handoff_status)}</Badge>
                  {drawer.ticket.contact && (
                    <span className="text-muted-foreground">
                      · {drawer.ticket.contact.name || drawer.ticket.contact.email}
                    </span>
                  )}
                </span>
              ) : null}
            </DialogDescription>
          </DialogHeader>

          {/* Handoff context from AI (question, AI answer, score) */}
          {drawer.ticket?.handoff_context && Object.keys(drawer.ticket.handoff_context).length > 0 && (
            <div className="rounded-md border border-border/50 bg-muted/30 p-3 text-xs space-y-1">
              {drawer.ticket.handoff_context.question && (
                <div><span className="text-muted-foreground">Question:</span> {drawer.ticket.handoff_context.question}</div>
              )}
              {drawer.ticket.handoff_context.ai_answer && (
                <div className="line-clamp-3"><span className="text-muted-foreground">AI answer:</span> {drawer.ticket.handoff_context.ai_answer}</div>
              )}
              {drawer.ticket.handoff_context.best_score != null && (
                <div>
                  <span className="text-muted-foreground">Score:</span> {drawer.ticket.handoff_context.best_score}
                  {drawer.ticket.handoff_context.threshold != null && (
                    <span className="text-muted-foreground"> (threshold {drawer.ticket.handoff_context.threshold})</span>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Thread */}
          <div className="flex-1 overflow-y-auto space-y-3 py-2 min-h-0">
            {drawer.loading ? (
              <div className="flex justify-center py-6">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : drawer.messages.length === 0 ? (
              <div className="text-center text-sm text-muted-foreground py-8">
                No messages on this ticket yet.
                {drawer.ticket?.handoff_context?.question && (
                  <div className="text-xs mt-2">Customer's original question appears in the context panel above.</div>
                )}
              </div>
            ) : drawer.messages.map((m) => (
              <div
                key={m.id}
                className={`rounded-md border p-3 text-sm ${m.direction === 'inbound'
                  ? 'border-border/50 bg-muted/40'
                  : 'border-violet-500/30 bg-violet-500/5'
                }`}
              >
                <div className="flex items-center justify-between gap-2 text-xs mb-1">
                  <span className="font-medium">
                    {m.direction === 'inbound' ? (m.from_name || m.from_address || 'Customer') : 'Agent'}
                  </span>
                  <span className="text-muted-foreground">
                    {m.created_at ? new Date(m.created_at).toLocaleString() : ''}
                  </span>
                </div>
                <div className="whitespace-pre-wrap break-words">{m.body_text || m.subject}</div>
              </div>
            ))}
          </div>

          {/* Customer-uploaded attachments from the public widget. Files are
              auth-gated server-side and stored under the company directory;
              the link below opens an inline-served stream (images / PDFs
              preview, binaries download). */}
          {(widgetAttachments.length > 0 || widgetAttachmentsLoading) && (
            <div className="space-y-2 pt-2 border-t border-border/50">
              <div className="flex items-center justify-between">
                <Label className="text-xs uppercase tracking-wider text-muted-foreground">Customer attachments</Label>
                {widgetAttachmentsLoading && <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />}
              </div>
              {widgetAttachments.length > 0 && (
                <div className="space-y-1">
                  {widgetAttachments.map((a) => (
                    <a
                      key={a.stored_filename}
                      href={frontlineAgentService.widgetAttachmentDownloadUrl(drawer.ticket.id, a.stored_filename)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-2 text-xs rounded border border-border/40 bg-muted/30 px-2 py-1.5 hover:bg-muted/50 transition-colors"
                    >
                      <Paperclip className="h-3 w-3 text-muted-foreground shrink-0" />
                      <span className="truncate flex-1">{a.name}</span>
                      {typeof a.size === 'number' && (
                        <span className="text-muted-foreground shrink-0">{formatAttachmentSize(a.size)}</span>
                      )}
                    </a>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Linked tickets — pick a relation + target ticket ID to annotate
              cross-ticket relationships. Backend stores them in TicketLink and
              the relation drives downstream automation (e.g. closing a parent
              cascades to children). */}
          <div className="space-y-2 pt-2 border-t border-border/50">
            <div className="flex items-center justify-between">
              <Label className="text-xs uppercase tracking-wider text-muted-foreground">Linked tickets</Label>
              {ticketLinksLoading && <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />}
            </div>
            {ticketLinks.length > 0 && (
              <div className="space-y-1">
                {ticketLinks.map((l) => (
                  <div key={l.id} className="flex items-center gap-2 text-xs rounded border border-border/40 bg-muted/30 px-2 py-1">
                    <Badge variant="secondary" className="text-[10px] shrink-0">
                      {(frontlineAgentService.TICKET_LINK_RELATIONS.find((r) => r.value === l.relation) || {}).label || l.relation}
                    </Badge>
                    <span className="truncate flex-1">
                      #{l.other_ticket?.id ?? l.to_ticket?.id ?? l.from_ticket?.id} —{' '}
                      {l.other_ticket?.title || l.to_ticket?.title || l.from_ticket?.title || 'Untitled'}
                    </span>
                    <Button size="icon" variant="ghost" className="h-6 w-6 text-destructive hover:text-destructive shrink-0"
                            onClick={() => handleDeleteTicketLink(l.id)} title="Remove link">
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </div>
                ))}
              </div>
            )}
            <div className="flex items-center gap-2">
              <Select value={newLink.relation} onValueChange={(v) => setNewLink((n) => ({ ...n, relation: v }))}>
                <SelectTrigger className="w-[160px] h-8 text-xs"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {frontlineAgentService.TICKET_LINK_RELATIONS.map((r) => (
                    <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Input
                type="number"
                inputMode="numeric"
                placeholder="Ticket ID"
                className="h-8 w-32 text-xs"
                value={newLink.toTicketId}
                onChange={(e) => setNewLink((n) => ({ ...n, toTicketId: e.target.value }))}
              />
              <Button size="sm" variant="outline" onClick={handleCreateTicketLink} disabled={creatingLink || !newLink.toTicketId}>
                {creatingLink ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : <Plus className="h-3 w-3 mr-1" />}
                Link
              </Button>
            </div>
          </div>

          {/* Reply box + actions */}
          <div className="space-y-2 pt-2 border-t border-border/50">
            <Textarea
              value={drawer.reply}
              onChange={(e) => setDrawer((prev) => ({ ...prev, reply: e.target.value }))}
              placeholder="Type your reply, or click 'Suggest reply' for an AI draft..."
              rows={5}
            />
            <div className="flex items-center gap-2 flex-wrap">
              <Button
                variant="outline"
                size="sm"
                onClick={handleSuggest}
                disabled={drawer.suggesting || drawer.sending}
              >
                {drawer.suggesting
                  ? <Loader2 className="h-4 w-4 animate-spin mr-1" />
                  : <Sparkles className="h-4 w-4 mr-1" />}
                Suggest reply
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setMacroOpen(true)}
                disabled={drawer.sending}
                title="Insert a saved reply"
              >
                <BookOpen className="h-4 w-4 mr-1" /> Macros
              </Button>
              {drawer.ticket?.handoff_status === 'pending' && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleAccept}
                  disabled={drawer.accepting}
                >
                  {drawer.accepting
                    ? <Loader2 className="h-4 w-4 animate-spin mr-1" />
                    : <CheckCircle2 className="h-4 w-4 mr-1" />}
                  Accept hand-off
                </Button>
              )}
              {/* Release returns the handoff to the unowned pending pool.
                  Only meaningful on accepted handoffs (the endpoint 400s
                  otherwise). Reassign explicitly transfers to another
                  agent and works on either pending or accepted. */}
              {drawer.ticket?.handoff_status === 'accepted' && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleReleaseHandoff}
                  disabled={releasingHandoff}
                  title="Send back to the unowned queue"
                >
                  {releasingHandoff
                    ? <Loader2 className="h-4 w-4 animate-spin mr-1" />
                    : <RotateCcw className="h-4 w-4 mr-1" />}
                  Release
                </Button>
              )}
              {(drawer.ticket?.handoff_status === 'pending' || drawer.ticket?.handoff_status === 'accepted') && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={openReassignPopover}
                  disabled={reassigningHandoff}
                  title="Hand off to a specific other agent"
                >
                  <User className="h-4 w-4 mr-1" /> Reassign…
                </Button>
              )}
              <div className="ml-auto">
                {/* FRONTLINE-BUG-06: KB-gap tickets are created internally
                    when the widget can't answer a public question and have
                    no customer to email back — "Send reply" always fails
                    with "No recipient available" on those. Detect that
                    shape and disable the button (with a tooltip explaining
                    why) instead of letting the click round-trip and toast
                    the raw error. */}
                {(() => {
                  const t = drawer.ticket;
                  const isInternalKbGap = !!t && (
                    t.category === 'knowledge_gap' &&
                    !t.contact &&
                    !t.contact_email &&
                    !t.customer_email
                  );
                  return (
                    <Button
                      onClick={handleSend}
                      disabled={drawer.sending || !drawer.reply.trim() || isInternalKbGap}
                      title={isInternalKbGap
                        ? "This is an internal knowledge-gap ticket with no customer to reply to. Add an internal note or resolve it instead."
                        : undefined}
                    >
                      {drawer.sending
                        ? <Loader2 className="h-4 w-4 animate-spin mr-1" />
                        : <Send className="h-4 w-4 mr-1" />}
                      {isInternalKbGap ? 'No recipient' : 'Send reply'}
                    </Button>
                  );
                })()}
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <MacroPickerDialog open={macroOpen}
        onOpenChange={setMacroOpen}
        onInsert={handleMacroInsert} />

      {/* Reassign-handoff picker. Opens when "Reassign…" is clicked in the
          drawer; lists company users and assigns the ticket directly to the
          picked one. */}
      <Dialog open={reassignPopover.open} onOpenChange={(open) => !open && !reassigningHandoff && setReassignPopover({ open: false, candidates: [], loading: false })}>
        <DialogContent className="max-w-md max-h-[70vh] flex flex-col">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <User className="h-4 w-4" /> Reassign hand-off
            </DialogTitle>
            <DialogDescription>
              Pick the agent to hand this ticket to. They'll see it in their own queue immediately.
            </DialogDescription>
          </DialogHeader>
          <div className="overflow-y-auto min-h-0 flex-1 space-y-1">
            {reassignPopover.loading ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground py-4">
                <Loader2 className="h-4 w-4 animate-spin" /> Loading agents…
              </div>
            ) : reassignPopover.candidates.length === 0 ? (
              <p className="text-sm text-muted-foreground py-4 text-center">No agents available in your company.</p>
            ) : (
              reassignPopover.candidates.map((cu) => (
                <Button
                  key={cu.id}
                  variant="ghost"
                  size="sm"
                  disabled={reassigningHandoff}
                  className="w-full justify-start"
                  onClick={() => handleReassignHandoff(cu)}
                >
                  <User className="h-3.5 w-3.5 mr-2 text-muted-foreground shrink-0" />
                  <div className="flex-1 min-w-0 text-left">
                    <div className="truncate">{cu.full_name || cu.username || cu.email}</div>
                    {cu.email && <div className="text-xs text-muted-foreground truncate">{cu.email}</div>}
                  </div>
                  {reassigningHandoff && <Loader2 className="h-3 w-3 animate-spin ml-2" />}
                </Button>
              ))
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setReassignPopover({ open: false, candidates: [], loading: false })} disabled={reassigningHandoff}>
              Cancel
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
