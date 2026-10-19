/**
 * App.jsx
 *
 * Routing architecture:
 *  - Admin monitoring route       → AdminSecurityLogs (React Router + Redux auth)
 *  - Everything else (catch-all)  → Storefront SPA (self-contained useReducer)
 *
 * The Storefront handles: home, products, product detail, cart, checkout,
 * orders, auth modal, vendor dashboard, and admin dashboard internally.
 */
import { useEffect } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { useDispatch } from 'react-redux';
import { initializeAuth } from './features/auth/authSlice';
import { useAuth } from './hooks/useAuth';
import { Navigate } from 'react-router-dom';
import './theme.css';

import Storefront            from './Storefront';
import AdminSecurityLogs     from './pages/admin/AdminSecurityLogs';

// ── Loading screen ────────────────────────────────────────────────────────
function LoadingScreen() {
  return (
    <div style={{
      display: 'flex', justifyContent: 'center', alignItems: 'center',
      minHeight: '100vh', background: '#091917', color: '#b3c2b9',
      fontFamily: 'system-ui, sans-serif', flexDirection: 'column', gap: 16,
    }}>
      <div style={{
        width: 36, height: 36, border: '3px solid #2a4540',
        borderTopColor: '#dfbd89', borderRadius: '50%',
        animation: 'spin 0.8s linear infinite',
      }} />
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      <span style={{ fontSize: 14 }}>Loading...</span>
    </div>
  );
}

// ── Admin guard ───────────────────────────────────────────────────────────
function RequireAdminAuth({ children }) {
  const { isAuthenticated, isLoading, user } = useAuth(); // هذه تجلب البيانات من Redux

  // 1. لا تفعل أي شيء طالما النظام يحاول جلب التوكن (isLoading = true)
  if (isLoading) return <LoadingScreen />; 

  // 2. إذا انتهى التحميل ولم يجد توكن أو كنت لست أدمن
  if (!isAuthenticated || user?.role !== 'admin') {
    return <Navigate to="/" replace />; 
  }

  // 3. إذا انتهى التحميل وكنت أدمن فعلاً، افتح الصفحة
  return children;
}

// ── Inner routes ──────────────────────────────────────────────────────────
function AppRoutes() {

  // Silent refresh for the Redux auth slice used by delivery/admin specialist pages.
  // The Storefront component manages its own auth state separately.
  const { isLoading } = useAuth(); // الوصول لحالة التحميل من Redux
  const dispatch = useDispatch();

  useEffect(() => {
    dispatch(initializeAuth());
  }, [dispatch]);

  // إذا كان النظام لا يزال يتأكد من الهوية عند فتح الموقع لأول مرة
  if (isLoading) return <LoadingScreen />;

  return (
    <Routes>
      {/* ── Admin: monitoring/observability page ───────────────────── */}
      <Route
        path="/admin/monitoring"
        element={
          <RequireAdminAuth>
            <AdminSecurityLogs />
          </RequireAdminAuth>
        }
      />

      {/* ── Catch-all: full Storefront SPA ─────────────────────────── */}
      {/* Handles: /, /products, /products/:id, /cart, /checkout,      */}
      {/* /orders, /login, /register, /admin (AdminDashboard),         */}
      {/* /vendor (VendorDashboard) — all via internal page state.     */}
      <Route path="*" element={<Storefront />} />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  );
}
