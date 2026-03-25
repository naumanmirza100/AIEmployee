import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import pmAgentService from '@/services/pmAgentService';
import { companyApi } from '@/services/companyAuthService';
import { Loader2, Users, Trophy, TrendingUp, AlertTriangle, BarChart3 } from 'lucide-react';

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

export default function TeamPerformanceDashboard() {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [projects, setProjects] = useState([]);
  const [selectedProject, setSelectedProject] = useState(null);
  const [performance, setPerformance] = useState(null);

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

  const fetchPerformance = async () => {
    if (!selectedProject) {
      toast({ title: 'Error', description: 'Please select a project first.', variant: 'destructive' });
      return;
    }
    setLoading(true);
    setPerformance(null);
    try {
      const res = await pmAgentService.teamPerformance(selectedProject);
      const data = res?.data?.data || res?.data || {};
      setPerformance(data);
    } catch (e) {
      toast({ title: 'Error', description: e.message || 'Failed to analyze team performance', variant: 'destructive' });
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
            <Users className="w-5 h-5" /> Team Performance Analytics
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
            <Button onClick={fetchPerformance} disabled={loading || !selectedProject} className="bg-violet-600 hover:bg-violet-700">
              {loading ? <><Loader2 className="w-4 h-4 animate-spin mr-2" /> Analyzing...</> : <><BarChart3 className="w-4 h-4 mr-2" /> Analyze Team</>}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-violet-400" />
          <span className="ml-3 text-gray-400">Analyzing team performance...</span>
        </div>
      )}

      {/* Results */}
      {!loading && performance && (
        <div className="space-y-4">
          {/* Summary Stats Bar */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <Card className="bg-gray-800/60 border-gray-700">
              <CardContent className="p-3 text-center">
                <div className="text-2xl font-bold text-violet-300">{performance.total_members || 0}</div>
                <div className="text-xs text-gray-400">Team Members</div>
              </CardContent>
            </Card>
            <Card className="bg-gray-800/60 border-gray-700">
              <CardContent className="p-3 text-center">
                <div className="text-2xl font-bold text-blue-300">{performance.total_tasks || 0}</div>
                <div className="text-xs text-gray-400">Total Tasks</div>
              </CardContent>
            </Card>
            <Card className="bg-gray-800/60 border-gray-700">
              <CardContent className="p-3 text-center">
                <div className="text-2xl font-bold text-green-400">{performance.overall_completion_rate || 0}%</div>
                <div className="text-xs text-gray-400">Completion Rate</div>
              </CardContent>
            </Card>
            <Card className="bg-gray-800/60 border-gray-700">
              <CardContent className="p-3 text-center">
                <div className="text-2xl font-bold text-yellow-400">{performance.unassigned_tasks || 0}</div>
                <div className="text-xs text-gray-400">Unassigned</div>
              </CardContent>
            </Card>
          </div>

          {/* Member Cards */}
          {performance.members?.length > 0 && (
            <div className="space-y-3">
              {performance.members.map((member, i) => {
                const workloadColor = member.workload === 'Overloaded' ? 'text-red-400 bg-red-500/10' :
                                      member.workload === 'Underloaded' ? 'text-yellow-400 bg-yellow-500/10' :
                                      'text-green-400 bg-green-500/10';
                return (
                  <Card key={i} className="bg-gray-800 border-gray-700">
                    <CardContent className="pt-4">
                      {/* Header: Avatar, Name, Score, Workload Badge */}
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-full bg-violet-600/30 flex items-center justify-center text-sm font-bold text-violet-300">
                            {(member.name || 'U')[0].toUpperCase()}
                          </div>
                          <div>
                            <div className="text-sm font-medium text-white">{member.name || 'Unknown'}</div>
                            <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${workloadColor}`}>
                              {member.workload || 'Balanced'}
                            </span>
                          </div>
                        </div>
                        <div className="text-right">
                          <div className={`text-2xl font-bold ${member.score >= 80 ? 'text-green-400' : member.score >= 60 ? 'text-yellow-400' : 'text-red-400'}`}>
                            {member.score ?? 0}
                          </div>
                          <div className="text-[10px] text-gray-500">SCORE</div>
                        </div>
                      </div>

                      {/* Stats Grid */}
                      <div className="grid grid-cols-3 sm:grid-cols-6 gap-2 text-xs mb-3">
                        <div className="bg-gray-900 rounded p-2 text-center">
                          <div className="text-white font-bold">{member.total_tasks || 0}</div>
                          <div className="text-gray-500">Total</div>
                        </div>
                        <div className="bg-gray-900 rounded p-2 text-center">
                          <div className="text-green-400 font-bold">{member.tasks_completed || 0}</div>
                          <div className="text-gray-500">Done</div>
                        </div>
                        <div className="bg-gray-900 rounded p-2 text-center">
                          <div className="text-blue-400 font-bold">{member.tasks_in_progress || 0}</div>
                          <div className="text-gray-500">In Progress</div>
                        </div>
                        <div className="bg-gray-900 rounded p-2 text-center">
                          <div className="text-gray-300 font-bold">{member.tasks_todo || 0}</div>
                          <div className="text-gray-500">To Do</div>
                        </div>
                        <div className="bg-gray-900 rounded p-2 text-center">
                          <div className="text-red-400 font-bold">{member.overdue || 0}</div>
                          <div className="text-gray-500">Overdue</div>
                        </div>
                        <div className="bg-gray-900 rounded p-2 text-center">
                          <div className="text-orange-400 font-bold">{member.blocked || 0}</div>
                          <div className="text-gray-500">Blocked</div>
                        </div>
                      </div>

                      {/* Completion Progress Bar */}
                      <div className="mb-2">
                        <div className="flex justify-between text-[10px] text-gray-400 mb-1">
                          <span>Completion</span>
                          <span>{member.completion_rate || 0}%</span>
                        </div>
                        <div className="w-full h-1.5 bg-gray-700 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full transition-all ${member.completion_rate >= 80 ? 'bg-green-500' : member.completion_rate >= 50 ? 'bg-yellow-500' : 'bg-red-500'}`}
                            style={{ width: `${member.completion_rate || 0}%` }}
                          />
                        </div>
                      </div>

                      {/* Task Titles */}
                      {member.task_titles?.length > 0 && (
                        <div className="mt-2 pt-2 border-t border-gray-700/50">
                          <div className="text-[10px] text-gray-500 mb-1">Assigned Tasks:</div>
                          <div className="flex flex-wrap gap-1">
                            {member.task_titles.map((title, ti) => (
                              <span key={ti} className="text-[10px] px-2 py-0.5 bg-gray-900 text-gray-300 rounded">
                                {title.length > 30 ? title.slice(0, 30) + '...' : title}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )}

          {/* Insights */}
          {performance.insights?.length > 0 && (
            <Card className="bg-gray-800 border-gray-700">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-violet-300 flex items-center gap-1">
                  <TrendingUp className="w-4 h-4" /> Insights
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-1.5">
                  {performance.insights.map((insight, i) => (
                    <div key={i} className="text-sm text-gray-300 flex items-start gap-2">
                      <span className="text-violet-400 mt-0.5">•</span>
                      <span>{typeof insight === 'string' ? insight : insight.text || JSON.stringify(insight)}</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Recommendations */}
          {performance.recommendations?.length > 0 && (
            <Card className="bg-gray-800 border-gray-700">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-green-400 flex items-center gap-1">
                  <Trophy className="w-4 h-4" /> Recommendations
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-1.5">
                {performance.recommendations.map((rec, i) => (
                  <div key={i} className="text-sm text-gray-300 flex items-start gap-2">
                    <span className="text-green-400 mt-0.5">•</span>
                    <span>{typeof rec === 'string' ? rec : rec.text || rec.recommendation || JSON.stringify(rec)}</span>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* Empty State */}
      {!loading && !performance && (
        <div className="flex flex-col items-center justify-center py-20 text-gray-500">
          <Users className="w-12 h-12 mb-3 text-gray-600" />
          <p className="text-sm text-center">Select a project and click Analyze Team to view performance metrics.</p>
        </div>
      )}
    </div>
  );
}
