import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/components/ui/use-toast';
import { Loader2, FileText, Calendar, TrendingUp } from 'lucide-react';
import { getCVRecords, getJobDescriptions } from '@/services/recruitmentAgentService';
import QualificationReasoning from './QualificationReasoning';

const CVRecords = () => {
  const { toast } = useToast();
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [jobFilter, setJobFilter] = useState('');
  const [decisionFilter, setDecisionFilter] = useState('');
  const [jobs, setJobs] = useState([]);

  useEffect(() => {
    fetchJobs();
  }, []);

  useEffect(() => {
    fetchRecords();
  }, [jobFilter, decisionFilter]);

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

  const fetchRecords = async () => {
    try {
      setLoading(true);
      const filters = {};
      if (jobFilter) filters.job_id = jobFilter;
      if (decisionFilter) filters.decision = decisionFilter;

      const response = await getCVRecords(filters);
      if (response.status === 'success') {
        setRecords(response.data || []);
      }
    } catch (error) {
      console.error('Error fetching CV records:', error);
      toast({
        title: 'Error',
        description: 'Failed to load CV records',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  const getDecisionBadge = (decision) => {
    switch (decision) {
      case 'INTERVIEW':
        return <Badge className="bg-green-500">INTERVIEW</Badge>;
      case 'HOLD':
        return <Badge className="bg-yellow-500">HOLD</Badge>;
      case 'REJECT':
        return <Badge className="bg-red-500">REJECT</Badge>;
      default:
        return <Badge variant="outline">{decision || 'N/A'}</Badge>;
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-bold">CV Records / Candidates</h2>
          <p className="text-sm text-muted-foreground">
            View and manage processed candidate CVs
          </p>
        </div>
        <div className="flex gap-2">
          <Select value={jobFilter || "all"} onValueChange={(value) => setJobFilter(value === "all" ? "" : value)}>
            <SelectTrigger className="w-[200px]">
              <SelectValue placeholder="Filter by job" />
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
          <Select value={decisionFilter || "all"} onValueChange={(value) => setDecisionFilter(value === "all" ? "" : value)}>
            <SelectTrigger className="w-[180px]">
              <SelectValue placeholder="Filter by decision" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Decisions</SelectItem>
              <SelectItem value="INTERVIEW">Interview</SelectItem>
              <SelectItem value="HOLD">Hold</SelectItem>
              <SelectItem value="REJECT">Reject</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {records.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <FileText className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
            <p className="text-lg font-medium mb-2">No CV records yet</p>
            <p className="text-sm text-muted-foreground">
              Process CVs to see candidate records here
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {records.map((record) => {
            const parsed = record.parsed || {};
            const qualified = record.qualified || {};
            const summary = record.summary || {};

            return (
              <Card key={record.id} className="border-l-4 border-l-primary">
                <CardHeader>
                  <div className="flex justify-between items-start">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-2">
                        {record.rank && (
                          <Badge variant="outline" className="font-bold">
                            Rank #{record.rank}
                          </Badge>
                        )}
                        {getDecisionBadge(record.qualification_decision)}
                        {record.qualification_priority && (
                          <Badge variant="secondary">{record.qualification_priority}</Badge>
                        )}
                      </div>
                      <CardTitle className="text-lg">
                        {parsed.name || record.file_name}
                      </CardTitle>
                      <CardDescription className="mt-1">
                        {record.job_description_title && (
                          <span>Job: {record.job_description_title} • </span>
                        )}
                        {parsed.email && <span>{parsed.email}</span>}
                      </CardDescription>
                    </div>
                    {record.role_fit_score !== null && (
                      <div className="text-right">
                        <div className="text-2xl font-bold text-primary">
                          {record.role_fit_score}%
                        </div>
                        <div className="text-xs text-muted-foreground">Fit Score</div>
                      </div>
                    )}
                  </div>
                </CardHeader>
                <CardContent className="space-y-3">
                  {summary.summary && (
                    <div>
                      <h4 className="font-semibold text-sm mb-1">Summary</h4>
                      <p className="text-sm text-muted-foreground">{summary.summary}</p>
                    </div>
                  )}
                  {qualified.reasoning && (
                    <QualificationReasoning 
                      reasoning={qualified.reasoning}
                      exactMatchedSkills={qualified.exact_matched_skills || []}
                      relatedMatchedSkills={qualified.related_matched_skills || []}
                      missingSkills={qualified.missing_skills || []}
                          inferredSkills={[]}
                    />
                  )}
                  {parsed.skills && parsed.skills.length > 0 && (
                    <div>
                      <h4 className="font-semibold text-sm mb-1">Skills</h4>
                      <div className="flex flex-wrap gap-1">
                        {parsed.skills.slice(0, 10).map((skill, idx) => (
                          <Badge key={idx} variant="outline" className="text-xs">
                            {skill}
                          </Badge>
                        ))}
                        {parsed.skills.length > 10 && (
                          <Badge variant="outline" className="text-xs">
                            +{parsed.skills.length - 10} more
                          </Badge>
                        )}
                      </div>
                    </div>
                  )}
                  {record.qualification_confidence !== null && (
                    <div className="text-sm">
                      <span className="font-medium">Confidence: </span>
                      {record.qualification_confidence}%
                    </div>
                  )}
                  {record.created_at && (
                    <div className="text-xs text-muted-foreground flex items-center gap-1">
                      <Calendar className="h-3 w-3" />
                      Processed: {new Date(record.created_at).toLocaleDateString()}
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default CVRecords;

