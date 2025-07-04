import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { User, App } from '@/types/admin';
import { formatDistanceToNow } from 'date-fns';
import { ArrowRight } from 'lucide-react';

interface RecentActivityProps {
  recentUsers: User[];
  recentApps: App[];
}

export function RecentActivity({ recentUsers, recentApps }: RecentActivityProps) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* Recent Users */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-lg font-semibold">Recent Users</CardTitle>
          <Button variant="outline" size="sm">
            View All
            <ArrowRight className="ml-2 h-4 w-4" />
          </Button>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {recentUsers.map((user) => (
              <div key={user.id} className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-purple-600 rounded-full flex items-center justify-center">
                    <span className="text-sm font-medium text-white">
                      {user.fairyname.charAt(0).toUpperCase()}
                    </span>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-slate-900">
                      {user.fairyname}
                    </p>
                    <p className="text-xs text-slate-500">
                      {user.email || 'Phone user'}
                    </p>
                  </div>
                </div>
                <div className="text-right">
                  <div className="flex items-center space-x-2">
                    <Badge variant={user.is_admin ? 'destructive' : 'secondary'} className="text-xs">
                      {user.is_admin ? 'Admin' : 'User'}
                    </Badge>
                  </div>
                  <p className="text-xs text-slate-500 mt-1">
                    {formatDistanceToNow(new Date(user.created_at), { addSuffix: true })}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Recent Apps */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-lg font-semibold">Recent Apps</CardTitle>
          <Button variant="outline" size="sm">
            View All
            <ArrowRight className="ml-2 h-4 w-4" />
          </Button>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {recentApps.map((app) => (
              <div key={app.id} className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <div className="w-8 h-8 bg-gradient-to-br from-green-500 to-blue-600 rounded-full flex items-center justify-center">
                    <span className="text-sm font-medium text-white">
                      {app.name.charAt(0).toUpperCase()}
                    </span>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-slate-900">
                      {app.name}
                    </p>
                    <p className="text-xs text-slate-500">
                      by {app.builder_name}
                    </p>
                  </div>
                </div>
                <div className="text-right">
                  <Badge 
                    variant={
                      app.status === 'approved' ? 'default' :
                      app.status === 'pending' ? 'secondary' :
                      'destructive'
                    }
                    className="text-xs"
                  >
                    {app.status}
                  </Badge>
                  <p className="text-xs text-slate-500 mt-1">
                    {formatDistanceToNow(new Date(app.created_at), { addSuffix: true })}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}