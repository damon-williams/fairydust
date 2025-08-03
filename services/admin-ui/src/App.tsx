import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { Layout } from '@/components/layout/Layout';
import { Dashboard } from '@/pages/Dashboard';
import { Users } from '@/pages/Users';
import { UserProfile } from '@/pages/UserProfile';
import { Apps } from '@/pages/Apps';
import { LLM } from '@/pages/LLM';
import { Referrals } from '@/pages/Referrals';
import Payments from '@/pages/Payments';
import DeletionLogs from '@/pages/DeletionLogs';
import Terms from '@/pages/Terms';
import { SystemStatus } from '@/pages/SystemStatus';
import Settings from '@/pages/Settings';
import { Toaster } from '@/components/ui/sonner';
import { AuthProvider } from '@/contexts/AuthContext';
import { ProtectedRoute } from '@/components/auth/ProtectedRoute';

function App() {
  return (
    <AuthProvider>
      <Router>
        <div className="min-h-screen bg-slate-50">
          <ProtectedRoute>
            <Routes>
              {/* Redirect root to dashboard */}
              <Route path="/" element={<Navigate to="/admin/dashboard" replace />} />
              
              {/* Admin routes */}
              <Route path="/admin/*" element={
                <Layout>
                  <Routes>
                    <Route path="dashboard" element={<Dashboard />} />
                    <Route path="users" element={<Users />} />
                    <Route path="users/:userId/profile" element={<UserProfile />} />
                    <Route path="apps" element={<Apps />} />
                    <Route path="llm" element={<LLM />} />
                    <Route path="referrals" element={<Referrals />} />
                    <Route path="payments" element={<Payments />} />
                    <Route path="deletion-logs" element={<DeletionLogs />} />
                    <Route path="terms" element={<Terms />} />
                    <Route path="system" element={<SystemStatus />} />
                    <Route path="settings" element={<Settings />} />
                    {/* Default to dashboard */}
                    <Route path="*" element={<Navigate to="/admin/dashboard" replace />} />
                  </Routes>
                </Layout>
              } />
              
              {/* Catch all */}
              <Route path="*" element={<Navigate to="/admin/dashboard" replace />} />
            </Routes>
          </ProtectedRoute>
          
          {/* Toast notifications */}
          <Toaster />
        </div>
      </Router>
    </AuthProvider>
  );
}

export default App;