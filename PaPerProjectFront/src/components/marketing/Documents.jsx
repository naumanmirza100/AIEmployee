import React from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';

const Documents = () => {
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Marketing Documents</CardTitle>
          <CardDescription>
            View and manage your marketing documents
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">Document management coming soon...</p>
        </CardContent>
      </Card>
    </div>
  );
};

export default Documents;

