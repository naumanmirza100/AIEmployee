import React from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Bell } from 'lucide-react';

const ProactiveNotifications = () => {
  return (
    <Card className="bg-[#1a1333]/60 border-[#2d2342]">
      <CardHeader>
        <div className="flex items-center gap-3 mb-2">
          <div className="flex items-center justify-center w-11 h-11 rounded-xl" style={{ backgroundColor: '#ef444415' }}>
            <Bell className="h-5 w-5" style={{ color: '#ef4444' }} />
          </div>
          <div>
            <CardTitle className="text-white text-lg">Proactive Notifications</CardTitle>
            <CardDescription className="text-gray-400">Alerts on anomalies, threshold breaches, and activity digests.</CardDescription>
          </div>
          <Badge variant="outline" className="text-xs ml-auto" style={{ borderColor: '#ef444440', color: '#ef4444' }}>Coming Soon</Badge>
        </div>
      </CardHeader>
      <CardContent>
        <p className="text-gray-500 text-sm">Get automatically notified when metrics change unexpectedly, thresholds are breached, or new documents need your attention. Daily and weekly digest summaries included.</p>
      </CardContent>
    </Card>
  );
};

export default ProactiveNotifications;
