import React, { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Loader2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { useToast } from '@/components/ui/use-toast';
import { companyApi } from '@/services/companyAuthService';

/**
 * Says when HR's or Frontline's document search can only match words (CO-70): no service for searching by meaning
 * works on the server, or some parts were saved while it did not. Nothing showed it before, and the upload pop-up
 * still said "embedded". Offers to fix the parts saved without. Backend: api/views/document_search.py.
 */
export default function DocumentSearchBanner({ agent, refreshKey }) {
  const { toast } = useToast();
  const [info, setInfo] = useState(null);
  const [fixing, setFixing] = useState(false);

  const load = useCallback(() => {
    companyApi.get('/company/document-search', { agent }).then((res) => setInfo(res?.data || null)).catch(() => {});
  }, [agent]);
  useEffect(() => { load(); }, [load, refreshKey]);

  if (!info || info.mode === 'meaning' || (info.mode === 'partly' && !info.chunks_without_vectors)) return null;

  const fix = async () => {
    setFixing(true);
    try {
      const res = await companyApi.post('/company/document-search', { agent });
      if (res?.data?.queued) {
        toast({ title: 'Working on it', description: 'Large documents take a minute or two. This note goes away when it is done.' });
        setTimeout(load, 30000);
      } else {
        load();
      }
    } catch (e) {
      toast({ title: 'Not fixed', description: e?.message, variant: 'destructive' });
    } finally {
      setFixing(false);
    }
  };

  const words = info.mode === 'words';
  return (
    <div className="mb-3 flex flex-col gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2.5 text-sm sm:flex-row sm:items-center"
         data-testid="document-search-banner">
      <AlertTriangle className="h-4 w-4 shrink-0 text-amber-300" />
      <div className="min-w-0 flex-1 text-amber-100/90">
        {words ? (
          <>
            <span className="font-medium">Document search is matching words only.</span> Searching by meaning is not
            working on the server, so an answer can miss a document that says the same thing in other words. Uploads
            still work. To turn it on, add an OpenAI key for this agent under API Keys, or ask Pay Per Project support.
          </>
        ) : (
          <>
            <span className="font-medium">{info.chunks_without_vectors} of {info.chunks} parts of your documents can
            only be found by matching words</span>: they were saved while searching by meaning was off.
            {!info.can_fix && ' An HR admin can fix this here.'}
          </>
        )}
      </div>
      {!words && info.can_fix && (
        <Button size="sm" variant="outline" className="h-8 shrink-0" disabled={fixing} onClick={fix}>
          {fixing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Make them searchable by meaning'}
        </Button>
      )}
    </div>
  );
}
