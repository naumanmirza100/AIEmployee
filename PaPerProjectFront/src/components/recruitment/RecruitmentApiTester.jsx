import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/components/ui/use-toast';
import {
  apiCvParse,
  apiCvSummarize,
  apiCvEnrich,
  apiCvQualify,
} from '@/services/recruitmentAgentService';
import {
  Loader2,
  Upload,
  FileText,
  ChevronRight,
  CheckCircle2,
  Copy,
  Sparkles,
  Layers,
  Target,
} from 'lucide-react';

const STEP = { PARSE: 1, SUMMARIZE: 2, ENRICH: 3, QUALIFY: 4 };

function ResultBlock({ title, data, onCopy }) {
  const str = typeof data === 'object' ? JSON.stringify(data, null, 2) : String(data);
  return (
    <div className="mt-2 rounded-md border bg-muted/30 p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-sm font-medium text-muted-foreground">{title}</span>
        <Button variant="ghost" size="sm" onClick={() => onCopy(str)}>
          <Copy className="h-4 w-4" />
        </Button>
      </div>
      <pre className="max-h-64 overflow-auto text-xs whitespace-pre-wrap break-words">{str}</pre>
    </div>
  );
}

const RecruitmentApiTester = () => {
  const { toast } = useToast();
  const [cvFile, setCvFile] = useState(null);
  const [cvText, setCvText] = useState('');
  const [jobKeywords, setJobKeywords] = useState('');
  const [loadingStep, setLoadingStep] = useState(null);

  const [parsed, setParsed] = useState(null);
  const [insights, setInsights] = useState(null);
  const [enrichment, setEnrichment] = useState(null);
  const [qualification, setQualification] = useState(null);

  const keywordsList = jobKeywords
    ? jobKeywords.split(',').map((k) => k.trim()).filter(Boolean)
    : [];

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text).then(() => {
      toast({ title: 'Copied to clipboard' });
    });
  };

  const runParse = async () => {
    if (!cvFile && !cvText.trim()) {
      toast({ title: 'Add a CV', description: 'Upload a file or paste CV text.', variant: 'destructive' });
      return;
    }
    setLoadingStep(STEP.PARSE);
    setParsed(null);
    setInsights(null);
    setEnrichment(null);
    setQualification(null);
    try {
      const res = await apiCvParse(cvFile || undefined, cvText.trim() || undefined);
      const data = res?.data !== undefined ? res.data : res;
      if (data?.status === 'success' && data.parsed) {
        setParsed(data.parsed);
        toast({ title: 'Parse done', description: 'CV parsed successfully.' });
      } else {
        toast({ title: 'Parse failed', description: data?.message || 'Unknown error', variant: 'destructive' });
      }
    } catch (err) {
      const msg = err?.data?.message || err?.message;
      toast({ title: 'Parse error', description: msg, variant: 'destructive' });
    } finally {
      setLoadingStep(null);
    }
  };

  const runSummarize = async () => {
    if (!parsed) {
      toast({ title: 'Run Parse first', variant: 'destructive' });
      return;
    }
    setLoadingStep(STEP.SUMMARIZE);
    setInsights(null);
    setEnrichment(null);
    setQualification(null);
    try {
      const res = await apiCvSummarize(parsed, null, keywordsList.length ? keywordsList : undefined);
      const data = res?.data !== undefined ? res.data : res;
      if (data?.status === 'success' && data.insights) {
        setInsights(data.insights);
        toast({ title: 'Summarize done', description: 'Insights generated.' });
      } else {
        toast({ title: 'Summarize failed', description: data?.message || 'Unknown error', variant: 'destructive' });
      }
    } catch (err) {
      const msg = err?.data?.message || err?.message;
      toast({ title: 'Summarize error', description: msg, variant: 'destructive' });
    } finally {
      setLoadingStep(null);
    }
  };

  const runEnrich = async () => {
    if (!parsed || !insights) {
      toast({ title: 'Run Parse and Summarize first', variant: 'destructive' });
      return;
    }
    setLoadingStep(STEP.ENRICH);
    setEnrichment(null);
    setQualification(null);
    try {
      const res = await apiCvEnrich(parsed, insights, null);
      const data = res?.data !== undefined ? res.data : res;
      if (data?.status === 'success' && data.enrichment) {
        setEnrichment(data.enrichment);
        toast({ title: 'Enrich done', description: 'Enrichment completed.' });
      } else {
        toast({ title: 'Enrich failed', description: data?.message || 'Unknown error', variant: 'destructive' });
      }
    } catch (err) {
      const msg = err?.data?.message || err?.message;
      toast({ title: 'Enrich error', description: msg, variant: 'destructive' });
    } finally {
      setLoadingStep(null);
    }
  };

  const runQualify = async () => {
    if (!parsed || !insights) {
      toast({ title: 'Run Parse and Summarize first', variant: 'destructive' });
      return;
    }
    setLoadingStep(STEP.QUALIFY);
    setQualification(null);
    try {
      const res = await apiCvQualify(
        parsed,
        insights,
        null,
        keywordsList.length ? keywordsList : undefined,
        enrichment || undefined
      );
      const data = res?.data !== undefined ? res.data : res;
      if (data?.status === 'success' && data.qualification) {
        setQualification(data.qualification);
        toast({ title: 'Qualify done', description: `Decision: ${data.qualification.decision}` });
      } else {
        toast({ title: 'Qualify failed', description: data?.message || 'Unknown error', variant: 'destructive' });
      }
    } catch (err) {
      const msg = err?.data?.message || err?.message;
      toast({ title: 'Qualify error', description: msg, variant: 'destructive' });
    } finally {
      setLoadingStep(null);
    }
  };

  return (
    <div className="space-y-6 w-full max-w-full">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5" />
            Test pipeline APIs step by step
          </CardTitle>
          <CardDescription>
            Add a CV (file or text), then run Parse → Summarize → Enrich → Qualify. Each step shows the result; press Next to run the next step.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Input: CV file or text */}
          <div className="space-y-2">
            <Label>CV input (file or paste text)</Label>
            <div className="flex flex-col sm:flex-row gap-2">
              <div className="flex items-center gap-2">
                <Input
                  type="file"
                  accept=".pdf,.docx,.txt"
                  onChange={(e) => {
                    setCvFile(e.target.files?.[0] || null);
                    if (!e.target.files?.[0]) setCvText('');
                  }}
                  className="max-w-xs"
                />
                {cvFile && <Badge variant="secondary">{cvFile.name}</Badge>}
              </div>
              <span className="text-sm text-muted-foreground self-center">or paste text below</span>
            </div>
            <Textarea
              placeholder="Paste raw CV text here if not using a file..."
              value={cvText}
              onChange={(e) => setCvText(e.target.value)}
              rows={4}
              className="font-mono text-sm"
            />
          </div>

          {/* Optional job keywords (used in Summarize & Qualify) */}
          <div className="space-y-2">
            <Label>Job keywords (optional, comma-separated)</Label>
            <Input
              placeholder="e.g. React, Node.js, Python"
              value={jobKeywords}
              onChange={(e) => setJobKeywords(e.target.value)}
            />
          </div>

          {/* Step 1: Parse */}
          <div className="rounded-lg border p-4 space-y-2">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <div className="flex items-center gap-2">
                <span className="font-semibold">1. CV Parse</span>
                {parsed && <CheckCircle2 className="h-5 w-5 text-green-600" />}
              </div>
              <Button
                onClick={runParse}
                disabled={loadingStep !== null}
              >
                {loadingStep === STEP.PARSE ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Upload className="h-4 w-4 mr-2" />}
                Parse
              </Button>
            </div>
            {parsed && (
              <>
                <ResultBlock title="Parsed result" data={parsed} onCopy={copyToClipboard} />
                <Button
                  variant="outline"
                  size="sm"
                  onClick={runSummarize}
                  disabled={loadingStep !== null}
                  className="mt-2"
                >
                  Next: Summarize
                  <ChevronRight className="h-4 w-4 ml-1" />
                </Button>
              </>
            )}
          </div>

          {/* Step 2: Summarize */}
          <div className="rounded-lg border p-4 space-y-2">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <div className="flex items-center gap-2">
                <span className="font-semibold">2. Summarize</span>
                {insights && <CheckCircle2 className="h-5 w-5 text-green-600" />}
              </div>
              <Button
                onClick={runSummarize}
                disabled={!parsed || loadingStep !== null}
              >
                {loadingStep === STEP.SUMMARIZE ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Sparkles className="h-4 w-4 mr-2" />}
                Summarize
              </Button>
            </div>
            {insights && (
              <>
                <ResultBlock title="Insights" data={insights} onCopy={copyToClipboard} />
                <Button
                  variant="outline"
                  size="sm"
                  onClick={runEnrich}
                  disabled={loadingStep !== null}
                  className="mt-2"
                >
                  Next: Enrich
                  <ChevronRight className="h-4 w-4 ml-1" />
                </Button>
              </>
            )}
          </div>

          {/* Step 3: Enrich */}
          <div className="rounded-lg border p-4 space-y-2">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <div className="flex items-center gap-2">
                <span className="font-semibold">3. Enrich</span>
                {enrichment && <CheckCircle2 className="h-5 w-5 text-green-600" />}
              </div>
              <Button
                onClick={runEnrich}
                disabled={!parsed || !insights || loadingStep !== null}
              >
                {loadingStep === STEP.ENRICH ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Layers className="h-4 w-4 mr-2" />}
                Enrich
              </Button>
            </div>
            {enrichment && (
              <>
                <ResultBlock title="Enrichment" data={enrichment} onCopy={copyToClipboard} />
                <Button
                  variant="outline"
                  size="sm"
                  onClick={runQualify}
                  disabled={loadingStep !== null}
                  className="mt-2"
                >
                  Next: Qualify
                  <ChevronRight className="h-4 w-4 ml-1" />
                </Button>
              </>
            )}
          </div>

          {/* Step 4: Qualify */}
          <div className="rounded-lg border p-4 space-y-2">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <div className="flex items-center gap-2">
                <span className="font-semibold">4. Qualify</span>
                {qualification && <CheckCircle2 className="h-5 w-5 text-green-600" />}
              </div>
              <Button
                onClick={runQualify}
                disabled={!parsed || !insights || loadingStep !== null}
              >
                {loadingStep === STEP.QUALIFY ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Target className="h-4 w-4 mr-2" />}
                Qualify
              </Button>
            </div>
            {qualification && (
              <div className="space-y-2">
                <div className="flex flex-wrap gap-2">
                  <Badge variant={qualification.decision === 'INTERVIEW' ? 'default' : qualification.decision === 'HOLD' ? 'secondary' : 'destructive'}>
                    {qualification.decision}
                  </Badge>
                  {qualification.confidence_score != null && (
                    <Badge variant="outline">Confidence: {qualification.confidence_score}</Badge>
                  )}
                  {qualification.priority && <Badge variant="outline">{qualification.priority} priority</Badge>}
                </div>
                {qualification.reasoning && (
                  <p className="text-sm text-muted-foreground">{qualification.reasoning}</p>
                )}
                <ResultBlock title="Full qualification" data={qualification} onCopy={copyToClipboard} />
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default RecruitmentApiTester;
