import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Users, Search, Plus, Upload, Brain,
  Flame, Thermometer, Snowflake, ExternalLink, Linkedin, Globe,
  MapPin, Briefcase, Phone, Mail, TrendingUp, RefreshCw, X,
  Loader2, Trash2, Zap, ChevronDown, HelpCircle, CheckCircle, Copy,
  ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight,
  ArrowUpDown, SlidersHorizontal, Download, FileText, FileSpreadsheet,
  Square, CheckSquare, MinusSquare, ShieldCheck, ShieldAlert, Target,
  AlertTriangle, Sparkles, Route, CheckCircle2, Tag, Pencil, Check,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import { useToast } from '@/components/ui/use-toast';
import { ToastAction } from '@/components/ui/toast';
import {
  listLeads, exportAllLeadsCsv, createLead, deleteLead, qualifyLead, importLeadsFromCSV,
  researchLead, getLeadResearch, researchLeads, getResearchJob, fetchApifyLeads, listIcpProfiles,
  createIcpProfile, updateIcpProfile, setDefaultIcpProfile, deleteIcpProfile,
  enrichLead, getLeadEnrichment, enrichLeadsBatch,
  bulkDeleteLeads, getSdrSettings, restoreLead, bulkRestoreLeads, qualifyAllLeads, updateLead,
  listLeadCategories, renameLeadCategory, deleteLeadCategory, bulkSetLeadCategory,
} from '@/services/aiSdrService';

// --------------------------------------------------------------------------
// Ensure URLs always have a protocol so <a href> doesn't treat them as relative
// --------------------------------------------------------------------------
const safeUrl = (url) => {
  if (!url) return '';
  const trimmed = url.trim();
  if (/^https?:\/\//i.test(trimmed)) return trimmed;
  return `https://${trimmed}`;
};

// --------------------------------------------------------------------------
// Score category system (fixed thresholds)
// --------------------------------------------------------------------------
const SCORE_CATEGORIES = [
  { min: 90, key: 'hot_lead',        label: 'Hot Lead 🔥',        color: '#f43f5e', bg: 'rgba(244,63,94,0.12)',  border: 'rgba(244,63,94,0.35)'  },
  { min: 75, key: 'high_potential',  label: 'High Potential',     color: '#f59e0b', bg: 'rgba(245,158,11,0.12)', border: 'rgba(245,158,11,0.35)' },
  { min: 60, key: 'qualified',       label: 'Qualified Lead',     color: '#10b981', bg: 'rgba(16,185,129,0.12)', border: 'rgba(16,185,129,0.35)' },
  { min: 40, key: 'low_priority',    label: 'Low Priority',       color: '#6b7280', bg: 'rgba(107,114,128,0.1)', border: 'rgba(107,114,128,0.3)' },
  { min: 0,  key: 'reject',          label: 'Reject',             color: '#4b5563', bg: 'rgba(75,85,99,0.08)',   border: 'rgba(75,85,99,0.25)'   },
];

function getScoreCategory(score) {
  if (score == null) return null;
  return SCORE_CATEGORIES.find(c => score >= c.min) || SCORE_CATEGORIES[SCORE_CATEGORIES.length - 1];
}

// ── CSV preview (client-side) — mirrors the backend's flexible header mapping
// so the modal shows exactly what will be imported. Actual import is still done
// by the backend for correctness. ─────────────────────────────────────────────
const CSV_FIELD_ALIASES = {
  full_name:        ['fullname', 'name', 'contactname', 'leadname'],
  first_name:       ['firstname', 'fname', 'givenname'],
  last_name:        ['lastname', 'lname', 'surname', 'familyname'],
  email:            ['email', 'emailaddress', 'workemail', 'businessemail', 'mail'],
  phone:            ['phone', 'phonenumber', 'mobile', 'mobilenumber', 'tel', 'telephone'],
  job_title:        ['jobtitle', 'title', 'position', 'role', 'designation'],
  company_name:     ['companyname', 'company', 'organization', 'organisation', 'employer', 'account'],
  company_industry: ['companyindustry', 'industry', 'sector', 'vertical'],
  company_size:     ['companysize', 'size', 'employees', 'employeecount', 'headcount'],
  company_location: ['companylocation', 'location', 'city', 'country', 'region', 'address'],
  linkedin_url:     ['linkedinurl', 'linkedin', 'linkedinprofile', 'profileurl'],
  company_website:  ['companywebsite', 'website', 'url', 'domain', 'web'],
};
const CSV_PREVIEW_COLUMNS = [
  { key: 'full_name', label: 'Name' },
  { key: 'email', label: 'Email' },
  { key: 'job_title', label: 'Title' },
  { key: 'company_name', label: 'Company' },
  { key: 'company_location', label: 'Location' },
];

// Minimal RFC-4180-ish CSV line splitter (handles quoted commas).
function splitCsvLine(line) {
  const out = [];
  let cur = '', inQ = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (inQ) {
      if (ch === '"' && line[i + 1] === '"') { cur += '"'; i++; }
      else if (ch === '"') inQ = false;
      else cur += ch;
    } else if (ch === '"') inQ = true;
    else if (ch === ',') { out.push(cur); cur = ''; }
    else cur += ch;
  }
  out.push(cur);
  return out.map(s => s.trim());
}

function parseCsvPreview(text) {
  const lines = String(text || '').replace(/\r\n/g, '\n').split('\n').filter(l => l.trim() !== '');
  if (!lines.length) return { rows: [], columns: CSV_PREVIEW_COLUMNS, skippedEmpty: 0, total: 0 };
  const headers = splitCsvLine(lines[0]).map(h => h.replace(/[^a-z0-9]/gi, '').toLowerCase());
  const idxFor = (field) => {
    for (const alias of CSV_FIELD_ALIASES[field] || []) {
      const i = headers.indexOf(alias);
      if (i !== -1) return i;
    }
    return -1;
  };
  const map = Object.fromEntries(Object.keys(CSV_FIELD_ALIASES).map(f => [f, idxFor(f)]));

  const rows = [];
  let skippedEmpty = 0;
  for (let r = 1; r < lines.length; r++) {
    const cells = splitCsvLine(lines[r]);
    const get = (f) => (map[f] >= 0 ? (cells[map[f]] || '').trim() : '');
    const fn = get('first_name'), ln = get('last_name');
    const full = get('full_name') || `${fn} ${ln}`.trim();
    const company = get('company_name');
    const email = get('email');
    if (!full && !company && !email) { skippedEmpty++; continue; }
    rows.push({
      full_name: full, email, job_title: get('job_title'),
      company_name: company, company_location: get('company_location'),
    });
  }
  return { rows, columns: CSV_PREVIEW_COLUMNS, skippedEmpty, total: rows.length };
}

const SCORE_COLOR = (s) => {
  if (s == null) return '#4b5563';
  const cat = getScoreCategory(s);
  return cat ? cat.color : '#4b5563';
};

const TEMP_CONFIG = {
  hot:  { label: 'Hot',  icon: Flame,       color: '#f43f5e', bg: 'rgba(244,63,94,0.12)',  border: 'rgba(244,63,94,0.3)'  },
  warm: { label: 'Warm', icon: Thermometer, color: '#f59e0b', bg: 'rgba(245,158,11,0.12)', border: 'rgba(245,158,11,0.3)' },
  cold: { label: 'Cold', icon: Snowflake,   color: '#60a5fa', bg: 'rgba(96,165,250,0.12)', border: 'rgba(96,165,250,0.3)' },
};

const SOURCE_LABELS = {
  apollo: 'Apollo.io', apify: 'Apify', ai_generated: 'AI Gen', csv_import: 'CSV', manual: 'Manual',
};

// The dot beside a lead's name; colours match the Enrichment filter. Not-yet-enriched leads get none.
const ENRICHMENT_DOT = {
  done:       { color: '#34d399', title: 'Enriched' },
  pending:    { color: '#60a5fa', title: 'Enriching' },
  processing: { color: '#60a5fa', title: 'Enriching' },
  failed:     { color: '#f87171', title: 'Enrichment failed' },
};

const LEAD_STATUS_CONFIG = {
  new:              { label: 'New',             color: '#6b7280', bg: 'rgba(107,114,128,0.12)', border: 'rgba(107,114,128,0.25)' },
  qualified:        { label: 'Qualified',        color: '#60a5fa', bg: 'rgba(96,165,250,0.12)',  border: 'rgba(96,165,250,0.25)'  },
  contacted:        { label: 'Contacted',        color: '#a78bfa', bg: 'rgba(167,139,250,0.12)', border: 'rgba(167,139,250,0.25)' },
  replied:          { label: 'Replied',          color: '#4ade80', bg: 'rgba(74,222,128,0.12)',  border: 'rgba(74,222,128,0.25)'  },
  meeting_scheduled:{ label: 'Meeting',          color: '#34d399', bg: 'rgba(52,211,153,0.12)',  border: 'rgba(52,211,153,0.25)'  },
  converted:        { label: 'Converted',        color: '#fbbf24', bg: 'rgba(251,191,36,0.12)',  border: 'rgba(251,191,36,0.25)'  },
  disqualified:     { label: 'Disqualified',     color: '#f87171', bg: 'rgba(248,113,113,0.12)', border: 'rgba(248,113,113,0.25)' },
};

const BLANK_LEAD = {
  first_name: '', last_name: '', email: '', phone: '',
  job_title: '', company_name: '', company_industry: '',
  company_size: '', company_location: '', linkedin_url: '',
};

// --------------------------------------------------------------------------
// Score breakdown categories (new 5-dim model)
// --------------------------------------------------------------------------
const SCORE_DIMS = [
  { key: 'company_quality',    label: 'Company Quality',    max: 30, icon: Briefcase, color: '#a855f7' },
  { key: 'contact_quality',    label: 'Contact Quality',    max: 20, icon: ShieldCheck, color: '#10b981' },
  { key: 'business_fit',       label: 'Business Fit',       max: 25, icon: Target,    color: '#3b82f6' },
  { key: 'engagement_signals', label: 'Engagement Signals', max: 15, icon: TrendingUp, color: '#f59e0b' },
  { key: 'data_completeness',  label: 'Data Completeness',  max: 10, icon: CheckCircle2, color: '#6b7280' },
];

// --------------------------------------------------------------------------
// Export helpers
// --------------------------------------------------------------------------
const EXPORT_COLUMNS = [
  { key: 'full_name',          label: 'Name' },
  { key: 'email',              label: 'Email' },
  { key: 'phone',              label: 'Phone' },
  { key: 'job_title',          label: 'Job Title' },
  { key: 'company_name',       label: 'Company' },
  { key: 'category',           label: 'Industry Category' },
  { key: 'company_industry',   label: 'Company Industry' },
  { key: 'company_size',       label: 'Company Size' },
  { key: 'company_location',   label: 'Location' },
  { key: 'score',              label: 'Score' },
  { key: 'temperature',        label: 'Temperature' },
  { key: 'status',             label: 'Status' },
  { key: 'source',             label: 'Source' },
  { key: 'linkedin_url',       label: 'LinkedIn' },
  { key: 'company_website',    label: 'Website' },
];

async function exportToExcel(leads, filename = 'leads') {
  const XLSX = await import('xlsx');
  const rows = leads.map((l, i) => ({
    'Sr#': i + 1,
    ...Object.fromEntries(EXPORT_COLUMNS.map(c => [c.label, l[c.key] ?? ''])),
  }));
  const ws = XLSX.utils.json_to_sheet(rows);
  ws['!cols'] = [{ wch: 6 }, ...EXPORT_COLUMNS.map(c => ({ wch: Math.max(c.label.length + 2, 16) }))];
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, 'Leads');
  XLSX.writeFile(wb, `${filename}.xlsx`);
}

async function exportToPdf(leads, filename = 'leads') {
  const { default: jsPDF } = await import('jspdf');
  const { default: autoTable } = await import('jspdf-autotable');
  const doc = new jsPDF({ orientation: 'landscape', unit: 'mm', format: 'a4' });
  doc.setFillColor(255, 255, 255);
  doc.rect(0, 0, 297, 210, 'F');
  doc.setFillColor(124, 58, 237);
  doc.rect(0, 0, 297, 10, 'F');
  doc.setTextColor(30, 30, 30);
  doc.setFontSize(16);
  doc.setFont('helvetica', 'bold');
  doc.text('SDR Leads Export', 14, 20);
  doc.setFontSize(8.5);
  doc.setFont('helvetica', 'normal');
  doc.setTextColor(100, 100, 100);
  doc.text(`Generated: ${new Date().toLocaleString()}   |   Total leads: ${leads.length}`, 14, 27);
  doc.setDrawColor(200, 200, 200);
  doc.setLineWidth(0.3);
  doc.line(14, 30, 283, 30);
  // Fit fewer data columns to leave room for the leading Sr# column.
  const columns = EXPORT_COLUMNS.slice(0, 10);
  autoTable(doc, {
    startY: 34,
    // Prepend a "Sr#" column so any lead can be referenced by row number.
    head: [['Sr#', ...columns.map(c => c.label)]],
    body: leads.map((l, i) => [
      String(i + 1),
      ...columns.map(c => { const v = l[c.key]; return v === null || v === undefined || v === '' ? '—' : String(v); }),
    ]),
    styles: { fontSize: 8, cellPadding: { top: 3, bottom: 3, left: 4, right: 4 }, textColor: [30, 30, 30], fillColor: [255, 255, 255], lineColor: [220, 220, 220], lineWidth: 0.25, overflow: 'linebreak' },
    headStyles: { fillColor: [124, 58, 237], textColor: [255, 255, 255], fontStyle: 'bold', fontSize: 8.5, halign: 'left' },
    alternateRowStyles: { fillColor: [248, 245, 255] },
    columnStyles: { 0: { cellWidth: 12, halign: 'right' }, 1: { cellWidth: 30 }, 2: { cellWidth: 40 }, 3: { cellWidth: 22 }, 4: { cellWidth: 28 }, 5: { cellWidth: 26 }, 6: { cellWidth: 24 }, 7: { cellWidth: 24 }, 8: { cellWidth: 14 }, 9: { cellWidth: 26 }, 10: { cellWidth: 12 } },
    margin: { left: 14, right: 14 },
    didDrawPage: (data) => {
      const pageCount = doc.internal.getNumberOfPages();
      doc.setFontSize(7.5);
      doc.setTextColor(160, 160, 160);
      doc.text(`Page ${data.pageNumber} of ${pageCount}  •  AI SDR Agent`, 14, doc.internal.pageSize.height - 6);
    },
  });
  doc.save(`${filename}.pdf`);
}

// --------------------------------------------------------------------------
// Shared styles
// --------------------------------------------------------------------------
const cardStyle = {
  background: 'linear-gradient(135deg, hsl(var(--sfr-0f0a1f) / 0.95) 0%, hsl(var(--sfr-140828) / 0.95) 100%)',
  border: '1px solid var(--line-1)', borderRadius: 12,
};

const inputStyle = {
  background: 'hsl(var(--sfr-1e0a32) / 0.6)', border: '1px solid var(--line-1)',
  borderRadius: 8, padding: '8px 12px', color: 'var(--text-soft)',
  outline: 'none', fontSize: 14, width: '100%', boxSizing: 'border-box',
};

const pgBtn = (disabled, active = false) => ({
  minWidth: 32, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center',
  borderRadius: 7, fontSize: 13, fontWeight: active ? 700 : 400, cursor: disabled ? 'not-allowed' : 'pointer',
  border: `1px solid ${active ? '#a855f7' : 'rgba(255,255,255,0.08)'}`,
  background: active ? 'rgba(168,85,247,0.18)' : 'rgba(255,255,255,0.03)',
  color: disabled ? 'var(--line-1)' : active ? '#c084fc' : '#9ca3af',
  opacity: disabled ? 0.5 : 1, transition: 'all 0.15s', padding: '0 8px',
});

