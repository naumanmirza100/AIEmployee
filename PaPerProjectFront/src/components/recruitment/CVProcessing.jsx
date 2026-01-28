import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/components/ui/use-toast';
import { Loader2, Upload, FileText, CheckCircle, XCircle, AlertCircle } from 'lucide-react';
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
    if (jobId && jobId !== "none") {
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
    
    setSelectedJobId(jobId === "none" ? "" : jobId);
    
    // Extract and display keywords when a job is selected
    if (jobId && jobId !== "none") {
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

    // Validate interview settings if a job is selected
    if (selectedJobId && selectedJobId !== "none") {
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
        selectedJobId && selectedJobId !== "none" ? selectedJobId : null,
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
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Process CV Files</CardTitle>
          <CardDescription>
            Upload CV files to analyze and rank candidates based on job requirements
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* File Upload */}
          <div className="space-y-2">
            <Label htmlFor="cv-files">CV Files</Label>
            <Input
              id="cv-files"
              type="file"
              multiple
              accept=".pdf,.doc,.docx"
              onChange={handleFileChange}
            />
            {files.length > 0 && (
              <div className="text-sm text-muted-foreground">
                {files.length} file(s) selected
              </div>
            )}
          </div>

          {/* Job Description Selection */}
          <div className="space-y-2">
            <Label htmlFor="job-description">Select Job Description</Label>
            <Select value={selectedJobId || "none"} onValueChange={handleJobSelection}>
              <SelectTrigger>
                <SelectValue placeholder="Select a job description" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">None - Use text/keywords below</SelectItem>
                {jobDescriptions.map((job) => (
                  <SelectItem key={job.id} value={job.id.toString()}>
                    {job.title}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            
            {/* Display Keywords when job is selected */}
            {selectedJobId && selectedJobId !== "none" && displayedKeywords.length > 0 && (
              <div className="mt-3 p-3 bg-muted/50 rounded-lg border">
                <div className="text-sm font-semibold mb-2">Extracted Keywords:</div>
                <div className="flex flex-wrap gap-2">
                  {displayedKeywords.map((keyword, index) => (
                    <Badge key={index} variant="secondary" className="text-xs">
                      {keyword}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Job Description Text */}
          {!selectedJobId && (
            <div className="space-y-2">
              <Label htmlFor="job-text">Job Description Text (Optional)</Label>
              <Textarea
                id="job-text"
                value={jobDescriptionText}
                onChange={(e) => setJobDescriptionText(e.target.value)}
                placeholder="Paste job description here..."
                className="min-h-[100px]"
              />
            </div>
          )}

          {/* Keywords */}
          <div className="space-y-2">
            <Label htmlFor="keywords">Keywords (Optional, comma-separated)</Label>
            <Input
              id="keywords"
              value={jobKeywords}
              onChange={(e) => setJobKeywords(e.target.value)}
              placeholder="e.g., Python, React, 5 years experience"
            />
          </div>

          {/* Top N */}
          <div className="space-y-2">
            <Label htmlFor="top-n">Top N Results (Optional)</Label>
            <Input
              id="top-n"
              type="number"
              value={topN}
              onChange={(e) => setTopN(e.target.value)}
              placeholder="Leave empty for all results"
            />
          </div>

          <Button
            onClick={handleProcess}
            disabled={processing || files.length === 0}
            className="w-full"
          >
            {processing ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Processing...
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
          <CardHeader>
            <CardTitle>Processing Results</CardTitle>
            <CardDescription>
              {results.results.length} candidate(s) analyzed and ranked
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {results.results.map((result, index) => {
                const qualified = result.qualified || {};
                const summary = result.summary || {};
                const parsed = result.parsed || {};

                return (
                  <Card key={index} className="border-l-4 border-l-primary">
                    <CardHeader>
                      <div className="flex justify-between items-start">
                        <div>
                          <CardTitle className="text-lg">
                            #{index + 1} - {result.file_name}
                          </CardTitle>
                        </div>
                        <div className="flex items-center gap-2">
                          {getDecisionBadge(qualified.decision)}
                          {qualified.priority && (
                            <Badge variant="outline">{qualified.priority}</Badge>
                          )}
                        </div>
                      </div>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      {summary.summary && (
                        <div>
                          <h4 className="font-semibold mb-1">Summary</h4>
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
                      {parsed.name && (
                        <div className="text-sm">
                          <span className="font-medium">Name:</span> {parsed.name}
                        </div>
                      )}
                      {parsed.email && (
                        <div className="text-sm">
                          <span className="font-medium">Email:</span> {parsed.email}
                        </div>
                      )}
                      {qualified.confidence_score !== undefined && (
                        <div className="text-sm">
                          <span className="font-medium">Confidence Score:</span> {qualified.confidence_score}%
                        </div>
                      )}
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

