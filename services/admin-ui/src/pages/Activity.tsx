import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { 
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Search, Filter, RefreshCw, AlertTriangle, ChevronLeft, ChevronRight, Activity as ActivityIcon } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import { AdminAPI } from '@/lib/admin-api';
import { toast } from 'sonner';
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

export function Activity() {
  const navigate = useNavigate();
  const [activities, setActivities] = useState<ActivityItem[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [activityType, setActivityType] = useState('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalActivities, setTotalActivities] = useState(0);

  const loadActivities = async (page: number = 1, userSearch?: string, type?: string) => {
    try {
      setLoading(true);
      setError(null);
      
      const data = await AdminAPI.getActivity({
        page,
        limit: 50,
        user_search: userSearch,
        activity_type: type !== 'all' ? type : undefined,
      });
      
      setActivities(data.activities);
      setTotalPages(data.pages);
      setTotalActivities(data.total);
    } catch (err) {
      console.error('Failed to load activities:', err);
      setError('Failed to load activities. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadActivities(currentPage, searchTerm || undefined, activityType);
  }, [currentPage, activityType]);

  const handleSearch = () => {
    setCurrentPage(1);
    loadActivities(1, searchTerm || undefined, activityType);
  };

  const handleFilterChange = (newType: string) => {
    setActivityType(newType);
    setCurrentPage(1);
  };

  const getActivityTypeColor = (type: string) => {
    switch (type) {
      case 'recipe': return 'bg-orange-100 text-orange-800';
      case 'story': return 'bg-blue-100 text-blue-800';
      case 'activity': return 'bg-green-100 text-green-800';
      case 'restaurant': return 'bg-purple-100 text-purple-800';
      case 'image': return 'bg-pink-100 text-pink-800';
      case 'inspiration': return 'bg-yellow-100 text-yellow-800';
      case 'fortune': return 'bg-indigo-100 text-indigo-800';
      case 'wyr': return 'bg-teal-100 text-teal-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">Activity Feed</h1>
          <p className="text-slate-500">DUST consumption across all users</p>
        </div>
        <div className="flex space-x-2">
          <Button variant="outline" onClick={() => loadActivities(currentPage, searchTerm || undefined, activityType)}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Refresh
          </Button>
        </div>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex space-x-4">
            <div className="flex-1">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-slate-400 h-4 w-4" />
                <Input
                  placeholder="Search by user name..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                  className="pl-10"
                />
              </div>
            </div>
            <Button onClick={handleSearch}>
              Search
            </Button>
            <Select value={activityType} onValueChange={handleFilterChange}>
              <SelectTrigger className="w-48">
                <Filter className="mr-2 h-4 w-4" />
                <SelectValue placeholder="Filter by type" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Activity</SelectItem>
                <SelectItem value="recipe">🍳 Recipes</SelectItem>
                <SelectItem value="story">📖 Stories</SelectItem>
                <SelectItem value="activity">🎯 Activities</SelectItem>
                <SelectItem value="restaurant">🍽️ Restaurants</SelectItem>
                <SelectItem value="image">🎨 Images</SelectItem>
                <SelectItem value="inspiration">✨ Inspiration</SelectItem>
                <SelectItem value="fortune">🔮 Fortune Teller</SelectItem>
                <SelectItem value="wyr">🤔 Would You Rather</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Activity Feed */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center space-x-2">
            <ActivityIcon className="h-5 w-5" />
            <span>Recent Activity</span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading && (
            <div className="flex items-center justify-center py-8">
              <RefreshCw className="h-6 w-6 animate-spin mr-2" />
              Loading activities...
            </div>
          )}
          
          {error && (
            <Alert variant="destructive" className="mb-4">
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
          
          {!loading && !error && activities.length === 0 && (
            <div className="text-center py-8 text-slate-500">
              No activities found.
            </div>
          )}
          
          {!loading && !error && activities.length > 0 && (
            <div className="space-y-4">
              {activities.map((activity) => (
                <div key={activity.id} className="flex items-center justify-between p-4 border border-slate-200 rounded-lg hover:bg-slate-50">
                  <div className="flex items-center space-x-4">
                    <div>
                      <div className="flex items-center space-x-2">
                        <p 
                          className="text-sm font-medium text-slate-900 hover:text-blue-600 cursor-pointer"
                          onClick={() => navigate(`/admin/users/${activity.user.id}/profile`)}
                        >
                          {activity.user.fairyname}
                        </p>
                        <Badge className={getActivityTypeColor(activity.activity_type)}>
                          {activity.activity_type}
                        </Badge>
                      </div>
                      <p className="text-xs text-slate-500">
                        {activity.description}
                      </p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-semibold text-red-600">
                      {activity.amount} DUST
                    </p>
                    <p className="text-xs text-slate-500">
                      {formatDistanceToNow(new Date(activity.created_at), { addSuffix: true })}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Pagination */}
      {!loading && !error && activities.length > 0 && totalPages > 1 && (
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <p className="text-sm text-slate-600">
                  Showing {((currentPage - 1) * 50) + 1} to {Math.min(currentPage * 50, totalActivities)} of {totalActivities} activities
                </p>
              </div>
              <div className="flex items-center space-x-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setCurrentPage(currentPage - 1)}
                  disabled={currentPage === 1}
                >
                  <ChevronLeft className="h-4 w-4 mr-1" />
                  Previous
                </Button>
                
                <div className="flex items-center space-x-1">
                  {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                    let pageNum;
                    if (totalPages <= 5) {
                      pageNum = i + 1;
                    } else if (currentPage <= 3) {
                      pageNum = i + 1;
                    } else if (currentPage >= totalPages - 2) {
                      pageNum = totalPages - 4 + i;
                    } else {
                      pageNum = currentPage - 2 + i;
                    }
                    
                    return (
                      <Button
                        key={pageNum}
                        variant={currentPage === pageNum ? "default" : "outline"}
                        size="sm"
                        onClick={() => setCurrentPage(pageNum)}
                        className="w-8 h-8 p-0"
                      >
                        {pageNum}
                      </Button>
                    );
                  })}
                </div>
                
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setCurrentPage(currentPage + 1)}
                  disabled={currentPage === totalPages}
                >
                  Next
                  <ChevronRight className="h-4 w-4 ml-1" />
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}