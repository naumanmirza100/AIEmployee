import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import pmAgentService from '@/services/pmAgentService';
import { companyApi } from '@/services/companyAuthService';
import { Loader2, Clock, AlertTriangle, CheckCircle, Timer } from 'lucide-react';

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

const complexityColors = {
  low: 'bg-green-900/30 text-green-400 border-green-700',
  medium: 'bg-yellow-900/30 text-yellow-400 border-yellow-700',
  high: 'bg-orange-900/30 text-orange-400 border-orange-700',
  critical: 'bg-red-900/30 text-red-400 border-red-700',
};

export default function TimeEstimationView() {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [projects, setProjects] = useState([]);
  const [selectedProject, setSelectedProject] = useState(null);
  const [estimation, setEstimation] = useState(null);

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

  const fetchEstimation = async () => {
    if (!selectedProject) {
      toast({ title: 'Error', description: 'Please select a project first.', variant: 'destructive' });
      return;
    }
    setLoading(true);
    setEstimation(null);
    try {
      const res = await pmAgentService.timeEstimation(selectedProject);
      const data = res?.data?.data || res?.data || {};
      setEstimation(data);
    } catch (e) {
      toast({ title: 'Error', description: e.message || 'Failed to estimate time', variant: 'destructive' });
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
            <Timer className="w-5 h-5" /> AI Time Estimation
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
            <Button onClick={fetchEstimation} disabled={loading || !selectedProject} className="bg-violet-600 hover:bg-violet-700">
              {loading ? <><Loader2 className="w-4 h-4 animate-spin mr-2" /> Estimating...</> : <><Clock className="w-4 h-4 mr-2" /> Estimate Time</>}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-violet-400" />
          <span className="ml-3 text-gray-400">AI is estimating task durations...</span>
        </div>
      )}

      {/* Results */}
      {!loading && estimation && (
        <div className="space-y-4">
          {/* Summary */}
          {(estimation.total_hours || estimation.total_days) && (
            <Card className="bg-violet-900/20 border-violet-700">
              <CardContent className="pt-6">
                <div className="flex items-center justify-center gap-8">
                  <div className="text-center">
                    <div className="text-3xl font-bold text-violet-300">{estimation.total_hours || '—'}</div>
                    <div className="text-sm text-gray-400">Total Hours</div>
                  </div>
                  <div className="h-12 w-px bg-gray-700" />
                  <div className="text-center">
                    <div className="text-3xl font-bold text-violet-300">{estimation.total_days || '—'}</div>
                    <div className="text-sm text-gray-400">Total Days</div>
                  </div>
                  {estimation.confidence && (
                    <>
                      <div className="h-12 w-px bg-gray-700" />
                      <div className="text-center">
                        <div className="text-3xl font-bold text-green-400">{estimation.confidence}%</div>
                        <div className="text-sm text-gray-400">Confidence</div>
                      </div>
                    </>
                  )}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Task Estimates */}
          {estimation.task_estimates?.length > 0 && (
            <Card className="bg-gray-800 border-gray-700">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-violet-300">Task-by-Task Estimates ({estimation.task_estimates.length})</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {estimation.task_estimates.map((task, i) => (
                  <div key={i} className="bg-gray-900 rounded-lg p-3">
                    <div className="flex items-center justify-between mb-2">
                      <div className="text-sm font-medium text-white flex-1 mr-2">{task.task || task.title || task.name}</div>
                      <div className="flex items-center gap-2 shrink-0">
                        {task.complexity && (
                          <span className={`text-xs px-2 py-0.5 rounded border ${complexityColors[task.complexity] || complexityColors.medium}`}>
                            {task.complexity}
                          </span>
                        )}
                        <span className="text-sm font-bold text-violet-300">{task.hours || task.estimated_hours}h</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-4 text-xs text-gray-400">
                      {task.days && <span>{task.days} days</span>}
                      {task.confidence && <span>Confidence: {task.confidence}%</span>}
                      {task.assignee && <span>Assignee: <span className="text-violet-300">{task.assignee}</span></span>}
                    </div>
                    {task.risk_factors?.length > 0 && (
                      <div className="mt-2 flex items-start gap-1 text-xs text-yellow-400">
                        <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />
                        <span>{task.risk_factors.join(', ')}</span>
                      </div>
                    )}
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {/* Fallback markdown */}
          {(estimation.answer || estimation.report) && !estimation.task_estimates && (
            <Card className="bg-gray-800 border-gray-700">
              <CardContent className="pt-4">
                <div className="text-sm leading-relaxed" dangerouslySetInnerHTML={{ __html: markdownToHtml(estimation.answer || estimation.report) }} />
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* Empty State */}
      {!loading && !estimation && (
        <div className="flex flex-col items-center justify-center py-20 text-gray-500">
          <Timer className="w-12 h-12 mb-3 text-gray-600" />
          <p className="text-sm text-center">Select a project to get AI-powered time estimates for all tasks.</p>
        </div>
      )}
    </div>
  );
}
