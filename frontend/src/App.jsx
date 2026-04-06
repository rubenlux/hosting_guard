import React from 'react';
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

const Home = () => (
  <>
    <Hero />
    <HowItWorks />
    <Benefits />
    <Pricing />
    <HostingCreationForm />
  </>
);

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

  if (loading) return null;

  return (
    <div className="min-h-screen bg-background text-white selection:bg-primary/30">
      {!user && <Navbar />}
      <main className={!user ? "max-w-7xl mx-auto px-4 sm:px-6 lg:px-8" : ""}>
        <Routes>
          <Route path="/" element={user ? <Navigate to="/dashboard" /> : <Home />} />
          <Route path="/dashboard" element={<PrivateRoute><Dashboard /></PrivateRoute>} />
          <Route path="/pixel"     element={<PrivateRoute><Dashboard /></PrivateRoute>} />
          <Route path="/admin"                         element={<AdminRoute><Dashboard /></AdminRoute>} />
          <Route path="/admin/users/:id"              element={<AdminRoute><AdminUserDetail /></AdminRoute>} />
          <Route path="/admin/pixel-users"            element={<AdminRoute><AdminPixelUsers /></AdminRoute>} />
          <Route path="/admin/pixel-users/:user_id"   element={<AdminRoute><AdminPixelUserDetail /></AdminRoute>} />
          {/* Fallback staff routes (shouldn't normally be needed but keeps router happy) */}
          <Route path="/staff/login"     element={<StaffLogin />} />
          <Route path="/staff/dashboard" element={<StaffDashboard />} />
        </Routes>
      </main>
      {!user && <Footer />}
    </div>
  );
}

export default App;
