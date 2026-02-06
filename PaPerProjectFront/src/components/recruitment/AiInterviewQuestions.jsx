import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/components/ui/use-toast';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Loader2, HelpCircle, Copy, Printer } from 'lucide-react';
import { getJobDescriptions, getCVRecords, suggestInterviewQuestions } from '@/services/recruitmentAgentService';

const AiInterviewQuestions = () => {
  const { toast } = useToast();
  const [jobs, setJobs] = useState([]);
  const [candidates, setCandidates] = useState([]);
  const [selectedJobId, setSelectedJobId] = useState('');
  const [selectedCvId, setSelectedCvId] = useState('');
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [questions, setQuestions] = useState([]);
  const [meta, setMeta] = useState(null);

  useEffect(() => {
    getJobDescriptions()
      .then((res) => {
        const data = res?.data !== undefined ? res.data : res;
        setJobs(Array.isArray(data) ? data : (data?.data || []));
      })
      .catch(() => setJobs([]));
  }, []);

  useEffect(() => {
    if (!selectedJobId) {
      setCandidates([]);
      setSelectedCvId('');
      return;
    }
    setLoading(true);
    getCVRecords({ job_id: selectedJobId })
      .then((res) => {
        const data = res?.data !== undefined ? res.data : res;
        const list = Array.isArray(data) ? data : (data?.data || []);
        setCandidates(list);
        setSelectedCvId('');
        setQuestions([]);
        setMeta(null);
      })
      .catch(() => setCandidates([]))
      .finally(() => setLoading(false));
  }, [selectedJobId]);

  const handleGenerate = async () => {
    if (!selectedJobId || !selectedCvId) {
      toast({ title: 'Select job and candidate', variant: 'destructive' });
      return;
    }
    setGenerating(true);
    setQuestions([]);
    setMeta(null);
    try {
      const res = await suggestInterviewQuestions(Number(selectedCvId), Number(selectedJobId));
      const data = res?.data !== undefined ? res.data : res;
      if (data?.status === 'success' && Array.isArray(data.questions)) {
        setQuestions(data.questions);
        setMeta({ candidate_name: data.candidate_name, job_title: data.job_title });
        toast({ title: 'Questions generated', description: `${data.questions.length} questions ready.` });
      } else {
        toast({ title: 'Generation failed', description: data?.message || 'No questions returned.', variant: 'destructive' });
      }
    } catch (err) {
      const msg = err?.data?.message || err?.message || 'Failed to generate questions.';
      toast({ title: 'Error', description: msg, variant: 'destructive' });
    } finally {
      setGenerating(false);
    }
  };

  const copyAll = () => {
    const text = questions
      .map((q) => `[${q.type}]\n${q.question}`)
      .join('\n\n');
    navigator.clipboard.writeText(text).then(() => toast({ title: 'Copied to clipboard' }));
  };

  const printAll = () => {
    const candidateName = meta?.candidate_name || 'Candidate';
    const jobTitle = meta?.job_title || 'Position';
    const title = `${candidateName} – ${jobTitle}`;
    const dateStr = new Date().toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });
    const questionsHtml = questions
      .map(
        (q, i) => `
        <tr>
          <td class="num">${i + 1}</td>
          <td class="type ${q.type}">${q.type}</td>
          <td class="question">${String(q.question).replace(/</g, '&lt;').replace(/>/g, '&gt;')}</td>
        </tr>`
      )
      .join('');
    const printWindow = window.open('', '_blank');
    if (!printWindow) {
      toast({ title: 'Print blocked', description: 'Allow popups to print.', variant: 'destructive' });
      return;
    }
    printWindow.document.write(`
      <!DOCTYPE html>
      <html>
        <head>
          <meta charset="utf-8">
          <title>Interview Questions - ${title.replace(/</g, '&lt;')}</title>
          <style>
            * { box-sizing: border-box; }
            body {
              font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
              margin: 0;
              padding: 40px 50px;
              color: #1a1a1a;
              font-size: 11pt;
              line-height: 1.5;
            }
            .header {
              border-bottom: 2px solid #2563eb;
              padding-bottom: 16px;
              margin-bottom: 24px;
            }
            .header h1 {
              margin: 0 0 4px 0;
              font-size: 18pt;
              font-weight: 600;
              color: #1e40af;
            }
            .header .sub {
              font-size: 10pt;
              color: #64748b;
              margin: 0;
            }
            .header .date {
              font-size: 9pt;
              color: #94a3b8;
              margin-top: 6px;
            }
            table {
              width: 100%;
              border-collapse: collapse;
            }
            tr {
              border-bottom: 1px solid #e2e8f0;
            }
            tr:last-child { border-bottom: none; }
            td {
              padding: 12px 10px 12px 0;
              vertical-align: top;
            }
            td.num {
              width: 28px;
              font-weight: 600;
              color: #64748b;
              font-size: 10pt;
            }
            td.type {
              width: 90px;
              font-size: 9pt;
              font-weight: 600;
              text-transform: capitalize;
            }
            td.type.technical {
              color: #0369a1;
            }
            td.type.behavioural {
              color: #15803d;
            }
            td.question {
              font-size: 11pt;
            }
            .footer {
              margin-top: 32px;
              padding-top: 12px;
              border-top: 1px solid #e2e8f0;
              font-size: 9pt;
              color: #94a3b8;
            }
            @media print {
              body { padding: 20px 30px; }
              .header { page-break-after: avoid; }
              tr { page-break-inside: avoid; }
            }
          </style>
        </head>
        <body>
          <div class="header">
            <h1>Interview Questions</h1>
            <p class="sub">${candidateName.replace(/</g, '&lt;')} · ${jobTitle.replace(/</g, '&lt;')}</p>
            <p class="date">Generated on ${dateStr}</p>
          </div>
          <table>
            <tbody>${questionsHtml}</tbody>
          </table>
          <div class="footer">AI-suggested questions for interview preparation. Confidential.</div>
        </body>
      </html>
    `);
    printWindow.document.close();
    setTimeout(() => {
      try {
        printWindow.focus();
        printWindow.print();
        toast({ title: 'Print dialog opened' });
      } catch (e) {
        toast({ title: 'Print failed', description: 'Try allowing popups and click Print again.', variant: 'destructive' });
      }
      setTimeout(() => printWindow.close(), 1000);
    }, 300);
  };

  return (
    <div className="space-y-6 w-full max-w-3xl">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <HelpCircle className="h-5 w-5" />
            AI Interview Questions
          </CardTitle>
          <CardDescription>
            Select a job and candidate. AI will suggest 5–10 tailored interview questions (technical + behavioural). Not saved – generate on demand.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>Job</Label>
              <Select value={selectedJobId} onValueChange={setSelectedJobId}>
                <SelectTrigger>
                  <SelectValue placeholder="Select job" />
                </SelectTrigger>
                <SelectContent>
                  {jobs.filter((j) => j.is_active !== false).map((j) => (
                    <SelectItem key={j.id} value={String(j.id)}>
                      {j.title}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Candidate</Label>
              <Select value={selectedCvId} onValueChange={setSelectedCvId} disabled={!selectedJobId || loading}>
                <SelectTrigger>
                  <SelectValue placeholder={loading ? 'Loading…' : 'Select candidate'} />
                </SelectTrigger>
                <SelectContent>
                  {candidates.map((c) => (
                    <SelectItem key={c.id} value={String(c.id)}>
                      {c.parsed?.name || c.file_name || `Candidate #${c.id}`}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <Button onClick={handleGenerate} disabled={!selectedJobId || !selectedCvId || generating}>
            {generating ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <HelpCircle className="h-4 w-4 mr-2" />}
            {generating ? 'Generating…' : 'Generate questions'}
          </Button>

          {meta && (
            <p className="text-sm text-muted-foreground">
              For <strong>{meta.candidate_name}</strong> × <strong>{meta.job_title}</strong>
            </p>
          )}

          {questions.length > 0 && (
            <div className="rounded-lg border p-4 space-y-3">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <span className="font-medium">Suggested questions</span>
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" onClick={copyAll}>
                    <Copy className="h-4 w-4 mr-1" />
                    Copy
                  </Button>
                  <Button variant="outline" size="sm" onClick={printAll}>
                    <Printer className="h-4 w-4 mr-1" />
                    Print
                  </Button>
                </div>
              </div>
              <ul className="space-y-2">
                {questions.map((q, i) => (
                  <li key={i} className="flex gap-2 items-start text-sm">
                    <Badge variant={q.type === 'technical' ? 'default' : 'secondary'} className="shrink-0 mt-0.5">
                      {q.type}
                    </Badge>
                    <span className="flex-1">{q.question}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default AiInterviewQuestions;
