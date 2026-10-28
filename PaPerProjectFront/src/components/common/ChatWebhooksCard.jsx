import React, { useEffect, useState } from 'react';
import { Loader2, MessageSquare, Send } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useToast } from '@/components/ui/use-toast';
import { companyApi } from '@/services/companyAuthService';

const CHANNELS = [['slack', 'Slack'], ['teams', 'Microsoft Teams']];

/**
 * Where HR and Frontline post their Slack and Teams notifications (CO-64): one incoming-webhook address per agent
 * and channel, set by the company's owner or an admin, with a test message. Nothing could set them before, so a
 * template sent "to Slack" went nowhere. Backend: api/views/notification_settings.chat_webhooks.
 */
export default function ChatWebhooksCard() {
  const { toast } = useToast();
  const [data, setData] = useState(null);
  const [typed, setTyped] = useState({});
  const [busy, setBusy] = useState('');

  useEffect(() => {
    companyApi.get('/company/notification-settings/chat-webhooks').then((res) => setData(res?.data || null)).catch(() => {});
  }, []);

  if (!data || !data.agents?.length) return null;

  const key = (agent, channel) => `${agent}:${channel}`;
  const save = async (agent, channel, url) => {
    setBusy(key(agent, channel));
    try {
      const res = await companyApi.patch('/company/notification-settings/chat-webhooks', { agent, channel, url });
      setData(res?.data || data);
      setTyped((t) => ({ ...t, [key(agent, channel)]: '' }));
      toast({ title: url ? 'Saved' : 'Removed', description: url ? 'Send a test message to check it.' : undefined });
    } catch (e) {
      toast({ title: 'Not saved', description: e?.message, variant: 'destructive' });
    } finally {
      setBusy('');
    }
  };
  const test = async (agent, channel) => {
    setBusy(`test:${key(agent, channel)}`);
    try {
      await companyApi.post('/company/notification-settings/chat-webhooks', { agent, channel });
      toast({ title: 'Test message sent', description: 'Look in the channel.' });
    } catch (e) {
      toast({ title: 'The test did not arrive', description: e?.message, variant: 'destructive' });
    } finally {
      setBusy('');
    }
  };

  return (
    <section className="overflow-hidden rounded-xl border border-border bg-[var(--panel-2)]" data-testid="chat-webhooks">
      <div className="border-b border-border px-4 py-2.5">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <MessageSquare className="h-4 w-4" /> Slack and Microsoft Teams
        </h2>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Where HR and Frontline notification templates set to Slack or Teams are posted: paste the channel's
          incoming-webhook address.{!data.can_edit && " Only the company's owner or an admin can change these."}
        </p>
      </div>
      <div className="divide-y divide-border">
        {data.agents.map((a) => CHANNELS.map(([channel, label]) => {
          const k = key(a.agent, channel);
          const current = a[channel];
          return (
            <div key={k} className="grid gap-2 px-4 py-3 sm:grid-cols-[12rem_minmax(0,1fr)] sm:items-center">
              <div className="text-sm text-foreground">{a.label} → {label}</div>
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                {data.can_edit ? (
                  <Input
                    className="h-8 min-w-0 flex-1 text-xs"
                    placeholder={current.set ? current.shown : `Not set: paste the ${label} incoming-webhook address`}
                    value={typed[k] || ''}
                    onChange={(e) => setTyped((t) => ({ ...t, [k]: e.target.value }))}
                    aria-label={`${a.label} ${label} webhook address`}
                  />
                ) : (
                  <span className="flex-1 truncate text-xs text-muted-foreground">{current.set ? current.shown : 'Not set'}</span>
                )}
                {data.can_edit && (
                  <Button size="sm" className="h-8" disabled={!typed[k]?.trim() || busy === k}
                          onClick={() => save(a.agent, channel, typed[k].trim())}>
                    {busy === k ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Save'}
                  </Button>
                )}
                {current.set && data.can_edit && (
                  <Button size="sm" variant="outline" className="h-8" disabled={busy === `test:${k}`}
                          onClick={() => test(a.agent, channel)}>
                    <Send className="mr-1 h-3.5 w-3.5" /> Test
                  </Button>
                )}
                {current.set && data.can_edit && (
                  <Button size="sm" variant="ghost" className="h-8 text-xs" onClick={() => save(a.agent, channel, '')}>Remove</Button>
                )}
              </div>
            </div>
          );
        }))}
      </div>
    </section>
  );
}
