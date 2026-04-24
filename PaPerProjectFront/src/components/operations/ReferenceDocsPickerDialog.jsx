import React, { useState, useEffect, useMemo } from 'react';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Search, FileText, Layers, Loader2, Check } from 'lucide-react';
import { AUTHORING_ACCENT } from './authoringConstants';

/**
 * ReferenceDocsPickerDialog
 *
 * Modal with search + checkboxes to select which uploaded documents the AI
 * should use as context.
 *
 * Props:
 *   open          boolean
 *   docs          Array<{id, title, file_type, page_count, document_type, original_filename}>
 *   loading       boolean
 *   value         number[]                    — currently selected doc ids
 *   onChange      (ids: number[]) => void     — fires when user confirms
 *   onOpenChange  (open: boolean) => void
 */
const ReferenceDocsPickerDialog = ({
  open, docs = [], loading = false, value = [], onChange, onOpenChange,
}) => {
  const [selected, setSelected] = useState(new Set(value));
  const [search, setSearch] = useState('');

  useEffect(() => {
    if (open) {
      setSelected(new Set(value));
      setSearch('');
    }
  }, [open, value]);

  const toggle = (id) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const clearAll = () => setSelected(new Set());

  const selectAll = () => {
    const ids = filtered.map((d) => d.id);
    setSelected(new Set([...selected, ...ids]));
  };

  const confirm = () => {
    onChange?.(Array.from(selected));
    onOpenChange?.(false);
  };

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return docs;
    return docs.filter((d) =>
      (d.title || '').toLowerCase().includes(q) ||
      (d.original_filename || '').toLowerCase().includes(q) ||
      (d.document_type || '').toLowerCase().includes(q),
    );
  }, [docs, search]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-[#1a1333] border border-white/10 text-white max-w-2xl">
        <DialogHeader>
          <DialogTitle className="text-white flex items-center gap-2">
            <Layers className="h-4 w-4 text-amber-300" />
            Select reference documents
          </DialogTitle>
          <DialogDescription className="text-white/55">
            The AI will ground the generated document in the content of the documents you pick.
          </DialogDescription>
        </DialogHeader>

        {/* Search bar */}
        <div className="relative mt-2">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-white/40" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search your documents..."
            className="w-full bg-black/30 border border-white/10 rounded-lg pl-9 pr-3 py-2 text-sm text-white/90 placeholder-white/40 focus:outline-none focus:border-amber-500/40"
          />
        </div>

        {/* Counters */}
        <div className="flex items-center justify-between text-xs text-white/60 mt-2">
          <span>
            {selected.size > 0 ? (
              <><strong className="text-amber-300">{selected.size}</strong> selected</>
            ) : 'None selected'}
            {' '}· {filtered.length} {search ? 'match' : 'available'}
          </span>
          <div className="flex gap-2">
            {filtered.length > 0 && (
              <button
                type="button"
                onClick={selectAll}
                className="text-[11px] text-white/70 hover:text-amber-300"
              >
                Select all
              </button>
            )}
            {selected.size > 0 && (
              <button
                type="button"
                onClick={clearAll}
                className="text-[11px] text-white/70 hover:text-amber-300"
              >
                Clear
              </button>
            )}
          </div>
        </div>

        {/* List */}
        <div className="rounded-lg border border-white/10 divide-y divide-white/5 max-h-[50vh] overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center py-8 text-white/50 text-sm">
              <Loader2 className="h-4 w-4 animate-spin mr-2" /> Loading your documents...
            </div>
          ) : docs.length === 0 ? (
            <div className="px-4 py-8 text-center">
              <Layers className="h-6 w-6 text-white/30 mx-auto mb-2" />
              <p className="text-xs text-white/55">
                No processed documents yet. Upload from the{' '}
                <strong className="text-white/80">Documents</strong> tab first.
              </p>
            </div>
          ) : filtered.length === 0 ? (
            <div className="px-4 py-6 text-center text-xs text-white/45">
              No documents match “{search}”.
            </div>
          ) : (
            filtered.map((d) => {
              const active = selected.has(d.id);
              return (
                <label
                  key={d.id}
                  className={`flex items-center gap-3 px-3 py-2.5 cursor-pointer transition-colors ${
                    active ? 'bg-amber-500/8' : 'hover:bg-white/[0.03]'
                  }`}
                >
                  <div
                    className={`h-4 w-4 rounded border flex items-center justify-center shrink-0 ${
                      active ? 'bg-amber-500 border-amber-500' : 'border-white/25 bg-black/30'
                    }`}
                    onClick={(e) => { e.preventDefault(); toggle(d.id); }}
                  >
                    {active && <Check className="h-3 w-3 text-black" strokeWidth={3} />}
                  </div>
                  <FileText className="h-4 w-4 text-white/40 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-white/90 truncate">{d.title || d.original_filename}</div>
                    <div className="text-[10px] text-white/45 truncate">
                      {d.file_type?.toUpperCase()} · {d.page_count || 0} pages · {d.document_type}
                    </div>
                  </div>
                  <input
                    type="checkbox"
                    className="hidden"
                    checked={active}
                    onChange={() => toggle(d.id)}
                  />
                </label>
              );
            })
          )}
        </div>

        <DialogFooter className="mt-3 gap-2">
          <Button
            variant="outline"
            onClick={() => onOpenChange?.(false)}
            className="border-white/10 bg-transparent text-white/80 hover:bg-white/5"
          >
            Cancel
          </Button>
          <Button
            onClick={confirm}
            className="font-semibold"
            style={{ backgroundColor: AUTHORING_ACCENT, color: '#1a0e00', border: 'none' }}
          >
            {selected.size > 0 ? `Use ${selected.size} reference${selected.size === 1 ? '' : 's'}` : 'No references'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default ReferenceDocsPickerDialog;
