import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import pmAgentService from '@/services/pmAgentService';
import { companyApi } from '@/services/companyAuthService';
import { Loader2, Activity, TrendingUp, AlertTriangle, CheckCircle, Clock, FileText } from 'lucide-react';

function markdownToHtml(markdown) {
  if (!markdown || typeof markdown !== 'string') return '';
  const escape = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const bold = (s) => s.replace(/\*\*(.+?)\*\*/g, '<strong class="font-semibold text-violet-300">$1</strong>');
  const lines = markdown.split('\n');
  const out = [];
  for (const line of lines) {
    const t = line.trim();
    if (!t) { out.push('<br/>'); continue; }
    if (t.startsWith('# ')) { out.push(`<h2 class="text-lg font-bold text-violet-300 mt-3 mb-1">${bold(escape(t.slice(2)))}</h2>`); continue; }
    if (t.startsWith('## ')) { out.push(`<h3 class="text-base font-semibold text-violet-300 mt-2 mb-1">${bold(escape(t.slice(3)))}</h3>`); continue; }
    if (t.startsWith('### ')) { out.push(`<h4 class="text-sm font-semibold text-violet-400 mt-2 mb-1">${bold(escape(t.slice(4)))}</h4>`); continue; }
    if (/^[-*]\s/.test(t)) { out.push(`<div class="flex items-start gap-2 ml-2"><span class="text-violet-400 mt-0.5">•</span><span class="text-gray-200">${bold(escape(t.replace(/^[-*]\s+/, '')))}</span></div>`); continue; }
    if (/^\d+\.\s/.test(t)) { out.push(`<div class="flex items-start gap-2 ml-2"><span class="text-violet-400 font-medium">${t.match(/^\d+/)[0]}.</span><span class="text-gray-200">${bold(escape(t.replace(/^\d+\.\s+/, '')))}</span></div>`); continue; }
    out.push(`<p class="text-gray-300 my-1">${bold(escape(t))}</p>`);
  }
  return out.join('\n');
}

function getScoreColor(score) {
  if (score >= 80) return 'text-green-400';
  if (score >= 60) return 'text-yellow-400';
  if (score >= 40) return 'text-orange-400';
  return 'text-red-400';
}

function getScoreBg(score) {
  if (score >= 80) return 'bg-green-900/30 border-green-700';
  if (score >= 60) return 'bg-yellow-900/30 border-yellow-700';
  if (score >= 40) return 'bg-orange-900/30 border-orange-700';
  return 'bg-red-900/30 border-red-700';
}

