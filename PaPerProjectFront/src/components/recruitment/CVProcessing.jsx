import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/components/ui/use-toast';
import { Loader2, Upload, FileText, CheckCircle, XCircle, AlertCircle, User, Mail, Percent } from 'lucide-react';
import { processCVs, getJobDescriptions, getInterviewSettings } from '@/services/recruitmentAgentService';
import QualificationReasoning from './QualificationReasoning';

const CVProcessing = ({ onProcessComplete }) => {
  const { toast } = useToast();
  const [files, setFiles] = useState([]);
  const [jobDescriptions, setJobDescriptions] = useState([]);
  const [selectedJobId, setSelectedJobId] = useState('');
  const [jobDescriptionText, setJobDescriptionText] = useState('');
  const [jobKeywords, setJobKeywords] = useState('');
  const [topN, setTopN] = useState('');
  const [processing, setProcessing] = useState(false);
  const [results, setResults] = useState(null);
  const [displayedKeywords, setDisplayedKeywords] = useState([]);

  React.useEffect(() => {
    fetchJobDescriptions();
  }, []);

  const fetchJobDescriptions = async () => {
    try {
      const response = await getJobDescriptions();
      if (response.status === 'success') {
        setJobDescriptions(response.data || []);
      }
    } catch (error) {
      console.error('Error fetching job descriptions:', error);
    }
  };

  const handleJobSelection = async (jobId) => {
    // Check interview settings if a job is selected
    if (jobId) {
      try {
        const settingsResponse = await getInterviewSettings(jobId);
        if (settingsResponse.status === 'success' && settingsResponse.data) {
          const settings = settingsResponse.data;
          // Check if interview settings are complete
          const isComplete = 
            settings.schedule_from_date && 
            settings.schedule_to_date && 
            settings.start_time && 
            settings.end_time &&
            settings.time_slots_json &&
            Array.isArray(settings.time_slots_json) &&
            settings.time_slots_json.length > 0;
          
          if (!isComplete) {
            toast({
              title: 'Interview Settings Incomplete',
              description: `Please complete interview settings for "${jobDescriptions.find(j => j.id.toString() === jobId.toString())?.title || 'this job'}" before processing CVs. Go to Settings > Interview Settings to configure.`,
              variant: 'destructive',
            });
            // Don't set the job if settings are incomplete
            return;
          }
        }
      } catch (error) {
        console.error('Error checking interview settings:', error);
        // Continue with job selection even if check fails
      }
    }
    
    setSelectedJobId(jobId || "");
    
    // Extract and display keywords when a job is selected
    if (jobId) {
      const selectedJob = jobDescriptions.find(job => job.id.toString() === jobId.toString());
      if (selectedJob && selectedJob.keywords_json) {
        try {
          const keywordsData = JSON.parse(selectedJob.keywords_json);
          const keywords = keywordsData.keywords || [];
          setDisplayedKeywords(keywords);
        } catch (error) {
          console.error('Error parsing keywords:', error);
          setDisplayedKeywords([]);
        }
      } else {
        setDisplayedKeywords([]);
      }
    } else {
      setDisplayedKeywords([]);
    }
  };

  const handleFileChange = (e) => {
    const selectedFiles = Array.from(e.target.files);
    setFiles(selectedFiles);
  };

  const handleProcess = async () => {
    if (files.length === 0) {
      toast({
        title: 'No files selected',
        description: 'Please select at least one CV file to process',
        variant: 'destructive',
      });
      return;
    }

    if (!selectedJobId) {
      toast({
        title: 'Job required',
        description: 'Please select a job description before processing CVs.',
        variant: 'destructive',
      });
      return;
    }

    // Validate interview settings for the selected job
    if (selectedJobId) {
      try {
        const settingsResponse = await getInterviewSettings(selectedJobId);
        if (settingsResponse.status === 'success' && settingsResponse.data) {
          const settings = settingsResponse.data;
          // Check if interview settings are complete
          const isComplete = 
            settings.schedule_from_date && 
            settings.schedule_to_date && 
            settings.start_time && 
            settings.end_time &&
            settings.time_slots_json &&
            Array.isArray(settings.time_slots_json) &&
            settings.time_slots_json.length > 0;
          
          if (!isComplete) {
            const selectedJob = jobDescriptions.find(j => j.id.toString() === selectedJobId.toString());
            toast({
              title: 'Interview Settings Incomplete',
              description: `Please complete interview settings for "${selectedJob?.title || 'this job'}" before processing CVs. Go to Settings > Interview Settings to configure.`,
              variant: 'destructive',
            });
            return;
          }
        }
      } catch (error) {
        console.error('Error checking interview settings:', error);
        // Continue with processing even if check fails
      }
    }

    try {
      setProcessing(true);
      setResults(null);

      const response = await processCVs(
        files,
        selectedJobId,
        jobDescriptionText,
        jobKeywords,
        topN ? parseInt(topN) : null,
        false
      );

      if (response.status === 'success') {
        setResults(response);
        toast({
          title: 'Success',
          description: `Processed ${response.results?.length || 0} CV(s) successfully`,
        });
        if (onProcessComplete) {
          onProcessComplete();
        }
      } else {
        throw new Error(response.message || 'Processing failed');
      }
    } catch (error) {
      console.error('Error processing CVs:', error);
      toast({
        title: 'Error',
        description: error.message || 'Failed to process CVs',
        variant: 'destructive',
      });
    } finally {
      setProcessing(false);
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

  return (
    <div className="space-y-4 sm:space-y-6 w-full">
      {/* Upload Form Card */}
      <Card>
        <CardHeader className="p-4 sm:p-6">
          <CardTitle className="text-lg sm:text-xl">Process CV Files</CardTitle>
          <CardDescription className="text-xs sm:text-sm">
            Upload CV files to analyze and rank candidates based on job requirements
          </CardDescription>
        </CardHeader>
        <CardContent className="p-4 sm:p-6 pt-0 sm:pt-0 space-y-4">
          {/* File Upload */}
          <div className="space-y-2">
            <Label htmlFor="cv-files" className="text-sm font-medium">CV Files</Label>
            <div className="relative">
              <Input
                id="cv-files"
                type="file"
                multiple
                accept=".pdf,.doc,.docx"
                onChange={handleFileChange}
                className="text-sm file:mr-3 file:py-1.5 file:px-3 file:rounded-md file:border-0 file:text-xs file:font-medium file:bg-primary file:text-primary-foreground hover:file:bg-primary/90 cursor-pointer"
              />
            </div>
            {files.length > 0 && (
              <div className="flex items-center gap-2 text-xs sm:text-sm text-muted-foreground bg-muted/50 p-2 rounded-md">
                <FileText className="h-4 w-4 shrink-0" />
                <span>{files.length} file(s) selected</span>
              </div>
            )}
          </div>

          {/* Job Description Selection (Required) */}
          <div className="space-y-2">
            <Label htmlFor="job-description" className="text-sm font-medium">
              Select Job Description <span className="text-destructive">*</span>
            </Label>
            <Select value={selectedJobId || ""} onValueChange={handleJobSelection}>
              <SelectTrigger className="w-full text-sm">
                <SelectValue placeholder="Select a job (required)" />
              </SelectTrigger>
              <SelectContent>
                {jobDescriptions.map((job) => (
                  <SelectItem key={job.id} value={job.id.toString()}>
                    {job.title}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-[10px] sm:text-xs text-muted-foreground">
              Job selection is required to process CVs. Ensure interview settings are complete for the selected job.
            </p>
            
            {/* Display Keywords when job is selected */}
            {selectedJobId && selectedJobId !== "none" && displayedKeywords.length > 0 && (
              <div className="mt-3 p-2.5 sm:p-3 bg-muted/50 rounded-lg border">
                <div className="text-xs sm:text-sm font-semibold mb-2">Extracted Keywords:</div>
                <div className="flex flex-wrap gap-1.5 sm:gap-2">
                  {displayedKeywords.map((keyword, index) => (
                    <Badge key={index} variant="secondary" className="text-[10px] sm:text-xs">
                      {keyword}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Keywords (Optional) */}
          <div className="space-y-2">
            <Label htmlFor="keywords" className="text-sm font-medium">
              Keywords <span className="text-muted-foreground text-xs">(Optional)</span>
            </Label>
            <Input
              id="keywords"
              value={jobKeywords}
              onChange={(e) => setJobKeywords(e.target.value)}
              placeholder="Python, React, etc."
              className="text-sm"
            />
          </div>

          {/* Top N */}
          <div className="space-y-2">
            <Label htmlFor="top-n" className="text-sm font-medium">
              Top N Results <span className="text-muted-foreground text-xs">(Optional)</span>
            </Label>
            <Input
              id="top-n"
              type="number"
              value={topN}
              onChange={(e) => setTopN(e.target.value)}
              placeholder="All results"
              className="text-sm"
            />
          </div>

          <Button
            onClick={handleProcess}
            disabled={processing || files.length === 0 || !selectedJobId}
            className="w-full sm:w-auto sm:min-w-[200px] h-10 text-sm"
          >
            {processing ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                <span className="hidden sm:inline">Processing CVs...</span>
                <span className="sm:hidden">Processing...</span>
              </>
            ) : (
              <>
                <Upload className="h-4 w-4 mr-2" />
                Process CVs
              </>
            )}
          </Button>
        </CardContent>
      </Card>

      {/* Results */}
      {results && results.results && (
        <Card>
          <CardHeader className="p-4 sm:p-6">
            <CardTitle className="text-lg sm:text-xl">Processing Results</CardTitle>
            <CardDescription className="text-xs sm:text-sm">
              {results.results.length} candidate(s) analyzed and ranked
            </CardDescription>
          </CardHeader>
          <CardContent className="p-4 sm:p-6 pt-0 sm:pt-0">
            <div className="space-y-3 sm:space-y-4">
              {results.results.map((result, index) => {
                const qualified = result.qualified || {};
                const summary = result.summary || {};
                const parsed = result.parsed || {};

                return (
                  <Card key={index} className="border-l-4 border-l-primary overflow-hidden">
                    <CardHeader className="p-3 sm:p-4 pb-2 sm:pb-3">
                      <div className="flex flex-col sm:flex-row sm:justify-between sm:items-start gap-2">
                        <div className="min-w-0 flex-1">
                          <CardTitle className="text-sm sm:text-lg flex items-center gap-2 flex-wrap">
                            <Badge variant="outline" className="shrink-0 text-xs">#{index + 1}</Badge>
                            <span className="truncate">{result.file_name}</span>
                          </CardTitle>
                        </div>
                        <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
                          {getDecisionBadge(qualified.decision)}
                          {qualified.priority && (
                            <Badge variant="outline" className="text-[10px] sm:text-xs">{qualified.priority}</Badge>
                          )}
                        </div>
                      </div>
                    </CardHeader>
                    <CardContent className="p-3 sm:p-4 pt-0 sm:pt-0 space-y-3">
                      {/* Summary */}
                      {summary.summary && (
                        <div className="bg-muted/30 rounded-md p-2.5 sm:p-3">
                          <h4 className="font-semibold text-xs sm:text-sm mb-1">Summary</h4>
                          <p className="text-xs sm:text-sm text-muted-foreground leading-relaxed">{summary.summary}</p>
                        </div>
                      )}
                      
                      {/* Qualification Reasoning */}
                      {qualified.reasoning && (
                        <QualificationReasoning 
                          reasoning={qualified.reasoning}
                          exactMatchedSkills={qualified.exact_matched_skills || []}
                          relatedMatchedSkills={qualified.related_matched_skills || []}
                          missingSkills={qualified.missing_skills || []}
                          inferredSkills={[]}
                        />
                      )}
                      
                      {/* Candidate Info */}
                      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs sm:text-sm pt-2 border-t">
                        {parsed.name && (
                          <div className="flex items-center gap-1.5">
                            <User className="h-3 w-3 sm:h-4 sm:w-4 text-muted-foreground shrink-0" />
                            <span className="font-medium">{parsed.name}</span>
                          </div>
                        )}
                        {parsed.email && (
                          <div className="flex items-center gap-1.5 min-w-0">
                            <Mail className="h-3 w-3 sm:h-4 sm:w-4 text-muted-foreground shrink-0" />
                            <span className="text-muted-foreground truncate">{parsed.email}</span>
                          </div>
                        )}
                        {qualified.confidence_score !== undefined && (
                          <div className="flex items-center gap-1.5">
                            <Percent className="h-3 w-3 sm:h-4 sm:w-4 text-muted-foreground shrink-0" />
                            <span className="font-medium">{qualified.confidence_score}%</span>
                            <span className="text-muted-foreground hidden sm:inline">confidence</span>
                          </div>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default CVProcessing;

