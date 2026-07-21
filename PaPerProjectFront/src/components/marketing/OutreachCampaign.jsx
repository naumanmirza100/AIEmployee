import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import HoverTip from '@/components/common/HoverTip';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { DatePicker } from '@/components/ui/date-picker';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { useToast } from '@/components/ui/use-toast';
import { Loader2, Megaphone, Send, Upload, CheckCircle, Sparkles, Mail, AlertTriangle } from 'lucide-react';
import marketingAgentService from '@/services/marketingAgentService';
import { parseDateLocal, formatDateLocal } from '@/lib/utils';
import AddEmailAccountModal from './AddEmailAccountModal';

const ACTIONS = [
  { value: 'create_multi_channel', label: 'Create Email Campaign' },
  // Design / Launch / Schedule / Optimize actions were removed from the UI —
  // the form now only creates email campaigns.
];

const DURATION_UNITS = [
  { value: 'week', label: 'Week(s)' },
  { value: 'month', label: 'Month(s)' },
];

const COMPANY_SIZES = [
  { value: '__any__', label: 'Any' },
  { value: '1-10', label: '1-10 employees' },
  { value: '11-50', label: '11-50 employees' },
  { value: '51-200', label: '51-200 employees' },
  { value: '201-1000', label: '201-1000 employees' },
  { value: '1001-5000', label: '1001-5000 employees' },
  { value: '5000+', label: '5000+ employees' },
];

/** Cut design to short summary: context + strategy only (before EMAIL CAMPAIGN PLAN etc.) */
function condenseDesign(rawDesign) {
  if (!rawDesign || typeof rawDesign !== 'string') return { short: '', hasMore: false };
  const stopPhrases = [
    'EMAIL CAMPAIGN PLAN',
    'MESSAGING FRAMEWORK',
    'TIMELINE & EXECUTION',
    'RESOURCE ALLOCATION',
    'PERFORMANCE METRICS',
    'RECOMMENDATIONS',
  ];
  const lines = rawDesign.split('\n');
  let cutIndex = lines.length;
  for (let i = 0; i < lines.length; i++) {
    const t = lines[i].trim();
    const u = t.toUpperCase();
    const isStop = stopPhrases.some(
      (p) => u === p || u === '## ' + p || u.startsWith('**' + p) || (t.length < 60 && u.includes(p))
    );
    if (isStop) {
      cutIndex = i;
      break;
    }
  }
  const maxLines = 85;
  if (cutIndex > maxLines) cutIndex = maxLines;
  const short = lines.slice(0, cutIndex).join('\n').trim();
  const hasMore = cutIndex < lines.length;
  return { short, hasMore };
}

/** Remove remaining markdown asterisks so ** and * never show in UI */
function stripMarkdownAsterisks(s) {
  if (!s || typeof s !== 'string') return s;
  return s.replace(/\*\*/g, '').replace(/\*/g, '');
}

/** Convert *Label:* style to clean label (no asterisks); then apply bold/italic and strip any leftover */
function formatDesignText(s) {
  const escape = (x) => String(x).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const bold = (x) => x.replace(/\*\*(.+?)\*\*/g, '<strong class="font-semibold text-foreground">$1</strong>');
  const italic = (x) => x.replace(/\*(.+?)\*/g, '<span class="text-muted-foreground">$1</span>');
  return stripMarkdownAsterisks(bold(italic(escape(s))));
}

/** Markdown to HTML - compact, professional style (no ** or * visible) */
function markdownToHtmlCompact(markdown) {
  if (!markdown || typeof markdown !== 'string') return '';
  const escape = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const lines = markdown.split('\n');
  const out = [];
  let inList = false;
  let inSubList = false;
  let i = 0;
  const labelClass = 'text-xs font-semibold text-muted-foreground uppercase tracking-wide mt-3 mb-1';
  const headingClass = 'text-sm font-semibold mt-3 mb-1 text-foreground';
  while (i < lines.length) {
    const line = lines[i];
    const t = line.trim();
    if (/^###\s+/.test(t)) {
      if (inSubList) { out.push('</ul>'); inSubList = false; }
      if (inList) { out.push('</ul>'); inList = false; }
      out.push(`<p class="${headingClass}">${stripMarkdownAsterisks(escape(t.slice(4)))}</p>`);
      i++; continue;
    }
    if (/^##\s+/.test(t)) {
      if (inSubList) { out.push('</ul>'); inSubList = false; }
      if (inList) { out.push('</ul>'); inList = false; }
      out.push(`<p class="${headingClass}">${stripMarkdownAsterisks(escape(t.slice(3)))}</p>`);
      i++; continue;
    }
    if (/^\*\*[^*]+\*\*$/.test(t) && t.length < 80) {
      if (inSubList) { out.push('</ul>'); inSubList = false; }
      if (inList) { out.push('</ul>'); inList = false; }
      const content = stripMarkdownAsterisks(escape(t.replace(/^\*\*|\*\*$/g, '')));
      out.push(`<p class="${headingClass}">${content}</p>`);
      i++; continue;
    }
    if (/^\s+(?:\+|\*)\s+/.test(line)) {
      if (!inSubList) { out.push('<ul class="list-[circle] pl-6 my-1 space-y-0.5 text-sm">'); inSubList = true; }
      if (!inList) { inList = true; }
      const content = line.replace(/^\s*(?:\+|\*)\s+/, '').trim();
      out.push(`<li class="leading-relaxed">${formatDesignText(content)}</li>`);
      i++; continue;
    }
    if (/^[\s]*(?:\*|\+|\-)\s+/.test(t) || /^\d+\.\s+/.test(t)) {
      if (inSubList) { out.push('</ul>'); inSubList = false; }
      if (!inList) { out.push('<ul class="list-disc pl-5 my-2 space-y-1 text-sm">'); inList = true; }
      const content = t.replace(/^[\s]*(?:\*|\+|\-|\d+\.)\s+/, '');
      out.push(`<li class="leading-relaxed">${formatDesignText(content)}</li>`);
      i++; continue;
    }
    if (t === '' && (inList || inSubList)) {
      if (inSubList) { out.push('</ul>'); inSubList = false; }
      if (inList) { out.push('</ul>'); inList = false; }
      i++; continue;
    }
    if (t && !t.startsWith('<')) {
      if (inSubList) { out.push('</ul>'); inSubList = false; }
      if (inList) { out.push('</ul>'); inList = false; }
      const isLabel = /^\*[^*]+\*:?\s*$/.test(t);
      const cls = isLabel ? labelClass : 'my-1 text-sm leading-relaxed text-foreground';
      out.push(`<p class="${cls}">${formatDesignText(t).replace(/\n/g, '<br/>')}</p>`);
    }
    i++;
  }
  if (inSubList) out.push('</ul>');
  if (inList) out.push('</ul>');
  return out.join('\n');
}