export default function ProjectHealthDashboard() {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [reportLoading, setReportLoading] = useState(false);
  const [projects, setProjects] = useState([]);
  const [selectedProject, setSelectedProject] = useState(null);
  const [health, setHealth] = useState(null);
  const [statusReport, setStatusReport] = useState(null);

  useEffect(() => {
    const fetchProjects = async () => {
      try {
        const res = await companyApi.get('/company/projects');
        const data = res?.data?.data || res?.data?.results || res?.data || [];
        setProjects(Array.isArray(data) ? data : []);
      } catch (e) { console.error(e); }
    };
    fetchProjects();
  }, []);

  const fetchHealth = async () => {
    if (!selectedProject) {
      toast({ title: 'Error', description: 'Please select a project first.', variant: 'destructive' });
      return;
    }
    setLoading(true);
    setHealth(null);
    setStatusReport(null);
    try {
      const res = await pmAgentService.projectHealth(selectedProject);
      const data = res?.data?.data || res?.data || {};
      setHealth(data);
    } catch (e) {
      toast({ title: 'Error', description: e.message || 'Failed to fetch health score', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  const fetchStatusReport = async () => {
    if (!selectedProject) {
      toast({ title: 'Error', description: 'Please select a project first.', variant: 'destructive' });
      return;
    }
    setReportLoading(true);
    setStatusReport(null);
    try {
      const res = await pmAgentService.statusReport(selectedProject);
      const data = res?.data?.data || res?.data || {};
      setStatusReport(data);
    } catch (e) {
      toast({ title: 'Error', description: e.message || 'Failed to generate report', variant: 'destructive' });
    } finally {
      setReportLoading(false);
    }
  };

  const score = health?.health_score ?? health?.overall_score ?? null;

  return (
    <div className="space-y-6">
      {/* Controls */}
      <Card className="bg-gray-900/50 border-gray-700">
        <CardHeader className="pb-3">
          <CardTitle className="text-lg text-violet-300 flex items-center gap-2">
            <Activity className="w-5 h-5" /> Project Health & Status
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
            <Select value={selectedProject || ''} onValueChange={(v) => setSelectedProject(v || null)}>
              <SelectTrigger className="flex-1 h-10 bg-gray-800 border-gray-600 text-white">
                <SelectValue placeholder="Select a Project" />
              </SelectTrigger>
              <SelectContent className="bg-gray-800 border-gray-600 z-50">
                {projects.map((p) => (
                  <SelectItem key={p.id} value={String(p.id)}>{p.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button onClick={fetchHealth} disabled={loading || !selectedProject} className="bg-violet-600 hover:bg-violet-700">
              {loading ? <><Loader2 className="w-4 h-4 animate-spin mr-2" /> Analyzing...</> : <><Activity className="w-4 h-4 mr-2" /> Health Score</>}
            </Button>
            <Button onClick={fetchStatusReport} disabled={reportLoading || !selectedProject} variant="outline" className="border-violet-600 text-violet-300 hover:bg-violet-600/20">
              {reportLoading ? <><Loader2 className="w-4 h-4 animate-spin mr-2" /> Generating...</> : <><FileText className="w-4 h-4 mr-2" /> Status Report</>}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Loading */}
      {(loading || reportLoading) && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-violet-400" />
          <span className="ml-3 text-gray-400">{loading ? 'Calculating health score...' : 'Generating status report...'}</span>
        </div>
      )}

      {/* Health Score Display */}
      {!loading && health && (
        <div className="space-y-4">
          {/* Score Circle */}
          {score !== null && (
            <Card className={`border ${getScoreBg(score)}`}>
              <CardContent className="pt-6">
                <div className="flex items-center justify-center gap-6">
                  <div className="text-center">
                    <div className={`text-5xl font-bold ${getScoreColor(score)}`}>{score}</div>
                    <div className="text-sm text-gray-400 mt-1">/ 100</div>
                    <div className={`text-sm font-medium mt-2 ${getScoreColor(score)}`}>
                      {score >= 80 ? 'Healthy' : score >= 60 ? 'Needs Attention' : score >= 40 ? 'At Risk' : 'Critical'}
                    </div>
                  </div>
                  <div className="h-20 w-px bg-gray-700" />
                  <div className="space-y-2 text-sm">
                    {health.metrics && Object.entries(health.metrics).map(([key, val]) => (
                      <div key={key} className="flex items-center gap-2">
                        <span className="text-gray-400 capitalize">{key.replace(/_/g, ' ')}:</span>
                        <span className="text-white font-medium">{typeof val === 'number' ? `${val}%` : String(val)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Issues */}
          {health.issues?.length > 0 && (
            <Card className="bg-gray-800 border-gray-700">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-red-400 flex items-center gap-1">
                  <AlertTriangle className="w-4 h-4" /> Issues ({health.issues.length})
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {health.issues.map((issue, i) => (
                  <div key={i} className="bg-gray-900 rounded p-2 text-sm text-gray-300">
                    {typeof issue === 'string' ? issue : issue.description || issue.message || JSON.stringify(issue)}
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {/* Recommendations */}
          {health.recommendations?.length > 0 && (
            <Card className="bg-gray-800 border-gray-700">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-green-400 flex items-center gap-1">
                  <CheckCircle className="w-4 h-4" /> Recommendations
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-1">
                {health.recommendations.map((rec, i) => (
                  <div key={i} className="text-sm text-gray-300 flex items-start gap-2">
                    <span className="text-green-400">•</span>
                    <span>{typeof rec === 'string' ? rec : rec.recommendation || rec.text || JSON.stringify(rec)}</span>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {/* Fallback: render answer or report as markdown */}
          {(health.answer || health.report) && !score && (
            <Card className="bg-gray-800 border-gray-700">
              <CardContent className="pt-4">
                <div className="text-sm leading-relaxed" dangerouslySetInnerHTML={{ __html: markdownToHtml(health.answer || health.report) }} />
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* Status Report Display */}
      {!reportLoading && statusReport && (
        <Card className="bg-gray-800 border-gray-700">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-violet-300 flex items-center gap-1">
              <FileText className="w-4 h-4" /> Status Report
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div
              className="text-sm leading-relaxed"
              dangerouslySetInnerHTML={{ __html: markdownToHtml(statusReport.report || statusReport.answer || JSON.stringify(statusReport, null, 2)) }}
            />
          </CardContent>
        </Card>
      )}

      {/* Empty State */}
      {!loading && !reportLoading && !health && !statusReport && (
        <div className="flex flex-col items-center justify-center py-20 text-gray-500">
          <Activity className="w-12 h-12 mb-3 text-gray-600" />
          <p className="text-sm text-center">Select a project and click Health Score or Status Report to get started.</p>
        </div>
      )}
    </div>
  );
}
