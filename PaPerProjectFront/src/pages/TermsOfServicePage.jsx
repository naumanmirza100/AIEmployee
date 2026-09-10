import React from 'react';
import LegalPage, { LegalList } from '@/components/legal/LegalPage';

const sections = [
  {
    id: 'accounts',
    title: 'Accounts',
    body: (
      <p>
        Give accurate details when you sign up and keep your login secure. You are responsible for
        what happens under your account, including the actions of people you invite into your
        company workspace.
      </p>
    ),
  },
  {
    id: 'using-the-service',
    title: 'Using the service',
    body: (
      <>
        <p>Use the platform for lawful business work. Do not:</p>
        <LegalList
          items={[
            'Upload content you do not have the right to use.',
            'Send outreach that breaks anti-spam or marketing law.',
            'Disrupt, reverse engineer, or try to gain unauthorised access to the service.',
            'Process personal data in ways that break privacy or employment law.',
          ]}
        />
      </>
    ),
  },
  {
    id: 'your-content',
    title: 'Your content',
    body: (
      <p>
        Job descriptions, candidate records, leads, and documents you upload stay yours. You give us
        a limited licence to process them so the features you turned on can run. You are responsible
        for having a lawful basis to upload personal data, including candidate data.
      </p>
    ),
  },
  {
    id: 'third-party-integrations',
    title: 'Third-party integrations',
    body: (
      <p>
        You can connect services such as Google Calendar, email providers, and CRMs. Those providers
        have their own terms, and your use of them is governed by those terms. Disconnect any
        integration from your account settings whenever you want.
      </p>
    ),
  },
  {
    id: 'ai-generated-output',
    title: 'AI-generated output',
    body: (
      <p>
        Our agents generate summaries, scores, drafts, and recommendations. This output can be
        wrong. Have a person review it before acting on it — particularly for hiring, contractual,
        or other consequential decisions. Those decisions remain yours.
      </p>
    ),
  },
  {
    id: 'fees-and-billing',
    title: 'Fees and billing',
    body: (
      <p>
        Paid modules and plans are billed through our payment processor at the rate shown when you
        buy. Charges are non-refundable except where the law requires otherwise. Cancel any time —
        access continues to the end of the billing period you have paid for.
      </p>
    ),
  },
  {
    id: 'availability',
    title: 'Availability',
    body: (
      <p>
        We work to keep the platform up, but we do not guarantee uninterrupted access. We may change
        or retire features, and we will give reasonable notice of material changes where we can.
      </p>
    ),
  },
  {
    id: 'termination',
    title: 'Termination',
    body: (
      <p>
        Close your account whenever you like. We may suspend or end access if these terms are broken
        or if we need to protect the service or its other users.
      </p>
    ),
  },
  {
    id: 'disclaimers-and-liability',
    title: 'Disclaimers and liability',
    body: (
      <p>
        The service is provided as is, without warranties, to the extent the law allows. To the
        maximum extent permitted by law we are not liable for indirect or consequential damages, or
        for lost profits, data, or business opportunity.
      </p>
    ),
  },
  {
    id: 'changes-to-these-terms',
    title: 'Changes to these terms',
    body: (
      <p>
        We update these terms from time to time. The date at the top of this page shows the last
        change, and we will tell you in the product when a change is material.
      </p>
    ),
  },
  {
    id: 'contact-us',
    title: 'Contact us',
    body: (
      <p>
        Questions about these terms go to{' '}
        <a href="mailto:payperproject.laskon@gmail.com">payperproject.laskon@gmail.com</a>.
      </p>
    ),
  },
];

const TermsOfServicePage = () => (
  <LegalPage
    title="Terms of Service"
    description="The terms covering your use of the PayPerProject platform and its AI automation agents."
    updated="8 September 2026"
    intro="These terms govern your use of PayPerProject. By creating an account or using the platform, you agree to them."
    sections={sections}
  />
);

export default TermsOfServicePage;
