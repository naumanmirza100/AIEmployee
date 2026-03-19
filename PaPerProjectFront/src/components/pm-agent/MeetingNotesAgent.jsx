import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import pmAgentService from '@/services/pmAgentService';
import { companyApi } from '@/services/companyAuthService';
import { Loader2, FileText, CheckSquare, AlertTriangle, Users, Lightbulb } from 'lucide-react';

export default function MeetingNotesAgent() {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [meetingText, setMeetingText] = useState('');
  const [projects, setProjects] = useState([]);
  const [selectedProject, setSelectedProject] = useState(null);
  const [result, setResult] = useState(null);

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
      setResult(data);
    } catch (e) {
      toast({ title: 'Error', description: e.message || 'Failed to process notes', variant: 'destructive' });
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
            <FileText className="w-5 h-5" /> Meeting Notes Analyzer
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Select value={selectedProject || 'none'} onValueChange={(v) => setSelectedProject(v === 'none' ? null : v)}>
            <SelectTrigger className="h-10 bg-gray-800 border-gray-600 text-white">
              <SelectValue placeholder="Link to Project (optional)" />
            </SelectTrigger>
            <SelectContent className="bg-gray-800 border-gray-600 z-50">
              <SelectItem value="none">No Project</SelectItem>
              {projects.map((p) => (
                <SelectItem key={p.id} value={String(p.id)}>{p.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Textarea
            value={meetingText}
            onChange={(e) => setMeetingText(e.target.value)}
            placeholder="Paste your meeting notes or transcript here..."
            className="min-h-[120px] max-h-[250px] bg-gray-800 border-gray-600 text-sm text-white resize-y"
            rows={5}
          />
          <Button onClick={processMeeting} disabled={loading || !meetingText.trim()} className="w-full bg-violet-600 hover:bg-violet-700">
            {loading ? <><Loader2 className="w-4 h-4 animate-spin mr-2" /> Analyzing...</> : <><FileText className="w-4 h-4 mr-2" /> Analyze Meeting Notes</>}
          </Button>
        </CardContent>
      </Card>

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-violet-400" />
          <span className="ml-3 text-gray-400">Analyzing meeting notes...</span>
        </div>
      )}

      {/* Empty State */}
      {!loading && !result && (
        <div className="flex flex-col items-center justify-center py-20 text-gray-500">
          <FileText className="w-12 h-12 mb-3 text-gray-600" />
          <p className="text-sm text-center">Paste meeting notes above to extract action items, decisions, and summaries.</p>
        </div>
      )}

      {/* Results */}
      {!loading && result && (
        <div className="space-y-4">
          {/* Summary */}
          {result.summary && (
            <Card className="bg-gray-800 border-gray-700">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-violet-300 flex items-center gap-1">
                  <Lightbulb className="w-4 h-4" /> Summary
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-gray-300">{result.summary}</p>
              </CardContent>
            </Card>
          )}

          {/* Action Items */}
          {result.action_items?.length > 0 && (
            <Card className="bg-gray-800 border-gray-700">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-green-400 flex items-center gap-1">
                  <CheckSquare className="w-4 h-4" /> Action Items ({result.action_items.length})
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {result.action_items.map((item, i) => (
                  <div key={i} className="bg-gray-900 rounded p-3 text-sm">
                    <div className="font-medium text-white">{item.action}</div>
                    <div className="flex items-center gap-3 mt-1 text-xs text-gray-400">
                      <span>Owner: <span className="text-violet-300">{item.owner || 'TBD'}</span></span>
                      <span>Due: <span className="text-yellow-300">{item.deadline || 'TBD'}</span></span>
                      <span className={`px-1.5 py-0.5 rounded text-xs ${
                        item.priority === 'high' ? 'bg-red-900/50 text-red-300' :
                        item.priority === 'medium' ? 'bg-yellow-900/50 text-yellow-300' :
                        'bg-gray-700 text-gray-300'
                      }`}>{item.priority}</span>
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {/* Key Decisions */}
          {result.key_decisions?.length > 0 && (
            <Card className="bg-gray-800 border-gray-700">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-blue-400">Key Decisions ({result.key_decisions.length})</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1">
                {result.key_decisions.map((d, i) => (
                  <div key={i} className="text-sm text-gray-300 flex items-start gap-2">
                    <span className="text-blue-400">•</span>
                    <span>{d.decision || d}</span>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {/* Risks */}
          {result.risks_mentioned?.length > 0 && (
            <Card className="bg-gray-800 border-gray-700">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-red-400 flex items-center gap-1">
                  <AlertTriangle className="w-4 h-4" /> Risks ({result.risks_mentioned.length})
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-1">
                {result.risks_mentioned.map((r, i) => (
                  <div key={i} className="text-sm text-gray-300 flex items-start gap-2">
                    <span className="text-red-400">!</span>
                    <span>{r.risk || r} {r.severity && <span className="text-xs text-gray-500">({r.severity})</span>}</span>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {/* Participants */}
          {result.participants_detected?.length > 0 && (
            <Card className="bg-gray-800 border-gray-700">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-gray-400 flex items-center gap-1">
                  <Users className="w-4 h-4" /> Participants
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-2">
                  {result.participants_detected.map((p, i) => (
                    <span key={i} className="bg-gray-700 text-gray-300 text-xs px-2 py-1 rounded">{p}</span>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Fallback text answer */}
          {result.answer && !result.summary && (
            <Card className="bg-gray-800 border-gray-700">
              <CardContent className="pt-4">
                <p className="text-sm text-gray-300 whitespace-pre-wrap">{result.answer}</p>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
