import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Plus, Edit2, Copy, Trash2, Send, Loader2, ChevronLeft, ChevronRight, AlertTriangle, Check, X,
  FileCode, Mail, Square, ChevronDown, ChevronUp, Wand2,
  Bold, Italic, Underline, Link2, Unlink, List, Undo2, Redo2, Code2, Type,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { useToast } from '@/components/ui/use-toast';
import { apiErrorMessage } from '@/utils/apiErrorMessage';
import SdrSelect from './SdrSelect';
import {
  listEmailTemplates, getEmailTemplate, createEmailTemplate, updateEmailTemplate, deleteEmailTemplate,
  previewEmailTemplate, listEmailSends, startEmailSend, getEmailSend, stopEmailSend, listLeadIndustries,
  listLeadCompanies,
} from '@/services/aiSdrService';

// Your own HTML emails: write a template, see it with a real lead, and send it to the leads of one industry
// through a campaign's mailbox. The server sends it a few at a time within the mailbox's daily limit.

const cardStyle = {
  background: 'linear-gradient(135deg, hsl(var(--sfr-0f0a1f) / 0.95) 0%, hsl(var(--sfr-140828) / 0.95) 100%)',
  border: '1px solid var(--line-1)', borderRadius: 12,
};
const inputStyle = {
  background: 'hsl(var(--sfr-1e0a32) / 0.6)', border: '1px solid var(--line-1)',
  borderRadius: 8, padding: '8px 12px', color: 'var(--text-soft)',
  outline: 'none', fontSize: 14, width: '100%', boxSizing: 'border-box',
};
const labelStyle = { color: '#9ca3af', fontSize: 12, display: 'block', marginBottom: 4 };
const primaryBtn = {
  background: 'linear-gradient(90deg,hsl(var(--brand-600)),#a855f7)', color: '#fff', border: 'none',
  borderRadius: 8, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6,
};
const ghostBtn = { border: '1px solid var(--line-1)', color: 'hsl(var(--pt-9ca3af))', borderRadius: 8, display: 'flex', alignItems: 'center', gap: 6 };
const iconBtn = { display: 'flex', alignItems: 'center', background: 'none', border: '1px solid var(--line-1)', borderRadius: 7, padding: 6, cursor: 'pointer', color: 'hsl(var(--pt-9ca3af))' };

const SEND_STATUS = {
  sending: { label: 'Sending', color: '#60a5fa' },
  done:    { label: 'Done',    color: '#34d399' },
  stopped: { label: 'Stopped', color: '#9ca3af' },
};
const RECIPIENT_COLOR = { queued: '#9ca3af', sent: '#34d399', skipped: '#f59e0b', failed: '#f87171' };

const fmtDate = (iso) => (iso ? new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : '');

