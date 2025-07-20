import { useState, useEffect } from 'react';
import { StatsCard } from '@/components/dashboard/StatsCard';
import { RecentActivity } from '@/components/dashboard/RecentActivity';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { 
  Users, 
  Sparkles,
  Activity,
  DollarSign,
  TrendingUp,
  RefreshCw,
  AlertTriangle
} from 'lucide-react';
import { DashboardStats, User } from '@/types/admin';
import { AdminAPI } from '@/lib/admin-api';

export function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [recentUsers, setRecentUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadDashboardData = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const [statsData, usersData] = await Promise.all([
        AdminAPI.getDashboardStats(),
        AdminAPI.getRecentUsers(),
      ]);
      
      setStats(statsData);
      setRecentUsers(usersData);
    } catch (err) {
      console.error('Failed to load dashboard data:', err);
      setError('Failed to load dashboard data. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDashboardData();
  }, []);


  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center space-y-4">
          <RefreshCw className="h-8 w-8 animate-spin mx-auto text-slate-400" />
          <p className="text-slate-500">Loading dashboard...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <Alert className="border-red-200 bg-red-50">
          <AlertTriangle className="h-4 w-4 text-red-600" />
          <AlertTitle className="text-red-800">Error Loading Dashboard</AlertTitle>
          <AlertDescription className="text-red-700">
            {error}
            <Button 
              variant="link" 
              className="p-0 ml-2 text-red-800 underline"
              onClick={loadDashboardData}
            >
              Retry
            </Button>
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header with Version */}
      <div>
        <h1 className="text-3xl font-bold text-slate-900">Dashboard</h1>
        <p className="text-slate-500">Welcome to the fairydust admin portal.</p>
      </div>


      {/* Top Row Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatsCard
          title="Total Users"
          value={stats?.total_users || 0}
          change={{ value: 12, trend: 'up', period: 'last month' }}
          icon={<Users className="h-5 w-5" />}
          gradient="from-blue-500 to-blue-600"
        />
        <StatsCard
          title="Active Today"
          value={stats?.active_users_today || 0}
          icon={<Activity className="h-5 w-5" />}
          gradient="from-emerald-500 to-emerald-600"
        />
        <StatsCard
          title="Active This Week"
          value={stats?.active_users_week || 0}
          icon={<TrendingUp className="h-5 w-5" />}
          gradient="from-cyan-500 to-cyan-600"
        />
        <StatsCard
          title="New This Week"
          value={stats?.new_users_week || 0}
          icon={<Users className="h-5 w-5" />}
          gradient="from-green-500 to-green-600"
        />
      </div>

      {/* Bottom Row Stats - DUST Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatsCard
          title="Total DUST Consumed"
          value={`${(stats?.total_dust_consumed || 0).toLocaleString()}`}
          icon={<DollarSign className="h-5 w-5" />}
          gradient="from-orange-500 to-orange-600"
        />
        <StatsCard
          title="Consumed Today"
          value={`${(stats?.dust_consumed_today || 0).toLocaleString()}`}
          icon={<Activity className="h-5 w-5" />}
          gradient="from-red-500 to-red-600"
        />
        <StatsCard
          title="Consumed This Week"
          value={`${(stats?.dust_consumed_week || 0).toLocaleString()}`}
          icon={<TrendingUp className="h-5 w-5" />}
          gradient="from-pink-500 to-pink-600"
        />
        <StatsCard
          title="Total DUST Issued"
          value={`${(stats?.total_dust_issued || 0).toLocaleString()}`}
          change={{ value: 15, trend: 'up', period: 'last week' }}
          icon={<Sparkles className="h-5 w-5" />}
          gradient="from-purple-500 to-purple-600"
        />
      </div>

      {/* Recent Activity */}
      <RecentActivity recentUsers={recentUsers} />
    </div>
  );
}