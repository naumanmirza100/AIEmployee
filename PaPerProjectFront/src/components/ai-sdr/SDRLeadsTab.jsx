import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Users, Search, Plus, Upload, Brain,
  Flame, Thermometer, Snowflake, ExternalLink, Linkedin, Globe,
  MapPin, Briefcase, Phone, Mail, TrendingUp, RefreshCw, X,
  Loader2, Trash2, Zap, ChevronDown,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import { useToast } from '@/components/ui/use-toast';
import {
  listLeads, createLead, deleteLead, qualifyLead, importLeadsFromCSV,
  researchLeads, listIcpProfiles, getIcpProfile, saveIcpProfile,
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

const BLANK_LEAD = {
  first_name: '', last_name: '', email: '', phone: '',
  job_title: '', company_name: '', company_industry: '',
  company_size: '', company_location: '', linkedin_url: '',
};

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
            { k: 'name',           l: 'Profile Name',             p: 'Default ICP' },
            { k: 'industries',     l: 'Industries (comma-sep)',    p: 'SaaS, FinTech, E-commerce' },
            { k: 'job_titles',     l: 'Job Titles (comma-sep)',    p: 'CEO, VP Sales, CTO' },
            { k: 'locations',      l: 'Locations (comma-sep)',     p: 'United States, UK' },
            { k: 'keywords',       l: 'Keywords (comma-sep)',      p: 'B2B, startup, Series A' },
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
// Main Component
// --------------------------------------------------------------------------
const SDRLeadsTab = () => {
  const { toast } = useToast();
  const fileInputRef = useRef(null);

  const [leads, setLeads] = useState([]);
  const [stats, setStats] = useState({ total: 0, hot: 0, warm: 0, cold: 0, unscored: 0 });

  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [selectedLead, setSelectedLead] = useState(null);
  const [newLead, setNewLead] = useState(BLANK_LEAD);
  const [addingLead, setAddingLead] = useState(false);
  const [qualifyingId, setQualifyingId] = useState(null);

  const [search, setSearch] = useState('');
  const [filterTemp, setFilterTemp] = useState('');

  // Generate leads modal
  const [showGenModal, setShowGenModal] = useState(false);
  const [genSource, setGenSource] = useState('apify');
  const [genCount, setGenCount] = useState(10);
  const [genIcpId, setGenIcpId] = useState('');
  const [icpProfiles, setIcpProfiles] = useState([]);
  const [generating, setGenerating] = useState(false);

  // ── Load ──────────────────────────────────────────────────────────────
  const loadLeads = useCallback(async () => {
    try {
      const resp = await listLeads({ search, temperature: filterTemp });
      setLeads(resp.data || []);
      setStats(resp.stats || { total: 0, hot: 0, warm: 0, cold: 0, unscored: 0 });
    } catch (e) { console.error(e); }
  }, [search, filterTemp]);

  useEffect(() => {
    const init = async () => {
      setLoading(true);
      await loadLeads();
      setLoading(false);
    };
    init();
  }, []);

  useEffect(() => { if (!loading) loadLeads(); }, [search, filterTemp]);

  const openGenModal = async () => {
    const profiles = await listIcpProfiles();
    setIcpProfiles(profiles);
    if (profiles.length > 0) setGenIcpId(profiles.find(p => p.is_active)?.id || profiles[0].id);
    setShowGenModal(true);
  };

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const resp = await researchLeads({ count: genCount, source: genSource, icp_id: genIcpId || undefined });
      const created = resp?.data?.leads_created ?? resp?.leads_created ?? '?';
      toast({ title: `${created} leads generated!`, description: `Source: ${genSource.toUpperCase()}` });
      setShowGenModal(false);
      await loadLeads();
    } catch (e) {
      toast({ title: 'Generate failed', description: e?.response?.data?.message || e.message, variant: 'destructive' });
    } finally { setGenerating(false); }
  };

  // ── Delete ────────────────────────────────────────────────────────────
  const handleDelete = async (lead) => {
    try {
      await deleteLead(lead.id);
      if (selectedLead?.id === lead.id) setSelectedLead(null);
      toast({ title: 'Lead removed' });
      await loadLeads();
    } catch (e) {
      toast({ title: 'Delete failed', description: e.message, variant: 'destructive' });
    }
  };

  // ── Qualify single ────────────────────────────────────────────────────
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
      await loadLeads();
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
      await loadLeads();
    } catch (e) {
      toast({ title: 'Import failed', description: e.message, variant: 'destructive' });
    }
    e.target.value = '';
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
        </div>
      </div>

      {/* Filter bar */}
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <div style={{ position: 'relative', flex: 1, minWidth: 200, maxWidth: 340 }}>
          <Search size={14} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: '#6b7280' }} />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search name, company, email…" style={{
            ...inputStyle, paddingLeft: 36, border: '1px solid #2d1f4a',
          }} />
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          {[
            { key: '', label: 'All', color: '#a855f7' },
            { key: 'hot',  label: 'Hot',  color: '#f43f5e' },
            { key: 'warm', label: 'Warm', color: '#f59e0b' },
            { key: 'cold', label: 'Cold', color: '#60a5fa' },
          ].map(({ key, label, color }) => (
            <button key={key} onClick={() => setFilterTemp(key)} style={{
              padding: '5px 14px', borderRadius: 20, cursor: 'pointer', fontSize: 13,
              fontWeight: filterTemp === key ? 600 : 400,
              background: filterTemp === key ? `${color}22` : 'rgba(255,255,255,0.04)',
              border: `1px solid ${filterTemp === key ? color : 'rgba(255,255,255,0.08)'}`,
              color: filterTemp === key ? color : '#6b7280',
            }}>{label}</button>
          ))}
        </div>
        <button onClick={loadLeads} style={{ background: 'none', border: '1px solid #2d1f4a', borderRadius: 8, padding: '7px 10px', cursor: 'pointer', color: '#6b7280' }}>
          <RefreshCw size={14} />
        </button>
      </div>

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
                {['Name & Company', 'Title', 'Score', 'Temperature', 'Location', 'Source', 'Actions'].map(h => (
                  <th key={h} style={{ padding: '12px 16px', textAlign: 'left', color: '#4b5563', fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {leads.map(lead => {
                const tcfg = TEMP_CONFIG[lead.temperature];
                const TIcon = tcfg?.icon;
                return (
                  <tr key={lead.id} onClick={() => setSelectedLead(lead)}
                    style={{ borderBottom: '1px solid rgba(45,31,74,0.4)', cursor: 'pointer', transition: 'background 0.15s' }}
                    onMouseEnter={e => e.currentTarget.style.background = 'rgba(168,85,247,0.04)'}
                    onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                  >
                    <td style={{ padding: '13px 16px' }}>
                      <div style={{ fontWeight: 600, color: '#e2d9f3', fontSize: 14 }}>{lead.full_name}</div>
                      <div style={{ color: '#6b7280', fontSize: 12, marginTop: 2 }}>{lead.company_name}</div>
                    </td>
                    <td style={{ padding: '13px 16px' }}>
                      <span style={{ color: '#9ca3af', fontSize: 13 }}>{lead.job_title || '—'}</span>
                    </td>
                    <td style={{ padding: '13px 16px' }}>
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
                    <td style={{ padding: '13px 16px' }}>
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
                    <td style={{ padding: '13px 16px' }}>
                      <span style={{ color: '#6b7280', fontSize: 13 }}>{lead.company_location || '—'}</span>
                    </td>
                    <td style={{ padding: '13px 16px' }}>
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

      {/* Lead detail slide-over */}
      {selectedLead && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 50, display: 'flex', justifyContent: 'flex-end' }}>
          <div style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.55)' }} onClick={() => setSelectedLead(null)} />
          <div style={{
            position: 'relative', width: 480, maxWidth: '95vw', height: '100%',
            background: 'linear-gradient(160deg,#0f0a1f 0%,#14082a 100%)',
            borderLeft: '1px solid #2d1f4a', overflowY: 'auto', padding: 24,
          }}>
            {/* Header */}
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

            {/* Score (if exists) */}
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

            {/* Score breakdown */}
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

            {/* Contact */}
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

            {/* Company */}
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

            {/* Technologies */}
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

            {/* Buying signals */}
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

            {/* Actions */}
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

            {/* Source selector */}
            <div>
              <label style={{ color: '#9ca3af', fontSize: 12, display: 'block', marginBottom: 8 }}>Source</label>
              <div style={{ display: 'flex', gap: 8 }}>
                {[
                  { key: 'apify',  label: '⚡ Apify',     desc: 'Real leads from web scraping', color: '#a855f7' },
                  { key: 'apollo', label: '🚀 Apollo.io',  desc: 'Verified B2B contact database', color: '#3b82f6' },
                ].map(s => (
                  <button key={s.key} onClick={() => setGenSource(s.key)} style={{
                    flex: 1, padding: '10px 14px', borderRadius: 10, cursor: 'pointer', textAlign: 'left',
                    background: genSource === s.key ? `${s.color}22` : 'rgba(255,255,255,0.03)',
                    border: `1px solid ${genSource === s.key ? s.color : '#2d1f4a'}`,
                    transition: 'all 0.2s',
                  }}>
                    <div style={{ color: '#e2d9f3', fontWeight: 600, fontSize: 14 }}>{s.label}</div>
                    <div style={{ color: '#6b7280', fontSize: 12, marginTop: 2 }}>{s.desc}</div>
                  </button>
                ))}
              </div>
              {genSource === 'apollo' && (
                <div style={{ marginTop: 8, padding: '8px 12px', borderRadius: 8, background: 'rgba(234,179,8,0.08)', border: '1px solid rgba(234,179,8,0.25)', color: '#fcd34d', fontSize: 12 }}>
                  ⚠️ Apollo People Search requires a paid Apollo plan. Free accounts may get a 403 error — use <strong>Apify</strong> for free lead generation.
                </div>
              )}
            </div>

            {/* ICP Profile selector */}
            {icpProfiles.length > 1 && (
              <div>
                <label style={{ color: '#9ca3af', fontSize: 12, display: 'block', marginBottom: 6 }}>ICP Profile</label>
                <select
                  value={genIcpId}
                  onChange={e => setGenIcpId(e.target.value)}
                  style={{ ...inputStyle, background: 'rgba(30,10,50,0.6)', border: '1px solid #2d1f4a' }}
                >
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

            {/* Count */}
            <div>
              <label style={{ color: '#9ca3af', fontSize: 12, display: 'block', marginBottom: 6 }}>
                Number of Leads: <span style={{ color: '#a855f7', fontWeight: 700 }}>{genCount}</span>
              </label>
              <input
                type="range" min={5} max={50} step={5}
                value={genCount} onChange={e => setGenCount(Number(e.target.value))}
                style={{ width: '100%', accentColor: '#a855f7' }}
              />
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
    </div>
  );
};

export default SDRLeadsTab;
