import React, { useCallback, useEffect, useState } from 'react';
import { Loader2, Send, Trash2 } from 'lucide-react';
import { useToast } from '@/components/ui/use-toast';
import { apiErrorMessage } from '@/utils/apiErrorMessage';
import { discardReplyDraft, listReplyDrafts, sendReplyDraft } from '@/services/aiSdrService';

// The answers the AI has written to leads who asked for more, held until a
// person reads them. Shown on a campaign that has "Check the AI's answers before
// they are sent" switched on. Each can be changed, then sent or discarded.

const cardStyle = {
  background: 'linear-gradient(135deg, hsl(var(--sfr-0f0a1f) / 0.95) 0%, hsl(var(--sfr-140828) / 0.95) 100%)',
  border: '1px solid rgba(245,158,11,0.35)', borderRadius: 12, padding: 18,
};
const inputStyle = {
  background: 'hsl(var(--sfr-1e0a32) / 0.6)', border: '1px solid var(--line-1)',
  borderRadius: 8, padding: '8px 12px', color: 'var(--text-soft)',
  outline: 'none', fontSize: 14, width: '100%', boxSizing: 'border-box',
};
const labelStyle = { color: '#9ca3af', fontSize: 12, display: 'block', marginBottom: 4 };
const buttonStyle = {
  borderRadius: 8, padding: '7px 14px', cursor: 'pointer', fontSize: 13, fontWeight: 600,
  display: 'inline-flex', alignItems: 'center', gap: 6,
};

export default function SDRReplyDrafts({ campaignId, waiting = 0, onChanged }) {
  const { toast } = useToast();
  const [drafts, setDrafts] = useState([]);
  const [edits, setEdits] = useState({});       // { [draft id]: { subject, body } }
  const [busy, setBusy] = useState(null);       // id of the draft being sent or discarded

  const load = useCallback(async () => {
    try {
      const resp = await listReplyDrafts(campaignId);
      setDrafts(resp.data || []);
    } catch (_) { /* the panel simply stays as it was */ }
  }, [campaignId]);

  // `waiting` comes from the campaign and changes when the background job holds another answer.
  useEffect(() => { load(); }, [load, waiting]);

  const valueOf = (draft, field) => (edits[draft.id]?.[field] ?? draft[field] ?? '');
  const edit = (draft, field, value) =>
    setEdits((prev) => ({ ...prev, [draft.id]: { ...prev[draft.id], [field]: value } }));

  const decide = async (draft, decision) => {
    setBusy(draft.id);
    try {
      if (decision === 'send') {
        await sendReplyDraft(draft.id, { subject: valueOf(draft, 'subject'), body: valueOf(draft, 'body') });
        toast({ title: `Sent to ${draft.lead_name}` });
      } else {
        await discardReplyDraft(draft.id);
        toast({ title: 'Answer discarded', description: `Nothing was sent to ${draft.lead_name}.` });
      }
      setDrafts((prev) => prev.filter((d) => d.id !== draft.id));
      onChanged?.();
    } catch (e) {
      toast({
        title: decision === 'send' ? 'Not sent' : 'Not discarded',
        description: apiErrorMessage(e, 'Please try again.'), variant: 'destructive',
      });
      load();
    } finally { setBusy(null); }
  };

  if (!drafts.length) return null;

  return (
    <div style={cardStyle} data-testid="sdr-answers-waiting">
      <h3 style={{ color: 'var(--text-soft)', fontWeight: 700, fontSize: 14, margin: '0 0 4px' }}>
        {drafts.length === 1 ? '1 answer is waiting for you' : `${drafts.length} answers are waiting for you`}
      </h3>
      <p style={{ color: '#9ca3af', fontSize: 12, margin: '0 0 14px', lineHeight: 1.5 }}>
        These leads replied asking for more. The AI has written an answer to each; nothing is sent until you
        press Send. Change the text first if you want to.
      </p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {drafts.map((draft) => (
          <div key={draft.id} data-testid="sdr-answer" style={{ borderTop: '1px solid var(--line-1)', paddingTop: 14 }}>
            <div style={{ color: 'var(--text-soft)', fontSize: 13, fontWeight: 600 }}>
              {draft.lead_name} <span style={{ color: '#9ca3af', fontWeight: 400 }}>· {draft.lead_email}</span>
            </div>
            {draft.lead_reply && (
              <blockquote style={{
                margin: '8px 0 12px', padding: '8px 12px', borderLeft: '3px solid rgba(96,165,250,0.5)',
                color: '#9ca3af', fontSize: 13, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere',
              }}>
                {draft.lead_reply}
              </blockquote>
            )}
            <label style={labelStyle} htmlFor={`answer-subject-${draft.id}`}>Subject</label>
            <input id={`answer-subject-${draft.id}`} style={inputStyle} value={valueOf(draft, 'subject')}
              onChange={(e) => edit(draft, 'subject', e.target.value)} />
            <label style={{ ...labelStyle, marginTop: 10 }} htmlFor={`answer-body-${draft.id}`}>Your answer</label>
            <textarea id={`answer-body-${draft.id}`} rows={7} style={{ ...inputStyle, resize: 'vertical', lineHeight: 1.5 }}
              value={valueOf(draft, 'body')} onChange={(e) => edit(draft, 'body', e.target.value)} />
            {draft.error && (
              <p style={{ color: '#f87171', fontSize: 12, margin: '8px 0 0' }}>Last try failed: {draft.error}</p>
            )}
            <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
              <button type="button" disabled={busy === draft.id} onClick={() => decide(draft, 'send')} style={{
                ...buttonStyle, background: '#10b981', border: '1px solid #10b981', color: '#fff',
                opacity: busy === draft.id ? 0.6 : 1,
              }}>
                {busy === draft.id ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
                Send to {draft.lead_name}
              </button>
              <button type="button" disabled={busy === draft.id} onClick={() => decide(draft, 'discard')} style={{
                ...buttonStyle, background: 'transparent', border: '1px solid var(--line-1)', color: '#9ca3af',
              }}>
                <Trash2 size={14} /> Discard
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
