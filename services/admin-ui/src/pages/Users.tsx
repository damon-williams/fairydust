import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { 
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { 
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { User } from '@/types/admin';
import { Search, Filter, Download, MoreHorizontal } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';

// Mock data
const mockUsers: User[] = [
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
    city: 'San Francisco',
    country: 'USA',
    created_at: '2024-01-15T10:30:00Z',
    updated_at: '2024-01-15T10:30:00Z',
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
    city: 'New York',
    country: 'USA',
    created_at: '2024-01-10T14:20:00Z',
    updated_at: '2024-01-15T09:15:00Z',
  },
  {
    id: '3',
    fairyname: 'mystic_moon_9012',
    phone: '+1234567890',
    is_builder: true,
    is_admin: false,
    is_active: true,
    dust_balance: 89,
    auth_provider: 'phone',
    total_profiling_sessions: 1,
    streak_days: 2,
    city: 'Los Angeles',
    country: 'USA',
    created_at: '2024-01-12T16:45:00Z',
    updated_at: '2024-01-14T11:30:00Z',
  },
];

export function Users() {
  const [users, setUsers] = useState<User[]>(mockUsers);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterType, setFilterType] = useState('all');

  const filteredUsers = users.filter(user => {
    const matchesSearch = user.fairyname.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         user.email?.toLowerCase().includes(searchTerm.toLowerCase());
    
    const matchesFilter = filterType === 'all' ||
                         (filterType === 'builders' && user.is_builder) ||
                         (filterType === 'regular' && !user.is_builder) ||
                         (filterType === 'admins' && user.is_admin);
    
    return matchesSearch && matchesFilter;
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">Users</h1>
          <p className="text-slate-500">Manage user accounts and permissions</p>
        </div>
        <div className="flex space-x-2">
          <Button variant="outline">
            <Download className="mr-2 h-4 w-4" />
            Export
          </Button>
          <Button>
            Add User
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
                  placeholder="Search users..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="pl-10"
                />
              </div>
            </div>
            <Select value={filterType} onValueChange={setFilterType}>
              <SelectTrigger className="w-48">
                <Filter className="mr-2 h-4 w-4" />
                <SelectValue placeholder="Filter by type" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Users</SelectItem>
                <SelectItem value="builders">Builders</SelectItem>
                <SelectItem value="regular">Regular Users</SelectItem>
                <SelectItem value="admins">Administrators</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Users Table */}
      <Card>
        <CardHeader>
          <CardTitle>User Accounts ({filteredUsers.length})</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>User</TableHead>
                <TableHead>Contact</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>DUST Balance</TableHead>
                <TableHead>Location</TableHead>
                <TableHead>Last Active</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredUsers.map((user) => (
                <TableRow key={user.id}>
                  <TableCell>
                    <div className="flex items-center space-x-3">
                      <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-purple-600 rounded-full flex items-center justify-center">
                        <span className="text-sm font-medium text-white">
                          {user.fairyname.charAt(0).toUpperCase()}
                        </span>
                      </div>
                      <div>
                        <div className="font-medium">{user.fairyname}</div>
                        <div className="text-sm text-slate-500">
                          {user.streak_days} day streak
                        </div>
                      </div>
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="text-sm">
                      {user.email || user.phone || 'No contact'}
                    </div>
                    <div className="text-xs text-slate-500 capitalize">
                      {user.auth_provider}
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="flex space-x-1">
                      {user.is_admin && (
                        <Badge variant="destructive" className="text-xs">Admin</Badge>
                      )}
                      {user.is_builder && (
                        <Badge variant="default" className="text-xs">Builder</Badge>
                      )}
                      {!user.is_admin && !user.is_builder && (
                        <Badge variant="secondary" className="text-xs">User</Badge>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="font-medium fairy-dust">
                      {user.dust_balance} DUST
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="text-sm">
                      {user.city && user.country ? `${user.city}, ${user.country}` : 'Unknown'}
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="text-sm text-slate-500">
                      {formatDistanceToNow(new Date(user.updated_at), { addSuffix: true })}
                    </div>
                  </TableCell>
                  <TableCell>
                    <Button variant="ghost" size="sm">
                      <MoreHorizontal className="h-4 w-4" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}