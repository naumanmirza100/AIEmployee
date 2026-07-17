import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
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
import {
  Loader2, Plus, TrendingUp, Pause, Play, Trash2, ChevronLeft, ChevronRight,
  Megaphone, Calendar, Users, Target, Mail, RefreshCw,
} from 'lucide-react';
import marketingAgentService from '@/services/marketingAgentService';
import OutreachCampaign from './OutreachCampaign';
import CampaignFilterBar from './CampaignFilterBar';

const PAGE_SIZE = 10;

// Left-edge stripe colour per status — mirrors getStatusColor below.
const STATUS_ACCENT = {
  active: 'bg-emerald-500',
  paused: 'bg-amber-500',
  completed: 'bg-blue-500',
  draft: 'bg-white/20',
  default: 'bg-white/20',
};

const Campaigns = ({ onRefresh }) => {
  const { toast } = useToast();
  const navigate = useNavigate();
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(true);   // full-screen spinner: first load only
  const [filtering, setFiltering] = useState(false); // subtle: search / filter refetch
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [selected, setSelected] = useState(new Set());
  const [deleting, setDeleting] = useState(false);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);

  // Filters (server-side). Search is debounced; status/date apply at once.
  const [filters, setFilters] = useState({ search: '', status: '', date: '' });

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  // `quiet` refetches (search/filter typing) keep the current list on screen and
  // only show a small inline spinner — no full-panel flash on every keystroke.
  const fetchCampaigns = useCallback(async (pageNum = 1, activeFilters = filters, quiet = false) => {
    try {
      if (quiet) setFiltering(true);
      else setLoading(true);
      const response = await marketingAgentService.listCampaigns({
        page: pageNum,
        limit: PAGE_SIZE,
        search: activeFilters.search,
        status: activeFilters.status,
        date: activeFilters.date,
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
      setFiltering(false);
    }
  }, [onRefresh, filters]);

  useEffect(() => {
    fetchCampaigns(page);
  }, [page]);

  // Any filter change resets to page 1 and re-fetches (search debounced 300ms).
  // `quiet` = true so the list stays put and only a small spinner shows.
  useEffect(() => {
    const t = setTimeout(() => {
      setPage(1);
      fetchCampaigns(1, filters, true);
    }, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters.search, filters.status, filters.date]);

  // Clear selection when campaigns change (page change, refresh, etc.)
  useEffect(() => {
    setSelected(new Set());
  }, [campaigns]);

  // Tinted for the dark dashboard. These were light-theme classes
  // (bg-green-100 / text-green-800), which rendered as harsh white blocks here.
  const getStatusColor = (status) => {
    switch (status) {
      case 'active':
        return 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30';
      case 'paused':
        return 'bg-amber-500/15 text-amber-300 border border-amber-500/30';
      case 'completed':
        return 'bg-blue-500/15 text-blue-300 border border-blue-500/30';
      case 'draft':
        return 'bg-white/10 text-white/60 border border-white/15';
      default:
        return 'bg-white/10 text-white/60 border border-white/15';
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
      <div data-tour-mkt="camp-create">
        <OutreachCampaign onCampaignCreated={() => fetchCampaigns(page)} />
      </div>

      <div data-tour-mkt="camp-list" className="space-y-6">
      <div className="flex justify-between items-center gap-3 flex-wrap">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-primary/15 border border-primary/25 flex items-center justify-center shrink-0">
            <Megaphone className="h-4 w-4 text-primary" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-white leading-tight">Your Campaigns</h3>
            <p className="text-xs text-white/40">
              {total > 0 ? `${total} campaign${total === 1 ? '' : 's'}` : 'No campaigns yet'}
            </p>
          </div>
        </div>
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
            <RefreshCw className={`mr-2 h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>
      </div>

      <CampaignFilterBar
        dataTour="camp-filters"
        search={filters.search}
        onSearchChange={(v) => setFilters((f) => ({ ...f, search: v }))}
        status={filters.status}
        onStatusChange={(v) => setFilters((f) => ({ ...f, status: v }))}
        date={filters.date}
        onDateChange={(v) => setFilters((f) => ({ ...f, date: v }))}
        onClear={() => setFilters({ search: '', status: '', date: '' })}
        loading={filtering}
      />

      {loading ? (
        <div className="flex justify-center py-8">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      ) : campaigns.length === 0 ? (
        <Card className="border-white/10 bg-black/20 backdrop-blur-sm border-dashed">
          <CardContent className="py-12 text-center">
            <div className="w-12 h-12 rounded-xl bg-white/[0.03] border border-white/10 flex items-center justify-center mx-auto mb-3">
              <Megaphone className="h-5 w-5 text-white/25" />
            </div>
            {(filters.search || filters.status || filters.date) ? (
              <>
                <p className="text-white/70 text-sm font-medium">No campaigns match these filters</p>
                <p className="text-white/35 text-xs mt-1">Try adjusting your search or filters.</p>
              </>
            ) : (
              <>
                <p className="text-white/70 text-sm font-medium">No campaigns yet</p>
                <p className="text-white/35 text-xs mt-1">
                  Use the Outreach &amp; Campaign Agent above to create your first one.
                </p>
              </>
            )}
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
              <label htmlFor="select-all" className="text-xs text-white/50 hover:text-white/80 cursor-pointer select-none transition-colors">
                Select all
              </label>
              {selected.size > 0 && (
                <span className="text-xs text-primary">{selected.size} selected</span>
              )}
            </div>
          )}

          <div className={`grid gap-3 transition-opacity duration-200 ${filtering ? 'opacity-50' : 'opacity-100'}`}>
            {campaigns.map((campaign) => {
              const isActive = campaign.status === 'active';
              const isChecked = selected.has(campaign.id);
              const accent = STATUS_ACCENT[campaign.status] || STATUS_ACCENT.default;
              return (
                <Card
                  key={campaign.id}
                  onClick={() => navigate(`/marketing/dashboard/campaign/${campaign.id}`)}
                  className={`group relative overflow-hidden border-white/10 bg-black/20 backdrop-blur-sm transition-all cursor-pointer hover:bg-white/[0.04] hover:border-primary/30 ${
                    isChecked ? 'ring-1 ring-primary border-primary/40' : ''
                  }`}
                >
                  {/* Status accent stripe — makes each card's state readable at a glance */}
                  <div className={`absolute left-0 top-0 bottom-0 w-[3px] ${accent}`} />

                  <CardHeader className="pb-3 pl-5">
                    <div className="flex justify-between items-start gap-3">
                      <div className="flex items-start gap-3 min-w-0">
                        <div className="pt-0.5" onClick={(e) => e.stopPropagation()}>
                          <Checkbox
                            checked={isChecked}
                            onCheckedChange={() => toggleSelect(campaign.id)}
                            disabled={isActive}
                            title={isActive ? 'Active campaigns cannot be deleted' : undefined}
                          />
                        </div>
                        <div className="min-w-0">
                          <CardTitle className="text-base text-white truncate group-hover:text-primary transition-colors">
                            {campaign.name}
                          </CardTitle>
                          {campaign.description && (
                            <p className="text-sm text-white/50 mt-1 line-clamp-2">{campaign.description}</p>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <Badge className={`${getStatusColor(campaign.status)} capitalize text-[11px] font-medium`}>
                          {campaign.status}
                        </Badge>
                        <ChevronRight className="h-4 w-4 text-white/20 group-hover:text-primary group-hover:translate-x-0.5 transition-all" />
                      </div>
                    </div>
                  </CardHeader>

                  <CardContent className="pl-5 pt-0">
                    {/* Compact meta row — icons carry the meaning, so the labels
                        that used to take a whole line each are gone. */}
                    <div className="flex items-center gap-x-5 gap-y-2 flex-wrap text-xs text-white/50 border-t border-white/5 pt-3">
                      <span className="inline-flex items-center gap-1.5" title="Start date">
                        <Calendar className="h-3.5 w-3.5 text-white/30" />
                        {campaign.start_date ? new Date(campaign.start_date).toLocaleDateString() : '—'}
                        <span className="text-white/20">→</span>
                        {campaign.end_date ? new Date(campaign.end_date).toLocaleDateString() : '—'}
                      </span>
                      {campaign.target_leads != null && (
                        <span className="inline-flex items-center gap-1.5" title="Target leads">
                          <Users className="h-3.5 w-3.5 text-white/30" />
                          <span className="text-white/80 font-medium">{campaign.target_leads}</span> leads
                        </span>
                      )}
                      {campaign.target_conversions != null && (
                        <span className="inline-flex items-center gap-1.5" title="Target conversions">
                          <Target className="h-3.5 w-3.5 text-white/30" />
                          <span className="text-white/80 font-medium">{campaign.target_conversions}</span> conversions
                        </span>
                      )}
                      {campaign.type && (
                        <span className="inline-flex items-center gap-1.5 capitalize" title="Campaign type">
                          <Mail className="h-3.5 w-3.5 text-white/30" />
                          {campaign.type}
                        </span>
                      )}
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </>
      )}

      {/* Pagination — count always shows; Prev/Next only when multi-page. */}
      {!loading && total > 0 && (() => {
        const rangeStart = (page - 1) * PAGE_SIZE + 1;
        const rangeEnd = Math.min(page * PAGE_SIZE, total);
        const multiPage = totalPages > 1;
        return (
          <div className="flex flex-wrap items-center justify-between gap-3 pt-4 pb-2 border-t">
            <p className="text-sm text-muted-foreground">
              {multiPage
                ? `Showing ${rangeStart}–${rangeEnd} of ${total} campaigns · page ${page} of ${totalPages}`
                : `${total} campaign${total === 1 ? '' : 's'}`}
            </p>
            {multiPage && (
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
            )}
          </div>
        );
      })()}
      </div>
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
