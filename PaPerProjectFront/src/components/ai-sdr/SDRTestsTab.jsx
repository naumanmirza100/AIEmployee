import React, { useMemo } from 'react';
import { Code2 } from 'lucide-react';
import { getCompanyUser } from '@/services/companyAuthService';
import { sdrChecksApi } from '@/services/aiSdrService';
import SDRChecksPanel from './SDRChecksPanel';
import SDRLiveChecks from './SDRLiveChecks';

// The same roles the backend lets in (IsCompanyAdmin).
const ADMIN_ROLES = ['owner', 'admin'];

/**
 * AI SDR → Tests: health checks and live tests of this company's AI SDR, then the automated tests of the
 * platform's code (run on a throwaway database).
 */
const SDRTestsTab = () => {
  const companyUser = useMemo(() => getCompanyUser(), []);
  if (!ADMIN_ROLES.includes(companyUser?.role)) {
    return (
      <div className="rounded-xl border border-white/10 bg-white/[0.03] p-6 text-center text-sm text-gray-400">
        Only your company's owner or an admin can run the AI SDR tests.
      </div>
    );
  }
  return (
    <div className="space-y-8">
      <SDRLiveChecks />
      <section className="space-y-3">
        <div className="space-y-1">
          <h2 className="text-white font-semibold flex items-center gap-2"><Code2 className="w-5 h-5 text-violet-400" /> Automated tests</h2>
          <p className="text-sm text-gray-400 max-w-2xl">
            The platform's own tests of the AI SDR code, run on a throwaway database. They prove the logic is right;
            the checks above prove your live setup works.
          </p>
        </div>
        <SDRChecksPanel api={sdrChecksApi} />
      </section>
    </div>
  );
};

export default SDRTestsTab;
