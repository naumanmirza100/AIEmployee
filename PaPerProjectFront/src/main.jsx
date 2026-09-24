
import React, { Suspense } from 'react';
import ReactDOM from 'react-dom/client';
import App from '@/App';
import ThemeProvider from '@/theme/ThemeProvider';
import '@/index.css';
import '@fontsource/inter/400.css';
import '@fontsource/inter/500.css';
import '@fontsource/inter/600.css';
import '@fontsource/inter/700.css';
import '@fontsource/inter/800.css';
import './fonts/cal-sans.css';
import Div100vh from 'react-div-100vh';

import './i18n';

ReactDOM.createRoot(document.getElementById('root')).render(
  <>
    <Suspense fallback={<div>Loading...</div>}>
      <ThemeProvider>
        <Div100vh>
          <App />
        </Div100vh>
      </ThemeProvider>
    </Suspense>
  </>
);
