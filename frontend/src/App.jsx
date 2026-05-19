import React, { useState } from 'react';
import { Toaster } from 'react-hot-toast';
import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import Navbar from './components/Navbar';
import Hero from './components/Hero';
import HowItWorks from './components/HowItWorks';
import Benefits from './components/Benefits';
import Pricing from './components/Pricing';
import HostingCreationForm from './components/HostingCreationForm';
import Footer from './components/Footer';
import Dashboard from './pages/Dashboard';
import AdminUserDetail from './pages/AdminUserDetail';
import AdminPixelUsers from './pages/AdminPixelUsers';
import AdminPixelUserDetail from './pages/AdminPixelUserDetail';
import StaffLogin from './pages/StaffLogin';
import StaffDashboard from './pages/StaffDashboard';
import PrivacyPolicy from './pages/PrivacyPolicy';
import TermsConditions from './pages/TermsConditions';
import ApiDocs from './pages/ApiDocs';
import VerifyEmail from './pages/VerifyEmail';
import ResetPassword from './pages/ResetPassword';
import Notifications from './pages/Notifications';
import AdminBlogList from './pages/AdminBlogList';
import AdminBlogEditor from './pages/AdminBlogEditor';
import BlogList from './pages/BlogList';
import BlogPost from './pages/BlogPost';
import NotFound from './pages/NotFound';
import { useAuth } from './hooks/useAuth';

const PrivateRoute = ({ children }) => {
  const { user, loading } = useAuth();
  if (loading) return null;
  return user ? children : <Navigate to="/" />;
};

const AdminRoute = ({ children }) => {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (!user) return <Navigate to="/" />;
  if (user.role !== 'admin') return <Navigate to="/dashboard" />;
  return children;
};

const Home = () => {
  const [selectedPlan, setSelectedPlan] = useState(null);

  const handleSelectPlan = (planId) => {
    setSelectedPlan(planId);
    setTimeout(() => {
      document.getElementById('nuevo-proyecto')?.scrollIntoView({ behavior: 'smooth' });
    }, 50);
  };

  return (
    <>
      <Hero />
      <HowItWorks />
      <Benefits />
      <Pricing onSelectPlan={handleSelectPlan} />
      <HostingCreationForm selectedPlan={selectedPlan} />
    </>
  );
};

function App() {
  const { user, loading } = useAuth();
  const location = useLocation();

  // Staff routes are fully independent — they use staff_token (not access_token).
  // Render them outside the normal auth flow so the Navbar/Footer never appear.
  if (location.pathname.startsWith('/staff/')) {
    return (
      <Routes>
        <Route path="/staff/login"     element={<StaffLogin />} />
        <Route path="/staff/dashboard" element={<StaffDashboard />} />
      </Routes>
    );
  }

  // Blog public routes are self-contained (own Navbar + Footer).
  // Skip landing Navbar/Footer wrapper to avoid double header and max-width constraint.
  if (location.pathname.startsWith('/blog')) {
    return (
      <>
        <Toaster position="top-right" toastOptions={{ style: { background: '#111', color: '#fff', border: '1px solid rgba(255,255,255,0.1)' } }} />
        <Routes>
          <Route path="/blog"       element={<BlogList />} />
          <Route path="/blog/:slug" element={<BlogPost />} />
          <Route path="*"           element={<NotFound />} />
        </Routes>
      </>
    );
  }

  if (loading) return null;

  return (
    <div className="min-h-screen bg-background text-white selection:bg-primary/30">
      <Toaster position="top-right" toastOptions={{ style: { background: '#111', color: '#fff', border: '1px solid rgba(255,255,255,0.1)' } }} />
      {!user && <Navbar />}
      <main className={!user ? "max-w-7xl mx-auto px-4 sm:px-6 lg:px-8" : ""}>
        <Routes>
          <Route path="/" element={user ? <Navigate to="/dashboard" /> : <Home />} />
          <Route path="/dashboard"      element={<PrivateRoute><Dashboard /></PrivateRoute>} />
          <Route path="/notifications"  element={<PrivateRoute><Notifications /></PrivateRoute>} />
          <Route path="/sites"     element={<PrivateRoute><Dashboard /></PrivateRoute>} />
          <Route path="/pixel"     element={<PrivateRoute><Dashboard /></PrivateRoute>} />
          <Route path="/advisory"  element={<PrivateRoute><Dashboard /></PrivateRoute>} />
          <Route path="/admin"                         element={<AdminRoute><Dashboard /></AdminRoute>} />
          <Route path="/admin/users/:id"              element={<AdminRoute><AdminUserDetail /></AdminRoute>} />
          <Route path="/admin/pixel-users"            element={<AdminRoute><AdminPixelUsers /></AdminRoute>} />
          <Route path="/admin/pixel-users/:user_id"   element={<AdminRoute><AdminPixelUserDetail /></AdminRoute>} />
          {/* Blog admin — admin only */}
          <Route path="/admin/blog"              element={<AdminRoute><AdminBlogList /></AdminRoute>} />
          <Route path="/admin/blog/new"          element={<AdminRoute><AdminBlogEditor /></AdminRoute>} />
          <Route path="/admin/blog/:id/edit"     element={<AdminRoute><AdminBlogEditor /></AdminRoute>} />
          {/* Blog public */}
          <Route path="/blog"           element={<BlogList />} />
          <Route path="/blog/:slug"     element={<BlogPost />} />
          {/* Legal & public pages — accessible without authentication */}
          <Route path="/privacy"        element={<PrivacyPolicy />} />
          <Route path="/terminos"       element={<TermsConditions />} />
          <Route path="/api-docs"       element={<ApiDocs />} />
          <Route path="/verify-email"   element={<VerifyEmail />} />
          <Route path="/reset-password" element={<ResetPassword />} />
          {/* Fallback staff routes (shouldn't normally be needed but keeps router happy) */}
          <Route path="/staff/login"     element={<StaffLogin />} />
          <Route path="/staff/dashboard" element={<StaffDashboard />} />
          {/* /login doesn't have its own page — the login flow lives on the landing page (/). */}
          <Route path="/login"           element={<Navigate to="/" />} />
          {/* Catch-all — must be last */}
          <Route path="*"               element={<NotFound />} />
        </Routes>
      </main>
      {!user && <Footer />}
    </div>
  );
}

export default App;
