import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { AuthGuard } from '@/components/AuthGuard';
import { ToastProvider } from '@/components/ui/Toast';
import { lazy, Suspense } from 'react';

const Login = lazy(() => import('@/pages/Login'));
const Dashboard = lazy(() => import('@/pages/Dashboard'));
const Portfolio = lazy(() => import('@/pages/Portfolio'));
const Orders = lazy(() => import('@/pages/Orders'));
const Agent = lazy(() => import('@/pages/Agent'));
const Scheduler = lazy(() => import('@/pages/Scheduler'));
const Backtest = lazy(() => import('@/pages/Backtest'));
const Settings = lazy(() => import('@/pages/Settings'));

function PageLoader() {
  return (
    <div className="flex h-64 items-center justify-center">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-accent border-t-transparent" />
    </div>
  );
}

export default function App() {
  return (
    <ToastProvider>
      <BrowserRouter>
        <Routes>
          {/* Public route */}
          <Route
            path="login"
            element={
              <Suspense fallback={<PageLoader />}>
                <Login />
              </Suspense>
            }
          />

          {/* Protected routes */}
          <Route element={<AuthGuard />}>
            <Route element={<Layout />}>
              <Route
                index
                element={
                  <Suspense fallback={<PageLoader />}>
                    <Dashboard />
                  </Suspense>
                }
              />
              <Route
                path="portfolio"
                element={
                  <Suspense fallback={<PageLoader />}>
                    <Portfolio />
                  </Suspense>
                }
              />
              <Route
                path="orders"
                element={
                  <Suspense fallback={<PageLoader />}>
                    <Orders />
                  </Suspense>
                }
              />
              <Route
                path="agent"
                element={
                  <Suspense fallback={<PageLoader />}>
                    <Agent />
                  </Suspense>
                }
              />
              <Route
                path="scheduler"
                element={
                  <Suspense fallback={<PageLoader />}>
                    <Scheduler />
                  </Suspense>
                }
              />
              <Route
                path="backtest"
                element={
                  <Suspense fallback={<PageLoader />}>
                    <Backtest />
                  </Suspense>
                }
              />
              <Route
                path="settings"
                element={
                  <Suspense fallback={<PageLoader />}>
                    <Settings />
                  </Suspense>
                }
              />
            </Route>
          </Route>
        </Routes>
      </BrowserRouter>
    </ToastProvider>
  );
}
