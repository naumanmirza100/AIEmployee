import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { useToast } from '@/components/ui/use-toast';
import { Loader2, Send, MessageSquare } from 'lucide-react';
import marketingAgentService from '@/services/marketingAgentService';

const MarketingQA = () => {
  const { toast } = useToast();
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState(null);

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
      const result = await marketingAgentService.marketingQA(question);
      
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

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <MessageSquare className="h-5 w-5" />
            Marketing Q&A Agent
          </CardTitle>
          <CardDescription>
            Ask questions about your marketing campaigns, strategies, and performance
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <Textarea
              placeholder="Ask a question about your marketing campaigns..."
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              rows={4}
              disabled={loading}
            />
            <Button type="submit" disabled={loading}>
              {loading ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Processing...
                </>
              ) : (
                <>
                  <Send className="h-4 w-4 mr-2" />
                  Ask Question
                </>
              )}
            </Button>
          </form>

          {response && (
            <div className="mt-6 p-4 bg-muted rounded-lg">
              <h4 className="font-semibold mb-2">Answer:</h4>
              <p className="text-sm whitespace-pre-wrap">{response.answer || response.message || JSON.stringify(response, null, 2)}</p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default MarketingQA;

