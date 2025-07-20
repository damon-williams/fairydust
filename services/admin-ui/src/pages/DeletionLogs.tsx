import { useState, useEffect, useCallback } from 'react';
import { AdminAPI } from '@/lib/admin-api';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { format } from 'date-fns';
import { Search, ChevronLeft, ChevronRight, User, Calendar, MessageSquare, Trash2 } from 'lucide-react';

interface DeletionLog {
  id: string;
  user_id: string;
  fairyname: string;
  email: string;
  deletion_reason: string;
  deletion_feedback: string;
  deleted_by: string;
  deleted_by_user_id?: string;
  user_created_at: string;
  deletion_requested_at: string;
  deletion_completed_at?: string;
  data_summary: {
    dust_balance?: number;
    account_age_days?: number;
    recipes_created?: number;
    stories_created?: number;
    images_generated?: number;
    people_in_life?: number;
    total_transactions?: number;
    storage_cleanup?: {
      total_deleted: number;
      avatars_deleted: number;
      people_photos_deleted: number;
      generated_images_deleted: number;
    };
  };
}

export default function DeletionLogs() {
  const [logs, setLogs] = useState<DeletionLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [renderError, setRenderError] = useState<string | null>(null);
  const [pagination, setPagination] = useState({
    total: 0,
    limit: 25,
    offset: 0,
    has_more: false
  });
  const [filters, setFilters] = useState({
    deleted_by: 'all',
    reason: 'all_reasons'
  });

  const fetchDeletionLogs = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      console.log('Fetching deletion logs with params:', {
        limit: pagination.limit,
        offset: pagination.offset,
        deleted_by: filters.deleted_by,
        reason: filters.reason
      });
      
      const response = await AdminAPI.getDeletionLogs({
        limit: pagination.limit,
        offset: pagination.offset,
        deleted_by: (filters.deleted_by === 'all' ? undefined : filters.deleted_by as 'self' | 'admin'),
        reason: (filters.reason === 'all_reasons' ? undefined : filters.reason)
      });
      
      console.log('Deletion logs response:', response);
      setLogs(response.deletion_logs);
      setPagination(response.pagination);
    } catch (error) {
      console.error('Failed to fetch deletion logs:', error);
      setError(error instanceof Error ? error.message : 'Failed to load deletion logs');
    } finally {
      setLoading(false);
    }
  }, [pagination.limit, pagination.offset, filters.deleted_by, filters.reason]);

  useEffect(() => {
    fetchDeletionLogs();
  }, [fetchDeletionLogs]);

  const handleFilterChange = (key: string, value: string) => {
    setFilters(prev => ({ ...prev, [key]: value }));
    setPagination(prev => ({ ...prev, offset: 0 })); // Reset to first page
  };

  const nextPage = () => {
    setPagination(prev => ({ ...prev, offset: prev.offset + prev.limit }));
  };

  const prevPage = () => {
    setPagination(prev => ({ ...prev, offset: Math.max(0, prev.offset - prev.limit) }));
  };

  const formatReason = (reason: string) => {
    const reasonMap: Record<string, string> = {
      'not_using_anymore': 'Not Using Anymore',
      'privacy_concerns': 'Privacy Concerns',
      'too_expensive': 'Too Expensive',
      'switching_platform': 'Switching Platform',
      'other': 'Other'
    };
    return reasonMap[reason] || reason;
  };

  const getReasonColor = (reason: string) => {
    const colorMap: Record<string, string> = {
      'not_using_anymore': 'bg-blue-100 text-blue-800',
      'privacy_concerns': 'bg-red-100 text-red-800',
      'too_expensive': 'bg-orange-100 text-orange-800',
      'switching_platform': 'bg-purple-100 text-purple-800',
      'other': 'bg-gray-100 text-gray-800'
    };
    return colorMap[reason] || 'bg-gray-100 text-gray-800';
  };

  if (renderError) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold">Account Deletion Logs</h1>
          <p className="text-muted-foreground">
            View and analyze account deletion history for compliance and insights
          </p>
        </div>
        <div className="flex items-center justify-center h-64">
          <div className="text-center">
            <p className="text-red-600 mb-4">Render Error: {renderError}</p>
            <button 
              onClick={() => window.location.reload()} 
              className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
            >
              Reload Page
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-muted-foreground">Loading deletion logs...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold">Account Deletion Logs</h1>
          <p className="text-muted-foreground">
            View and analyze account deletion history for compliance and insights
          </p>
        </div>
        <div className="flex items-center justify-center h-64">
          <div className="text-center">
            <p className="text-red-600 mb-4">Error: {error}</p>
            <button 
              onClick={fetchDeletionLogs} 
              className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
            >
              Try Again
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Account Deletion Logs</h1>
        <p className="text-muted-foreground">
          View and analyze account deletion history for compliance and insights
        </p>
      </div>

      {/* Filters */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Search className="h-5 w-5" />
            Filters
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex gap-4">
            <div className="flex-1">
              <label className="text-sm font-medium">Deleted By</label>
              <Select value={filters.deleted_by} onValueChange={(value) => handleFilterChange('deleted_by', value)}>
                <SelectTrigger>
                  <SelectValue placeholder="All" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All</SelectItem>
                  <SelectItem value="self">Self</SelectItem>
                  <SelectItem value="admin">Admin</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex-1">
              <label className="text-sm font-medium">Reason</label>
              <Select value={filters.reason} onValueChange={(value) => handleFilterChange('reason', value)}>
                <SelectTrigger>
                  <SelectValue placeholder="All reasons" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all_reasons">All Reasons</SelectItem>
                  <SelectItem value="not_using_anymore">Not Using Anymore</SelectItem>
                  <SelectItem value="privacy_concerns">Privacy Concerns</SelectItem>
                  <SelectItem value="too_expensive">Too Expensive</SelectItem>
                  <SelectItem value="switching_platform">Switching Platform</SelectItem>
                  <SelectItem value="other">Other</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Results */}
      <Card>
        <CardHeader>
          <CardTitle>Deletion Records ({pagination.total} total)</CardTitle>
          <CardDescription>
            Account deletions with detailed audit information
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {logs.map((log) => (
              <div key={log.id} className="border rounded-lg p-4 space-y-3">
                <div className="flex items-start justify-between">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <User className="h-4 w-4 text-muted-foreground" />
                      <span className="font-medium">{log.fairyname}</span>
                      <span className="text-muted-foreground">({log.email})</span>
                      <Badge variant={log.deleted_by === 'self' ? 'default' : 'destructive'}>
                        {log.deleted_by === 'self' ? 'Self-deleted' : 'Admin-deleted'}
                      </Badge>
                    </div>
                    <div className="flex items-center gap-4 text-sm text-muted-foreground">
                      <span className="flex items-center gap-1">
                        <Calendar className="h-3 w-3" />
                        {(() => {
                          try {
                            return format(new Date(log.deletion_requested_at), 'MMM d, yyyy HH:mm');
                          } catch (e) {
                            return new Date(log.deletion_requested_at).toLocaleDateString();
                          }
                        })()}
                      </span>
                      <span>Account age: {log.data_summary.account_age_days || 0} days</span>
                    </div>
                  </div>
                  <Badge className={getReasonColor(log.deletion_reason)}>
                    {formatReason(log.deletion_reason)}
                  </Badge>
                </div>

                {log.deletion_feedback && (
                  <div className="flex items-start gap-2 text-sm">
                    <MessageSquare className="h-4 w-4 text-muted-foreground mt-0.5" />
                    <span className="text-muted-foreground italic">"{log.deletion_feedback}"</span>
                  </div>
                )}

                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                  <div>
                    <span className="text-muted-foreground">DUST Balance:</span>
                    <div className="font-medium">{log.data_summary.dust_balance || 0}</div>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Content Created:</span>
                    <div className="font-medium">
                      {(log.data_summary.recipes_created || 0) + 
                       (log.data_summary.stories_created || 0) + 
                       (log.data_summary.images_generated || 0)}
                    </div>
                  </div>
                  <div>
                    <span className="text-muted-foreground">People in Life:</span>
                    <div className="font-medium">{log.data_summary.people_in_life || 0}</div>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Transactions:</span>
                    <div className="font-medium">{log.data_summary.total_transactions || 0}</div>
                  </div>
                </div>

                {log.data_summary.storage_cleanup && (
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Trash2 className="h-4 w-4" />
                    <span>
                      Storage cleaned: {log.data_summary.storage_cleanup.total_deleted} files
                      ({log.data_summary.storage_cleanup.avatars_deleted} avatars, {' '}
                      {log.data_summary.storage_cleanup.people_photos_deleted} photos, {' '}
                      {log.data_summary.storage_cleanup.generated_images_deleted} images)
                    </span>
                  </div>
                )}

              </div>
            ))}

            {logs.length === 0 && (
              <div className="text-center py-8 text-muted-foreground">
                No deletion logs found matching your filters.
              </div>
            )}
          </div>

          {/* Pagination */}
          {pagination.total > pagination.limit && (
            <div className="flex items-center justify-between mt-6">
              <div className="text-sm text-muted-foreground">
                Showing {pagination.offset + 1} to {Math.min(pagination.offset + pagination.limit, pagination.total)} of {pagination.total} entries
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={prevPage}
                  disabled={pagination.offset === 0}
                >
                  <ChevronLeft className="h-4 w-4" />
                  Previous
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={nextPage}
                  disabled={!pagination.has_more}
                >
                  Next
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}