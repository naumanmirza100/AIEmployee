import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import { Loader2, Send, MessageSquare } from 'lucide-react';
import marketingAgentService from '@/services/marketingAgentService';

/** Suggested questions matching backend / agents_test.html Knowledge Q&A + Analytics */
const SUGGESTED_QUESTIONS = [
  { group: 'Performance & Analytics', options: [
    'What campaigns are performing best?',
    'What is our overall ROI?',
    'Which marketing channels are most effective?',
    'What is our conversion rate?',
    'How are our campaigns performing this month?',
    'What is our customer acquisition cost (CAC)?',
  ]},
  { group: 'Analysis & Insights', options: [
    'Why are sales dropping?',
    'What should we focus on to improve performance?',
    'What are the key trends in our marketing data?',
    'Which campaigns need optimization?',
    'What are our top performing campaigns and why?',
  ]},
  { group: 'Goals & Targets', options: [
    'How many leads have we generated this month?',
    'What is our lead conversion rate?',
    'Are we on track to meet our campaign goals?',
  ]},
  { group: 'Strategy & Recommendations', options: [
    'What marketing strategies should we implement?',
    'What opportunities are we missing?',
    'How can we improve our campaign performance?',
    'What are the best practices for our industry?',
  ]},
];

const MarketingQA = () => {
  const { toast } = useToast();
  const [question, setQuestion] = useState('');
  const [suggestedValue, setSuggestedValue] = useState('__none__');
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState(null);

  const fillFromSuggestion = (value) => {
    const v = value || '__none__';
    setSuggestedValue(v);
    if (v !== '__none__') setQuestion(v);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!question.trim()) {
      toast({
        title: 'Error',
        description: 'Please enter a question or select from suggested questions.',
        variant: 'destructive',
      });
      return;
    }

    try {
      setLoading(true);
      setResponse(null);
      const result = await marketingAgentService.marketingQA(question.trim());

      if (result.status === 'success' && result.data) {
        setResponse(result.data);
      } else {
        throw new Error(result.message || 'Failed to get response');
      }
    } catch (error) {
      console.error('Marketing Q&A error:', error);
      toast({
        title: 'Error',
        description: error.message || 'Failed to get answer',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  const insights = response?.insights || [];
  const hasMultipleInsightValues = insights.some((i) => i.value && String(i.value).includes(':')) || insights.length > 3;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <MessageSquare className="h-5 w-5" />
            Knowledge Q&A + Analytics Agent
          </CardTitle>
          <CardDescription>
            Ask marketing questions and get data-driven answers. This foundation agent analyzes your campaigns,
            performance metrics, and provides intelligent insights (PayPerProject backend).
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="qa-question">Ask a Marketing Question</Label>
              <Textarea
                id="qa-question"
                placeholder="Type your question here or select from suggested questions below..."
                value={question}
                onChange={(e) => { setQuestion(e.target.value); setSuggestedValue('__none__'); }}
                rows={4}
                disabled={loading}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="suggested-questions">Suggested Questions</Label>
              <Select value={suggestedValue} onValueChange={fillFromSuggestion}>
                <SelectTrigger id="suggested-questions">
                  <SelectValue placeholder="Select a suggested question" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">Select a suggested question</SelectItem>
                  {SUGGESTED_QUESTIONS.map((g) => (
                    <React.Fragment key={g.group}>
                      {g.options.map((opt) => (
                        <SelectItem key={opt} value={opt}>
                          {opt}
                        </SelectItem>
                      ))}
                    </React.Fragment>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">Select a question to auto-fill the question field</p>
            </div>

            <Button type="submit" disabled={loading} className="w-full sm:w-auto">
              {loading ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Analyzing data and generating insights...
                </>
              ) : (
                <>
                  <Send className="h-4 w-4 mr-2" />
                  Ask AI
                </>
              )}
            </Button>
          </form>

          {response && (
            <div className="mt-6 rounded-lg border bg-muted/30 p-4 space-y-4">
              <h4 className="font-semibold">AI Response</h4>
              <div className="space-y-3 text-sm">
                <div>
                  <h5 className="font-medium mb-1">Analysis</h5>
                  <p className="whitespace-pre-wrap text-muted-foreground">
                    {response.answer || 'No answer provided.'}
                  </p>
                </div>
                {insights.length > 0 && (
                  <div>
                    <h5 className="font-medium mb-2">Key Insights & Metrics</h5>
                    {hasMultipleInsightValues ? (
                      <div className="overflow-x-auto">
                        <table className="w-full text-left border-collapse text-sm">
                          <thead>
                            <tr className="border-b">
                              <th className="py-1.5 pr-2 font-medium">Metric</th>
                              <th className="py-1.5 font-medium">Value</th>
                            </tr>
                          </thead>
                          <tbody>
                            {insights.map((insight, i) => (
                              <tr key={i} className="border-b border-border/50">
                                <td className="py-1.5 pr-2">{insight.title || 'N/A'}</td>
                                <td className="py-1.5 text-muted-foreground">{insight.value || 'N/A'}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <ul className="list-disc pl-4 space-y-1">
                        {insights.map((insight, i) => (
                          <li key={i}>
                            <strong>{insight.title || 'N/A'}</strong>: {insight.value || 'N/A'}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default MarketingQA;
