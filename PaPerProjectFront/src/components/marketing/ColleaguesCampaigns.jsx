import React, { useCallback, useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/components/ui/use-toast';
import { Loader2, Pause, Users } from 'lucide-react';
import { Link } from 'react-router-dom';
import { companyApi } from '@/services/companyAuthService';

// For an owner or admin: the campaigns of everyone else in the company. Each
// opens on its own page, where they can see its leads and replies, edit, pause,
// resume and launch it (the user's decision of 29 Oct 2026); running ones also
// have a Pause button here. Shown to nobody else, and not at all when there are none.

const STATUS_CLASS = {
  active: 'border-emerald-400/50 text-emerald-300',
  scheduled: 'border-sky-400/50 text-sky-300',
  paused: 'border-amber-400/50 text-amber-300',
};

export default function ColleaguesCampaigns() {
  const { toast } = useToast();
  const [campaigns, setCampaigns] = useState([]);
  const [stopping, setStopping] = useState(null);

  const load = useCallback(async () => {
    try {
      const res = await companyApi.get('/marketing/colleagues-campaigns');
      setCampaigns(res?.data?.can_manage ? (res.data.campaigns || []) : []);
    } catch (_) { /* not shown is the right fallback */ }
  }, []);

  useEffect(() => { load(); }, [load]);

  const stop = async (campaign) => {
    setStopping(campaign.id);
    try {
      const res = await companyApi.post(`/marketing/colleagues-campaigns/${campaign.id}/stop`, {});
      toast({ title: 'Campaign paused', description: res?.message });
      await load();
    } catch (e) {
      toast({ title: 'Not paused', description: e?.message || 'Please try again.', variant: 'destructive' });
    } finally { setStopping(null); }
  };

  if (!campaigns.length) return null;

  return (
    <Card data-testid="MKT-colleagues-campaigns" className="border-white/10 bg-pure-black/20 backdrop-blur-sm">
      <CardHeader className="pb-3">
        <CardTitle className="text-base text-white flex items-center gap-2">
          <Users className="h-4 w-4" /> Colleagues' campaigns
        </CardTitle>
        <p className="text-xs text-white/60">
          Campaigns made by other logins in your company. You see them because you run the company: open one to see
          its leads and replies, change, pause or launch it. It still sends from its maker's mailbox.
        </p>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="divide-y divide-white/10">
          {campaigns.map((c) => {
            const running = c.status === 'active' || c.status === 'scheduled';
            return (
              <div key={c.id} data-testid="MKT-colleagues-campaign" className="flex items-center justify-between gap-3 py-2.5">
                <div className="min-w-0">
                  <Link to={`/marketing/dashboard/campaign/${c.id}`} data-testid="MKT-colleagues-campaign-open"
                    className="text-sm text-white truncate block hover:underline">{c.name}</Link>
                  <p className="text-xs text-white/50">
                    {c.owner.name}{c.owner.is_active ? '' : ' · login switched off'} · {c.leads} lead{c.leads === 1 ? '' : 's'}
                  </p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <Badge variant="outline" className={`text-[10px] capitalize ${STATUS_CLASS[c.status] || 'border-white/20 text-white/60'}`}>
                    {c.status}
                  </Badge>
                  {running && (
                    <Button size="sm" variant="outline" disabled={stopping === c.id} onClick={() => stop(c)}>
                      {stopping === c.id ? <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" /> : <Pause className="h-3.5 w-3.5 mr-1.5" />}
                      Pause
                    </Button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