// --------------------------------------------------------------------------
// The email as a lead will see it: subject on top, the HTML in a sandboxed frame (its links and scripts do
// nothing here, and it cannot reach this page).
// --------------------------------------------------------------------------
const EmailFrame = ({ subject, html, loading, height = 560 }) => (
  <div style={{ border: '1px solid var(--line-1)', borderRadius: 10, overflow: 'hidden', background: '#ffffff' }}>
    <div style={{ padding: '10px 14px', borderBottom: '1px solid #ececf1', background: '#fafafc' }}>
      <div style={{ color: '#6b7280', fontSize: 11 }}>Subject</div>
      <div style={{ color: '#111827', fontSize: 14, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {subject || '(no subject)'}
      </div>
    </div>
    <iframe title="Email preview" srcDoc={html || ''} sandbox=""
      style={{ width: '100%', height, border: 'none', display: 'block', opacity: loading ? 0.55 : 1, transition: 'opacity 0.15s' }} />
  </div>
);

// --------------------------------------------------------------------------
// One company: a search box over the companies you have leads with an email at.
// --------------------------------------------------------------------------
const CompanyPicker = ({ value, onChange }) => {
  const [query, setQuery] = useState(value);
  const [options, setOptions] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const boxRef = useRef(null);

  useEffect(() => { setQuery(value); }, [value]);
  useEffect(() => {
    if (!open) return undefined;
    let live = true;
    setLoading(true);
    const id = setTimeout(() => {
      listLeadCompanies(query === value ? '' : query)
        .then(r => { if (live) setOptions(r?.data || []); })
        .catch(() => { if (live) setOptions([]); })
        .finally(() => { if (live) setLoading(false); });
    }, 250);
    return () => { live = false; clearTimeout(id); };
  }, [query, open]);
  useEffect(() => {
    if (!open) return undefined;
    const close = (e) => { if (boxRef.current && !boxRef.current.contains(e.target)) { setOpen(false); setQuery(value); } };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [open, value]);

  return (
    <div ref={boxRef} style={{ position: 'relative' }}>
      <input value={query} onChange={e => { setQuery(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)}
        placeholder="Search a company…" style={inputStyle} />
      {open && (
        <div style={{ position: 'absolute', top: 'calc(100% + 4px)', left: 0, right: 0, zIndex: 60, maxHeight: 280, overflowY: 'auto',
          background: 'var(--sfc-14082a, #160d26)', border: '1px solid var(--line-1)', borderRadius: 10, boxShadow: '0 12px 32px rgba(0,0,0,0.45)', padding: 4 }}>
          {loading && !options.length ? (
            <div style={{ padding: 12, display: 'flex', justifyContent: 'center' }}><Loader2 size={14} className="animate-spin" style={{ color: '#a78bfa' }} /></div>
          ) : !options.length ? (
            <div style={{ padding: '9px 10px', color: '#6b7280', fontSize: 13 }}>No company with an emailable lead matches.</div>
          ) : options.map(o => (
            <button key={o.name} onClick={() => { onChange(o.name); setQuery(o.name); setOpen(false); }}
              style={{ display: 'flex', width: '100%', alignItems: 'center', gap: 8, padding: '7px 10px', border: 'none', borderRadius: 7, cursor: 'pointer', textAlign: 'left',
                background: o.name === value ? 'rgba(168,85,247,0.15)' : 'transparent', color: 'var(--text-soft)', fontSize: 13 }}
              onMouseEnter={e => { if (o.name !== value) e.currentTarget.style.background = 'rgba(255,255,255,0.05)'; }}
              onMouseLeave={e => { if (o.name !== value) e.currentTarget.style.background = 'transparent'; }}>
              <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{o.name}</span>
              <span style={{ color: '#6b7280', fontSize: 12, flexShrink: 0 }}>{o.lead_count} lead{o.lead_count === 1 ? '' : 's'}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

// --------------------------------------------------------------------------
// Visual editor: the template shown as the email looks, to click into and type, with a small toolbar. Variables
// stay as {first_name} here (the preview beside it fills them in). It writes back the same HTML the code view shows.
// --------------------------------------------------------------------------
const toolBtn = { display: 'flex', alignItems: 'center', justifyContent: 'center', width: 30, height: 28, background: 'none', border: 'none', borderRadius: 6, cursor: 'pointer', color: 'hsl(var(--pt-d1d5db))' };

const VisualEditor = React.forwardRef(({ html, onChange }, ref) => {
  const frameRef = useRef(null);
  const lastEmitted = useRef(null);

  const doc = () => frameRef.current?.contentDocument;
  const emit = () => {
    const d = doc();
    if (!d?.documentElement) return;
    const doctype = d.doctype ? '<!DOCTYPE html>\n' : '';
    const out = doctype + d.documentElement.outerHTML;
    lastEmitted.current = out;
    onChange(out);
  };

  // Load the HTML into the frame, unless it is what this editor just wrote (that would move the cursor).
  useEffect(() => {
    if (html === lastEmitted.current) return;
    const d = doc();
    if (!d) return;
    d.open();
    d.write(html || '<!DOCTYPE html><html><body style="font-family:Helvetica,Arial,sans-serif;font-size:15px;"><p>Start writing your email here…</p></body></html>');
    d.close();
    d.designMode = 'on';
    lastEmitted.current = html;
    d.addEventListener('input', emit);
    // Links do nothing while editing.
    d.addEventListener('click', e => { if (e.target.closest && e.target.closest('a')) e.preventDefault(); });
  }, [html]);

  const run = (command, value = null) => {
    const d = doc();
    if (!d) return;
    frameRef.current.contentWindow.focus();
    d.execCommand(command, false, value);
    emit();
  };

  // A link: edit the one the cursor is in (a button's link too), or make the selected text one.
  const editLink = () => {
    const d = doc();
    if (!d) return;
    const sel = frameRef.current.contentWindow.getSelection();
    let node = sel?.anchorNode;
    while (node && node.nodeName !== 'A' && node !== d.body) node = node.parentNode;
    const current = node?.nodeName === 'A' ? node.getAttribute('href') : '';
    const url = window.prompt('Link address (or a variable like {unsubscribe_url}):', current || 'https://');
    if (url === null) return;
    if (node?.nodeName === 'A') { node.setAttribute('href', url.trim()); emit(); } else if (url.trim()) run('createLink', url.trim());
  };

  React.useImperativeHandle(ref, () => ({ insertText: (t) => run('insertText', t) }));

  return (
    <div style={{ border: '1px solid var(--line-1)', borderRadius: 10, overflow: 'hidden' }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 2, padding: 4, background: 'hsl(var(--sfr-1e0a32) / 0.6)', borderBottom: '1px solid var(--line-1)' }}>
        <button title="Bold" onMouseDown={e => e.preventDefault()} onClick={() => run('bold')} style={toolBtn}><Bold size={14} /></button>
        <button title="Italic" onMouseDown={e => e.preventDefault()} onClick={() => run('italic')} style={toolBtn}><Italic size={14} /></button>
        <button title="Underline" onMouseDown={e => e.preventDefault()} onClick={() => run('underline')} style={toolBtn}><Underline size={14} /></button>
        <button title="Heading" onMouseDown={e => e.preventDefault()} onClick={() => run('formatBlock', 'h2')} style={toolBtn}><Type size={14} /></button>
        <button title="Bullet list" onMouseDown={e => e.preventDefault()} onClick={() => run('insertUnorderedList')} style={toolBtn}><List size={14} /></button>
        <span style={{ width: 1, background: 'var(--line-1)', margin: '4px 3px' }} />
        <button title="Add or edit a link (also a button's link)" onMouseDown={e => e.preventDefault()} onClick={editLink} style={toolBtn}><Link2 size={14} /></button>
        <button title="Remove link" onMouseDown={e => e.preventDefault()} onClick={() => run('unlink')} style={toolBtn}><Unlink size={14} /></button>
        <span style={{ width: 1, background: 'var(--line-1)', margin: '4px 3px' }} />
        <button title="Undo" onMouseDown={e => e.preventDefault()} onClick={() => run('undo')} style={toolBtn}><Undo2 size={14} /></button>
        <button title="Redo" onMouseDown={e => e.preventDefault()} onClick={() => run('redo')} style={toolBtn}><Redo2 size={14} /></button>
      </div>
      {/* Same origin so the page can edit it; no scripts in it run. */}
      <iframe ref={frameRef} title="Visual editor" sandbox="allow-same-origin" style={{ width: '100%', height: 520, border: 'none', display: 'block', background: '#ffffff' }} />
    </div>
  );
});

// --------------------------------------------------------------------------
// Template editor: HTML on the left, the live preview with a real lead on the right.
// --------------------------------------------------------------------------
const TemplateEditor = ({ initial, variables, starterHtml, industries, onSaved, onCancel }) => {
  const { toast } = useToast();
  const [draft, setDraft] = useState({ name: initial?.name || '', subject: initial?.subject || '', html: initial?.html || '' });
  const [saving, setSaving] = useState(false);
  const [previewIndustry, setPreviewIndustry] = useState(initial?.previewIndustry || '');
  const [leadIndex, setLeadIndex] = useState(0);
  const [preview, setPreview] = useState(null);
  const [previewing, setPreviewing] = useState(false);
  const htmlRef = useRef(null);
  const subjectRef = useRef(null);
  const visualRef = useRef(null);
  const focused = useRef('html');
  // Visual (click into the email and type) or the HTML code: the same template either way.
  const [mode, setMode] = useState('visual');

  // Refresh the preview shortly after typing stops.
  useEffect(() => {
    let live = true;
    const id = setTimeout(async () => {
      setPreviewing(true);
      try {
        const r = await previewEmailTemplate({ subject: draft.subject, html: draft.html, industry: previewIndustry, lead_index: leadIndex });
        if (live) setPreview(r?.data ?? r);
      } catch (_) { /* the last preview stays */ } finally { if (live) setPreviewing(false); }
    }, 500);
    return () => { live = false; clearTimeout(id); };
  }, [draft.subject, draft.html, previewIndustry, leadIndex]);

  const insert = (token) => {
    const field = focused.current;
    if (field === 'html' && mode === 'visual') { visualRef.current?.insertText(token); return; }
    const el = (field === 'subject' ? subjectRef : htmlRef).current;
    const cur = draft[field] || '';
    const start = el?.selectionStart ?? cur.length;
    const end = el?.selectionEnd ?? cur.length;
    setDraft(d => ({ ...d, [field]: cur.slice(0, start) + token + cur.slice(end) }));
    requestAnimationFrame(() => { if (el) { el.focus(); el.setSelectionRange(start + token.length, start + token.length); } });
  };

  const save = async () => {
    setSaving(true);
    try {
      const resp = initial?.id ? await updateEmailTemplate(initial.id, draft) : await createEmailTemplate(draft);
      toast({ title: initial?.id ? 'Template saved' : 'Template created' });
      onSaved(resp?.data ?? resp);
    } catch (e) {
      toast({ title: 'Could not save the template', description: apiErrorMessage(e, 'Please try again.'), variant: 'destructive' });
    } finally { setSaving(false); }
  };

  const unknown = preview?.unknown_variables || [];
  const count = preview?.lead_count || 0;
  const lead = preview?.lead;

  return (
    <div style={{ ...cardStyle, padding: 18 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
        <button onClick={onCancel} style={{ ...iconBtn, padding: '6px 10px', gap: 4, fontSize: 12 }}><ChevronLeft size={13} /> Templates</button>
        <h3 style={{ margin: 0, color: 'var(--text-soft)', fontSize: 16, fontWeight: 700 }}>{initial?.id ? 'Edit template' : 'New template'}</h3>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <Button variant="outline" onClick={onCancel} style={ghostBtn}>Cancel</Button>
          <Button onClick={save} disabled={saving || !draft.name.trim()} style={primaryBtn}>
            {saving ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />} Save template
          </Button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: 18 }}>
        {/* Left: the template */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, minWidth: 0 }}>
          <div>
            <label style={labelStyle}>Template name</label>
            <input value={draft.name} maxLength={200} onChange={e => setDraft(d => ({ ...d, name: e.target.value }))} placeholder="e.g. Spring offer — dental clinics" style={inputStyle} />
          </div>
          <div>
            <label style={labelStyle}>Subject</label>
            <input ref={subjectRef} value={draft.subject} maxLength={500} onFocus={() => { focused.current = 'subject'; }}
              onChange={e => setDraft(d => ({ ...d, subject: e.target.value }))} placeholder="e.g. A quick idea for {company_name}" style={inputStyle} />
          </div>
          <div style={{ padding: '10px 12px', borderRadius: 8, background: 'rgba(168,85,247,0.06)', border: '1px solid rgba(168,85,247,0.2)' }}>
            <p style={{ color: '#a855f7', fontSize: 11, fontWeight: 600, margin: '0 0 8px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Variables — click to insert at the cursor
            </p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {variables.map(v => (
                <button key={v} onClick={() => insert(v)} style={{ background: 'rgba(168,85,247,0.12)', border: '1px solid rgba(168,85,247,0.35)', borderRadius: 6, padding: '3px 8px', cursor: 'pointer', color: 'hsl(var(--pt-c084fc))', fontSize: 11, fontFamily: 'monospace' }}>{v}</button>
              ))}
            </div>
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', marginBottom: 4 }}>
              <div style={{ display: 'flex', border: '1px solid var(--line-1)', borderRadius: 7, overflow: 'hidden' }}>
                {[['visual', 'Visual', Type], ['code', 'HTML code', Code2]].map(([k, l, Icon]) => (
                  <button key={k} onClick={() => setMode(k)} style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '4px 10px', fontSize: 12, border: 'none', cursor: 'pointer',
                    background: mode === k ? 'rgba(168,85,247,0.2)' : 'transparent', color: mode === k ? 'hsl(var(--pt-c084fc))' : '#9ca3af', fontWeight: mode === k ? 600 : 400 }}>
                    <Icon size={12} /> {l}
                  </button>
                ))}
              </div>
              <button onClick={() => { if (!draft.html.trim() || window.confirm('Replace the HTML with the starter layout?')) setDraft(d => ({ ...d, html: starterHtml })); }}
                style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 4, background: 'none', border: 'none', cursor: 'pointer', color: '#a78bfa', fontSize: 12 }}>
                <Wand2 size={12} /> Start from a simple layout
              </button>
            </div>
            {mode === 'visual' ? (
              <div onFocusCapture={() => { focused.current = 'html'; }} onMouseDown={() => { focused.current = 'html'; }}>
                <VisualEditor ref={visualRef} html={draft.html} onChange={html => setDraft(d => ({ ...d, html }))} />
                <p style={{ color: '#6b7280', fontSize: 11, margin: '6px 0 0' }}>
                  Click into the email and type. Select text for bold, links and lists; click a button and use the link tool to change where it goes.
                </p>
              </div>
            ) : (
            <textarea ref={htmlRef} value={draft.html} spellCheck={false} onFocus={() => { focused.current = 'html'; }}
              onChange={e => setDraft(d => ({ ...d, html: e.target.value }))}
              onKeyDown={e => {
                if (e.key !== 'Tab') return;   // Tab indents instead of leaving the box
                e.preventDefault();
                const el = e.currentTarget; const s = el.selectionStart; const t = el.selectionEnd;
                setDraft(d => ({ ...d, html: d.html.slice(0, s) + '  ' + d.html.slice(t) }));
                requestAnimationFrame(() => el.setSelectionRange(s + 2, s + 2));
              }}
              placeholder={'<p>Hi {first_name},</p>\n<p>...</p>\n<p><a href="{unsubscribe_url}">Unsubscribe</a></p>'}
              style={{ ...inputStyle, minHeight: 420, resize: 'vertical', fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace", fontSize: 12.5, lineHeight: 1.55, whiteSpace: 'pre', tabSize: 2 }} />
            )}
            <p style={{ color: '#6b7280', fontSize: 11, margin: '6px 0 0' }}>
              Without {'{unsubscribe_url}'} in it, an unsubscribe link and your campaign's postal address are added at the bottom.
            </p>
          </div>
        </div>

        {/* Right: the live preview */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span style={{ color: 'var(--text-soft)', fontSize: 13, fontWeight: 600 }}>Preview</span>
            {previewing && <Loader2 size={13} className="animate-spin" style={{ color: '#a78bfa' }} />}
            <div style={{ marginLeft: 'auto', width: 210 }}>
              <SdrSelect value={previewIndustry} onChange={v => { setPreviewIndustry(v); setLeadIndex(0); }} style={{ ...inputStyle, padding: '5px 10px', fontSize: 12 }}
                options={[{ value: '', label: 'A lead from any industry' }, ...industries.map(i => ({ value: i.name, label: i.name }))]} />
            </div>
            {count > 1 && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <button title="Previous lead" onClick={() => setLeadIndex(i => (i - 1 + count) % count)} style={iconBtn}><ChevronLeft size={13} /></button>
                <span style={{ color: '#6b7280', fontSize: 12, minWidth: 40, textAlign: 'center' }}>{(preview?.lead_index ?? 0) + 1}/{count}</span>
                <button title="Next lead" onClick={() => setLeadIndex(i => (i + 1) % count)} style={iconBtn}><ChevronRight size={13} /></button>
              </div>
            )}
          </div>
          <span style={{ color: '#6b7280', fontSize: 12 }}>
            {lead ? (lead.sample ? 'Shown with a sample lead.' : `As ${lead.name || lead.email}${lead.company ? ` at ${lead.company}` : ''} will see it.`) : ' '}
          </span>
          {unknown.length > 0 && (
            <div style={{ padding: '8px 12px', borderRadius: 8, background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.3)', color: 'hsl(var(--pt-fbbf24))', fontSize: 12 }}>
              <AlertTriangle size={11} style={{ display: 'inline', marginRight: 4 }} />
              Still to fill in before this can be sent: {unknown.join(', ')}
            </div>
          )}
          <EmailFrame subject={preview?.subject} html={preview?.html} loading={previewing} />
        </div>
      </div>
    </div>
  );
};

// --------------------------------------------------------------------------
// Main tab
// --------------------------------------------------------------------------
const SDREmailTemplatesTab = () => {
  const { toast } = useToast();
  const [templates, setTemplates] = useState([]);
  const [presets, setPresets] = useState([]);
  const [variables, setVariables] = useState([]);
  const [starterHtml, setStarterHtml] = useState('');
  const [industries, setIndustries] = useState([]);
  const [sends, setSends] = useState([]);
  const [mailboxes, setMailboxes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);          // null = the list; {} = new; a template = editing it
  const [deleting, setDeleting] = useState(null);

  // Send panel
  const [sendTo, setSendTo] = useState('industry');      // 'industry' | 'company'
  const [sendIndustry, setSendIndustry] = useState('');
  const [sendCompany, setSendCompany] = useState('');
  // Who it goes to, as the API takes it, and as it reads in sentences.
  const audience = sendTo === 'company' ? { company: sendCompany } : { industry: sendIndustry };
  const audienceValue = sendTo === 'company' ? sendCompany : sendIndustry;
  const audienceLabel = sendTo === 'company' ? `at ${sendCompany}` : `of ${sendIndustry}`;
  const [sendTemplate, setSendTemplate] = useState('');
  const [sendCampaign, setSendCampaign] = useState('');
  const [summary, setSummary] = useState(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [sendPreview, setSendPreview] = useState(null);
  const [confirming, setConfirming] = useState(false);
  const [starting, setStarting] = useState(false);
  const [openSend, setOpenSend] = useState(null);        // a send's id, with its recipients shown
  const [openSendData, setOpenSendData] = useState(null);
  const [templateVersion, setTemplateVersion] = useState(0);   // a saved edit refreshes the send summary

  const loadTemplates = useCallback(async () => {
    const r = await listEmailTemplates();
    setTemplates(r?.data || []);
    setPresets(r?.presets || []);
    setVariables(r?.variables || []);
    setStarterHtml(r?.starter_html || '');
  }, []);
  const loadSends = useCallback(async () => {
    const r = await listEmailSends();
    setSends(r?.data || []);
    setMailboxes(r?.mailboxes || []);
  }, []);

  useEffect(() => {
    Promise.allSettled([loadTemplates(), loadSends(), listLeadIndustries().then(r => setIndustries(r?.data || []))])
      .finally(() => setLoading(false));
  }, [loadTemplates, loadSends]);

  // While a send is going out, its numbers move on their own.
  const anySending = sends.some(s => s.status === 'sending');
  useEffect(() => {
    if (!anySending) return undefined;
    const id = setInterval(() => { loadSends().catch(() => {}); }, 10000);
    return () => clearInterval(id);
  }, [anySending, loadSends]);

  // Who would get it: counted (not sent) whenever the three choices change.
  useEffect(() => {
    setSummary(null);
    setSendPreview(null);
    if (!audienceValue || !sendTemplate || !sendCampaign) return undefined;
    let live = true;
    setSummaryLoading(true);
    const body = { template_id: Number(sendTemplate), campaign_id: Number(sendCampaign), ...audience };
    Promise.all([
      startEmailSend({ ...body, dry_run: true }).then(r => r?.data ?? r).catch(e => ({ error: apiErrorMessage(e, 'Could not count the leads.') })),
      getEmailTemplate(Number(sendTemplate)).then(r => r?.data ?? r)
        .then(t => previewEmailTemplate({ subject: t.subject, html: t.html, ...audience, campaign_id: Number(sendCampaign) }))
        .then(r => r?.data ?? r).catch(() => null),
    ]).then(([s, p]) => { if (live) { setSummary(s); setSendPreview(p); } })
      .finally(() => { if (live) setSummaryLoading(false); });
    return () => { live = false; };
  }, [sendTo, sendIndustry, sendCompany, sendTemplate, sendCampaign, templateVersion]);

  const handleDuplicate = async (t) => {
    try {
      const full = (await getEmailTemplate(t.id))?.data;
      await createEmailTemplate({ name: `${full.name} (copy)`.slice(0, 200), subject: full.subject, html: full.html });
      toast({ title: 'Template duplicated' });
      loadTemplates();
    } catch (e) {
      toast({ title: 'Could not duplicate', description: apiErrorMessage(e, 'Please try again.'), variant: 'destructive' });
    }
  };
  const handleEdit = async (t, selectAfterSave = false) => {
    try { setEditing({ ...(await getEmailTemplate(t.id))?.data, selectAfterSave }); } catch (e) {
      toast({ title: 'Could not open the template', description: apiErrorMessage(e, 'Please try again.'), variant: 'destructive' });
    }
  };
  const handleDelete = async () => {
    const t = deleting;
    setDeleting(null);
    try {
      await deleteEmailTemplate(t.id);
      toast({ title: `Deleted "${t.name}"` });
      if (String(t.id) === sendTemplate) setSendTemplate('');
      loadTemplates();
    } catch (e) {
      toast({ title: 'Could not delete', description: apiErrorMessage(e, 'Please try again.'), variant: 'destructive' });
    }
  };

  const handleStart = async () => {
    setStarting(true);
    try {
      const r = await startEmailSend({ template_id: Number(sendTemplate), campaign_id: Number(sendCampaign), ...audience });
      toast({ title: 'Sending started', description: r?.message });
      setConfirming(false);
      setSendTemplate(''); setSendIndustry(''); setSendCompany('');
      loadSends();
    } catch (e) {
      toast({ title: 'Could not start the send', description: apiErrorMessage(e, 'Please try again.'), variant: 'destructive' });
    } finally { setStarting(false); }
  };

  const handleStop = async (send) => {
    try {
      const r = await stopEmailSend(send.id);
      toast({ title: 'Send stopped', description: r?.message });
      loadSends();
      if (openSend === send.id) toggleSend(send.id, true);
    } catch (e) {
      toast({ title: 'Could not stop the send', description: apiErrorMessage(e, 'Please try again.'), variant: 'destructive' });
    }
  };

  const toggleSend = async (id, refresh = false) => {
    if (openSend === id && !refresh) { setOpenSend(null); return; }
    setOpenSend(id);
    setOpenSendData(null);
    try { setOpenSendData((await getEmailSend(id))?.data); } catch (_) { setOpenSendData({ recipients: [] }); }
  };

  if (editing) {
    return (
      <TemplateEditor initial={editing} variables={variables} starterHtml={starterHtml} industries={industries}
        onCancel={() => setEditing(null)}
        onSaved={(t) => {
          // Opened from the send panel's dropdown: back there with it chosen.
          if (editing.selectAfterSave && t?.id) setSendTemplate(String(t.id));
          setTemplateVersion(v => v + 1);
          setEditing(null);
          loadTemplates();
        }} />
    );
  }

  // A ready-made template opens in the editor as a new one of your own, previewed with a lead of a matching industry.
  const usePreset = (p, selectAfterSave = false) => {
    const wanted = (p.industries || []).map(i => i.toLowerCase());
    const match = industries.find(i => wanted.includes(i.name.toLowerCase()))
      || industries.find(i => i.name.toLowerCase() === sendIndustry.toLowerCase());
    setEditing({ name: p.name, subject: p.subject, html: p.html, previewIndustry: match?.name || '', selectAfterSave });
  };

  // The send panel's template choices: your saved templates, then the ready-made ones. A ready-made one has parts to
  // fill in first, so choosing it opens it in the editor; saved, it comes back here chosen.
  const PRESET_PREFIX = 'preset:';
  const templateOptions = [
    ...templates.map(t => ({ value: String(t.id), label: t.name })),
    ...presets.map(p => ({ value: PRESET_PREFIX + p.key, label: `Ready-made: ${p.name} — fill in & save first` })),
  ];
  const chooseTemplate = (v) => {
    if (v.startsWith(PRESET_PREFIX)) {
      const p = presets.find(x => PRESET_PREFIX + x.key === v);
      if (p) usePreset(p, true);
      return;
    }
    setSendTemplate(v);
  };

  const readyMailboxes = mailboxes.filter(m => m.ready);
  const mailbox = mailboxes.find(m => String(m.campaign_id) === sendCampaign);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Templates */}
      <div style={{ ...cardStyle, padding: 18 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
          <FileCode size={18} color="#a855f7" />
          <h3 style={{ margin: 0, color: 'var(--text-soft)', fontSize: 16, fontWeight: 700 }}>Email templates</h3>
          <Button onClick={() => setEditing({})} style={{ ...primaryBtn, marginLeft: 'auto' }}><Plus size={14} /> New template</Button>
        </div>
        {loading ? (
          <div style={{ padding: 30, display: 'flex', justifyContent: 'center' }}><Loader2 size={18} className="animate-spin" style={{ color: '#a78bfa' }} /></div>
        ) : templates.length === 0 ? (
          <p style={{ color: '#6b7280', fontSize: 13, margin: 0, padding: '18px 0', textAlign: 'center' }}>
            No templates yet. Create one with your own HTML — you'll see it with a real lead as you write it.
          </p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {templates.map(t => (
              <div key={t.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 4px', borderTop: '1px solid hsl(var(--surface-invert) / 0.05)' }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ color: 'var(--text-soft)', fontSize: 14, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.name}</div>
                  <div style={{ color: '#6b7280', fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {t.subject || '(no subject)'} · edited {fmtDate(t.updated_at)}
                  </div>
                </div>
                <button title="Edit" onClick={() => handleEdit(t)} style={iconBtn}><Edit2 size={13} /></button>
                <button title="Duplicate" onClick={() => handleDuplicate(t)} style={iconBtn}><Copy size={13} /></button>
                <button title="Delete" onClick={() => setDeleting(t)} style={{ ...iconBtn, color: '#f87171' }}><Trash2 size={13} /></button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Ready-made */}
      {presets.length > 0 && (
        <div style={{ ...cardStyle, padding: 18 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
            <Wand2 size={17} color="#a855f7" />
            <h3 style={{ margin: 0, color: 'var(--text-soft)', fontSize: 16, fontWeight: 700 }}>Ready-made templates</h3>
          </div>
          <p style={{ color: '#6b7280', fontSize: 12, margin: '0 0 14px' }}>
            Designed for an industry and ready to go: open one, fill in the parts in [square brackets] with what you offer, and save it as your own.
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))', gap: 12 }}>
            {presets.map(p => (
              <div key={p.key} style={{ border: '1px solid var(--line-1)', borderRadius: 10, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
                <div style={{ height: 6, background: p.accent || '#7c3aed' }} />
                <div style={{ padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 6, flex: 1 }}>
                  <div style={{ color: 'var(--text-soft)', fontSize: 14, fontWeight: 600 }}>{p.name}</div>
                  <div style={{ color: '#6b7280', fontSize: 12, lineHeight: 1.5, flex: 1 }}>{p.description}</div>
                  <div style={{ color: '#9ca3af', fontSize: 11, fontStyle: 'italic', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>Subject: {p.subject}</div>
                  <Button onClick={() => usePreset(p)} variant="outline" style={{ ...ghostBtn, marginTop: 6, justifyContent: 'center', color: 'hsl(var(--pt-c084fc))', borderColor: 'rgba(168,85,247,0.35)' }}>
                    <Edit2 size={13} /> Use this
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Send */}
      <div style={{ ...cardStyle, padding: 18 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
          <Send size={17} color="#a855f7" />
          <h3 style={{ margin: 0, color: 'var(--text-soft)', fontSize: 16, fontWeight: 700 }}>Send to an industry</h3>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', marginBottom: 4 }}>
              <label style={{ ...labelStyle, marginBottom: 0 }}>1. Send to</label>
              {/* An industry's leads, or the leads at one company. */}
              <div style={{ marginLeft: 'auto', display: 'flex', border: '1px solid var(--line-1)', borderRadius: 7, overflow: 'hidden' }}>
                {[['industry', 'An industry'], ['company', 'One company']].map(([k, l]) => (
                  <button key={k} onClick={() => setSendTo(k)} style={{ padding: '2px 9px', fontSize: 11, border: 'none', cursor: 'pointer',
                    background: sendTo === k ? 'rgba(168,85,247,0.2)' : 'transparent', color: sendTo === k ? 'hsl(var(--pt-c084fc))' : '#6b7280', fontWeight: sendTo === k ? 600 : 400 }}>{l}</button>
                ))}
              </div>
            </div>
            {sendTo === 'company' ? (
              <CompanyPicker value={sendCompany} onChange={setSendCompany} />
            ) : (
              <SdrSelect value={sendIndustry} onChange={setSendIndustry} style={inputStyle} placeholder="Choose an industry"
                options={industries.map(i => ({ value: i.name, label: `${i.name} (${i.lead_count})` }))} />
            )}
          </div>
          <div>
            <label style={labelStyle}>2. Template</label>
            <div style={{ display: 'flex', gap: 6 }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <SdrSelect value={sendTemplate} onChange={chooseTemplate} style={inputStyle}
                  placeholder={templates.length ? 'Choose a template' : presets.length ? 'Choose a ready-made template' : 'Create a template first'}
                  options={templateOptions.length ? templateOptions : [{ value: '__none__', label: 'No templates yet — create one above', disabled: true }]} />
              </div>
              {/* Change the chosen template before sending: saved, the summary and preview below show the change. */}
              {sendTemplate && (
                <button title="Edit this template" onClick={() => handleEdit({ id: Number(sendTemplate) }, true)}
                  style={{ ...iconBtn, padding: '0 10px', gap: 4, fontSize: 12, color: 'hsl(var(--pt-c084fc))', borderColor: 'rgba(168,85,247,0.35)' }}>
                  <Edit2 size={13} /> Edit
                </button>
              )}
            </div>
            {!templates.length && presets.length > 0 && (
              <p style={{ color: '#6b7280', fontSize: 11, margin: '4px 0 0' }}>A ready-made one opens in the editor: fill in the [square brackets], save, and it's ready to send.</p>
            )}
          </div>
          <div>
            <label style={labelStyle}>3. Send from (a campaign's mailbox)</label>
            <SdrSelect value={sendCampaign} onChange={setSendCampaign} style={inputStyle}
              placeholder={readyMailboxes.length ? 'Choose a mailbox' : 'No campaign has a mailbox set up'}
              options={mailboxes.map(m => ({
                value: String(m.campaign_id), disabled: !m.ready,
                label: m.ready ? `${m.campaign_name} — ${m.from_email}` : `${m.campaign_name} (no mailbox set up)`,
              }))} />
            {mailbox?.ready && (
              <p style={{ color: '#6b7280', fontSize: 11, margin: '4px 0 0' }}>
                From {mailbox.sender_name || mailbox.from_email}{mailbox.sender_company ? `, ${mailbox.sender_company}` : ''} · {mailbox.left_today} more email{mailbox.left_today === 1 ? '' : 's'} today
              </p>
            )}
          </div>
        </div>

        {(summaryLoading || summary) && (
          <div style={{ marginTop: 16, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 16, alignItems: 'start' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {summaryLoading ? (
                <span style={{ color: '#6b7280', fontSize: 13, display: 'flex', alignItems: 'center', gap: 6 }}><Loader2 size={13} className="animate-spin" /> Counting the leads…</span>
              ) : summary?.error ? (
                <div style={{ padding: '10px 12px', borderRadius: 8, background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.3)', color: '#f87171', fontSize: 13 }}>{summary.error}</div>
              ) : (
                <>
                  <div style={{ padding: '12px 14px', borderRadius: 10, background: 'rgba(52,211,153,0.07)', border: '1px solid rgba(52,211,153,0.25)' }}>
                    <div style={{ color: '#34d399', fontSize: 22, fontWeight: 700 }}>{summary.will_send.toLocaleString()}</div>
                    <div style={{ color: 'var(--text-soft)', fontSize: 13 }}>lead{summary.will_send === 1 ? '' : 's'} {audienceLabel} will get this email</div>
                    {summary.skipped > 0 && (
                      <div style={{ color: '#f59e0b', fontSize: 12, marginTop: 4 }}>{summary.skipped} skipped: on the do-not-email list, or bounced before</div>
                    )}
                  </div>
                  <p style={{ color: '#6b7280', fontSize: 12, margin: 0, lineHeight: 1.5 }}>
                    It goes out a few at a time, within the mailbox's daily limit (shared with its campaigns), and each lead gets at most one email a day.
                    {mailbox && summary.will_send > mailbox.left_today ? ` At today's limit, the rest go out over the next days.` : ''}
                  </p>
                  <div>
                    <Button onClick={() => setConfirming(true)} disabled={!summary.will_send} style={primaryBtn}>
                      <Send size={13} /> Send to {summary.will_send.toLocaleString()} lead{summary.will_send === 1 ? '' : 's'}
                    </Button>
                  </div>
                </>
              )}
            </div>
            {sendPreview && (
              <div>
                <div style={{ color: '#6b7280', fontSize: 12, marginBottom: 6 }}>
                  {sendPreview.lead?.sample ? 'Preview' : `Preview — as ${sendPreview.lead?.name || sendPreview.lead?.email} will see it`}
                </div>
                <EmailFrame subject={sendPreview.subject} html={sendPreview.html} height={420} />
              </div>
            )}
          </div>
        )}
      </div>

      {/* Sends */}
      <div style={{ ...cardStyle, padding: 18 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
          <Mail size={17} color="#a855f7" />
          <h3 style={{ margin: 0, color: 'var(--text-soft)', fontSize: 16, fontWeight: 700 }}>Sends</h3>
        </div>
        {sends.length === 0 ? (
          <p style={{ color: '#6b7280', fontSize: 13, margin: 0, padding: '10px 0' }}>Nothing sent yet.</p>
        ) : sends.map(s => {
          const st = SEND_STATUS[s.status] || SEND_STATUS.done;
          const done = s.counts.sent + s.counts.skipped + s.counts.failed;
          const pct = s.total ? Math.round((done / s.total) * 100) : 100;
          return (
            <div key={s.id} style={{ borderTop: '1px solid hsl(var(--surface-invert) / 0.05)', padding: '10px 2px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                <div style={{ flex: 1, minWidth: 200 }}>
                  <div style={{ color: 'var(--text-soft)', fontSize: 14, fontWeight: 600 }}>{s.template_name || 'Template'} → {s.company || s.industry}</div>
                  <div style={{ color: '#6b7280', fontSize: 12 }}>{fmtDate(s.created_at)} · from {s.campaign_name || 'a deleted campaign'}</div>
                </div>
                <span style={{ color: st.color, fontSize: 12, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 5 }}>
                  {s.status === 'sending' && <Loader2 size={12} className="animate-spin" />}{st.label}
                </span>
                <span style={{ color: '#9ca3af', fontSize: 12 }}>
                  <span style={{ color: RECIPIENT_COLOR.sent }}>{s.counts.sent} sent</span> · {s.counts.queued} queued
                  {s.counts.skipped ? <> · <span style={{ color: RECIPIENT_COLOR.skipped }}>{s.counts.skipped} skipped</span></> : null}
                  {s.counts.failed ? <> · <span style={{ color: RECIPIENT_COLOR.failed }}>{s.counts.failed} failed</span></> : null}
                </span>
                {s.status === 'sending' && (
                  <button onClick={() => handleStop(s)} title="Stop: the leads not emailed yet won't be" style={{ ...iconBtn, gap: 4, fontSize: 12, padding: '5px 9px', color: '#f87171' }}><Square size={11} /> Stop</button>
                )}
                <button onClick={() => toggleSend(s.id)} title="Who got it" style={iconBtn}>{openSend === s.id ? <ChevronUp size={13} /> : <ChevronDown size={13} />}</button>
              </div>
              <div style={{ height: 4, borderRadius: 4, background: 'hsl(var(--surface-invert) / 0.06)', marginTop: 8, overflow: 'hidden' }}>
                <div style={{ width: `${pct}%`, height: '100%', background: st.color, transition: 'width 0.3s' }} />
              </div>
              {openSend === s.id && (
                <div style={{ marginTop: 10, maxHeight: 280, overflowY: 'auto', border: '1px solid var(--line-1)', borderRadius: 8 }}>
                  {!openSendData ? (
                    <div style={{ padding: 16, display: 'flex', justifyContent: 'center' }}><Loader2 size={14} className="animate-spin" style={{ color: '#a78bfa' }} /></div>
                  ) : openSendData.recipients.map((r, i) => (
                    <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'center', padding: '6px 10px', borderTop: i ? '1px solid hsl(var(--surface-invert) / 0.04)' : 'none', fontSize: 12 }}>
                      <span style={{ width: 8, height: 8, borderRadius: 4, background: RECIPIENT_COLOR[r.status], flexShrink: 0 }} />
                      <span style={{ color: 'var(--text-soft)', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>{r.name ? `${r.name} · ` : ''}{r.email}</span>
                      <span style={{ color: RECIPIENT_COLOR[r.status], textTransform: 'capitalize' }}>{r.status}</span>
                      {r.error && <span title={r.error} style={{ color: '#6b7280', maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.error}</span>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Confirm send */}
      <Dialog open={confirming} onOpenChange={setConfirming}>
        <DialogContent style={{ background: 'linear-gradient(135deg,var(--sfc-0f0a1f) 0%,var(--sfc-14082a) 100%)', border: '1px solid var(--line-1)', color: 'var(--text-soft)', maxWidth: 440 }}>
          <DialogHeader><DialogTitle style={{ color: 'var(--text-soft)' }}>Send this email?</DialogTitle></DialogHeader>
          <p style={{ color: 'hsl(var(--pt-9ca3af))', fontSize: 14, lineHeight: 1.6, margin: 0 }}>
            <strong style={{ color: 'var(--text-soft)' }}>{templates.find(t => String(t.id) === sendTemplate)?.name}</strong> to{' '}
            <strong style={{ color: 'var(--text-soft)' }}>{summary?.will_send?.toLocaleString()} lead{summary?.will_send === 1 ? '' : 's'}</strong> {audienceLabel},
            from {mailbox?.from_email}. Emails that have gone out can't be taken back; you can stop the rest at any time.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirming(false)} style={ghostBtn}><X size={13} /> Cancel</Button>
            <Button onClick={handleStart} disabled={starting} style={primaryBtn}>
              {starting ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} />} Send
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Confirm delete */}
      <Dialog open={!!deleting} onOpenChange={o => { if (!o) setDeleting(null); }}>
        <DialogContent style={{ background: 'linear-gradient(135deg,var(--sfc-0f0a1f) 0%,var(--sfc-14082a) 100%)', border: '1px solid var(--line-1)', color: 'var(--text-soft)', maxWidth: 420 }}>
          <DialogHeader><DialogTitle style={{ color: 'var(--text-soft)' }}>Delete this template?</DialogTitle></DialogHeader>
          <p style={{ color: 'hsl(var(--pt-9ca3af))', fontSize: 14, margin: 0 }}>
            "{deleting?.name}" will be deleted. Sends already made with it keep their own copy.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleting(null)} style={ghostBtn}>Keep it</Button>
            <Button onClick={handleDelete} style={{ ...primaryBtn, background: '#dc2626' }}><Trash2 size={13} /> Delete</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default SDREmailTemplatesTab;
