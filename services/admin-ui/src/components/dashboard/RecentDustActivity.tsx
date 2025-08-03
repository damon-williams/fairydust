import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { formatDistanceToNow } from 'date-fns';
import { ArrowRight, Activity } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

interface ActivityItem {
  id: string;
  amount: number;
  type: string;
  activity_type: string;
  icon: string;
  description: string;
  created_at: string;
  user: {
    id: string;
    fairyname: string;
    first_name: string;
    avatar_url?: string;
  };
}

interface RecentDustActivityProps {
  recentActivity: ActivityItem[];
}

export function RecentDustActivity({ recentActivity }: RecentDustActivityProps) {
  const navigate = useNavigate();

  const getActivityTypeColor = (type: string) => {
    switch (type) {
      case 'recipe': return 'bg-orange-100 text-orange-800';
      case 'story': return 'bg-blue-100 text-blue-800';
      case 'activity': return 'bg-green-100 text-green-800';
      case 'restaurant': return 'bg-purple-100 text-purple-800';
      case 'image': return 'bg-pink-100 text-pink-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-lg font-semibold flex items-center space-x-2">
          <Activity className="h-5 w-5" />
          <span>Recent Activity</span>
        </CardTitle>
        <Button 
          variant="outline" 
          size="sm"
          onClick={() => navigate('/admin/activity')}
        >
          View All
          <ArrowRight className="ml-2 h-4 w-4" />
        </Button>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {recentActivity.length === 0 ? (
            <p className="text-sm text-slate-500 text-center py-4">
              No recent activity
            </p>
          ) : (
            recentActivity.map((activity) => (
              <div key={activity.id} className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <div className="w-8 h-8 bg-gradient-to-br from-orange-500 to-red-600 rounded-full flex items-center justify-center">
                    <span className="text-sm">{activity.icon}</span>
                  </div>
                  <div className="flex items-center space-x-2">
                    <div className="w-6 h-6 bg-gradient-to-br from-green-500 to-blue-600 rounded-full flex items-center justify-center">
                      <span className="text-xs font-medium text-white">
                        {(activity.user.first_name || activity.user.fairyname).charAt(0).toUpperCase()}
                      </span>
                    </div>
                    <div>
                      <div className="flex items-center space-x-2">
                        <p className="text-sm font-medium text-slate-900">
                          {activity.user.first_name || activity.user.fairyname}
                        </p>
                        <Badge className={`${getActivityTypeColor(activity.activity_type)} text-xs`}>
                          {activity.activity_type}
                        </Badge>
                      </div>
                      <p className="text-xs text-slate-500 truncate max-w-48">
                        {activity.description}
                      </p>
                    </div>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-sm font-semibold text-red-600">
                    -{activity.amount} DUST
                  </p>
                  <p className="text-xs text-slate-500 mt-1">
                    {formatDistanceToNow(new Date(activity.created_at), { addSuffix: true })}
                  </p>
                </div>
              </div>
            ))
          )}
        </div>
      </CardContent>
    </Card>
  );
}