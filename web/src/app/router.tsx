import { useEffect } from 'react';
import { createBrowserRouter, Navigate, RouterProvider, useNavigate } from 'react-router-dom';
import { RedirectIfAuthed, RequireAuth } from '@shared/auth/RequireAuth';
import { setSessionExpiredHandler } from '@shared/auth/session';
import { AppLayout } from '@features/layout/AppLayout';
import { DashboardPage } from '@pages/DashboardPage';
import { LoginPage } from '@pages/LoginPage';
import { RegisterPage } from '@pages/RegisterPage';
import { SendMoneyPage } from '@pages/SendMoneyPage';
import { PayMerchantPage } from '@pages/PayMerchantPage';
import { ReceivePage } from '@pages/ReceivePage';
import { PaymentRequestsPage } from '@pages/PaymentRequestsPage';
import { HistoryPage } from '@pages/HistoryPage';
import { DepositCashPage, WithdrawCashPage } from '@pages/CashPages';
import { OperatorsPage } from '@pages/OperatorsPage';
import { VaultPage } from '@pages/VaultPage';
import { SavingsPage } from '@pages/SavingsPage';
import { CardPage } from '@pages/CardPage';
import { ProfilePage } from '@pages/ProfilePage';
import { NotificationsPage } from '@pages/NotificationsPage';
import { UiGalleryPage } from '@pages/UiGalleryPage';
import { NotFoundPage, RouteErrorPage } from '@pages/ErrorPages';
import {
  AgentDashboardPage,
  AgentDepositPage,
  AgentFloatPage,
  AgentOperationsPage,
  AgentWithdrawPage,
} from '@pages/agent/AgentPages';
import { AdminLayout, AdminLoginPage, RequireAdmin } from '@pages/admin/AdminShell';
import {
  AdminAccountsPage,
  AdminAmlPage,
  AdminAuditPage,
  AdminFinancePage,
  AdminKycPage,
  AdminReferencePage,
} from '@pages/admin/AdminPages';

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
      { path: 'send', element: <SendMoneyPage /> },
      { path: 'request', element: <PaymentRequestsPage /> },
      { path: 'pay', element: <PayMerchantPage /> },
      { path: 'receive', element: <ReceivePage /> },
      { path: 'history', element: <HistoryPage /> },
      { path: 'cash/withdraw', element: <WithdrawCashPage /> },
      { path: 'cash/deposit', element: <DepositCashPage /> },
      { path: 'operators', element: <OperatorsPage /> },
      { path: 'vault', element: <VaultPage /> },
      { path: 'savings', element: <SavingsPage /> },
      { path: 'card', element: <CardPage /> },
      { path: 'notifications', element: <NotificationsPage /> },
      { path: 'profile', element: <ProfilePage /> },
      { path: 'agent', element: <AgentDashboardPage /> },
      { path: 'agent/deposit', element: <AgentDepositPage /> },
      { path: 'agent/withdraw', element: <AgentWithdrawPage /> },
      { path: 'agent/operations', element: <AgentOperationsPage /> },
      { path: 'agent/float', element: <AgentFloatPage /> },
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
  {
    path: '/register',
    element: (
      <RedirectIfAuthed>
        <RegisterPage />
      </RedirectIfAuthed>
    ),
  },
  { path: '/admin/login', element: <AdminLoginPage /> },
  {
    path: '/admin',
    element: (
      <RequireAdmin>
        <AdminLayout />
      </RequireAdmin>
    ),
    errorElement: <RouteErrorPage />,
    children: [
      { index: true, element: <AdminAccountsPage /> },
      { path: 'kyc', element: <AdminKycPage /> },
      { path: 'aml', element: <AdminAmlPage /> },
      { path: 'reference', element: <AdminReferencePage /> },
      { path: 'finance', element: <AdminFinancePage /> },
      { path: 'audit', element: <AdminAuditPage /> },
    ],
  },
  { path: '/404', element: <NotFoundPage /> },
  { path: '*', element: <Navigate to="/404" replace /> },
]);

export function AppRouter() {
  return <RouterProvider router={router} />;
}
