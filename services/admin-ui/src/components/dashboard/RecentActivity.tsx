import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { User } from '@/types/admin';
import { formatDistanceToNow } from 'date-fns';
import { ArrowRight } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

interface RecentActivityProps {
  recentUsers: User[];
}

export function RecentActivity({ recentUsers }: RecentActivityProps) {
  const navigate = useNavigate();

  return (
    <div className="grid grid-cols-1 gap-6">
      {/* Recent Users */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-lg font-semibold">Recent Users</CardTitle>
          <Button 
            variant="outline" 
            size="sm"
            onClick={() => navigate('/admin/users')}
          >
            View All
            <ArrowRight className="ml-2 h-4 w-4" />
          </Button>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {recentUsers.map((user) => (
              <div key={user.id} className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <div>
                    <p 
                      className="text-sm font-medium text-slate-900 hover:text-blue-600 cursor-pointer"
                      onClick={() => navigate(`/admin/users/${user.id}`)}
                    >
                      {user.fairyname}
                    </p>
                    <p className="text-xs text-slate-500">
                      {user.email || 'Phone user'}
                    </p>
                  </div>
                </div>
                <div className="text-right">
                  <div className="flex items-center space-x-2">
                    {user.is_admin && (
                      <Badge variant="destructive" className="text-xs">
                        Admin
                      </Badge>
                    )}
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
    </div>
  );
}