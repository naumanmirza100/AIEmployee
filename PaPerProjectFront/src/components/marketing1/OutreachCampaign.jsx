import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { DatePicker } from '@/components/ui/date-picker';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import { Loader2, Megaphone, Send, Upload, CheckCircle } from 'lucide-react';
import marketingAgentService from '@/services/marketingAgentService';
import { parseDateLocal, formatDateLocal } from '@/lib/utils';

const ACTIONS = [
  { value: 'design', label: 'Design Campaign' },
  { value: 'create_multi_channel', label: 'Create Email Campaign' },
  { value: 'launch', label: 'Launch Campaign' },
  // { value: 'optimize', label: 'Optimize Campaign' },
  { value: 'schedule', label: 'Schedule Campaign' },
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
  const [action, setAction] = useState('design');
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
    if (startDate) data.start_date = startDate;
    if (endDate) data.end_date = endDate;
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
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setResult(null);

    if (action === 'launch' || action === 'optimize' || action === 'schedule') {
      if (!campaignId) {
        toast({ title: 'Select a campaign', description: 'Choose a campaign first.', variant: 'destructive' });
        return;
      }
    }

    if (action === 'design' || action === 'create_multi_channel') {
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
      const cid = campaignId ? Number(campaignId) : null;
      const file = action === 'create_multi_channel' || action === 'launch' ? leadsFile : null;

      const agentResult = await marketingAgentService.outreachCampaign(
        action,
        campaignData,
        cid,
        {},
        file || undefined
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
      setError(err.message || 'Request failed');
      toast({ title: 'Error', description: err.message, variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  const showCampaignSelect = action === 'launch' || action === 'optimize' || action === 'schedule';
  const showLeadsUpload = action === 'create_multi_channel' || action === 'launch';
  const showDates = action === 'create_multi_channel' || action === 'schedule';

  const created = result && result.success !== false && action === 'create_multi_channel';
  const goToLaunch = () => {
    if (result?.campaign_id) setCampaignId(String(result.campaign_id));
    useDesignForAction('launch');
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Megaphone className="h-5 w-5" />
          Outreach & Campaign Agent
        </CardTitle>
        <CardDescription>
          Design, create, launch, optimize, or schedule email campaigns. Optionally upload leads (CSV/Excel).
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label>Action</Label>
            <Select value={action} onValueChange={(v) => { setAction(v); setResult(null); setError(null); setDesignReady(false); }}>
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
              <Label>Campaign (required)</Label>
              <Select value={campaignId} onValueChange={setCampaignId} disabled={loadingCampaigns}>
                <SelectTrigger>
                  <SelectValue placeholder={loadingCampaigns ? 'Loading...' : 'Select campaign'} />
                </SelectTrigger>
                <SelectContent>
                  {campaigns.map((c) => (
                    <SelectItem key={c.id} value={String(c.id)}>{c.name} ({c.status})</SelectItem>
                  ))}
                  {/* Radix Select requires non-empty value; when no campaigns, only placeholder is shown */}
                </SelectContent>
              </Select>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2 md:col-span-2">
              <Label htmlFor="camp-name">Campaign name</Label>
              <Input
                id="camp-name"
                placeholder="e.g. Summer Sale 2024"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label htmlFor="camp-desc">Description</Label>
              <Textarea
                id="camp-desc"
                placeholder="Goals and key messaging..."
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={2}
              />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="target-leads">Target leads</Label>
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
              <Label htmlFor="target-conv">Target conversions</Label>
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

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="age">Age range</Label>
              <Input id="age" placeholder="e.g. 25-45" value={ageRange} onChange={(e) => setAgeRange(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="loc">Location</Label>
              <Input id="loc" placeholder="e.g. North America" value={location} onChange={(e) => setLocation(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="ind">Industry</Label>
              <Input id="ind" placeholder="e.g. Technology" value={industry} onChange={(e) => setIndustry(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label>Company size</Label>
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
              <Label htmlFor="int">Interests</Label>
              <Input id="int" placeholder="e.g. tech, marketing" value={interests} onChange={(e) => setInterests(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="lang">Language</Label>
              <Input id="lang" placeholder="e.g. English" value={language} onChange={(e) => setLanguage(e.target.value)} />
            </div>
          </div>

          {showDates && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="start">Start date</Label>
                <DatePicker
                  date={startDate ? parseDateLocal(startDate) : undefined}
                  setDate={(d) => setStartDate(d ? formatDateLocal(d) : '')}
                  placeholder="Select start date"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="end">End date</Label>
                <DatePicker
                  date={endDate ? parseDateLocal(endDate) : undefined}
                  setDate={(d) => setEndDate(d ? formatDateLocal(d) : '')}
                  placeholder="Select end date"
                />
              </div>
            </div>
          )}

          {created ? (
            <div className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-violet-200 p-4">
              <div className="flex items-center gap-2 text-green-700 dark:text-green-400">
                <CheckCircle className="h-5 w-5 shrink-0" />
                <span className="font-medium">Created.</span>
              </div>
              <Button
                type="button"
                className="bg-violet-600 hover:bg-violet-700 text-white border-0"
                onClick={goToLaunch}
              >
                Launch Campaign
              </Button>
            </div>
          ) : designReady ? (
            <div className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-violet-200 p-4">
              <div className="flex flex-col items-start gap-2 text-green-700 dark:text-green-400">
                <div className="flex items-center gap-2">
                  <CheckCircle className="h-5 w-5 shrink-0" />
                  <span className="font-medium">Campaign design ready</span>
                </div>
                <p className="text-sm text-muted-foreground">Use the form below to create, launch, or schedule this campaign.</p>
              </div>
              <Button
                type="button"
                className="bg-violet-600 hover:bg-violet-700 text-white border-0"
                onClick={() => useDesignForAction('create_multi_channel')}
              >
                Create Campaign
              </Button>
            </div>
          ) : (
            <div className="flex justify-end">
              <Button type="submit" disabled={loading}>
                {loading ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Processing...
                  </>
                ) : (
                  <>
                    <Send className="h-4 w-4 mr-2" />
                    Execute
                  </>
                )}
              </Button>
            </div>
          )}

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
    </Card>
  );
};

export default OutreachCampaign;
