import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from 'react-router-dom';

import { router } from './router';

import './styles/reset.css';
import './styles/tokens.css';
import './styles/globals.css';

async function bootstrap() {
  if (import.meta.env.VITE_USE_MOCK === 'true') {
    const { installMockFetch } = await import('./mocks/install');
    installMockFetch();
  }

  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { staleTime: 30_000, refetchOnWindowFocus: false },
    },
  });

  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </React.StrictMode>,
  );
}

bootstrap();
