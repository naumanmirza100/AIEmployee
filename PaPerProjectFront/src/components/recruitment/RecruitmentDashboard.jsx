import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/components/ui/use-toast';
import { Loader2, FileText, Briefcase, Calendar, Settings, Users, Upload } from 'lucide-react';
import { 
  getJobDescriptions, 
  getInterviews, 
  getCVRecords,
  getEmailSettings,
  getInterviewSettings 
} from '@/services/recruitmentAgentService';
import CVProcessing from './CVProcessing';
import JobDescriptions from './JobDescriptions';
import Interviews from './Interviews';
import CVRecords from './CVRecords';
import RecruiterSettings from './RecruiterSettings';

const RecruitmentDashboard = () => {
  const { toast } = useToast();
  const [activeTab, setActiveTab] = useState('dashboard');
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState({
    totalCVs: 0,
    totalInterviews: 0,
    activeJobs: 0,
    pendingInterviews: 0,
  });

  useEffect(() => {
    fetchStats();
  }, []);

  const fetchStats = async () => {
    try {
      setLoading(true);
      
      const [jobsRes, interviewsRes, cvRecordsRes] = await Promise.all([
        getJobDescriptions().catch(() => ({ status: 'success', data: [] })),
        getInterviews().catch(() => ({ status: 'success', data: [] })),
        getCVRecords().catch(() => ({ status: 'success', data: [] })),
      ]);

      const jobs = jobsRes.data || [];
      const interviews = interviewsRes.data || [];
      const cvRecords = cvRecordsRes.data || [];

      setStats({
        totalCVs: cvRecords.length,
        totalInterviews: interviews.length,
        activeJobs: jobs.filter(j => j.is_active).length,
        pendingInterviews: interviews.filter(i => i.status === 'PENDING').length,
      });
    } catch (error) {
      console.error('Error fetching stats:', error);
      toast({
        title: 'Error',
        description: 'Failed to load recruitment statistics',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6 w-full max-w-full overflow-x-hidden">
      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8 w-full">
        <Card className="w-full min-w-0">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total CVs Processed</CardTitle>
            <FileText className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.totalCVs}</div>
            <p className="text-xs text-muted-foreground">Candidates analyzed</p>
          </CardContent>
        </Card>

        <Card className="w-full min-w-0">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Active Jobs</CardTitle>
            <Briefcase className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.activeJobs}</div>
            <p className="text-xs text-muted-foreground">Job descriptions</p>
          </CardContent>
        </Card>

        <Card className="w-full min-w-0">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Interviews</CardTitle>
            <Calendar className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.totalInterviews}</div>
            <p className="text-xs text-muted-foreground">Scheduled interviews</p>
          </CardContent>
        </Card>

        <Card className="w-full min-w-0">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Pending Interviews</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.pendingInterviews}</div>
            <p className="text-xs text-muted-foreground">Awaiting confirmation</p>
          </CardContent>
        </Card>
      </div>

      {/* Main Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="grid w-full grid-cols-6">
          <TabsTrigger value="dashboard">Dashboard</TabsTrigger>
          <TabsTrigger value="cv-processing">
            <Upload className="h-4 w-4 mr-2" />
            CV Processing
          </TabsTrigger>
          <TabsTrigger value="jobs">
            <Briefcase className="h-4 w-4 mr-2" />
            Job Descriptions
          </TabsTrigger>
          <TabsTrigger value="candidates">
            <Users className="h-4 w-4 mr-2" />
            Candidates
          </TabsTrigger>
          <TabsTrigger value="interviews">
            <Calendar className="h-4 w-4 mr-2" />
            Interviews
          </TabsTrigger>
          <TabsTrigger value="settings">
            <Settings className="h-4 w-4 mr-2" />
            Settings
          </TabsTrigger>
        </TabsList>

        <TabsContent value="dashboard" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Quick Actions</CardTitle>
              <CardDescription>Get started with recruitment tasks</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 w-full max-w-full">
                <Button
                  variant="outline"
                  className="h-auto flex-col items-start p-4"
                  onClick={() => setActiveTab('cv-processing')}
                >
                  <Upload className="h-6 w-6 mb-2" />
                  <span className="font-semibold">Process CVs</span>
                  <span className="text-xs text-muted-foreground mt-1">
                    Upload and analyze candidate resumes
                  </span>
                </Button>

                <Button
                  variant="outline"
                  className="h-auto flex-col items-start p-4"
                  onClick={() => setActiveTab('jobs')}
                >
                  <Briefcase className="h-6 w-6 mb-2" />
                  <span className="font-semibold">Manage Jobs</span>
                  <span className="text-xs text-muted-foreground mt-1">
                    Create and manage job descriptions
                  </span>
                </Button>

                <Button
                  variant="outline"
                  className="h-auto flex-col items-start p-4"
                  onClick={() => setActiveTab('interviews')}
                >
                  <Calendar className="h-6 w-6 mb-2" />
                  <span className="font-semibold">Schedule Interview</span>
                  <span className="text-xs text-muted-foreground mt-1">
                    Schedule interviews with candidates
                  </span>
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="cv-processing">
          <CVProcessing onProcessComplete={fetchStats} />
        </TabsContent>

        <TabsContent value="jobs">
          <JobDescriptions onUpdate={fetchStats} />
        </TabsContent>

        <TabsContent value="candidates">
          <CVRecords />
        </TabsContent>

        <TabsContent value="interviews">
          <Interviews onUpdate={fetchStats} />
        </TabsContent>

        <TabsContent value="settings">
          <RecruiterSettings />
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default RecruitmentDashboard;


