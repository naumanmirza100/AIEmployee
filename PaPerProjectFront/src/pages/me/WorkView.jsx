import React from 'react';

import MyWorkList from '@/components/common/MyWorkList';

/** /me/work — "My work" inside My Space: everything waiting for the signed-in
 *  person, soonest first. Dashboard logins have it at /my-work too. */
export default function WorkView() {
  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <div>
        <h2 className="text-2xl font-bold text-foreground">My work</h2>
        <p className="mt-1 text-sm text-muted-foreground">Everything waiting for you, soonest first.</p>
      </div>
      <MyWorkList />
    </div>
  );
}
