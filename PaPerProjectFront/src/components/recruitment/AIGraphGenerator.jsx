import React, { useState, useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Loader2,
  Sparkles,
  Save,
  Star,
  StarOff,
  Play,
  Trash2,
  MoreVertical,
  BarChart3,
  PieChart,
  TrendingUp,
  Activity,
  Clock,
  Tag,
  Search,
  RefreshCw,
  Copy,
  Download,
  LayoutDashboard,
} from 'lucide-react';
import { generateGraph, getSavedPrompts, savePrompt, deletePrompt, toggleFavorite, toggleDashboardPrompt, isPromptOnDashboard } from '@/services/recruitmentAgentService';

// Chart Components
const SimpleBarChart = ({ data, colors, height = 250, title }) => {
  if (!data || Object.keys(data).length === 0) {
    return <div className="flex items-center justify-center h-48 text-muted-foreground">No data available</div>;
  }
  
  const maxValue = Math.max(...Object.values(data), 1);
  const defaultColors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16'];
  const chartColors = colors || defaultColors;

  return (
    <div className="space-y-3" style={{ minHeight: `${height}px` }}>
      {title && <h4 className="font-medium text-sm text-muted-foreground mb-4">{title}</h4>}
      {Object.entries(data).map(([key, value], index) => {
        const percentage = (value / maxValue) * 100;
        return (
          <div key={key} className="flex items-center gap-3">
            <div className="w-24 sm:w-32 text-xs sm:text-sm text-muted-foreground truncate shrink-0" title={key}>
              {key}
            </div>
            <div className="flex-1 min-w-0">
              <div className="h-8 bg-muted rounded-md overflow-hidden">
                <div
                  className="h-full flex items-center justify-end pr-2 text-xs font-semibold text-white transition-all duration-500"
                  style={{
                    width: `${Math.max(percentage, 5)}%`,
                    backgroundColor: chartColors[index % chartColors.length],
                  }}
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
  if (!data || Object.keys(data).length === 0) {
    return <div className="flex items-center justify-center h-48 text-muted-foreground">No data available</div>;
  }

  const total = Object.values(data).reduce((sum, val) => sum + val, 0);
  if (total === 0) {
    return <div className="flex items-center justify-center h-48 text-muted-foreground">No data available</div>;
  }

  const defaultColors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16'];
  const chartColors = colors || defaultColors;

  let currentAngle = 0;
  const segments = Object.entries(data).map(([key, value], index) => {
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
  if (!data || data.length === 0) {
    return <div className="flex items-center justify-center h-48 text-muted-foreground">No data available</div>;
  }

  const values = data.map(d => d.value || d.count || 0);
  const maxValue = Math.max(...values, 1);
  const labels = data.map(d => d.label || d.date || d.month || '');

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
          {labels.length <= 7 ? labels.map((label, i) => (
            <span key={i} className="truncate">{label}</span>
          )) : (
            <>
              <span>{labels[0]}</span>
              <span>{labels[Math.floor(labels.length / 2)]}</span>
              <span>{labels[labels.length - 1]}</span>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

const SimpleAreaChart = ({ data, color = '#10b981', height = 200, title }) => {
  return <SimpleLineChart data={data} color={color} height={height} title={title} />;
};

const SimpleScatterPlot = ({ data, color = '#8b5cf6', height = 200, title }) => {
  if (!data || data.length === 0) {
    return <div className="flex items-center justify-center h-48 text-muted-foreground">No data available</div>;
  }

  const xValues = data.map(d => d.x || 0);
  const yValues = data.map(d => d.y || 0);
  const maxX = Math.max(...xValues, 1);
  const maxY = Math.max(...yValues, 1);

  return (
    <div className="space-y-2">
      {title && <h4 className="font-medium text-sm text-muted-foreground">{title}</h4>}
      <div className="relative w-full border-l border-b border-muted" style={{ height: `${height}px` }}>
        <svg width="100%" height="100%" viewBox="0 0 100 100" preserveAspectRatio="none">
          {data.map((point, index) => {
            const x = (point.x / maxX) * 95 + 2;
            const y = 98 - (point.y / maxY) * 95;
            return (
              <circle
                key={index}
                cx={x}
                cy={y}
                r="2"
                fill={color}
                opacity="0.7"
              />
            );
          })}
        </svg>
      </div>
    </div>
  );
};

const SimpleHeatMap = ({ data, title }) => {
  if (!data || !data.rows || !data.cols || !data.values) {
    return <div className="flex items-center justify-center h-48 text-muted-foreground">No data available</div>;
  }

  const maxValue = Math.max(...data.values.flat(), 1);
  const getColor = (value) => {
    const intensity = value / maxValue;
    return `rgba(59, 130, 246, ${intensity})`;
  };

  return (
    <div className="space-y-2">
      {title && <h4 className="font-medium text-sm text-muted-foreground">{title}</h4>}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr>
              <th className="p-1"></th>
              {data.cols.map((col, i) => (
                <th key={i} className="p-1 font-medium truncate max-w-[60px]">{col}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                <td className="p-1 font-medium truncate max-w-[80px]">{row}</td>
                {data.values[rowIndex]?.map((value, colIndex) => (
                  <td
                    key={colIndex}
                    className="p-1 text-center rounded"
                    style={{ backgroundColor: getColor(value) }}
                  >
                    {value}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

// Chart type icons mapping
const chartTypeIcons = {
  bar: BarChart3,
  pie: PieChart,
  line: TrendingUp,
  area: Activity,
  scatter: Activity,
  heatmap: BarChart3,
};

// Render chart based on type
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
    case 'scatter':
      return <SimpleScatterPlot data={data} color={color} title={title} />;
    case 'heatmap':
      return <SimpleHeatMap data={data} title={title} />;
    default:
      return <SimpleBarChart data={data} colors={colors} title={title} />;
  }
};

// Example prompts for users
const examplePrompts = [
  "Show candidate decisions as a pie chart",
  "Display monthly CV processing trends as a line chart",
  "Compare interview outcomes by job position as a bar chart",
  "Show top 5 jobs by number of applicants",
  "Show interviews by hour of day",
  "Display interviews by day of week",
  "Show online vs onsite interview distribution",
  "Show interview time gaps distribution",
  "Display interviews by job role",
  "Show interview scheduling summary",
];

const AIGraphGenerator = () => {
  const { toast } = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const runPromptIdFromUrl = searchParams.get('runPromptId');
  const hasRunFromUrl = useRef(false);
  const [activeTab, setActiveTab] = useState('generate');
  
  // Generate tab state
  const [prompt, setPrompt] = useState('');
  const [generating, setGenerating] = useState(false);
  const [generatedChart, setGeneratedChart] = useState(null);
  const [chartInsights, setChartInsights] = useState('');
  
  // Save modal state
  const [saveModalOpen, setSaveModalOpen] = useState(false);
  const [saveTitle, setSaveTitle] = useState('');
  const [saveTags, setSaveTags] = useState('');
  const [saving, setSaving] = useState(false);
  
  // Saved prompts state
  const [savedPrompts, setSavedPrompts] = useState([]);
  const [loadingPrompts, setLoadingPrompts] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterFavorites, setFilterFavorites] = useState(false);

  useEffect(() => {
    if (activeTab === 'saved') {
      fetchSavedPrompts();
    }
  }, [activeTab]);

  // When opened with ?runPromptId=123 (e.g. from dashboard card), run that saved prompt and show graph
  useEffect(() => {
    const id = runPromptIdFromUrl ? parseInt(runPromptIdFromUrl, 10) : null;
    if (!id || hasRunFromUrl.current) return;

    const run = async () => {
      hasRunFromUrl.current = true;
      try {
        const response = await getSavedPrompts();
        const list = response?.data || [];
        const savedPrompt = list.find((p) => p.id === id);
        if (savedPrompt) {
          setPrompt(savedPrompt.prompt);
          setActiveTab('generate');
          setGenerating(true);
          setGeneratedChart(null);
          setChartInsights('');
          const genResponse = await generateGraph(savedPrompt.prompt);
          if (genResponse.status === 'success') {
            setGeneratedChart(genResponse.data.chart);
            setChartInsights(genResponse.data.insights || '');
          }
          setSearchParams((prev) => {
            const next = new URLSearchParams(prev);
            next.delete('runPromptId');
            return next;
          });
        }
      } catch (e) {
        console.error('Error running prompt from URL:', e);
      } finally {
        setGenerating(false);
      }
    };
    run();
  }, [runPromptIdFromUrl]);

  const fetchSavedPrompts = async () => {
    try {
      setLoadingPrompts(true);
      const response = await getSavedPrompts();
      if (response.status === 'success') {
        setSavedPrompts(response.data || []);
      }
    } catch (error) {
      console.error('Error fetching saved prompts:', error);
      toast({
        title: 'Error',
        description: 'Failed to load saved prompts',
        variant: 'destructive',
      });
    } finally {
      setLoadingPrompts(false);
    }
  };

  const handleGenerate = async () => {
    if (!prompt.trim()) {
      toast({
        title: 'Empty prompt',
        description: 'Please enter a prompt to generate a graph',
        variant: 'destructive',
      });
      return;
    }

    try {
      setGenerating(true);
      setGeneratedChart(null);
      setChartInsights('');

      const response = await generateGraph(prompt);
      
      if (response.status === 'success') {
        setGeneratedChart(response.data.chart);
        setChartInsights(response.data.insights || '');
        toast({
          title: 'Graph generated',
          description: 'Your visualization is ready',
        });
      } else {
        throw new Error(response.message || 'Failed to generate graph');
      }
    } catch (error) {
      console.error('Error generating graph:', error);
      toast({
        title: 'Generation failed',
        description: error.message || 'Failed to generate graph. Please try a different prompt.',
        variant: 'destructive',
      });
    } finally {
      setGenerating(false);
    }
  };

  const handleSavePrompt = async () => {
    if (!saveTitle.trim()) {
      toast({
        title: 'Title required',
        description: 'Please enter a title for this prompt',
        variant: 'destructive',
      });
      return;
    }

    try {
      setSaving(true);
      const tags = saveTags.split(',').map(t => t.trim()).filter(t => t);
      
      const response = await savePrompt({
        title: saveTitle,
        prompt: prompt,
        tags: tags,
        chart_type: generatedChart?.type || 'bar',
      });

      if (response.status === 'success') {
        toast({
          title: 'Prompt saved',
          description: 'You can find it in your saved prompts',
        });
        setSaveModalOpen(false);
        setSaveTitle('');
        setSaveTags('');
        // Refresh saved prompts if on that tab
        if (activeTab === 'saved') {
          fetchSavedPrompts();
        }
      } else {
        throw new Error(response.message || 'Failed to save prompt');
      }
    } catch (error) {
      console.error('Error saving prompt:', error);
      toast({
        title: 'Save failed',
        description: error.message || 'Failed to save prompt',
        variant: 'destructive',
      });
    } finally {
      setSaving(false);
    }
  };

  const handleRunSavedPrompt = async (savedPrompt) => {
    setPrompt(savedPrompt.prompt);
    setActiveTab('generate');
    
    // Auto-generate after switching
    setTimeout(async () => {
      try {
        setGenerating(true);
        setGeneratedChart(null);
        setChartInsights('');

        const response = await generateGraph(savedPrompt.prompt);
        
        if (response.status === 'success') {
          setGeneratedChart(response.data.chart);
          setChartInsights(response.data.insights || '');
        }
      } catch (error) {
        console.error('Error running saved prompt:', error);
        toast({
          title: 'Generation failed',
          description: 'Failed to generate graph from saved prompt',
          variant: 'destructive',
        });
      } finally {
        setGenerating(false);
      }
    }, 100);
  };

  const handleDeletePrompt = async (promptId) => {
    try {
      const response = await deletePrompt(promptId);
      if (response.status === 'success') {
        setSavedPrompts(prev => prev.filter(p => p.id !== promptId));
        toast({
          title: 'Prompt deleted',
          description: 'The prompt has been removed',
        });
      }
    } catch (error) {
      console.error('Error deleting prompt:', error);
      toast({
        title: 'Delete failed',
        description: 'Failed to delete prompt',
        variant: 'destructive',
      });
    }
  };

  const handleToggleFavorite = async (promptId, currentFavorite) => {
    try {
      const response = await toggleFavorite(promptId, !currentFavorite);
      if (response.status === 'success') {
        setSavedPrompts(prev => prev.map(p => 
          p.id === promptId ? { ...p, is_favorite: !currentFavorite } : p
        ));
      }
    } catch (error) {
      console.error('Error toggling favorite:', error);
    }
  };

  const handleToggleDashboard = async (savedPrompt) => {
    try {
      const response = await toggleDashboardPrompt(savedPrompt.id);
      if (response.status === 'success' && response.data) {
        setSavedPrompts(prev => prev.map(p =>
          p.id === savedPrompt.id ? { ...p, tags: response.data.tags || p.tags } : p
        ));
        toast({
          title: response.data.on_dashboard ? 'Added to dashboard' : 'Removed from dashboard',
          description: response.data.on_dashboard ? 'Card will appear on recruitment dashboard' : '',
        });
      }
    } catch (error) {
      console.error('Error toggling dashboard:', error);
      toast({
        title: 'Failed',
        description: 'Could not update dashboard',
        variant: 'destructive',
      });
    }
  };

  const handleCopyPrompt = (promptText) => {
    navigator.clipboard.writeText(promptText);
    toast({
      title: 'Copied',
      description: 'Prompt copied to clipboard',
    });
  };

  const filteredPrompts = savedPrompts.filter(p => {
    const matchesSearch = !searchQuery || 
      p.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.prompt.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.tags?.some(t => t.toLowerCase().includes(searchQuery.toLowerCase()));
    const matchesFavorite = !filterFavorites || p.is_favorite;
    return matchesSearch && matchesFavorite;
  });

  return (
    <div className="space-y-4 sm:space-y-6 w-full">
      <div>
        <h2 className="text-xl sm:text-2xl font-bold py-3 sm:py-5">AI Graph Generator</h2>
        <p className="text-xs sm:text-sm text-muted-foreground">
          Generate visualizations using natural language. Describe what you want to see and AI will create the chart.
        </p>
      </div>

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

        {/* Generate Tab */}
        <TabsContent value="generate" className="space-y-4 mt-4">
          <Card>
            <CardHeader className="p-4 sm:p-6">
              <CardTitle className="text-base sm:text-lg flex items-center gap-2">
                <Sparkles className="h-5 w-5 text-primary" />
                Create Visualization
              </CardTitle>
              <CardDescription className="text-xs sm:text-sm">
                Describe the chart you want to create in plain English
              </CardDescription>
            </CardHeader>
            <CardContent className="p-4 sm:p-6 pt-0 space-y-4">
              {/* Prompt Input */}
              <div className="space-y-2">
                <Label htmlFor="prompt" className="text-sm font-medium">Your Prompt</Label>
                <Textarea
                  id="prompt"
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  placeholder="e.g., Show monthly CV processing trends as a line chart"
                  className="min-h-[100px] text-sm resize-none"
                />
              </div>

              {/* Example Prompts */}
              <div className="space-y-2">
                <Label className="text-xs text-muted-foreground">Try these examples:</Label>
                <div className="flex flex-wrap gap-2">
                  {examplePrompts.slice(0, 4).map((example, index) => (
                    <Button
                      key={index}
                      variant="outline"
                      size="sm"
                      className="text-xs h-auto py-1.5 px-2"
                      onClick={() => setPrompt(example)}
                    >
                      {example}
                    </Button>
                  ))}
                </div>
              </div>

              {/* Generate Button */}
              <Button
                onClick={handleGenerate}
                disabled={generating || !prompt.trim()}
                className="w-full sm:w-auto"
              >
                {generating ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Generating...
                  </>
                ) : (
                  <>
                    <Sparkles className="h-4 w-4 mr-2" />
                    Generate Graph
                  </>
                )}
              </Button>
            </CardContent>
          </Card>

          {/* Generated Chart Display */}
          {generating && (
            <Card>
              <CardContent className="py-12 flex flex-col items-center justify-center">
                <Loader2 className="h-8 w-8 animate-spin text-primary mb-4" />
                <p className="text-sm text-muted-foreground">Analyzing your request and generating visualization...</p>
              </CardContent>
            </Card>
          )}

          {generatedChart && !generating && (
            <Card>
              <CardHeader className="p-4 sm:p-6 flex flex-row items-start justify-between">
                <div>
                  <CardTitle className="text-base sm:text-lg flex items-center gap-2">
                    {chartTypeIcons[generatedChart.type] && 
                      React.createElement(chartTypeIcons[generatedChart.type], { className: "h-5 w-5" })}
                    {generatedChart.title || 'Generated Chart'}
                  </CardTitle>
                  {chartInsights && (
                    <CardDescription className="text-xs sm:text-sm mt-1">
                      {chartInsights}
                    </CardDescription>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setSaveTitle(generatedChart.title || '');
                      setSaveModalOpen(true);
                    }}
                  >
                    <Save className="h-4 w-4 mr-2" />
                    Save Prompt
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="p-4 sm:p-6 pt-0">
                <div className="bg-muted/30 rounded-lg p-4 sm:p-6">
                  {renderChart(generatedChart)}
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* Saved Prompts Tab */}
        <TabsContent value="saved" className="space-y-4 mt-4">
          <Card>
            <CardHeader className="p-4 sm:p-6">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                <div>
                  <CardTitle className="text-base sm:text-lg">Saved Prompts</CardTitle>
                  <CardDescription className="text-xs sm:text-sm">
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
                  <p className="text-sm font-medium mb-1">No saved prompts</p>
                  <p className="text-xs text-muted-foreground">
                    {searchQuery || filterFavorites 
                      ? 'Try adjusting your filters'
                      : 'Generate a graph and save it to see it here'}
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
                              {savedPrompt.is_favorite && (
                                <Star className="h-3.5 w-3.5 fill-yellow-400 text-yellow-400 shrink-0" />
                              )}
                            </div>
                            <p className="text-xs text-muted-foreground line-clamp-2 mb-2">
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
                                <span className="text-[10px] text-muted-foreground flex items-center gap-1">
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
                              onClick={() => handleRunSavedPrompt(savedPrompt)}
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
        </TabsContent>
      </Tabs>

      {/* Save Prompt Modal */}
      <Dialog open={saveModalOpen} onOpenChange={setSaveModalOpen}>
        <DialogContent className="w-[95vw] max-w-md">
          <DialogHeader>
            <DialogTitle>Save Prompt</DialogTitle>
            <DialogDescription>
              Save this prompt for quick access later
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="save-title">Title</Label>
              <Input
                id="save-title"
                value={saveTitle}
                onChange={(e) => setSaveTitle(e.target.value)}
                placeholder="e.g., Monthly CV Trends"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="save-prompt">Prompt</Label>
              <Textarea
                id="save-prompt"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                className="min-h-[80px] text-sm"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="save-tags">Tags (comma-separated)</Label>
              <Input
                id="save-tags"
                value={saveTags}
                onChange={(e) => setSaveTags(e.target.value)}
                placeholder="e.g., analytics, monthly, trends"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setSaveModalOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleSavePrompt} disabled={saving}>
              {saving ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Saving...
                </>
              ) : (
                <>
                  <Save className="h-4 w-4 mr-2" />
                  Save Prompt
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default AIGraphGenerator;
