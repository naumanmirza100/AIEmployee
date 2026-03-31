import React from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { FileText } from 'lucide-react';

const SummarizationInsights = () => {
  return (
    <Card className="bg-[#1a1333]/60 border-[#2d2342]">
      <CardHeader>
        <div className="flex items-center gap-3 mb-2">
          <div className="flex items-center justify-center w-11 h-11 rounded-xl" style={{ backgroundColor: '#8b5cf615' }}>
            <FileText className="h-5 w-5" style={{ color: '#8b5cf6' }} />
          </div>
          <div>
            <CardTitle className="text-white text-lg">Summarization & Insights</CardTitle>
            <CardDescription className="text-gray-400">Generate executive summaries, extract key findings, compare documents.</CardDescription>
          </div>
          <Badge variant="outline" className="text-xs ml-auto" style={{ borderColor: '#8b5cf640', color: '#8b5cf6' }}>Coming Soon</Badge>
        </div>
      </CardHeader>
      <CardContent>
        <p className="text-gray-500 text-sm">This module will allow you to generate AI-powered summaries of your uploaded documents, extract action items and key findings, and compare multiple documents side by side.</p>
      </CardContent>
    </Card>
  );
};

export default SummarizationInsights;
