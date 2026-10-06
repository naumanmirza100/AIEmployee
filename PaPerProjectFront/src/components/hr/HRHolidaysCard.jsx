import React, { useEffect, useState } from 'react';
import { CalendarOff, Loader2, Plus, Trash2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { useToast } from '@/components/ui/use-toast';
import hrAgentService from '@/services/hrAgentService';

const label = (iso) => {
  const d = new Date(`${iso}T00:00:00`);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' });
};

/**
 * Company holidays: days off for everyone. Every agent refuses bookings on
 * one, and it is left out when leave days are counted. There was no screen to
 * enter one: the only way was to call the API by hand. HR admins add and
 * remove them here; everyone else can see the list.
 */
export default function HRHolidaysCard() {
  const { toast } = useToast();
  const [holidays, setHolidays] = useState(null);
  const [canManage, setCanManage] = useState(false);
  const [name, setName] = useState('');
  const [date, setDate] = useState('');
  const [busy, setBusy] = useState('');          // 'add' or the id being removed
  const [confirming, setConfirming] = useState(null);

  const load = async () => {
    try {
      const res = await hrAgentService.listHolidays();
      setHolidays(res?.data || []);
      setCanManage(!!res?.can_manage);
    } catch (e) {
      setHolidays([]);
      toast({ title: 'Could not load holidays', description: e?.message || 'Please try again.', variant: 'destructive' });
    }
  };
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const add = async (event) => {
    event.preventDefault();
    if (!name.trim() || !date || busy) return;
    setBusy('add');
    try {
      const res = await hrAgentService.createHoliday({ name: name.trim(), date });
      const booked = res?.already_booked || [];
      setName('');
      setDate('');
      await load();
      toast(booked.length ? {
        title: `Added. ${booked.length} booking${booked.length === 1 ? ' is' : 's are'} already on that day`,
        description: `${booked.slice(0, 3).map((b) => b.title).join(', ')}${booked.length > 3 ? ' and more' : ''}. `
          + 'They are not cancelled: tell the people involved or move them.',
      } : { title: 'Holiday added', description: 'Nobody can be booked on that day from now on.' });
    } catch (e) {
      toast({ title: 'Not added', description: e?.message || 'Please try again.', variant: 'destructive' });
    } finally {
      setBusy('');
    }
  };

  const remove = async (holiday) => {
    setBusy(holiday.id);
    try {
      await hrAgentService.deleteHoliday(holiday.id);
      await load();
    } catch (e) {
      toast({ title: 'Not removed', description: e?.message || 'Please try again.', variant: 'destructive' });
    } finally {
      setBusy('');
      setConfirming(null);
    }
  };

  // Days off for the whole company; the few rows with a region or marked as a
  // working day are shown as they are but cannot be made here.
  const today = new Date().toISOString().slice(0, 10);
  const upcoming = (holidays || []).filter((h) => h.date >= today);
  const past = (holidays || []).length - upcoming.length;

  return (
    <Card data-testid="hr-holidays" className="border-white/10 bg-pure-black/20 backdrop-blur-sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <CalendarOff className="h-5 w-5 text-violet-400" /> Company holidays
        </CardTitle>
        <CardDescription>
          A day off for everyone. No meeting or interview can be booked on one, in any agent, and it is not counted
          as a day of leave.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {canManage && (
          <form onSubmit={add} className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <label className="flex-1 text-xs text-white/60">
              Name
              <Input required value={name} maxLength={200} onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Independence Day" className="mt-1" />
            </label>
            <label className="text-xs text-white/60">
              Date
              <Input required type="date" value={date} onChange={(e) => setDate(e.target.value)} className="mt-1" />
            </label>
            <Button type="submit" disabled={busy === 'add' || !name.trim() || !date} className="shrink-0">
              {busy === 'add' ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Plus className="mr-1 h-4 w-4" />}
              Add holiday
            </Button>
          </form>
        )}

        {holidays === null && (
          <p className="flex items-center gap-2 text-sm text-white/60"><Loader2 className="h-4 w-4 animate-spin" /> Loading…</p>
        )}
        {holidays !== null && upcoming.length === 0 && (
          <p className="text-sm text-white/60">No holidays coming up.</p>
        )}

        <div className="divide-y divide-white/10">
          {upcoming.map((h) => (
            <div key={h.id} className="flex flex-wrap items-center justify-between gap-3 py-2.5">
              <div className="min-w-0">
                <p className="text-sm text-white">{h.name}</p>
                <p className="text-xs text-white/55">
                  {label(h.date)}
                  {h.region ? ` · ${h.region} only (does not block the calendar)` : ''}
                  {h.is_working_day ? ' · a working day' : ''}
                </p>
              </div>
              {canManage && (confirming === h.id ? (
                <div className="flex shrink-0 items-center gap-2">
                  <span className="text-xs text-white/60">Allow bookings on this day again?</span>
                  <Button size="sm" variant="destructive" disabled={busy === h.id} onClick={() => remove(h)}>
                    {busy === h.id && <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />} Yes, remove
                  </Button>
                  <Button size="sm" variant="outline" disabled={busy === h.id} onClick={() => setConfirming(null)}>Keep</Button>
                </div>
              ) : (
                <Button size="sm" variant="outline" className="shrink-0" onClick={() => setConfirming(h.id)}
                  aria-label={`Remove ${h.name}`}>
                  <Trash2 className="mr-1 h-3.5 w-3.5" /> Remove
                </Button>
              ))}
            </div>
          ))}
        </div>

        {past > 0 && <p className="text-xs text-white/45">{past} earlier holiday{past === 1 ? '' : 's'} not shown.</p>}
        {!canManage && holidays !== null && (
          <p className="text-xs text-white/55">Only an HR admin can add or remove a holiday.</p>
        )}
      </CardContent>
    </Card>
  );
}
