import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/components/ui/use-toast';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu';
import { Loader2, Sparkles, BarChart3, Save, Star, StarOff, Play, MoreVertical, Trash2, Copy, Search, RefreshCw, Clock } from 'lucide-react';
import frontlineAgentService from '@/services/frontlineAgentService';

// Chart components (same data shapes as recruitment AIGraphGenerator)
const SimpleBarChart = ({ data, colors, height = 250, title }) => {
  if (!data || (typeof data === 'object' && !Array.isArray(data) && Object.keys(data).length === 0)) {
    return <div className="flex items-center justify-center h-48 text-muted-foreground">No data available</div>;
  }
  const entries = Array.isArray(data) ? data.map((d) => [d.category || d.status || d.priority || d.label || String(d), d.count ?? d.value ?? 0]) : Object.entries(data);
  const maxValue = Math.max(...entries.map(([, v]) => v), 1);
  const defaultColors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16'];
  const chartColors = colors || defaultColors;
  return (
    <div className="space-y-3" style={{ minHeight: `${height}px` }}>
      {title && <h4 className="font-medium text-sm text-muted-foreground mb-4">{title}</h4>}
      {entries.map(([key, value], index) => {
        const percentage = (value / maxValue) * 100;
        return (
          <div key={key} className="flex items-center gap-3">
            <div className="w-24 sm:w-32 text-xs sm:text-sm text-muted-foreground truncate shrink-0" title={key}>{key}</div>
            <div className="flex-1 min-w-0">
              <div className="h-8 bg-muted rounded-md overflow-hidden">
                <div
                  className="h-full flex items-center justify-end pr-2 text-xs font-semibold text-white transition-all duration-500"
                  style={{ width: `${Math.max(percentage, 5)}%`, backgroundColor: chartColors[index % chartColors.length] }}
                >
                  {value > 0 && value}
                </div>
              </div>
            </div>
            <div className="w-12 text-sm font-medium text-right shrink-0">{value}</div>
          </div>
        );
      })}
    </div>
  );
};

const SimplePieChart = ({ data, colors, title }) => {
  const entries = !data || (typeof data === 'object' && !Array.isArray(data))
    ? Object.entries(data || {})
    : data.map((d) => [d.category || d.status || d.priority || d.label || '', d.count ?? d.value ?? 0]);
  if (!entries.length) {
    return <div className="flex items-center justify-center h-48 text-muted-foreground">No data available</div>;
  }
  const total = entries.reduce((sum, [, v]) => sum + v, 0);
  if (total === 0) return <div className="flex items-center justify-center h-48 text-muted-foreground">No data available</div>;
  const defaultColors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16'];
  const chartColors = colors || defaultColors;
  let currentAngle = 0;
  const segments = entries.map(([key, value], index) => {
    const percentage = (value / total) * 100;
    const angle = (percentage / 100) * 360;
    const startAngle = currentAngle;
    currentAngle += angle;
    return { key, value, percentage: percentage.toFixed(1), startAngle, angle, color: chartColors[index % chartColors.length] };
  });
  return (
    <div className="flex flex-col items-center gap-4">
      {title && <h4 className="font-medium text-sm text-muted-foreground">{title}</h4>}
      <div className="relative w-48 h-48 sm:w-56 sm:h-56">
        <svg width="100%" height="100%" viewBox="0 0 200 200" className="transform -rotate-90">
          {segments.map((segment, index) => {
            const largeArcFlag = segment.angle > 180 ? 1 : 0;
            const x1 = 100 + 90 * Math.cos((segment.startAngle * Math.PI) / 180);
            const y1 = 100 + 90 * Math.sin((segment.startAngle * Math.PI) / 180);
            const x2 = 100 + 90 * Math.cos(((segment.startAngle + segment.angle) * Math.PI) / 180);
            const y2 = 100 + 90 * Math.sin(((segment.startAngle + segment.angle) * Math.PI) / 180);
            return (
              <path
                key={index}
                d={`M 100 100 L ${x1} ${y1} A 90 90 0 ${largeArcFlag} 1 ${x2} ${y2} Z`}
                fill={segment.color}
                stroke="white"
                strokeWidth="2"
              />
            );
          })}
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="text-center">
            <div className="text-2xl font-bold">{total}</div>
            <div className="text-xs text-muted-foreground">Total</div>
          </div>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2 w-full max-w-xs">
        {segments.map((segment, index) => (
          <div key={index} className="flex items-center gap-2 text-xs sm:text-sm">
            <div className="w-3 h-3 rounded shrink-0" style={{ backgroundColor: segment.color }} />
            <span className="truncate flex-1">{segment.key}</span>
            <span className="font-medium shrink-0">{segment.percentage}%</span>
          </div>
        ))}
      </div>
    </div>
  );
};

