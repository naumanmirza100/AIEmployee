/**
 * MacroPickerDialog — agent saved-replies / quick-reply picker.
 *
 * Opens from a "Macros" button in the ticket reply composer.
 *
 * Modes
 *   • pick (default) — searchable list with one-click-insert. A collapsible
 *     "+ New macro" panel sits ABOVE the list so creating a fresh macro
 *     never hides the existing ones (agents often want to copy structure
 *     from another macro while writing a new one).
 *   • edit            — focused single-macro form (replaces the list because
 *     editing is the focused task).
 *
 * Inline UX wins shipped here:
 *   - List stays visible while a new macro is being drafted.
 *   - When a search returns zero matches, the empty state offers
 *     "Create '<search>' as a new macro" with the name pre-filled.
 *   - Delete uses the shared `ConfirmDialog` instead of a native
 *     `window.confirm` so it matches the rest of the app's UX.
 *
 * Backend: TicketMacro CRUD endpoints (api/views/frontline_agent.py). On
 * insert, calls bumpTicketMacroUsage so most-used surfaces bubble up next
 * time.
 */
import React, { useEffect, useState } from 'react';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/components/ui/use-toast';
import {
  Loader2, Plus, Pencil, Trash2, ChevronLeft, Send, X,
} from 'lucide-react';
import {
  listTicketMacros, createTicketMacro, updateTicketMacro,
  deleteTicketMacro, bumpTicketMacroUsage,
} from '@/services/frontlineAgentService';
import ConfirmDialog from '@/components/common/ConfirmDialog';


