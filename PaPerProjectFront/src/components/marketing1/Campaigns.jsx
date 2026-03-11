import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/components/ui/use-toast';
import { Loader2, Plus, TrendingUp, Pause, Play, Trash2, ChevronLeft, ChevronRight } from 'lucide-react';
import marketingAgentService from '@/services/marketingAgentService';
import OutreachCampaign from './OutreachCampaign';

const PAGE_SIZE = 10;

const Campaigns = ({ onRefresh }) => {
  const { toast } = useToast();
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const fetchCampaigns = useCallback(async (pageNum = 1) => {
    try {
      setLoading(true);
      const response = await marketingAgentService.listCampaigns({
        page: pageNum,
        limit: PAGE_SIZE,
      });
      if (response?.status === 'success' && response?.data) {
        setCampaigns(response.data.campaigns || []);
        setTotal(response.data.total ?? 0);
      }
      if (onRefresh) onRefresh();
    } catch (error) {
      setCampaigns([]);
    } finally {
      setLoading(false);
    }
  }, [onRefresh]);

  useEffect(() => {
    fetchCampaigns(page);
  }, [page]);

  const getStatusColor = (status) => {
    switch (status) {
      case 'active':
        return 'bg-green-100 text-green-800';
      case 'paused':
        return 'bg-yellow-100 text-yellow-800';
      case 'completed':
        return 'bg-blue-100 text-blue-800';
      case 'draft':
        return 'bg-gray-100 text-gray-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  return (
    <div className="h-full min-h-0 flex flex-col overflow-hidden">
      <div className="flex-1 min-h-0 overflow-y-auto space-y-6">
      <OutreachCampaign onCampaignCreated={() => fetchCampaigns(page)} />

      <div className="flex justify-between items-center">
        <h3 className="text-lg font-semibold">Your Campaigns</h3>
        <Button onClick={() => fetchCampaigns(page)} variant="outline" size="sm" disabled={loading}>
          Refresh
        </Button>
      </div>

      {loading ? (
        <div className="flex justify-center py-8">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      ) : campaigns.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center">
            <p className="text-muted-foreground">No campaigns found. Create your first campaign to get started.</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4">
          {campaigns.map((campaign) => (
            <Card key={campaign.id}>
              <CardHeader>
                <div className="flex justify-between items-start">
                  <div>
                    <CardTitle className="text-lg">{campaign.name}</CardTitle>
                    <p className="text-sm text-muted-foreground mt-1">{campaign.description}</p>
                  </div>
                  <Badge className={getStatusColor(campaign.status)}>
                    {campaign.status}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                  <div>
                    <p className="text-muted-foreground">Start Date</p>
                    <p className="font-semibold">
                      {campaign.start_date ? new Date(campaign.start_date).toLocaleDateString() : 'N/A'}
                    </p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">End Date</p>
                    <p className="font-semibold">
                      {campaign.end_date ? new Date(campaign.end_date).toLocaleDateString() : 'N/A'}
                    </p>
                  </div>
                  {campaign.target_leads != null && (
                    <div>
                      <p className="text-muted-foreground">Target Leads</p>
                      <p className="font-semibold">{campaign.target_leads}</p>
                    </div>
                  )}
                  {campaign.target_conversions != null && (
                    <div>
                      <p className="text-muted-foreground">Target Conversions</p>
                      <p className="font-semibold">{campaign.target_conversions}</p>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Pagination */}
      {!loading && total > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 pt-4 pb-2 border-t">
          <p className="text-sm text-muted-foreground">
            Showing page {page} of {totalPages} ({total} total campaigns)
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              <ChevronLeft className="h-4 w-4" />
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
      </div>
    </div>
  );
};

export default Campaigns;

