import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Users, Search, Plus, Upload, Brain,
  Flame, Thermometer, Snowflake, ExternalLink, Linkedin, Globe,
  MapPin, Briefcase, Phone, Mail, TrendingUp, RefreshCw, X,
  Loader2, Trash2, Zap, ChevronDown, HelpCircle, CheckCircle, Copy,
  ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight,
  ArrowUpDown, SlidersHorizontal, Download, FileText, FileSpreadsheet,
  Square, CheckSquare, MinusSquare,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import { useToast } from '@/components/ui/use-toast';
import {
  listLeads, createLead, deleteLead, qualifyLead, importLeadsFromCSV,
  researchLeads, listIcpProfiles, getIcpProfile, saveIcpProfile,
  bulkDeleteLeads,
} from '@/services/aiSdrService';

// --------------------------------------------------------------------------
// Constants
// --------------------------------------------------------------------------
const TEMP_CONFIG = {
  hot:  { label: 'Hot',  icon: Flame,       color: '#f43f5e', bg: 'rgba(244,63,94,0.12)',  border: 'rgba(244,63,94,0.3)'  },
  warm: { label: 'Warm', icon: Thermometer, color: '#f59e0b', bg: 'rgba(245,158,11,0.12)', border: 'rgba(245,158,11,0.3)' },
  cold: { label: 'Cold', icon: Snowflake,   color: '#60a5fa', bg: 'rgba(96,165,250,0.12)', border: 'rgba(96,165,250,0.3)' },
};

const SCORE_COLOR = (s) =>
  s >= 70 ? '#f43f5e' : s >= 40 ? '#f59e0b' : '#60a5fa';

const SOURCE_LABELS = {
  apollo: 'Apollo.io', apify: 'Apify', ai_generated: 'AI', csv_import: 'CSV', manual: 'Manual',
};

const LEAD_STATUS_CONFIG = {
  new:              { label: 'New',            color: '#6b7280', bg: 'rgba(107,114,128,0.12)', border: 'rgba(107,114,128,0.25)' },
  qualified:        { label: 'Qualified',       color: '#60a5fa', bg: 'rgba(96,165,250,0.12)',  border: 'rgba(96,165,250,0.25)'  },
  contacted:        { label: 'Contacted',       color: '#a78bfa', bg: 'rgba(167,139,250,0.12)', border: 'rgba(167,139,250,0.25)' },
  replied:          { label: 'Replied',         color: '#4ade80', bg: 'rgba(74,222,128,0.12)',  border: 'rgba(74,222,128,0.25)'  },
  meeting_scheduled:{ label: 'Meeting',         color: '#34d399', bg: 'rgba(52,211,153,0.12)',  border: 'rgba(52,211,153,0.25)'  },
  converted:        { label: 'Converted',       color: '#fbbf24', bg: 'rgba(251,191,36,0.12)',  border: 'rgba(251,191,36,0.25)'  },
  disqualified:     { label: 'Disqualified',    color: '#f87171', bg: 'rgba(248,113,113,0.12)', border: 'rgba(248,113,113,0.25)' },
};

const BLANK_LEAD = {
  first_name: '', last_name: '', email: '', phone: '',
  job_title: '', company_name: '', company_industry: '',
  company_size: '', company_location: '', linkedin_url: '',
};

// --------------------------------------------------------------------------
// Export helpers
// --------------------------------------------------------------------------
const EXPORT_COLUMNS = [
  { key: 'full_name',          label: 'Name' },
  { key: 'email',              label: 'Email' },
  { key: 'phone',              label: 'Phone' },
  { key: 'job_title',          label: 'Job Title' },
  { key: 'company_name',       label: 'Company' },
  { key: 'company_industry',   label: 'Industry' },
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
  const rows = leads.map(l =>
    Object.fromEntries(EXPORT_COLUMNS.map(c => [c.label, l[c.key] ?? '']))
  );
  const ws = XLSX.utils.json_to_sheet(rows);

  // Column widths
  ws['!cols'] = EXPORT_COLUMNS.map(c => ({ wch: Math.max(c.label.length + 2, 16) }));

  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, 'Leads');
  XLSX.writeFile(wb, `${filename}.xlsx`);
}

async function exportToPdf(leads, filename = 'leads') {
  const { default: jsPDF } = await import('jspdf');
  const { default: autoTable } = await import('jspdf-autotable');

  const doc = new jsPDF({ orientation: 'landscape', unit: 'mm', format: 'a4' });

  // White background for whole page
  doc.setFillColor(255, 255, 255);
  doc.rect(0, 0, 297, 210, 'F');

  // Top accent bar
  doc.setFillColor(124, 58, 237);   // purple
  doc.rect(0, 0, 297, 10, 'F');

  // Title
  doc.setTextColor(30, 30, 30);
  doc.setFontSize(16);
  doc.setFont('helvetica', 'bold');
  doc.text('SDR Leads Export', 14, 20);

  // Sub-info line
  doc.setFontSize(8.5);
  doc.setFont('helvetica', 'normal');
  doc.setTextColor(100, 100, 100);
  doc.text(
    `Generated: ${new Date().toLocaleString()}   |   Total leads: ${leads.length}`,
    14, 27
  );

  // Thin separator line
  doc.setDrawColor(200, 200, 200);
  doc.setLineWidth(0.3);
  doc.line(14, 30, 283, 30);

  const columns = EXPORT_COLUMNS.slice(0, 10); // 10 cols fit well on landscape A4

  autoTable(doc, {
    startY: 34,
    head: [columns.map(c => c.label)],
    body: leads.map(l =>
      columns.map(c => {
        const v = l[c.key];
        return v === null || v === undefined || v === '' ? '—' : String(v);
      })
    ),
    styles: {
      fontSize: 8,
      cellPadding: { top: 3, bottom: 3, left: 4, right: 4 },
      textColor: [30, 30, 30],
      fillColor: [255, 255, 255],
      lineColor: [220, 220, 220],
      lineWidth: 0.25,
      overflow: 'linebreak',
    },
    headStyles: {
      fillColor: [124, 58, 237],   // purple header
      textColor: [255, 255, 255],
      fontStyle: 'bold',
      fontSize: 8.5,
      halign: 'left',
    },
    alternateRowStyles: {
      fillColor: [248, 245, 255],  // very light lavender stripe
    },
    columnStyles: {
      0: { cellWidth: 36 },   // Name
      1: { cellWidth: 44 },   // Email
      2: { cellWidth: 24 },   // Phone
      3: { cellWidth: 36 },   // Job Title
      4: { cellWidth: 28 },   // Company
      5: { cellWidth: 22 },   // Industry
      6: { cellWidth: 18 },   // Company Size
      7: { cellWidth: 22 },   // Location
      8: { cellWidth: 14 },   // Score
      9: { cellWidth: 18 },   // Temperature
    },
    margin: { left: 14, right: 14 },
    didDrawPage: (data) => {
      // Footer on every page
      const pageCount = doc.internal.getNumberOfPages();
      const currentPage = data.pageNumber;
      doc.setFontSize(7.5);
      doc.setTextColor(160, 160, 160);
      doc.text(
        `Page ${currentPage} of ${pageCount}  •  AI SDR Agent`,
        14,
        doc.internal.pageSize.height - 6
      );
    },
  });

  doc.save(`${filename}.pdf`);
}

// --------------------------------------------------------------------------
// Custom Filter Dropdown
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
          background: value ? `${selected?.color}15` : 'rgba(255,255,255,0.04)',
          border: `1px solid ${value ? selected?.color + '60' : '#2d1f4a'}`,
          color: value ? selected?.color : '#9ca3af',
          fontSize: 13, fontWeight: value ? 600 : 400,
          transition: 'all 0.15s', whiteSpace: 'nowrap',
          minWidth: fullWidth ? 'auto' : 120,
          width: fullWidth ? '100%' : 'auto',
        }}
      >
        {LabelIcon && <LabelIcon size={13} style={{ color: value ? selected?.color : '#6b7280' }} />}
        {value && selected?.dot && (
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: selected.color, flexShrink: 0, display: 'inline-block' }} />
        )}
        <span style={{ flex: 1, textAlign: 'left' }}>
          {value ? selected?.label : label}
        </span>
        <ChevronDown size={12} style={{ color: '#6b7280', transform: open ? 'rotate(180deg)' : 'none', transition: '0.15s', flexShrink: 0 }} />
      </button>

      {open && (
        <div style={{
          position: 'absolute', top: 'calc(100% + 6px)', left: 0, zIndex: 50,
          background: 'linear-gradient(135deg,#0f0a1f,#140830)',
          border: '1px solid #2d1f4a', borderRadius: 11,
          boxShadow: '0 12px 32px rgba(0,0,0,0.5)',
          minWidth: '100%', width: 'max-content', overflow: 'hidden',
          animation: 'fadeDown 0.12s ease',
        }}>
          {options.map((opt, idx) => {
            const isSelected = opt.key === value;
            return (
              <button
                key={opt.key}
                onClick={() => { onChange(opt.key); setOpen(false); }}
                style={{
                  display: 'flex', alignItems: 'center', gap: 10,
                  width: '100%', padding: '9px 14px', border: 'none', cursor: 'pointer',
                  background: isSelected ? `${opt.color}18` : 'transparent',
                  borderBottom: idx < options.length - 1 ? '1px solid rgba(255,255,255,0.04)' : 'none',
                  transition: 'background 0.1s',
                }}
                onMouseEnter={e => { if (!isSelected) e.currentTarget.style.background = 'rgba(255,255,255,0.05)'; }}
                onMouseLeave={e => { if (!isSelected) e.currentTarget.style.background = 'transparent'; }}
              >
                <span style={{
                  width: 10, height: 10, borderRadius: '50%', flexShrink: 0,
                  background: opt.key ? opt.color : 'transparent',
                  border: opt.key ? `2px solid ${opt.color}` : '2px solid #2d1f4a',
                }} />
                {opt.Icon && <opt.Icon size={13} style={{ color: opt.color, flexShrink: 0 }} />}
                <span style={{
                  flex: 1, textAlign: 'left', fontSize: 13,
                  color: isSelected ? opt.color : opt.key ? '#d1d5db' : '#6b7280',
                  fontWeight: isSelected ? 600 : 400,
                }}>
                  {opt.label}
                </span>
                {isSelected && (
                  <CheckCircle size={13} style={{ color: opt.color, flexShrink: 0 }} />
                )}
              </button>
            );
          })}
        </div>
      )}
      <style>{`@keyframes fadeDown{from{opacity:0;transform:translateY(-6px)}to{opacity:1;transform:translateY(0)}}`}</style>
    </div>
  );
};

