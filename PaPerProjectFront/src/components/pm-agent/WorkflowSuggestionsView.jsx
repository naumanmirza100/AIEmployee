import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import pmAgentService from '@/services/pmAgentService';
import { companyApi } from '@/services/companyAuthService';
import { Loader2, Workflow, CheckSquare, ArrowRight, Lightbulb } from 'lucide-react';

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

const PHASES = [
  { value: 'planning', label: 'Planning' },
  { value: 'development', label: 'Development' },
  { value: 'testing', label: 'Testing' },
  { value: 'deployment', label: 'Deployment' },
  { value: 'maintenance', label: 'Maintenance' },
];

export default function WorkflowSuggestionsView() {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [checklistLoading, setChecklistLoading] = useState(false);
  const [projects, setProjects] = useState([]);
  const [selectedProject, setSelectedProject] = useState(null);
  const [phase, setPhase] = useState('development');
  const [workflow, setWorkflow] = useState(null);
  const [checklist, setChecklist] = useState(null);

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

  const fetchWorkflow = async () => {
    if (!selectedProject) {
      toast({ title: 'Error', description: 'Please select a project first.', variant: 'destructive' });
      return;
    }
    setLoading(true);
    setWorkflow(null);
    try {
      const res = await pmAgentService.workflowSuggest(selectedProject, 'suggest', phase);
      const data = res?.data?.data || res?.data || {};
      setWorkflow(data);
    } catch (e) {
      toast({ title: 'Error', description: e.message || 'Failed to get suggestions', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  const fetchChecklist = async () => {
    if (!selectedProject) {
      toast({ title: 'Error', description: 'Please select a project first.', variant: 'destructive' });
      return;
    }
    setChecklistLoading(true);
    setChecklist(null);
    try {
      const res = await pmAgentService.workflowSuggest(selectedProject, 'checklist', phase);
      const data = res?.data?.data || res?.data || {};
      setChecklist(data);
    } catch (e) {
      toast({ title: 'Error', description: e.message || 'Failed to generate checklist', variant: 'destructive' });
    } finally {
      setChecklistLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Controls */}
      <Card className="bg-gray-900/50 border-gray-700">
        <CardHeader className="pb-3">
          <CardTitle className="text-lg text-violet-300 flex items-center gap-2">
            <Workflow className="w-5 h-5" /> Workflow & SOP Suggestions
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
            <Select value={phase} onValueChange={setPhase}>
              <SelectTrigger className="w-[160px] h-10 bg-gray-800 border-gray-600 text-white">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-gray-800 border-gray-600 z-50">
                {PHASES.map((p) => (
                  <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button onClick={fetchWorkflow} disabled={loading || !selectedProject} className="bg-violet-600 hover:bg-violet-700">
              {loading ? <><Loader2 className="w-4 h-4 animate-spin mr-2" /> Loading...</> : <><Lightbulb className="w-4 h-4 mr-2" /> Get Suggestions</>}
            </Button>
            <Button onClick={fetchChecklist} disabled={checklistLoading || !selectedProject} variant="outline" className="border-violet-600 text-violet-300 hover:bg-violet-600/20">
              {checklistLoading ? <><Loader2 className="w-4 h-4 animate-spin mr-2" /> Loading...</> : <><CheckSquare className="w-4 h-4 mr-2" /> Checklist</>}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Loading */}
      {(loading || checklistLoading) && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-violet-400" />
          <span className="ml-3 text-gray-400">{loading ? 'Generating workflow suggestions...' : 'Creating checklist...'}</span>
        </div>
      )}

      {/* Workflow Suggestions */}
      {!loading && workflow && (
        <div className="space-y-4">
          {/* Steps */}
          {workflow.steps?.length > 0 && (
            <Card className="bg-gray-800 border-gray-700">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-violet-300">Suggested Workflow Steps</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {workflow.steps.map((step, i) => (
                  <div key={i} className="flex items-start gap-3 bg-gray-900 rounded-lg p-3">
                    <div className="w-6 h-6 rounded-full bg-violet-600/30 flex items-center justify-center text-xs font-bold text-violet-300 shrink-0 mt-0.5">
                      {i + 1}
                    </div>
                    <div className="flex-1">
                      <div className="text-sm font-medium text-white">{step.title || step.name || step.step || (typeof step === 'string' ? step : '')}</div>
                      {step.description && <div className="text-xs text-gray-400 mt-1">{step.description}</div>}
                      {step.tools && <div className="text-xs text-violet-400 mt-1">Tools: {Array.isArray(step.tools) ? step.tools.join(', ') : step.tools}</div>}
                    </div>
                    {i < workflow.steps.length - 1 && <ArrowRight className="w-4 h-4 text-gray-600 shrink-0 mt-1" />}
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {/* Best Practices */}
          {workflow.best_practices?.length > 0 && (
            <Card className="bg-gray-800 border-gray-700">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-green-400">Best Practices</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1">
                {workflow.best_practices.map((bp, i) => (
                  <div key={i} className="text-sm text-gray-300 flex items-start gap-2">
                    <span className="text-green-400">•</span>
                    <span>{typeof bp === 'string' ? bp : bp.text || bp.practice || JSON.stringify(bp)}</span>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {/* Fallback markdown */}
          {(workflow.answer || workflow.report || workflow.suggestions) && !workflow.steps && (
            <Card className="bg-gray-800 border-gray-700">
              <CardContent className="pt-4">
                <div className="text-sm leading-relaxed" dangerouslySetInnerHTML={{ __html: markdownToHtml(workflow.answer || workflow.report || workflow.suggestions) }} />
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* Checklist */}
      {!checklistLoading && checklist && (
        <Card className="bg-gray-800 border-gray-700">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-yellow-400 flex items-center gap-1">
              <CheckSquare className="w-4 h-4" /> Phase Checklist — {phase}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {checklist.checklist?.length > 0 ? (
              <div className="space-y-1">
                {checklist.checklist.map((item, i) => (
                  <div key={i} className="text-sm text-gray-300 flex items-start gap-2">
                    <CheckSquare className="w-4 h-4 text-yellow-400 shrink-0 mt-0.5" />
                    <span>{typeof item === 'string' ? item : item.text || item.item || JSON.stringify(item)}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-sm leading-relaxed" dangerouslySetInnerHTML={{ __html: markdownToHtml(checklist.answer || checklist.report || JSON.stringify(checklist, null, 2)) }} />
            )}
          </CardContent>
        </Card>
      )}

      {/* Empty State */}
      {!loading && !checklistLoading && !workflow && !checklist && (
        <div className="flex flex-col items-center justify-center py-20 text-gray-500">
          <Workflow className="w-12 h-12 mb-3 text-gray-600" />
          <p className="text-sm text-center">Select a project and phase to get AI-powered workflow suggestions and checklists.</p>
        </div>
      )}
    </div>
  );
}