/** Markdown to HTML for campaign design / QA-style result - headings, lists, bold */
function markdownToHtml(markdown) {
  if (!markdown || typeof markdown !== 'string') return '';
  const escape = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const bold = (s) => s.replace(/\*\*(.+?)\*\*/g, '<strong class="font-semibold text-foreground">$1</strong>');
  const italic = (s) => s.replace(/\*(.+?)\*/g, '<em class="text-muted-foreground">$1</em>');
  const lines = markdown.split('\n');
  const out = [];
  let inList = false;
  let inSubList = false;
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const t = line.trim();
    const trimmedOnly = line.replace(/^\s+/, '');
    // ### Heading
    if (/^###\s+/.test(t)) {
      if (inSubList) { out.push('</ul>'); inSubList = false; }
      if (inList) { out.push('</ul>'); inList = false; }
      out.push(`<h3 class="text-lg font-bold mt-5 mb-2 text-violet-600 dark:text-violet-400 border-b border-violet-200 dark:border-violet-800 pb-2">${bold(escape(t.slice(4)))}</h3>`);
      i++; continue;
    }
    // ## Heading
    if (/^##\s+/.test(t)) {
      if (inSubList) { out.push('</ul>'); inSubList = false; }
      if (inList) { out.push('</ul>'); inList = false; }
      out.push(`<h2 class="text-xl font-bold mt-6 mb-3 text-violet-600 dark:text-violet-400 border-b border-violet-200 dark:border-violet-800 pb-2">${bold(escape(t.slice(3)))}</h2>`);
      i++; continue;
    }
    // **ALL CAPS or Section** at start of line -> section heading (no ##)
    if (/^\*\*[A-Z\s]+\*\*$/.test(t) || (/^\*\*[^*]+\*\*$/.test(t) && t.length < 80)) {
      if (inSubList) { out.push('</ul>'); inSubList = false; }
      if (inList) { out.push('</ul>'); inList = false; }
      const content = t.replace(/^\*\*|\*\*$/g, '');
      out.push(`<h2 class="text-xl font-bold mt-6 mb-3 text-violet-600 dark:text-violet-400 border-b border-violet-200 dark:border-violet-800 pb-2">${escape(content)}</h2>`);
      i++; continue;
    }
    // Sub-bullet: line starts with whitespace then + or * (e.g. tab+ or spaces+)
    if (/^\s+(?:\+|\*)\s+/.test(line)) {
      if (!inSubList) { out.push('<ul class="list-[circle] pl-8 my-1 space-y-1 text-sm">'); inSubList = true; }
      if (!inList) { inList = true; }
      const content = line.replace(/^\s*(?:\+|\*)\s+/, '').trim();
      out.push(`<li class="leading-relaxed">${bold(italic(escape(content)))}</li>`);
      i++; continue;
    }
    // Top-level bullet: * **x** or + **x** or * x or 1. x
    if (/^[\s]*(?:\*|\+|\-)\s+/.test(t) || /^\d+\.\s+/.test(t)) {
      if (inSubList) { out.push('</ul>'); inSubList = false; }
      if (!inList) { out.push('<ul class="list-disc pl-6 my-3 space-y-2">'); inList = true; }
      const content = t.replace(/^[\s]*(?:\*|\+|\-|\d+\.)\s+/, '');
      out.push(`<li class="text-sm leading-relaxed">${bold(italic(escape(content)))}</li>`);
      i++; continue;
    }
    if (t === '' && (inList || inSubList)) {
      if (inSubList) { out.push('</ul>'); inSubList = false; }
      if (inList) { out.push('</ul>'); inList = false; }
      i++; continue;
    }
    if (t && !t.startsWith('<')) {
      if (inSubList) { out.push('</ul>'); inSubList = false; }
      if (inList) { out.push('</ul>'); inList = false; }
      out.push(`<p class="my-2 text-sm leading-relaxed text-foreground">${bold(italic(escape(t)).replace(/\n/g, '<br/>'))}</p>`);
    }
    i++;
  }
  if (inSubList) out.push('</ul>');
  if (inList) out.push('</ul>');
  return out.join('\n');
}

