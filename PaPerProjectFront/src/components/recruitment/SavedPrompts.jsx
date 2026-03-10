import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { useToast } from '@/components/ui/use-toast';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu';
import {
  Loader2, Star, StarOff, Play, Trash2, MoreVertical,
  Search, RefreshCw, Copy, Clock, LayoutDashboard, X, BarChart2,
} from 'lucide-react';
import {
  getSavedPrompts,
  generateGraph,
  deletePrompt,
  toggleFavorite,
  toggleDashboardPrompt,
  isPromptOnDashboard,
} from '@/services/recruitmentAgentService';
import { renderChart } from './ChartRenderer';

const SavedPrompts = () => {
  const { toast } = useToast();
  const [savedPrompts, setSavedPrompts] = useState([]);
  const [loadingPrompts, setLoadingPrompts] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterFavorites, setFilterFavorites] = useState(false);
  const [selectedPrompt, setSelectedPrompt] = useState(null);
  const [graphLoading, setGraphLoading] = useState(false);
  const [graphData, setGraphData] = useState(null);
  const [graphInsights, setGraphInsights] = useState('');

  const fetchSavedPrompts = async () => {
    try {
      setLoadingPrompts(true);
      const res = await getSavedPrompts();
      setSavedPrompts(res?.data || []);
    } catch (e) {
      console.error('Error fetching saved prompts:', e);
    } finally {
      setLoadingPrompts(false);
    }
  };

  useEffect(() => {
    fetchSavedPrompts();
  }, []);

  const filteredPrompts = savedPrompts.filter((p) => {
    const matchesSearch = !searchQuery ||
      p.title?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.prompt?.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesFav = !filterFavorites || p.is_favorite;
    return matchesSearch && matchesFav;
  });

  const handleRunPrompt = async (prompt) => {
    setSelectedPrompt(prompt);
    setGraphLoading(true);
    setGraphData(null);
    setGraphInsights('');
    try {
      const response = await generateGraph(prompt.prompt);
      if (response.status === 'success') {
        setGraphData(response.data.chart);
        setGraphInsights(response.data.insights || '');
      }
    } catch (error) {
      console.error('Error generating graph:', error);
      toast({ title: 'Error', description: 'Failed to generate graph', variant: 'destructive' });
    } finally {
      setGraphLoading(false);
    }
  };

  const handleCloseGraph = () => {
    setSelectedPrompt(null);
    setGraphData(null);
    setGraphInsights('');
  };

  const handleDeletePrompt = async (id) => {
    try {
      await deletePrompt(id);
      setSavedPrompts((prev) => prev.filter((p) => p.id !== id));
      toast({ title: 'Deleted', description: 'Prompt deleted successfully' });
    } catch (e) {
      toast({ title: 'Error', description: 'Failed to delete prompt', variant: 'destructive' });
    }
  };

  const handleToggleFavorite = async (id, currentFav) => {
    try {
      await toggleFavorite(id);
      setSavedPrompts((prev) =>
        prev.map((p) => (p.id === id ? { ...p, is_favorite: !currentFav } : p))
      );
    } catch (e) {
      toast({ title: 'Error', description: 'Failed to update favorite', variant: 'destructive' });
    }
  };

  const handleToggleDashboard = async (prompt) => {
    try {
      await toggleDashboardPrompt(prompt.id);
      setSavedPrompts((prev) =>
        prev.map((p) => (p.id === prompt.id ? { ...p, on_dashboard: !p.on_dashboard } : p))
      );
      toast({
        title: 'Updated',
        description: isPromptOnDashboard(prompt) ? 'Removed from dashboard' : 'Added to dashboard',
      });
    } catch (e) {
      toast({ title: 'Error', description: 'Failed to update dashboard', variant: 'destructive' });
    }
  };

  const handleCopyPrompt = (text) => {
    navigator.clipboard.writeText(text);
    toast({ title: 'Copied', description: 'Prompt copied to clipboard' });
  };

  return (
    <div className="space-y-4">
      <Card className="border-white/10 bg-black/20 backdrop-blur-sm">
        <CardHeader className="p-4 sm:p-6">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
              <CardTitle className="text-base sm:text-lg text-white">Saved Prompts</CardTitle>
              <CardDescription className="text-xs sm:text-sm text-white/60">
                Your saved graph prompts for quick access
              </CardDescription>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant={filterFavorites ? "default" : "outline"}
                size="sm"
                onClick={() => setFilterFavorites(!filterFavorites)}
              >
                <Star className={`h-4 w-4 ${filterFavorites ? '' : 'mr-2'}`} />
                {!filterFavorites && <span className="hidden sm:inline">Favorites</span>}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={fetchSavedPrompts}
                disabled={loadingPrompts}
              >
                <RefreshCw className={`h-4 w-4 ${loadingPrompts ? 'animate-spin' : ''}`} />
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-4 sm:p-6 pt-0 space-y-4">
          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search prompts..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9"
            />
          </div>

          {/* Prompts List */}
          {loadingPrompts ? (
            <div className="py-8 flex justify-center">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : filteredPrompts.length === 0 ? (
            <div className="py-8 text-center">
              <Star className="h-10 w-10 mx-auto text-muted-foreground mb-3" />
              <p className="text-sm font-medium mb-1 text-white">No saved prompts</p>
              <p className="text-xs text-white/60">
                {searchQuery || filterFavorites
                  ? 'Try adjusting your filters'
                  : 'Generate a graph and save it to see it here'}
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {filteredPrompts.map((savedPrompt) => (
                <Card key={savedPrompt.id} className="overflow-hidden border-white/10 bg-black/20 backdrop-blur-sm">
                  <CardContent className="p-3 sm:p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <h4 className="font-medium text-sm truncate text-white">{savedPrompt.title}</h4>
                          {savedPrompt.is_favorite && (
                            <Star className="h-3.5 w-3.5 fill-yellow-400 text-yellow-400 shrink-0" />
                          )}
                        </div>
                        <p className="text-xs text-white/60 line-clamp-2 mb-2">
                          {savedPrompt.prompt}
                        </p>
                        <div className="flex items-center gap-2 flex-wrap">
                          {savedPrompt.chart_type && (
                            <Badge variant="secondary" className="text-[10px]">
                              {savedPrompt.chart_type}
                            </Badge>
                          )}
                          {savedPrompt.tags?.slice(0, 3).map((tag, i) => (
                            <Badge key={i} variant="outline" className="text-[10px]">
                              {tag}
                            </Badge>
                          ))}
                          {savedPrompt.created_at && (
                            <span className="text-[10px] text-white/40 flex items-center gap-1">
                              <Clock className="h-3 w-3" />
                              {new Date(savedPrompt.created_at).toLocaleDateString()}
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-1 shrink-0">
                        <Button
                          variant="default"
                          size="sm"
                          onClick={() => handleRunPrompt(savedPrompt)}
                        >
                          <Play className="h-3.5 w-3.5 mr-1" />
                          Run
                        </Button>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
                              <MoreVertical className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem onClick={() => handleToggleFavorite(savedPrompt.id, savedPrompt.is_favorite)}>
                              {savedPrompt.is_favorite ? (
                                <>
                                  <StarOff className="h-4 w-4 mr-2" />
                                  Remove from favorites
                                </>
                              ) : (
                                <>
                                  <Star className="h-4 w-4 mr-2" />
                                  Add to favorites
                                </>
                              )}
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={() => handleCopyPrompt(savedPrompt.prompt)}>
                              <Copy className="h-4 w-4 mr-2" />
                              Copy prompt
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={() => handleToggleDashboard(savedPrompt)}>
                              <LayoutDashboard className="h-4 w-4 mr-2" />
                              {isPromptOnDashboard(savedPrompt) ? 'Remove from dashboard' : 'Add to dashboard'}
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              onClick={() => handleDeletePrompt(savedPrompt.id)}
                              className="text-destructive focus:text-destructive"
                            >
                              <Trash2 className="h-4 w-4 mr-2" />
                              Delete
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Inline Graph Render */}
      {(graphLoading || graphData) && (
        <Card className="border-white/10 bg-black/20 backdrop-blur-sm">
          <CardContent className="p-4 sm:p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                <BarChart2 className="h-5 w-5" />
                {selectedPrompt?.title || 'Graph'}
              </h3>
              <Button variant="ghost" size="sm" onClick={handleCloseGraph} className="text-white/60 hover:text-white">
                <X className="h-4 w-4" />
              </Button>
            </div>
            {graphLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
                <span className="ml-3 text-white/60">Generating graph...</span>
              </div>
            ) : graphData ? (
              <div>
                <div className="bg-black/20 rounded-lg p-4 min-h-[300px]">
                  {renderChart(graphData)}
                </div>
                {graphInsights && (
                  <div className="mt-4 p-3 rounded-lg bg-black/20 border border-white/10">
                    <p className="text-sm text-white/70 whitespace-pre-wrap">{graphInsights}</p>
                  </div>
                )}
              </div>
            ) : null}
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default SavedPrompts;
