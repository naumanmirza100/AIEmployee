import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import { Loader2, FileText, Send } from 'lucide-react';
import marketingAgentService from '@/services/marketingAgentService';

/**
 * Document Authoring sub-agent.
 * API: POST /api/marketing/document-authoring (Company auth).
 * Body: { action, document_type, document_data, campaign_id?, context }.
 * Response: { status: 'success', data: { success, title?, content?, message?, error? } }
 */
const DOCUMENT_TYPES = [
  { value: 'strategy', label: 'Marketing Strategy' },
  { value: 'proposal', label: 'Campaign Proposal' },
  { value: 'report', label: 'Performance Report' },
  { value: 'brief', label: 'Campaign Brief' },
  { value: 'presentation', label: 'Presentation Outline' },
];

const Documents = () => {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [documentType, setDocumentType] = useState('strategy');
  const [title, setTitle] = useState('');
  const [notes, setNotes] = useState('');
  const [campaignId, setCampaignId] = useState('');
  const [campaigns, setCampaigns] = useState([]);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    const loadCampaigns = async () => {
      try {
        const response = await marketingAgentService.listCampaigns({ limit: 50 });
        if (response?.status === 'success' && response?.data?.campaigns) {
          setCampaigns(response.data.campaigns);
        }
      } catch (e) {
        console.error('Load campaigns for documents:', e);
      }
    };
    loadCampaigns();
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setResult(null);
    const needsCampaign = documentType === 'report' || documentType === 'brief';
    if (needsCampaign && !campaignId) {
      toast({
        title: 'Campaign required',
        description: 'Performance Report and Campaign Brief require a campaign.',
        variant: 'destructive',
      });
      return;
    }

    setLoading(true);
    try {
      const documentData = {};
      if (title?.trim()) documentData.title = title.trim();
      if (notes?.trim()) documentData.notes = notes.trim();
      const campaignIdNum = campaignId ? Number(campaignId) : null;

      const response = await marketingAgentService.documentAuthoring(
        'create',
        documentType,
        documentData,
        campaignIdNum,
        {}
      );

      if (response.status === 'error') {
        setError(response.message || 'Request failed');
        toast({ title: 'Error', description: response.message, variant: 'destructive' });
        return;
      }
      if (response.status !== 'success' || !response.data) {
        setError('Invalid response from server');
        return;
      }

      const data = response.data;
      if (data.success === false) {
        setError(data.error || 'Document generation failed');
        toast({ title: 'Error', description: data.error, variant: 'destructive' });
        return;
      }

      setResult(data);
      toast({ title: 'Success', description: data.message || 'Document generated' });
    } catch (err) {
      setError(err.message || 'Failed to generate document');
      toast({
        title: 'Error',
        description: err.message || 'Failed to generate document',
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
            <FileText className="h-5 w-5" />
            Document Authoring Agent
          </CardTitle>
          <CardDescription>
            Generate documents via API: POST /api/marketing/document-authoring
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="documentType">Document Type</Label>
              <Select value={documentType} onValueChange={(v) => { setDocumentType(v); setResult(null); setError(null); }}>
                <SelectTrigger id="documentType">
                  <SelectValue placeholder="Select type" />
                </SelectTrigger>
                <SelectContent>
                  {DOCUMENT_TYPES.map((t) => (
                    <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {(documentType === 'report' || documentType === 'brief') && (
              <div className="space-y-2">
                <Label htmlFor="campaign">Campaign (required)</Label>
                <Select value={campaignId} onValueChange={setCampaignId}>
                  <SelectTrigger id="campaign">
                    <SelectValue placeholder="Select campaign" />
                  </SelectTrigger>
                  <SelectContent>
                    {campaigns.map((c) => (
                      <SelectItem key={c.id} value={String(c.id)}>{c.name}</SelectItem>
                    ))}
                    {campaigns.length === 0 && <SelectItem value="" disabled>No campaigns</SelectItem>}
                  </SelectContent>
                </Select>
              </div>
            )}

            <div className="space-y-2">
              <Label htmlFor="title">Title (optional)</Label>
              <Input
                id="title"
                placeholder="e.g. Q1 Marketing Strategy"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="notes">Notes / Key points (optional)</Label>
              <Textarea
                id="notes"
                placeholder="Context, key points, or requirements..."
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={3}
              />
            </div>

            <Button type="submit" disabled={loading}>
              {loading ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Generating...
                </>
              ) : (
                <>
                  <Send className="h-4 w-4 mr-2" />
                  Generate Document
                </>
              )}
            </Button>
          </form>

          {error && <p className="text-sm text-destructive">{error}</p>}

          {result && (result.content != null || result.title) && (
            <div className="mt-6 rounded-lg border bg-muted/30 p-4">
              <h4 className="font-semibold mb-2">{result.title || result.document_type || 'Document'}</h4>
              {result.message && <p className="text-sm text-muted-foreground mb-2">{result.message}</p>}
              {result.content != null && (
                <div className="text-sm whitespace-pre-wrap max-h-[400px] overflow-y-auto">
                  {result.content}
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default Documents;
