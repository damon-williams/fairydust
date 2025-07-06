import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { Layout } from '@/components/layout/Layout';
import { Dashboard } from '@/pages/Dashboard';
import { Users } from '@/pages/Users';
import { Apps } from '@/pages/Apps';
import { LLM } from '@/pages/LLM';
import { Referrals } from '@/pages/Referrals';
import { SystemStatus } from '@/pages/SystemStatus';
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
                    <Route path="apps" element={<Apps />} />
                    <Route path="llm" element={<LLM />} />
                    <Route path="referrals" element={<Referrals />} />
                    <Route path="system" element={<SystemStatus />} />
                    <Route path="settings" element={
                      <div className="flex items-center justify-center h-64">
                        <p className="text-slate-500">Settings page coming soon...</p>
                      </div>
                    } />
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