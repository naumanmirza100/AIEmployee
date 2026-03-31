import React from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { BarChart3 } from 'lucide-react';

const AnalyticsDashboardTab = () => {
  return (
    <Card className="bg-[#1a1333]/60 border-[#2d2342]">
      <CardHeader>
        <div className="flex items-center gap-3 mb-2">
          <div className="flex items-center justify-center w-11 h-11 rounded-xl" style={{ backgroundColor: '#10b98115' }}>
            <BarChart3 className="h-5 w-5" style={{ color: '#10b981' }} />
          </div>
          <div>
            <CardTitle className="text-white text-lg">Analytics & Dashboard</CardTitle>
            <CardDescription className="text-gray-400">Aggregate metrics from documents, detect trends and anomalies, build visual dashboards.</CardDescription>
          </div>
          <Badge variant="outline" className="text-xs ml-auto" style={{ borderColor: '#10b98140', color: '#10b981' }}>Coming Soon</Badge>
        </div>
      </CardHeader>
      <CardContent>
        <p className="text-gray-500 text-sm">This module will let you create custom dashboards from your document data, track KPIs over time, and automatically detect anomalies in your metrics.</p>
      </CardContent>
    </Card>
  );
};

export default AnalyticsDashboardTab;
