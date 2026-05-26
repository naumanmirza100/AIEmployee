/**
 * MacroPickerDialog — agent saved-replies / quick-reply picker.
 *
 * Opens from a "Macros" button in the ticket reply composer. Two modes:
 *   • pick (default) — list with one-click-insert into the reply textarea
 *   • manage — create / edit / delete macros
 *
 * Backend: TicketMacro CRUD endpoints (api/views/frontline_agent.py). On
 * insert, calls bumpTicketMacroUsage so most-used surfaces bubble up next time.
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
  Loader2, Plus, Pencil, Trash2, ChevronLeft, Send,
} from 'lucide-react';
import {
  listTicketMacros, createTicketMacro, updateTicketMacro,
  deleteTicketMacro, bumpTicketMacroUsage,
} from '@/services/frontlineAgentService';


export default function MacroPickerDialog({ open, onOpenChange, onInsert }) {
  const { toast } = useToast();
  const [mode, setMode] = useState('pick'); // 'pick' | 'edit' | 'create'
  const [macros, setMacros] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [editing, setEditing] = useState(null); // null | macro
  const [form, setForm] = useState({ name: '', body: '' });
  const [saving, setSaving] = useState(false);

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
    setForm({ name: '', body: '' });
    setSearch('');
    load();
  }, [open]);

  const openCreate = () => {
    setForm({ name: '', body: '' });
    setEditing(null);
    setMode('create');
  };
  const openEdit = (m) => {
    setForm({ name: m.name, body: m.body });
    setEditing(m);
    setMode('edit');
  };

  const handleSave = async () => {
    const name = form.name.trim();
    const body = form.body.trim();
    if (!name || !body) {
      toast({ title: 'Name and body are required', variant: 'destructive' });
      return;
    }
    setSaving(true);
    try {
      if (mode === 'create') {
        const res = await createTicketMacro({ name, body });
        setMacros((arr) => [res?.data, ...arr.filter(Boolean)]);
        toast({ title: 'Macro created' });
      } else if (mode === 'edit' && editing) {
        const res = await updateTicketMacro(editing.id, { name, body });
        setMacros((arr) => arr.map((m) => m.id === editing.id ? (res?.data || m) : m));
        toast({ title: 'Macro updated' });
      }
      setMode('pick');
      setEditing(null);
    } catch (e) {
      toast({ title: 'Save failed', description: e.message, variant: 'destructive' });
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (m) => {
    if (!confirm(`Delete macro "${m.name}"?`)) return;
    try {
      await deleteTicketMacro(m.id);
      setMacros((arr) => arr.filter((x) => x.id !== m.id));
      toast({ title: 'Macro deleted' });
    } catch (e) {
      toast({ title: 'Delete failed', description: e.message, variant: 'destructive' });
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

  const isFormMode = mode === 'create' || mode === 'edit';

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {isFormMode && (
              <Button variant="ghost" size="sm" className="h-7 px-2"
                onClick={() => { setMode('pick'); setEditing(null); }}>
                <ChevronLeft className="h-4 w-4" />
              </Button>
            )}
            {mode === 'create' ? 'New macro'
              : mode === 'edit' ? 'Edit macro'
              : 'Saved replies (macros)'}
          </DialogTitle>
          <DialogDescription>
            {isFormMode
              ? 'Macros are company-wide. Use {{customer_name}} / {{ticket_title}} placeholders when you write them — the reply composer will leave them as-is.'
              : 'Quick-insert canned replies into the ticket composer. Click "Use" to insert.'}
          </DialogDescription>
        </DialogHeader>

        {isFormMode ? (
          <div className="space-y-3 flex-1 overflow-y-auto">
            <div>
              <Label className="text-xs">Name</Label>
              <Input value={form.name}
                onChange={(e) => setForm((s) => ({ ...s, name: e.target.value }))}
                placeholder="e.g. Greeting / Refund decline / Ask for log files" />
            </div>
            <div className="flex-1 min-h-0">
              <Label className="text-xs">Body</Label>
              <Textarea rows={10} className="font-mono text-xs"
                value={form.body}
                onChange={(e) => setForm((s) => ({ ...s, body: e.target.value }))}
                placeholder="Hi {{customer_name}},

Thanks for reaching out…" />
            </div>
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto space-y-2">
            <div className="flex items-center gap-2">
              <Input value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search macros…"
                className="flex-1" />
              <Button variant="outline" size="sm" onClick={openCreate}>
                <Plus className="h-4 w-4 mr-1" /> New
              </Button>
            </div>
            {loading ? (
              <div className="flex justify-center py-8">
                <Loader2 className="h-5 w-5 animate-spin text-white/40" />
              </div>
            ) : filtered.length === 0 ? (
              <div className="text-center text-sm text-white/55 py-8">
                {search.trim()
                  ? `No macros match "${search.trim()}".`
                  : 'No macros yet. Create your first one for a one-click reply.'}
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
                          onClick={() => handleDelete(m)}>
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
          {isFormMode ? (
            <>
              <Button variant="outline"
                onClick={() => { setMode('pick'); setEditing(null); }}>Cancel</Button>
              <Button onClick={handleSave} disabled={saving}>
                {saving ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : null}
                {mode === 'create' ? 'Create' : 'Save'}
              </Button>
            </>
          ) : (
            <Button variant="outline" onClick={() => onOpenChange?.(false)}>Close</Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
