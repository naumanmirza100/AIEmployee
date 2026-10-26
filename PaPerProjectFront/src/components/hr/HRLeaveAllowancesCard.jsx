import React, { useEffect, useState } from 'react';
import { CalendarCheck2, Loader2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { useToast } from '@/components/ui/use-toast';
import hrAgentService from '@/services/hrAgentService';

/**
 * Leave allowances: each leave type's days a year, for the whole company (hr_agent/allowances.py).
 *
 * A new company's employees had no balance at all ("HR has not set up your leave balance yet"): one came only from
 * an accrual policy, which had no screen, or HR's Adjust button, one person and one type at a time. Applying sets
 * this year's balance of everyone to these days (days already used are kept); anyone who joins later gets them too,
 * and next year they are credited again. HR admins change them; everyone else sees them.
 */
export default function HRLeaveAllowancesCard() {
  const { toast } = useToast();
  const [data, setData] = useState(null);
  const [days, setDays] = useState({});
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const res = await hrAgentService.getLeaveAllowances();
      const d = res?.data || null;
      setData(d);
      setDays(Object.fromEntries((d?.allowances || []).map((a) => [a.leave_type, a.days ? String(a.days) : ''])));
    } catch (e) {
      setData({ allowances: [], can_manage: false });
      toast({ title: 'Could not load leave allowances', description: e?.message || 'Please try again.', variant: 'destructive' });
    }
  };
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const apply = async (event) => {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    try {
      const wanted = Object.fromEntries(Object.entries(days).map(([k, v]) => [k, Number(v) || 0]));
      const res = await hrAgentService.applyLeaveAllowances(wanted);
      setData(res?.data || data);
      toast({
        title: 'Leave allowances applied',
        description: `Everyone's balance for ${res?.data?.year || 'this year'} is set (${res?.data?.employees ?? ''} people). `
          + 'Days already taken are kept, and anyone who joins later gets them too.',
      });
    } catch (e) {
      toast({ title: 'Not applied', description: e?.message || 'Please try again.', variant: 'destructive' });
    } finally {
      setBusy(false);
    }
  };

  const set = (data?.allowances || []).filter((a) => a.days > 0);

  return (
    <Card data-testid="hr-leave-allowances" className="border-white/10 bg-pure-black/20 backdrop-blur-sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <CalendarCheck2 className="h-5 w-5 text-violet-400" /> Leave allowances
        </CardTitle>
        <CardDescription>
          How many days of each kind of leave everyone gets a year. People can't ask for more than they have left;
          for the rest there is Unpaid leave.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {data === null && (
          <p className="flex items-center gap-2 text-sm text-white/60"><Loader2 className="h-4 w-4 animate-spin" /> Loading…</p>
        )}
        {data !== null && data.can_manage && (
          <form onSubmit={apply} className="space-y-3">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              {(data.allowances || []).map((a) => (
                <label key={a.leave_type} className="text-xs text-white/60">
                  {a.label} <span className="text-white/35">days a year</span>
                  <Input type="number" min="0" max="366" step="0.5" value={days[a.leave_type] ?? ''}
                    data-testid={`allowance-${a.leave_type}`} placeholder="0"
                    onChange={(e) => setDays((d) => ({ ...d, [a.leave_type]: e.target.value }))} className="mt-1" />
                </label>
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <Button type="submit" disabled={busy} data-testid="allowances-apply">
                {busy && <Loader2 className="mr-1 h-4 w-4 animate-spin" />} Apply to everyone
              </Button>
              <span className="text-xs text-white/50">
                Sets this year's balance of all {data.employees} current employees. 0 or empty: that kind of leave
                has no balance.
              </span>
            </div>
          </form>
        )}
        {data !== null && !data.can_manage && (
          set.length === 0
            ? <p className="text-sm text-white/60">No allowances set yet. HR sets them here.</p>
            : <ul className="space-y-1 text-sm text-white/80">
                {set.map((a) => <li key={a.leave_type}>{a.label}: {a.days} days a year</li>)}
              </ul>
        )}
      </CardContent>
    </Card>
  );
}
