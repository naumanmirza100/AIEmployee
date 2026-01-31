import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import { Loader2, Megaphone, Send, Upload, CheckCircle } from 'lucide-react';
import marketingAgentService from '@/services/marketingAgentService';

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

/**
 * Format agent result for display (markdown-like text to simple HTML/JSX)
 */
function formatResult(result, action) {
  if (!result) return null;
  if (result.success === false) {
    return <p className="text-destructive">{result.error || 'Action failed'}</p>;
  }
  const parts = [];
  if (result.campaign_design?.raw_design) {
    parts.push(<div key="design" className="whitespace-pre-wrap text-sm">{result.campaign_design.raw_design}</div>);
  }
  if (result.campaign_name) parts.push(<p key="name"><strong>Campaign:</strong> {result.campaign_name}</p>);
  if (result.campaign_id) parts.push(<p key="id"><strong>Campaign ID:</strong> {result.campaign_id}</p>);
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
      <div key="rec" className="mt-2 border-t pt-2">
        <strong>Recommendations</strong>
        <ul className="list-disc pl-4 mt-1">
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
                <Input id="start" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="end">End date</Label>
                <Input id="end" type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
              </div>
            </div>
          )}

          {created ? (
            <div className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-violet-200 bg-violet-50/80 dark:border-violet-800 dark:bg-violet-950/30 p-4">
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
            <div className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-violet-200 bg-violet-50/80 dark:border-violet-800 dark:bg-violet-950/30 p-4">
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
          <div className="rounded-lg border bg-muted/30 p-4">
            <h4 className="font-semibold mb-2">Result</h4>
            {formatResult(result, action)}
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default OutreachCampaign;
