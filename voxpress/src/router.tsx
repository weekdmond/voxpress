import { createBrowserRouter } from 'react-router-dom';
import { AppShell } from './layouts/AppShell';
import { HomePage } from './pages/Home';
import { LibraryPage } from './pages/Library';
import { ArticlesPage } from './pages/Articles';
import { ArticlePage } from './pages/Article';
import { ImportPage } from './pages/Import';
import { SettingsPage } from './pages/Settings';

export const router = createBrowserRouter([
  {
    element: <AppShell />,
    children: [
      { index: true, element: <HomePage /> },
      { path: 'library', element: <LibraryPage /> },
      { path: 'articles', element: <ArticlesPage /> },
      { path: 'articles/:id', element: <ArticlePage /> },
      { path: 'import/:creatorId', element: <ImportPage /> },
      { path: 'settings', element: <SettingsPage /> },
    ],
  },
]);
