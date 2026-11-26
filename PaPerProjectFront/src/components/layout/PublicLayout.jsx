import React from 'react';
import Header from './Header';
import Footer from './Footer';
import TopInfoBar from './TopInfoBar';
import Chatbot from './Chatbot';
import { Toaster } from '@/components/ui/toaster';

const PublicLayout = ({ children }) => {
  return (
    <div className="flex flex-col min-h-screen bg-background text-foreground font-sans" style={{ background: 'var(--app-page-bg)' }}>
      <TopInfoBar />
      <Header />
      <main className="flex-grow">{children}</main>
      <Footer />
      <Chatbot />
      <Toaster />
    </div>
  );
};

export default PublicLayout;

