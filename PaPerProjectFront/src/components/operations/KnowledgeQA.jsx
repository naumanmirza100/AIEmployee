import React from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { MessageSquareText } from 'lucide-react';

const KnowledgeQA = () => {
  return (
    <Card className="bg-[#1a1333]/60 border-[#2d2342]">
      <CardHeader>
        <div className="flex items-center gap-3 mb-2">
          <div className="flex items-center justify-center w-11 h-11 rounded-xl" style={{ backgroundColor: '#f59e0b15' }}>
            <MessageSquareText className="h-5 w-5" style={{ color: '#f59e0b' }} />
          </div>
          <div>
            <CardTitle className="text-white text-lg">Knowledge Q&A</CardTitle>
            <CardDescription className="text-gray-400">Ask questions about your documents and get answers with source citations.</CardDescription>
          </div>
          <Badge variant="outline" className="text-xs ml-auto" style={{ borderColor: '#f59e0b40', color: '#f59e0b' }}>Coming Soon</Badge>
        </div>
      </CardHeader>
      <CardContent>
        <p className="text-gray-500 text-sm">Chat with your documents using AI. Get accurate answers with references to the exact source document, page, and section.</p>
      </CardContent>
    </Card>
  );
};

export default KnowledgeQA;