const SimpleLineChart = ({ data, color = '#3b82f6', height = 200, title }) => {
  const arr = Array.isArray(data) ? data : [];
  if (arr.length === 0) return <div className="flex items-center justify-center h-48 text-muted-foreground">No data available</div>;
  const values = arr.map((d) => d.value ?? d.count ?? 0);
  const maxValue = Math.max(...values, 1);
  const labels = arr.map((d) => d.label ?? d.date ?? d.month ?? '');
  const points = values.map((value, index) => {
    const x = (index / (values.length - 1 || 1)) * 100;
    const y = 100 - (value / maxValue) * 80;
    return `${x},${y}`;
  }).join(' ');
  const areaPoints = `0,100 ${points} 100,100`;
  return (
    <div className="space-y-2">
      {title && <h4 className="font-medium text-sm text-muted-foreground">{title}</h4>}
      <div className="relative w-full" style={{ height: `${height}px` }}>
        <svg width="100%" height="100%" viewBox="0 0 100 100" preserveAspectRatio="none">
          <polygon points={areaPoints} fill={`${color}20`} />
          <polyline points={points} fill="none" stroke={color} strokeWidth="0.5" strokeLinecap="round" strokeLinejoin="round" />
          {values.map((value, index) => {
            const x = (index / (values.length - 1 || 1)) * 100;
            const y = 100 - (value / maxValue) * 80;
            return <circle key={index} cx={x} cy={y} r="1.5" fill={color} />;
          })}
        </svg>
        <div className="absolute bottom-0 left-0 right-0 flex justify-between text-[10px] text-muted-foreground px-1">
          {labels.length <= 7 ? labels.map((label, i) => <span key={i} className="truncate">{label}</span>) : <><span>{labels[0]}</span><span>{labels[Math.floor(labels.length / 2)]}</span><span>{labels[labels.length - 1]}</span></>}
        </div>
      </div>
    </div>
  );
};

const SimpleAreaChart = ({ data, color = '#10b981', height = 200, title }) => (
  <SimpleLineChart data={data} color={color} height={height} title={title} />
);

const renderChart = (chartData) => {
  if (!chartData) return null;
  const { type, data, title, color, colors } = chartData;
  switch (type) {
    case 'bar':
      return <SimpleBarChart data={data} colors={colors} title={title} />;
    case 'pie':
      return <SimplePieChart data={data} colors={colors} title={title} />;
    case 'line':
      return <SimpleLineChart data={data} color={color} title={title} />;
    case 'area':
      return <SimpleAreaChart data={data} color={color} title={title} />;
    default:
      return <SimpleBarChart data={data} colors={colors} title={title} />;
  }
};

const examplePrompts = [
  'Show tickets by status as a pie chart',
  'Display ticket volume over time as a line chart',
  'Compare tickets by category as a bar chart',
  'Show tickets by priority as a pie chart',
  'Top 5 categories by ticket count',
  'Tickets trend by date (last 20 days)',
  'Auto-resolved vs manual resolution',
];

