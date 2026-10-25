import React from 'react';
import { Link } from 'react-router-dom';
import { Building2, User } from 'lucide-react';
import { cn } from '@/lib/utils';

// The two ways in: a company's dashboard, or an employee's own space. Each sign-in page had at most a small
// text link to the other, so people changed the address by hand.
const WAYS_IN = [
  { key: 'company', to: '/company/login', label: 'Company', icon: Building2 },
  { key: 'employee', to: '/login', label: 'Employee', icon: User },
];

export default function LoginSwitch({ active }) {
  return (
    <div className="mb-4 grid grid-cols-2 gap-1 rounded-lg border bg-muted/40 p-1" role="tablist" aria-label="Sign in as">
      {WAYS_IN.map(({ key, to, label, icon: Icon }) => {
        const isActive = key === active;
        return (
          <Link
            key={key}
            to={to}
            role="tab"
            aria-selected={isActive}
            data-testid={`login-switch-${key}`}
            className={cn(
              'flex items-center justify-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors',
              isActive ? 'bg-primary text-primary-foreground shadow' : 'text-muted-foreground hover:bg-muted hover:text-foreground',
            )}
          >
            <Icon className="h-4 w-4" />
            {label} login
          </Link>
        );
      })}
    </div>
  );
}