export default function MacroPickerDialog({ open, onOpenChange, onInsert }) {
  const { toast } = useToast();
  // `mode` distinguishes the picking flow (with inline-create) from the
  // dedicated edit flow. Editing intentionally takes the whole content
  // area; creating intentionally keeps the list visible underneath.
  const [mode, setMode] = useState('pick'); // 'pick' | 'edit'
  const [macros, setMacros] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [editing, setEditing] = useState(null);
  const [editForm, setEditForm] = useState({ name: '', body: '' });

  // Inline-create panel state. `createOpen` toggles the visible form above
  // the list. We deliberately use separate state from `editForm` so a
  // half-typed create draft survives a search/scroll/edit interruption
  // without leaking into edit mode.
  const [createOpen, setCreateOpen] = useState(false);
  const [createForm, setCreateForm] = useState({ name: '', body: '' });
  const [creating, setCreating] = useState(false);
  const [savingEdit, setSavingEdit] = useState(false);

  // ConfirmDialog state for delete — replaces the native `window.confirm`.
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const res = await listTicketMacros({ activeOnly: true });
      setMacros(res?.data || []);
    } catch (e) {
      toast({ title: 'Failed to load macros', description: e.message, variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!open) return;
    setMode('pick');
    setEditing(null);
    setEditForm({ name: '', body: '' });
    setSearch('');
    setCreateOpen(false);
    setCreateForm({ name: '', body: '' });
    load();
  }, [open]);

  // Prefill the create form from the current search string when the user
  // clicks the empty-state CTA. Saves the "I searched X, didn't find it,
  // now I have to retype X as the macro name" friction.
  const openCreateFromSearch = () => {
    setCreateForm({ name: search.trim(), body: '' });
    setCreateOpen(true);
  };

  const openCreatePanel = () => {
    setCreateOpen(true);
    if (!createForm.name && !createForm.body) {
      setCreateForm({ name: '', body: '' });
    }
  };

  const cancelCreate = () => {
    setCreateOpen(false);
    setCreateForm({ name: '', body: '' });
  };

  const handleCreateSave = async () => {
    const name = createForm.name.trim();
    const body = createForm.body.trim();
    if (!name || !body) {
      toast({ title: 'Name and body are required', variant: 'destructive' });
      return;
    }
    setCreating(true);
    try {
      const res = await createTicketMacro({ name, body });
      const created = res?.data;
      setMacros((arr) => (created ? [created, ...arr] : arr));
      toast({ title: 'Macro created' });
      setCreateOpen(false);
      setCreateForm({ name: '', body: '' });
    } catch (e) {
      toast({ title: 'Save failed', description: e.message, variant: 'destructive' });
    } finally {
      setCreating(false);
    }
  };

  const openEdit = (m) => {
    setEditForm({ name: m.name, body: m.body });
    setEditing(m);
    setMode('edit');
  };

  const handleEditSave = async () => {
    if (!editing) return;
    const name = editForm.name.trim();
    const body = editForm.body.trim();
    if (!name || !body) {
      toast({ title: 'Name and body are required', variant: 'destructive' });
      return;
    }
    setSavingEdit(true);
    try {
      const res = await updateTicketMacro(editing.id, { name, body });
      setMacros((arr) => arr.map((m) => (m.id === editing.id ? (res?.data || m) : m)));
      toast({ title: 'Macro updated' });
      setMode('pick');
      setEditing(null);
    } catch (e) {
      toast({ title: 'Save failed', description: e.message, variant: 'destructive' });
    } finally {
      setSavingEdit(false);
    }
  };

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deleteTicketMacro(deleteTarget.id);
      setMacros((arr) => arr.filter((x) => x.id !== deleteTarget.id));
      toast({ title: 'Macro deleted' });
      setDeleteTarget(null);
    } catch (e) {
      toast({ title: 'Delete failed', description: e.message, variant: 'destructive' });
    } finally {
      setDeleting(false);
    }
  };

  const handleInsert = async (m) => {
    onInsert?.(m.body);
    // Best-effort usage bump; failure shouldn't block the insert.
    try { await bumpTicketMacroUsage(m.id); } catch { /* swallow */ }
    onOpenChange?.(false);
  };

  const filtered = macros.filter((m) => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return m.name.toLowerCase().includes(q) || m.body.toLowerCase().includes(q);
  });

  const isEditMode = mode === 'edit';

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-2xl max-h-[80vh] flex flex-col">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {isEditMode && (
                <Button variant="ghost" size="sm" className="h-7 px-2"
                  onClick={() => { setMode('pick'); setEditing(null); }}>
                  <ChevronLeft className="h-4 w-4" />
                </Button>
              )}
              {isEditMode ? 'Edit macro' : 'Saved replies (macros)'}
            </DialogTitle>
            <DialogDescription>
              {isEditMode
                ? 'Macros are company-wide. Use {{customer_name}} / {{ticket_title}} placeholders when you write them — the reply composer will leave them as-is.'
                : 'Quick-insert canned replies into the ticket composer. Click "Use" to insert.'}
            </DialogDescription>
          </DialogHeader>

          {isEditMode ? (
            // ── Edit mode: dedicated form, list hidden ─────────────────
            <div className="space-y-3 flex-1 overflow-y-auto">
              <div>
                <Label className="text-xs">Name</Label>
                <Input value={editForm.name}
                  onChange={(e) => setEditForm((s) => ({ ...s, name: e.target.value }))}
                  placeholder="e.g. Greeting / Refund decline / Ask for log files" />
              </div>
              <div className="flex-1 min-h-0">
                <Label className="text-xs">Body</Label>
                <Textarea rows={10} className="font-mono text-xs"
                  value={editForm.body}
                  onChange={(e) => setEditForm((s) => ({ ...s, body: e.target.value }))}
                  placeholder="Hi {{customer_name}},

Thanks for reaching out…" />
              </div>
            </div>
          ) : (
            // ── Pick mode: search + inline create panel + list ─────────
            <div className="flex-1 overflow-y-auto space-y-3">
              {/* Inline create panel — list stays visible underneath so
                  agents can reference an existing macro while drafting. */}
              {createOpen && (
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/[0.04] p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <Label className="text-xs font-semibold uppercase tracking-wider text-amber-300">New macro</Label>
                    <Button variant="ghost" size="icon" className="h-6 w-6"
                      onClick={cancelCreate} aria-label="Close new macro form">
                      <X className="h-3 w-3" />
                    </Button>
                  </div>
                  <div>
                    <Label className="text-xs">Name</Label>
                    <Input value={createForm.name}
                      onChange={(e) => setCreateForm((s) => ({ ...s, name: e.target.value }))}
                      placeholder="e.g. Refund decline" />
                  </div>
                  <div>
                    <Label className="text-xs">Body</Label>
                    <Textarea rows={5} className="font-mono text-xs"
                      value={createForm.body}
                      onChange={(e) => setCreateForm((s) => ({ ...s, body: e.target.value }))}
                      placeholder="Hi {{customer_name}}, …" />
                  </div>
                  <div className="flex justify-end gap-2">
                    <Button variant="ghost" size="sm" onClick={cancelCreate} disabled={creating}>Cancel</Button>
                    <Button size="sm" onClick={handleCreateSave} disabled={creating}>
                      {creating ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : <Plus className="h-3 w-3 mr-1" />}
                      Save macro
                    </Button>
                  </div>
                </div>
              )}

              <div className="flex items-center gap-2">
                <Input value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search macros…"
                  className="flex-1" />
                {!createOpen && (
                  <Button variant="outline" size="sm" onClick={openCreatePanel}>
                    <Plus className="h-4 w-4 mr-1" /> New
                  </Button>
                )}
              </div>

              {loading ? (
                <div className="flex justify-center py-8">
                  <Loader2 className="h-5 w-5 animate-spin text-white/40" />
                </div>
              ) : filtered.length === 0 ? (
                <div className="text-center py-8 space-y-3">
                  <p className="text-sm text-white/55">
                    {search.trim()
                      ? `No macros match "${search.trim()}".`
                      : 'No macros yet. Create your first one for a one-click reply.'}
                  </p>
                  {/* CTA — pre-fills the search string as the new macro's
                      name so the agent doesn't retype what they were
                      looking for. Hidden when the create panel is already
                      open above. */}
                  {!createOpen && (
                    <Button variant="outline" size="sm" onClick={search.trim() ? openCreateFromSearch : openCreatePanel}>
                      <Plus className="h-4 w-4 mr-1" />
                      {search.trim()
                        ? `Create "${search.trim()}" as a new macro`
                        : 'Create your first macro'}
                    </Button>
                  )}
                </div>
              ) : (
                <div className="space-y-1.5">
                  {filtered.map((m) => (
                    <div key={m.id}
                      className="rounded-lg border border-white/[0.08] bg-white/[0.02] p-2.5 hover:bg-white/[0.04] transition-colors">
                      <div className="flex items-baseline justify-between gap-2 flex-wrap">
                        <div className="flex items-baseline gap-2 min-w-0">
                          <span className="text-white font-semibold text-sm truncate">{m.name}</span>
                          {m.times_used > 0 && (
                            <Badge variant="outline" className="text-[10px]">
                              used {m.times_used}×
                            </Badge>
                          )}
                        </div>
                        <div className="flex gap-1 shrink-0">
                          <Button size="sm" className="h-7 px-2 text-xs"
                            onClick={() => handleInsert(m)}>
                            <Send className="h-3 w-3 mr-1" /> Use
                          </Button>
                          <Button variant="ghost" size="sm" className="h-7 px-2 text-xs"
                            onClick={() => openEdit(m)}>
                            <Pencil className="h-3 w-3" />
                          </Button>
                          <Button variant="ghost" size="sm"
                            className="h-7 px-2 text-xs text-rose-400 hover:text-rose-300"
                            onClick={() => setDeleteTarget(m)}>
                            <Trash2 className="h-3 w-3" />
                          </Button>
                        </div>
                      </div>
                      <div className="text-xs text-white/65 mt-1 line-clamp-2 whitespace-pre-line font-mono">
                        {m.body}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          <DialogFooter>
            {isEditMode ? (
              <>
                <Button variant="outline"
                  onClick={() => { setMode('pick'); setEditing(null); }}>Cancel</Button>
                <Button onClick={handleEditSave} disabled={savingEdit}>
                  {savingEdit ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : null}
                  Save
                </Button>
              </>
            ) : (
              <Button variant="outline" onClick={() => onOpenChange?.(false)}>Close</Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(o) => !o && !deleting && setDeleteTarget(null)}
        title={`Delete macro "${deleteTarget?.name || ''}"?`}
        description="The macro is removed from your company's saved replies. Already-sent messages that used it are unaffected. This cannot be undone."
        confirmLabel="Delete macro"
        variant="danger"
        loading={deleting}
        onConfirm={handleConfirmDelete}
      />
    </>
  );
}
