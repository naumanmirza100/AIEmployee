// The "Figures" tab of an Operations document: its key amounts, KPIs and the period each refers to, in one table.
//
// Read by the AI only when asked ("Read the figures"), then kept on the document (operations_agent/figures.py), so
// reopening the page costs nothing and Analytics can list figures across documents.

import React, { useState } from 'react';
import { Hash, Loader2, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useToast } from '@/components/ui/use-toast';
import * as operationsService from '@/services/operationsAgentService';

export const formatFigure = (f) => {
  if (f.value === null || f.value === undefined) return f.text || '—';
  const n = Number(f.value).toLocaleString(undefined, { maximumFractionDigits: 2 });
  if (!f.unit) return n;
  return f.unit === '%' ? `${n}%` : `${n} ${f.unit}`;
};

export const FiguresTable = ({ rows, showDocument = false }) => (
  <div className="overflow-x-auto rounded-xl border border-white/[0.06]">
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-white/[0.06] text-left text-[11px] uppercase tracking-wider text-white/40">
          {showDocument && <th className="px-4 py-2 font-medium">Document</th>}
          <th className="px-4 py-2 font-medium">Figure</th>
          <th className="px-4 py-2 font-medium text-right">Value</th>
          <th className="px-4 py-2 font-medium">Period</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((f, i) => (
          <tr key={i} className="border-b border-white/[0.04] last:border-0">
            {showDocument && <td className="px-4 py-2 text-white/50">{f.document}</td>}
            <td className="px-4 py-2 text-white/80">{f.label}</td>
            <td className="px-4 py-2 text-right font-medium tabular-nums text-emerald-300">{formatFigure(f)}</td>
            <td className="px-4 py-2 text-white/50">{f.period || '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

export default function DocumentFiguresPanel({ document, onRead }) {
  const { toast } = useToast();
  const [reading, setReading] = useState(false);
  const saved = document?.metadata?.figures;
  const rows = saved?.items || [];

  const read = async () => {
    setReading(true);
    try {
      const res = await operationsService.extractDocumentFigures(document.id);
      onRead?.(res?.figures);
      toast({ title: res?.count ? `${res.count} figures found` : 'No figures found in this document' });
    } catch (e) {
      toast({ title: 'Could not read the figures', description: e?.message || '', variant: 'destructive' });
    } finally {
      setReading(false);
    }
  };

  return (
    <div className="space-y-4" data-testid="OPS-docdetail-figures">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-white/40">
          {saved ? `Read ${new Date(saved.extracted_at).toLocaleString()}` : 'Amounts, KPIs and the period each refers to, pulled out of the document.'}
        </p>
        <Button size="sm" variant="outline" onClick={read} disabled={reading || !document?.parsed_text} data-testid="OPS-docdetail-figures-read">
          {reading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : saved ? <RefreshCw className="mr-2 h-4 w-4" /> : <Hash className="mr-2 h-4 w-4" />}
          {saved ? 'Read again' : 'Read the figures'}
        </Button>
      </div>
      {rows.length > 0 ? <FiguresTable rows={rows} /> : saved ? (
        <p className="rounded-xl border border-white/[0.06] p-8 text-center text-sm text-white/30">No figures were found in this document.</p>
      ) : null}
    </div>
  );
}
