import { useState } from 'react';
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
  TrendingUp
} from 'lucide-react';
import { DashboardStats, User, App, SystemHealth } from '@/types/admin';

// Mock data - in real app, this would come from API
const mockStats: DashboardStats = {
  total_users: 1247,
  total_apps: 23,
  pending_apps: 3,
  total_dust_issued: 31250,
  active_users_today: 89,
  active_users_week: 432,
  total_transactions: 5678,
  total_llm_usage: 12450
};

const mockRecentUsers: User[] = [
  {
    id: '1',
    fairyname: 'cosmic_dreamer_1234',
    email: 'user1@example.com',
    is_builder: false,
    is_admin: false,
    is_active: true,
    dust_balance: 25,
    auth_provider: 'email',
    total_profiling_sessions: 0,
    streak_days: 1,
    created_at: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: '2',
    fairyname: 'stellar_spark_5678',
    email: 'builder@example.com',
    is_builder: true,
    is_admin: false,
    is_active: true,
    dust_balance: 150,
    auth_provider: 'google',
    total_profiling_sessions: 3,
    streak_days: 5,
    created_at: new Date(Date.now() - 4 * 60 * 60 * 1000).toISOString(),
    updated_at: new Date().toISOString(),
  },
];

const mockRecentApps: App[] = [
  {
    id: '1',
    name: 'Recipe Generator',
    slug: 'recipe-generator',
    description: 'AI-powered recipe creation',
    status: 'approved',
    builder_id: '2',
    builder_name: 'stellar_spark_5678',
    category: 'cooking',
    created_at: new Date(Date.now() - 1 * 60 * 60 * 1000).toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: '2',
    name: 'Story Creator',
    slug: 'story-creator',
    description: 'Personalized storytelling',
    status: 'pending',
    builder_id: '3',
    builder_name: 'mystic_moon_9012',
    category: 'entertainment',
    created_at: new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString(),
    updated_at: new Date().toISOString(),
  },
];

const mockSystemHealth: SystemHealth = {
  identity: 'online',
  ledger: 'online',
  apps: 'online',
  content: 'degraded',
  admin: 'online',
  builder: 'online',
};

export function Dashboard() {
  const [stats, setStats] = useState<DashboardStats>(mockStats);
  const [recentUsers, setRecentUsers] = useState<User[]>(mockRecentUsers);
  const [recentApps, setRecentApps] = useState<App[]>(mockRecentApps);
  const [systemHealth, setSystemHealth] = useState<SystemHealth>(mockSystemHealth);

  const hasSystemIssues = Object.values(systemHealth).some(status => status !== 'online');

  return (
    <div className="space-y-6">
      {/* System Health Alert */}
      {hasSystemIssues && (
        <Alert className="border-yellow-200 bg-yellow-50">
          <AlertTriangle className="h-4 w-4 text-yellow-600" />
          <AlertTitle className="text-yellow-800">System Status Alert</AlertTitle>
          <AlertDescription className="text-yellow-700">
            Some services are experiencing issues. 
            <Button variant="link" className="p-0 ml-1 text-yellow-800 underline">
              View System Status
            </Button>
          </AlertDescription>
        </Alert>
      )}

      {/* Pending Apps Alert */}
      {stats.pending_apps > 0 && (
        <Alert className="border-blue-200 bg-blue-50">
          <Clock className="h-4 w-4 text-blue-600" />
          <AlertTitle className="text-blue-800">Action Required</AlertTitle>
          <AlertDescription className="text-blue-700">
            There are {stats.pending_apps} app{stats.pending_apps !== 1 ? 's' : ''} waiting for approval.
            <Button variant="link" className="p-0 ml-1 text-blue-800 underline">
              Review Pending Apps
            </Button>
          </AlertDescription>
        </Alert>
      )}

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatsCard
          title="Total Users"
          value={stats.total_users}
          change={{ value: 12, trend: 'up', period: 'last month' }}
          icon={<Users className="h-5 w-5" />}
          gradient="from-blue-500 to-blue-600"
        />
        <StatsCard
          title="Total Apps"
          value={stats.total_apps}
          change={{ value: 8, trend: 'up', period: 'last month' }}
          icon={<Smartphone className="h-5 w-5" />}
          gradient="from-green-500 to-green-600"
        />
        <StatsCard
          title="Pending Apps"
          value={stats.pending_apps}
          icon={<Clock className="h-5 w-5" />}
          gradient="from-yellow-500 to-yellow-600"
        />
        <StatsCard
          title="Total DUST Issued"
          value={`${stats.total_dust_issued.toLocaleString()}`}
          change={{ value: 15, trend: 'up', period: 'last week' }}
          icon={<Sparkles className="h-5 w-5" />}
          gradient="from-purple-500 to-purple-600"
        />
      </div>

      {/* Secondary Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatsCard
          title="Active Today"
          value={stats.active_users_today}
          icon={<Activity className="h-5 w-5" />}
          gradient="from-emerald-500 to-emerald-600"
        />
        <StatsCard
          title="Active This Week"
          value={stats.active_users_week}
          icon={<TrendingUp className="h-5 w-5" />}
          gradient="from-cyan-500 to-cyan-600"
        />
        <StatsCard
          title="Total Transactions"
          value={stats.total_transactions}
          icon={<DollarSign className="h-5 w-5" />}
          gradient="from-orange-500 to-orange-600"
        />
        <StatsCard
          title="LLM Requests"
          value={stats.total_llm_usage}
          icon={<Activity className="h-5 w-5" />}
          gradient="from-pink-500 to-pink-600"
        />
      </div>

      {/* Recent Activity */}
      <RecentActivity recentUsers={recentUsers} recentApps={recentApps} />

      {/* System Health Overview */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center">
            <Activity className="mr-2 h-5 w-5" />
            System Health
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
            {Object.entries(systemHealth).map(([service, status]) => (
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
                  {status}
                </Badge>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}