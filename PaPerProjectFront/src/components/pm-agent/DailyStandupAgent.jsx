import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import pmAgentService from '@/services/pmAgentService';
import { companyApi } from '@/services/companyAuthService';
import { Loader2, Calendar, Users, AlertTriangle, CheckCircle, Clock } from 'lucide-react';

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

export default function DailyStandupAgent() {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [projects, setProjects] = useState([]);
  const [selectedProject, setSelectedProject] = useState(null);
  const [reportType, setReportType] = useState('daily');
  const [report, setReport] = useState(null);

  useEffect(() => {
    const fetchProjects = async () => {
      try {
        const res = await companyApi.get('/company/projects/list');
        const data = res?.data?.data || res?.data?.results || res?.data || [];
        setProjects(Array.isArray(data) ? data : []);
      } catch (e) { console.error(e); }
    };
    fetchProjects();
  }, []);

  const generateReport = async () => {
    setLoading(true);
    setReport(null);
    try {
      const res = await pmAgentService.dailyStandup(selectedProject, reportType);
      const data = res?.data?.data || res?.data || {};
      setReport(data);
    } catch (e) {
      toast({ title: 'Error', description: e.message || 'Failed to generate report', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Controls */}
      <Card className="bg-gray-900/50 border-gray-700">
        <CardHeader className="pb-3">
          <CardTitle className="text-lg text-violet-300 flex items-center gap-2">
            <Calendar className="w-5 h-5" /> Daily Standup
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
            <Select value={selectedProject || 'all'} onValueChange={(v) => setSelectedProject(v === 'all' ? null : v)}>
              <SelectTrigger className="flex-1 h-10 bg-gray-800 border-gray-600 text-white">
                <SelectValue placeholder="All Projects" />
              </SelectTrigger>
              <SelectContent className="bg-gray-800 border-gray-600 z-50">
                <SelectItem value="all">All Projects</SelectItem>
                {projects.map((p) => (
                  <SelectItem key={p.id} value={String(p.id)}>{p.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={reportType} onValueChange={setReportType}>
              <SelectTrigger className="w-[140px] h-10 bg-gray-800 border-gray-600 text-white">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-gray-800 border-gray-600 z-50">
                <SelectItem value="daily">Daily</SelectItem>
                <SelectItem value="weekly">Weekly</SelectItem>
              </SelectContent>
            </Select>
            <Button onClick={generateReport} disabled={loading} className="bg-violet-600 hover:bg-violet-700">
              {loading ? <><Loader2 className="w-4 h-4 animate-spin mr-2" /> Generating...</> : <><Calendar className="w-4 h-4 mr-2" /> Generate Report</>}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-violet-400" />
          <span className="ml-3 text-gray-400">Generating {reportType} standup report...</span>
        </div>
      )}

      {/* Empty State */}
      {!loading && !report && (
        <div className="flex flex-col items-center justify-center py-20 text-gray-500">
          <Calendar className="w-12 h-12 mb-3 text-gray-600" />
          <p className="text-sm">Select a project and click Generate to create a standup report.</p>
        </div>
      )}

      {/* Report */}
      {!loading && report && (
        <div className="space-y-4">
          {/* Summary Stats */}
          {report.summary && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <Card className="bg-gray-800 border-gray-700">
                <CardContent className="pt-4 text-center">
                  <Users className="w-5 h-5 mx-auto text-violet-400 mb-1" />
                  <div className="text-2xl font-bold text-white">{report.summary.total_members || 0}</div>
                  <div className="text-xs text-gray-400">Team Members</div>
                </CardContent>
              </Card>
              <Card className="bg-gray-800 border-gray-700">
                <CardContent className="pt-4 text-center">
                  <CheckCircle className="w-5 h-5 mx-auto text-green-400 mb-1" />
                  <div className="text-2xl font-bold text-green-400">{report.summary.active_members || 0}</div>
                  <div className="text-xs text-gray-400">Active</div>
                </CardContent>
              </Card>
              <Card className="bg-gray-800 border-gray-700">
                <CardContent className="pt-4 text-center">
                  <Clock className="w-5 h-5 mx-auto text-yellow-400 mb-1" />
                  <div className="text-2xl font-bold text-yellow-400">{(report.summary.inactive_members || []).length}</div>
                  <div className="text-xs text-gray-400">Inactive</div>
                </CardContent>
              </Card>
              <Card className="bg-gray-800 border-gray-700">
                <CardContent className="pt-4 text-center">
                  <AlertTriangle className="w-5 h-5 mx-auto text-red-400 mb-1" />
                  <div className="text-2xl font-bold text-red-400">{report.summary.total_blockers || 0}</div>
                  <div className="text-xs text-gray-400">Blockers</div>
                </CardContent>
              </Card>
            </div>
          )}

          {/* Report Content */}
          {report.report && (
            <Card className="bg-gray-800 border-gray-700">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-violet-300">
                  {reportType === 'daily' ? 'Daily' : 'Weekly'} Standup Report — {report.date || ''}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div
                  className="text-sm leading-relaxed"
                  dangerouslySetInnerHTML={{ __html: markdownToHtml(report.report) }}
                />
              </CardContent>
            </Card>
          )}

          {/* Weekly Stats */}
          {report.stats && (
            <Card className="bg-gray-800 border-gray-700">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-violet-300">Week Stats</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div>Total Tasks: <span className="font-bold text-white">{report.stats.total_tasks}</span></div>
                  <div>Completed: <span className="font-bold text-green-400">{report.stats.completed}</span></div>
                  <div>In Progress: <span className="font-bold text-blue-400">{report.stats.in_progress}</span></div>
                  <div>Blocked: <span className="font-bold text-red-400">{report.stats.blocked}</span></div>
                  <div className="col-span-2">Completion Rate: <span className="font-bold text-violet-400">{report.stats.completion_rate}%</span></div>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
