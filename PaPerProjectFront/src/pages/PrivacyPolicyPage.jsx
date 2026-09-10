import React from 'react';
import LegalPage, { LegalList, ScopeCallout } from '@/components/legal/LegalPage';

const sections = [
  {
    id: 'information-we-collect',
    title: 'Information we collect',
    body: (
      <>
        <p>We collect what you and your team give us to run the platform:</p>
        <LegalList
          items={[
            'Account and company details — name, work email, and business information you enter when you sign up.',
            'Content you upload — job descriptions, candidate CVs, leads, and documents your agents work on.',
            'Usage data — which features you use, so we can keep the service running and improve it.',
          ]}
        />
      </>
    ),
  },
  {
    id: 'google-account-access',
    title: 'Google account access',
    body: (
      <>
        <p>
          Connecting a Google account is optional. If you connect one, we ask for a single
          permission:
        </p>
        <ScopeCallout>
          <p className="font-medium text-foreground">Google Calendar</p>
          <p className="mt-1 break-all font-mono text-sm text-primary">
            https://www.googleapis.com/auth/calendar
          </p>
          <p className="mt-4">
            We use it only to create calendar events and Google Meet links on your behalf — for
            interviews your Recruitment agent schedules, and meetings your Sales agent schedules.
          </p>
          <p className="mt-3">
            <strong>We never read, change, or delete your existing events.</strong> We only add
            events that you or your agents start from inside the platform.
          </p>
        </ScopeCallout>
        <p>
          Data we receive from Google is used for that scheduling feature and nothing else. We do
          not sell it, share it for advertising, or use it to train models.
        </p>
        <p>
          Our use and transfer of information received from Google APIs follows the{' '}
          <a
            href="https://developers.google.com/terms/api-services-user-data-policy"
            target="_blank"
            rel="noopener noreferrer"
          >
            Google API Services User Data Policy
          </a>
          , including the Limited Use requirements.
        </p>
      </>
    ),
  },
  {
    id: 'how-we-use-information',
    title: 'How we use information',
    body: (
      <LegalList
        items={[
          'Run the features you have turned on.',
          'Schedule meetings and interviews when you ask an agent to.',
          'Reply to your support requests and send account notices.',
          'Keep the service secure and reliable.',
        ]}
      />
    ),
  },
  {
    id: 'data-sharing',
    title: 'Data sharing',
    body: (
      <p>
        We do not sell your personal information. We share it with service providers — cloud
        hosting, email delivery, payment processing — only where they need it to run the platform
        on our behalf.
      </p>
    ),
  },
  {
    id: 'data-retention',
    title: 'Data retention',
    body: (
      <p>
        We keep your account and integration data while your account is active. Disconnecting
        Google Calendar from Company Profile revokes our access immediately and stops any further
        use of that connection.
      </p>
    ),
  },
  {
    id: 'security',
    title: 'Security',
    body: (
      <p>
        Credentials and tokens are stored encrypted, and access to production data is restricted to
        the people who need it to operate the service.
      </p>
    ),
  },
  {
    id: 'your-choices',
    title: 'Your choices',
    body: (
      <p>
        You can disconnect any integration, including Google Calendar, from your account settings at
        any time. To request deletion of your account data, email us and we will confirm once it is
        done.
      </p>
    ),
  },
  {
    id: 'contact-us',
    title: 'Contact us',
    body: (
      <p>
        Questions about this policy go to{' '}
        <a href="mailto:payperproject.laskon@gmail.com">payperproject.laskon@gmail.com</a>.
      </p>
    ),
  },
];

const PrivacyPolicyPage = () => (
  <LegalPage
    title="Privacy Policy"
    description="What PayPerProject collects, how we use it, and exactly what our Google Calendar integration can and cannot do."
    updated="8 September 2026"
    intro="PayPerProject runs AI agents for recruitment, sales, marketing, HR, and operations work. This page covers what we collect from the companies using it, and what our Google Calendar integration is allowed to touch."
    sections={sections}
  />
);

export default PrivacyPolicyPage;
