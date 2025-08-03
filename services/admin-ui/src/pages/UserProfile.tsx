import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { ArrowLeft, User as UserIcon, RefreshCw, AlertTriangle } from 'lucide-react';
import { User } from '@/types/admin';
import { AdminAPI } from '@/lib/admin-api';
import { formatDistanceToNow } from 'date-fns';
import { toast } from 'sonner';

export function UserProfile() {
  const { userId } = useParams<{ userId: string }>();
  const navigate = useNavigate();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadUserData = async () => {
    if (!userId) return;
    
    try {
      setLoading(true);
      setError(null);
      
      // For now, we'll get user data from the users list API
      // In the future, you might want to create a specific getUserById API
      const data = await AdminAPI.getUsers(1, 1000); // Get all users and find the one we need
      const foundUser = data.users.find(u => u.id === userId);
      
      if (!foundUser) {
        setError('User not found');
        return;
      }
      
      setUser(foundUser);
    } catch (err) {
      console.error('Failed to load user:', err);
      setError('Failed to load user data. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadUserData();
  }, [userId]);

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center space-x-4">
          <Button variant="ghost" onClick={() => navigate('/admin/users')}>
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back to Users
          </Button>
        </div>
        <div className="flex items-center justify-center py-8">
          <RefreshCw className="h-6 w-6 animate-spin mr-2" />
          Loading user profile...
        </div>
      </div>
    );
  }

  if (error || !user) {
    return (
      <div className="space-y-6">
        <div className="flex items-center space-x-4">
          <Button variant="ghost" onClick={() => navigate('/admin/users')}>
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back to Users
          </Button>
        </div>
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>{error || 'User not found'}</AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <Button variant="ghost" onClick={() => navigate('/admin/users')}>
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back to Users
          </Button>
          <div>
            <h1 className="text-3xl font-bold text-slate-900">User Profile</h1>
            <p className="text-slate-500">Detailed information for {user.first_name || user.fairyname}</p>
          </div>
        </div>
        <Button variant="outline" onClick={loadUserData}>
          <RefreshCw className="h-4 w-4 mr-2" />
          Refresh
        </Button>
      </div>

      {/* User Basic Info */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card className="md:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center space-x-2">
              <UserIcon className="h-5 w-5" />
              <span>User Information</span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center space-x-4">
              <div className="w-16 h-16 bg-gradient-to-br from-blue-500 to-purple-600 rounded-full flex items-center justify-center">
                <span className="text-xl font-medium text-white">
                  {(user.first_name || user.fairyname).charAt(0).toUpperCase()}
                </span>
              </div>
              <div>
                <div className="flex items-center space-x-2">
                  <h2 className="text-xl font-semibold">{user.first_name || 'No name provided'}</h2>
                  {user.is_admin && (
                    <Badge variant="destructive">Admin</Badge>
                  )}
                </div>
                <p className="text-slate-500">@{user.fairyname}</p>
              </div>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="text-sm font-medium text-slate-600">Email</label>
                <p className="text-slate-900">{user.email || 'No email provided'}</p>
              </div>
              <div>
                <label className="text-sm font-medium text-slate-600">Phone</label>
                <p className="text-slate-900">{user.phone || 'No phone provided'}</p>
              </div>
              <div>
                <label className="text-sm font-medium text-slate-600">Auth Provider</label>
                <p className="text-slate-900 capitalize">{user.auth_provider || 'Unknown'}</p>
              </div>
              <div>
                <label className="text-sm font-medium text-slate-600">Birth Date</label>
                <p className="text-slate-900">{user.birth_date || 'Not provided'}</p>
              </div>
              <div>
                <label className="text-sm font-medium text-slate-600">Member Since</label>
                <p className="text-slate-900">{new Date(user.created_at).toLocaleDateString()}</p>
              </div>
              <div>
                <label className="text-sm font-medium text-slate-600">Last Updated</label>
                <p className="text-slate-900">{formatDistanceToNow(new Date(user.updated_at), { addSuffix: true })}</p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Quick Stats */}
        <Card>
          <CardHeader>
            <CardTitle>Quick Stats</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <label className="text-sm font-medium text-slate-600">DUST Balance</label>
              <p className="text-2xl font-bold text-slate-900">{user.dust_balance}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-slate-600">Onboarding</label>
              <p className="text-slate-900">
                {user.is_onboarding_completed ? (
                  <Badge variant="secondary">Completed</Badge>
                ) : (
                  <Badge variant="outline">In Progress</Badge>
                )}
              </p>
            </div>
            <div>
              <label className="text-sm font-medium text-slate-600">Account Type</label>
              <p className="text-slate-900">
                {user.is_admin ? (
                  <Badge variant="destructive">Administrator</Badge>
                ) : (
                  <Badge variant="secondary">Regular User</Badge>
                )}
              </p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Future sections - these would be implemented with additional API calls */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle>People in My Life</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-slate-500 text-center py-8">
              Coming soon - will show user's added people and pets
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>App Usage</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-slate-500 text-center py-8">
              Coming soon - will show which apps they've used
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Generated Content</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-slate-500 text-center py-8">
              Coming soon - will show stories, recipes, and images created
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>DUST Transactions</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-slate-500 text-center py-8">
              Coming soon - will show transaction history
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}