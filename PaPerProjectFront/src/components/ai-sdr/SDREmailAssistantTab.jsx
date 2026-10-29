import React, { useEffect, useState } from 'react';
import { Sparkles, Copy, Loader2, MailOpen, PenLine } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useToast } from '@/components/ui/use-toast';
import { apiErrorMessage } from '@/utils/apiErrorMessage';
import { listCampaigns, assistantWriteEmail, assistantReadReply } from '@/services/aiSdrService';

// The client's list, part 6: the Email Assistant. It was a "Coming soon" page. Write a personal email from a kind,
// a tone and what you know about the prospect; or paste a lead's reply and the AI says what it means and drafts the
// answer. Both use only what is typed here or in the chosen campaign.

const KINDS = [
  { value: 'first_email', label: 'First email' },
  { value: 'follow_up', label: 'Follow-up' },
  { value: 'meeting_request', label: 'Ask for a call' },
  { value: 'last_touch', label: 'Last email' },
];
const TONES = [
  { value: 'professional', label: 'Professional' },
  { value: 'friendly', label: 'Friendly' },
  { value: 'direct', label: 'Direct' },
];
const CATEGORY_COLOR = {
  positive_interest: '#10b981', wants_more_info: '#60a5fa', not_interested: '#f87171',
  unsubscribe: '#f87171', out_of_office: '#f59e0b', neutral: '#9ca3af',
};
const NEXT_STEP = {
  book_meeting: 'In a campaign the agent makes a meeting and sends a link to pick a time.',
  send_info: 'In a campaign the agent answers with the AI (or holds the answer for you to check).',
  stop: 'In a campaign the agent stops emailing this lead in that campaign.',
  unsubscribe: 'In a campaign the address goes on the do-not-email list for the whole company.',
  pause: 'In a campaign the agent waits until they are back.',
  wait: 'In a campaign the follow-ups stop and the reply waits for you to read.',
};

const card = { background: 'var(--sfc-0f0a1f)', border: '1px solid var(--line-1)', borderRadius: 12, padding: 20 };
const label = { color: '#9ca3af', fontSize: 12, fontWeight: 600, marginBottom: 6, display: 'block' };
const input = {
  width: '100%', background: 'var(--sfc-0d0820)', border: '1px solid var(--line-1)', borderRadius: 8,
  color: 'var(--text-soft)', padding: '8px 12px', fontSize: 14, boxSizing: 'border-box', outline: 'none',
};
const chip = (active) => ({
  padding: '6px 12px', borderRadius: 8, fontSize: 13, cursor: 'pointer', fontWeight: active ? 700 : 500,
  border: `1px solid ${active ? '#a855f7' : 'var(--line-1)'}`,
  background: active ? 'rgba(168,85,247,0.15)' : 'transparent', color: active ? '#c084fc' : '#c4b5d4',
});

