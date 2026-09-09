import { useEffect } from 'react';
import { createBrowserRouter, Navigate, RouterProvider, useNavigate } from 'react-router-dom';
import { RequireAuth, RedirectIfAuthed } from '@shared/auth/RequireAuth';
import { setSessionExpiredHandler } from '@shared/auth/session';
import { AppLayout } from '@features/layout/AppLayout';
import { DashboardPage } from '@pages/DashboardPage';
import { LoginPage } from '@pages/LoginPage';
import { PlaceholderPage } from '@pages/PlaceholderPage';
import { UiGalleryPage } from '@pages/UiGalleryPage';
import { NotFoundPage, RouteErrorPage } from '@pages/ErrorPages';

function SessionExpiryBridge() {
  const navigate = useNavigate();
  useEffect(() => {
    setSessionExpiredHandler(() => navigate('/login', { replace: true }));
    return () => setSessionExpiredHandler(() => {});
  }, [navigate]);
  return null;
}

const router = createBrowserRouter([
  {
    element: (
      <>
        <SessionExpiryBridge />
        <RequireAuth>
          <AppLayout />
        </RequireAuth>
      </>
    ),
    errorElement: <RouteErrorPage />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: 'send', element: <PlaceholderPage title="Envoyer de l’argent" /> },
      { path: 'pay', element: <PlaceholderPage title="Payer un marchand" /> },
      { path: 'history', element: <PlaceholderPage title="Historique" /> },
      { path: 'vault', element: <PlaceholderPage title="Coffre" /> },
      { path: 'savings', element: <PlaceholderPage title="Épargne" /> },
      { path: 'card', element: <PlaceholderPage title="Carte" /> },
      { path: 'profile', element: <PlaceholderPage title="Profil & KYC" /> },
      { path: 'ui', element: <UiGalleryPage /> },
    ],
  },
  {
    path: '/login',
    element: (
      <RedirectIfAuthed>
        <LoginPage />
      </RedirectIfAuthed>
    ),
  },
  { path: '/404', element: <NotFoundPage /> },
  { path: '*', element: <Navigate to="/404" replace /> },
]);

export function AppRouter() {
  return <RouterProvider router={router} />;
}
