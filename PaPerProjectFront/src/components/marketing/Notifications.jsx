import React from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';

const Notifications = () => {
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Marketing Notifications</CardTitle>
          <CardDescription>
            View marketing-related notifications
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">Notifications coming soon...</p>
        </CardContent>
      </Card>
    </div>
  );
};

export default Notifications;

