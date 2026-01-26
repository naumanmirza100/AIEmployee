import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { Check, ArrowRight, Sparkles, CheckCircle2, Lock } from 'lucide-react';
import { useToast } from '@/components/ui/use-toast';
import { getCompanyUser } from '@/services/companyAuthService';
import { checkModuleAccess, createCheckoutSession } from '@/services/modulePurchaseService';

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

  useEffect(() => {
    // Check if company user is logged in
    const companyUser = getCompanyUser();
    setIsLoggedIn(!!companyUser);
    
    // If logged in and moduleName provided, check access
    if (companyUser && moduleName) {
      checkAccess();
    }
  }, [moduleName]);

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

    setIsPurchasing(true);
    try {
      const response = await createCheckoutSession(moduleName);
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
          {/* Price */}
          {price && (
            <div className="mb-6">
              <div className="flex items-baseline gap-2">
                <span className="text-4xl font-bold text-foreground">${price}</span>
                <span className="text-muted-foreground">/{pricePeriod}</span>
              </div>
            </div>
          )}

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
              Already Purchased
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
              Login to Buy
            </Button>
          ) : (
            <Button
              onClick={handleBuyClick}
              disabled={isPurchasing || isChecking}
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
              ) : (
                <>
                  Buy Now
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
