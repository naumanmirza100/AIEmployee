import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { useToast } from '@/components/ui/use-toast';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
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
  const [selected, setSelected] = useState(new Set());
  const [deleting, setDeleting] = useState(false);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);

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

  // Clear selection when campaigns change (page change, refresh, etc.)
  useEffect(() => {
    setSelected(new Set());
  }, [campaigns]);

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

  const selectableCampaigns = campaigns.filter((c) => c.status !== 'active');
  const allSelectableChecked = selectableCampaigns.length > 0 && selectableCampaigns.every((c) => selected.has(c.id));

  const toggleSelect = (id) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (allSelectableChecked) {
      setSelected(new Set());
    } else {
      setSelected(new Set(selectableCampaigns.map((c) => c.id)));
    }
  };

  const handleBulkDelete = async () => {
    setDeleteConfirmOpen(false);
    setDeleting(true);
    let successCount = 0;
    let failCount = 0;
    for (const cid of selected) {
      try {
        await marketingAgentService.campaignDelete(cid);
        successCount++;
      } catch {
        failCount++;
      }
    }
    setDeleting(false);
    setSelected(new Set());
    if (successCount > 0) {
      toast({ title: 'Deleted', description: `${successCount} campaign${successCount > 1 ? 's' : ''} deleted successfully` });
    }
    if (failCount > 0) {
      toast({ title: 'Error', description: `${failCount} campaign${failCount > 1 ? 's' : ''} failed to delete`, variant: 'destructive' });
    }
    fetchCampaigns(page);
  };

  return (
    <div className="h-full min-h-0 flex flex-col overflow-hidden">
      <div className="flex-1 min-h-0 overflow-y-auto space-y-6">
      <OutreachCampaign onCampaignCreated={() => fetchCampaigns(page)} />

      <div className="flex justify-between items-center">
        <h3 className="text-lg font-semibold text-white">Your Campaigns</h3>
        <div className="flex items-center gap-2">
          {selected.size > 0 && (
            <Button
              variant="destructive"
              size="sm"
              disabled={deleting}
              onClick={() => setDeleteConfirmOpen(true)}
            >
              {deleting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Trash2 className="mr-2 h-4 w-4" />}
              Delete ({selected.size})
            </Button>
          )}
          <Button onClick={() => fetchCampaigns(page)} variant="outline" size="sm" disabled={loading}>
            Refresh
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-8">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      ) : campaigns.length === 0 ? (
        <Card className="border-white/10 bg-black/20 backdrop-blur-sm">
          <CardContent className="py-8 text-center">
            <p className="text-white/60">No campaigns found. Create your first campaign to get started.</p>
          </CardContent>
        </Card>
      ) : (
        <>
          {/* Select All */}
          {selectableCampaigns.length > 0 && (
            <div className="flex items-center gap-2 px-1">
              <Checkbox
                checked={allSelectableChecked}
                onCheckedChange={toggleSelectAll}
                id="select-all"
              />
              <label htmlFor="select-all" className="text-sm text-white/70 cursor-pointer select-none">
                Select all
              </label>
            </div>
          )}

          <div className="grid gap-4">
            {campaigns.map((campaign) => {
              const isActive = campaign.status === 'active';
              const isChecked = selected.has(campaign.id);
              return (
                <Card key={campaign.id} className={`border-white/10 bg-black/20 backdrop-blur-sm transition-colors ${isChecked ? 'ring-1 ring-primary' : ''}`}>
                  <CardHeader>
                    <div className="flex justify-between items-start">
                      <div className="flex items-start gap-3">
                        <div className="pt-1">
                          <Checkbox
                            checked={isChecked}
                            onCheckedChange={() => toggleSelect(campaign.id)}
                            disabled={isActive}
                            title={isActive ? 'Active campaigns cannot be deleted' : undefined}
                          />
                        </div>
                        <div>
                          <CardTitle className="text-lg text-white">{campaign.name}</CardTitle>
                          <p className="text-sm text-white/60 mt-1">{campaign.description}</p>
                        </div>
                      </div>
                      <Badge className={getStatusColor(campaign.status)}>
                        {campaign.status}
                      </Badge>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                      <div>
                        <p className="text-white/60">Start Date</p>
                        <p className="font-semibold">
                          {campaign.start_date ? new Date(campaign.start_date).toLocaleDateString() : 'N/A'}
                        </p>
                      </div>
                      <div>
                        <p className="text-white/60">End Date</p>
                        <p className="font-semibold">
                          {campaign.end_date ? new Date(campaign.end_date).toLocaleDateString() : 'N/A'}
                        </p>
                      </div>
                      {campaign.target_leads != null && (
                        <div>
                          <p className="text-white/60">Target Leads</p>
                          <p className="font-semibold">{campaign.target_leads}</p>
                        </div>
                      )}
                      {campaign.target_conversions != null && (
                        <div>
                          <p className="text-white/60">Target Conversions</p>
                          <p className="font-semibold">{campaign.target_conversions}</p>
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </>
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

      {/* Bulk Delete Confirmation Dialog */}
      <Dialog open={deleteConfirmOpen} onOpenChange={setDeleteConfirmOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Delete {selected.size} Campaign{selected.size > 1 ? 's' : ''}</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete the selected campaign{selected.size > 1 ? 's' : ''}? This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" onClick={() => setDeleteConfirmOpen(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleBulkDelete}>
              <Trash2 className="mr-2 h-4 w-4" />
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default Campaigns;
