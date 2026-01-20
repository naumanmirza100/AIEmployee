import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import { Loader2, Sparkles } from 'lucide-react';
import marketingAgentService from '@/services/marketingAgentService';

const MarketResearch = () => {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [researchType, setResearchType] = useState('market_trend');
  const [topic, setTopic] = useState('');
  const [context, setContext] = useState('');
  const [response, setResponse] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!topic.trim()) {
      toast({
        title: 'Error',
        description: 'Please enter a research topic',
        variant: 'destructive',
      });
      return;
    }

    try {
      setLoading(true);
      const additionalContext = context.trim() ? { notes: context } : {};
      
      const result = await marketingAgentService.marketResearch(
        researchType,
        topic,
        additionalContext
      );
      
      if (result.status === 'success' && result.data) {
        setResponse(result.data);
        toast({
          title: 'Success',
          description: 'Market research completed',
        });
      } else {
        throw new Error(result.message || 'Failed to conduct research');
      }
    } catch (error) {
      console.error('Market research error:', error);
      toast({
        title: 'Error',
        description: error.message || 'Failed to conduct market research',
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
            <Sparkles className="h-5 w-5" />
            Market Research Agent
          </CardTitle>
          <CardDescription>
            Research market trends, competitors, and opportunities
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="researchType">Research Type</Label>
              <Select value={researchType} onValueChange={setResearchType}>
                <SelectTrigger>
                  <SelectValue placeholder="Select research type" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="market_trend">Market Trend</SelectItem>
                  <SelectItem value="competitor">Competitor Analysis</SelectItem>
                  <SelectItem value="customer">Customer Insights</SelectItem>
                  <SelectItem value="opportunity">Opportunity Analysis</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="topic">Research Topic *</Label>
              <Input
                id="topic"
                placeholder="e.g., AI automation tools market"
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                required
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="context">Additional Context (Optional)</Label>
              <Textarea
                id="context"
                placeholder="Provide any additional context or specific questions..."
                value={context}
                onChange={(e) => setContext(e.target.value)}
                rows={3}
              />
            </div>

            <Button type="submit" disabled={loading}>
              {loading ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Researching...
                </>
              ) : (
                <>
                  <Sparkles className="h-4 w-4 mr-2" />
                  Conduct Research
                </>
              )}
            </Button>
          </form>

          {response && (
            <div className="mt-6 p-4 bg-muted rounded-lg">
              <h4 className="font-semibold mb-2">Research Results:</h4>
              <div className="text-sm whitespace-pre-wrap">
                {response.insights || response.answer || response.message || JSON.stringify(response, null, 2)}
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default MarketResearch;