/**
 * Format agent result for display (markdown-like text to simple HTML/JSX).
 * options: { designView: 'condensed'|'full', onShowFullDesign }
 */
function formatResult(result, action, options = {}) {
  if (!result) return null;
  if (result.success === false) {
    return <p className="text-destructive">{result.error || 'Action failed'}</p>;
  }
  const parts = [];
  const designView = options.designView || 'condensed';
  const onShowFullDesign = options.onShowFullDesign;
  if (result.campaign_design?.raw_design) {
    const raw = stripMarkdownAsterisks(result.campaign_design.raw_design);
    const { short, hasMore } = condenseDesign(raw);
    const designHtml = designView === 'full'
      ? markdownToHtmlCompact(raw)
      : markdownToHtmlCompact(short);
    parts.push(
      <div key="design" className="text-foreground campaign-design-content">
        <div
          className="prose prose-sm dark:prose-invert max-w-none"
          dangerouslySetInnerHTML={{ __html: designHtml }}
        />
        {/* {designView === 'condensed' && hasMore && onShowFullDesign && (
          <button
            type="button"
            className="text-sm text-violet-600 dark:text-violet-400 hover:underline mt-2"
            onClick={onShowFullDesign}
          >
            Show full design
          </button>
        )} */}
      </div>
    );
  }
  if (result.campaign_name) parts.push(<p key="name"><strong>Campaign:</strong> {result.campaign_name}</p>);
  // if (result.campaign_id) parts.push(<p key="id"><strong>Campaign ID:</strong> {result.campaign_id}</p>);
  if (result.status) parts.push(<p key="status"><strong>Status:</strong> {result.status}</p>);
  if (result.message) parts.push(<p key="msg" className="text-muted-foreground">{result.message}</p>);
  if (result.leads_uploaded != null && result.leads_uploaded > 0) {
    parts.push(<p key="leads"><strong>Leads uploaded:</strong> {result.leads_uploaded}</p>);
  }
  if (result.launch_plan?.full_plan) {
    parts.push(<div key="launch" className="mt-2 whitespace-pre-wrap text-sm border-t pt-2">{result.launch_plan.full_plan}</div>);
  }
  if (result.optimization_plan?.optimization_plan) {
    parts.push(<div key="opt" className="mt-2 whitespace-pre-wrap text-sm border-t pt-2">{result.optimization_plan.optimization_plan}</div>);
  }
  if (result.schedule?.schedule) {
    parts.push(<div key="sched" className="mt-2 whitespace-pre-wrap text-sm border-t pt-2">{result.schedule.schedule}</div>);
  }
  if (result.performance) {
    const p = result.performance;
    parts.push(
      <div key="perf" className="mt-2 border-t pt-2">
        <strong>Performance</strong>
        <p className="text-muted-foreground text-xs mt-1">
          Impressions: {(p.total_impressions ?? 0).toLocaleString()} · Clicks: {(p.total_clicks ?? 0).toLocaleString()} · Conversions: {(p.total_conversions ?? 0).toLocaleString()} · CTR: {(p.ctr ?? 0).toFixed(2)}%
        </p>
      </div>
    );
  }
  if (result.management_plan?.assessment) {
    parts.push(<div key="mgmt" className="mt-2 whitespace-pre-wrap text-sm border-t pt-2">{result.management_plan.assessment}</div>);
  }
  if (result.consistency_check?.assessment) {
    parts.push(<div key="cons" className="mt-2 whitespace-pre-wrap text-sm border-t pt-2">{result.consistency_check.assessment}</div>);
  }
  if (result.priority_actions?.length) {
    parts.push(
      <div key="prio" className="mt-2 border-t pt-2">
        <strong>Priority actions</strong>
        <ul className="list-disc pl-4 mt-1">{result.priority_actions.map((a, i) => <li key={i}>{a}</li>)}</ul>
      </div>
    );
  }
  if (result.recommendations?.length) {
    parts.push(
      <div key="rec" className="mt-4 pt-4 border-t border-border">
        <h3 className="text-lg font-bold mb-2 text-violet-600 dark:text-violet-400 border-b border-violet-200 dark:border-violet-800 pb-2 w-fit">
          Recommendations
        </h3>
        <ul className="list-disc pl-6 mt-2 space-y-2 text-sm leading-relaxed">
          {result.recommendations.map((r, i) => <li key={i}>{r}</li>)}
        </ul>
      </div>
    );
  }
  return <div className="space-y-1 text-sm">{parts.length ? parts : <p>Success.</p>}</div>;
}