// --------------------------------------------------------------------------
// Export Dropdown
// --------------------------------------------------------------------------
const ExportDropdown = ({ leads, selectedLeads, allLeadsOnPage }) => {
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

  const exportTarget = selectedLeads.size > 0
    ? allLeadsOnPage.filter(l => selectedLeads.has(l.id))
    : allLeadsOnPage;

  const label = selectedLeads.size > 0
    ? `Export ${selectedLeads.size} selected`
    : `Export ${allLeadsOnPage.length} leads`;

  const doExport = async (format) => {
    setExporting(format);
    setOpen(false);
    try {
      const ts = new Date().toISOString().slice(0, 10);
      const filename = `sdr-leads-${ts}`;
      if (format === 'excel') await exportToExcel(exportTarget, filename);
      else await exportToPdf(exportTarget, filename);
      toast({ title: `Exported ${exportTarget.length} leads as ${format.toUpperCase()}` });
    } catch (e) {
      toast({ title: 'Export failed', description: e.message, variant: 'destructive' });
    } finally { setExporting(null); }
  };

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button
        onClick={() => setOpen(v => !v)}
        disabled={exportTarget.length === 0 || !!exporting}
        style={{
          display: 'flex', alignItems: 'center', gap: 7,
          padding: '7px 14px', borderRadius: 9, cursor: exportTarget.length === 0 ? 'not-allowed' : 'pointer',
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
        <div style={{
          position: 'absolute', top: 'calc(100% + 6px)', right: 0, zIndex: 60,
          background: 'linear-gradient(135deg,#0f0a1f,#140830)',
          border: '1px solid #2d1f4a', borderRadius: 11,
          boxShadow: '0 12px 32px rgba(0,0,0,0.5)',
          minWidth: 190, overflow: 'hidden',
          animation: 'fadeDown 0.12s ease',
        }}>
          {[
            { key: 'excel', Icon: FileSpreadsheet, label: 'Export as Excel (.xlsx)', color: '#10b981' },
            { key: 'pdf',   Icon: FileText,        label: 'Export as PDF',           color: '#f43f5e' },
          ].map((opt, idx) => (
            <button
              key={opt.key}
              onClick={() => doExport(opt.key)}
              style={{
                display: 'flex', alignItems: 'center', gap: 10,
                width: '100%', padding: '11px 16px', border: 'none', cursor: 'pointer',
                background: 'transparent',
                borderBottom: idx === 0 ? '1px solid rgba(255,255,255,0.04)' : 'none',
                transition: 'background 0.1s',
              }}
              onMouseEnter={e => { e.currentTarget.style.background = `${opt.color}12`; }}
              onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; }}
            >
              <opt.Icon size={15} style={{ color: opt.color, flexShrink: 0 }} />
              <span style={{ color: '#d1d5db', fontSize: 13 }}>{opt.label}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

// --------------------------------------------------------------------------
// Pagination button style helper
// --------------------------------------------------------------------------
const pgBtn = (disabled, active = false) => ({
  minWidth: 32, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center',
  borderRadius: 7, fontSize: 13, fontWeight: active ? 700 : 400, cursor: disabled ? 'not-allowed' : 'pointer',
  border: `1px solid ${active ? '#a855f7' : 'rgba(255,255,255,0.08)'}`,
  background: active ? 'rgba(168,85,247,0.18)' : 'rgba(255,255,255,0.03)',
  color: disabled ? '#2d1f4a' : active ? '#c084fc' : '#9ca3af',
  opacity: disabled ? 0.5 : 1, transition: 'all 0.15s',
  padding: '0 8px',
});

// --------------------------------------------------------------------------
// Micro-components
// --------------------------------------------------------------------------
const ScoreBar = ({ label, value, max }) => (
  <div style={{ marginBottom: 8 }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
      <span style={{ fontSize: 12, color: '#9ca3af' }}>{label}</span>
      <span style={{ fontSize: 12, color: '#e2d9f3', fontWeight: 600 }}>{value}/{max}</span>
    </div>
    <div style={{ height: 6, borderRadius: 3, background: 'rgba(255,255,255,0.08)' }}>
      <div style={{
        height: '100%', borderRadius: 3, width: `${(value / max) * 100}%`,
        background: value / max >= 0.7 ? '#f43f5e' : value / max >= 0.4 ? '#f59e0b' : '#60a5fa',
        transition: 'width 0.4s ease',
      }} />
    </div>
  </div>
);

const cardStyle = {
  background: 'linear-gradient(135deg, rgba(15,10,31,0.95) 0%, rgba(20,8,40,0.95) 100%)',
  border: '1px solid #2d1f4a', borderRadius: 12,
};

const inputStyle = {
  background: 'rgba(30,10,50,0.6)', border: '1px solid #2d1f4a',
  borderRadius: 8, padding: '8px 12px', color: '#e2d9f3',
  outline: 'none', fontSize: 14, width: '100%', boxSizing: 'border-box',
};

// --------------------------------------------------------------------------
// ICP Profile Panel
// --------------------------------------------------------------------------
const BLANK_ICP = { name: 'Default ICP', industries: '', job_titles: '', locations: '', keywords: '', company_size_min: '', company_size_max: '' };

const ICPProfilePanel = ({ onSaved }) => {
  const { toast } = useToast();
  const [open, setOpen] = useState(false);
  const [icp, setIcp] = useState(null);
  const [form, setForm] = useState(BLANK_ICP);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getIcpProfile().then(res => {
      const data = res?.data?.data || res?.data || null;
      if (data) { setIcp(data); setForm({ name: data.name || '', industries: (data.industries || []).join(', '), job_titles: (data.job_titles || []).join(', '), locations: (data.locations || []).join(', '), keywords: (data.keywords || []).join(', '), company_size_min: data.company_size_min || '', company_size_max: data.company_size_max || '' }); }
    }).catch(() => {});
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      const toArr = v => v.split(',').map(s => s.trim()).filter(Boolean);
      await saveIcpProfile({ name: form.name, industries: toArr(form.industries), job_titles: toArr(form.job_titles), locations: toArr(form.locations), keywords: toArr(form.keywords), company_size_min: form.company_size_min ? parseInt(form.company_size_min) : null, company_size_max: form.company_size_max ? parseInt(form.company_size_max) : null });
      toast({ title: 'ICP Profile saved!' });
      const res = await getIcpProfile();
      setIcp(res?.data?.data || res?.data || null);
      setOpen(false);
      onSaved?.();
    } catch (e) { toast({ title: 'Save failed', description: e.message, variant: 'destructive' }); }
    finally { setSaving(false); }
  };

  return (
    <div style={{ ...cardStyle, padding: '14px 18px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Brain size={16} color="#a855f7" />
          <span style={{ color: '#e2d9f3', fontWeight: 600, fontSize: 14 }}>ICP Profile</span>
          {icp ? (
            <span style={{ color: '#10b981', fontSize: 12, padding: '2px 8px', borderRadius: 10, background: 'rgba(16,185,129,0.1)', border: '1px solid rgba(16,185,129,0.2)' }}>
              {icp.name}
            </span>
          ) : (
            <span style={{ color: '#f59e0b', fontSize: 12 }}>Not set up yet</span>
          )}
        </div>
        <button onClick={() => setOpen(!open)} style={{ background: 'rgba(168,85,247,0.1)', border: '1px solid rgba(168,85,247,0.3)', borderRadius: 8, padding: '5px 12px', color: '#a855f7', cursor: 'pointer', fontSize: 13, display: 'flex', alignItems: 'center', gap: 5 }}>
          <ChevronDown size={13} style={{ transform: open ? 'rotate(180deg)' : 'none', transition: '0.2s' }} />
          {icp ? 'Edit' : 'Setup'}
        </button>
      </div>

      {icp && !open && (
        <div style={{ marginTop: 10, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {[...(icp.industries||[]), ...(icp.job_titles||[])].slice(0,6).map(t => (
            <span key={t} style={{ padding: '2px 8px', borderRadius: 10, fontSize: 11, background: 'rgba(168,85,247,0.1)', border: '1px solid rgba(168,85,247,0.2)', color: '#c4b5fd' }}>{t}</span>
          ))}
        </div>
      )}

      {open && (
        <div style={{ marginTop: 14, display: 'flex', flexDirection: 'column', gap: 12 }}>
          {[
            { k: 'name',       l: 'Profile Name',          p: 'Default ICP' },
            { k: 'industries', l: 'Industries (comma-sep)', p: 'SaaS, FinTech, E-commerce' },
            { k: 'job_titles', l: 'Job Titles (comma-sep)', p: 'CEO, VP Sales, CTO' },
            { k: 'locations',  l: 'Locations (comma-sep)',  p: 'United States, UK' },
            { k: 'keywords',   l: 'Keywords (comma-sep)',   p: 'B2B, startup, Series A' },
          ].map(({ k, l, p }) => (
            <div key={k}>
              <label style={{ color: '#9ca3af', fontSize: 12, display: 'block', marginBottom: 4 }}>{l}</label>
              <input style={inputStyle} placeholder={p} value={form[k]} onChange={e => setForm(f => ({ ...f, [k]: e.target.value }))} />
            </div>
          ))}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            {[{ k: 'company_size_min', l: 'Min Employees', p: '10' }, { k: 'company_size_max', l: 'Max Employees', p: '500' }].map(({ k, l, p }) => (
              <div key={k}>
                <label style={{ color: '#9ca3af', fontSize: 12, display: 'block', marginBottom: 4 }}>{l}</label>
                <input style={inputStyle} type="number" placeholder={p} value={form[k]} onChange={e => setForm(f => ({ ...f, [k]: e.target.value }))} />
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button onClick={() => setOpen(false)} style={{ background: 'none', border: '1px solid #2d1f4a', borderRadius: 8, padding: '7px 16px', color: '#9ca3af', cursor: 'pointer', fontSize: 13 }}>Cancel</button>
            <button onClick={handleSave} disabled={saving} style={{ background: 'linear-gradient(90deg,#7c3aed,#a855f7)', border: 'none', borderRadius: 8, padding: '7px 20px', color: '#fff', cursor: 'pointer', fontSize: 13, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}>
              {saving ? <Loader2 size={12} className="animate-spin" /> : null} Save ICP
            </button>
          </div>
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

// --------------------------------------------------------------------------
// Sort options
// --------------------------------------------------------------------------
const PAGE_SIZE_OPTIONS = [10, 25, 50, 100];

// --------------------------------------------------------------------------
// Main Component
// --------------------------------------------------------------------------
const SDRLeadsTab = () => {
  const { toast } = useToast();
  const fileInputRef = useRef(null);

  // Data
  const [leads, setLeads] = useState([]);
  const [stats, setStats] = useState({ total: 0, hot: 0, warm: 0, cold: 0, unscored: 0 });
  const [pagination, setPagination] = useState({ page: 1, page_size: 25, total_count: 0, total_pages: 1, has_next: false, has_prev: false });

  // UI
  const [loading, setLoading] = useState(true);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);
  const [selectedLead, setSelectedLead] = useState(null);
  const [newLead, setNewLead] = useState(BLANK_LEAD);
  const [addingLead, setAddingLead] = useState(false);
  const [qualifyingId, setQualifyingId] = useState(null);

  // Filters (raw — debounced for search)
  const [searchRaw, setSearchRaw] = useState('');
  const [filterTemp, setFilterTemp] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [filterSource, setFilterSource] = useState('');
  const [sortBy, setSortBy] = useState('score_desc');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

  const search = useDebounce(searchRaw, 450);

  // Bulk selection
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [showBulkDeleteConfirm, setShowBulkDeleteConfirm] = useState(false);

  // Generate leads modal
  const [showGenModal, setShowGenModal] = useState(false);
  const [genSource, setGenSource] = useState('apify');
  const [genCount, setGenCount] = useState(10);
  const [genIcpId, setGenIcpId] = useState('');
  const [showSetupGuide, setShowSetupGuide] = useState(null);
  const [copiedKey, setCopiedKey] = useState(null);
  const [icpProfiles, setIcpProfiles] = useState([]);
  const [generating, setGenerating] = useState(false);

  // ── Load ──────────────────────────────────────────────────────────────
  const loadLeads = useCallback(async (opts = {}) => {
    setLoading(true);
    try {
      const resp = await listLeads({
        search:      opts.search      ?? search,
        temperature: opts.temperature ?? filterTemp,
        status:      opts.status      ?? filterStatus,
        source:      opts.source      ?? filterSource,
        sort:        opts.sort        ?? sortBy,
        page:        opts.page        ?? page,
        page_size:   opts.page_size   ?? pageSize,
      });
      setLeads(resp?.data || []);
      setStats(resp?.stats || { total: 0, hot: 0, warm: 0, cold: 0, unscored: 0 });
      setPagination(resp?.pagination || { page: 1, page_size: pageSize, total_count: 0, total_pages: 1, has_next: false, has_prev: false });
      // Clear selection on data reload
      setSelectedIds(new Set());
    } catch (e) {
      console.error(e);
      toast({ title: 'Failed to load leads', description: e?.message, variant: 'destructive' });
    } finally { setLoading(false); }
  }, [search, filterTemp, filterStatus, filterSource, sortBy, page, pageSize, toast]);

  useEffect(() => { loadLeads(); }, []);

  useEffect(() => {
    setPage(1);
    loadLeads({ page: 1, search, temperature: filterTemp, status: filterStatus, source: filterSource, sort: sortBy, page_size: pageSize });
  }, [search, filterTemp, filterStatus, filterSource, sortBy, pageSize]);

  const goToPage = useCallback((p) => {
    setPage(p);
    loadLeads({ page: p });
  }, [loadLeads]);

  const activeFiltersCount = [filterTemp, filterStatus, filterSource].filter(Boolean).length;

  // ── Bulk selection helpers ─────────────────────────────────────────────
  const allPageIds = leads.map(l => l.id);
  const allSelected = allPageIds.length > 0 && allPageIds.every(id => selectedIds.has(id));
  const someSelected = allPageIds.some(id => selectedIds.has(id)) && !allSelected;

  const toggleSelectAll = () => {
    if (allSelected) {
      setSelectedIds(prev => { const n = new Set(prev); allPageIds.forEach(id => n.delete(id)); return n; });
    } else {
      setSelectedIds(prev => { const n = new Set(prev); allPageIds.forEach(id => n.add(id)); return n; });
    }
  };

  const toggleSelect = (id) => {
    setSelectedIds(prev => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });
  };

  // ── Bulk delete ───────────────────────────────────────────────────────
  const handleBulkDelete = async () => {
    setBulkDeleting(true);
    try {
      const ids = [...selectedIds];
      const resp = await bulkDeleteLeads(ids);
      toast({ title: `Deleted ${resp?.deleted ?? ids.length} lead(s)` });
      setShowBulkDeleteConfirm(false);
      setSelectedIds(new Set());
      loadLeads();
    } catch (e) {
      toast({ title: 'Bulk delete failed', description: e.message, variant: 'destructive' });
    } finally { setBulkDeleting(false); }
  };

  const openGenModal = async () => {
    try {
      const profiles = await listIcpProfiles();
      setIcpProfiles(profiles);
      if (profiles.length > 0) setGenIcpId(profiles.find(p => p.is_active)?.id || profiles[0].id);
    } catch (_) { setIcpProfiles([]); }
    setShowGenModal(true);
  };

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const resp = await researchLeads({ count: genCount, source: genSource, icp_id: genIcpId || undefined });
      const created = resp?.data?.leads_created ?? resp?.leads_created ?? '?';
      toast({ title: `${created} leads generated!`, description: `Source: ${genSource.toUpperCase()}` });
      setShowGenModal(false);
      setPage(1);
      loadLeads({ page: 1 });
    } catch (e) {
      toast({ title: 'Generate failed', description: e?.response?.data?.message || e.message, variant: 'destructive' });
    } finally { setGenerating(false); }
  };

  // ── Delete single ─────────────────────────────────────────────────────
  const handleDelete = async (lead) => {
    try {
      await deleteLead(lead.id);
      if (selectedLead?.id === lead.id) setSelectedLead(null);
      setSelectedIds(prev => { const n = new Set(prev); n.delete(lead.id); return n; });
      toast({ title: 'Lead removed' });
      loadLeads();
    } catch (e) {
      toast({ title: 'Delete failed', description: e.message, variant: 'destructive' });
    }
  };

  // ── Qualify ───────────────────────────────────────────────────────────
  const handleQualifyOne = async (lead) => {
    setQualifyingId(lead.id);
    try {
      const resp = await qualifyLead(lead.id);
      setLeads(prev => prev.map(l => l.id === lead.id ? resp.data : l));
      if (selectedLead?.id === lead.id) setSelectedLead(resp.data);
      toast({ title: `Score: ${resp.data.score}/100`, description: `${resp.data.temperature?.toUpperCase()} — ${lead.full_name}` });
    } catch (e) {
      toast({ title: 'Qualify failed', description: e.message, variant: 'destructive' });
    } finally { setQualifyingId(null); }
  };

  // ── Add manual ────────────────────────────────────────────────────────
  const handleAddLead = async () => {
    setAddingLead(true);
    try {
      await createLead({ ...newLead, company_size: newLead.company_size ? parseInt(newLead.company_size) : null });
      setShowAddModal(false);
      setNewLead(BLANK_LEAD);
      toast({ title: 'Lead added successfully' });
      setPage(1);
      loadLeads({ page: 1 });
    } catch (e) {
      toast({ title: 'Add failed', description: e.message, variant: 'destructive' });
    } finally { setAddingLead(false); }
  };

  // ── CSV import ────────────────────────────────────────────────────────
  const handleCsvImport = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const resp = await importLeadsFromCSV(file);
      toast({ title: `Imported ${resp.created} leads` });
      setPage(1);
      loadLeads({ page: 1 });
    } catch (e) {
      toast({ title: 'Import failed', description: e.message, variant: 'destructive' });
    }
    e.target.value = '';
  };

  // ── Checkbox icon helper ──────────────────────────────────────────────
  const CheckIcon = ({ checked, indeterminate, size = 16 }) => {
    if (indeterminate) return <MinusSquare size={size} style={{ color: '#a855f7' }} />;
    if (checked) return <CheckSquare size={size} style={{ color: '#a855f7' }} />;
    return <Square size={size} style={{ color: '#4b5563' }} />;
  };

  // ── Render ────────────────────────────────────────────────────────────
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

      {/* ICP Profile Panel */}
      <ICPProfilePanel onSaved={openGenModal} />

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
              <span style={{ color: '#9ca3af', fontSize: 12 }}>{label}</span>
            </div>
            <span style={{ color, fontSize: 26, fontWeight: 700 }}>{value}</span>
          </div>
        ))}
      </div>

      {/* Action bar */}
      <div style={{ ...cardStyle, padding: '14px 18px' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
          <Button onClick={() => setShowAddModal(true)} style={{
            background: 'linear-gradient(90deg,#f43f5e 0%,#a855f7 100%)',
            color: '#fff', border: 'none', borderRadius: 8, fontWeight: 600,
            display: 'flex', alignItems: 'center', gap: 6, padding: '8px 16px',
          }}>
            <Plus size={15} /> Add Lead
          </Button>

          <div style={{ width: 1, height: 28, background: '#2d1f4a' }} />

          <Button onClick={openGenModal} style={{
            background: 'linear-gradient(90deg,#7c3aed 0%,#a855f7 100%)',
            color: '#fff', border: 'none', borderRadius: 8, fontWeight: 600,
            display: 'flex', alignItems: 'center', gap: 6, padding: '8px 16px',
          }}>
            <Zap size={15} /> Generate Leads
          </Button>

          <div style={{ width: 1, height: 28, background: '#2d1f4a' }} />

          <Button onClick={() => fileInputRef.current?.click()} variant="outline" style={{
            border: '1px solid #2d1f4a', color: '#9ca3af', borderRadius: 8,
            display: 'flex', alignItems: 'center', gap: 6,
          }}>
            <Upload size={14} /> Import CSV
          </Button>
          <input ref={fileInputRef} type="file" accept=".csv" style={{ display: 'none' }} onChange={handleCsvImport} />

          {/* Export button — always visible */}
          <div style={{ marginLeft: 'auto' }}>
            <ExportDropdown leads={leads} selectedLeads={selectedIds} allLeadsOnPage={leads} />
          </div>
        </div>
      </div>

      {/* ── Bulk action bar (visible when leads are selected) ── */}
      {selectedIds.size > 0 && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap',
          padding: '12px 18px', borderRadius: 12,
          background: 'linear-gradient(90deg, rgba(168,85,247,0.08), rgba(99,102,241,0.08))',
          border: '1px solid rgba(168,85,247,0.3)',
          animation: 'fadeDown 0.15s ease',
        }}>
          <span style={{ color: '#c084fc', fontWeight: 700, fontSize: 14 }}>
            {selectedIds.size} lead{selectedIds.size > 1 ? 's' : ''} selected
          </span>

          <div style={{ width: 1, height: 20, background: '#2d1f4a' }} />

          {/* Bulk delete */}
          <button
            onClick={() => setShowBulkDeleteConfirm(true)}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '6px 14px', borderRadius: 8, cursor: 'pointer',
              background: 'rgba(244,63,94,0.1)', border: '1px solid rgba(244,63,94,0.3)',
              color: '#f87171', fontSize: 13, fontWeight: 600,
            }}
          >
            <Trash2 size={13} /> Delete {selectedIds.size} selected
          </button>

          {/* Deselect all */}
          <button
            onClick={() => setSelectedIds(new Set())}
            style={{
              display: 'flex', alignItems: 'center', gap: 5,
              padding: '6px 12px', borderRadius: 8, cursor: 'pointer',
              background: 'none', border: '1px solid #2d1f4a',
              color: '#6b7280', fontSize: 13,
            }}
          >
            <X size={12} /> Deselect all
          </button>
        </div>
      )}

      {/* ── Filter bar ── */}
      <div style={{ ...cardStyle, padding: '12px 16px' }}>

        {/* Top row: search + filter toggle + page size + refresh */}
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>

          {/* Search */}
          <div style={{ position: 'relative', flex: '1 1 200px', minWidth: 180 }}>
            <Search size={14} style={{ position: 'absolute', left: 11, top: '50%', transform: 'translateY(-50%)', color: '#6b7280', pointerEvents: 'none' }} />
            <input
              value={searchRaw}
              onChange={e => setSearchRaw(e.target.value)}
              placeholder="Search name, company, email…"
              style={{ ...inputStyle, paddingLeft: 34, paddingRight: searchRaw ? 32 : 12, border: '1px solid #2d1f4a', borderRadius: 9, fontSize: 13 }}
            />
            {searchRaw && (
              <button onClick={() => setSearchRaw('')} style={{ position: 'absolute', right: 9, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: '#6b7280', display: 'flex', padding: 0 }}>
                <X size={13} />
              </button>
            )}
          </div>

          {/* Filters toggle */}
          {(() => {
            const totalActive = activeFiltersCount + (sortBy !== 'score_desc' ? 1 : 0);
            return (
              <button
                onClick={() => setFiltersOpen(v => !v)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 7, padding: '7px 14px',
                  borderRadius: 9, cursor: 'pointer', whiteSpace: 'nowrap',
                  background: filtersOpen || totalActive > 0 ? 'rgba(168,85,247,0.12)' : 'rgba(255,255,255,0.04)',
                  border: `1px solid ${filtersOpen || totalActive > 0 ? 'rgba(168,85,247,0.5)' : '#2d1f4a'}`,
                  color: filtersOpen || totalActive > 0 ? '#c084fc' : '#9ca3af',
                  fontSize: 13, fontWeight: totalActive > 0 ? 600 : 400, transition: 'all 0.15s',
                }}
              >
                <SlidersHorizontal size={13} />
                Filters
                {totalActive > 0 && (
                  <span style={{ background: 'linear-gradient(135deg,#a855f7,#6366f1)', color: '#fff', borderRadius: '50%', width: 18, height: 18, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, fontWeight: 700 }}>
                    {totalActive}
                  </span>
                )}
                <ChevronDown size={11} style={{ color: '#6b7280', transform: filtersOpen ? 'rotate(180deg)' : 'none', transition: '0.15s', flexShrink: 0 }} />
              </button>
            );
          })()}

          {/* Page size */}
          <select
            value={pageSize}
            onChange={e => setPageSize(Number(e.target.value))}
            style={{ ...inputStyle, width: 'auto', padding: '7px 10px', fontSize: 13, border: '1px solid #2d1f4a', borderRadius: 9, cursor: 'pointer' }}
          >
            {PAGE_SIZE_OPTIONS.map(n => <option key={n} value={n}>{n} / page</option>)}
          </select>

          {/* Refresh */}
          <button onClick={() => loadLeads()} style={{ display: 'flex', alignItems: 'center', padding: '7px 10px', background: 'none', border: '1px solid #2d1f4a', borderRadius: 9, cursor: 'pointer', color: '#6b7280' }} title="Refresh">
            <RefreshCw size={14} style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }} />
          </button>
        </div>

        {/* ── Collapsible filter panel ── */}
        {filtersOpen && (
          <div style={{
            marginTop: 10,
            padding: '16px 16px 14px',
            background: 'linear-gradient(135deg,rgba(10,4,28,0.9),rgba(16,6,38,0.95))',
            border: '1px solid rgba(168,85,247,0.2)',
            borderRadius: 11,
            boxShadow: 'inset 0 1px 0 rgba(168,85,247,0.06), 0 4px 20px rgba(0,0,0,0.3)',
          }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12 }}>

              <div>
                <div style={{ color: '#6b7280', fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', marginBottom: 7, display: 'flex', alignItems: 'center', gap: 5 }}>
                  <Thermometer size={11} style={{ color: '#f59e0b' }} /> TEMPERATURE
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
                  <ArrowUpDown size={11} style={{ color: '#a78bfa' }} /> SORT BY
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

            {/* Panel footer */}
            {(() => {
              const totalActive = activeFiltersCount + (sortBy !== 'score_desc' ? 1 : 0);
              return totalActive > 0 ? (
                <div style={{ marginTop: 12, paddingTop: 10, borderTop: '1px solid rgba(255,255,255,0.05)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <button
                    onClick={() => { setFilterTemp(''); setFilterStatus(''); setFilterSource(''); setSortBy('score_desc'); }}
                    style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '5px 12px', borderRadius: 8, background: 'rgba(244,63,94,0.08)', border: '1px solid rgba(244,63,94,0.25)', color: '#f87171', fontSize: 12, cursor: 'pointer' }}
                  >
                    <X size={11} /> Clear all
                  </button>
                  <span style={{ color: '#6b7280', fontSize: 12 }}>{totalActive} active</span>
                </div>
              ) : null;
            })()}
          </div>
        )}

        {/* Result summary */}
        <div style={{ marginTop: 8, fontSize: 12, color: '#4b5563', display: 'flex', alignItems: 'center', gap: 8 }}>
          {loading
            ? <span style={{ color: '#a78bfa' }}>Loading…</span>
            : <>
                <span>
                  Showing <strong style={{ color: '#e2d9f3' }}>
                    {pagination.total_count === 0 ? 0 : ((pagination.page - 1) * pagination.page_size) + 1}–{Math.min(pagination.page * pagination.page_size, pagination.total_count)}
                  </strong> of <strong style={{ color: '#e2d9f3' }}>{pagination.total_count.toLocaleString()}</strong> leads
                </span>
                {(searchRaw || activeFiltersCount > 0) && (
                  <span style={{ padding: '1px 8px', borderRadius: 10, background: 'rgba(167,139,250,0.12)', border: '1px solid rgba(167,139,250,0.25)', color: '#a78bfa', fontSize: 11 }}>
                    filtered
                  </span>
                )}
              </>
          }
        </div>
      </div>

      <style>{`@keyframes spin{from{transform:rotate(0)}to{transform:rotate(360deg)}}`}</style>

      {/* Lead table */}
      <div style={{ ...cardStyle, overflow: 'hidden' }}>
        {loading ? (
          <div style={{ textAlign: 'center', padding: 60, color: '#6b7280' }}>
            <Loader2 size={28} className="animate-spin" style={{ margin: '0 auto 12px', color: '#a855f7' }} />
            <p>Loading leads…</p>
          </div>
        ) : leads.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 60 }}>
            <Users size={40} style={{ color: '#1e0f38', margin: '0 auto 12px' }} />
            <p style={{ color: '#6b7280', marginBottom: 6 }}>No leads yet.</p>
            <p style={{ color: '#4b5563', fontSize: 13 }}>Add a lead manually or import a CSV file to get started.</p>
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #1e0f38' }}>
                {/* Checkbox header */}
                <th style={{ padding: '12px 14px', width: 40 }}>
                  <button
                    onClick={toggleSelectAll}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', padding: 0 }}
                    title={allSelected ? 'Deselect all' : 'Select all on this page'}
                  >
                    <CheckIcon checked={allSelected} indeterminate={someSelected} />
                  </button>
                </th>
                {['Name & Company', 'Title', 'Score', 'Temperature', 'Status', 'Location', 'Source', 'Actions'].map(h => (
                  <th key={h} style={{ padding: '12px 16px', textAlign: 'left', color: '#4b5563', fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {leads.map(lead => {
                const tcfg = TEMP_CONFIG[lead.temperature];
                const TIcon = tcfg?.icon;
                const isChecked = selectedIds.has(lead.id);
                return (
                  <tr key={lead.id}
                    style={{ borderBottom: '1px solid rgba(45,31,74,0.4)', cursor: 'pointer', transition: 'background 0.15s', background: isChecked ? 'rgba(168,85,247,0.06)' : 'transparent' }}
                    onMouseEnter={e => { if (!isChecked) e.currentTarget.style.background = 'rgba(168,85,247,0.04)'; }}
                    onMouseLeave={e => { e.currentTarget.style.background = isChecked ? 'rgba(168,85,247,0.06)' : 'transparent'; }}
                  >
                    {/* Checkbox cell */}
                    <td style={{ padding: '13px 14px' }} onClick={e => { e.stopPropagation(); toggleSelect(lead.id); }}>
                      <button style={{ background: 'none', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', padding: 0 }}>
                        <CheckIcon checked={isChecked} />
                      </button>
                    </td>
                    <td style={{ padding: '13px 16px' }} onClick={() => setSelectedLead(lead)}>
                      <div style={{ fontWeight: 600, color: '#e2d9f3', fontSize: 14 }}>{lead.full_name}</div>
                      <div style={{ color: '#6b7280', fontSize: 12, marginTop: 2 }}>{lead.company_name}</div>
                    </td>
                    <td style={{ padding: '13px 16px' }} onClick={() => setSelectedLead(lead)}>
                      <span style={{ color: '#9ca3af', fontSize: 13 }}>{lead.job_title || '—'}</span>
                    </td>
                    <td style={{ padding: '13px 16px' }} onClick={() => setSelectedLead(lead)}>
                      {lead.score != null ? (
                        <span style={{
                          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                          width: 40, height: 40, borderRadius: '50%',
                          background: `${SCORE_COLOR(lead.score)}18`,
                          border: `2px solid ${SCORE_COLOR(lead.score)}55`,
                          color: SCORE_COLOR(lead.score), fontWeight: 700, fontSize: 14,
                        }}>{lead.score}</span>
                      ) : <span style={{ color: '#2d1f4a', fontSize: 12 }}>—</span>}
                    </td>
                    <td style={{ padding: '13px 16px' }} onClick={() => setSelectedLead(lead)}>
                      {tcfg ? (
                        <span style={{
                          display: 'inline-flex', alignItems: 'center', gap: 5,
                          padding: '3px 10px', borderRadius: 12, fontSize: 12, fontWeight: 600,
                          background: tcfg.bg, border: `1px solid ${tcfg.border}`, color: tcfg.color,
                        }}>
                          <TIcon size={11} /> {tcfg.label}
                        </span>
                      ) : <span style={{ color: '#2d1f4a', fontSize: 12 }}>Unscored</span>}
                    </td>
                    <td style={{ padding: '13px 16px' }} onClick={() => setSelectedLead(lead)}>
                      {(() => {
                        const sc = LEAD_STATUS_CONFIG[lead.status];
                        return sc ? (
                          <span style={{
                            padding: '3px 9px', borderRadius: 10, fontSize: 11, fontWeight: 600,
                            background: sc.bg, border: `1px solid ${sc.border}`, color: sc.color,
                            whiteSpace: 'nowrap',
                          }}>{sc.label}</span>
                        ) : <span style={{ color: '#4b5563', fontSize: 12 }}>—</span>;
                      })()}
                    </td>
                    <td style={{ padding: '13px 16px' }} onClick={() => setSelectedLead(lead)}>
                      <span style={{ color: '#6b7280', fontSize: 13 }}>{lead.company_location || '—'}</span>
                    </td>
                    <td style={{ padding: '13px 16px' }} onClick={() => setSelectedLead(lead)}>
                      <span style={{ padding: '2px 8px', borderRadius: 8, fontSize: 11, background: 'rgba(255,255,255,0.05)', color: '#6b7280' }}>
                        {SOURCE_LABELS[lead.source] || lead.source}
                      </span>
                    </td>
                    <td style={{ padding: '13px 16px' }} onClick={e => e.stopPropagation()}>
                      <div style={{ display: 'flex', gap: 6 }}>
                        <button onClick={() => handleQualifyOne(lead)} disabled={qualifyingId === lead.id} title="AI Score" style={{
                          background: 'rgba(168,85,247,0.12)', border: '1px solid rgba(168,85,247,0.3)',
                          borderRadius: 6, padding: '5px 8px', cursor: 'pointer', color: '#c084fc',
                        }}>
                          {qualifyingId === lead.id ? <Loader2 size={12} className="animate-spin" /> : <Brain size={12} />}
                        </button>
                        <button onClick={() => handleDelete(lead)} title="Delete" style={{
                          background: 'rgba(244,63,94,0.08)', border: '1px solid rgba(244,63,94,0.2)',
                          borderRadius: 6, padding: '5px 8px', cursor: 'pointer', color: '#f87171',
                        }}>
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

      {/* ── Pagination footer ── */}
      {pagination.total_pages > 1 && (
        <div style={{ display:'flex',alignItems:'center',justifyContent:'space-between',flexWrap:'wrap',gap:10,...cardStyle,padding:'12px 18px' }}>
          <span style={{ fontSize:13,color:'#6b7280' }}>
            Page <strong style={{ color:'#e2d9f3' }}>{pagination.page}</strong> of <strong style={{ color:'#e2d9f3' }}>{pagination.total_pages}</strong>
            <span style={{ color:'#4b5563',marginLeft:8 }}>({pagination.total_count.toLocaleString()} total)</span>
          </span>

          <div style={{ display:'flex',gap:4,alignItems:'center' }}>
            <button onClick={() => goToPage(1)} disabled={!pagination.has_prev} style={pgBtn(!pagination.has_prev)} title="First page">
              <ChevronsLeft size={14} />
            </button>
            <button onClick={() => goToPage(pagination.page - 1)} disabled={!pagination.has_prev} style={pgBtn(!pagination.has_prev)} title="Previous">
              <ChevronLeft size={14} />
            </button>

            {Array.from({ length: pagination.total_pages }, (_, i) => i + 1)
              .filter(p => p === 1 || p === pagination.total_pages || Math.abs(p - pagination.page) <= 2)
              .reduce((acc, p, idx, arr) => {
                if (idx > 0 && p - arr[idx - 1] > 1) acc.push('…');
                acc.push(p);
                return acc;
              }, [])
              .map((p, i) =>
                p === '…'
                  ? <span key={`ellipsis-${i}`} style={{ color:'#4b5563',padding:'0 4px',fontSize:13 }}>…</span>
                  : <button key={p} onClick={() => goToPage(p)} style={pgBtn(false, p === pagination.page)}>
                      {p}
                    </button>
              )}

            <button onClick={() => goToPage(pagination.page + 1)} disabled={!pagination.has_next} style={pgBtn(!pagination.has_next)} title="Next">
              <ChevronRight size={14} />
            </button>
            <button onClick={() => goToPage(pagination.total_pages)} disabled={!pagination.has_next} style={pgBtn(!pagination.has_next)} title="Last page">
              <ChevronsRight size={14} />
            </button>
          </div>
        </div>
      )}

      {/* Lead detail slide-over */}
      {selectedLead && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 50, display: 'flex', justifyContent: 'flex-end' }}>
          <div style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.55)' }} onClick={() => setSelectedLead(null)} />
          <div style={{
            position: 'relative', width: 480, maxWidth: '95vw', height: '100%',
            background: 'linear-gradient(160deg,#0f0a1f 0%,#14082a 100%)',
            borderLeft: '1px solid #2d1f4a', overflowY: 'auto', padding: 24,
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 }}>
              <div>
                <h2 style={{ color: '#e2d9f3', fontSize: 18, fontWeight: 700, margin: 0 }}>{selectedLead.full_name}</h2>
                <p style={{ color: '#9ca3af', fontSize: 14, marginTop: 4 }}>
                  {selectedLead.job_title}{selectedLead.company_name ? ` @ ${selectedLead.company_name}` : ''}
                </p>
              </div>
              <button onClick={() => setSelectedLead(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#6b7280' }}>
                <X size={20} />
              </button>
            </div>

            {selectedLead.score != null && (
              <div style={{
                display: 'flex', gap: 14, alignItems: 'center', marginBottom: 20,
                padding: '14px 16px', borderRadius: 10,
                background: `${SCORE_COLOR(selectedLead.score)}10`,
                border: `1px solid ${SCORE_COLOR(selectedLead.score)}30`,
              }}>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: 30, fontWeight: 800, color: SCORE_COLOR(selectedLead.score) }}>{selectedLead.score}</div>
                  <div style={{ fontSize: 11, color: '#6b7280' }}>/ 100</div>
                </div>
                <div style={{ flex: 1 }}>
                  {selectedLead.temperature && (() => {
                    const cfg = TEMP_CONFIG[selectedLead.temperature];
                    const Icon = cfg.icon;
                    return (
                      <span style={{
                        display: 'inline-flex', alignItems: 'center', gap: 6, padding: '4px 12px',
                        borderRadius: 20, marginBottom: 8, background: cfg.bg,
                        border: `1px solid ${cfg.border}`, color: cfg.color, fontWeight: 700, fontSize: 13,
                      }}>
                        <Icon size={13} /> {cfg.label} Lead
                      </span>
                    );
                  })()}
                  <p style={{ color: '#9ca3af', fontSize: 13, lineHeight: 1.5, margin: 0 }}>
                    {selectedLead.qualification_reasoning || 'No reasoning available.'}
                  </p>
                </div>
              </div>
            )}

            {selectedLead.score_breakdown && Object.keys(selectedLead.score_breakdown).length > 0 && (
              <div style={{ marginBottom: 20 }}>
                <h4 style={{ color: '#4b5563', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>Score Breakdown</h4>
                <ScoreBar label="Industry Match"  value={selectedLead.score_breakdown.industry       || 0} max={30} />
                <ScoreBar label="Job Title Match" value={selectedLead.score_breakdown.job_title      || 0} max={30} />
                <ScoreBar label="Company Size"    value={selectedLead.score_breakdown.company_size   || 0} max={20} />
                <ScoreBar label="Location"        value={selectedLead.score_breakdown.location       || 0} max={10} />
                <ScoreBar label="Buying Signals"  value={selectedLead.score_breakdown.buying_signals || 0} max={10} />
              </div>
            )}

            <div style={{ marginBottom: 20 }}>
              <h4 style={{ color: '#4b5563', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>Contact</h4>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {selectedLead.email && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Mail size={13} style={{ color: '#6b7280' }} />
                    <a href={`mailto:${selectedLead.email}`} style={{ color: '#c084fc', fontSize: 13 }}>{selectedLead.email}</a>
                  </div>
                )}
                {selectedLead.phone && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Phone size={13} style={{ color: '#6b7280' }} />
                    <span style={{ color: '#e2d9f3', fontSize: 13 }}>{selectedLead.phone}</span>
                  </div>
                )}
                {selectedLead.linkedin_url && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Linkedin size={13} style={{ color: '#6b7280' }} />
                    <a href={selectedLead.linkedin_url} target="_blank" rel="noreferrer" style={{ color: '#60a5fa', fontSize: 13 }}>
                      LinkedIn <ExternalLink size={10} style={{ display: 'inline', marginLeft: 2 }} />
                    </a>
                  </div>
                )}
              </div>
            </div>

            <div style={{ marginBottom: 20 }}>
              <h4 style={{ color: '#4b5563', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>Company</h4>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {selectedLead.company_industry && <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}><Briefcase size={13} style={{ color: '#6b7280' }} /><span style={{ color: '#e2d9f3', fontSize: 13 }}>{selectedLead.company_industry}</span></div>}
                {selectedLead.company_size && <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}><Users size={13} style={{ color: '#6b7280' }} /><span style={{ color: '#e2d9f3', fontSize: 13 }}>{selectedLead.company_size.toLocaleString()} employees</span></div>}
                {selectedLead.company_location && <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}><MapPin size={13} style={{ color: '#6b7280' }} /><span style={{ color: '#e2d9f3', fontSize: 13 }}>{selectedLead.company_location}</span></div>}
                {selectedLead.company_website && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Globe size={13} style={{ color: '#6b7280' }} />
                    <a href={selectedLead.company_website} target="_blank" rel="noreferrer" style={{ color: '#60a5fa', fontSize: 13 }}>
                      {selectedLead.company_website} <ExternalLink size={10} style={{ display: 'inline' }} />
                    </a>
                  </div>
                )}
              </div>
            </div>

            {selectedLead.company_technologies?.length > 0 && (
              <div style={{ marginBottom: 20 }}>
                <h4 style={{ color: '#4b5563', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>Technologies</h4>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {selectedLead.company_technologies.map(t => (
                    <span key={t} style={{ padding: '3px 10px', borderRadius: 10, fontSize: 12, background: 'rgba(96,165,250,0.1)', border: '1px solid rgba(96,165,250,0.25)', color: '#93c5fd' }}>{t}</span>
                  ))}
                </div>
              </div>
            )}

            {selectedLead.buying_signals?.length > 0 && (
              <div style={{ marginBottom: 20 }}>
                <h4 style={{ color: '#4b5563', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>Buying Signals</h4>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {selectedLead.buying_signals.map((s, i) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                      <TrendingUp size={12} style={{ color: '#10b981', marginTop: 2, flexShrink: 0 }} />
                      <span style={{ color: '#d1fae5', fontSize: 13 }}>{s}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div style={{ display: 'flex', gap: 8, paddingTop: 12, borderTop: '1px solid #1e0f38' }}>
              <Button onClick={() => handleQualifyOne(selectedLead)} disabled={qualifyingId === selectedLead.id} style={{
                flex: 1, background: 'linear-gradient(90deg,#7c3aed,#a855f7)',
                color: '#fff', border: 'none', borderRadius: 8, fontWeight: 600,
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
              }}>
                {qualifyingId === selectedLead.id ? <Loader2 size={13} className="animate-spin" /> : <Brain size={13} />}
                {selectedLead.score != null ? 'Re-score with AI' : 'Score with AI'}
              </Button>
              <Button onClick={() => handleDelete(selectedLead)} variant="outline" style={{ border: '1px solid rgba(244,63,94,0.4)', color: '#f87171', borderRadius: 8 }}>
                <Trash2 size={13} />
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* ── Bulk Delete Confirmation Dialog ── */}
      <Dialog open={showBulkDeleteConfirm} onOpenChange={setShowBulkDeleteConfirm}>
        <DialogContent style={{ background: 'linear-gradient(135deg,#0f0a1f 0%,#14082a 100%)', border: '1px solid #2d1f4a', color: '#e2d9f3', maxWidth: 420 }}>
          <DialogHeader>
            <DialogTitle style={{ color: '#f87171', display: 'flex', alignItems: 'center', gap: 8 }}>
              <Trash2 size={18} /> Confirm Bulk Delete
            </DialogTitle>
          </DialogHeader>
          <div style={{ padding: '8px 0', lineHeight: 1.6 }}>
            <p style={{ color: '#e2d9f3', marginBottom: 8 }}>
              You are about to permanently delete <strong style={{ color: '#f87171' }}>{selectedIds.size} lead{selectedIds.size > 1 ? 's' : ''}</strong>.
            </p>
            <p style={{ color: '#6b7280', fontSize: 13 }}>
              This action cannot be undone. Any campaign enrollments for these leads will also be affected.
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowBulkDeleteConfirm(false)} style={{ border: '1px solid #2d1f4a', color: '#9ca3af', borderRadius: 8 }}>
              Cancel
            </Button>
            <Button onClick={handleBulkDelete} disabled={bulkDeleting} style={{
              background: 'linear-gradient(90deg,#dc2626,#f43f5e)', color: '#fff',
              border: 'none', borderRadius: 8, fontWeight: 600,
              display: 'flex', alignItems: 'center', gap: 6,
            }}>
              {bulkDeleting ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
              {bulkDeleting ? 'Deleting…' : `Delete ${selectedIds.size} lead${selectedIds.size > 1 ? 's' : ''}`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Add Lead Modal */}
      <Dialog open={showAddModal} onOpenChange={setShowAddModal}>
        <DialogContent style={{ background: 'linear-gradient(135deg,#0f0a1f 0%,#14082a 100%)', border: '1px solid #2d1f4a', color: '#e2d9f3', maxWidth: 560 }}>
          <DialogHeader>
            <DialogTitle style={{ color: '#e2d9f3' }}>Add Lead Manually</DialogTitle>
          </DialogHeader>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, padding: '8px 0' }}>
            {[
              { k: 'first_name',       l: 'First Name',   p: 'Jane' },
              { k: 'last_name',        l: 'Last Name',    p: 'Doe' },
              { k: 'email',            l: 'Email',        p: 'jane@company.com', span: true },
              { k: 'phone',            l: 'Phone',        p: '+1 555 000 0000' },
              { k: 'job_title',        l: 'Job Title',    p: 'VP of Sales' },
              { k: 'company_name',     l: 'Company',      p: 'Acme Corp' },
              { k: 'company_industry', l: 'Industry',     p: 'SaaS' },
              { k: 'company_size',     l: 'Company Size', p: '150', type: 'number' },
              { k: 'company_location', l: 'Location',     p: 'San Francisco, CA', span: true },
              { k: 'linkedin_url',     l: 'LinkedIn URL', p: 'https://linkedin.com/in/…', span: true },
            ].map(({ k, l, p, span, type }) => (
              <div key={k} style={{ gridColumn: span ? '1 / -1' : undefined }}>
                <label style={{ color: '#9ca3af', fontSize: 12, display: 'block', marginBottom: 4 }}>{l}</label>
                <input type={type || 'text'} placeholder={p} value={newLead[k]} onChange={e => setNewLead(prev => ({ ...prev, [k]: e.target.value }))} style={inputStyle} />
              </div>
            ))}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setShowAddModal(false); setNewLead(BLANK_LEAD); }} style={{ border: '1px solid #2d1f4a', color: '#9ca3af', borderRadius: 8 }}>Cancel</Button>
            <Button onClick={handleAddLead} disabled={addingLead} style={{ background: 'linear-gradient(90deg,#f43f5e,#a855f7)', color: '#fff', border: 'none', borderRadius: 8, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}>
              {addingLead ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />}
              Add Lead
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Generate Leads Modal */}
      <Dialog open={showGenModal} onOpenChange={setShowGenModal}>
        <DialogContent style={{ background: 'linear-gradient(135deg,#0f0a1f 0%,#14082a 100%)', border: '1px solid #2d1f4a', color: '#e2d9f3', maxWidth: 480 }}>
          <DialogHeader>
            <DialogTitle style={{ color: '#e2d9f3', display: 'flex', alignItems: 'center', gap: 8 }}>
              <Zap size={18} color="#a855f7" /> Generate Leads Automatically
            </DialogTitle>
          </DialogHeader>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 18, padding: '8px 0' }}>
            <div>
              <label style={{ color: '#9ca3af', fontSize: 12, display: 'block', marginBottom: 8 }}>Source</label>
              <div style={{ display: 'flex', gap: 8 }}>
                {[
                  { key: 'apify',  label: '⚡ Apify',    desc: 'Web scraping — LinkedIn & Google', color: '#a855f7' },
                  { key: 'apollo', label: '🚀 Apollo.io', desc: 'Verified B2B contact database', color: '#3b82f6' },
                ].map(s => (
                  <button key={s.key} onClick={() => setGenSource(s.key)} style={{
                    flex: 1, padding: '10px 14px', borderRadius: 10, cursor: 'pointer', textAlign: 'left', position: 'relative',
                    background: genSource === s.key ? `${s.color}22` : 'rgba(255,255,255,0.03)',
                    border: `1px solid ${genSource === s.key ? s.color : '#2d1f4a'}`,
                    transition: 'all 0.2s',
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ color: '#e2d9f3', fontWeight: 600, fontSize: 14 }}>{s.label}</span>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                        <span style={{ fontSize: 10, padding: '1px 6px', borderRadius: 4, background: 'rgba(234,179,8,0.15)', color: '#fcd34d' }}>PAID</span>
                        <span
                          title="How to Connect"
                          onClick={(e) => { e.stopPropagation(); setShowSetupGuide(s.key); }}
                          style={{ color: '#4b5563', cursor: 'pointer', display: 'flex', alignItems: 'center', transition: 'color 0.2s' }}
                          onMouseEnter={e => e.currentTarget.style.color = s.color}
                          onMouseLeave={e => e.currentTarget.style.color = '#4b5563'}
                        >
                          <HelpCircle size={13} />
                        </span>
                      </div>
                    </div>
                    <div style={{ color: '#6b7280', fontSize: 12, marginTop: 2 }}>{s.desc}</div>
                  </button>
                ))}
              </div>
            </div>

            {icpProfiles.length > 1 && (
              <div>
                <label style={{ color: '#9ca3af', fontSize: 12, display: 'block', marginBottom: 6 }}>ICP Profile</label>
                <select value={genIcpId} onChange={e => setGenIcpId(e.target.value)} style={{ ...inputStyle, background: 'rgba(30,10,50,0.6)', border: '1px solid #2d1f4a' }}>
                  {icpProfiles.map(p => (
                    <option key={p.id} value={p.id}>{p.name}{p.is_active ? ' (Active)' : ''}</option>
                  ))}
                </select>
              </div>
            )}
            {icpProfiles.length === 1 && (
              <div style={{ padding: '8px 12px', borderRadius: 8, background: 'rgba(168,85,247,0.08)', border: '1px solid #2d1f4a' }}>
                <span style={{ color: '#9ca3af', fontSize: 12 }}>ICP: </span>
                <span style={{ color: '#e2d9f3', fontSize: 13, fontWeight: 600 }}>{icpProfiles[0].name}</span>
              </div>
            )}
            {icpProfiles.length === 0 && (
              <div style={{ padding: 12, borderRadius: 8, background: 'rgba(244,63,94,0.08)', border: '1px solid rgba(244,63,94,0.2)', color: '#f87171', fontSize: 13 }}>
                No ICP profile found. Set up your ICP profile first.
              </div>
            )}

            <div>
              <label style={{ color: '#9ca3af', fontSize: 12, display: 'block', marginBottom: 6 }}>
                Number of Leads: <span style={{ color: '#a855f7', fontWeight: 700 }}>{genCount}</span>
              </label>
              <input type="range" min={5} max={50} step={5} value={genCount} onChange={e => setGenCount(Number(e.target.value))} style={{ width: '100%', accentColor: '#a855f7' }} />
              <div style={{ display: 'flex', justifyContent: 'space-between', color: '#4b5563', fontSize: 11, marginTop: 2 }}>
                <span>5</span><span>50</span>
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowGenModal(false)} style={{ border: '1px solid #2d1f4a', color: '#9ca3af', borderRadius: 8 }}>Cancel</Button>
            <Button onClick={handleGenerate} disabled={generating || icpProfiles.length === 0} style={{
              background: 'linear-gradient(90deg,#7c3aed,#a855f7)', color: '#fff',
              border: 'none', borderRadius: 8, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6,
            }}>
              {generating ? <Loader2 size={13} className="animate-spin" /> : <Zap size={13} />}
              {generating ? 'Generating...' : `Generate ${genCount} Leads`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Setup Guide Modal */}
      <Dialog open={!!showSetupGuide} onOpenChange={() => setShowSetupGuide(null)}>
        <DialogContent style={{ background: 'linear-gradient(135deg,#0f0a1f 0%,#14082a 100%)', border: '1px solid #2d1f4a', color: '#e2d9f3', maxWidth: 560, maxHeight: '85vh', overflowY: 'auto' }}>
          <DialogHeader>
            <DialogTitle style={{ color: '#e2d9f3', display: 'flex', alignItems: 'center', gap: 8 }}>
              {showSetupGuide === 'apify'
                ? <><span style={{ fontSize: 20 }}>⚡</span> How to Connect Apify</>
                : <><span style={{ fontSize: 20 }}>🚀</span> How to Connect Apollo.io</>}
            </DialogTitle>
          </DialogHeader>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 16, padding: '4px 0 8px' }}>
            {showSetupGuide === 'apify' && (
              <>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', borderRadius: 8, background: 'rgba(234,179,8,0.08)', border: '1px solid rgba(234,179,8,0.2)' }}>
                  <span style={{ fontSize: 14 }}>⚠️</span>
                  <span style={{ color: '#fcd34d', fontSize: 13, fontWeight: 600 }}>Apify requires a paid plan for production-level lead scraping</span>
                </div>
                {[
                  { step: 1, title: 'Create an Apify account', detail: 'Go to apify.com and sign up. Then upgrade to a paid plan (Starter $49/month or higher) to get enough credits for regular lead generation.', link: 'https://apify.com/sign-up', linkLabel: 'apify.com/sign-up' },
                  { step: 2, title: 'Get your API Token', detail: 'After login, click your profile icon (top right) → Settings → Integrations tab. You will see your "Personal API token". Click "Copy" to copy it.', note: 'URL: console.apify.com/account/integrations' },
                  { step: 3, title: 'Add token to your .env file', detail: 'Open the .env file in your project root folder and add this line:', code: 'APIFY_API_TOKEN=apify_api_xxxxxxxxxxxxxxxxxxxxxxxx' },
                  { step: 4, title: 'Choose your scraping actor', detail: 'The default actor searches Google for LinkedIn profiles. For more accurate results you can use a LinkedIn-specific actor. Set the actor ID in .env:', code: 'APIFY_ACTOR_ID=apify/google-search-scraper' },
                  { step: 5, title: 'Restart the server & generate leads', detail: 'Stop your Django server (Ctrl+C) and start it again. Then come back here and click "Generate Leads" with Apify selected.', code: 'python manage.py runserver' },
                ].map(s => (
                  <div key={s.step} style={{ display: 'flex', gap: 12 }}>
                    <div style={{ flexShrink: 0, width: 24, height: 24, borderRadius: '50%', background: 'rgba(168,85,247,0.2)', border: '1px solid #7c3aed', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#a855f7', fontSize: 12, fontWeight: 700, marginTop: 2 }}>{s.step}</div>
                    <div style={{ flex: 1 }}>
                      <div style={{ color: '#e2d9f3', fontWeight: 600, fontSize: 13, marginBottom: 4 }}>{s.title}</div>
                      <div style={{ color: '#9ca3af', fontSize: 12, lineHeight: 1.5 }}>{s.detail}</div>
                      {s.link && <a href={s.link} target="_blank" rel="noreferrer" style={{ color: '#a855f7', fontSize: 12, display: 'inline-flex', alignItems: 'center', gap: 4, marginTop: 4 }}><ExternalLink size={11} />{s.linkLabel}</a>}
                      {s.note && <div style={{ marginTop: 4, padding: '4px 8px', borderRadius: 6, background: 'rgba(255,255,255,0.04)', color: '#6b7280', fontSize: 11, fontFamily: 'monospace' }}>{s.note}</div>}
                      {s.code && (
                        <div style={{ marginTop: 6, padding: '8px 12px', borderRadius: 8, background: 'rgba(0,0,0,0.4)', border: '1px solid #1e1035', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                          <code style={{ color: '#a855f7', fontSize: 11, flex: 1, wordBreak: 'break-all' }}>{s.code}</code>
                          <button onClick={() => { navigator.clipboard.writeText(s.code); setCopiedKey(s.step); setTimeout(() => setCopiedKey(null), 2000); }} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: copiedKey === s.step ? '#4ade80' : '#6b7280', flexShrink: 0 }}>
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
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', borderRadius: 8, background: 'rgba(234,179,8,0.08)', border: '1px solid rgba(234,179,8,0.2)' }}>
                  <span style={{ fontSize: 14 }}>⚠️</span>
                  <span style={{ color: '#fcd34d', fontSize: 13, fontWeight: 600 }}>Apollo People Search API requires a PAID plan ($49+/month)</span>
                </div>
                <div style={{ padding: '8px 12px', borderRadius: 8, background: 'rgba(168,85,247,0.06)', border: '1px solid #2d1f4a', color: '#9ca3af', fontSize: 12 }}>
                  💡 <strong style={{ color: '#e2d9f3' }}>Recommendation:</strong> Use <strong style={{ color: '#a855f7' }}>Apify</strong> (free) for lead generation if you don't have a paid Apollo plan.
                </div>
                {[
                  { step: 1, title: 'Create an Apollo.io account', detail: 'Go to app.apollo.io and sign up. Free plan gives 50 credits/month but does NOT include the API People Search endpoint.', link: 'https://app.apollo.io', linkLabel: 'app.apollo.io' },
                  { step: 2, title: 'Upgrade to a paid plan', detail: 'Go to app.apollo.io → Settings → Plans & Billing. The "Basic" plan ($49/month) or higher includes API access to People Search.' },
                  { step: 3, title: 'Get your API Key', detail: 'Go to developer.apollo.io → Create Account → Create API Key. Name it anything (e.g. "AI Employee"). Copy the key immediately — it is shown only once.', link: 'https://developer.apollo.io', linkLabel: 'developer.apollo.io' },
                  { step: 4, title: 'Add API key to your .env file', detail: 'Open the .env file in your project root and add this line:', code: 'APOLLO_API_KEY=your_apollo_api_key_here' },
                  { step: 5, title: 'Restart the server & generate leads', detail: 'Stop your Django server (Ctrl+C) and start it again. Then select Apollo.io as your source and click Generate Leads.', code: 'python manage.py runserver' },
                ].map(s => (
                  <div key={s.step} style={{ display: 'flex', gap: 12 }}>
                    <div style={{ flexShrink: 0, width: 24, height: 24, borderRadius: '50%', background: 'rgba(59,130,246,0.2)', border: '1px solid #3b82f6', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#60a5fa', fontSize: 12, fontWeight: 700, marginTop: 2 }}>{s.step}</div>
                    <div style={{ flex: 1 }}>
                      <div style={{ color: '#e2d9f3', fontWeight: 600, fontSize: 13, marginBottom: 4 }}>{s.title}</div>
                      <div style={{ color: '#9ca3af', fontSize: 12, lineHeight: 1.5 }}>{s.detail}</div>
                      {s.link && <a href={s.link} target="_blank" rel="noreferrer" style={{ color: '#60a5fa', fontSize: 12, display: 'inline-flex', alignItems: 'center', gap: 4, marginTop: 4 }}><ExternalLink size={11} />{s.linkLabel}</a>}
                      {s.code && (
                        <div style={{ marginTop: 6, padding: '8px 12px', borderRadius: 8, background: 'rgba(0,0,0,0.4)', border: '1px solid #1e1035', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                          <code style={{ color: '#60a5fa', fontSize: 11, flex: 1, wordBreak: 'break-all' }}>{s.code}</code>
                          <button onClick={() => { navigator.clipboard.writeText(s.code); setCopiedKey(s.step + 10); setTimeout(() => setCopiedKey(null), 2000); }} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: copiedKey === s.step + 10 ? '#4ade80' : '#6b7280', flexShrink: 0 }}>
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
            <Button
              onClick={() => { setShowSetupGuide(null); setGenSource(showSetupGuide); }}
              style={{ background: showSetupGuide === 'apify' ? 'linear-gradient(90deg,#7c3aed,#a855f7)' : 'linear-gradient(90deg,#1d4ed8,#3b82f6)', color: '#fff', border: 'none', borderRadius: 8, fontWeight: 600 }}
            >
              Got it — Use {showSetupGuide === 'apify' ? 'Apify' : 'Apollo.io'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default SDRLeadsTab;
