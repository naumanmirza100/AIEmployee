import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/components/ui/use-toast';
import { Loader2, TrendingUp, Users, Calendar, BarChart3, PieChart, Activity, Target } from 'lucide-react';
import { getRecruitmentAnalytics, getJobDescriptions } from '@/services/recruitmentAgentService';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

const RecruitmentAnalytics = () => {
  const { toast } = useToast();
  const [loading, setLoading] = useState(true);
  const [analytics, setAnalytics] = useState(null);
  const [timeRange, setTimeRange] = useState({ days: 30, months: 6 });
  const [selectedJobId, setSelectedJobId] = useState(null);
  const [jobs, setJobs] = useState([]);

  useEffect(() => {
    fetchJobs();
  }, []);

  useEffect(() => {
    fetchAnalytics();
  }, [timeRange, selectedJobId]);

  const fetchJobs = async () => {
    try {
      const response = await getJobDescriptions();
      if (response.status === 'success') {
        setJobs(response.data || []);
      }
    } catch (error) {
      console.error('Error fetching jobs:', error);
    }
  };

  const fetchAnalytics = async () => {
    try {
      setLoading(true);
      const response = await getRecruitmentAnalytics(timeRange.days, timeRange.months, selectedJobId);
      if (response.status === 'success') {
        setAnalytics(response.data);
      } else {
        throw new Error(response.message || 'Failed to load analytics data');
      }
    } catch (error) {
      console.error('Error fetching analytics:', error);
      const errorMessage = error?.message || error?.data?.message || 'Failed to load analytics data. Please ensure the backend is running and CORS is configured correctly.';
      toast({
        title: 'Error',
        description: errorMessage,
        variant: 'destructive',
      });
      setAnalytics(null);
    } finally {
      setLoading(false);
    }
  };

  // Helper function to calculate percentage for bar charts
  const calculatePercentage = (value, total) => {
    if (total === 0) return 0;
    return Math.round((value / total) * 100);
  };

  // Simple Bar Chart Component - responsive
  const SimpleBarChart = ({ data, colors, height = 200 }) => {
    const maxValue = Math.max(...Object.values(data), 1);
    
    return (
      <div className="space-y-2 min-w-0" style={{ height: `${height}px` }}>
        {Object.entries(data).map(([key, value], index) => {
          const percentage = calculatePercentage(value, maxValue);
          return (
            <div key={key} className="flex items-center gap-2 sm:gap-3 min-w-0">
              <div className="w-16 sm:w-20 md:w-24 text-xs sm:text-sm text-muted-foreground truncate shrink-0">
                {key}
              </div>
              <div className="flex-1 min-w-0 relative">
                <div className="h-6 sm:h-8 bg-muted rounded-md overflow-hidden">
                  <div
                    className="h-full flex items-center justify-end pr-1 sm:pr-2 text-[10px] sm:text-xs font-semibold text-white transition-all duration-500 min-w-[1.5rem]"
                    style={{
                      width: `${percentage}%`,
                      backgroundColor: colors[index % colors.length],
                    }}
                  >
                    {value > 0 && value}
                  </div>
                </div>
              </div>
              <div className="w-8 sm:w-10 md:w-12 text-xs sm:text-sm font-medium text-right shrink-0">
                {value}
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  // Simple Pie Chart Component (using CSS) - responsive size
  const SimplePieChart = ({ data, colors }) => {
    const total = Object.values(data).reduce((sum, val) => sum + val, 0);
    if (total === 0) {
      return (
        <div className="flex items-center justify-center w-40 h-40 sm:w-48 sm:h-48 md:w-52 md:h-52">
          <p className="text-muted-foreground text-sm">No data</p>
        </div>
      );
    }

    let currentAngle = 0;
    const segments = Object.entries(data).map(([key, value], index) => {
      const percentage = (value / total) * 100;
      const angle = (percentage / 100) * 360;
      const startAngle = currentAngle;
      currentAngle += angle;

      return {
        key,
        value,
        percentage: percentage.toFixed(1),
        startAngle,
        angle,
        color: colors[index % colors.length],
      };
    });

    return (
      <div className="flex flex-col items-center gap-4 w-full max-w-full overflow-hidden">
        <div className="relative shrink-0 w-40 h-40 sm:w-48 sm:h-48 md:w-52 md:h-52">
          <svg width="100%" height="100%" viewBox="0 0 200 200" className="transform -rotate-90">
            {segments.map((segment, index) => {
              const largeArcFlag = segment.angle > 180 ? 1 : 0;
              const x1 = 100 + 100 * Math.cos((segment.startAngle * Math.PI) / 180);
              const y1 = 100 + 100 * Math.sin((segment.startAngle * Math.PI) / 180);
              const x2 = 100 + 100 * Math.cos(((segment.startAngle + segment.angle) * Math.PI) / 180);
              const y2 = 100 + 100 * Math.sin(((segment.startAngle + segment.angle) * Math.PI) / 180);

              return (
                <path
                  key={index}
                  d={`M 100 100 L ${x1} ${y1} A 100 100 0 ${largeArcFlag} 1 ${x2} ${y2} Z`}
                  fill={segment.color}
                  stroke="white"
                  strokeWidth="2"
                />
              );
            })}
          </svg>
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center">
              <div className="text-lg sm:text-2xl font-bold">{total}</div>
              <div className="text-[10px] sm:text-xs text-muted-foreground">Total</div>
            </div>
          </div>
        </div>
        <div className="space-y-2 w-full min-w-0">
          {segments.map((segment, index) => (
            <div key={index} className="flex items-center justify-between text-xs sm:text-sm gap-2 min-w-0">
              <div className="flex items-center gap-2 min-w-0">
                <div
                  className="w-3 h-3 sm:w-4 sm:h-4 rounded shrink-0"
                  style={{ backgroundColor: segment.color }}
                />
                <span className="truncate">{segment.key}</span>
              </div>
              <div className="flex items-center gap-1 sm:gap-2 shrink-0">
                <span className="font-medium">{segment.value}</span>
                <span className="text-muted-foreground text-xs">({segment.percentage}%)</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  };

  // Line Chart Component - responsive
  const SimpleLineChart = ({ data, color = '#3b82f6', height = 200 }) => {
    if (!data || data.length === 0) {
      return (
        <div className="flex items-center justify-center h-32 sm:h-48 text-muted-foreground text-sm">
          No data available
        </div>
      );
    }

    const maxValue = Math.max(...data.map(d => d.count), 1);
    const points = data.map((item, index) => {
      const x = (index / (data.length - 1 || 1)) * 100;
      const y = 100 - (item.count / maxValue) * 100;
      return `${x},${y}`;
    }).join(' ');

    return (
      <div className="relative w-full min-w-0 overflow-hidden" style={{ height: `${height}px` }}>
        <svg width="100%" height="100%" viewBox="0 0 100 100" preserveAspectRatio="none" className="overflow-visible">
          <polyline
            points={points}
            fill="none"
            stroke={color}
            strokeWidth="0.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          {data.map((item, index) => {
            const x = (index / (data.length - 1 || 1)) * 100;
            const y = 100 - (item.count / maxValue) * 100;
            return (
              <circle
                key={index}
                cx={x}
                cy={y}
                r="1"
                fill={color}
              />
            );
          })}
        </svg>
        <div className="absolute bottom-0 left-0 right-0 flex justify-between gap-0.5 text-[10px] sm:text-xs text-muted-foreground overflow-hidden">
          {data.map((item, index) => (
            <span key={index} className="truncate flex-1 min-w-0 text-center" title={new Date(item.date || item.month).toLocaleDateString()}>
              {new Date(item.date || item.month).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
            </span>
          ))}
        </div>
      </div>
    );
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center py-8 sm:py-12 min-h-[200px]">
        <Loader2 className="h-6 w-6 sm:h-8 sm:w-8 animate-spin" />
      </div>
    );
  }

  if (!analytics) {
    return (
      <Card className="overflow-hidden">
        <CardContent className="py-8 sm:py-12 px-4 text-center">
          <p className="text-muted-foreground text-sm sm:text-base">No analytics data available</p>
        </CardContent>
      </Card>
    );
  }

  const { overview, cv_statistics, interview_statistics } = analytics;

  const chartColors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'];

  const selectedJob = selectedJobId ? jobs.find(j => j.id === parseInt(selectedJobId)) : null;

  return (
    <div className="space-y-4 sm:space-y-6 w-full max-w-full overflow-x-hidden">
      {/* Job Filter: All Jobs = analytics for all; specific job = analytics for that job only */}
      <Card className="overflow-hidden">
        <CardContent className="pt-4 sm:pt-6 px-4 sm:px-6">
          <div className="flex flex-col sm:flex-row sm:flex-wrap items-stretch sm:items-center gap-3 sm:gap-4">
            <label className="text-sm font-medium shrink-0">Filter by Job:</label>
            <Select value={selectedJobId ? String(selectedJobId) : 'all'} onValueChange={(value) => setSelectedJobId(value === 'all' ? null : value)}>
              <SelectTrigger className="w-full sm:w-[280px] md:w-[300px] min-w-0">
                <SelectValue placeholder="Select a job" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Jobs</SelectItem>
                {jobs.map((job) => (
                  <SelectItem key={job.id} value={job.id.toString()}>
                    {job.title}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {selectedJob ? (
              <Badge variant="secondary" className="w-fit truncate max-w-full">
                <span className="truncate">Showing: {selectedJob.title}</span>
              </Badge>
            ) : (
              <span className="text-sm text-muted-foreground">Showing analytics for all jobs</span>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Overview Cards - subtle color accents (marketing style) */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        <Card className="border-l-4 border-l-blue-500 bg-blue-500/5 dark:bg-blue-500/10 min-w-0 overflow-hidden">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 p-4 sm:p-6 pb-2">
            <CardTitle className="text-xs sm:text-sm font-medium truncate">Total CVs Processed</CardTitle>
            <Users className="h-4 w-4 text-blue-500" />
          </CardHeader>
          <CardContent className="px-4 sm:px-6 pt-0">
            <div className="text-xl sm:text-2xl font-bold">{overview.total_cvs}</div>
            <p className="text-[10px] sm:text-xs text-muted-foreground">Candidates analyzed</p>
          </CardContent>
        </Card>

        <Card className="border-l-4 border-l-emerald-500 bg-emerald-500/5 dark:bg-emerald-500/10 min-w-0 overflow-hidden">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 p-4 sm:p-6 pb-2">
            <CardTitle className="text-xs sm:text-sm font-medium truncate">Total Interviews</CardTitle>
            <Calendar className="h-4 w-4 text-emerald-500" />
          </CardHeader>
          <CardContent className="px-4 sm:px-6 pt-0">
            <div className="text-xl sm:text-2xl font-bold">{overview.total_interviews}</div>
            <p className="text-[10px] sm:text-xs text-muted-foreground">Scheduled interviews</p>
          </CardContent>
        </Card>

        <Card className="border-l-4 border-l-amber-500 bg-amber-500/5 dark:bg-amber-500/10 min-w-0 overflow-hidden">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 p-4 sm:p-6 pb-2">
            <CardTitle className="text-xs sm:text-sm font-medium truncate">Conversion Rate</CardTitle>
            <Target className="h-4 w-4 text-amber-500" />
          </CardHeader>
          <CardContent className="px-4 sm:px-6 pt-0">
            <div className="text-xl sm:text-2xl font-bold">{overview.conversion_rate}%</div>
            <p className="text-[10px] sm:text-xs text-muted-foreground">CV to Interview</p>
          </CardContent>
        </Card>

        <Card className="border-l-4 border-l-violet-500 bg-violet-500/5 dark:bg-violet-500/10 min-w-0 overflow-hidden">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 p-4 sm:p-6 pb-2">
            <CardTitle className="text-xs sm:text-sm font-medium truncate">Avg Role Fit Score</CardTitle>
            <TrendingUp className="h-4 w-4 text-violet-500" />
          </CardHeader>
          <CardContent className="px-4 sm:px-6 pt-0">
            <div className="text-xl sm:text-2xl font-bold">{overview.avg_role_fit_score}%</div>
            <p className="text-[10px] sm:text-xs text-muted-foreground">Average match score</p>
          </CardContent>
        </Card>
      </div>

      {/* CV Statistics */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">
        <Card className="min-w-0 overflow-hidden">
          <CardHeader className="px-4 sm:px-6 pb-2">
            <CardTitle className="flex items-center gap-2 text-base sm:text-lg">
              <PieChart className="h-4 w-4 sm:h-5 sm:w-5 shrink-0" />
              <span className="truncate">CVs by Decision</span>
            </CardTitle>
            <CardDescription className="text-xs sm:text-sm">Distribution of candidate decisions</CardDescription>
          </CardHeader>
          <CardContent className="px-4 sm:px-6 pt-0 overflow-x-auto">
            <SimplePieChart
              data={cv_statistics.by_decision}
              colors={['#10b981', '#f59e0b', '#ef4444', '#6b7280']}
            />
          </CardContent>
        </Card>

        <Card className="min-w-0 overflow-hidden">
          <CardHeader className="px-4 sm:px-6 pb-2">
            <CardTitle className="flex items-center gap-2 text-base sm:text-lg">
              <BarChart3 className="h-4 w-4 sm:h-5 sm:w-5 shrink-0" />
              <span className="truncate">CVs Over Time</span>
            </CardTitle>
            <CardDescription className="text-xs sm:text-sm">Daily CV processing trend</CardDescription>
          </CardHeader>
          <CardContent className="px-4 sm:px-6 pt-0 min-w-0">
            <SimpleLineChart
              data={cv_statistics.over_time}
              color={chartColors[0]}
              height={180}
            />
          </CardContent>
        </Card>
      </div>

      {/* Interview Statistics */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">
        <Card className="min-w-0 overflow-hidden">
          <CardHeader className="px-4 sm:px-6 pb-2">
            <CardTitle className="flex items-center gap-2 text-base sm:text-lg">
              <Activity className="h-4 w-4 sm:h-5 sm:w-5 shrink-0" />
              <span className="truncate">Interviews by Status</span>
            </CardTitle>
            <CardDescription className="text-xs sm:text-sm">Current interview status distribution</CardDescription>
          </CardHeader>
          <CardContent className="px-4 sm:px-6 pt-0 min-w-0">
            <SimpleBarChart
              data={interview_statistics.by_status}
              colors={['#f59e0b', '#10b981', '#3b82f6', '#ef4444', '#8b5cf6']}
              height={180}
            />
          </CardContent>
        </Card>

        <Card className="min-w-0 overflow-hidden">
          <CardHeader className="px-4 sm:px-6 pb-2">
            <CardTitle className="flex items-center gap-2 text-base sm:text-lg">
              <BarChart3 className="h-4 w-4 sm:h-5 sm:w-5 shrink-0" />
              <span className="truncate">Interviews Over Time</span>
            </CardTitle>
            <CardDescription className="text-xs sm:text-sm">Daily interview scheduling trend</CardDescription>
          </CardHeader>
          <CardContent className="px-4 sm:px-6 pt-0 min-w-0">
            <SimpleLineChart
              data={interview_statistics.over_time}
              color={chartColors[1]}
              height={180}
            />
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default RecruitmentAnalytics;
