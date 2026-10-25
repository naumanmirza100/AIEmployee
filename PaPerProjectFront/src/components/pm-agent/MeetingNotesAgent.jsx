import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useToast } from '@/components/ui/use-toast';
import pmAgentService from '@/services/pmAgentService';
import { apiErrorMessage, toastForError } from '@/utils/apiErrorMessage';
import { companyApi } from '@/services/companyAuthService';
import { Loader2, FileText, CheckSquare, AlertTriangle, Users, Lightbulb, ListPlus, History, ClipboardList } from 'lucide-react';
import ProjectRecordView from './ProjectRecordView';

export default function MeetingNotesAgent() {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [meetingText, setMeetingText] = useState('');
  const [projects, setProjects] = useState([]);
  const [selectedProject, setSelectedProject] = useState(null);
  const [result, setResult] = useState(null);
  // Notes analysed against a project are kept on it (project_manager_agent/tool_results.py).
  const [savedNotes, setSavedNotes] = useState([]);
  const [ticked, setTicked] = useState(new Set());
  const [creatingTasks, setCreatingTasks] = useState(false);
  // Analyze notes (paste a meeting's notes) or Project record (what was decided and done on the project).
  const [tab, setTab] = useState('analyze');

  const loadSaved = (projectId) => {
    if (!projectId) { setSavedNotes([]); return; }
    pmAgentService.getSavedMeetingNotes(projectId)
      .then((res) => setSavedNotes(Array.isArray(res?.data) ? res.data : []))
      .catch(() => setSavedNotes([]));
  };

  useEffect(() => { loadSaved(selectedProject); }, [selectedProject]);

  const show = (data) => {
    setResult(data);
    setTicked(new Set((data?.action_items || []).map((_, i) => i)));
  };

  const createTasks = async () => {
    const items = (result?.action_items || []).filter((_, i) => ticked.has(i));
    if (!items.length || !selectedProject) return;
    setCreatingTasks(true);
    try {
      const res = await pmAgentService.tasksFromSuggestions(selectedProject, items.map((it) => ({
        title: it.action, priority: it.priority, assignee_name: it.owner, due: it.deadline,
        description: 'From meeting notes',
      })));
      const made = res?.data?.created || [];
      const owned = made.filter((t) => t.assignee_id).length;
      const problems = res?.data?.problems || [];
      toast({
        title: `${made.length} task${made.length === 1 ? '' : 's'} added to the project`,
        description: [
          made.length ? `${owned} with an owner matched by name.` : '',
          problems.length ? `${problems.length} could not be added: ${problems[0].message}` : '',
        ].filter(Boolean).join(' ') || undefined,
      });
    } catch (e) {
      toast({ title: 'Could not create tasks', description: apiErrorMessage(e, ''), variant: 'destructive' });
    } finally {
      setCreatingTasks(false);
    }
  };

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

  const processMeeting = async () => {
    if (!meetingText.trim()) {
      toast({ title: 'Error', description: 'Please paste meeting notes first.', variant: 'destructive' });
      return;
    }
    setLoading(true);
    setResult(null);
    try {
      const res = await pmAgentService.meetingNotes(meetingText, selectedProject, 'summarize');
      const data = res?.data?.data || res?.data || {};
      show(data);
      if (data.saved_id) loadSaved(selectedProject);
    } catch (e) {
      toast({ title: 'Error', description: apiErrorMessage(e, 'Failed to process notes'), variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList className="bg-white/[0.04]">
            <TabsTrigger value="analyze" data-testid="tab-analyze" className="text-xs sm:text-sm">
              <FileText className="w-4 h-4 mr-1.5" /> Analyze notes
            </TabsTrigger>
            <TabsTrigger value="record" data-testid="tab-record" className="text-xs sm:text-sm">
              <ClipboardList className="w-4 h-4 mr-1.5" /> Project record
            </TabsTrigger>
          </TabsList>
        </Tabs>
        <Select value={selectedProject || 'none'} onValueChange={(v) => setSelectedProject(v === 'none' ? null : v)}>
          <SelectTrigger className="h-10 sm:w-80 bg-white/[0.02] border-white/[0.08] text-white text-left [&>span]:line-clamp-1" data-testid="meeting-notes-project">
            <SelectValue placeholder={tab === 'record' ? 'Choose a project' : 'Link to Project (optional)'} />
          </SelectTrigger>
          <SelectContent className="bg-white/[0.02] border-white/[0.08] z-50">
            <SelectItem value="none">{tab === 'record' ? 'Choose a project' : 'No Project'}</SelectItem>
            {projects.map((p) => (
              <SelectItem key={p.id} value={String(p.id)}>{p.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {tab === 'record' ? <ProjectRecordView projectId={selectedProject} /> : (
    <div className="space-y-6">
      {/* Controls */}
      <Card className="bg-black/30 border-white/[0.06]">
        <CardHeader className="pb-3">
          <CardTitle className="text-lg text-violet-300 flex items-center gap-2">
            <FileText className="w-5 h-5" /> Meeting Notes Analyzer
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Textarea
            value={meetingText}
            onChange={(e) => setMeetingText(e.target.value)}
            placeholder="Paste your meeting notes or transcript here..."
            className="min-h-[120px] max-h-[250px] bg-white/[0.02] border-white/[0.08] text-sm text-white resize-y"
            rows={5}
          />
          <Button onClick={processMeeting} disabled={loading || !meetingText.trim()} className="w-full bg-violet-600 hover:bg-violet-700">
            {loading ? <><Loader2 className="w-4 h-4 animate-spin mr-2" /> Analyzing...</> : <><FileText className="w-4 h-4 mr-2" /> Analyze Meeting Notes</>}
          </Button>
        </CardContent>
      </Card>

      {/* Earlier meetings kept on this project */}
      {savedNotes.length > 0 && (
        <Card className="bg-white/[0.02] border-white/[0.06]">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-white/70 flex items-center gap-1">
              <History className="w-4 h-4" /> Earlier meetings on this project
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {savedNotes.slice(0, 12).map((n) => (
              <Button key={n.id} size="sm" variant="outline" className="h-7 text-xs" onClick={() => show(n.result)}>
                {n.topic || 'Meeting'} · {n.date || n.saved_at?.slice(0, 10)}
              </Button>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-violet-400" />
          <span className="ml-3 text-white/55">Analyzing meeting notes...</span>
        </div>
      )}

      {/* Empty State */}
      {!loading && !result && (
        <div className="flex flex-col items-center justify-center py-20 text-white/40">
          <FileText className="w-12 h-12 mb-3 text-white/35" />
          <p className="text-sm text-center">Paste meeting notes above to extract action items, decisions, and summaries.</p>
        </div>
      )}

      {/* Validation Error with Instructions */}
      {!loading && result && result.success === false && result.instructions && (
        <Card className="bg-white/[0.02] border-amber-600/50">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-amber-400 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4" /> {result.error}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-white/65 whitespace-pre-wrap">{result.instructions}</p>
          </CardContent>
        </Card>
      )}

      {/* Results */}
      {!loading && result && result.success !== false && (
        <div className="space-y-4">
          {/* Warnings (unrecognized participants) */}
          {result.warnings?.length > 0 && (
            <Card className="bg-amber-900/20 border-amber-600/50">
              <CardContent className="pt-4">
                {result.warnings.map((w, i) => (
                  <div key={i} className="flex items-start gap-2 text-sm text-amber-300">
                    <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
                    <span>{w}</span>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {/* Summary */}
          {result.summary && (
            <Card className="bg-white/[0.02] border-white/[0.06]">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-violet-300 flex items-center gap-1">
                  <Lightbulb className="w-4 h-4" /> Summary
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-white/65">{result.summary}</p>
              </CardContent>
            </Card>
          )}

          {/* Action Items */}
          {result.action_items?.length > 0 && (
            <Card className="bg-white/[0.02] border-white/[0.06]">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-emerald-400 flex items-center gap-1">
                  <CheckSquare className="w-4 h-4" /> Action Items ({result.action_items.length})
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {selectedProject && (
                  <div className="flex justify-end">
                    <Button size="sm" variant="outline" className="h-7 text-xs" disabled={creatingTasks || !ticked.size} onClick={createTasks}>
                      {creatingTasks ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <ListPlus className="w-3 h-3 mr-1" />}
                      Create {ticked.size} task{ticked.size === 1 ? '' : 's'} in the project
                    </Button>
                  </div>
                )}
                {result.action_items.map((item, i) => (
                  <div key={i} className="bg-black/30 rounded p-3 text-sm">
                    <div className="font-medium text-white flex items-start gap-2">
                      {selectedProject && (
                        <input
                          type="checkbox" className="mt-1 h-3.5 w-3.5 accent-violet-500"
                          checked={ticked.has(i)}
                          onChange={() => setTicked((prev) => { const next = new Set(prev); if (next.has(i)) next.delete(i); else next.add(i); return next; })}
                          aria-label={`Make "${item.action}" a task`}
                        />
                      )}
                      <span>{item.action}</span>
                    </div>
                    <div className="flex items-center gap-3 mt-1 text-xs text-white/55">
                      <span>Owner: <span className="text-violet-300">{item.owner || 'TBD'}</span></span>
                      <span>Due: <span className="text-amber-300">{item.deadline || 'TBD'}</span></span>
                      <span className={`px-1.5 py-0.5 rounded text-xs ${
                        item.priority === 'high' ? 'bg-red-900/50 text-red-300' :
                        item.priority === 'medium' ? 'bg-amber-900/50 text-amber-300' :
                        'bg-white/[0.05] text-white/65'
                      }`}>{item.priority}</span>
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {/* Key Decisions */}
          {result.key_decisions?.length > 0 && (
            <Card className="bg-white/[0.02] border-white/[0.06]">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-violet-400">Key Decisions ({result.key_decisions.length})</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1">
                {result.key_decisions.map((d, i) => (
                  <div key={i} className="text-sm text-white/65 flex items-start gap-2">
                    <span className="text-violet-400">•</span>
                    <span>{d.decision || d}</span>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {/* Risks */}
          {result.risks_mentioned?.length > 0 && (
            <Card className="bg-white/[0.02] border-white/[0.06]">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-red-400 flex items-center gap-1">
                  <AlertTriangle className="w-4 h-4" /> Risks ({result.risks_mentioned.length})
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-1">
                {result.risks_mentioned.map((r, i) => (
                  <div key={i} className="text-sm text-white/65 flex items-start gap-2">
                    <span className="text-red-400">!</span>
                    <span>{r.risk || r} {r.severity && <span className="text-xs text-white/40">({r.severity})</span>}</span>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {/* Participants */}
          {result.participants_detected?.length > 0 && (
            <Card className="bg-white/[0.02] border-white/[0.06]">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-white/55 flex items-center gap-1">
                  <Users className="w-4 h-4" /> Participants
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-2">
                  {result.participants_detected.map((p, i) => (
                    <span key={i} className="bg-white/[0.05] text-white/65 text-xs px-2 py-1 rounded">{p}</span>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Fallback text answer */}
          {result.answer && !result.summary && (
            <Card className="bg-white/[0.02] border-white/[0.06]">
              <CardContent className="pt-4">
                <p className="text-sm text-white/65 whitespace-pre-wrap">{result.answer}</p>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
      )}
    </div>
  );
}