export default function FrontlineAIGraphs() {
  const { toast } = useToast();
  const [activeTab, setActiveTab] = useState('generate');
  const [prompt, setPrompt] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [generating, setGenerating] = useState(false);
  const [generatedChart, setGeneratedChart] = useState(null);
  const [chartInsights, setChartInsights] = useState('');
  const [saveModalOpen, setSaveModalOpen] = useState(false);
  const [saveTitle, setSaveTitle] = useState('');
  const [saveTags, setSaveTags] = useState('');
  const [saving, setSaving] = useState(false);
  const [savedPrompts, setSavedPrompts] = useState([]);
  const [loadingPrompts, setLoadingPrompts] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterFavorites, setFilterFavorites] = useState(false);

  useEffect(() => {
    if (activeTab === 'saved') {
      fetchSavedPrompts();
    }
  }, [activeTab]);

  const fetchSavedPrompts = async () => {
    try {
      setLoadingPrompts(true);
      const response = await frontlineAgentService.getFrontlineSavedGraphPrompts();
      if (response.status === 'success') setSavedPrompts(response.data || []);
    } catch (error) {
      toast({ title: 'Error', description: 'Failed to load saved prompts', variant: 'destructive' });
    } finally {
      setLoadingPrompts(false);
    }
  };

  const handleGenerate = async () => {
    if (!prompt.trim()) {
      toast({ title: 'Empty prompt', description: 'Enter a prompt to generate a graph', variant: 'destructive' });
      return;
    }
    try {
      setGenerating(true);
      setGeneratedChart(null);
      setChartInsights('');
      const response = await frontlineAgentService.generateFrontlineGraph(prompt, dateFrom || undefined, dateTo || undefined);
      if (response.status === 'success') {
        setGeneratedChart(response.data.chart);
        setChartInsights(response.data.insights || '');
        toast({ title: 'Graph generated', description: 'Your visualization is ready' });
      } else {
        throw new Error(response.message || 'Failed to generate graph');
      }
    } catch (error) {
      toast({ title: 'Generation failed', description: error.message || 'Try a different prompt.', variant: 'destructive' });
    } finally {
      setGenerating(false);
    }
  };

  const handleSavePrompt = async () => {
    if (!saveTitle.trim()) {
      toast({ title: 'Title required', description: 'Enter a title for this prompt', variant: 'destructive' });
      return;
    }
    try {
      setSaving(true);
      const tags = saveTags.split(',').map((t) => t.trim()).filter(Boolean);
      const response = await frontlineAgentService.saveFrontlineGraphPrompt({
        title: saveTitle,
        prompt,
        tags,
        chart_type: generatedChart?.type || 'bar',
      });
      if (response.status === 'success') {
        toast({ title: 'Prompt saved', description: 'Find it in Saved Prompts' });
        setSaveModalOpen(false);
        setSaveTitle('');
        setSaveTags('');
        if (activeTab === 'saved') fetchSavedPrompts();
      } else throw new Error(response.message || 'Failed to save');
    } catch (error) {
      toast({ title: 'Save failed', description: error.message, variant: 'destructive' });
    } finally {
      setSaving(false);
    }
  };

  const handleRunSavedPrompt = async (savedPrompt) => {
    setPrompt(savedPrompt.prompt);
    setActiveTab('generate');
    setTimeout(async () => {
      try {
        setGenerating(true);
        setGeneratedChart(null);
        setChartInsights('');
        const response = await frontlineAgentService.generateFrontlineGraph(savedPrompt.prompt, dateFrom || undefined, dateTo || undefined);
        if (response.status === 'success') {
          setGeneratedChart(response.data.chart);
          setChartInsights(response.data.insights || '');
        }
      } catch (error) {
        toast({ title: 'Generation failed', description: 'Failed to run saved prompt', variant: 'destructive' });
      } finally {
        setGenerating(false);
      }
    }, 100);
  };

  const handleDeletePrompt = async (promptId) => {
    try {
      const response = await frontlineAgentService.deleteFrontlineGraphPrompt(promptId);
      if (response.status === 'success') {
        setSavedPrompts((prev) => prev.filter((p) => p.id !== promptId));
        toast({ title: 'Prompt deleted' });
      }
    } catch (error) {
      toast({ title: 'Delete failed', description: error.message, variant: 'destructive' });
    }
  };

  const handleToggleFavorite = async (promptId, currentFavorite) => {
    try {
      const response = await frontlineAgentService.toggleFrontlineGraphPromptFavorite(promptId, !currentFavorite);
      if (response.status === 'success') {
        setSavedPrompts((prev) => prev.map((p) => (p.id === promptId ? { ...p, is_favorite: !currentFavorite } : p)));
      }
    } catch (error) {
      toast({ title: 'Failed to update favorite', variant: 'destructive' });
    }
  };

  const handleCopyPrompt = (text) => {
    navigator.clipboard.writeText(text);
    toast({ title: 'Copied', description: 'Prompt copied to clipboard' });
  };

  const filteredPrompts = savedPrompts.filter((p) => {
    const matchSearch = !searchQuery ||
      p.title?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.prompt?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (p.tags || []).some((t) => String(t).toLowerCase().includes(searchQuery.toLowerCase()));
    const matchFav = !filterFavorites || p.is_favorite;
    return matchSearch && matchFav;
  });

  return (
    <div className="space-y-4">
      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="grid w-full grid-cols-2 max-w-md">
          <TabsTrigger value="generate" className="text-sm">
            <Sparkles className="h-4 w-4 mr-2" />
            Generate
          </TabsTrigger>
          <TabsTrigger value="saved" className="text-sm">
            <Star className="h-4 w-4 mr-2" />
            Saved Prompts
          </TabsTrigger>
        </TabsList>

        <TabsContent value="generate" className="space-y-4 mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Sparkles className="h-5 w-5" />
                AI Graph Maker
              </CardTitle>
              <CardDescription>
                Describe the graph you want in plain language. Use ticket data by status, category, priority, or over time.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label>Prompt</Label>
                <Textarea
                  placeholder="e.g. Show tickets by status as a pie chart"
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  rows={3}
                  className="resize-none"
                />
              </div>
              <div className="flex flex-wrap items-end gap-3">
                <div className="space-y-1">
                  <Label className="text-xs">From</Label>
                  <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="w-[140px]" />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">To</Label>
                  <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="w-[140px]" />
                </div>
                <Button onClick={handleGenerate} disabled={generating}>
                  {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : <BarChart3 className="h-4 w-4" />}
                  {generating ? ' Generating...' : ' Generate graph'}
                </Button>
              </div>
              <div className="flex flex-wrap gap-2">
                {examplePrompts.map((ex) => (
                  <Button key={ex} variant="outline" size="sm" onClick={() => setPrompt(ex)} className="text-xs">
                    {ex}
                  </Button>
                ))}
              </div>
              {generatedChart && (
                <div className="space-y-4 pt-4 border-t">
                  <div className="flex items-start justify-between gap-2">
                    <div className="p-3 rounded-lg bg-muted/50 border text-sm flex-1">{chartInsights}</div>
                    <Button variant="outline" size="sm" onClick={() => { setSaveTitle(generatedChart.title || ''); setSaveModalOpen(true); }}>
                      <Save className="h-4 w-4 mr-2" />
                      Save Prompt
                    </Button>
                  </div>
                  <div className="min-h-[280px]">{renderChart(generatedChart)}</div>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="saved" className="space-y-4 mt-4">
          <Card>
            <CardHeader className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
              <div>
                <CardTitle>Saved Prompts</CardTitle>
                <CardDescription>Your saved graph prompts for quick access</CardDescription>
              </div>
              <div className="flex items-center gap-2">
                <Button variant={filterFavorites ? 'default' : 'outline'} size="sm" onClick={() => setFilterFavorites(!filterFavorites)}>
                  <Star className={`h-4 w-4 ${filterFavorites ? '' : 'mr-2'}`} />
                  {!filterFavorites && 'Favorites'}
                </Button>
                <Button variant="outline" size="sm" onClick={fetchSavedPrompts} disabled={loadingPrompts}>
                  <RefreshCw className={`h-4 w-4 ${loadingPrompts ? 'animate-spin' : ''}`} />
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input placeholder="Search prompts..." value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} className="pl-9" />
              </div>
              {loadingPrompts ? (
                <div className="py-8 flex justify-center">
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
              ) : filteredPrompts.length === 0 ? (
                <div className="py-8 text-center">
                  <Star className="h-10 w-10 mx-auto text-muted-foreground mb-3" />
                  <p className="text-sm font-medium mb-1">No saved prompts</p>
                  <p className="text-xs text-muted-foreground">
                    {searchQuery || filterFavorites ? 'Try adjusting your filters' : 'Generate a graph and save it to see it here'}
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  {filteredPrompts.map((savedPrompt) => (
                    <Card key={savedPrompt.id} className="overflow-hidden">
                      <CardContent className="p-3 sm:p-4">
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-1">
                              <h4 className="font-medium text-sm truncate">{savedPrompt.title}</h4>
                              {savedPrompt.is_favorite && <Star className="h-3.5 w-3.5 fill-yellow-400 text-yellow-400 shrink-0" />}
                            </div>
                            <p className="text-xs text-muted-foreground line-clamp-2 mb-2">{savedPrompt.prompt}</p>
                            <div className="flex items-center gap-2 flex-wrap">
                              {savedPrompt.chart_type && <Badge variant="secondary" className="text-[10px]">{savedPrompt.chart_type}</Badge>}
                              {(savedPrompt.tags || []).slice(0, 3).map((tag, i) => (
                                <Badge key={i} variant="outline" className="text-[10px]">{tag}</Badge>
                              ))}
                              {savedPrompt.created_at && (
                                <span className="text-[10px] text-muted-foreground flex items-center gap-1">
                                  <Clock className="h-3 w-3" />{new Date(savedPrompt.created_at).toLocaleDateString()}
                                </span>
                              )}
                            </div>
                          </div>
                          <div className="flex items-center gap-1 shrink-0">
                            <Button variant="default" size="sm" onClick={() => handleRunSavedPrompt(savedPrompt)}>
                              <Play className="h-3.5 w-3.5 mr-1" />Run
                            </Button>
                            <DropdownMenu>
                              <DropdownMenuTrigger asChild>
                                <Button variant="ghost" size="sm" className="h-8 w-8 p-0"><MoreVertical className="h-4 w-4" /></Button>
                              </DropdownMenuTrigger>
                              <DropdownMenuContent align="end">
                                <DropdownMenuItem onClick={() => handleToggleFavorite(savedPrompt.id, savedPrompt.is_favorite)}>
                                  {savedPrompt.is_favorite ? <><StarOff className="h-4 w-4 mr-2" />Remove from favorites</> : <><Star className="h-4 w-4 mr-2" />Add to favorites</>}
                                </DropdownMenuItem>
                                <DropdownMenuItem onClick={() => handleCopyPrompt(savedPrompt.prompt)}>
                                  <Copy className="h-4 w-4 mr-2" />Copy prompt
                                </DropdownMenuItem>
                                <DropdownMenuSeparator />
                                <DropdownMenuItem onClick={() => handleDeletePrompt(savedPrompt.id)} className="text-destructive focus:text-destructive">
                                  <Trash2 className="h-4 w-4 mr-2" />Delete
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
        </TabsContent>
      </Tabs>

      <Dialog open={saveModalOpen} onOpenChange={setSaveModalOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Save Prompt</DialogTitle>
            <DialogDescription>Save this prompt for quick access later</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="save-title">Title</Label>
              <Input id="save-title" value={saveTitle} onChange={(e) => setSaveTitle(e.target.value)} placeholder="e.g., Tickets by status" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="save-prompt">Prompt</Label>
              <Textarea id="save-prompt" value={prompt} onChange={(e) => setPrompt(e.target.value)} className="min-h-[80px] text-sm" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="save-tags">Tags (comma-separated)</Label>
              <Input id="save-tags" value={saveTags} onChange={(e) => setSaveTags(e.target.value)} placeholder="e.g., analytics, status" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setSaveModalOpen(false)}>Cancel</Button>
            <Button onClick={handleSavePrompt} disabled={saving}>
              {saving ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Save className="h-4 w-4 mr-2" />}
              {saving ? 'Saving...' : 'Save Prompt'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
