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
  activity_type?: string;
  icon?: string;
  description: string;
  created_at: string;
  fairyname: string;
  first_name: string;
  user_id: string;
  // Alternative format from full activity API
  user?: {
    id: string;
    fairyname: string;
    first_name: string;
    avatar_url?: string;
  };
}

interface RecentDustActivityProps {
  recentActivity?: ActivityItem[];
}

export function RecentDustActivity({ recentActivity }: RecentDustActivityProps) {
  const navigate = useNavigate();

  // Handle case where recentActivity might be undefined
  const activities = recentActivity || [];

  const getActivityTypeColor = (type: string) => {
    switch (type) {
      case 'recipe': return 'bg-orange-100 text-orange-800';
      case 'story': return 'bg-blue-100 text-blue-800';
      case 'activity': return 'bg-green-100 text-green-800';
      case 'restaurant': return 'bg-purple-100 text-purple-800';
      case 'image': return 'bg-pink-100 text-pink-800';
      case 'video': return 'bg-red-100 text-red-800';
      case 'inspiration': return 'bg-yellow-100 text-yellow-800';
      case 'fortune': return 'bg-indigo-100 text-indigo-800';
      case 'wyr': return 'bg-teal-100 text-teal-800';
      case 'grant': return 'bg-emerald-100 text-emerald-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  const getActivityType = (activity: ActivityItem): string => {
    if (activity.activity_type) {
      return activity.activity_type;
    }
    
    // Handle grants vs consumption
    if (activity.type === 'grant' || activity.amount > 0) {
      return 'grant';
    }
    
    // Determine activity type from description for dashboard endpoint
    const description = activity.description.toLowerCase();
    if (description.includes('recipe')) return 'recipe';
    if (description.includes('story')) return 'story';
    if (description.includes('activity') || description.includes('search')) return 'activity';
    if (description.includes('restaurant')) return 'restaurant';
    if (description.includes('image')) return 'image';
    if (description.includes('video')) return 'video';
    if (description.includes('inspiration') || description.includes('inspire')) return 'inspiration';
    if (description.includes('fortune')) return 'fortune';
    if (description.includes('would you rather') || description.includes('wyr')) return 'wyr';
    return 'other';
  };

  const getFairyname = (activity: ActivityItem): string => {
    return activity.user?.fairyname || activity.fairyname || activity.user?.first_name || activity.first_name || 'Unknown User';
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
          {activities.length === 0 ? (
            <p className="text-sm text-slate-500 text-center py-4">
              No recent activity
            </p>
          ) : (
            activities.map((activity) => (
              <div key={activity.id} className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <div>
                    <div className="flex items-center space-x-2">
                      <p 
                        className="text-sm font-medium text-slate-900 hover:text-blue-600 cursor-pointer"
                        onClick={() => navigate(`/admin/users/${activity.user?.id || activity.user_id}/profile`)}
                      >
                        {getFairyname(activity)}
                      </p>
                      <Badge className={`${getActivityTypeColor(getActivityType(activity))} text-xs`}>
                        {getActivityType(activity)}
                      </Badge>
                    </div>
                    <p className="text-xs text-slate-500 truncate max-w-48">
                      {activity.description || 'No description'}
                    </p>
                  </div>
                </div>
                <div className="text-right">
                  <p className={`text-sm font-semibold ${
                    (activity.type === 'grant' || activity.amount > 0) 
                      ? 'text-green-600' 
                      : 'text-red-600'
                  }`}>
                    {(activity.type === 'grant' || activity.amount > 0) ? '+' : ''}
                    {Math.abs(activity.amount || 0)} DUST
                  </p>
                  <p className="text-xs text-slate-500 mt-1">
                    {activity.created_at ? formatDistanceToNow(new Date(activity.created_at), { addSuffix: true }) : 'Unknown time'}
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