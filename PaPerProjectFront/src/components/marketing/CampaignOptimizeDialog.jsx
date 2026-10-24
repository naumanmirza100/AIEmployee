// "Optimize with AI" on a campaign's Overview.
//
// The AI reads what the campaign's emails have done (sent, opened, replies by kind, each email in the sequence) and
// advises how to get more positive replies. It only advises: nothing in the campaign is changed.

import React, { useEffect, useState } from 'react';
import { Loader2, Sparkles, RefreshCw } from 'lucide-react';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import ChatMarkdown from '@/components/shared/ChatMarkdown';
import marketingAgentService from '@/services/marketingAgentService';

export const CampaignOptimizeDialog = ({ open, onClose, campaignId }) => {
  const [loading, setLoading] = useState(false);
  const [advice, setAdvice] = useState('');
  const [error, setError] = useState('');
  const [asked, setAsked] = useState(0);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setAdvice('');
    setError('');
    marketingAgentService.outreachCampaign('optimize', {}, campaignId)
      .then((result) => {
        if (cancelled) return;
        if (result?.success === false) throw new Error(result.error || 'The AI could not review this campaign.');
        const text = result?.optimization_plan?.optimization_plan;
        if (!text) throw new Error(result?.optimization_plan?.error || 'The AI gave no advice. Try again.');
        setAdvice(text);
      })
      .catch((err) => { if (!cancelled) setError(err?.message || 'The AI could not review this campaign.'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [open, campaignId, asked]);

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-w-2xl" data-testid="MKT-optimize-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Sparkles className="h-4 w-4 text-violet-400" /> Optimize with AI</DialogTitle>
          <DialogDescription>
            Advice from this campaign's results so far. Nothing is changed: make the changes you agree with yourself.
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="flex items-center justify-center gap-2 py-10 text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Reading the campaign's results…
          </div>
        ) : error ? (
          <p className="py-6 text-center text-sm text-destructive">{error}</p>
        ) : (
          <div className="max-h-[60vh] overflow-y-auto pr-1 text-sm">
            <ChatMarkdown tables>{advice}</ChatMarkdown>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => setAsked((n) => n + 1)} disabled={loading}>
            <RefreshCw className="mr-2 h-4 w-4" /> Ask again
          </Button>
          <Button onClick={onClose}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default CampaignOptimizeDialog;
