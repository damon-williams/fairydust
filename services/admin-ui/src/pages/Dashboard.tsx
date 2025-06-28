import { useState, useEffect } from 'react';
import { StatsCard } from '@/components/dashboard/StatsCard';
import { RecentActivity } from '@/components/dashboard/RecentActivity';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { 
  Users, 
  Smartphone, 
  Clock, 
  Sparkles,
  AlertTriangle,
  Activity,
  DollarSign,
  TrendingUp,
  RefreshCw
} from 'lucide-react';
import { DashboardStats, User, App, SystemHealth } from '@/types/admin';
import { AdminAPI } from '@/lib/admin-api';

export function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [recentUsers, setRecentUsers] = useState<User[]>([]);
  const [recentApps, setRecentApps] = useState<App[]>([]);
  const [systemHealth, setSystemHealth] = useState<SystemHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadDashboardData = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const [statsData, healthData, usersData, appsData] = await Promise.all([
        AdminAPI.getDashboardStats(),
        AdminAPI.getSystemHealth(),
        AdminAPI.getRecentUsers(),
        AdminAPI.getRecentApps(),
      ]);
      
      setStats(statsData);
      setSystemHealth(healthData);
      setRecentUsers(usersData);
      setRecentApps(appsData);
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

  const hasSystemIssues = systemHealth && Object.values(systemHealth).some(status => status !== 'online');

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
      {/* System Health Alert */}
      {hasSystemIssues && (
        <Alert className="border-yellow-200 bg-yellow-50">
          <AlertTriangle className="h-4 w-4 text-yellow-600" />
          <AlertTitle className="text-yellow-800">System Status Alert</AlertTitle>
          <AlertDescription className="text-yellow-700">
            Some services are experiencing issues. 
            <Button 
              variant="link" 
              className="p-0 ml-1 text-yellow-800 underline"
              onClick={() => {
                // Scroll to system health section
                document.getElementById('system-health-section')?.scrollIntoView({ behavior: 'smooth' });
              }}
            >
              View System Status
            </Button>
          </AlertDescription>
        </Alert>
      )}

      {/* Pending Apps Alert */}
      {stats && stats.pending_apps > 0 && (
        <Alert className="border-blue-200 bg-blue-50">
          <Clock className="h-4 w-4 text-blue-600" />
          <AlertTitle className="text-blue-800">Action Required</AlertTitle>
          <AlertDescription className="text-blue-700">
            There are {stats?.pending_apps} app{stats?.pending_apps !== 1 ? 's' : ''} waiting for approval.
            <Button variant="link" className="p-0 ml-1 text-blue-800 underline">
              Review Pending Apps
            </Button>
          </AlertDescription>
        </Alert>
      )}

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
      <RecentActivity recentUsers={recentUsers} recentApps={recentApps} />

      {/* System Health Overview */}
      <Card id="system-health-section">
        <CardHeader>
          <CardTitle className="flex items-center">
            <Activity className="mr-2 h-5 w-5" />
            System Health
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
            {systemHealth && Object.entries(systemHealth).map(([service, status]) => (
              <div key={service} className="text-center">
                <div className="capitalize font-medium text-sm text-slate-700 mb-2">
                  {service}
                </div>
                <Badge
                  variant={
                    status === 'online' ? 'default' :
                    status === 'degraded' ? 'secondary' :
                    'destructive'
                  }
                  className="w-full justify-center"
                >
                  {status as string}
                </Badge>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}