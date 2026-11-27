import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';

// A way back to the website from the sign-in pages, which had none (27 Nov 2026). It sits above the card,
// in the page's flow, so it never overlaps the form on a short phone screen.
const BackToHome = () => (
  <Link
    to="/"
    data-testid="back-to-home"
    className="mb-3 inline-flex items-center gap-1.5 rounded-md px-2 py-1.5 -ml-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground hover:bg-muted/60"
  >
    <ArrowLeft className="h-4 w-4" />
    Back to home
  </Link>
);

export default BackToHome;
