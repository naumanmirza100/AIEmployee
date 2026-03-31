import React from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { PenTool } from 'lucide-react';

const DocumentAuthoring = () => {
  return (
    <Card className="bg-[#1a1333]/60 border-[#2d2342]">
      <CardHeader>
        <div className="flex items-center gap-3 mb-2">
          <div className="flex items-center justify-center w-11 h-11 rounded-xl" style={{ backgroundColor: '#ec489915' }}>
            <PenTool className="h-5 w-5" style={{ color: '#ec4899' }} />
          </div>
          <div>
            <CardTitle className="text-white text-lg">Document Authoring</CardTitle>
            <CardDescription className="text-gray-400">Generate reports, memos, proposals using your documents as reference.</CardDescription>
          </div>
          <Badge variant="outline" className="text-xs ml-auto" style={{ borderColor: '#ec489940', color: '#ec4899' }}>Coming Soon</Badge>
        </div>
      </CardHeader>
      <CardContent>
        <p className="text-gray-500 text-sm">Create professional documents powered by AI. Use your uploaded documents as context to generate accurate, well-structured reports, memos, and proposals.</p>
      </CardContent>
    </Card>
  );
};

export default DocumentAuthoring;
