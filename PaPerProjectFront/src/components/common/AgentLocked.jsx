import { useNavigate } from 'react-router-dom';
import { CreditCard, Lock } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import LapsedLeftovers from '@/components/common/LapsedLeftovers';

export const BILLING_PATH = '/company/dashboard/billing';

/**
 * Why a company cannot open an agent, from the status of its purchase
 * (`purchase_status` from the access check, or `status` of its row in
 * usePurchasedModules().allPurchases). No status means it never had the agent.
 */
export const lockReason = (status) => {
  if (!status) return 'not_bought';
  return status === 'past_due' ? 'payment_failed' : 'ended';
};

const WORDING = {
  not_bought: (title) => ({
    heading: 'Module Not Purchased',
    body: `You need to purchase the ${title} module to access this dashboard.`,
    action: 'Go to Home Page to Purchase',
  }),
  // A failed card has nothing to buy: checkout refuses a second subscription
  // beside the one being retried. Send them to their card instead.
  payment_failed: (title) => ({
    heading: 'Payment failed',
    body: `We could not take the payment for ${title}, so it is paused for everyone in your company. `
      + 'Update your card on the Billing page and we will try it again over the next few days. '
      + 'To get back in now, pay the unpaid invoice there.',
    action: 'Update your card',
  }),
  ended: (title) => ({
    heading: 'Subscription ended',
    body: `Your ${title} subscription has ended. Subscribe again to open it.`,
    action: 'Subscribe again',
  }),
};

/** The toast shown once when a locked agent is opened. */
export const lockToast = (title, status) => {
  const { heading, body } = WORDING[lockReason(status)](title);
  return { title: heading, description: body, variant: 'default' };
};

/**
 * Shown in place of an agent the company cannot open. Under the buttons, for an
 * agent it once had: what that agent still holds on everyone's calendar, which
 * can be removed from here and nowhere else.
 */
const AgentLocked = ({ title, moduleKey, status }) => {
  const navigate = useNavigate();
  const reason = lockReason(status);
  const { heading, body, action } = WORDING[reason](title);
  const Icon = reason === 'payment_failed' ? CreditCard : Lock;
  // Deep link straight to this agent's card on the landing page rather than
  // dropping the visitor at the top of it — HomePage scrolls to the section and
  // ModuleCardsSection rings the matching card.
  const buy = `/#ai-modules${moduleKey ? `?agent=${encodeURIComponent(moduleKey)}` : ''}`;

  return (
    <Card className="max-w-md w-full" data-testid="agent-locked" data-reason={reason}>
      <CardHeader>
        <div className="flex items-center justify-center mb-4">
          <Icon className="h-12 w-12 text-muted-foreground" />
        </div>
        <CardTitle className="text-center">{heading}</CardTitle>
        <CardDescription className="text-center">{body}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <Button onClick={() => navigate(reason === 'payment_failed' ? BILLING_PATH : buy)} className="w-full">
          {action}
        </Button>
        <Button onClick={() => navigate('/company/dashboard')} variant="outline" className="w-full">
          Back to Dashboard
        </Button>
        {reason !== 'not_bought' && moduleKey && <LapsedLeftovers moduleKey={moduleKey} />}
      </CardContent>
    </Card>
  );
};

export default AgentLocked;
