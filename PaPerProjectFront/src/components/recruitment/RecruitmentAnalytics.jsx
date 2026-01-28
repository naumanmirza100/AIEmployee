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

  // Simple Bar Chart Component
  const SimpleBarChart = ({ data, colors, height = 200 }) => {
    const maxValue = Math.max(...Object.values(data), 1);
    
    return (
      <div className="space-y-2" style={{ height: `${height}px` }}>
        {Object.entries(data).map(([key, value], index) => {
          const percentage = calculatePercentage(value, maxValue);
          return (
            <div key={key} className="flex items-center gap-3">
              <div className="w-24 text-sm text-muted-foreground truncate">
                {key}
              </div>
              <div className="flex-1 relative">
                <div className="h-8 bg-muted rounded-md overflow-hidden">
                  <div
                    className="h-full flex items-center justify-end pr-2 text-xs font-semibold text-white transition-all duration-500"
                    style={{
                      width: `${percentage}%`,
                      backgroundColor: colors[index % colors.length],
                    }}
                  >
                    {value > 0 && value}
                  </div>
                </div>
              </div>
              <div className="w-12 text-sm font-medium text-right">
                {value}
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  // Simple Pie Chart Component (using CSS)
  const SimplePieChart = ({ data, colors, size = 200 }) => {
    const total = Object.values(data).reduce((sum, val) => sum + val, 0);
    if (total === 0) {
      return (
        <div className="flex items-center justify-center" style={{ width: size, height: size }}>
          <p className="text-muted-foreground">No data</p>
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
      <div className="flex flex-col items-center gap-4">
        <div className="relative" style={{ width: size, height: size }}>
          <svg width={size} height={size} viewBox="0 0 200 200" className="transform -rotate-90">
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
              <div className="text-2xl font-bold">{total}</div>
              <div className="text-xs text-muted-foreground">Total</div>
            </div>
          </div>
        </div>
        <div className="space-y-2 w-full">
          {segments.map((segment, index) => (
            <div key={index} className="flex items-center justify-between text-sm">
              <div className="flex items-center gap-2">
                <div
                  className="w-4 h-4 rounded"
                  style={{ backgroundColor: segment.color }}
                />
                <span>{segment.key}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="font-medium">{segment.value}</span>
                <span className="text-muted-foreground">({segment.percentage}%)</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  };

  // Line Chart Component
  const SimpleLineChart = ({ data, color = '#3b82f6', height = 200 }) => {
    if (!data || data.length === 0) {
      return (
        <div className="flex items-center justify-center h-48 text-muted-foreground">
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
      <div className="relative" style={{ height: `${height}px` }}>
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
        <div className="absolute bottom-0 left-0 right-0 flex justify-between text-xs text-muted-foreground">
          {data.map((item, index) => (
            <span key={index} className="truncate" style={{ flex: 1 }}>
              {new Date(item.date || item.month).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
            </span>
          ))}
        </div>
      </div>
    );
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center py-12">
        <Loader2 className="h-8 w-8 animate-spin" />
      </div>
    );
  }

  if (!analytics) {
    return (
      <Card>
        <CardContent className="py-12 text-center">
          <p className="text-muted-foreground">No analytics data available</p>
        </CardContent>
      </Card>
    );
  }

  const { overview, cv_statistics, interview_statistics } = analytics;

  const chartColors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'];

  const selectedJob = selectedJobId ? jobs.find(j => j.id === parseInt(selectedJobId)) : null;

  return (
    <div className="space-y-6">
      {/* Job Filter Dropdown */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center gap-4">
            <label className="text-sm font-medium">Filter by Job:</label>
            <Select value={selectedJobId || 'all'} onValueChange={(value) => setSelectedJobId(value === 'all' ? null : value)}>
              <SelectTrigger className="w-[300px]">
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
            {selectedJob && (
              <Badge variant="secondary" className="ml-2">
                {selectedJob.title}
              </Badge>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Overview Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total CVs Processed</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{overview.total_cvs}</div>
            <p className="text-xs text-muted-foreground">Candidates analyzed</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Interviews</CardTitle>
            <Calendar className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{overview.total_interviews}</div>
            <p className="text-xs text-muted-foreground">Scheduled interviews</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Conversion Rate</CardTitle>
            <Target className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{overview.conversion_rate}%</div>
            <p className="text-xs text-muted-foreground">CV to Interview</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Avg Role Fit Score</CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{overview.avg_role_fit_score}%</div>
            <p className="text-xs text-muted-foreground">Average match score</p>
          </CardContent>
        </Card>
      </div>

      {/* CV Statistics */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <PieChart className="h-5 w-5" />
              CVs by Decision
            </CardTitle>
            <CardDescription>Distribution of candidate decisions</CardDescription>
          </CardHeader>
          <CardContent>
            <SimplePieChart
              data={cv_statistics.by_decision}
              colors={['#10b981', '#f59e0b', '#ef4444', '#6b7280']}
              size={200}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <BarChart3 className="h-5 w-5" />
              CVs Over Time
            </CardTitle>
            <CardDescription>Daily CV processing trend</CardDescription>
          </CardHeader>
          <CardContent>
            <SimpleLineChart
              data={cv_statistics.over_time}
              color={chartColors[0]}
              height={200}
            />
          </CardContent>
        </Card>
      </div>

      {/* Interview Statistics */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-5 w-5" />
              Interviews by Status
            </CardTitle>
            <CardDescription>Current interview status distribution</CardDescription>
          </CardHeader>
          <CardContent>
            <SimpleBarChart
              data={interview_statistics.by_status}
              colors={['#f59e0b', '#10b981', '#3b82f6', '#ef4444', '#8b5cf6']}
              height={200}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <BarChart3 className="h-5 w-5" />
              Interviews Over Time
            </CardTitle>
            <CardDescription>Daily interview scheduling trend</CardDescription>
          </CardHeader>
          <CardContent>
            <SimpleLineChart
              data={interview_statistics.over_time}
              color={chartColors[1]}
              height={200}
            />
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default RecruitmentAnalytics;