const OutreachCampaign = ({ onCampaignCreated }) => {
  const { toast } = useToast();
  const [action, setAction] = useState('create_multi_channel');
  const [campaigns, setCampaigns] = useState([]);
  const [campaignId, setCampaignId] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingCampaigns, setLoadingCampaigns] = useState(true);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [designReady, setDesignReady] = useState(false);
  const [leadsFile, setLeadsFile] = useState(null);
  const [showFullDesign, setShowFullDesign] = useState(false);

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [targetLeads, setTargetLeads] = useState('');
  const [targetConversions, setTargetConversions] = useState('');
  const [ageRange, setAgeRange] = useState('');
  const [location, setLocation] = useState('');
  const [industry, setIndustry] = useState('');
  const [companySize, setCompanySize] = useState('__any__');
  const [interests, setInterests] = useState('');
  const [language, setLanguage] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');

  // Quick-create flow: name + description + duration -> AI fills the rest -> editable review
  const [durationAmount, setDurationAmount] = useState('1');
  const [durationUnit, setDurationUnit] = useState('week');
  const [autoFilling, setAutoFilling] = useState(false);
  const [fieldsRevealed, setFieldsRevealed] = useState(false);

  const [emailAccounts, setEmailAccounts] = useState([]);
  const [emailAccountsLoading, setEmailAccountsLoading] = useState(true);
  const [emailAccountId, setEmailAccountId] = useState('');
  const [noEmailAccountDialogOpen, setNoEmailAccountDialogOpen] = useState(false);
  const [addEmailAccountOpen, setAddEmailAccountOpen] = useState(false);

  useEffect(() => {
    setShowFullDesign(false);
  }, [result, action]);

  useEffect(() => {
    const load = async () => {
      try {
        const res = await marketingAgentService.listCampaigns({ limit: 100 });
        if (res?.status === 'success' && res?.data?.campaigns) {
          setCampaigns(res.data.campaigns);
        }
      } catch (e) {
        console.error('Load campaigns:', e);
      } finally {
        setLoadingCampaigns(false);
      }
    };
    load();
  }, []);

  const loadEmailAccounts = async () => {
    try {
      const res = await marketingAgentService.listEmailAccounts();
      const list = res?.status === 'success' && res?.data ? res.data : [];
      setEmailAccounts(list);
      if (list.length === 0) {
        setNoEmailAccountDialogOpen(true);
      } else {
        const def = list.find((a) => a.is_default) || list[0];
        setEmailAccountId(String(def.id));
      }
      return list;
    } catch (e) {
      console.error('Load email accounts:', e);
      setEmailAccounts([]);
      return [];
    } finally {
      setEmailAccountsLoading(false);
    }
  };

  useEffect(() => {
    loadEmailAccounts();
  }, []);

  useEffect(() => {
    if (!campaignId || action !== 'launch' && action !== 'optimize' && action !== 'schedule') return;
    const load = async () => {
      try {
        const res = await marketingAgentService.getCampaign(campaignId);
        if (res?.status === 'success' && res?.data?.campaign) {
          const c = res.data.campaign;
          setName(c.name || '');
          setDescription(c.description || '');
          setTargetLeads(c.target_leads != null ? String(c.target_leads) : '');
          setTargetConversions(c.target_conversions != null ? String(c.target_conversions) : '');
          setAgeRange(c.age_range || '');
          setLocation(c.location || '');
          setIndustry(c.industry || '');
          setCompanySize(c.company_size && c.company_size !== '' ? c.company_size : '__any__');
          setInterests(c.interests || '');
          setLanguage(c.language || '');
          setStartDate(c.start_date || '');
          setEndDate(c.end_date || '');
        }
      } catch (e) {
        console.error('Load campaign details:', e);
      }
    };
    load();
  }, [campaignId, action]);

  const buildCampaignData = () => {
    const data = {
      name: name?.trim() || undefined,
      description: description?.trim() || undefined,
      campaign_type: 'email',
      channels: ['email'],
    };
    if (targetLeads) data.target_leads = parseInt(targetLeads, 10);
    if (targetConversions) data.target_conversions = parseInt(targetConversions, 10);
    if (ageRange) data.age_range = ageRange.trim();
    if (location) data.location = location.trim();
    if (industry) data.industry = industry.trim();
    if (companySize && companySize !== '__any__') data.company_size = companySize;
    if (interests) data.interests = interests.trim();
    if (language) data.language = language.trim();
    if (showDates) {
      // Dates are directly editable here — send whatever the user set.
      if (startDate) data.start_date = startDate;
      if (endDate) data.end_date = endDate;
    } else if (action === 'launch') {
      // No date fields shown for Launch — the campaign record may still carry
      // a stale start_date from whenever the draft was first created (possibly
      // in the past), which the backend re-validates against today() on every
      // launch. Always send a fresh pair computed from Duration so launching
      // an old draft doesn't fail a "start date in the past" check the user
      // never got a chance to see or fix.
      const { start, end } = computeDatesFromDuration();
      data.start_date = start;
      data.end_date = end;
    }
    if (emailAccountId) data.email_account_id = Number(emailAccountId);
    data.goals = {};
    if (data.target_leads) data.goals.leads = data.target_leads;
    if (data.target_conversions) data.goals.conversions = data.target_conversions;
    data.target_audience = {
      age_range: data.age_range,
      location: data.location,
      industry: data.industry,
      company_size: data.company_size,
      interests: data.interests ? data.interests.split(',').map((i) => i.trim()).filter(Boolean) : [],
      language: data.language,
    };
    return data;
  };

  const useDesignForAction = (newAction) => {
    setAction(newAction);
    setDesignReady(false);
    setResult(null);
    setError(null);
    setFieldsRevealed(true);
  };

  const computeDatesFromDuration = () => {
    const amount = parseInt(durationAmount, 10);
    const today = new Date();
    const end = new Date(today);
    if (Number.isFinite(amount) && amount > 0) {
      if (durationUnit === 'month') {
        end.setMonth(end.getMonth() + amount);
      } else {
        end.setDate(end.getDate() + amount * 7);
      }
    }
    return { start: formatDateLocal(today), end: formatDateLocal(end) };
  };

  const handleAutoFill = async () => {
    if (campaignSelectRequired && !campaignId) {
      toast({ title: 'Select a campaign', description: 'Choose a campaign first.', variant: 'destructive' });
      return;
    }

    // An existing campaign is selected (Launch/Optimize/Schedule): its fields already
    // loaded via the effect above — just reveal them for editing, no AI call needed.
    if (showCampaignSelect && campaignId) {
      if (showDates) {
        // Always recompute from Duration (not just when empty) — the campaign-load
        // effect fills startDate/endDate from the saved draft, which can be weeks
        // old. The user is looking at Duration right now, so it should win over a
        // stale saved date instead of being silently ignored.
        const { start, end } = computeDatesFromDuration();
        setStartDate(start);
        setEndDate(end);
      }
      setFieldsRevealed(true);
      return;
    }

    if (!name?.trim()) {
      toast({ title: 'Campaign name required', variant: 'destructive' });
      return;
    }
    const nameTrimmed = name.trim();
    const duplicate = campaigns.some(
      (c) => c.name && String(c.name).trim().toLowerCase() === nameTrimmed.toLowerCase()
    );
    if (duplicate) {
      toast({
        title: 'Duplicate campaign name',
        description: 'A campaign with this name already exists. Use a different name.',
        variant: 'destructive',
      });
      return;
    }

    const { start, end } = computeDatesFromDuration();
    if (showDates) {
      setStartDate(start);
      setEndDate(end);
    }

    setAutoFilling(true);
    setError(null);
    try {
      const agentResult = await marketingAgentService.outreachCampaign(
        'auto_fill',
        {
          name: nameTrimmed,
          description: description?.trim() || '',
          start_date: start || '',
          end_date: end || '',
        }
      );
      if (agentResult?.success === false) {
        toast({ title: 'Error', description: agentResult.error, variant: 'destructive' });
        return;
      }
      const fields = agentResult?.suggested_fields || {};
      if (fields.target_leads != null) setTargetLeads(String(fields.target_leads));
      if (fields.target_conversions != null) setTargetConversions(String(fields.target_conversions));
      if (fields.age_range) setAgeRange(fields.age_range);
      if (fields.location) setLocation(fields.location);
      if (fields.industry) setIndustry(fields.industry);
      if (fields.company_size) setCompanySize(fields.company_size);
      if (fields.interests) setInterests(fields.interests);
      if (fields.language) setLanguage(fields.language);
      setFieldsRevealed(true);
      toast({ title: 'Suggestions ready', description: 'Review and edit the details below, then continue.' });
    } catch (err) {
      const isHardBlock = err?.status === 402 || err?.status === 403 || err?.data?.hard_block;
      const msg = isHardBlock
        ? (err?.data?.message || err?.message || 'API key or token quota issue. Check your API Keys settings.')
        : (err?.message || 'Request failed');
      setError(msg);
      toast({ title: isHardBlock ? 'Request blocked' : 'Error', description: msg, variant: 'destructive' });
    } finally {
      setAutoFilling(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setResult(null);

    // Launch/Optimize/Schedule: an existing campaign is optional now — if none is
    // selected, a new campaign is created from Name/Description/Duration first,
    // then immediately launched/scheduled.
    const needsNewCampaign = (action === 'launch' || action === 'schedule') && !campaignId;
    if (action === 'optimize' && !campaignId) {
      toast({ title: 'Select a campaign', description: 'Choose a campaign first.', variant: 'destructive' });
      return;
    }

    if (action === 'design' || action === 'create_multi_channel' || needsNewCampaign) {
      if (!name?.trim()) {
        toast({ title: 'Campaign name required', variant: 'destructive' });
        return;
      }
      const nameTrimmed = name.trim();
      const duplicate = campaigns.some(
        (c) => c.name && String(c.name).trim().toLowerCase() === nameTrimmed.toLowerCase()
      );
      if (duplicate) {
        toast({
          title: 'Duplicate campaign name',
          description: 'A campaign with this name already exists. Use a different name.',
          variant: 'destructive',
        });
        return;
      }
    }

    setLoading(true);
    try {
      const campaignData = buildCampaignData();
      let cid = campaignId ? Number(campaignId) : null;

      if (needsNewCampaign) {
        const createResult = await marketingAgentService.outreachCampaign(
          'create_multi_channel',
          campaignData,
          null,
          {},
          leadsFile || undefined
        );
        if (createResult?.success === false) {
          setError(createResult.error || 'Campaign creation failed');
          toast({ title: 'Error', description: createResult.error, variant: 'destructive' });
          return;
        }
        cid = createResult?.campaign_id;
        if (onCampaignCreated) onCampaignCreated();
      }

      const file = action === 'create_multi_channel' || action === 'launch' ? leadsFile : null;

      const agentResult = await marketingAgentService.outreachCampaign(
        action,
        campaignData,
        cid,
        {},
        needsNewCampaign ? undefined : (file || undefined)
      );

      if (agentResult?.success === false) {
        setError(agentResult.error || 'Action failed');
        toast({ title: 'Error', description: agentResult.error, variant: 'destructive' });
        return;
      }
      setResult(agentResult);
      if (action === 'design') setDesignReady(true);
      if (action === 'create_multi_channel' && onCampaignCreated) onCampaignCreated();
      toast({ title: 'Success', description: agentResult?.message || 'Done' });
    } catch (err) {
      const isHardBlock = err?.status === 402 || err?.status === 403 || err?.data?.hard_block;
      const msg = isHardBlock
        ? (err?.data?.message || err?.message || 'API key or token quota issue. Check your API Keys settings.')
        : (err?.message || 'Request failed');
      setError(msg);
      toast({ title: isHardBlock ? 'Request blocked' : 'Error', description: msg, variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  const showCampaignSelect = action === 'launch' || action === 'optimize' || action === 'schedule';
  const campaignSelectRequired = action === 'optimize';
  const showLeadsUpload = action === 'create_multi_channel' || action === 'launch';
  const showDates = action === 'create_multi_channel' || action === 'schedule';

  const created = result && result.success !== false && action === 'create_multi_channel';
  const goToLaunch = () => {
    if (result?.campaign_id) setCampaignId(String(result.campaign_id));
    useDesignForAction('launch');
  };

  return (
    <Card className="border-white/10 bg-black/20 backdrop-blur-sm">
      <CardHeader>
        <CardTitle className="text-white flex items-center gap-2.5">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-violet-500/15 ring-1 ring-violet-400/30">
            <Megaphone className="h-[18px] w-[18px] text-violet-400" />
          </span>
          Outreach & Campaign Agent
        </CardTitle>
        <CardDescription className="text-white/60">
          Design, create, launch, optimize, or schedule email campaigns. Optionally upload leads (CSV/Excel).
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="space-y-4 rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <div className={`grid grid-cols-1 gap-4 items-end ${showCampaignSelect ? 'md:grid-cols-3' : 'md:grid-cols-2'}`}>
              <div className="space-y-2">
                <Label className="text-white/90">Action</Label>
                <Select value={action} onValueChange={(v) => { setAction(v); setResult(null); setError(null); setDesignReady(false); setFieldsRevealed(false); }}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select action" />
                  </SelectTrigger>
                  <SelectContent>
                    {ACTIONS.map((a) => (
                      <SelectItem key={a.value} value={a.value}>{a.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {showCampaignSelect && (
                <div className="space-y-2">
                  <Label className="text-white/90">Existing campaign {campaignSelectRequired ? '(required)' : '(optional)'}</Label>
                  <Select
                    value={campaignId || (campaignSelectRequired ? '' : '__new__')}
                    onValueChange={(v) => {
                      if (v === '__new__') {
                        // Switching to "Create a new campaign" — clear out whatever
                        // the previously-selected existing campaign loaded into these
                        // fields, otherwise its name/description/account/etc. linger
                        // and look like they belong to the new campaign.
                        setCampaignId('');
                        setName('');
                        setDescription('');
                        setTargetLeads('');
                        setTargetConversions('');
                        setAgeRange('');
                        setLocation('');
                        setIndustry('');
                        setCompanySize('__any__');
                        setInterests('');
                        setLanguage('');
                        setStartDate('');
                        setEndDate('');
                      } else {
                        setCampaignId(v);
                      }
                      setFieldsRevealed(false);
                    }}
                    disabled={loadingCampaigns}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder={loadingCampaigns ? 'Loading...' : 'Select campaign'} />
                    </SelectTrigger>
                    <SelectContent>
                      {!campaignSelectRequired && (
                        <SelectItem value="__new__">Create a new campaign</SelectItem>
                      )}
                      {campaigns.map((c) => (
                        <SelectItem key={c.id} value={String(c.id)}>{c.name} ({c.status})</SelectItem>
                      ))}
                      {/* Radix Select requires non-empty value; when no campaigns, only placeholder is shown */}
                    </SelectContent>
                  </Select>
                </div>
              )}

              <div className="space-y-2">
                <Label className="text-white/90">Duration</Label>
                <div className="flex gap-2">
                  <Input
                    id="duration-amount"
                    type="number"
                    min={1}
                    placeholder="Duration"
                    className="w-30 h-10 shrink-0"
                    value={durationAmount}
                    onChange={(e) => {
                      setDurationAmount(e.target.value);
                      if (showDates) {
                        const { start, end } = computeDatesFromDuration();
                        setStartDate(start);
                        setEndDate(end);
                      }
                    }}
                  />
                  <Select
                    value={durationUnit}
                    onValueChange={(v) => {
                      setDurationUnit(v);
                      if (showDates) {
                        const amount = parseInt(durationAmount, 10);
                        const today = new Date();
                        const end = new Date(today);
                        if (Number.isFinite(amount) && amount > 0) {
                          if (v === 'month') end.setMonth(end.getMonth() + amount);
                          else end.setDate(end.getDate() + amount * 7);
                        }
                        setStartDate(formatDateLocal(today));
                        setEndDate(formatDateLocal(end));
                      }
                    }}
                  >
                    <SelectTrigger className="flex-1">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {DURATION_UNITS.map((u) => (
                        <SelectItem key={u.value} value={u.value}>{u.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </div>

            {!fieldsRevealed && (
              <div className="flex justify-end pt-1">
                <HoverTip tip="AI fills in the campaign details from what you entered above">
                  <Button
                    type="button"
                    className="bg-violet-600 hover:bg-violet-700 text-white border-0"
                    onClick={handleAutoFill}
                    disabled={autoFilling || (campaignSelectRequired && !campaignId)}
                  >
                    {autoFilling ? (
                      <>
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                        Generating...
                      </>
                    ) : showCampaignSelect && campaignId ? (
                      <>
                        <Sparkles className="h-4 w-4 mr-2" />
                        Show details
                      </>
                    ) : (
                      <>
                        <Sparkles className="h-4 w-4 mr-2" />
                        Generate with AI
                      </>
                    )}
                  </Button>
                </HoverTip>
              </div>
            )}
          </div>

          <div className="space-y-4 rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2 md:col-span-2">
                <Label htmlFor="camp-name" className="text-white/90">Campaign name</Label>
                <Input
                  id="camp-name"
                  placeholder="e.g. Summer Sale 2024"
                  value={name}
                  onChange={(e) => { setName(e.target.value); setFieldsRevealed(false); }}
                  disabled={campaignSelectRequired && !campaignId}
                />
              </div>
              <div className="space-y-2 md:col-span-2">
                <Label htmlFor="camp-desc" className="text-white/90">Description</Label>
                <Textarea
                  id="camp-desc"
                  placeholder="Goals and key messaging..."
                  value={description}
                  onChange={(e) => { setDescription(e.target.value); setFieldsRevealed(false); }}
                  rows={2}
                  disabled={campaignSelectRequired && !campaignId}
                />
              </div>
            </div>

            {emailAccounts.length > 0 && (
              <div className="space-y-2">
                <Label htmlFor="email-account" className="text-white/90">Send from</Label>
                <Select value={emailAccountId} onValueChange={setEmailAccountId} disabled={emailAccountsLoading}>
                  <SelectTrigger id="email-account">
                    <SelectValue placeholder="Select email account" />
                  </SelectTrigger>
                  <SelectContent>
                    {emailAccounts.map((acc) => (
                      <SelectItem key={acc.id} value={String(acc.id)}>
                        {acc.name} ({acc.email}){acc.is_default ? ' — Default' : ''}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>

          {fieldsRevealed && (
            <div className="space-y-5 rounded-xl border border-violet-400/20 bg-violet-500/[0.06] p-4">
              <div className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-violet-400" />
                <span className="text-sm font-medium text-white/90">Campaign details</span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="target-leads" className="text-white/90">Target leads</Label>
                  <Input
                    id="target-leads"
                    type="number"
                    min={0}
                    placeholder="e.g. 1000"
                    value={targetLeads}
                    onChange={(e) => setTargetLeads(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="target-conv" className="text-white/90">Target conversions</Label>
                  <Input
                    id="target-conv"
                    type="number"
                    min={0}
                    placeholder="e.g. 500"
                    value={targetConversions}
                    onChange={(e) => setTargetConversions(e.target.value)}
                  />
                </div>
              </div>

              {/* {showLeadsUpload && (
                <div className="space-y-2">
                  <Label>Leads file (CSV, XLS, XLSX) – optional</Label>
                  <div className="flex items-center gap-2">
                    <Input
                      type="file"
                      accept=".csv,.xls,.xlsx"
                      onChange={(e) => setLeadsFile(e.target.files?.[0] || null)}
                    />
                    <Upload className="h-4 w-4 text-muted-foreground" />
                  </div>
                  <p className="text-xs text-muted-foreground">Required columns: Email. Optional: First Name, Last Name, Phone, Company, Job Title.</p>
                </div>
              )} */}

              <div className="h-px bg-white/10" />

              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-white/40 mb-3">Target audience</p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="age" className="text-white/90">Age range</Label>
                    <Input id="age" placeholder="e.g. 25-45" value={ageRange} onChange={(e) => setAgeRange(e.target.value)} />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="loc" className="text-white/90">Location</Label>
                    <Input id="loc" placeholder="e.g. North America" value={location} onChange={(e) => setLocation(e.target.value)} />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="ind" className="text-white/90">Industry</Label>
                    <Input id="ind" placeholder="e.g. Technology" value={industry} onChange={(e) => setIndustry(e.target.value)} />
                  </div>
                  <div className="space-y-2">
                    <Label className="text-white/90">Company size</Label>
                    <Select value={companySize || '__any__'} onValueChange={setCompanySize}>
                      <SelectTrigger>
                        <SelectValue placeholder="Any" />
                      </SelectTrigger>
                      <SelectContent>
                        {COMPANY_SIZES.map((s) => (
                          <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="int" className="text-white/90">Interests</Label>
                    <Input id="int" placeholder="e.g. tech, marketing" value={interests} onChange={(e) => setInterests(e.target.value)} />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="lang" className="text-white/90">Language</Label>
                    <Input id="lang" placeholder="e.g. English" value={language} onChange={(e) => setLanguage(e.target.value)} />
                  </div>
                </div>
              </div>

              {showDates && (
                <>
                  <div className="h-px bg-white/10" />
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label htmlFor="start" className="text-white/90">Start date</Label>
                      <DatePicker
                        date={startDate ? parseDateLocal(startDate) : undefined}
                        setDate={(d) => setStartDate(d ? formatDateLocal(d) : '')}
                        placeholder="Select start date"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="end" className="text-white/90">End date</Label>
                      <DatePicker
                        date={endDate ? parseDateLocal(endDate) : undefined}
                        setDate={(d) => setEndDate(d ? formatDateLocal(d) : '')}
                        placeholder="Select end date"
                      />
                    </div>
                  </div>
                </>
              )}
            </div>
          )}

          {created ? (
            <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-emerald-400/20 bg-emerald-500/[0.08] p-4">
              <div className="flex items-center gap-2 text-emerald-400">
                <CheckCircle className="h-5 w-5 shrink-0" />
                <span className="font-medium">Created.</span>
              </div>
              {/* Launch button removed — launching is no longer part of this form's flow. */}
            </div>
          ) : designReady ? (
            <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-emerald-400/20 bg-emerald-500/[0.08] p-4">
              <div className="flex flex-col items-start gap-2">
                <div className="flex items-center gap-2 text-emerald-400">
                  <CheckCircle className="h-5 w-5 shrink-0" />
                  <span className="font-medium">Campaign design ready</span>
                </div>
                <p className="text-sm text-white/60">Use the form below to create, launch, or schedule this campaign.</p>
              </div>
              <Button
                type="button"
                className="bg-violet-600 hover:bg-violet-700 text-white border-0"
                onClick={() => useDesignForAction('create_multi_channel')}
              >
                Create Campaign
              </Button>
            </div>
          ) : fieldsRevealed ? (
            <div className="flex justify-end">
              <Button type="submit" className="bg-violet-600 hover:bg-violet-700 text-white border-0" disabled={loading}>
                {loading ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Processing...
                  </>
                ) : (
                  <>
                    <Send className="h-4 w-4 mr-2" />
                    {action === 'create_multi_channel'
                      ? 'Create Campaign'
                      : action === 'launch' && !campaignId
                        ? 'Create & Launch'
                        : action === 'schedule' && !campaignId
                          ? 'Create & Schedule'
                          : 'Execute'}
                  </>
                )}
              </Button>
            </div>
          ) : null}

        </form>

        {/* {error && <p className="text-sm text-destructive">{error}</p>} */}

        {result && (
          <div className="rounded-lg border border-border bg-muted/30 p-4">
            <h3 className="text-lg font-bold mb-3 text-violet-600 dark:text-violet-400 border-b border-violet-200 dark:border-violet-800 pb-2">
              {action === 'design' ? 'Campaign design' : action === 'create_multi_channel' ? 'Campaign created' : action === 'launch' ? 'Launch result' : action === 'schedule' ? 'Schedule result' : 'Result'}
            </h3>
            {action === 'design' && result.campaign_design?.raw_design && (
              <p className="text-xs text-muted-foreground mb-3">
                Strategy, target audience, key messaging, and channel recommendations.
              </p>
            )}
            <div className="pr-1">
              {formatResult(result, action, {
                designView: showFullDesign ? 'full' : 'condensed',
                onShowFullDesign: () => setShowFullDesign(true),
              })}
            </div>
          </div>
        )}
      </CardContent>

      <Dialog open={noEmailAccountDialogOpen} onOpenChange={setNoEmailAccountDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-amber-500" />
              Add an email account first
            </DialogTitle>
            <DialogDescription>
              You don't have any sender email accounts yet. An email account is required to send
              campaign emails — add one before creating or launching a campaign.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" onClick={() => setNoEmailAccountDialogOpen(false)}>
              Not now
            </Button>
            <Button
              onClick={() => {
                setNoEmailAccountDialogOpen(false);
                setAddEmailAccountOpen(true);
              }}
            >
              <Mail className="mr-2 h-4 w-4" />
              Add email account
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AddEmailAccountModal
        open={addEmailAccountOpen}
        onOpenChange={setAddEmailAccountOpen}
        onCreated={(created) => {
          loadEmailAccounts().then(() => {
            if (created?.account_id) setEmailAccountId(String(created.account_id));
          });
        }}
      />
    </Card>
  );
};

export default OutreachCampaign;