// --------------------------------------------------------------------------
// Filter Dropdown
// --------------------------------------------------------------------------
const FilterDropdown = ({ label, value, options, onChange, icon: LabelIcon, fullWidth }) => {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const selected = options.find(o => o.key === value) || options[0];

  return (
    <div ref={ref} style={{ position: 'relative', userSelect: 'none', width: fullWidth ? '100%' : 'auto' }}>
      <button
        onClick={() => setOpen(v => !v)}
        style={{
          display: 'flex', alignItems: 'center', gap: 7,
          padding: '7px 12px', borderRadius: 9, cursor: 'pointer',
          background: value ? `${selected?.color}15` : 'hsl(var(--surface-invert) / 0.04)',
          border: `1px solid ${value ? selected?.color + '60' : 'var(--line-1)'}`,
          color: value ? selected?.color : 'hsl(var(--pt-9ca3af))',
          fontSize: 13, fontWeight: value ? 600 : 400,
          transition: 'all 0.15s', whiteSpace: 'nowrap',
          minWidth: fullWidth ? 'auto' : 120, width: fullWidth ? '100%' : 'auto',
        }}
      >
        {LabelIcon && <LabelIcon size={13} style={{ color: value ? selected?.color : '#6b7280' }} />}
        {value && selected?.dot && <span style={{ width: 8, height: 8, borderRadius: '50%', background: selected.color, flexShrink: 0, display: 'inline-block' }} />}
        <span style={{ flex: 1, textAlign: 'left' }}>{value ? selected?.label : label}</span>
        <ChevronDown size={12} style={{ color: '#6b7280', transform: open ? 'rotate(180deg)' : 'none', transition: '0.15s', flexShrink: 0 }} />
      </button>

      {open && (
        <div style={{
          position: 'absolute', top: 'calc(100% + 6px)', left: 0, zIndex: 50,
          background: 'linear-gradient(135deg,var(--sfc-0f0a1f),var(--sfc-140830))',
          border: '1px solid var(--line-1)', borderRadius: 11,
          boxShadow: '0 12px 32px rgba(0,0,0,0.5)',
          minWidth: '100%', width: 'max-content', overflow: 'hidden',
        }}>
          {options.map((opt, idx) => {
            const isSel = opt.key === value;
            return (
              <button
                key={opt.key}
                onClick={() => { onChange(opt.key); setOpen(false); }}
                style={{
                  display: 'flex', alignItems: 'center', gap: 10,
                  width: '100%', padding: '9px 14px', border: 'none', cursor: 'pointer',
                  background: isSel ? `${opt.color}18` : 'transparent',
                  borderBottom: idx < options.length - 1 ? '1px solid hsl(var(--surface-invert) / 0.04)' : 'none',
                  transition: 'background 0.1s',
                }}
                onMouseEnter={e => { if (!isSel) e.currentTarget.style.background = 'rgba(255,255,255,0.05)'; }}
                onMouseLeave={e => { if (!isSel) e.currentTarget.style.background = 'transparent'; }}
              >
                <span style={{ width: 10, height: 10, borderRadius: '50%', flexShrink: 0, background: opt.key ? opt.color : 'transparent', border: opt.key ? `2px solid ${opt.color}` : '2px solid var(--line-1)' }} />
                {opt.Icon && <opt.Icon size={13} style={{ color: opt.color, flexShrink: 0 }} />}
                <span style={{ flex: 1, textAlign: 'left', fontSize: 13, color: isSel ? opt.color : opt.key ? 'hsl(var(--pt-d1d5db))' : '#6b7280', fontWeight: isSel ? 600 : 400 }}>{opt.label}</span>
                {isSel && <CheckCircle size={13} style={{ color: opt.color, flexShrink: 0 }} />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
};

// --------------------------------------------------------------------------
// Category picker — one of the user's industry categories, or a new one typed
// in. `value` is a category name ('' = none); the server makes a new name into
// a category on first use, so nothing here is a fixed list.
// --------------------------------------------------------------------------
const NEW_CATEGORY = '__new__';

const CategoryPicker = ({ categories, value, onChange, emptyLabel = 'No category' }) => {
  const match = categories.find(c => c.name.toLowerCase() === (value || '').trim().toLowerCase());
  const [typing, setTyping] = useState(!!value && !match);

  if (typing) {
    return (
      <div style={{ display: 'flex', gap: 6 }}>
        <input autoFocus value={value} maxLength={100} onChange={e => onChange(e.target.value)}
          placeholder="New category, e.g. Educational Institutes" style={inputStyle} />
        <button type="button" title="Pick from your categories" onClick={() => { setTyping(false); onChange(''); }}
          style={{ flexShrink: 0, display: 'flex', alignItems: 'center', padding: '0 10px', background: 'none', border: '1px solid var(--line-1)', borderRadius: 8, cursor: 'pointer', color: '#6b7280' }}>
          <X size={14} />
        </button>
      </div>
    );
  }
  return (
    <select value={match ? match.name : ''} style={{ ...inputStyle, cursor: 'pointer' }}
      onChange={e => {
        if (e.target.value === NEW_CATEGORY) { setTyping(true); onChange(''); } else onChange(e.target.value);
      }}>
      <option value="">{emptyLabel}</option>
      {categories.map(c => <option key={c.id} value={c.name}>{c.name}</option>)}
      <option value={NEW_CATEGORY}>+ Add new category…</option>
    </select>
  );
};

// The ICP new leads are scored with. '' = the default ICP (the server picks it), so the default needs no id here.
// Shown only with more than one ICP: with one there is nothing to choose.
const IcpPicker = ({ icps, value, onChange, label = 'Score these leads with' }) => {
  if (icps.length < 2) return null;
  const def = icps.find(i => i.is_active);
  return (
    <div>
      <label style={{ color: 'hsl(var(--pt-9ca3af))', fontSize: 12, display: 'block', marginBottom: 4 }}>{label}</label>
      <select value={value || ''} onChange={e => onChange(e.target.value)} style={{ ...inputStyle, cursor: 'pointer' }}>
        <option value="">{def ? `${def.name} (default ICP)` : 'Default ICP'}</option>
        {icps.filter(i => !i.is_active).map(i => <option key={i.id} value={String(i.id)}>{i.name}</option>)}
      </select>
    </div>
  );
};

// --------------------------------------------------------------------------
// Manage categories — rename (e.g. tidy a provider's "Hospital & Health Care")
// or delete one; a deleted category's leads stay, with no category.
// --------------------------------------------------------------------------
const CategoryManagerDialog = ({ open, onOpenChange, categories, onChanged }) => {
  const { toast } = useToast();
  const [editingId, setEditingId] = useState(null);
  const [draft, setDraft] = useState('');
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);
  const [busyId, setBusyId] = useState(null);

  useEffect(() => { if (!open) { setEditingId(null); setConfirmDeleteId(null); } }, [open]);

  const rename = async (cat) => {
    if (!draft.trim() || draft.trim() === cat.name) { setEditingId(null); return; }
    setBusyId(cat.id);
    try {
      await renameLeadCategory(cat.id, draft.trim());
      setEditingId(null);
      onChanged();
    } catch (e) {
      toast({ title: 'Could not rename', description: e?.message, variant: 'destructive' });
    } finally { setBusyId(null); }
  };

  const remove = async (cat) => {
    setBusyId(cat.id);
    try {
      await deleteLeadCategory(cat.id);
      setConfirmDeleteId(null);
      toast({ title: `Deleted "${cat.name}"`, description: 'Its leads are kept, with no category.' });
      onChanged();
    } catch (e) {
      toast({ title: 'Could not delete', description: e?.message, variant: 'destructive' });
    } finally { setBusyId(null); }
  };

  const iconBtn = { display: 'flex', alignItems: 'center', padding: 6, background: 'none', border: 'none', cursor: 'pointer' };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent style={{ background: 'linear-gradient(135deg,var(--sfc-0f0a1f) 0%,var(--sfc-14082a) 100%)', border: '1px solid var(--line-1)', color: 'var(--text-soft)', maxWidth: 520 }}>
        <DialogHeader>
          <DialogTitle style={{ color: 'var(--text-soft)', display: 'flex', alignItems: 'center', gap: 8 }}>
            <Tag size={18} color="#a855f7" /> Lead categories
          </DialogTitle>
        </DialogHeader>
        {categories.length === 0 ? (
          <p style={{ color: '#6b7280', fontSize: 13, padding: '8px 0' }}>
            No categories yet. They're made from the industry as leads come in, or when you pick "Add new category" anywhere.
          </p>
        ) : (
          <div style={{ border: '1px solid var(--line-1)', borderRadius: 10, maxHeight: '55vh', overflowY: 'auto' }}>
            {categories.map(cat => (
              <div key={cat.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', borderBottom: '1px solid hsl(var(--sfr-2d1f4a) / 0.5)' }}>
                {editingId === cat.id ? (
                  <input autoFocus value={draft} maxLength={100} onChange={e => setDraft(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter') rename(cat); if (e.key === 'Escape') setEditingId(null); }}
                    style={{ ...inputStyle, padding: '5px 10px', fontSize: 13 }} />
                ) : (
                  <span style={{ flex: 1, minWidth: 0, fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{cat.name}</span>
                )}
                <span style={{ color: '#6b7280', fontSize: 12, whiteSpace: 'nowrap' }}>{cat.lead_count ?? 0} leads</span>
                {busyId === cat.id ? <Loader2 size={14} className="animate-spin" style={{ color: '#6b7280', margin: 6 }} />
                  : editingId === cat.id ? (
                    <button title="Save" onClick={() => rename(cat)} style={{ ...iconBtn, color: 'hsl(var(--pt-4ade80))' }}><Check size={14} /></button>
                  ) : confirmDeleteId === cat.id ? (
                    <>
                      <button onClick={() => remove(cat)} style={{ ...iconBtn, color: '#f87171', fontSize: 12, fontWeight: 600 }}>Delete</button>
                      <button onClick={() => setConfirmDeleteId(null)} style={{ ...iconBtn, color: '#6b7280', fontSize: 12 }}>Keep</button>
                    </>
                  ) : (
                    <>
                      <button title="Rename" onClick={() => { setEditingId(cat.id); setDraft(cat.name); setConfirmDeleteId(null); }} style={{ ...iconBtn, color: '#9ca3af' }}><Pencil size={13} /></button>
                      <button title="Delete" onClick={() => { setConfirmDeleteId(cat.id); setEditingId(null); }} style={{ ...iconBtn, color: '#f87171' }}><Trash2 size={13} /></button>
                    </>
                  )}
              </div>
            ))}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
};

// --------------------------------------------------------------------------
// Export Dropdown
// --------------------------------------------------------------------------
const ExportDropdown = ({ leads, selectedLeads, allLeadsOnPage, totalCount = 0, exportParams = {} }) => {
  const [open, setOpen] = useState(false);
  const [exporting, setExporting] = useState(null);
  const ref = useRef(null);
  const { toast } = useToast();

  useEffect(() => {
    if (!open) return;
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const exportTarget = selectedLeads.size > 0 ? allLeadsOnPage.filter(l => selectedLeads.has(l.id)) : allLeadsOnPage;
  const label = selectedLeads.size > 0 ? `Export ${selectedLeads.size} selected` : `Export ${allLeadsOnPage.length} leads`;

  const doExport = async (format) => {
    setExporting(format);
    setOpen(false);
    try {
      const ts = new Date().toISOString().slice(0, 10);
      if (format === 'excel') await exportToExcel(exportTarget, `sdr-leads-${ts}`);
      else await exportToPdf(exportTarget, `sdr-leads-${ts}`);
      toast({ title: `Exported ${exportTarget.length} leads as ${format.toUpperCase()}` });
    } catch (e) {
      toast({ title: 'Export failed', description: e.message, variant: 'destructive' });
    } finally { setExporting(null); }
  };

  // Export EVERY lead matching the current filters (all pages), streamed as CSV
  // from the server — so 1000s of leads export in one download.
  const doExportAll = async () => {
    setExporting('all');
    setOpen(false);
    try {
      const blob = await exportAllLeadsCsv(exportParams);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `sdr-leads-all-${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      toast({ title: `Exported all ${totalCount ? totalCount.toLocaleString() + ' ' : ''}leads as CSV` });
    } catch (e) {
      toast({ title: 'Export failed', description: e?.response?.data?.message || e.message, variant: 'destructive' });
    } finally { setExporting(null); }
  };

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button
        onClick={() => setOpen(v => !v)}
        disabled={exportTarget.length === 0 || !!exporting}
        style={{
          display: 'flex', alignItems: 'center', gap: 7, padding: '7px 14px', borderRadius: 9,
          cursor: exportTarget.length === 0 ? 'not-allowed' : 'pointer',
          background: 'rgba(16,185,129,0.08)', border: '1px solid rgba(16,185,129,0.3)',
          color: '#10b981', fontSize: 13, fontWeight: 600, whiteSpace: 'nowrap',
          opacity: exportTarget.length === 0 ? 0.5 : 1, transition: 'all 0.15s',
        }}
      >
        {exporting ? <Loader2 size={13} style={{ animation: 'spin 1s linear infinite' }} /> : <Download size={13} />}
        {label}
        <ChevronDown size={11} style={{ color: '#6b7280', transform: open ? 'rotate(180deg)' : 'none', transition: '0.15s' }} />
      </button>
      {open && (
        <div style={{ position: 'absolute', top: 'calc(100% + 6px)', right: 0, zIndex: 60, background: 'linear-gradient(135deg,var(--sfc-0f0a1f),var(--sfc-140830))', border: '1px solid var(--line-1)', borderRadius: 11, boxShadow: '0 12px 32px rgba(0,0,0,0.5)', minWidth: 190, overflow: 'hidden' }}>
          {[
            { key: 'excel', Icon: FileSpreadsheet, label: 'Export as Excel (.xlsx)', color: '#10b981' },
            { key: 'pdf',   Icon: FileText,        label: 'Export as PDF',           color: '#f43f5e' },
          ].map((opt, idx) => (
            <button key={opt.key} onClick={() => doExport(opt.key)}
              style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%', padding: '11px 16px', border: 'none', cursor: 'pointer', background: 'transparent', borderBottom: idx === 0 ? '1px solid hsl(var(--surface-invert) / 0.04)' : 'none', transition: 'background 0.1s' }}
              onMouseEnter={e => { e.currentTarget.style.background = `${opt.color}12`; }}
              onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; }}
            >
              <opt.Icon size={15} style={{ color: opt.color, flexShrink: 0 }} />
              <span style={{ color: 'hsl(var(--pt-d1d5db))', fontSize: 13 }}>{opt.label}</span>
            </button>
          ))}
          {/* Export ALL matching leads (every page) as CSV, streamed from the server. */}
          <button onClick={doExportAll}
            style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%', padding: '11px 16px', border: 'none', borderTop: '1px solid hsl(var(--surface-invert) / 0.08)', cursor: 'pointer', background: 'rgba(168,85,247,0.06)', transition: 'background 0.1s' }}
            onMouseEnter={e => { e.currentTarget.style.background = 'rgba(168,85,247,0.14)'; }}
            onMouseLeave={e => { e.currentTarget.style.background = 'rgba(168,85,247,0.06)'; }}
          >
            <Download size={15} style={{ color: '#a855f7', flexShrink: 0 }} />
            <span style={{ color: 'hsl(var(--pt-d1d5db))', fontSize: 13 }}>
              Export ALL{totalCount ? ` ${totalCount.toLocaleString()}` : ''} leads (CSV)
            </span>
          </button>
        </div>
      )}
    </div>
  );
};

// --------------------------------------------------------------------------
// Debounce hook
// --------------------------------------------------------------------------
function useDebounce(value, delay = 400) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

const PAGE_SIZE_OPTIONS = [10, 25, 50, 100];

// --------------------------------------------------------------------------
// ICP Profile Panel
// --------------------------------------------------------------------------
const BLANK_ICP = { name: 'Default ICP', industries: '', job_titles: '', locations: '', keywords: '', company_size_min: '', company_size_max: '' };

// Several ICPs. Each lead is scored with the ICP it was found for, so one ICP's leads can still be waiting to be
// scored while leads are found for another. The default ICP is preselected in Generate / Import / Add lead.
const ICPProfilePanel = ({ icps, onChanged, onSaved }) => {
  const { toast } = useToast();
  const [open, setOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);   // null: the list; 'new': a new ICP; a number: that ICP
  const [form, setForm] = useState(BLANK_ICP);
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);

  const defaultIcp = icps.find(i => i.is_active) || null;

  const startEdit = (icp) => {
    setConfirmDeleteId(null);
    if (!icp) {
      setEditingId('new');
      setForm({ ...BLANK_ICP, name: icps.length ? '' : 'Default ICP' });
    } else {
      setEditingId(icp.id);
      setForm({ name: icp.name || '', industries: (icp.industries || []).join(', '), job_titles: (icp.job_titles || []).join(', '), locations: (icp.locations || []).join(', '), keywords: (icp.keywords || []).join(', '), company_size_min: icp.company_size_min || '', company_size_max: icp.company_size_max || '' });
    }
    setOpen(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const toArr = v => v.split(',').map(s => s.trim()).filter(Boolean);
      const payload = { name: form.name, industries: toArr(form.industries), job_titles: toArr(form.job_titles), locations: toArr(form.locations), keywords: toArr(form.keywords), company_size_min: form.company_size_min ? parseInt(form.company_size_min) : null, company_size_max: form.company_size_max ? parseInt(form.company_size_max) : null };
      const isNew = editingId === 'new';
      const res = isNew ? await createIcpProfile(payload) : await updateIcpProfile(editingId, payload);
      const saved = res?.data?.data || res?.data || null;
      toast({ title: 'ICP saved' });
      setEditingId(null);
      await onChanged?.();
      // A new ICP goes straight on to finding leads for it.
      if (isNew) { setOpen(false); onSaved?.(saved?.id); }
    } catch (e) { toast({ title: 'Save failed', description: e.message, variant: 'destructive' }); }
    finally { setSaving(false); }
  };

  const makeDefault = async (icp) => {
    setBusyId(icp.id);
    try {
      await setDefaultIcpProfile(icp.id);
      toast({ title: `"${icp.name}" is now your default ICP`, description: 'Leads already found for another ICP keep being scored with theirs.' });
      await onChanged?.();
    } catch (e) { toast({ title: 'Could not change the default', description: e?.message, variant: 'destructive' }); }
    finally { setBusyId(null); }
  };

  const remove = async (icp) => {
    setBusyId(icp.id);
    try {
      await deleteIcpProfile(icp.id);
      setConfirmDeleteId(null);
      toast({ title: `Deleted "${icp.name}"`, description: 'Its scored leads keep their scores.' });
      await onChanged?.();
    } catch (e) {
      // The server says why: the default ICP, or leads still being scored with it.
      toast({ title: 'Could not delete', description: e?.message, variant: 'destructive' });
      setConfirmDeleteId(null);
    } finally { setBusyId(null); }
  };

  const iconBtn = { display: 'flex', alignItems: 'center', gap: 4, padding: '4px 6px', background: 'none', border: 'none', cursor: 'pointer', fontSize: 12 };
  const smallBtn = { background: 'rgba(168,85,247,0.1)', border: '1px solid rgba(168,85,247,0.3)', borderRadius: 8, padding: '5px 12px', color: '#a855f7', cursor: 'pointer', fontSize: 13, display: 'flex', alignItems: 'center', gap: 5 };

  return (
    <div style={{ ...cardStyle, padding: '14px 18px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
          <Brain size={16} color="#a855f7" />
          <span style={{ color: 'var(--text-soft)', fontWeight: 600, fontSize: 14 }}>ICP Profiles</span>
          {defaultIcp ? (
            <span title="Your default ICP" style={{ color: '#10b981', fontSize: 12, padding: '2px 8px', borderRadius: 10, background: 'rgba(16,185,129,0.1)', border: '1px solid rgba(16,185,129,0.2)' }}>{defaultIcp.name}</span>
          ) : (
            <span style={{ color: 'hsl(var(--pt-f59e0b))', fontSize: 12 }}>Not configured — scoring won't work without this</span>
          )}
          {icps.length > 1 && <span style={{ color: '#6b7280', fontSize: 12 }}>+{icps.length - 1} more</span>}
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          {icps.length > 0 && (
            <button onClick={() => startEdit(null)} style={smallBtn}><Plus size={13} /> New ICP</button>
          )}
          <button onClick={() => (icps.length ? (setOpen(!open), setEditingId(null)) : startEdit(null))} style={smallBtn}>
            <ChevronDown size={13} style={{ transform: open ? 'rotate(180deg)' : 'none', transition: '0.2s' }} />
            {icps.length ? 'Manage' : 'Setup'}
          </button>
        </div>
      </div>

      {defaultIcp && !open && (
        <div style={{ marginTop: 10, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {[...(defaultIcp.industries || []), ...(defaultIcp.job_titles || [])].slice(0, 6).map(t => (
            <span key={t} style={{ padding: '2px 8px', borderRadius: 10, fontSize: 11, background: 'rgba(168,85,247,0.1)', border: '1px solid rgba(168,85,247,0.2)', color: 'hsl(var(--pt-c4b5fd))' }}>{t}</span>
          ))}
        </div>
      )}

      {open && editingId === null && icps.length > 0 && (
        <div style={{ marginTop: 12, border: '1px solid var(--line-1)', borderRadius: 10 }}>
          {icps.map(icp => (
            <div key={icp.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', borderBottom: '1px solid hsl(var(--sfr-2d1f4a) / 0.5)', flexWrap: 'wrap' }}>
              <span style={{ flex: 1, minWidth: 120, fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={[...(icp.industries || []), ...(icp.job_titles || [])].join(', ')}>
                {icp.name}
              </span>
              {icp.is_active && (
                <span style={{ color: '#10b981', fontSize: 11, padding: '1px 8px', borderRadius: 10, background: 'rgba(16,185,129,0.1)', border: '1px solid rgba(16,185,129,0.2)' }}>Default</span>
              )}
              {icp.waiting > 0 && (
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, color: '#60a5fa', fontSize: 11 }}>
                  <Loader2 size={11} className="animate-spin" /> {icp.waiting.toLocaleString()} being scored
                </span>
              )}
              <span style={{ color: '#6b7280', fontSize: 12, whiteSpace: 'nowrap' }}>{(icp.lead_count ?? 0).toLocaleString()} leads</span>
              {busyId === icp.id ? <Loader2 size={14} className="animate-spin" style={{ color: '#6b7280', margin: 6 }} />
                : confirmDeleteId === icp.id ? (
                  <>
                    <button onClick={() => remove(icp)} style={{ ...iconBtn, color: '#f87171', fontWeight: 600 }}>Delete</button>
                    <button onClick={() => setConfirmDeleteId(null)} style={{ ...iconBtn, color: '#6b7280' }}>Keep</button>
                  </>
                ) : (
                  <>
                    {!icp.is_active && (
                      <button title="Preselect this ICP in Generate, Import and Add lead" onClick={() => makeDefault(icp)} style={{ ...iconBtn, color: '#a855f7' }}>Make default</button>
                    )}
                    <button title="Edit" onClick={() => startEdit(icp)} style={{ ...iconBtn, color: '#9ca3af' }}><Pencil size={13} /></button>
                    {!icp.is_active && (
                      <button title="Delete" onClick={() => setConfirmDeleteId(icp.id)} style={{ ...iconBtn, color: '#f87171' }}><Trash2 size={13} /></button>
                    )}
                  </>
                )}
            </div>
          ))}
        </div>
      )}

      {open && editingId !== null && (
        <div style={{ marginTop: 14, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ color: 'hsl(var(--pt-9ca3af))', fontSize: 12 }}>
            {editingId === 'new'
              ? 'A new ICP. Leads you find or import for it are scored with it, whatever else you change meanwhile.'
              : 'Leads of this ICP still waiting to be scored use your changes; scored leads keep their scores.'}
          </div>
          {[
            { k: 'name',       l: 'Profile Name',          p: 'e.g. Dentistry' },
            { k: 'industries', l: 'Target Industries (comma-separated)', p: 'SaaS, FinTech, E-commerce' },
            { k: 'job_titles', l: 'Target Job Titles (comma-separated)', p: 'CEO, VP Sales, Head of Growth' },
            { k: 'locations',  l: 'Target Locations (comma-separated)',  p: 'United States, United Kingdom' },
            { k: 'keywords',   l: 'Keywords (comma-separated)',          p: 'B2B, startup, Series A, automation' },
          ].map(({ k, l, p }) => (
            <div key={k}>
              <label style={{ color: 'hsl(var(--pt-9ca3af))', fontSize: 12, display: 'block', marginBottom: 4 }}>{l}</label>
              <input style={inputStyle} placeholder={p} value={form[k]} onChange={e => setForm(f => ({ ...f, [k]: e.target.value }))} />
            </div>
          ))}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            {[{ k: 'company_size_min', l: 'Min Employees', p: '10' }, { k: 'company_size_max', l: 'Max Employees', p: '500' }].map(({ k, l, p }) => (
              <div key={k}>
                <label style={{ color: 'hsl(var(--pt-9ca3af))', fontSize: 12, display: 'block', marginBottom: 4 }}>{l}</label>
                <input style={inputStyle} type="number" placeholder={p} value={form[k]} onChange={e => setForm(f => ({ ...f, [k]: e.target.value }))} />
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button onClick={() => { setEditingId(null); if (!icps.length) setOpen(false); }} style={{ background: 'none', border: '1px solid var(--line-1)', borderRadius: 8, padding: '7px 16px', color: 'hsl(var(--pt-9ca3af))', cursor: 'pointer', fontSize: 13 }}>Cancel</button>
            <button onClick={handleSave} disabled={saving} style={{ background: 'linear-gradient(90deg,hsl(var(--brand-600)),#a855f7)', border: 'none', borderRadius: 8, padding: '7px 20px', color: '#fff', cursor: 'pointer', fontSize: 13, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}>
              {saving ? <Loader2 size={12} className="animate-spin" /> : null} Save ICP
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

// --------------------------------------------------------------------------
// Score Breakdown Bar
// --------------------------------------------------------------------------
const ScoreBar = ({ label, value, max, color, icon: Icon }) => {
  const pct = max > 0 ? (value / max) * 100 : 0;
  const barColor = pct >= 70 ? color : pct >= 40 ? '#f59e0b' : '#4b5563';
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          {Icon && <Icon size={11} style={{ color }} />}
          <span style={{ fontSize: 12, color: 'hsl(var(--pt-9ca3af))' }}>{label}</span>
        </div>
        <span style={{ fontSize: 12, color: 'var(--text-soft)', fontWeight: 600 }}>{value}/{max}</span>
      </div>
      <div style={{ height: 5, borderRadius: 3, background: 'hsl(var(--surface-invert) / 0.06)' }}>
        <div style={{ height: '100%', borderRadius: 3, width: `${pct}%`, background: barColor, transition: 'width 0.4s ease' }} />
      </div>
    </div>
  );
};

// --------------------------------------------------------------------------
// Confidence badge
// --------------------------------------------------------------------------
const ConfidenceBadge = ({ score }) => {
  if (score == null) return null;
  const color = score >= 75 ? '#10b981' : score >= 50 ? '#f59e0b' : '#f43f5e';
  const icon = score >= 75 ? ShieldCheck : ShieldAlert;
  const Icon = icon;
  const label = score >= 75 ? 'High' : score >= 50 ? 'Medium' : 'Low';
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 3,
      padding: '2px 7px', borderRadius: 8, fontSize: 11,
      background: `${color}14`, border: `1px solid ${color}40`, color, whiteSpace: 'nowrap',
    }}>
      <Icon size={10} /> {label} quality
    </span>
  );
};

// Shimmer placeholder rows shown while leads load — conveys the table shape
// (and that data is coming) better than a bare spinner.
const LeadTableSkeleton = ({ rows = 8 }) => (
  <div style={{ padding: '8px 0' }}>
    <style>{`@keyframes sdrShimmer{0%{opacity:.45}50%{opacity:.9}100%{opacity:.45}}`}</style>
    {Array.from({ length: rows }).map((_, i) => (
      <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 16, padding: '14px 16px', borderBottom: '1px solid var(--sfc-160b2e)' }}>
        <div style={{ width: 16, height: 16, borderRadius: 4, background: 'var(--sfc-241638)', animation: 'sdrShimmer 1.4s ease-in-out infinite', animationDelay: `${i * 0.06}s` }} />
        <div style={{ flex: 2, display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div style={{ width: '55%', height: 11, borderRadius: 4, background: 'var(--sfc-241638)', animation: 'sdrShimmer 1.4s ease-in-out infinite', animationDelay: `${i * 0.06}s` }} />
          <div style={{ width: '35%', height: 9, borderRadius: 4, background: 'var(--sfc-1c1030)', animation: 'sdrShimmer 1.4s ease-in-out infinite', animationDelay: `${i * 0.06 + 0.1}s` }} />
        </div>
        <div style={{ flex: 1, height: 10, borderRadius: 4, background: 'var(--sfc-1c1030)', animation: 'sdrShimmer 1.4s ease-in-out infinite', animationDelay: `${i * 0.06}s` }} />
        <div style={{ width: 60, height: 20, borderRadius: 10, background: 'var(--sfc-241638)', animation: 'sdrShimmer 1.4s ease-in-out infinite', animationDelay: `${i * 0.06}s` }} />
        <div style={{ width: 70, height: 10, borderRadius: 4, background: 'var(--sfc-1c1030)', animation: 'sdrShimmer 1.4s ease-in-out infinite', animationDelay: `${i * 0.06}s` }} />
      </div>
    ))}
  </div>
);

// --------------------------------------------------------------------------
// Main Component
// --------------------------------------------------------------------------
const SDRLeadsTab = () => {
  const { toast } = useToast();
  const navigate = useNavigate();
  const fileInputRef = useRef(null);

  const [sdrKeyStatus, setSdrKeyStatus] = useState({ apollo: false, apify: false, loaded: false });
  const hasSource = sdrKeyStatus.loaded && (sdrKeyStatus.apollo || sdrKeyStatus.apify);
  useEffect(() => {
    getSdrSettings().then((res) => {
      const d = res?.data || res || {};
      setSdrKeyStatus({ apollo: !!d.apollo_api_key_set, apify: !!d.apify_api_token_set, loaded: true });
    }).catch(() => setSdrKeyStatus({ apollo: false, apify: false, loaded: true }));
  }, []);
  // CSV import preview modal state.
  const [csvImport, setCsvImport] = useState(null); // { file, rows, columns, skippedEmpty } | null
  const [csvImporting, setCsvImporting] = useState(false);
  const [leads, setLeads] = useState([]);
  const [stats, setStats] = useState({ total: 0, hot: 0, warm: 0, cold: 0, unscored: 0, qualifying: 0, unqueued: 0, enriching: 0 });
  const [pagination, setPagination] = useState({ page: 1, page_size: 25, total_count: 0, total_pages: 1, has_next: false, has_prev: false });

  const [loading, setLoading] = useState(true);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);
  const [selectedLead, setSelectedLead] = useState(null);
  const [newLead, setNewLead] = useState(BLANK_LEAD);
  const [addingLead, setAddingLead] = useState(false);
  const [qualifyingId, setQualifyingId] = useState(null);
  const [researchingId, setResearchingId] = useState(null);
  const [enrichingId, setEnrichingId] = useState(null);

  const [searchRaw, setSearchRaw] = useState('');
  const [filterTemp, setFilterTemp] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [filterSource, setFilterSource] = useState('');
  const [filterCategory, setFilterCategory] = useState('');   // '' all, 'none', or a category id
  const [filterEnrichment, setFilterEnrichment] = useState(''); // '' all, done, not, in_progress, failed
  const [filterIcp, setFilterIcp] = useState('');               // '' all, 'none', or an ICP id
  const [sortBy, setSortBy] = useState('score_desc');
  // The ICP a lead added by hand / an imported file is scored with ('' = the default ICP).
  const [newLeadIcpId, setNewLeadIcpId] = useState('');
  const [csvIcpId, setCsvIcpId] = useState('');

  // Industry categories (made from the data as leads come in, or typed in by hand).
  const [categories, setCategories] = useState([]);
  const [uncategorizedCount, setUncategorizedCount] = useState(0);
  const [newLeadCategory, setNewLeadCategory] = useState('');
  const [csvCategory, setCsvCategory] = useState('');
  const [genCategory, setGenCategory] = useState('');
  const [bulkCategory, setBulkCategory] = useState('');
  const [bulkCategorySaving, setBulkCategorySaving] = useState(false);
  const [allMatching, setAllMatching] = useState(false);   // the bulk action covers every lead the filters match
  const [detailCategory, setDetailCategory] = useState('');
  const [showCategoryManager, setShowCategoryManager] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

  const search = useDebounce(searchRaw, 450);

  const [selectedIds, setSelectedIds] = useState(new Set());
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [showBulkDeleteConfirm, setShowBulkDeleteConfirm] = useState(false);
  // Single-lead delete confirmation: holds the lead pending deletion (or null).
  const [pendingDeleteLead, setPendingDeleteLead] = useState(null);
  const [deletingSingle, setDeletingSingle] = useState(false);

  const [showGenModal, setShowGenModal] = useState(false);
  const [genSource, setGenSource] = useState('apollo');
  const [genCount, setGenCount] = useState(10);
  const [genIcpId, setGenIcpId] = useState('');
  const [icpProfiles, setIcpProfiles] = useState([]);
  const [generating, setGenerating] = useState(false);
  const [genProgress, setGenProgress] = useState(null); // { created, total } while a run is in flight
  const [copiedKey, setCopiedKey] = useState(null);
  const [showSetupGuide, setShowSetupGuide] = useState(null);

  // ── Load ──────────────────────────────────────────────────────────────
  // Each load is numbered; a reply that a newer load has overtaken is dropped, so a slow
  // background refresh can't put back the page a filter change just replaced.
  const loadSeq = useRef(0);
  // opts.quiet: the background refresh. The table stays on screen and updates in place,
  // ticked rows stay ticked and a failed refresh says nothing (the next one tries again).
  const loadLeads = useCallback(async (opts = {}) => {
    const { quiet = false } = opts;
    const seq = ++loadSeq.current;
    if (!quiet) setLoading(true);
    try {
      const resp = await listLeads({
        search:      opts.search      ?? search,
        temperature: opts.temperature ?? filterTemp,
        status:      opts.status      ?? filterStatus,
        source:      opts.source      ?? filterSource,
        category:    opts.category    ?? filterCategory,
        enrichment:  opts.enrichment  ?? filterEnrichment,
        icp:         opts.icp         ?? filterIcp,
        sort:       opts.sort        ?? sortBy,
        page:        opts.page        ?? page,
        page_size:   opts.page_size   ?? pageSize,
      });
      if (seq !== loadSeq.current) return;
      setLeads(resp?.data || []);
      setStats(resp?.stats || { total: 0, hot: 0, warm: 0, cold: 0, unscored: 0, qualifying: 0, unqueued: 0, enriching: 0 });
      setPagination(resp?.pagination || { page: 1, page_size: pageSize, total_count: 0, total_pages: 1, has_next: false, has_prev: false });
      if (quiet) {
        // Keep the ticks on rows still on the page.
        const onPage = new Set((resp?.data || []).map(l => l.id));
        setSelectedIds(prev => (prev.size ? new Set([...prev].filter(id => onPage.has(id))) : prev));
      } else {
        setSelectedIds(new Set());
        setAllMatching(false);
      }
      if (resp?.data) {
        setSelectedLead(prev => {
          if (!prev?.id) return prev;
          const fresh = resp.data.find(l => l.id === prev.id);
          return fresh ? { ...prev, ...fresh } : prev;
        });
      }
    } catch (e) {
      if (!quiet && seq === loadSeq.current) {
        toast({ title: 'Failed to load leads', description: e?.message, variant: 'destructive' });
      }
    } finally {
      // The latest load ends the spinner, quiet or not: a refresh that overtook a full load must not leave it on.
      if (seq === loadSeq.current) setLoading(false);
    }
  }, [search, filterTemp, filterStatus, filterSource, filterCategory, filterEnrichment, filterIcp, sortBy, page, pageSize, toast]);

  const loadCategories = useCallback(async () => {
    try {
      const resp = await listLeadCategories();
      setCategories(resp?.data || []);
      setUncategorizedCount(resp?.uncategorized || 0);
    } catch (_) { /* the pickers just show no categories */ }
  }, []);

  // The login's ICPs, for the ICP panel, the filter and the ICP pickers in Generate / Import / Add lead.
  const loadIcps = useCallback(async () => { setIcpProfiles(await listIcpProfiles()); }, []);

  useEffect(() => { loadLeads(); loadCategories(); loadIcps(); }, []);

  // While leads are being qualified or enriched in the background, poll every
  // 12s so scores and enriched fields appear on their own. Stops once both
  // queues drain. Quietly: the list must not blink every 12s.
  useEffect(() => {
    if (!stats.qualifying && !stats.enriching) return undefined;
    const id = setInterval(() => { loadLeads({ quiet: true }); if (stats.qualifying) loadIcps(); }, 12000);
    return () => clearInterval(id);
  }, [stats.qualifying, stats.enriching, loadLeads, loadIcps]);

  useEffect(() => {
    setPage(1);
    loadLeads({ page: 1, search, temperature: filterTemp, status: filterStatus, source: filterSource, category: filterCategory, enrichment: filterEnrichment, icp: filterIcp, sort: sortBy, page_size: pageSize });
  }, [search, filterTemp, filterStatus, filterSource, filterCategory, filterEnrichment, filterIcp, sortBy, pageSize]);

  const goToPage = useCallback((p) => { setPage(p); loadLeads({ page: p }); }, [loadLeads]);

  // The Filters panel's count; the category and ICP filters sit outside the panel.
  const activeFiltersCount = [filterTemp, filterStatus, filterSource, filterEnrichment].filter(Boolean).length;
  const anyFilter = activeFiltersCount > 0 || !!filterCategory || !!filterIcp;
  const clearAllFilters = () => { setFilterTemp(''); setFilterStatus(''); setFilterSource(''); setFilterCategory(''); setFilterEnrichment(''); setFilterIcp(''); };
  // The list's current filters, for actions that cover every matching lead (bulk category, Export ALL).
  const currentFilters = { search, temperature: filterTemp, status: filterStatus, source: filterSource, category: filterCategory, enrichment: filterEnrichment, icp: filterIcp };

  // After a change that can add categories or move leads between them.
  const refreshAfterCategoryChange = () => { loadLeads(); loadCategories(); };

  const handleBulkSetCategory = async () => {
    setBulkCategorySaving(true);
    try {
      const resp = await bulkSetLeadCategory({
        category: bulkCategory.trim() || null,
        ...(allMatching ? { filters: currentFilters } : { ids: [...selectedIds] }),
      });
      toast({ title: resp?.message || 'Category updated' });
      setBulkCategory('');
      refreshAfterCategoryChange();
    } catch (e) {
      toast({ title: 'Could not change the category', description: e?.message, variant: 'destructive' });
    } finally { setBulkCategorySaving(false); }
  };

  // Filtering by a category that was just deleted would show an empty list: go back to all.
  useEffect(() => {
    if (filterCategory && filterCategory !== 'none' && !categories.some(c => String(c.id) === filterCategory)) {
      setFilterCategory('');
    }
  }, [categories]);
  // Likewise for a deleted ICP.
  useEffect(() => {
    if (filterIcp && filterIcp !== 'none' && !icpProfiles.some(i => String(i.id) === filterIcp)) setFilterIcp('');
  }, [icpProfiles]);

  // A closed import dialog forgets its category, so the next file starts on Automatic.
  useEffect(() => { if (!csvImport) setCsvCategory(''); }, [csvImport]);

  // The detail panel's picker follows whichever lead is open.
  useEffect(() => { setDetailCategory(selectedLead?.category || ''); }, [selectedLead?.id, selectedLead?.category]);

  const handleSaveDetailCategory = async () => {
    if (!selectedLead) return;
    try {
      const resp = await updateLead(selectedLead.id, { category: detailCategory.trim() || null });
      const updated = resp?.data;
      if (updated) setSelectedLead(prev => ({ ...prev, ...updated }));
      toast({ title: updated?.category ? `Moved to "${updated.category}"` : 'Category removed' });
      refreshAfterCategoryChange();
    } catch (e) {
      toast({ title: 'Could not change the category', description: e?.message, variant: 'destructive' });
    }
  };
  const allPageIds = leads.map(l => l.id);
  const allSelected = allPageIds.length > 0 && allPageIds.every(id => selectedIds.has(id));
  const someSelected = allPageIds.some(id => selectedIds.has(id)) && !allSelected;

  const toggleSelectAll = () => {
    setAllMatching(false);
    if (allSelected) {
      setSelectedIds(prev => { const n = new Set(prev); allPageIds.forEach(id => n.delete(id)); return n; });
    } else {
      setSelectedIds(prev => { const n = new Set(prev); allPageIds.forEach(id => n.add(id)); return n; });
    }
  };

  const toggleSelect = (id) => {
    setAllMatching(false);
    setSelectedIds(prev => { const n = new Set(prev); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  };

  // Show a toast with an Undo action that restores the just-deleted lead(s).
  const showUndoToast = (ids, label) => {
    const undo = async () => {
      try {
        if (ids.length === 1) await restoreLead(ids[0]);
        else await bulkRestoreLeads(ids);
        toast({ title: 'Restored', description: `${label} restored.` });
        loadLeads();
      } catch (e) {
        toast({ title: 'Restore failed', description: e.message, variant: 'destructive' });
      }
    };
    toast({
      title: `${label} deleted`,
      description: 'You can undo this.',
      action: (
        <ToastAction altText="Undo delete" onClick={undo}>
          Undo
        </ToastAction>
      ),
    });
  };

  const handleBulkDelete = async () => {
    setBulkDeleting(true);
    try {
      const ids = [...selectedIds];
      const resp = await bulkDeleteLeads(ids);
      const restoreIds = resp?.deleted_ids?.length ? resp.deleted_ids : ids;
      setShowBulkDeleteConfirm(false);
      setSelectedIds(new Set());
      loadLeads();
      showUndoToast(restoreIds, `${resp?.deleted ?? ids.length} lead(s)`);
    } catch (e) {
      toast({ title: 'Bulk delete failed', description: e.message, variant: 'destructive' });
    } finally { setBulkDeleting(false); }
  };

  // preferIcpId: an ICP just made, to find leads for it; else the default ICP is preselected.
  const openGenModal = async (preferIcpId) => {
    try {
      const [profiles, settingsRes] = await Promise.allSettled([listIcpProfiles(), getSdrSettings()]);
      if (profiles.status === 'fulfilled') {
        const p = profiles.value;
        setIcpProfiles(p);
        const preferred = typeof preferIcpId === 'number' && p.some(x => x.id === preferIcpId) ? preferIcpId : null;
        if (p.length > 0) setGenIcpId(preferred || p.find(x => x.is_active)?.id || p[0].id);
      } else { setIcpProfiles([]); }
      if (settingsRes.status === 'fulfilled') {
        const d = settingsRes.value?.data || settingsRes.value;
        setSdrKeyStatus({ apollo: !!d.apollo_api_key_set, apify: !!d.apify_api_token_set, loaded: true });
      } else {
        setSdrKeyStatus({ apollo: false, apify: false, loaded: true });
      }
    } catch (_) { setIcpProfiles([]); }
    setShowGenModal(true);
  };

  const handleGenerate = async () => {
    setGenerating(true);
    setGenProgress({ created: 0, total: genCount });
    const apifyApprovalToast = (url) => toast({
      title: 'Approve the Apify actor first',
      description: 'This actor needs a one-time permission approval on Apify. Approve it, then try again.',
      variant: 'destructive',
      action: (
        <ToastAction altText="Open Apify" onClick={() => window.open(url, '_blank', 'noopener,noreferrer')}>
          Open Apify
        </ToastAction>
      ),
    });
    try {
      // Kick off the background job; the backend returns a job id immediately.
      const startResp = await researchLeads({
        count: genCount, source: genSource, icp_id: genIcpId || undefined, category: genCategory.trim() || undefined,
      });
      const started = startResp?.data ?? startResp;
      const jobId = started?.job_id;
      if (!jobId) {
        throw Object.assign(new Error(started?.message || 'Could not start generation.'), { data: started });
      }

      // Poll the job until it finishes (large Apify/Apollo runs can take minutes).
      const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
      let job = null;
      for (let i = 0; i < 400; i++) { // ~20 min ceiling at 3s/poll
        await sleep(3000);
        let jobResp;
        try { jobResp = await getResearchJob(jobId); } catch (_) { continue; }
        job = (jobResp?.data ?? jobResp)?.job;
        if (!job) continue;
        setGenProgress({ created: job.leads_created || 0, total: genCount });
        if (job.done) break;
      }

      if (!job || !job.done) {
        toast({
          title: 'Still generating…',
          description: 'This run is taking a while. It keeps going in the background — refresh the list shortly.',
        });
        setShowGenModal(false);
        setPage(1);
        loadLeads({ page: 1 });
        return;
      }

      if (job.state === 'failed') {
        if (job.error_code === 'apify_approval_required' && job.approval_url) {
          apifyApprovalToast(job.approval_url);
        } else {
          toast({ title: 'Generate failed', description: job.error_message || 'Lead generation failed.', variant: 'destructive' });
        }
        return;
      }

      const created = job.leads_created || 0;
      const skipped = job.skipped_duplicates || 0;
      toast({
        title: created ? `${created} leads generated!` : 'No new leads found',
        description: [
          `Source: ${(job.source || genSource).toUpperCase()}`,
          skipped ? `${skipped} duplicates skipped.` : '',
          job.leads_queued ? `Qualifying ${job.leads_queued} in the background.` : '',
        ].filter(Boolean).join(' '),
      });
      setShowGenModal(false);
      setGenCategory('');
      setPage(1);
      loadLeads({ page: 1 });
      loadCategories();
    } catch (e) {
      const data = e?.data || e?.response?.data;
      if (data?.code === 'apify_approval_required') {
        apifyApprovalToast(data.approval_url);
      } else {
        toast({ title: 'Generate failed', description: data?.message || e.message, variant: 'destructive' });
      }
    } finally {
      setGenerating(false);
      setGenProgress(null);
    }
  };

  // Import leads already generated in the Apify Console (works on the free plan,
  // which can't RUN paid actors via API but CAN read finished runs).
  const [fetchingApify, setFetchingApify] = useState(false);
  const handleFetchApify = async () => {
    setFetchingApify(true);
    try {
      const resp = await fetchApifyLeads({ count: 200, category: genCategory.trim() || undefined });
      const created = resp?.data?.leads_created ?? resp?.leads_created ?? 0;
      const skipped = resp?.data?.skipped_duplicates ?? resp?.skipped_duplicates ?? 0;
      toast({
        title: created ? `Imported ${created} leads from Apify` : 'No new leads found',
        description: skipped ? `${skipped} duplicates skipped.` : (resp?.message || resp?.data?.message || ''),
      });
      setShowGenModal(false);
      setGenCategory('');
      setPage(1);
      loadLeads({ page: 1 });
      loadCategories();
    } catch (e) {
      toast({ title: 'Fetch failed', description: e?.response?.data?.message || e.message, variant: 'destructive' });
    } finally { setFetchingApify(false); }
  };

  // Ask for confirmation before deleting a single lead (was a one-click delete).
  const requestDelete = (lead) => setPendingDeleteLead(lead);

  const confirmDelete = async () => {
    const lead = pendingDeleteLead;
    if (!lead) return;
    setDeletingSingle(true);
    try {
      await deleteLead(lead.id);
      if (selectedLead?.id === lead.id) setSelectedLead(null);
      setSelectedIds(prev => { const n = new Set(prev); n.delete(lead.id); return n; });
      setPendingDeleteLead(null);
      loadLeads();
      showUndoToast([lead.id], lead.display_name || lead.full_name || 'Lead');
    } catch (e) {
      toast({ title: 'Delete failed', description: e.message, variant: 'destructive' });
    } finally { setDeletingSingle(false); }
  };

  const handleEnrichOne = async (lead) => {
    if (!lead?.id) return;
    setEnrichingId(lead.id);
    try {
      const resp = await enrichLead(lead.id, { force: true });
      const data = resp?.data || resp;
      // The backend returns the updated-field list at the top level as
      // `fields_updated` (and as the keys of `changes`). It is NOT on the
      // contract object, so reading data.contract.fields_updated was always
      // empty → every enrichment showed "No New Data" even when it added data.
      const updatedFields = data?.fields_updated || Object.keys(data?.changes || {});
      if (updatedFields.length > 0) {
        toast({
          title: 'Enrichment Complete',
          description: `Successfully added ${updatedFields.join(', ')} for ${lead.full_name || lead.email || 'lead'}.`,
        });
      } else {
        toast({
          title: 'Enrichment Finished (No New Data)',
          description: `No additional contact details found on public website or providers for ${lead.full_name || lead.email || 'lead'}.`,
        });
      }
      if (selectedLead?.id === lead.id) {
        setSelectedLead(prev => ({
          ...prev,
          email: data?.contract?.fields?.email?.value || prev.email,
          phone: data?.contract?.fields?.phone?.value || prev.phone,
          job_title: data?.contract?.fields?.job_title?.value || prev.job_title,
          company_domain: data?.contract?.fields?.company_domain?.value || prev.company_domain,
          company_website: data?.contract?.fields?.company_website?.value || prev.company_website,
          linkedin_url: data?.contract?.fields?.linkedin_url?.value || prev.linkedin_url,
          enrichment_status: data.enrichment_status || 'completed',
          enrichment_contract: data.contract,
        }));
      }
      loadLeads();
    } catch (e) {
      toast({
        title: 'Enrichment Failed',
        description: e?.response?.data?.message || 'Could not complete enrichment waterfall.',
        variant: 'destructive',
      });
    } finally {
      setEnrichingId(null);
    }
  };

  const handleResearchOne = async (lead) => {
    if (!lead) return;
    setResearchingId(lead.id);
    try {
      const startResp = await researchLead(lead.id, { force: true, async: true });
      const started = startResp?.data || startResp;

      // R1: research now runs in the background (it can take ~47 s). Poll the GET
      // side of the endpoint for research_status until it finishes.
      let data = started;
      if (started?.status === 'queued') {
        const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
        const TERMINAL = ['completed', 'partial', 'failed'];
        data = null;
        for (let i = 0; i < 60; i++) {          // ~3 min at 3s/poll
          await sleep(3000);
          let pollResp;
          try { pollResp = await getLeadResearch(lead.id); } catch (_) { continue; }
          const p = pollResp?.data || pollResp;
          if (TERMINAL.includes(p?.research_status)) { data = p; break; }
        }
        if (!data) {
          toast({ title: 'Still researching…', description: 'Taking a while — it keeps running in the background; refresh shortly.' });
          loadLeads();
          return;
        }
      }

      if (data?.research_status === 'failed') {
        toast({ title: 'Research failed', description: 'Could not complete research for this lead.', variant: 'destructive' });
        return;
      }

      toast({
        title: 'Research Complete',
        description: `Intelligence gathered for ${lead.company_name || lead.full_name || 'lead'}`,
      });
      if (selectedLead?.id === lead.id) {
        const pStatus = data?.research_profile?.verification?.prospect?.status;
        setSelectedLead(prev => ({
          ...prev,
          data_quality_flags: pStatus === 'verified'
            ? (prev.data_quality_flags || []).filter(f => !f.startsWith('Research:'))
            : (prev.data_quality_flags || []),
          research_status: data.research_status || 'completed',
          research_profile: data.research_profile,
        }));
      }
      loadLeads();
    } catch (e) {
      toast({
        title: 'Research failed',
        description: e?.response?.data?.message || e.message || 'Could not complete research',
        variant: 'destructive',
      });
    } finally {
      setResearchingId(null);
    }
  };

  const handleQualifyOne = async (lead) => {
    setQualifyingId(lead.id);
    try {
      const resp = await qualifyLead(lead.id);
      setLeads(prev => prev.map(l => l.id === lead.id ? resp.data : l));
      if (selectedLead?.id === lead.id) setSelectedLead(resp.data);
      const cat = getScoreCategory(resp.data.score);
      toast({ title: `Score: ${resp.data.score}/100 — ${cat?.label || ''}`, description: lead.full_name });
    } catch (e) {
      toast({ title: 'Score failed', description: e.message, variant: 'destructive' });
    } finally { setQualifyingId(null); }
  };

  // Qualify all currently-unscored leads (e.g. ones auto-qualify skipped when
  // AI tokens ran out). Backend batches up to 50 per call.
  const [qualifyingAll, setQualifyingAll] = useState(false);
  const handleQualifyAll = async () => {
    setQualifyingAll(true);
    try {
      const resp = await qualifyAllLeads();
      const n = resp?.queued ?? resp?.data?.queued ?? 0;
      toast({ title: `Queued ${n} lead${n === 1 ? '' : 's'} for qualification`, description: resp?.message });
      loadLeads();
    } catch (e) {
      toast({ title: 'Qualify failed', description: e?.message, variant: 'destructive' });
    } finally { setQualifyingAll(false); }
  };

  const handleAddLead = async () => {
    // ── Validation ──────────────────────────────────────────────────────────
    // A lead needs at least a name or an email to be useful, and any email /
    // LinkedIn URL provided must be well-formed (previously anything was saved).
    const name = `${newLead.first_name || ''} ${newLead.last_name || ''}`.trim();
    const email = (newLead.email || '').trim();
    const linkedin = (newLead.linkedin_url || '').trim();

    if (!name && !email) {
      toast({ title: 'Missing details', description: 'Enter at least a name or a business email.', variant: 'destructive' });
      return;
    }
    if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      toast({ title: 'Invalid email', description: 'Enter a valid business email like jane@company.com.', variant: 'destructive' });
      return;
    }
    if (linkedin) {
      let ok = false;
      try {
        const u = new URL(/^https?:\/\//i.test(linkedin) ? linkedin : `https://${linkedin}`);
        ok = /(^|\.)linkedin\.com$/i.test(u.hostname);
      } catch { ok = false; }
      if (!ok) {
        toast({ title: 'Invalid LinkedIn URL', description: 'Enter a valid LinkedIn URL like https://linkedin.com/in/jane.', variant: 'destructive' });
        return;
      }
    }
    if (newLead.company_size && !/^\d+$/.test(String(newLead.company_size).trim())) {
      toast({ title: 'Invalid employees', description: 'Employees must be a whole number.', variant: 'destructive' });
      return;
    }

    setAddingLead(true);
    try {
      await createLead({
        ...newLead,
        company_size: newLead.company_size ? parseInt(newLead.company_size) : null,
        category: newLeadCategory.trim() || null,   // none picked → the Industry typed in decides
        ...(newLeadIcpId ? { icp_id: newLeadIcpId } : {}),   // none picked → the default ICP
      });
      setShowAddModal(false);
      setNewLead(BLANK_LEAD);
      setNewLeadCategory('');
      setNewLeadIcpId('');
      toast({ title: 'Lead added' });
      setPage(1);
      loadLeads({ page: 1 });
      loadCategories();
    } catch (e) {
      toast({ title: 'Add failed', description: e.message, variant: 'destructive' });
    } finally { setAddingLead(false); }
  };

  // File chosen → parse client-side and open the preview modal (don't import yet).
  const handleCsvImport = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    try {
      const text = await file.text();
      const parsed = parseCsvPreview(text);
      if (!parsed.rows.length) {
        toast({ title: 'Nothing to import', description: 'The file has a header row but no data rows with a name / email / company.', variant: 'destructive' });
        return;
      }
      setCsvImport({ file, ...parsed });
    } catch (err) {
      toast({ title: 'Could not read file', description: err?.message || 'Make sure it is a valid CSV.', variant: 'destructive' });
    }
  };

  // Download a ready-to-fill CSV template with the expected header row.
  const downloadCsvTemplate = () => {
    const csv = 'Full Name,Email,Job Title,Company,Industry,Employees,Location,Phone,LinkedIn URL\n'
      + 'Jane Doe,jane@acme.com,VP Sales,Acme Corp,SaaS,150,"San Francisco, CA",,https://linkedin.com/in/jane\n';
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'leads-template.csv';
    a.click();
    URL.revokeObjectURL(url);
  };

  // Confirm in the modal → actually send the file to the backend (robust parser).
  const handleCsvConfirm = async () => {
    if (!csvImport?.file) return;
    setCsvImporting(true);
    try {
      const resp = await importLeadsFromCSV(csvImport.file, csvCategory.trim(), csvIcpId);
      // Refused rows are listed with their reasons: 5 seconds was too short to read them (AI SDR film, 30 Oct).
      toast({ title: `Imported ${resp.created} leads`, description: resp.message,
        ...(resp.refused?.length ? { duration: 15000 } : {}) });
      setCsvImport(null);
      setCsvCategory('');
      setCsvIcpId('');
      setPage(1);
      loadLeads({ page: 1 });
      loadCategories();
    } catch (err) {
      toast({ title: 'Import failed', description: err?.message, variant: 'destructive' });
    } finally { setCsvImporting(false); }
  };

  const CheckIcon = ({ checked, indeterminate, size = 16 }) => {
    if (indeterminate) return <MinusSquare size={size} style={{ color: '#a855f7' }} />;
    if (checked) return <CheckSquare size={size} style={{ color: '#a855f7' }} />;
    return <Square size={size} style={{ color: '#4b5563' }} />;
  };

  // ── Render ────────────────────────────────────────────────────────────
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <style>{`@keyframes spin{from{transform:rotate(0)}to{transform:rotate(360deg)}}`}</style>

      {/* With no Apollo or Apify key, saving the profile opened a lead search that could not run. */}
      <ICPProfilePanel icps={icpProfiles} onChanged={loadIcps} onSaved={(icpId) => (hasSource ? openGenModal(icpId) : toast({
        title: 'ICP saved', description: 'Now bring in your leads with Import CSV, or add a lead by hand.' }))} />

      {/* Stats row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12 }}>
        {[
          { label: 'Total',    value: stats.total,    color: '#a855f7' },
          { label: 'Hot',      value: stats.hot,      color: '#f43f5e', icon: Flame },
          { label: 'Warm',     value: stats.warm,     color: '#f59e0b', icon: Thermometer },
          { label: 'Cold',     value: stats.cold,     color: '#60a5fa', icon: Snowflake },
          { label: 'Unscored', value: stats.unscored, color: '#6b7280' },
        ].map(({ label, value, color, icon: Icon }) => (
          <div key={label} style={{ ...cardStyle, padding: '14px 16px', textAlign: 'center' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5, marginBottom: 4 }}>
              {Icon && <Icon size={13} style={{ color }} />}
              <span style={{ color: 'hsl(var(--pt-9ca3af))', fontSize: 12 }}>{label}</span>
            </div>
            <span style={{ color, fontSize: 26, fontWeight: 700 }}>{value}</span>
          </div>
        ))}
      </div>

      {/* Action bar */}
      <div style={{ ...cardStyle, padding: '14px 18px' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
          <Button onClick={() => setShowAddModal(true)} style={{ background: 'linear-gradient(90deg,#f43f5e 0%,#a855f7 100%)', color: '#fff', border: 'none', borderRadius: 8, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6, padding: '8px 16px' }}>
            <Plus size={15} /> Add Lead
          </Button>
          <div style={{ width: 1, height: 28, background: 'var(--line-1)' }} />
          <Button onClick={() => openGenModal()} style={{ background: 'linear-gradient(90deg,hsl(var(--brand-600)) 0%,#a855f7 100%)', color: '#fff', border: 'none', borderRadius: 8, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6, padding: '8px 16px' }}>
            <Zap size={15} /> Generate Leads
          </Button>
          <div style={{ width: 1, height: 28, background: 'var(--line-1)' }} />
          <Button onClick={() => setCsvImport({})} variant="outline" style={{ border: '1px solid var(--line-1)', color: 'hsl(var(--pt-9ca3af))', borderRadius: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
            <Upload size={14} /> Import CSV
          </Button>
          <input ref={fileInputRef} type="file" accept=".csv" style={{ display: 'none' }} onChange={handleCsvImport} />
          {/* Only for unscored leads the queue won't reach on its own (never queued, or failed for good);
              queued leads are already covered by the "Qualifying…" status below. */}
          {stats.unqueued > 0 && (
            <Button onClick={handleQualifyAll} disabled={qualifyingAll} title={`${stats.unqueued} unscored lead${stats.unqueued === 1 ? ' is' : 's are'} not in the qualification queue (never queued, or qualification failed). Add ${stats.unqueued === 1 ? 'it' : 'them'} to the queue.`} style={{ background: 'rgba(245,158,11,0.14)', border: '1px solid rgba(245,158,11,0.4)', color: 'hsl(var(--pt-fbbf24))', borderRadius: 8, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6, padding: '8px 14px' }}>
              {qualifyingAll ? <Loader2 size={15} className="animate-spin" /> : <Brain size={15} />}
              Qualify {stats.unqueued} more
            </Button>
          )}
          <div style={{ marginLeft: 'auto' }}>
            <ExportDropdown leads={leads} selectedLeads={selectedIds} allLeadsOnPage={leads}
              totalCount={pagination.total_count}
              exportParams={{ ...currentFilters, sort: sortBy }} />
          </div>
        </div>
        {/* Background work in progress. A line of its own: as buttons in the row above, "Qualifying" and
            "Enriching" pushed Export onto a second line on the live site. */}
        {(stats.qualifying > 0 || stats.enriching > 0) && (
          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8, marginTop: 10, paddingTop: 10, borderTop: '1px solid hsl(var(--surface-invert) / 0.05)' }}>
            {stats.qualifying > 0 && (
              <span title="Leads are being qualified in the background." style={{ display: 'inline-flex', alignItems: 'center', gap: 5, background: 'rgba(96,165,250,0.1)', border: '1px solid rgba(96,165,250,0.3)', color: '#60a5fa', borderRadius: 20, fontWeight: 600, fontSize: 12, padding: '3px 10px' }}>
                <Loader2 size={12} className="animate-spin" /> Qualifying {stats.qualifying.toLocaleString()}…
              </span>
            )}
            {stats.enriching > 0 && (
              <span title="Leads are being enriched in the background — missing fields (phone, email, LinkedIn…) will appear on their own." style={{ display: 'inline-flex', alignItems: 'center', gap: 5, background: 'rgba(168,85,247,0.1)', border: '1px solid rgba(168,85,247,0.3)', color: 'hsl(var(--pt-c084fc))', borderRadius: 20, fontWeight: 600, fontSize: 12, padding: '3px 10px' }}>
                <Loader2 size={12} className="animate-spin" /> Enriching {stats.enriching.toLocaleString()}…
              </span>
            )}
            <span style={{ color: '#6b7280', fontSize: 12 }}>Runs in the background; scores and details fill in on their own.</span>
          </div>
        )}
      </div>

      {/* Bulk action bar */}
      {selectedIds.size > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', padding: '12px 18px', borderRadius: 12, background: 'linear-gradient(90deg, rgba(168,85,247,0.08), rgba(99,102,241,0.08))', border: '1px solid rgba(168,85,247,0.3)' }}>
          <span style={{ color: 'hsl(var(--pt-c084fc))', fontWeight: 700, fontSize: 14 }}>
            {allMatching
              ? `All ${pagination.total_count.toLocaleString()} matching leads selected`
              : `${selectedIds.size} lead${selectedIds.size > 1 ? 's' : ''} selected`}
          </span>
          {/* Every lead on the page ticked, with more pages: offer the whole filtered list (for filing a big import at once). */}
          {!allMatching && allSelected && pagination.total_count > leads.length && (
            <button onClick={() => setAllMatching(true)} style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', color: '#60a5fa', fontSize: 13, textDecoration: 'underline' }}>
              Select all {pagination.total_count.toLocaleString()} matching leads
            </button>
          )}
          <div style={{ width: 1, height: 20, background: 'var(--line-1)' }} />
          {/* File the selection under a category (pick one, type a new one, or "No category" to clear). */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <Tag size={13} style={{ color: '#a78bfa', flexShrink: 0 }} />
            <div style={{ width: 220 }}>
              <CategoryPicker categories={categories} value={bulkCategory} onChange={setBulkCategory} emptyLabel="No category (clear)" />
            </div>
            <button onClick={handleBulkSetCategory} disabled={bulkCategorySaving} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 14px', borderRadius: 8, cursor: 'pointer', background: 'rgba(167,139,250,0.12)', border: '1px solid rgba(167,139,250,0.35)', color: 'hsl(var(--pt-a78bfa))', fontSize: 13, fontWeight: 600, whiteSpace: 'nowrap' }}>
              {bulkCategorySaving ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />} Set category
            </button>
          </div>
          {/* Delete works on ticked leads only, never on "all matching". */}
          {!allMatching && (
            <button onClick={() => setShowBulkDeleteConfirm(true)} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 14px', borderRadius: 8, cursor: 'pointer', background: 'rgba(244,63,94,0.1)', border: '1px solid rgba(244,63,94,0.3)', color: '#f87171', fontSize: 13, fontWeight: 600 }}>
              <Trash2 size={13} /> Delete {selectedIds.size} selected
            </button>
          )}
          <button onClick={() => { setSelectedIds(new Set()); setAllMatching(false); }} style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '6px 12px', borderRadius: 8, cursor: 'pointer', background: 'none', border: '1px solid var(--line-1)', color: '#6b7280', fontSize: 13 }}>
            <X size={12} /> Deselect all
          </button>
        </div>
      )}

      {/* Filter bar */}
      <div style={{ ...cardStyle, padding: '12px 16px' }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <div style={{ position: 'relative', flex: '1 1 200px', minWidth: 180 }}>
            <Search size={14} style={{ position: 'absolute', left: 11, top: '50%', transform: 'translateY(-50%)', color: '#6b7280', pointerEvents: 'none' }} />
            <input value={searchRaw} onChange={e => setSearchRaw(e.target.value)} placeholder="Search name, company, email…"
              style={{ ...inputStyle, paddingLeft: 34, paddingRight: searchRaw ? 32 : 12, border: '1px solid var(--line-1)', borderRadius: 9, fontSize: 13 }} />
            {searchRaw && (
              <button onClick={() => setSearchRaw('')} style={{ position: 'absolute', right: 9, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: '#6b7280', display: 'flex', padding: 0 }}>
                <X size={13} />
              </button>
            )}
          </div>
          {/* Which ICP the leads were found for (and are scored with). */}
          {icpProfiles.length > 1 && (
            <FilterDropdown label="All ICPs" value={filterIcp} onChange={setFilterIcp} icon={Target}
              options={[
                { key: '', label: 'All ICPs', color: '#6b7280' },
                ...icpProfiles.map(i => ({ key: String(i.id), label: `${i.name} (${(i.lead_count ?? 0).toLocaleString()})`, color: '#a78bfa' })),
                { key: 'none', label: 'No ICP (older leads)', color: '#9ca3af' },
              ]} />
          )}
          {/* Industry category: the main way to keep one industry's leads apart from another's. */}
          <FilterDropdown label="All categories" value={filterCategory} onChange={setFilterCategory} icon={Tag}
            options={[
              { key: '', label: 'All categories', color: '#6b7280' },
              ...categories.map(c => ({ key: String(c.id), label: `${c.name} (${c.lead_count ?? 0})`, color: '#a78bfa' })),
              { key: 'none', label: `No category (${uncategorizedCount})`, color: '#9ca3af' },
            ]}
          />
          <button onClick={() => setShowCategoryManager(true)} title="Rename or delete categories"
            style={{ display: 'flex', alignItems: 'center', padding: '7px 10px', background: 'none', border: '1px solid var(--line-1)', borderRadius: 9, cursor: 'pointer', color: '#6b7280' }}>
            <Pencil size={13} />
          </button>
          {(() => {
            const totalActive = activeFiltersCount + (sortBy !== 'score_desc' ? 1 : 0);
            return (
              <button onClick={() => setFiltersOpen(v => !v)} style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '7px 14px', borderRadius: 9, cursor: 'pointer', whiteSpace: 'nowrap', background: filtersOpen || totalActive > 0 ? 'rgba(168,85,247,0.12)' : 'hsl(var(--surface-invert) / 0.04)', border: `1px solid ${filtersOpen || totalActive > 0 ? 'rgba(168,85,247,0.5)' : 'var(--line-1)'}`, color: filtersOpen || totalActive > 0 ? 'hsl(var(--pt-c084fc))' : '#9ca3af', fontSize: 13, fontWeight: totalActive > 0 ? 600 : 400 }}>
                <SlidersHorizontal size={13} />
                Filters
                {totalActive > 0 && <span style={{ background: 'linear-gradient(135deg,#a855f7,#6366f1)', color: '#fff', borderRadius: '50%', width: 18, height: 18, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, fontWeight: 700 }}>{totalActive}</span>}
                <ChevronDown size={11} style={{ color: '#6b7280', transform: filtersOpen ? 'rotate(180deg)' : 'none', transition: '0.15s' }} />
              </button>
            );
          })()}
          <select value={pageSize} onChange={e => setPageSize(Number(e.target.value))} style={{ ...inputStyle, width: 'auto', padding: '7px 10px', fontSize: 13, border: '1px solid var(--line-1)', borderRadius: 9, cursor: 'pointer' }}>
            {PAGE_SIZE_OPTIONS.map(n => <option key={n} value={n}>{n} / page</option>)}
          </select>
          <button onClick={() => loadLeads()} style={{ display: 'flex', alignItems: 'center', padding: '7px 10px', background: 'none', border: '1px solid var(--line-1)', borderRadius: 9, cursor: 'pointer', color: '#6b7280' }}>
            <RefreshCw size={14} style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }} />
          </button>
        </div>

        {filtersOpen && (
          <div style={{ marginTop: 10, padding: '16px 16px 14px', background: 'linear-gradient(135deg,hsl(var(--sfr-0a041c) / 0.9),hsl(var(--sfr-100626) / 0.95))', border: '1px solid rgba(168,85,247,0.2)', borderRadius: 11, boxShadow: 'inset 0 1px 0 rgba(168,85,247,0.06)' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12 }}>
              <div>
                <div style={{ color: '#6b7280', fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', marginBottom: 7, display: 'flex', alignItems: 'center', gap: 5 }}>
                  <Thermometer size={11} style={{ color: 'hsl(var(--pt-f59e0b))' }} /> TEMPERATURE
                </div>
                <FilterDropdown fullWidth label="All Temperatures" value={filterTemp} onChange={setFilterTemp}
                  options={[
                    { key: '',     label: 'All Temperatures', color: '#6b7280' },
                    { key: 'hot',  label: 'Hot',  color: '#f43f5e', dot: true, Icon: Flame },
                    { key: 'warm', label: 'Warm', color: '#f59e0b', dot: true, Icon: Thermometer },
                    { key: 'cold', label: 'Cold', color: '#60a5fa', dot: true, Icon: Snowflake },
                  ]}
                />
              </div>
              <div>
                <div style={{ color: '#6b7280', fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', marginBottom: 7, display: 'flex', alignItems: 'center', gap: 5 }}>
                  <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#a78bfa', display: 'inline-block' }} /> STATUS
                </div>
                <FilterDropdown fullWidth label="All Statuses" value={filterStatus} onChange={setFilterStatus}
                  options={[
                    { key: '',                  label: 'All Statuses',      color: '#6b7280' },
                    { key: 'new',               label: 'New',               color: '#6b7280', dot: true },
                    { key: 'qualified',         label: 'Qualified',         color: '#60a5fa', dot: true },
                    { key: 'contacted',         label: 'Contacted',         color: '#a78bfa', dot: true },
                    { key: 'replied',           label: 'Replied',           color: '#4ade80', dot: true },
                    { key: 'meeting_scheduled', label: 'Meeting Scheduled', color: '#34d399', dot: true },
                    { key: 'converted',         label: 'Converted',         color: '#fbbf24', dot: true },
                    { key: 'disqualified',      label: 'Disqualified',      color: '#f87171', dot: true },
                  ]}
                />
              </div>
              <div>
                <div style={{ color: '#6b7280', fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', marginBottom: 7, display: 'flex', alignItems: 'center', gap: 5 }}>
                  <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#10b981', display: 'inline-block' }} /> SOURCE
                </div>
                <FilterDropdown fullWidth label="All Sources" value={filterSource} onChange={setFilterSource}
                  options={[
                    { key: '',           label: 'All Sources', color: '#6b7280' },
                    { key: 'apollo',     label: 'Apollo.io',   color: '#3b82f6', dot: true },
                    { key: 'apify',      label: 'Apify',       color: '#a855f7', dot: true },
                    { key: 'csv_import', label: 'CSV Import',  color: '#10b981', dot: true },
                    { key: 'manual',     label: 'Manual',      color: '#6b7280', dot: true },
                  ]}
                />
              </div>
              <div>
                <div style={{ color: '#6b7280', fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', marginBottom: 7, display: 'flex', alignItems: 'center', gap: 5 }}>
                  <Sparkles size={11} style={{ color: 'hsl(var(--pt-a78bfa))' }} /> ENRICHMENT
                </div>
                <FilterDropdown fullWidth label="All Enrichment" value={filterEnrichment} onChange={setFilterEnrichment}
                  options={[
                    { key: '',            label: 'All Enrichment', color: '#6b7280' },
                    { key: 'done',        label: 'Enriched',       color: '#34d399', dot: true },
                    { key: 'not',         label: 'Not enriched',   color: '#6b7280', dot: true },
                    { key: 'in_progress', label: 'Enriching',      color: '#60a5fa', dot: true },
                    { key: 'failed',      label: 'Enrichment failed', color: '#f87171', dot: true },
                  ]}
                />
              </div>
              <div>
                <div style={{ color: '#6b7280', fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', marginBottom: 7, display: 'flex', alignItems: 'center', gap: 5 }}>
                  <ArrowUpDown size={11} style={{ color: 'hsl(var(--pt-a78bfa))' }} /> SORT BY
                </div>
                <FilterDropdown fullWidth label="Sort by" value={sortBy} onChange={setSortBy} icon={ArrowUpDown}
                  options={[
                    { key: 'score_desc',   label: 'Score: High → Low', color: '#a78bfa' },
                    { key: 'score_asc',    label: 'Score: Low → High', color: '#a78bfa' },
                    { key: 'created_desc', label: 'Newest First',      color: '#60a5fa' },
                    { key: 'created_asc',  label: 'Oldest First',      color: '#60a5fa' },
                    { key: 'name_asc',     label: 'Name A → Z',        color: '#4ade80' },
                    { key: 'company_asc',  label: 'Company A → Z',     color: '#4ade80' },
                  ]}
                />
              </div>
            </div>
            {(() => {
              const totalActive = activeFiltersCount + (sortBy !== 'score_desc' ? 1 : 0);
              return totalActive > 0 ? (
                <div style={{ marginTop: 12, paddingTop: 10, borderTop: '1px solid hsl(var(--surface-invert) / 0.05)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <button onClick={() => { setFilterTemp(''); setFilterStatus(''); setFilterSource(''); setSortBy('score_desc'); }}
                    style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '5px 12px', borderRadius: 8, background: 'rgba(244,63,94,0.08)', border: '1px solid rgba(244,63,94,0.25)', color: '#f87171', fontSize: 12, cursor: 'pointer' }}>
                    <X size={11} /> Clear all
                  </button>
                  <span style={{ color: '#6b7280', fontSize: 12 }}>{totalActive} active</span>
                </div>
              ) : null;
            })()}
          </div>
        )}

        <div style={{ marginTop: 8, fontSize: 12, color: '#4b5563', display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          {loading
            ? <span style={{ color: 'hsl(var(--pt-a78bfa))' }}>Loading…</span>
            : <>
                <span>Showing <strong style={{ color: 'var(--text-soft)' }}>{pagination.total_count === 0 ? 0 : ((pagination.page - 1) * pagination.page_size) + 1}–{Math.min(pagination.page * pagination.page_size, pagination.total_count)}</strong> of <strong style={{ color: 'var(--text-soft)' }}>{pagination.total_count.toLocaleString()}</strong> leads</span>
                {(searchRaw || anyFilter) && <span style={{ padding: '1px 8px', borderRadius: 10, background: 'rgba(167,139,250,0.12)', border: '1px solid rgba(167,139,250,0.25)', color: 'hsl(var(--pt-a78bfa))', fontSize: 11 }}>filtered</span>}
                {/* Key to the dot beside each name. */}
                <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                  {[['#34d399', 'Enriched'], ['#60a5fa', 'Enriching'], ['#f87171', 'Enrichment failed']].map(([color, label]) => (
                    <span key={label} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, whiteSpace: 'nowrap' }}>
                      <span style={{ width: 7, height: 7, borderRadius: '50%', background: color }} /> {label}
                    </span>
                  ))}
                  <span style={{ whiteSpace: 'nowrap' }}>No dot = not enriched</span>
                </span>
              </>
          }
        </div>
      </div>

      {/* Lead table. Scrolls sideways on a narrow screen: with overflow hidden the Actions column was cut off. */}
      <div style={{ ...cardStyle, overflowX: 'auto' }}>
        {loading ? (
          <LeadTableSkeleton />
        ) : leads.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '56px 24px' }}>
            <div style={{ width: 64, height: 64, borderRadius: 16, margin: '0 auto 16px', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(168,85,247,0.08)', border: '1px solid rgba(168,85,247,0.2)' }}>
              <Users size={30} style={{ color: '#a855f7' }} />
            </div>
            <p style={{ color: 'var(--text-soft)', fontWeight: 600, marginBottom: 6, fontSize: 15 }}>
              {(search || anyFilter) ? 'No leads match your filters' : 'No leads yet'}
            </p>
            <p style={{ color: '#6b7280', fontSize: 13, marginBottom: 20, maxWidth: 360, marginLeft: 'auto', marginRight: 'auto', lineHeight: 1.6 }}>
              {(search || anyFilter)
                ? 'Try clearing your search or filters to see more leads.'
                : hasSource
                  ? 'Generate leads from Apollo.io / Apify, import a CSV, or add one manually to get started.'
                  : 'Import a CSV of your leads, or add one by hand. Lead search needs an Apollo.io or Apify key in Settings.'}
            </p>
            {(search || anyFilter) ? (
              <Button onClick={() => { setSearchRaw(''); clearAllFilters(); }} variant="outline" style={{ border: '1px solid var(--line-1)', color: 'hsl(var(--pt-9ca3af))', borderRadius: 8 }}>
                Clear filters
              </Button>
            ) : (
              <div style={{ display: 'flex', gap: 10, justifyContent: 'center', flexWrap: 'wrap' }}>
                {hasSource && (
                <Button onClick={() => openGenModal()} style={{ background: 'linear-gradient(90deg,hsl(var(--brand-600)) 0%,#a855f7 100%)', color: '#fff', border: 'none', borderRadius: 8, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Zap size={15} /> Generate Leads
                </Button>
                )}
                <Button onClick={() => setCsvImport({})} variant="outline" style={{ border: '1px solid var(--line-1)', color: 'hsl(var(--pt-9ca3af))', borderRadius: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Upload size={15} /> Import CSV
                </Button>
                <Button onClick={() => setShowAddModal(true)} variant="outline" style={{ border: '1px solid var(--line-1)', color: 'hsl(var(--pt-9ca3af))', borderRadius: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Plus size={15} /> Add Lead
                </Button>
              </div>
            )}
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--sfc-1e0f38)' }}>
                <th style={{ padding: '12px 14px', width: 40 }}>
                  <button onClick={toggleSelectAll} style={{ background: 'none', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', padding: 0 }}>
                    <CheckIcon checked={allSelected} indeterminate={someSelected} />
                  </button>
                </th>
                {['Lead', 'Title', 'Score', 'Category', 'Status', 'Quality', 'Source', 'Actions'].map(h => (
                  <th key={h} style={{ padding: '12px 16px', textAlign: 'left', color: '#4b5563', fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {leads.map(lead => {
                const tcfg = TEMP_CONFIG[lead.temperature];
                const TIcon = tcfg?.icon;
                const cat = getScoreCategory(lead.score);
                const isChecked = selectedIds.has(lead.id);
                const hasFlags = (lead.data_quality_flags || []).length > 0;
                const confScore = lead.confidence_score;
                return (
                  <tr key={lead.id}
                    style={{ borderBottom: '1px solid hsl(var(--sfr-2d1f4a) / 0.4)', cursor: 'pointer', transition: 'background 0.15s', background: isChecked ? 'rgba(168,85,247,0.06)' : 'transparent' }}
                    onMouseEnter={e => { if (!isChecked) e.currentTarget.style.background = 'rgba(168,85,247,0.04)'; }}
                    onMouseLeave={e => { e.currentTarget.style.background = isChecked ? 'rgba(168,85,247,0.06)' : 'transparent'; }}
                  >
                    <td style={{ padding: '13px 14px' }} onClick={e => { e.stopPropagation(); toggleSelect(lead.id); }}>
                      <button style={{ background: 'none', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', padding: 0 }}>
                        <CheckIcon checked={isChecked} />
                      </button>
                    </td>
                    <td style={{ padding: '13px 16px' }} onClick={() => setSelectedLead(lead)}>
                      <div style={{ fontWeight: 600, color: 'var(--text-soft)', fontSize: 14, display: 'flex', alignItems: 'center', gap: 6, whiteSpace: 'nowrap' }}>
                        {lead.full_name}
                        {/* Enrichment at a glance: the same colours as the Enrichment filter. */}
                        {ENRICHMENT_DOT[lead.enrichment_status] && (
                          <span title={ENRICHMENT_DOT[lead.enrichment_status].title}
                            style={{ width: 7, height: 7, borderRadius: '50%', flexShrink: 0, background: ENRICHMENT_DOT[lead.enrichment_status].color }} />
                        )}
                      </div>
                      {lead.category && (
                        <span title={`Show only "${lead.category}" leads`}
                          onClick={e => { e.stopPropagation(); setFilterCategory(String(lead.category_id)); }}
                          style={{ display: 'inline-flex', alignItems: 'center', gap: 4, marginTop: 4, marginRight: 4, padding: '2px 7px', borderRadius: 8, fontSize: 10, fontWeight: 600, background: 'rgba(167,139,250,0.1)', border: '1px solid rgba(167,139,250,0.3)', color: 'hsl(var(--pt-a78bfa))', whiteSpace: 'nowrap', cursor: 'pointer' }}>
                          <Tag size={9} /> {lead.category}
                        </span>
                      )}
                    </td>
                    <td style={{ padding: '13px 16px', minWidth: 200 }} onClick={() => setSelectedLead(lead)}>
                      <span style={{ color: 'hsl(var(--pt-9ca3af))', fontSize: 13 }}>{lead.job_title || '—'}</span>
                    </td>
                    <td style={{ padding: '13px 16px' }} onClick={() => setSelectedLead(lead)}>
                      {lead.score != null ? (
                        <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 40, height: 40, borderRadius: '50%', background: `${SCORE_COLOR(lead.score)}18`, border: `2px solid ${SCORE_COLOR(lead.score)}55`, color: SCORE_COLOR(lead.score), fontWeight: 700, fontSize: 14 }}>
                          {lead.score}
                        </span>
                      ) : <span style={{ color: 'var(--line-1)', fontSize: 12 }}>—</span>}
                    </td>
                    <td style={{ padding: '13px 16px' }} onClick={() => setSelectedLead(lead)}>
                      {cat ? (
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '3px 9px', borderRadius: 10, fontSize: 11, fontWeight: 600, background: cat.bg, border: `1px solid ${cat.border}`, color: cat.color, whiteSpace: 'nowrap' }}>
                          {cat.label}
                        </span>
                      ) : tcfg ? (
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '3px 10px', borderRadius: 12, fontSize: 12, fontWeight: 600, background: tcfg.bg, border: `1px solid ${tcfg.border}`, color: tcfg.color, whiteSpace: 'nowrap' }}>
                          <TIcon size={11} /> {tcfg.label}
                        </span>
                      ) : (lead.qualification_status === 'pending' || lead.qualification_status === 'processing') ? (
                        <span title="Queued for AI qualification — score will appear shortly." style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '3px 9px', borderRadius: 10, fontSize: 11, fontWeight: 600, background: 'rgba(96,165,250,0.1)', border: '1px solid rgba(96,165,250,0.3)', color: '#60a5fa', whiteSpace: 'nowrap' }}>
                          <Loader2 size={10} className="animate-spin" /> Qualifying…
                        </span>
                      ) : (
                        <span title="This lead hasn't been AI-qualified yet — click the ✦ Qualify button to score it." style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '3px 9px', borderRadius: 10, fontSize: 11, fontWeight: 600, background: 'rgba(245,158,11,0.1)', border: '1px solid rgba(245,158,11,0.3)', color: 'hsl(var(--pt-f59e0b))', whiteSpace: 'nowrap' }}>
                          <AlertTriangle size={10} /> Not qualified
                        </span>
                      )}
                    </td>
                    <td style={{ padding: '13px 16px' }} onClick={() => setSelectedLead(lead)}>
                      {(() => {
                        const sc = LEAD_STATUS_CONFIG[lead.status];
                        return sc ? <span style={{ padding: '3px 9px', borderRadius: 10, fontSize: 11, fontWeight: 600, background: sc.bg, border: `1px solid ${sc.border}`, color: sc.color, whiteSpace: 'nowrap' }}>{sc.label}</span> : <span style={{ color: '#4b5563', fontSize: 12 }}>—</span>;
                      })()}
                    </td>
                    <td style={{ padding: '13px 16px' }} onClick={() => setSelectedLead(lead)}>
                      {confScore != null ? (
                        <ConfidenceBadge score={confScore} />
                      ) : hasFlags ? (
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, padding: '2px 7px', borderRadius: 8, fontSize: 11, background: 'rgba(245,158,11,0.1)', border: '1px solid rgba(245,158,11,0.3)', color: 'hsl(var(--pt-f59e0b))', whiteSpace: 'nowrap' }}>
                          <AlertTriangle size={10} /> {(lead.data_quality_flags || []).length} flag{(lead.data_quality_flags || []).length > 1 ? 's' : ''}
                        </span>
                      ) : <span style={{ color: 'var(--line-1)', fontSize: 12 }}>—</span>}
                    </td>
                    <td style={{ padding: '13px 16px' }} onClick={() => setSelectedLead(lead)}>
                      <span style={{ padding: '2px 8px', borderRadius: 8, fontSize: 11, background: 'hsl(var(--surface-invert) / 0.05)', color: '#6b7280', whiteSpace: 'nowrap' }}>
                        {SOURCE_LABELS[lead.source] || lead.source}
                      </span>
                    </td>
                    <td style={{ padding: '13px 16px' }} onClick={e => e.stopPropagation()}>
                      <div style={{ display: 'flex', gap: 6 }}>
                        {lead.score == null ? (
                          // Unscored → prominent amber "Qualify" so the user can
                          // score leads that auto-qualify skipped (e.g. AI tokens out).
                          <button onClick={() => handleQualifyOne(lead)} disabled={qualifyingId === lead.id} title="Qualify this lead with AI" style={{ display: 'inline-flex', alignItems: 'center', gap: 5, background: 'rgba(245,158,11,0.14)', border: '1px solid rgba(245,158,11,0.4)', borderRadius: 6, padding: '5px 9px', cursor: 'pointer', color: 'hsl(var(--pt-fbbf24))', fontSize: 11, fontWeight: 600, whiteSpace: 'nowrap' }}>
                            {qualifyingId === lead.id ? <Loader2 size={12} className="animate-spin" /> : <><Brain size={12} /> Qualify</>}
                          </button>
                        ) : (
                          <button onClick={() => handleQualifyOne(lead)} disabled={qualifyingId === lead.id} title="Re-score with AI" style={{ background: 'rgba(168,85,247,0.12)', border: '1px solid rgba(168,85,247,0.3)', borderRadius: 6, padding: '5px 8px', cursor: 'pointer', color: 'hsl(var(--pt-c084fc))' }}>
                            {qualifyingId === lead.id ? <Loader2 size={12} className="animate-spin" /> : <Brain size={12} />}
                          </button>
                        )}
                        <button onClick={() => requestDelete(lead)} title="Delete" style={{ background: 'rgba(244,63,94,0.08)', border: '1px solid rgba(244,63,94,0.2)', borderRadius: 6, padding: '5px 8px', cursor: 'pointer', color: '#f87171' }}>
                          <Trash2 size={12} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      {pagination.total_pages > 1 && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10, ...cardStyle, padding: '12px 18px' }}>
          <span style={{ fontSize: 13, color: '#6b7280' }}>
            Page <strong style={{ color: 'var(--text-soft)' }}>{pagination.page}</strong> of <strong style={{ color: 'var(--text-soft)' }}>{pagination.total_pages}</strong>
            <span style={{ color: '#4b5563', marginLeft: 8 }}>({pagination.total_count.toLocaleString()} total)</span>
          </span>
          <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
            <button onClick={() => goToPage(1)} disabled={!pagination.has_prev} style={pgBtn(!pagination.has_prev)}><ChevronsLeft size={14} /></button>
            <button onClick={() => goToPage(pagination.page - 1)} disabled={!pagination.has_prev} style={pgBtn(!pagination.has_prev)}><ChevronLeft size={14} /></button>
            {Array.from({ length: pagination.total_pages }, (_, i) => i + 1)
              .filter(p => p === 1 || p === pagination.total_pages || Math.abs(p - pagination.page) <= 2)
              .reduce((acc, p, idx, arr) => { if (idx > 0 && p - arr[idx - 1] > 1) acc.push('…'); acc.push(p); return acc; }, [])
              .map((p, i) => p === '…'
                ? <span key={`e-${i}`} style={{ color: '#4b5563', padding: '0 4px', fontSize: 13 }}>…</span>
                : <button key={p} onClick={() => goToPage(p)} style={pgBtn(false, p === pagination.page)}>{p}</button>
              )}
            <button onClick={() => goToPage(pagination.page + 1)} disabled={!pagination.has_next} style={pgBtn(!pagination.has_next)}><ChevronRight size={14} /></button>
            <button onClick={() => goToPage(pagination.total_pages)} disabled={!pagination.has_next} style={pgBtn(!pagination.has_next)}><ChevronsRight size={14} /></button>
          </div>
        </div>
      )}

      {/* ── Lead Detail Slide-over ── */}
      {selectedLead && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 50, display: 'flex', justifyContent: 'flex-end' }}>
          <div style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.55)' }} onClick={() => setSelectedLead(null)} />
          <div style={{ position: 'relative', width: 520, maxWidth: '95vw', height: '100%', background: 'linear-gradient(160deg,var(--sfc-0f0a1f) 0%,var(--sfc-14082a) 100%)', borderLeft: '1px solid var(--line-1)', overflowY: 'auto', padding: 24 }}>

            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 }}>
              <div>
                <h2 style={{ color: 'var(--text-soft)', fontSize: 18, fontWeight: 700, margin: 0 }}>{selectedLead.full_name}</h2>
                <p style={{ color: 'hsl(var(--pt-9ca3af))', fontSize: 14, marginTop: 4 }}>
                  {selectedLead.job_title}{selectedLead.company_name ? ` @ ${selectedLead.company_name}` : ''}
                </p>
                {selectedLead.confidence_score != null && (
                  <div style={{ marginTop: 6 }}>
                    <ConfidenceBadge score={selectedLead.confidence_score} />
                  </div>
                )}
              </div>
              <button onClick={() => setSelectedLead(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#6b7280' }}>
                <X size={20} />
              </button>
            </div>

            {/* Industry category: move this lead to another category, or a new one. */}
            <div style={{ marginBottom: 20 }}>
              <h4 style={{ color: '#4b5563', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 5 }}>
                <Tag size={11} /> Industry category
              </h4>
              <div style={{ display: 'flex', gap: 8 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <CategoryPicker key={selectedLead.id} categories={categories} value={detailCategory} onChange={setDetailCategory} />
                </div>
                {detailCategory.trim().toLowerCase() !== (selectedLead.category || '').toLowerCase() && (
                  <Button onClick={handleSaveDetailCategory} style={{ background: 'linear-gradient(90deg,hsl(var(--brand-600)),#a855f7)', color: '#fff', border: 'none', borderRadius: 8, fontWeight: 600, fontSize: 12, height: 38 }}>
                    Save
                  </Button>
                )}
              </div>
            </div>

            {/* The ICP this lead was found for and is scored with. */}
            <div style={{ marginBottom: 20 }}>
              <h4 style={{ color: '#4b5563', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 5 }}>
                <Target size={11} /> ICP
              </h4>
              <span style={{ fontSize: 13, color: selectedLead.icp_name ? 'var(--text-soft)' : '#6b7280' }}>
                {selectedLead.icp_name || 'None of its own: scored with your default ICP'}
              </span>
            </div>

            {/* Score + category */}
            {selectedLead.score != null && (() => {
              const cat = getScoreCategory(selectedLead.score);
              const tcfg = TEMP_CONFIG[selectedLead.temperature];
              const TIcon = tcfg?.icon;
              return (
                <div style={{ display: 'flex', gap: 14, alignItems: 'center', marginBottom: 20, padding: '14px 16px', borderRadius: 10, background: `${cat.color}10`, border: `1px solid ${cat.color}30` }}>
                  <div style={{ textAlign: 'center', flexShrink: 0 }}>
                    <div style={{ fontSize: 30, fontWeight: 800, color: cat.color }}>{selectedLead.score}</div>
                    <div style={{ fontSize: 11, color: '#6b7280' }}>/ 100</div>
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 6 }}>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '4px 10px', borderRadius: 16, background: cat.bg, border: `1px solid ${cat.border}`, color: cat.color, fontWeight: 700, fontSize: 12 }}>
                        {cat.label}
                      </span>
                      {tcfg && (
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '4px 10px', borderRadius: 16, background: tcfg.bg, border: `1px solid ${tcfg.border}`, color: tcfg.color, fontWeight: 600, fontSize: 12 }}>
                          <TIcon size={12} /> {tcfg.label}
                        </span>
                      )}
                    </div>
                    {selectedLead.qualification_reasoning && (
                      <p style={{ color: 'hsl(var(--pt-9ca3af))', fontSize: 13, lineHeight: 1.5, margin: 0 }}>{selectedLead.qualification_reasoning}</p>
                    )}
                  </div>
                </div>
              );
            })()}

            {/* Score Breakdown */}
            {selectedLead.score_breakdown && Object.keys(selectedLead.score_breakdown).length > 0 && (() => {
              const bd = selectedLead.score_breakdown;
              const hasNewDims = SCORE_DIMS.some(d => bd[d.key] !== undefined);
              return (
                <div style={{ marginBottom: 20 }}>
                  <h4 style={{ color: '#4b5563', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>Score Breakdown</h4>
                  {hasNewDims ? (
                    SCORE_DIMS.map(dim => (
                      <ScoreBar key={dim.key} label={dim.label} value={bd[dim.key] ?? 0} max={dim.max} color={dim.color} icon={dim.icon} />
                    ))
                  ) : (
                    // Fallback for old scoring model
                    <>
                      <ScoreBar label="Industry Match"  value={bd.industry       ?? 0} max={30} color="#a855f7" />
                      <ScoreBar label="Job Title Match" value={bd.job_title      ?? 0} max={30} color="#10b981" />
                      <ScoreBar label="Company Size"    value={bd.company_size   ?? 0} max={20} color="#3b82f6" />
                      <ScoreBar label="Location"        value={bd.location       ?? 0} max={10} color="#f59e0b" />
                      <ScoreBar label="Buying Signals"  value={bd.buying_signals ?? 0} max={10} color="#6b7280" />
                    </>
                  )}
                </div>
              );
            })()}

            {/* Key Strengths */}
            {(selectedLead.key_strengths || []).length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <h4 style={{ color: '#4b5563', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>Key Strengths</h4>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                  {selectedLead.key_strengths.map((s, i) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 7 }}>
                      <CheckCircle2 size={13} style={{ color: '#10b981', marginTop: 1, flexShrink: 0 }} />
                      <span style={{ color: 'hsl(var(--pt-d1fae5))', fontSize: 13, lineHeight: 1.4 }}>{s}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Concerns */}
            {(selectedLead.concerns || []).length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <h4 style={{ color: '#4b5563', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>Concerns</h4>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                  {selectedLead.concerns.map((c, i) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 7 }}>
                      <AlertTriangle size={13} style={{ color: 'hsl(var(--pt-f59e0b))', marginTop: 1, flexShrink: 0 }} />
                      <span style={{ color: 'hsl(var(--pt-fef3c7))', fontSize: 13, lineHeight: 1.4 }}>{c}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Outreach Strategy */}
            {selectedLead.outreach_strategy && (
              <div style={{ marginBottom: 20, padding: '12px 14px', borderRadius: 10, background: 'rgba(59,130,246,0.08)', border: '1px solid rgba(59,130,246,0.25)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                  <Route size={13} style={{ color: '#60a5fa' }} />
                  <h4 style={{ color: '#60a5fa', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', margin: 0 }}>Recommended Outreach</h4>
                </div>
                <p style={{ color: 'hsl(var(--pt-bfdbfe))', fontSize: 13, lineHeight: 1.5, margin: 0 }}>{selectedLead.outreach_strategy}</p>
              </div>
            )}

            {/* Data Quality Flags */}
            {(() => {
              const isProspectVerified = selectedLead.research_profile?.verification?.prospect?.status === 'verified';
              const displayFlags = (selectedLead.data_quality_flags || []).filter(
                f => !(isProspectVerified && f.startsWith('Research:'))
              );
              if (!displayFlags.length) return null;
              return (
                <div style={{ marginBottom: 20, padding: '10px 14px', borderRadius: 10, background: 'rgba(245,158,11,0.06)', border: '1px solid rgba(245,158,11,0.2)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                    <ShieldAlert size={13} style={{ color: 'hsl(var(--pt-f59e0b))' }} />
                    <h4 style={{ color: 'hsl(var(--pt-f59e0b))', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', margin: 0 }}>Data Quality Issues</h4>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    {displayFlags.map((flag, i) => (
                      <span key={i} style={{ color: 'hsl(var(--pt-fef3c7))', fontSize: 12 }}>• {flag}</span>
                    ))}
                  </div>
                </div>
              );
            })()}

            {/* Enriched Data — only what the enrichment agent found, with its source.
                Fields seeded from the lead itself (source "lead_model:...") are not enrichment. */}
            {(() => {
              const enriched = Object.entries(selectedLead.enrichment_contract?.fields || {})
                .filter(([, f]) => f && f.value && !String(f.source || '').startsWith('lead_model:'));
              if (!enriched.length) return null;
              return (
              <div style={{ marginBottom: 20, padding: '12px 14px', borderRadius: 10, background: 'rgba(16,185,129,0.07)', border: '1px solid rgba(16,185,129,0.25)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                  <Sparkles size={13} style={{ color: '#10b981' }} />
                  <h4 style={{ color: '#10b981', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', margin: 0 }}>Enriched Data</h4>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {enriched
                    .map(([key, f]) => (
                      <div key={key} style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10 }}>
                        <span style={{ color: 'hsl(var(--pt-9ca3af))', fontSize: 12, textTransform: 'capitalize', flexShrink: 0 }}>{key.replace(/_/g, ' ')}</span>
                        <span style={{ color: 'var(--text-soft)', fontSize: 12.5, textAlign: 'right', wordBreak: 'break-word' }}>
                          {String(f.value)}
                          {f.source && <span style={{ marginLeft: 6, color: '#6b7280', fontSize: 10 }}>({f.source})</span>}
                        </span>
                      </div>
                    ))}
                </div>
              </div>
              );
            })()}

            {/* Contact */}
            <div style={{ marginBottom: 20 }}>
              <h4 style={{ color: '#4b5563', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>Contact</h4>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {selectedLead.email && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Mail size={13} style={{ color: '#6b7280' }} />
                    <a href={`mailto:${selectedLead.email}`} style={{ color: 'hsl(var(--pt-c084fc))', fontSize: 13 }}>{selectedLead.email}</a>
                    {selectedLead.email_bounced && <span style={{ fontSize: 11, color: '#f87171', background: 'rgba(248,113,113,0.1)', border: '1px solid rgba(248,113,113,0.3)', borderRadius: 4, padding: '1px 6px' }}>bounced</span>}
                  </div>
                )}
                {selectedLead.phone && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Phone size={13} style={{ color: '#6b7280' }} />
                    <span style={{ color: 'var(--text-soft)', fontSize: 13 }}>{selectedLead.phone}</span>
                  </div>
                )}
                {selectedLead.linkedin_url && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Linkedin size={13} style={{ color: '#6b7280' }} />
                    <a href={safeUrl(selectedLead.linkedin_url)} target="_blank" rel="noreferrer" style={{ color: '#60a5fa', fontSize: 13 }}>
                      LinkedIn Profile <ExternalLink size={10} style={{ display: 'inline', marginLeft: 2 }} />
                    </a>
                  </div>
                )}
              </div>
            </div>

            {/* Company */}
            <div style={{ marginBottom: 20 }}>
              <h4 style={{ color: '#4b5563', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>Company</h4>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {selectedLead.company_industry && <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}><Briefcase size={13} style={{ color: '#6b7280' }} /><span style={{ color: 'var(--text-soft)', fontSize: 13 }}>{selectedLead.company_industry}</span></div>}
                {selectedLead.company_size && <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}><Users size={13} style={{ color: '#6b7280' }} /><span style={{ color: 'var(--text-soft)', fontSize: 13 }}>{selectedLead.company_size.toLocaleString()} employees</span></div>}
                {selectedLead.company_location && <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}><MapPin size={13} style={{ color: '#6b7280' }} /><span style={{ color: 'var(--text-soft)', fontSize: 13 }}>{selectedLead.company_location}</span></div>}
                {selectedLead.company_website && <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}><Globe size={13} style={{ color: '#6b7280' }} /><a href={safeUrl(selectedLead.company_website)} target="_blank" rel="noreferrer" style={{ color: '#60a5fa', fontSize: 13 }}>{selectedLead.company_website} <ExternalLink size={10} style={{ display: 'inline' }} /></a></div>}
              </div>
            </div>

            {/* Technologies */}
            {(() => {
              const rawTech = selectedLead.company_technologies;
              const techList = Array.isArray(rawTech)
                ? rawTech
                : typeof rawTech === 'string' && rawTech.trim()
                  ? rawTech.split(',').map(t => t.trim()).filter(Boolean)
                  : [];
              if (!techList.length) return null;
              return (
                <div style={{ marginBottom: 20 }}>
                  <h4 style={{ color: '#4b5563', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>Technologies</h4>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    {techList.map((t, idx) => (
                      <span key={`${t}-${idx}`} style={{ padding: '3px 10px', borderRadius: 10, fontSize: 12, background: 'rgba(96,165,250,0.1)', border: '1px solid rgba(96,165,250,0.25)', color: 'hsl(var(--pt-93c5fd))' }}>{t}</span>
                    ))}
                  </div>
                </div>
              );
            })()}

            {/* Research Intelligence Profile */}
            {selectedLead.research_profile && (
              <div style={{ marginBottom: 20, padding: '14px', borderRadius: 10, background: 'rgba(14,165,233,0.06)', border: '1px solid rgba(14,165,233,0.25)' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <Search size={14} style={{ color: '#38bdf8' }} />
                    <h4 style={{ color: '#38bdf8', fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.06em', margin: 0, fontWeight: 700 }}>Company Intelligence</h4>
                  </div>
                  {(() => {
                    const c = selectedLead.research_profile.research_confidence ?? 0;
                    const tier = c >= 70
                      ? { bg: 'rgba(16,185,129,0.15)', text: '#34d399', label: 'High' }
                      : c >= 45
                        ? { bg: 'rgba(56,189,248,0.15)', text: '#38bdf8', label: 'Moderate' }
                        : { bg: 'rgba(245,158,11,0.15)', text: '#fbbf24', label: 'Limited' };
                    return (
                      <span title={`${tier.label} source verification (${c}%)`} style={{ fontSize: 11, padding: '3px 9px', borderRadius: 6, background: tier.bg, color: tier.text, fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                        <span style={{ width: 6, height: 6, borderRadius: '50%', background: tier.text }} />
                        {tier.label} {c}%
                      </span>
                    );
                  })()}
                </div>

                {selectedLead.research_profile.company_research?.overview && (
                  <p style={{ color: 'hsl(var(--pt-e0f2fe))', fontSize: 12.5, lineHeight: 1.5, marginBottom: 10 }}>
                    {selectedLead.research_profile.company_research.overview.toLowerCase() === 'unknown'
                      ? 'Research could not establish what this company does.'
                      : selectedLead.research_profile.company_research.overview}
                  </p>
                )}

                {selectedLead.research_profile.verification?.prospect?.reason && (
                  <p style={{ color: selectedLead.research_profile.verification.prospect.status === 'verified' ? '#34d399' : '#fbbf24', fontSize: 12, marginBottom: 10 }}>
                    {selectedLead.research_profile.verification.prospect.reason}
                  </p>
                )}

                {selectedLead.research_profile.prospect_research?.decision_making_relevance
                  && selectedLead.research_profile.prospect_research.decision_making_relevance.toLowerCase() !== 'unknown' && (
                  <div style={{ marginBottom: 10, padding: '8px 10px', borderRadius: 6, background: 'rgba(0,0,0,0.2)' }}>
                    <span style={{ color: '#94a3b8', fontSize: 11, textTransform: 'uppercase', display: 'block', marginBottom: 2 }}>Prospect Context</span>
                    <span style={{ color: '#f1f5f9', fontSize: 12 }}>
                      {selectedLead.research_profile.prospect_research.decision_making_relevance}
                    </span>
                  </div>
                )}

                {Array.isArray(selectedLead.research_profile.evidence) && selectedLead.research_profile.evidence.length > 0 && (
                  <div>
                    <span style={{ color: '#94a3b8', fontSize: 11, textTransform: 'uppercase', display: 'block', marginBottom: 6 }}>Evidence ({selectedLead.research_profile.evidence.length})</span>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                      {selectedLead.research_profile.evidence.slice(0, 3).map((ev, i) => (
                        <div key={i} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 11 }}>
                          <span style={{ color: '#cbd5e1', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '75%' }}>
                            {ev.finding}
                          </span>
                          {ev.source_url && (
                            <a href={safeUrl(ev.source_url)} target="_blank" rel="noreferrer" style={{ color: '#38bdf8', display: 'flex', alignItems: 'center', gap: 2 }}>
                              source <ExternalLink size={10} />
                            </a>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Buying Signals */}
            {(() => {
              const rawSignals = selectedLead.buying_signals;
              const signalsList = Array.isArray(rawSignals)
                ? rawSignals
                : typeof rawSignals === 'string' && rawSignals.trim()
                  ? [rawSignals]
                  : [];
              if (!signalsList.length) return null;
              return (
                <div style={{ marginBottom: 20 }}>
                  <h4 style={{ color: '#4b5563', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>Buying Signals</h4>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {signalsList.map((s, i) => (
                      <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                        <Sparkles size={12} style={{ color: '#10b981', marginTop: 2, flexShrink: 0 }} />
                        <span style={{ color: 'hsl(var(--pt-d1fae5))', fontSize: 13 }}>
                          {typeof s === 'object' && s !== null ? (s.description || s.title || JSON.stringify(s)) : String(s)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })()}

            {/* Actions Toolbar - 2x2 Balanced Layout */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, paddingTop: 14, borderTop: '1px solid var(--sfc-1e0f38)' }}>
              <Button
                onClick={() => handleEnrichOne(selectedLead)}
                disabled={enrichingId === selectedLead.id || ['pending', 'processing'].includes(selectedLead.enrichment_status)}
                style={{
                  height: 38,
                  padding: '0 10px',
                  background: 'linear-gradient(90deg,#059669,#10b981)',
                  color: '#fff',
                  border: 'none',
                  borderRadius: 8,
                  fontWeight: 600,
                  fontSize: 12,
                  whiteSpace: 'nowrap',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 6,
                }}
              >
                {(enrichingId === selectedLead.id || ['pending', 'processing'].includes(selectedLead.enrichment_status)) ? <Loader2 size={13} className="animate-spin flex-shrink-0" /> : <Sparkles size={13} className="flex-shrink-0" />}
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {(enrichingId === selectedLead.id || selectedLead.enrichment_status === 'pending' || selectedLead.enrichment_status === 'processing')
                    ? 'Enriching…'
                    : (['done', 'completed', 'partial'].includes(selectedLead.enrichment_status) ? 'Re-enrich' : 'Enrich Lead')}
                </span>
              </Button>

              <Button
                onClick={() => handleResearchOne(selectedLead)}
                disabled={researchingId === selectedLead.id}
                style={{
                  height: 38,
                  padding: '0 10px',
                  background: 'linear-gradient(90deg,#0284c7,#0369a1)',
                  color: '#fff',
                  border: 'none',
                  borderRadius: 8,
                  fontWeight: 600,
                  fontSize: 12,
                  whiteSpace: 'nowrap',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 6,
                }}
              >
                {researchingId === selectedLead.id ? <Loader2 size={13} className="animate-spin flex-shrink-0" /> : <Search size={13} className="flex-shrink-0" />}
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {selectedLead.research_status === 'completed' ? 'Re-research' : 'Research Lead'}
                </span>
              </Button>

              <Button
                onClick={() => handleQualifyOne(selectedLead)}
                disabled={qualifyingId === selectedLead.id}
                style={{
                  height: 38,
                  padding: '0 10px',
                  background: 'linear-gradient(90deg,hsl(var(--brand-600)),#a855f7)',
                  color: '#fff',
                  border: 'none',
                  borderRadius: 8,
                  fontWeight: 600,
                  fontSize: 12,
                  whiteSpace: 'nowrap',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 6,
                }}
              >
                {qualifyingId === selectedLead.id ? <Loader2 size={13} className="animate-spin flex-shrink-0" /> : <Brain size={13} className="flex-shrink-0" />}
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {selectedLead.score != null ? 'Re-score with AI' : 'Score with AI'}
                </span>
              </Button>

              <Button
                onClick={() => requestDelete(selectedLead)}
                variant="outline"
                style={{
                  height: 38,
                  padding: '0 10px',
                  border: '1px solid rgba(244,63,94,0.35)',
                  background: 'rgba(244,63,94,0.06)',
                  color: '#f87171',
                  borderRadius: 8,
                  fontWeight: 600,
                  fontSize: 12,
                  whiteSpace: 'nowrap',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 6,
                }}
              >
                <Trash2 size={13} className="flex-shrink-0" />
                <span>Delete Lead</span>
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Bulk Delete Dialog */}
      <Dialog open={showBulkDeleteConfirm} onOpenChange={setShowBulkDeleteConfirm}>
        <DialogContent style={{ background: 'linear-gradient(135deg,var(--sfc-0f0a1f) 0%,var(--sfc-14082a) 100%)', border: '1px solid var(--line-1)', color: 'var(--text-soft)', maxWidth: 420 }}>
          <DialogHeader>
            <DialogTitle style={{ color: '#f87171', display: 'flex', alignItems: 'center', gap: 8 }}>
              <Trash2 size={18} /> Confirm Delete
            </DialogTitle>
          </DialogHeader>
          <div style={{ padding: '8px 0', lineHeight: 1.6 }}>
            <p style={{ color: 'var(--text-soft)', marginBottom: 8 }}>Delete <strong style={{ color: '#f87171' }}>{selectedIds.size} lead{selectedIds.size > 1 ? 's' : ''}</strong>?</p>
            <p style={{ color: '#6b7280', fontSize: 13 }}>You can undo this from the notification right after.</p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowBulkDeleteConfirm(false)} style={{ border: '1px solid var(--line-1)', color: 'hsl(var(--pt-9ca3af))', borderRadius: 8 }}>Cancel</Button>
            <Button onClick={handleBulkDelete} disabled={bulkDeleting} style={{ background: 'linear-gradient(90deg,#dc2626,#f43f5e)', color: '#fff', border: 'none', borderRadius: 8, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}>
              {bulkDeleting ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
              {bulkDeleting ? 'Deleting…' : `Delete ${selectedIds.size}`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Single Delete Confirmation Dialog */}
      <Dialog open={!!pendingDeleteLead} onOpenChange={(open) => { if (!open) setPendingDeleteLead(null); }}>
        <DialogContent style={{ background: 'linear-gradient(135deg,var(--sfc-0f0a1f) 0%,var(--sfc-14082a) 100%)', border: '1px solid var(--line-1)', color: 'var(--text-soft)', maxWidth: 420 }}>
          <DialogHeader>
            <DialogTitle style={{ color: '#f87171', display: 'flex', alignItems: 'center', gap: 8 }}>
              <Trash2 size={18} /> Confirm Delete
            </DialogTitle>
          </DialogHeader>
          <div style={{ padding: '8px 0', lineHeight: 1.6 }}>
            <p style={{ color: 'var(--text-soft)', marginBottom: 8 }}>
              Delete <strong style={{ color: '#f87171' }}>{pendingDeleteLead?.display_name || pendingDeleteLead?.full_name || 'this lead'}</strong>?
            </p>
            <p style={{ color: '#6b7280', fontSize: 13 }}>You can undo this from the notification right after.</p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPendingDeleteLead(null)} style={{ border: '1px solid var(--line-1)', color: 'hsl(var(--pt-9ca3af))', borderRadius: 8 }}>Cancel</Button>
            <Button onClick={confirmDelete} disabled={deletingSingle} style={{ background: 'linear-gradient(90deg,#dc2626,#f43f5e)', color: '#fff', border: 'none', borderRadius: 8, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}>
              {deletingSingle ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
              {deletingSingle ? 'Deleting…' : 'Delete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* CSV Import Preview Modal */}
      <Dialog open={!!csvImport} onOpenChange={(open) => { if (!open && !csvImporting) setCsvImport(null); }}>
        <DialogContent style={{ background: 'linear-gradient(135deg,var(--sfc-0f0a1f) 0%,var(--sfc-14082a) 100%)', border: '1px solid var(--line-1)', color: 'var(--text-soft)', maxWidth: 760 }}>
          <DialogHeader>
            <DialogTitle style={{ color: 'var(--text-soft)', display: 'flex', alignItems: 'center', gap: 8 }}>
              <Upload size={18} color="#a855f7" /> Import leads from CSV
            </DialogTitle>
          </DialogHeader>
          {/* STEP 1 — no file yet: show the expected column format + guidance */}
          {csvImport && !csvImport.file && (
            <div style={{ padding: '4px 0' }}>
              <p style={{ fontSize: 13, color: 'hsl(var(--pt-c4b5d4))', marginBottom: 12 }}>
                Your CSV needs a <b style={{ color: 'var(--text-soft)' }}>header row</b>. Put the columns in this order
                (capitalisation and spacing don’t matter):
              </p>

              {/* Column guide */}
              <div style={{ border: '1px solid var(--line-1)', borderRadius: 10, overflow: 'hidden', marginBottom: 14 }}>
                {[
                  { n: 1, col: 'Full Name',    req: true,  ex: 'Jane Doe' },
                  { n: 2, col: 'Email',        req: true,  ex: 'jane@acme.com' },
                  { n: 3, col: 'Job Title',    req: false, ex: 'VP of Sales' },
                  { n: 4, col: 'Company',      req: false, ex: 'Acme Corp' },
                  { n: 5, col: 'Industry',     req: false, ex: 'SaaS' },
                  { n: 6, col: 'Employees',    req: false, ex: '150' },
                  { n: 7, col: 'Location',     req: false, ex: 'San Francisco, CA' },
                  { n: 8, col: 'Phone',        req: false, ex: '+1 555 000 0000' },
                  { n: 9, col: 'LinkedIn URL', req: false, ex: 'https://linkedin.com/in/jane' },
                ].map((r) => (
                  <div key={r.n} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px', borderBottom: '1px solid hsl(var(--sfr-2d1f4a) / 0.5)' }}>
                    <span style={{ width: 22, height: 22, borderRadius: 6, background: 'rgba(168,85,247,0.15)', color: 'hsl(var(--pt-c084fc))', fontSize: 12, fontWeight: 700, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>{r.n}</span>
                    <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-soft)', minWidth: 110 }}>{r.col}</span>
                    {r.req
                      ? <span style={{ fontSize: 10, fontWeight: 700, color: '#f87171', background: 'rgba(244,63,94,0.12)', border: '1px solid rgba(244,63,94,0.3)', borderRadius: 6, padding: '1px 7px' }}>Required</span>
                      : <span style={{ fontSize: 10, color: '#6b7280' }}>optional</span>}
                    <span style={{ marginLeft: 'auto', fontSize: 12, color: '#8b7bb5', fontFamily: 'monospace' }}>{r.ex}</span>
                  </div>
                ))}
              </div>

              {/* Example line */}
              <div style={{ background: 'var(--sfc-0b0716)', border: '1px solid var(--line-1)', borderRadius: 8, padding: '10px 12px', marginBottom: 14, overflowX: 'auto' }}>
                <p style={{ fontSize: 10, color: '#6b7280', margin: '0 0 4px' }}>Example CSV</p>
                <pre style={{ margin: 0, fontSize: 11, color: 'hsl(var(--pt-c4b5d4))', fontFamily: 'monospace', whiteSpace: 'pre' }}>{`Full Name,Email,Job Title,Company,Industry,Employees,Location,Phone,LinkedIn URL
Jane Doe,jane@acme.com,VP Sales,Acme Corp,SaaS,150,"San Francisco, CA",,https://linkedin.com/in/jane`}</pre>
              </div>

              <p style={{ fontSize: 11, color: '#6b7280', marginBottom: 4 }}>
                Only <b style={{ color: 'hsl(var(--pt-c4b5d4))' }}>Full Name</b> and <b style={{ color: 'hsl(var(--pt-c4b5d4))' }}>Email</b> are required — the rest are optional. Duplicate emails are skipped automatically.
              </p>
            </div>
          )}

          {/* STEP 2 — file chosen: show the parsed preview */}
          {csvImport && csvImport.file && (
            <div style={{ padding: '4px 0' }}>
              {/* Summary */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 12 }}>
                <span style={{ fontSize: 13, color: 'hsl(var(--pt-9ca3af))', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                  <FileText size={14} /> {csvImport.file?.name}
                </span>
                <span style={{ fontSize: 12, fontWeight: 700, color: 'hsl(var(--pt-4ade80))', background: 'rgba(74,222,128,0.1)', border: '1px solid rgba(74,222,128,0.3)', borderRadius: 20, padding: '3px 12px' }}>
                  {csvImport.total} lead{csvImport.total === 1 ? '' : 's'} to import
                </span>
                {csvImport.skippedEmpty > 0 && (
                  <span style={{ fontSize: 12, color: 'hsl(var(--pt-9ca3af))' }}>{csvImport.skippedEmpty} empty row{csvImport.skippedEmpty === 1 ? '' : 's'} skipped</span>
                )}
              </div>

              {/* Preview table (first 10) */}
              <div style={{ border: '1px solid var(--line-1)', borderRadius: 10, maxHeight: 340, overflow: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                  <thead style={{ position: 'sticky', top: 0, background: 'var(--panel-1)' }}>
                    <tr>
                      {csvImport.columns.map((c) => (
                        <th key={c.key} style={{ textAlign: 'left', padding: '9px 12px', color: '#8b7bb5', fontWeight: 600, borderBottom: '1px solid var(--line-1)', whiteSpace: 'nowrap' }}>{c.label}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {csvImport.rows.slice(0, 10).map((row, ri) => (
                      <tr key={ri} style={{ borderBottom: '1px solid hsl(var(--sfr-2d1f4a) / 0.5)' }}>
                        {csvImport.columns.map((c) => (
                          <td key={c.key} style={{ padding: '8px 12px', color: row[c.key] ? 'var(--text-soft)' : '#4b5563', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {row[c.key] || '—'}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {csvImport.total > 10 && (
                <p style={{ fontSize: 11, color: '#6b7280', marginTop: 8 }}>Showing first 10 of {csvImport.total}. All will be imported.</p>
              )}
              <div style={{ marginTop: 12 }}>
                <label style={{ color: 'hsl(var(--pt-9ca3af))', fontSize: 12, display: 'block', marginBottom: 6 }}>Category for these leads</label>
                <CategoryPicker categories={categories} value={csvCategory} onChange={setCsvCategory}
                  emptyLabel="Automatic (each row's Industry column)" />
              </div>
              <div style={{ marginTop: 12 }}>
                <IcpPicker icps={icpProfiles} value={csvIcpId} onChange={setCsvIcpId} />
              </div>
              <p style={{ fontSize: 11, color: '#6b7280', marginTop: 8 }}>
                Duplicate emails already in your list are skipped automatically.
              </p>
            </div>
          )}
          <DialogFooter>
            {csvImport && !csvImport.file ? (
              <>
                <Button variant="outline" onClick={downloadCsvTemplate} style={{ border: '1px solid var(--line-1)', color: 'hsl(var(--pt-9ca3af))', borderRadius: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Download size={14} /> Download template
                </Button>
                <Button onClick={() => fileInputRef.current?.click()} style={{ background: 'linear-gradient(90deg,hsl(var(--brand-600)),#a855f7)', color: '#fff', border: 'none', borderRadius: 8, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Upload size={14} /> Choose CSV file
                </Button>
              </>
            ) : (
              <>
                <Button variant="outline" onClick={() => setCsvImport(null)} disabled={csvImporting} style={{ border: '1px solid var(--line-1)', color: 'hsl(var(--pt-9ca3af))', borderRadius: 8 }}>Cancel</Button>
                <Button onClick={handleCsvConfirm} disabled={csvImporting || !csvImport?.total} style={{ background: 'linear-gradient(90deg,hsl(var(--brand-600)),#a855f7)', color: '#fff', border: 'none', borderRadius: 8, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}>
                  {csvImporting ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
                  {csvImporting ? 'Importing…' : `Import ${csvImport?.total || 0} leads`}
                </Button>
              </>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Add Lead Modal */}
      <Dialog open={showAddModal} onOpenChange={setShowAddModal}>
        <DialogContent style={{ background: 'linear-gradient(135deg,var(--sfc-0f0a1f) 0%,var(--sfc-14082a) 100%)', border: '1px solid var(--line-1)', color: 'var(--text-soft)', maxWidth: 560 }}>
          <DialogHeader>
            <DialogTitle style={{ color: 'var(--text-soft)' }}>Add Lead Manually</DialogTitle>
          </DialogHeader>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, padding: '8px 0' }}>
            {[
              { k: 'first_name',       l: 'First Name',   p: 'Jane' },
              { k: 'last_name',        l: 'Last Name',    p: 'Doe' },
              { k: 'email',            l: 'Business Email', p: 'jane@company.com', span: true },
              { k: 'phone',            l: 'Phone',        p: '+1 555 000 0000' },
              { k: 'job_title',        l: 'Job Title',    p: 'VP of Sales' },
              { k: 'company_name',     l: 'Company',      p: 'Acme Corp' },
              { k: 'company_industry', l: 'Industry',     p: 'SaaS' },
              { k: 'company_size',     l: 'Employees',    p: '150', type: 'number' },
              { k: 'company_location', l: 'Location',     p: 'San Francisco, CA', span: true },
              { k: 'linkedin_url',     l: 'LinkedIn URL', p: 'https://linkedin.com/in/…', span: true },
            ].map(({ k, l, p, span, type }) => (
              <div key={k} style={{ gridColumn: span ? '1 / -1' : undefined }}>
                <label style={{ color: 'hsl(var(--pt-9ca3af))', fontSize: 12, display: 'block', marginBottom: 4 }}>{l}</label>
                <input type={type || 'text'} placeholder={p} value={newLead[k]} onChange={e => setNewLead(prev => ({ ...prev, [k]: e.target.value }))} style={inputStyle} />
              </div>
            ))}
            <div style={{ gridColumn: '1 / -1' }}>
              <label style={{ color: 'hsl(var(--pt-9ca3af))', fontSize: 12, display: 'block', marginBottom: 4 }}>Category</label>
              <CategoryPicker categories={categories} value={newLeadCategory} onChange={setNewLeadCategory}
                emptyLabel="Automatic (from the Industry above)" />
            </div>
            {icpProfiles.length > 1 && (
              <div style={{ gridColumn: '1 / -1' }}>
                <IcpPicker icps={icpProfiles} value={newLeadIcpId} onChange={setNewLeadIcpId} label="Score this lead with" />
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setShowAddModal(false); setNewLead(BLANK_LEAD); setNewLeadCategory(''); }} style={{ border: '1px solid var(--line-1)', color: 'hsl(var(--pt-9ca3af))', borderRadius: 8 }}>Cancel</Button>
            <Button onClick={handleAddLead} disabled={addingLead} style={{ background: 'linear-gradient(90deg,#f43f5e,#a855f7)', color: '#fff', border: 'none', borderRadius: 8, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}>
              {addingLead ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />}
              Add Lead
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Generate Leads Modal */}
      <Dialog open={showGenModal} onOpenChange={setShowGenModal}>
        <DialogContent style={{ background: 'linear-gradient(135deg,var(--sfc-0f0a1f) 0%,var(--sfc-14082a) 100%)', border: '1px solid var(--line-1)', color: 'var(--text-soft)', maxWidth: 480 }}>
          <DialogHeader>
            <DialogTitle style={{ color: 'var(--text-soft)', display: 'flex', alignItems: 'center', gap: 8 }}>
              <Zap size={18} color="#a855f7" /> Generate Leads
            </DialogTitle>
          </DialogHeader>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 18, padding: '8px 0' }}>
            {/* Source selection */}
            <div>
              <label style={{ color: 'hsl(var(--pt-9ca3af))', fontSize: 12, display: 'block', marginBottom: 8 }}>Data Source</label>
              <div style={{ display: 'flex', gap: 8, flexDirection: 'column' }}>
                {[
                  { key: 'apify',  label: 'Apify',     desc: 'Web scraping — LinkedIn & Google search', color: '#a855f7', paid: true },
                  { key: 'apollo', label: 'Apollo.io', desc: 'Verified B2B contact database',           color: '#3b82f6', paid: true },
                ].map(s => (
                  <button key={s.key} onClick={() => setGenSource(s.key)} style={{
                    padding: '10px 14px', borderRadius: 10, cursor: 'pointer', textAlign: 'left',
                    background: genSource === s.key ? `${s.color}22` : 'hsl(var(--surface-invert) / 0.03)',
                    border: `1px solid ${genSource === s.key ? s.color : 'var(--line-1)'}`,
                    transition: 'all 0.2s',
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ color: 'var(--text-soft)', fontWeight: 600, fontSize: 14 }}>{s.label}</span>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        {s.paid ? (
                          <span style={{ fontSize: 10, padding: '1px 6px', borderRadius: 4, background: 'rgba(234,179,8,0.15)', color: 'hsl(var(--pt-fcd34d))' }}>PAID API</span>
                        ) : (
                          <span style={{ fontSize: 10, padding: '1px 6px', borderRadius: 4, background: 'rgba(16,185,129,0.15)', color: '#34d399' }}>FREE</span>
                        )}
                        {s.paid && (
                          <span onClick={(e) => { e.stopPropagation(); setShowSetupGuide(s.key); }} style={{ color: '#4b5563', cursor: 'pointer', display: 'flex', alignItems: 'center', transition: 'color 0.2s' }}
                            onMouseEnter={e => e.currentTarget.style.color = s.color}
                            onMouseLeave={e => e.currentTarget.style.color = '#4b5563'}>
                            <HelpCircle size={13} />
                          </span>
                        )}
                      </div>
                    </div>
                    <div style={{ color: '#6b7280', fontSize: 12, marginTop: 2 }}>{s.desc}</div>
                  </button>
                ))}
              </div>
            </div>

            {/* Key warning */}
            {sdrKeyStatus.loaded && !sdrKeyStatus[genSource] && (
              <div style={{ padding: '12px 14px', borderRadius: 10, background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)', display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                <span style={{ fontSize: 18, lineHeight: 1 }}>🔑</span>
                <div>
                  <p style={{ color: '#f87171', fontWeight: 600, fontSize: 13, marginBottom: 4 }}>
                    {genSource === 'apollo' ? 'Apollo.io' : 'Apify'} API key not configured
                  </p>
                  <button onClick={() => { setShowGenModal(false); navigate('/ai-sdr/settings'); }}
                    style={{ background: 'linear-gradient(135deg,#a855f7,#ec4899)', border: 'none', borderRadius: 6, padding: '6px 14px', color: '#fff', fontSize: 12, fontWeight: 600, cursor: 'pointer' }}>
                    Go to Settings →
                  </button>
                </div>
              </div>
            )}

            {/* ICP */}
            {icpProfiles.length > 1 && (
              <div>
                <label style={{ color: 'hsl(var(--pt-9ca3af))', fontSize: 12, display: 'block', marginBottom: 6 }}>ICP Profile</label>
                <select value={genIcpId} onChange={e => setGenIcpId(e.target.value)} style={{ ...inputStyle, background: 'hsl(var(--sfr-1e0a32) / 0.6)', border: '1px solid var(--line-1)' }}>
                  {icpProfiles.map(p => <option key={p.id} value={p.id}>{p.name}{p.is_active ? ' (Default)' : ''}</option>)}
                </select>
              </div>
            )}
            {icpProfiles.length === 0 && (
              <div style={{ padding: 12, borderRadius: 8, background: 'rgba(244,63,94,0.08)', border: '1px solid rgba(244,63,94,0.2)', color: '#f87171', fontSize: 13 }}>
                No ICP profile found. Set up your ICP profile first to target the right leads.
              </div>
            )}

            {/* Category the new leads are filed under */}
            <div>
              <label style={{ color: 'hsl(var(--pt-9ca3af))', fontSize: 12, display: 'block', marginBottom: 6 }}>Category</label>
              <CategoryPicker categories={categories} value={genCategory} onChange={setGenCategory}
                emptyLabel="Automatic (the industry you search for)" />
              <p style={{ color: '#6b7280', fontSize: 11, marginTop: 4 }}>
                Automatic files each lead under the ICP industry it matches{(() => {
                  const ind = icpProfiles.find(p => String(p.id) === String(genIcpId))?.industries || [];
                  return ind.length ? ` (${ind.join(', ')})` : '';
                })()}. Apify runs you fetch go under each lead's own industry.
              </p>
            </div>

            {/* Count */}
            <div>
              <label style={{ color: 'hsl(var(--pt-9ca3af))', fontSize: 12, display: 'block', marginBottom: 6 }}>
                Number of Leads: <span style={{ color: '#a855f7', fontWeight: 700 }}>{genCount}</span>
              </label>
              <input type="range" min={5} max={200} step={5} value={genCount} onChange={e => setGenCount(Number(e.target.value))} style={{ width: '100%', accentColor: '#a855f7' }} />
              <div style={{ display: 'flex', justifyContent: 'space-between', color: '#4b5563', fontSize: 11, marginTop: 2 }}>
                <span>5</span><span>200</span>
              </div>
            </div>
          </div>

          {/* Fetch-from-Apify — import runs you generated in the Apify Console.
              Useful on the free Apify plan (can't RUN paid actors via API, but
              can read finished runs). */}
          <div style={{ marginTop: 6, padding: '10px 12px', borderRadius: 10, background: 'hsl(var(--brand-600) / 0.06)', border: '1px solid var(--line-1)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--text-soft)' }}>Already generated in Apify?</div>
              <div style={{ fontSize: 11.5, color: 'hsl(var(--pt-9ca3af))' }}>Import leads from your finished Apify runs (works on the free plan).</div>
            </div>
            <button onClick={handleFetchApify} disabled={fetchingApify}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: 'hsl(var(--brand-600) / 0.15)', border: '1px solid rgba(168,85,247,0.35)', color: 'hsl(var(--pt-c4b5fd))', borderRadius: 8, padding: '7px 14px', fontSize: 12.5, fontWeight: 600, cursor: fetchingApify ? 'default' : 'pointer', whiteSpace: 'nowrap' }}>
              {fetchingApify ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />}
              {fetchingApify ? 'Fetching…' : 'Fetch from Apify'}
            </button>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowGenModal(false)} style={{ border: '1px solid var(--line-1)', color: 'hsl(var(--pt-9ca3af))', borderRadius: 8 }}>Cancel</Button>
            <Button onClick={handleGenerate}
              disabled={generating || icpProfiles.length === 0 || (sdrKeyStatus.loaded && !sdrKeyStatus[genSource])}
              style={{ background: 'linear-gradient(90deg,hsl(var(--brand-600)),#a855f7)', color: '#fff', border: 'none', borderRadius: 8, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}>
              {generating ? <Loader2 size={13} className="animate-spin" /> : <Zap size={13} />}
              {generating
                ? (genProgress ? `Generating… ${genProgress.created}/${genProgress.total}` : 'Starting…')
                : `Generate ${genCount} Leads`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <CategoryManagerDialog open={showCategoryManager} onOpenChange={setShowCategoryManager}
        categories={categories} onChanged={refreshAfterCategoryChange} />

      {/* Setup Guide Modal */}
      <Dialog open={!!showSetupGuide} onOpenChange={() => setShowSetupGuide(null)}>
        <DialogContent style={{ background: 'linear-gradient(135deg,var(--sfc-0f0a1f) 0%,var(--sfc-14082a) 100%)', border: '1px solid var(--line-1)', color: 'var(--text-soft)', maxWidth: 520, maxHeight: '85vh', overflowY: 'auto' }}>
          <DialogHeader>
            <DialogTitle style={{ color: 'var(--text-soft)' }}>
              {showSetupGuide === 'apify' ? '⚡ Connect Apify' : '🚀 Connect Apollo.io'}
            </DialogTitle>
          </DialogHeader>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16, padding: '4px 0 8px' }}>
            {showSetupGuide === 'apify' && (
              <>
                <div style={{ padding: '8px 12px', borderRadius: 8, background: 'rgba(234,179,8,0.08)', border: '1px solid rgba(234,179,8,0.2)' }}>
                  <span style={{ color: 'hsl(var(--pt-fcd34d))', fontSize: 13, fontWeight: 600 }}>⚠️ Requires Apify paid plan ($49+/month)</span>
                </div>
                {[
                  { step: 1, title: 'Create account & upgrade', detail: 'Sign up at apify.com and upgrade to a paid plan (Starter $49/month) for enough credits.' },
                  { step: 2, title: 'Copy your API Token', detail: 'Profile icon → Settings → Integrations tab → Personal API token → Copy.' },
                  { step: 3, title: 'Add to .env', code: 'APIFY_API_TOKEN=apify_api_xxxxxxxx' },
                  { step: 4, title: 'Restart server & generate', code: 'python manage.py runserver' },
                ].map(s => (
                  <div key={s.step} style={{ display: 'flex', gap: 12 }}>
                    <div style={{ flexShrink: 0, width: 24, height: 24, borderRadius: '50%', background: 'rgba(168,85,247,0.2)', border: '1px solid hsl(var(--brand-600))', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#a855f7', fontSize: 12, fontWeight: 700, marginTop: 2 }}>{s.step}</div>
                    <div style={{ flex: 1 }}>
                      <div style={{ color: 'var(--text-soft)', fontWeight: 600, fontSize: 13, marginBottom: 3 }}>{s.title}</div>
                      {s.detail && <div style={{ color: 'hsl(var(--pt-9ca3af))', fontSize: 12, lineHeight: 1.5 }}>{s.detail}</div>}
                      {s.code && (
                        <div style={{ marginTop: 6, padding: '8px 12px', borderRadius: 8, background: 'rgba(0,0,0,0.4)', border: '1px solid var(--sfc-1e1035)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                          <code style={{ color: '#a855f7', fontSize: 11, flex: 1, wordBreak: 'break-all' }}>{s.code}</code>
                          <button onClick={() => { navigator.clipboard.writeText(s.code); setCopiedKey(s.step); setTimeout(() => setCopiedKey(null), 2000); }} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: copiedKey === s.step ? 'hsl(var(--pt-4ade80))' : '#6b7280' }}>
                            {copiedKey === s.step ? <CheckCircle size={13} /> : <Copy size={13} />}
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </>
            )}
            {showSetupGuide === 'apollo' && (
              <>
                <div style={{ padding: '8px 12px', borderRadius: 8, background: 'rgba(234,179,8,0.08)', border: '1px solid rgba(234,179,8,0.2)' }}>
                  <span style={{ color: 'hsl(var(--pt-fcd34d))', fontSize: 13, fontWeight: 600 }}>⚠️ Requires Apollo.io Basic plan ($49+/month)</span>
                </div>
                {[
                  { step: 1, title: 'Create & upgrade account', detail: 'Go to app.apollo.io and upgrade to Basic or higher — free plan does not include API People Search.' },
                  { step: 2, title: 'Create API Key', detail: 'developer.apollo.io → Create Account → Create API Key. Copy it immediately.' },
                  { step: 3, title: 'Add to .env', code: 'APOLLO_API_KEY=your_apollo_api_key_here' },
                  { step: 4, title: 'Restart server', code: 'python manage.py runserver' },
                ].map(s => (
                  <div key={s.step} style={{ display: 'flex', gap: 12 }}>
                    <div style={{ flexShrink: 0, width: 24, height: 24, borderRadius: '50%', background: 'rgba(59,130,246,0.2)', border: '1px solid #3b82f6', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#60a5fa', fontSize: 12, fontWeight: 700, marginTop: 2 }}>{s.step}</div>
                    <div style={{ flex: 1 }}>
                      <div style={{ color: 'var(--text-soft)', fontWeight: 600, fontSize: 13, marginBottom: 3 }}>{s.title}</div>
                      {s.detail && <div style={{ color: 'hsl(var(--pt-9ca3af))', fontSize: 12, lineHeight: 1.5 }}>{s.detail}</div>}
                      {s.code && (
                        <div style={{ marginTop: 6, padding: '8px 12px', borderRadius: 8, background: 'rgba(0,0,0,0.4)', border: '1px solid var(--sfc-1e1035)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                          <code style={{ color: '#60a5fa', fontSize: 11, flex: 1, wordBreak: 'break-all' }}>{s.code}</code>
                          <button onClick={() => { navigator.clipboard.writeText(s.code); setCopiedKey(s.step + 10); setTimeout(() => setCopiedKey(null), 2000); }} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: copiedKey === s.step + 10 ? 'hsl(var(--pt-4ade80))' : '#6b7280' }}>
                            {copiedKey === s.step + 10 ? <CheckCircle size={13} /> : <Copy size={13} />}
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </>
            )}
          </div>
          <DialogFooter>
            <Button onClick={() => { setShowSetupGuide(null); setGenSource(showSetupGuide); }}
              style={{ background: showSetupGuide === 'apify' ? 'linear-gradient(90deg,hsl(var(--brand-600)),#a855f7)' : 'linear-gradient(90deg,#1d4ed8,#3b82f6)', color: '#fff', border: 'none', borderRadius: 8, fontWeight: 600 }}>
              Use {showSetupGuide === 'apify' ? 'Apify' : 'Apollo.io'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default SDRLeadsTab;