const EmailResult = ({ email, onCopy }) => (
  <div data-testid="sdr-assistant-email" style={{ ...card, marginTop: 14, background: 'rgba(168,85,247,0.05)' }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
      <div style={{ color: 'var(--text-soft)', fontWeight: 700, fontSize: 14 }}>{email.subject}</div>
      <Button variant="outline" onClick={onCopy} style={{ border: '1px solid var(--line-1)', borderRadius: 8, height: 30 }}>
        <Copy size={13} /> Copy
      </Button>
    </div>
    <pre style={{ whiteSpace: 'pre-wrap', fontFamily: 'inherit', color: 'hsl(var(--pt-c4b5d4))', fontSize: 14, lineHeight: 1.6, margin: '12px 0 0' }}>
      {email.body}
    </pre>
  </div>
);

const SDREmailAssistantTab = () => {
  const { toast } = useToast();
  const [mode, setMode] = useState('write');
  const [campaigns, setCampaigns] = useState([]);
  const [campaignId, setCampaignId] = useState('');
  const [offer, setOffer] = useState('');
  const [kind, setKind] = useState('first_email');
  const [tone, setTone] = useState('professional');
  const [prospect, setProspect] = useState({ name: '', title: '', company: '', industry: '', notes: '' });
  const [reply, setReply] = useState('');
  const [busy, setBusy] = useState(false);
  const [written, setWritten] = useState(null);
  const [reading, setReading] = useState(null);

  useEffect(() => {
    listCampaigns().then(resp => setCampaigns(resp.data || [])).catch(() => setCampaigns([]));
  }, []);

  const context = () => ({ campaign_id: campaignId || undefined, offer: offer.trim() || undefined });

  const copy = (email) => {
    navigator.clipboard?.writeText(`${email.subject}\n\n${email.body}`);
    toast({ title: 'Copied' });
  };

  const write = async () => {
    setBusy(true); setWritten(null);
    try {
      const resp = await assistantWriteEmail({ kind, tone, ...prospect, ...context() });
      setWritten(resp.data);
    } catch (e) {
      toast({ title: 'Could not write the email', description: apiErrorMessage(e, e.message), variant: 'destructive' });
    } finally { setBusy(false); }
  };

  const read = async () => {
    setBusy(true); setReading(null);
    try {
      const resp = await assistantReadReply({ reply, ...context() });
      setReading(resp.data);
    } catch (e) {
      toast({ title: 'Could not read the reply', description: apiErrorMessage(e, e.message), variant: 'destructive' });
    } finally { setBusy(false); }
  };

  const field = (key, text, placeholder) => (
    <div>
      <span style={label}>{text}</span>
      <input data-testid={`sdr-assistant-${key}`} style={input} value={prospect[key]} placeholder={placeholder}
        onChange={e => setProspect(p => ({ ...p, [key]: e.target.value }))} />
    </div>
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div>
        <h2 style={{ color: 'var(--text-soft)', fontSize: 20, fontWeight: 700, margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
          <Sparkles size={18} style={{ color: '#ec4899' }} /> AI Email Assistant
        </h2>
        <p style={{ color: '#6b7280', fontSize: 13, marginTop: 4 }}>
          Write a personal email for a prospect, or paste a lead's reply to see what it means and get an answer.
        </p>
      </div>

      <div style={{ display: 'flex', gap: 8 }}>
        <button data-testid="sdr-assistant-mode-write" style={chip(mode === 'write')} onClick={() => setMode('write')}>
          <PenLine size={13} style={{ verticalAlign: -2 }} /> Write an email
        </button>
        <button data-testid="sdr-assistant-mode-read" style={chip(mode === 'read')} onClick={() => setMode('read')}>
          <MailOpen size={13} style={{ verticalAlign: -2 }} /> Read a reply
        </button>
      </div>

      <div style={card}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
          <div>
            <span style={label}>Sender and offer from a campaign (optional)</span>
            <select data-testid="sdr-assistant-campaign" style={input} value={campaignId} onChange={e => setCampaignId(e.target.value)}>
              <option value="">None: use what I type</option>
              {campaigns.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>
          <div>
            <span style={label}>What you offer (the AI uses only this)</span>
            <input data-testid="sdr-assistant-offer" style={input} value={offer}
              placeholder={campaignId ? "Left empty: the campaign's description" : 'e.g. A patient booking app for dental clinics'}
              onChange={e => setOffer(e.target.value)} />
          </div>
        </div>
      </div>

      {mode === 'write' ? (
        <div style={card}>
          <span style={label}>Kind of email</span>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 14 }}>
            {KINDS.map(k => <button key={k.value} style={chip(kind === k.value)} onClick={() => setKind(k.value)}>{k.label}</button>)}
          </div>
          <span style={label}>Tone</span>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 14 }}>
            {TONES.map(t => <button key={t.value} style={chip(tone === t.value)} onClick={() => setTone(t.value)}>{t.label}</button>)}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
            {field('name', 'Prospect name', 'e.g. Sana Malik')}
            {field('title', 'Job title', 'e.g. Practice manager')}
            {field('company', 'Company', 'e.g. Smile Line Dental')}
            {field('industry', 'Industry', 'e.g. Dental clinics')}
          </div>
          <div style={{ marginTop: 14 }}>
            <span style={label}>Anything else you know (optional)</span>
            <textarea data-testid="sdr-assistant-notes" rows={3} style={{ ...input, resize: 'vertical' }} value={prospect.notes}
              placeholder="e.g. Met at the Islamabad health expo; they have two branches."
              onChange={e => setProspect(p => ({ ...p, notes: e.target.value }))} />
          </div>
          <Button data-testid="sdr-assistant-write" onClick={write} disabled={busy} style={{
            marginTop: 14, background: 'linear-gradient(90deg,#ec4899,#a855f7)', color: '#fff', border: 'none', borderRadius: 8, fontWeight: 600,
          }}>
            {busy ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />} Write the email
          </Button>
          {written && <EmailResult email={written} onCopy={() => copy(written)} />}
        </div>
      ) : (
        <div style={card}>
          <span style={label}>The lead's reply</span>
          <textarea data-testid="sdr-assistant-reply" rows={6} style={{ ...input, resize: 'vertical' }} value={reply}
            placeholder="Paste the reply here, in any language."
            onChange={e => setReply(e.target.value)} />
          <Button data-testid="sdr-assistant-read" onClick={read} disabled={busy || !reply.trim()} style={{
            marginTop: 14, background: 'linear-gradient(90deg,#ec4899,#a855f7)', color: '#fff', border: 'none', borderRadius: 8, fontWeight: 600,
          }}>
            {busy ? <Loader2 size={14} className="animate-spin" /> : <MailOpen size={14} />} Read the reply
          </Button>
          {reading && (
            <div data-testid="sdr-assistant-reading" style={{ marginTop: 14 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{ color: CATEGORY_COLOR[reading.category] || '#9ca3af', fontWeight: 700, fontSize: 15 }}>{reading.label}</span>
                <span style={{ color: '#6b7280', fontSize: 13 }}>{reading.reason}</span>
              </div>
              <p style={{ color: '#9ca3af', fontSize: 13, margin: '6px 0 0' }}>{NEXT_STEP[reading.action] || ''}</p>
              {reading.answer
                ? <EmailResult email={reading.answer} onCopy={() => copy(reading.answer)} />
                : <p style={{ color: '#6b7280', fontSize: 13, marginTop: 10 }}>No answer is needed for this one.</p>}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default SDREmailAssistantTab;
