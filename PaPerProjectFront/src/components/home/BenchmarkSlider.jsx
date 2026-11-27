import React, { useState } from 'react';
    import { Link, useNavigate } from 'react-router-dom';
    import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
    import { Slider } from '@/components/ui/slider';
    import { Button } from '@/components/ui/button';
    import { useToast } from "@/components/ui/use-toast";
    import { 
      ArrowRight, 
      TrendingUp, 
      Code, 
      Users, 
      Calendar, 
      Database, 
      Shield, 
    } from 'lucide-react';
    import { useTranslation, Trans } from 'react-i18next';
    import { FaStripeS, FaCcPaypal, FaCcStripe } from "react-icons/fa";
    
    const BenchmarkSlider = () => {
      const navigate = useNavigate();
      const { t } = useTranslation();
      const [budget, setBudget] = useState(25000);
      const { toast } = useToast();
      const gbpRate = 0.8;
      const budgetGbp = budget * gbpRate;
    
      const features = [
        { icon: Code, text: t('benchmark_slider_basis_1') },
        { icon: Users, text: t('benchmark_slider_basis_2') },
        { icon: Calendar, text: t('benchmark_slider_basis_3') },
        { icon: TrendingUp, text: t('benchmark_slider_basis_4') },
        { icon: Database, text: t('benchmark_slider_basis_5') },
        { icon: Shield, text: t('benchmark_slider_basis_6') },
      ];
    
      const handleGetQuote = () => {
        const formElement = document.getElementById('project-form');
        if (formElement) {
          formElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
          
          const inputElement = formElement.querySelector('input[type="text"]');
          if(inputElement) {
            setTimeout(() => inputElement.focus(), 500);
          }
        } else {
          // The project form lives on its own page (26 Nov 2026: the button only showed a message).
          navigate('/start-project');
        }
      };
    
      return (
        <section id="benchmark-slider" className="py-16 md:py-24 bg-background">
          <div className="container mx-auto px-4 md:px-6">
            <div className="grid lg:grid-cols-2 gap-8 items-start">
              
              <Card className="shadow-lg h-full flex flex-col bg-card rounded-xl card-border-glow">
                <CardHeader className="bg-secondary/40 p-6 border-b">
                  <CardTitle className="text-xl md:text-2xl font-bold font-heading">{t('benchmark_slider_title')}</CardTitle>
                  <CardDescription className="mt-2">{t('benchmark_slider_desc')}</CardDescription>
                </CardHeader>
                <CardContent className="pt-8 px-6 md:px-8 flex-grow flex flex-col justify-between">
                  <div>
                    <div className="text-center mb-6">
                      <p className="text-4xl font-extrabold text-gradient">
                        ${budget.toLocaleString()}
                      </p>
                      <p className="text-lg text-muted-foreground">≈ £{budgetGbp.toLocaleString('en-GB')}</p>
                      <p className="text-sm text-muted-foreground mt-1">{t('benchmark_slider_price_suffix')}</p>
                    </div>
                    <Slider
                      defaultValue={[budget]}
                      max={100000}
                      min={1000}
                      step={500}
                      onValueChange={(value) => setBudget(value[0])}
                      className="mb-6"
                    />
                    <div className="text-left mb-6">
                      <p className="font-semibold text-foreground mb-3">{t('benchmark_slider_basis_title')}</p>
                      <ul className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-3 text-sm text-muted-foreground">
                        {features.map((feature) => (
                          <li key={feature.text} className="flex items-center">
                            <feature.icon className="h-4 w-4 text-primary mr-2 flex-shrink-0" />
                            <span>{feature.text}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                  <div className="flex justify-center mt-4">
                     <Button onClick={handleGetQuote} size="lg">
                        {t('benchmark_slider_button')}
                        <ArrowRight className="ml-2 h-5 w-5" />
                    </Button>
                  </div>
                </CardContent>
              </Card>
    
              <Card className="shadow-lg h-full flex flex-col bg-card rounded-xl card-border-glow">
                <CardHeader className="bg-secondary/40 p-6 border-b">
                  <CardTitle className="text-xl md:text-2xl font-bold font-heading">{t('payment_options_title')}</CardTitle>
                  <CardDescription className="mt-2">{t('payment_options_desc')}</CardDescription>
                </CardHeader>
                <CardContent className="pt-8 px-6 md:px-8 flex-grow flex flex-col justify-between">
                    <div className="space-y-4">
                        <div className="flex items-center gap-4 p-4 border rounded-lg bg-secondary/40 hover:bg-secondary/60 transition-colors">
                            <div className="flex-shrink-0 text-4xl text-[#FFB3C7]">
                                <FaStripeS />
                            </div>
                            <div className="flex-grow">
                                <p className="font-bold text-foreground">{t('payment_options_klarna', 'Klarna / Affirm')}</p>
                                <p className="text-sm text-muted-foreground">{t('payment_options_klarna_desc')}</p>
                            </div>
                        </div>
    
                        <div className="flex items-center gap-4 p-4 border rounded-lg bg-secondary/40 hover:bg-secondary/60 transition-colors">
                            <div className="flex-shrink-0 text-4xl text-[#B2FCE4]">
                               <FaCcPaypal />
                            </div>
                            <div className="flex-grow">
                                <p className="font-bold text-foreground">{t('payment_options_clearpay', 'PayPal / Clearpay')}</p>
                                <p className="text-sm text-muted-foreground">{t('payment_options_clearpay_desc')}</p>
                            </div>
                        </div>
    
                        <div className="flex items-center gap-4 p-4 border rounded-lg bg-secondary/40 hover:bg-secondary/60 transition-colors">
                            <div className="flex-shrink-0 text-4xl text-indigo-500">
                               <FaCcStripe />
                            </div>
                            <div className="flex-grow">
                                <p className="font-bold text-foreground">{t('payment_options_stripe', 'Stripe')}</p>
                                <p className="text-sm text-muted-foreground">{t('payment_options_stripe_desc', 'Secure credit card payments & financing.')}</p>
                            </div>
                        </div>
                        
                        <div className="p-4 border-2 border-primary rounded-lg bg-primary/10 text-center">
                            <p className="font-extrabold text-primary text-lg">{t('payment_options_deposit_title')}</p>
                            <p className="text-sm text-primary/80 mt-1">
                              <Trans i18nKey="payment_options_deposit_desc">
                                Secure your team and kick off your project with a small down payment. <span className="font-bold">0% interest</span> on project financing.
                              </Trans>
                            </p>
                        </div>
    
                    </div>
                    <div className="flex justify-center mt-6">
                      <Button asChild variant="outline">
                          <Link to="/payment-options">{t('payment_options_button')}</Link>
                      </Button>
                    </div>
                </CardContent>
              </Card>
            </div>
          </div>
        </section>
      );
    };
    
    export default BenchmarkSlider;