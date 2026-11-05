import React, { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import {
  Loader2, Play, PlayCircle, CheckCircle2, XCircle, AlertTriangle, MinusCircle, ChevronDown, ChevronRight,
  HeartPulse, Zap,
} from 'lucide-react';
import { CARD_CLASS, ROW_CLASS } from '@/components/admin/apiKeysShared';
import { sdrLiveChecksApi } from '@/services/aiSdrService';

const STATUS_META = {
  passed:  { label: 'Passed',  icon: CheckCircle2,  cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30' },
  warning: { label: 'Warning', icon: AlertTriangle, cls: 'bg-amber-500/15 text-amber-300 border-amber-500/30' },
  failed:  { label: 'Failed',  icon: XCircle,       cls: 'bg-red-500/15 text-red-300 border-red-500/30' },
  skipped: { label: 'Skipped', icon: MinusCircle,   cls: 'bg-white/5 text-white/50 border-white/10' },
  running: { label: 'Running', icon: Loader2,       cls: 'bg-violet-500/15 text-violet-300 border-violet-500/30' },
};

const StatusBadge = ({ status }) => {
  const meta = STATUS_META[status];
  if (!meta) return <Badge variant="outline" className="border-white/10 text-white/50">Not run</Badge>;
  const Icon = meta.icon;
  return (
    <Badge variant="outline" className={`${meta.cls} gap-1 shrink-0`}>
      <Icon className={`w-3 h-3 ${status === 'running' ? 'animate-spin' : ''}`} /> {meta.label}
    </Badge>
  );
};

const NEEDS_TEXT = { email: 'a test email address', campaign: 'a campaign' };

const CheckRow = ({ check, result, running, onRun, runLabel, missing }) => {
  const [open, setOpen] = useState(false);
  const details = result?.details || [];
  useEffect(() => { if (result && result.status !== 'passed') setOpen(true); }, [result]);
  return (
    <div className={`${ROW_CLASS} rounded-lg p-3 space-y-2`}>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-0.5">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-white">{check.title}</span>
            <StatusBadge status={running ? 'running' : result?.status} />
          </div>
          <p className="text-xs text-white/50">{check.description}</p>
          {missing.length ? <p className="text-xs text-amber-300/80">Needs {missing.map((n) => NEEDS_TEXT[n]).join(' and ')}, above.</p> : null}
        </div>
        <Button size="sm" onClick={onRun} disabled={running || missing.length > 0}
          className="bg-violet-600 hover:bg-violet-500 text-white shrink-0">
          {running ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <Play className="w-3.5 h-3.5 mr-1.5" />}
          {runLabel || 'Run'}
        </Button>
      </div>
      {result && !running ? (
        <div className="space-y-1">
          <button type="button" className="flex w-full items-start gap-1.5 text-left text-sm text-white/80"
            onClick={() => setOpen((o) => !o)} disabled={!details.length}>
            {details.length ? (open ? <ChevronDown className="w-4 h-4 mt-0.5 text-white/40 shrink-0" /> : <ChevronRight className="w-4 h-4 mt-0.5 text-white/40 shrink-0" />) : null}
            <span>{result.summary}</span>
            <span className="ml-auto shrink-0 text-xs text-white/30">{(result.duration_ms / 1000).toFixed(1)}s</span>
          </button>
          {open && details.length ? (
            <pre className="max-h-72 overflow-auto rounded bg-black/40 p-3 text-[11px] leading-relaxed text-white/70 whitespace-pre-wrap break-words">
              {details.join('\n')}
            </pre>
          ) : null}
        </div>
      ) : null}
    </div>
  );
};

/**
 * AI SDR → Tests, the checks of this company's live AI SDR: read-only health checks, and live tests that do
 * the work for real with the company's own AI key, mailbox and CRM (ai_sdr_agent/live_checks.py).
 */
const SDRLiveChecks = () => {
  const { toast } = useToast();
  const [catalog, setCatalog] = useState(null);
  const [results, setResults] = useState({});
  const [running, setRunning] = useState({});
  const [email, setEmail] = useState('');
  const [campaignId, setCampaignId] = useState('');

  useEffect(() => {
    sdrLiveChecksApi.getCatalog()
      .then((data) => {
        setCatalog(data);
        if (data.campaigns?.length) setCampaignId(String(data.campaigns[0].id));
      })
      .catch((e) => toast({ title: 'Could not load the checks', description: String(e.message || e), variant: 'destructive' }));
  }, [toast]);

  const missingFor = (check) => (check.needs || []).filter((n) =>
    (n === 'email' && !email.trim()) || (n === 'campaign' && !campaignId));

  const run = async (check) => {
    setRunning((r) => ({ ...r, [check.key]: true }));
    try {
      const body = {};
      if (check.needs?.includes('email')) body.email = email.trim();
      if (check.needs?.includes('campaign')) body.campaign_id = Number(campaignId);
      const result = await sdrLiveChecksApi.run(check.key, body);
      setResults((r) => ({ ...r, [check.key]: result }));
    } catch (e) {
      toast({ title: `${check.title}: could not run`, description: String(e.message || e), variant: 'destructive' });
    } finally {
      setRunning((r) => ({ ...r, [check.key]: false }));
    }
  };

  if (!catalog) {
    return <div className="flex justify-center py-10"><Loader2 className="w-6 h-6 animate-spin text-violet-400" /></div>;
  }

  const anyHealthRunning = catalog.health.some((c) => running[c.key]);

  return (
    <div className="space-y-6">
      <section className={`${CARD_CLASS} rounded-xl p-4 sm:p-5 space-y-4`}>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-1">
            <h2 className="text-white font-semibold flex items-center gap-2"><HeartPulse className="w-5 h-5 text-violet-400" /> Health checks</h2>
            <p className="text-sm text-white/50 max-w-2xl">
              Looks at your live AI SDR without changing anything: no email is sent and no lead is touched.
            </p>
          </div>
          <Button onClick={() => catalog.health.forEach(run)} disabled={anyHealthRunning}
            className="bg-violet-600 hover:bg-violet-500 text-white shrink-0">
            {anyHealthRunning ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <PlayCircle className="w-4 h-4 mr-2" />}
            Run all health checks
          </Button>
        </div>
        <div className="space-y-2">
          {catalog.health.map((check) => (
            <CheckRow key={check.key} check={check} result={results[check.key]} running={running[check.key]}
              onRun={() => run(check)} missing={[]} />
          ))}
        </div>
      </section>

      <section className={`${CARD_CLASS} rounded-xl p-4 sm:p-5 space-y-4`}>
        <div className="space-y-1">
          <h2 className="text-white font-semibold flex items-center gap-2"><Zap className="w-5 h-5 text-violet-400" /> Live tests</h2>
          <p className="text-sm text-white/50 max-w-2xl">
            Does the work for real, with your own AI key, mailbox and CRM. AI tests use a few AI credits. The test
            lead is never saved, and the only email sent goes to the address you type here.
          </p>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="sdr-test-email" className="text-white/70 text-xs">Send test emails to</Label>
            <Input id="sdr-test-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)}
              placeholder={catalog.email || 'you@yourcompany.com'} className="bg-black/20 border-white/10 text-white" />
          </div>
          <div className="space-y-1.5">
            <Label className="text-white/70 text-xs">Campaign mailbox to use</Label>
            {catalog.campaigns.length ? (
              <Select value={campaignId} onValueChange={setCampaignId}>
                <SelectTrigger className="bg-black/20 border-white/10 text-white"><SelectValue placeholder="Choose a campaign" /></SelectTrigger>
                <SelectContent>
                  {catalog.campaigns.map((c) => (
                    <SelectItem key={c.id} value={String(c.id)}>{c.name} — {c.from_email} ({c.status})</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <p className="text-sm text-white/50 pt-2">No campaign has a mailbox set up yet.</p>
            )}
          </div>
        </div>
        <div className="space-y-2">
          {catalog.live.map((check) => (
            <CheckRow key={check.key} check={check} result={results[check.key]} running={running[check.key]}
              onRun={() => run(check)} missing={missingFor(check)}
              runLabel={check.key === 'live_send' ? 'Send test email' : undefined} />
          ))}
        </div>
      </section>
    </div>
  );
};

export default SDRLiveChecks;
