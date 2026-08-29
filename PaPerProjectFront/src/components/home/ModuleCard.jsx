import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { Check, ArrowRight, Sparkles, CheckCircle2, Lock } from 'lucide-react';
import { useToast } from '@/components/ui/use-toast';
import { getCompanyUser } from '@/services/companyAuthService';
import { checkModuleAccess, createCheckoutSession, getModulePlans } from '@/services/modulePurchaseService';

const ModuleCard = ({
  title,
  description,
  icon: Icon,
  features = [],
  price,
  pricePeriod = 'month',
  highlight = false,
  gradientFrom,
  gradientTo,
  iconColor = 'text-primary',
  moduleName, // Internal module name (e.g., 'recruitment_agent')
  className
}) => {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [hasAccess, setHasAccess] = useState(false);
  const [isChecking, setIsChecking] = useState(false);
  const [isPurchasing, setIsPurchasing] = useState(false);
  // Admin-defined plans (duration + price) the company picks from when buying.
  const [plans, setPlans] = useState([]);
  const [plansLoading, setPlansLoading] = useState(true);
  const [selectedPlanId, setSelectedPlanId] = useState(null);

  useEffect(() => {
    // Check if company user is logged in
    const companyUser = getCompanyUser();
    setIsLoggedIn(!!companyUser);

    // If logged in and moduleName provided, check access
    if (companyUser && moduleName) {
      checkAccess();
    }
    // Load the buy plans (public — works even when logged out).
    if (moduleName) {
      loadPlans();
    } else {
      setPlansLoading(false);
    }
  }, [moduleName]);

  const loadPlans = async () => {
    setPlansLoading(true);
    try {
      const res = await getModulePlans(moduleName);
      const list = res?.status === 'success' ? (res.plans || []) : [];
      setPlans(list);
      if (list.length) setSelectedPlanId(list[0].id); // preselect cheapest/shortest
    } catch (error) {
      console.error('Error loading module plans:', error);
      setPlans([]);
    } finally {
      setPlansLoading(false);
    }
  };

  const selectedPlan = plans.find((p) => p.id === selectedPlanId) || null;

  const checkAccess = async () => {
    if (!moduleName) return;

    setIsChecking(true);
    try {
      const response = await checkModuleAccess(moduleName);
      if (response.status === 'success') {
        setHasAccess(response.has_access);
      }
    } catch (error) {
      console.error('Error checking module access:', error);
    } finally {
      setIsChecking(false);
    }
  };

  const handleBuyClick = async () => {
    // If not logged in, redirect to login
    if (!isLoggedIn) {
      toast({
        title: 'Login Required',
        description: 'Please log in to purchase modules',
        variant: 'default',
      });
      navigate('/company/login');
      return;
    }

    // If already has access, show message
    if (hasAccess) {
      toast({
        title: 'Already Purchased',
        description: `You already have access to ${title}`,
        variant: 'default',
      });
      return;
    }

    // Purchase the module
    if (!moduleName) {
      toast({
        title: 'Error',
        description: 'Module name is missing',
        variant: 'destructive',
      });
      return;
    }

    // A plan must exist and be selected before buying.
    if (!plans.length) {
      toast({
        title: 'No plans available',
        description: `${title} can't be purchased yet — please check back later.`,
        variant: 'destructive',
      });
      return;
    }
    if (!selectedPlanId) {
      toast({
        title: 'Choose a plan',
        description: 'Please select a plan before buying.',
        variant: 'default',
      });
      return;
    }

    setIsPurchasing(true);
    try {
      const response = await createCheckoutSession(moduleName, selectedPlanId);
      if (response.status === 'success' && response.url) {
        window.location.href = response.url;
        return;
      }
      toast({
        title: 'Checkout Failed',
        description: response.message || 'Could not start checkout',
        variant: 'destructive',
      });
    } catch (error) {
      console.error('Checkout error:', error);
      toast({
        title: 'Checkout Failed',
        description: error?.data?.message || error?.message || 'An error occurred. Please try again.',
        variant: 'destructive',
      });
    } finally {
      setIsPurchasing(false);
    }
  };
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.3 }}
      transition={{ duration: 0.5 }}
      className={cn("h-full", className)}
    >
      <Card className={cn(
        "relative h-full flex flex-col transition-all duration-300 hover:shadow-2xl overflow-hidden",
        highlight 
          ? "border-2 border-primary shadow-xl scale-105" 
          : "hover:shadow-lg hover:scale-[1.02]"
      )}>
        {/* Gradient Background */}
        {gradientFrom && gradientTo && (
          <div 
            className="absolute inset-0 opacity-5 pointer-events-none"
            style={{
              background: `linear-gradient(to bottom right, ${gradientFrom}, ${gradientTo})`
            }}
          />
        )}
        
        {/* Highlight Badge */}
        {highlight && (
          <div className="absolute top-4 right-4 z-10">
            <div className="flex items-center gap-1 bg-primary text-primary-foreground px-3 py-1 rounded-full text-xs font-semibold">
              <Sparkles className="h-3 w-3" />
              Popular
            </div>
          </div>
        )}

        <CardHeader className="relative">
          {/* Icon */}
          <div className={cn(
            "inline-flex items-center justify-center w-16 h-16 rounded-2xl mb-4",
            highlight 
              ? "bg-primary/10" 
              : "bg-secondary"
          )}>
            <Icon className={cn("h-8 w-8", iconColor)} />
          </div>
          
          <CardTitle className="text-2xl font-bold text-foreground mb-2">
            {title}
          </CardTitle>
          <CardDescription className="text-base text-muted-foreground">
            {description}
          </CardDescription>
        </CardHeader>

        <CardContent className="flex-1">
          {/* Plans — the company picks an admin-defined duration + price. */}
          <div className="mb-6">
            {plansLoading ? (
              <div className="h-10 w-32 rounded-md bg-muted animate-pulse" />
            ) : plans.length > 0 ? (
              <>
                {/* Selected plan's price, shown large */}
                <div className="flex items-baseline gap-2">
                  <span className="text-4xl font-bold text-foreground">
                    ${selectedPlan ? Number(selectedPlan.price_usd).toLocaleString() : '—'}
                  </span>
                  {selectedPlan && (
                    <span className="text-muted-foreground">
                      /{selectedPlan.billing_interval === 'year' ? 'year' : 'month'}
                    </span>
                  )}
                </div>

                {/* Plan chooser — only shown when there's more than one */}
                {plans.length > 1 && (
                  <div className="flex flex-wrap gap-2 mt-3">
                    {plans.map((p) => {
                      const active = p.id === selectedPlanId;
                      return (
                        <button
                          key={p.id}
                          type="button"
                          onClick={() => setSelectedPlanId(p.id)}
                          className={cn(
                            "px-3 py-1.5 rounded-full text-sm font-medium border transition-colors",
                            active
                              ? "border-primary bg-primary/10 text-primary"
                              : "border-border text-muted-foreground hover:border-primary/50"
                          )}
                        >
                          ${Number(p.price_usd).toLocaleString()}/{p.billing_interval === 'year' ? 'yr' : 'mo'}
                        </button>
                      );
                    })}
                  </div>
                )}
              </>
            ) : (
              <div className="inline-flex items-center gap-2 rounded-md bg-muted px-3 py-2 text-sm text-muted-foreground">
                <Lock className="h-3.5 w-3.5" />
                No plans available yet
              </div>
            )}
          </div>

          {/* Features List */}
          {features.length > 0 && (
            <ul className="space-y-3">
              {features.map((feature, index) => (
                <li key={index} className="flex items-start gap-3">
                  <div className={cn(
                    "flex-shrink-0 mt-0.5 rounded-full p-1",
                    highlight ? "bg-primary/10" : "bg-secondary"
                  )}>
                    <Check className={cn(
                      "h-4 w-4",
                      highlight ? "text-primary" : "text-muted-foreground"
                    )} />
                  </div>
                  <span className="text-sm text-foreground">{feature}</span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>

        <CardFooter className="pt-6">
          {hasAccess ? (
            <Button
              disabled
              className="w-full bg-green-600 hover:bg-green-600 cursor-not-allowed"
              size="lg"
            >
              <CheckCircle2 className="mr-2 h-4 w-4" />
              Active Subscription
            </Button>
          ) : !isLoggedIn ? (
            <Button
              onClick={handleBuyClick}
              className={cn(
                "w-full group",
                highlight 
                  ? "bg-primary hover:bg-primary/90" 
                  : "bg-secondary hover:bg-secondary/80"
              )}
              size="lg"
            >
              <Lock className="mr-2 h-4 w-4" />
              Login to Subscribe
            </Button>
          ) : (
            <Button
              onClick={handleBuyClick}
              disabled={isPurchasing || isChecking || plansLoading || plans.length === 0}
              className={cn(
                "w-full group",
                highlight
                  ? "bg-primary hover:bg-primary/90"
                  : "bg-secondary hover:bg-secondary/80"
              )}
              size="lg"
            >
              {isPurchasing ? (
                <>Processing...</>
              ) : plans.length === 0 && !plansLoading ? (
                <>
                  <Lock className="mr-2 h-4 w-4" />
                  Unavailable
                </>
              ) : (
                <>
                  Subscribe
                  <ArrowRight className="ml-2 h-4 w-4 transition-transform group-hover:translate-x-1" />
                </>
              )}
            </Button>
          )}
        </CardFooter>
      </Card>
    </motion.div>
  );
};

export default ModuleCard;

