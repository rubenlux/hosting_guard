import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import Navbar from './components/Navbar';
import Hero from './components/Hero';
import HowItWorks from './components/HowItWorks';
import Benefits from './components/Benefits';
import Pricing from './components/Pricing';
import HostingCreationForm from './components/HostingCreationForm';
import Footer from './components/Footer';
import Dashboard from './pages/Dashboard';
import AdminUserDetail from './pages/AdminUserDetail';
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

  if (loading) return null;

  return (
    <div className="min-h-screen bg-background text-white selection:bg-primary/30">
      {!user && <Navbar />}
      <main className={!user ? "max-w-7xl mx-auto px-4 sm:px-6 lg:px-8" : ""}>
        <Routes>
          <Route path="/" element={user ? <Navigate to="/dashboard" /> : <Home />} />
          <Route path="/dashboard" element={<PrivateRoute><Dashboard /></PrivateRoute>} />
          <Route path="/pixel"     element={<PrivateRoute><Dashboard /></PrivateRoute>} />
          <Route path="/admin"          element={<AdminRoute><Dashboard /></AdminRoute>} />
          <Route path="/admin/users/:id" element={<AdminRoute><AdminUserDetail /></AdminRoute>} />
        </Routes>
      </main>
      {!user && <Footer />}
    </div>
  );
}

export default App;
