import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import pmAgentService from '@/services/pmAgentService';
import { companyApi } from '@/services/companyAuthService';
import { Loader2, CalendarDays, AlertTriangle, Clock, User } from 'lucide-react';

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

const priorityColors = {
  high: 'border-l-red-500',
  medium: 'border-l-yellow-500',
  low: 'border-l-green-500',
};

export default function CalendarScheduleView() {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [projects, setProjects] = useState([]);
  const [selectedProject, setSelectedProject] = useState(null);
  const [schedule, setSchedule] = useState(null);

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

  const fetchSchedule = async () => {
    if (!selectedProject) {
      toast({ title: 'Error', description: 'Please select a project first.', variant: 'destructive' });
      return;
    }
    setLoading(true);
    setSchedule(null);
    try {
      const res = await pmAgentService.calendarSchedule(selectedProject);
      const data = res?.data?.data || res?.data || {};
      setSchedule(data);
    } catch (e) {
      toast({ title: 'Error', description: e.message || 'Failed to generate schedule', variant: 'destructive' });
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
            <CalendarDays className="w-5 h-5" /> Calendar & Schedule Planner
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
            <Button onClick={fetchSchedule} disabled={loading || !selectedProject} className="bg-violet-600 hover:bg-violet-700">
              {loading ? <><Loader2 className="w-4 h-4 animate-spin mr-2" /> Generating...</> : <><CalendarDays className="w-4 h-4 mr-2" /> Generate Schedule</>}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-violet-400" />
          <span className="ml-3 text-gray-400">Generating optimized schedule...</span>
        </div>
      )}

      {/* Results */}
      {!loading && schedule && (
        <div className="space-y-4">
          {/* Day-by-Day Schedule */}
          {schedule.schedule?.length > 0 && (
            <div className="space-y-3">
              {schedule.schedule.map((day, i) => (
                <Card key={i} className="bg-gray-800 border-gray-700">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm text-violet-300">{day.date || day.day || `Day ${i + 1}`}</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    {(day.tasks || day.items || []).map((task, j) => (
                      <div key={j} className={`bg-gray-900 rounded p-2 text-sm border-l-2 ${priorityColors[task.priority] || 'border-l-gray-600'}`}>
                        <div className="flex items-center justify-between">
                          <span className="font-medium text-white">{task.title || task.task || task.name}</span>
                          {task.time && <span className="text-xs text-gray-400 flex items-center gap-1"><Clock className="w-3 h-3" />{task.time}</span>}
                        </div>
                        <div className="flex items-center gap-3 mt-1 text-xs text-gray-400">
                          {task.assignee && <span className="flex items-center gap-1"><User className="w-3 h-3" />{task.assignee}</span>}
                          {task.duration && <span>{task.duration}</span>}
                          {task.priority && <span className={`px-1.5 py-0.5 rounded ${task.priority === 'high' ? 'bg-red-900/50 text-red-300' : task.priority === 'medium' ? 'bg-yellow-900/50 text-yellow-300' : 'bg-gray-700 text-gray-300'}`}>{task.priority}</span>}
                        </div>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              ))}
            </div>
          )}

          {/* Conflicts */}
          {schedule.conflicts?.length > 0 && (
            <Card className="bg-gray-800 border-gray-700">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-yellow-400 flex items-center gap-1">
                  <AlertTriangle className="w-4 h-4" /> Scheduling Conflicts ({schedule.conflicts.length})
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {schedule.conflicts.map((conflict, i) => (
                  <div key={i} className="bg-yellow-900/20 border border-yellow-700 rounded p-2 text-sm text-gray-300">
                    {typeof conflict === 'string' ? conflict : conflict.description || conflict.message || JSON.stringify(conflict)}
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {/* Fallback markdown */}
          {(schedule.answer || schedule.report) && !schedule.schedule && (
            <Card className="bg-gray-800 border-gray-700">
              <CardContent className="pt-4">
                <div className="text-sm leading-relaxed" dangerouslySetInnerHTML={{ __html: markdownToHtml(schedule.answer || schedule.report) }} />
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* Empty State */}
      {!loading && !schedule && (
        <div className="flex flex-col items-center justify-center py-20 text-gray-500">
          <CalendarDays className="w-12 h-12 mb-3 text-gray-600" />
          <p className="text-sm text-center">Select a project to generate an AI-optimized schedule for your team.</p>
        </div>
      )}
    </div>
  );
}
