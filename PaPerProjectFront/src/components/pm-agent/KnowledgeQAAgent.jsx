import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import pmAgentService from '@/services/pmAgentService';
import { Loader2, Send, MessageSquare } from 'lucide-react';

const KnowledgeQAAgent = ({ projects = [] }) => {
  const [question, setQuestion] = useState('');
  const [selectedProjectId, setSelectedProjectId] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const { toast } = useToast();
  
  // Ensure projects is always an array
  const safeProjects = Array.isArray(projects) ? projects : [];

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!question.trim()) {
      toast({
        title: 'Error',
        description: 'Please enter a question',
        variant: 'destructive',
      });
      return;
    }

    try {
      setLoading(true);
      setResult(null);

      const projectId = selectedProjectId && selectedProjectId !== "all" ? selectedProjectId : null;
      const response = await pmAgentService.knowledgeQA(
        question,
        projectId
      );

      console.log('Knowledge Q&A response:', response);
      
      if (response.status === 'success') {
        setResult(response);
        
        if (!response.data?.answer && !response.answer) {
          toast({
            title: 'Warning',
            description: 'No answer received from AI',
            variant: 'default',
          });
        }
      } else {
        toast({
          title: 'Error',
          description: 'Something went wrong. Please try again.',
          variant: 'destructive',
        });
      }
    } catch (error) {
      console.error('Knowledge Q&A error:', error);
      toast({
        title: 'Error',
        description: 'Something went wrong. Please try again.',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <MessageSquare className="h-5 w-5 text-primary" />
            Knowledge Q&A Agent
          </CardTitle>
          <CardDescription>
            Ask questions about your projects, tasks, deadlines, and get AI-powered answers.
            Example: "What tasks are overdue?" or "What's the status of my project?"
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-sm font-medium mb-2 block">
                Select Project (optional)
              </label>
              <Select value={selectedProjectId || "all"} onValueChange={(value) => setSelectedProjectId(value === "all" ? "" : value)}>
                <SelectTrigger>
                  <SelectValue placeholder="General Questions" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">General Questions</SelectItem>
                  {safeProjects && safeProjects.length > 0 ? (
                    safeProjects.map((project) => (
                      <SelectItem key={project.id} value={String(project.id)}>
                        {project.title || project.name}
                      </SelectItem>
                    ))
                  ) : (
                    <SelectItem value="none" disabled>No projects available</SelectItem>
                  )}
                </SelectContent>
              </Select>
            </div>

            <div>
              <label className="text-sm font-medium mb-2 block">
                Your Question
              </label>
              <Textarea
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="e.g., What tasks are overdue? What's the status of my project? Who is working on what?"
                rows={4}
                className="resize-none"
              />
            </div>

            <Button type="submit" disabled={loading} className="w-full">
              {loading ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Processing...
                </>
              ) : (
                <>
                  <Send className="h-4 w-4 mr-2" />
                  Ask AI
                </>
              )}
            </Button>
          </form>
        </CardContent>
      </Card>

      {result && (
        <Card>
          <CardHeader>
            <CardTitle>Answer</CardTitle>
          </CardHeader>
          <CardContent>
            {(result.data?.answer || result.answer) ? (
              <div className="p-4 bg-muted rounded-lg">
                <p className="whitespace-pre-wrap">{result.data?.answer || result.answer}</p>
              </div>
            ) : (
              <div className="space-y-2">
                <p className="text-muted-foreground">No answer provided</p>
                <details className="text-xs">
                  <summary className="cursor-pointer text-muted-foreground">View raw response</summary>
                  <pre className="mt-2 p-2 bg-muted rounded overflow-auto">{JSON.stringify(result, null, 2)}</pre>
                </details>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default KnowledgeQAAgent;



