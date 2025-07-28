import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { adminApi } from '../lib/admin-api';
import { useToast } from '../components/ui/sonner';

interface PaymentTransaction {
  id: string;
  user_id: string;
  amount: number;
  type: string;
  status: string;
  description: string;
  payment_id?: string;
  receipt_verification_status?: string;
  apple_transaction_id?: string;
  apple_product_id?: string;
  apple_purchase_date_ms?: number;
  payment_amount_cents?: number;
  created_at: string;
  metadata?: any;
}

interface PaymentStats {
  total_transactions: number;
  total_revenue_cents: number;
  successful_purchases: number;
  failed_verifications: number;
  apple_transactions: number;
}

export default function Payments() {
  const [transactions, setTransactions] = useState<PaymentTransaction[]>([]);
  const [stats, setStats] = useState<PaymentStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchUserId, setSearchUserId] = useState('');
  const [filterStatus, setFilterStatus] = useState('all');
  const [filterPlatform, setFilterPlatform] = useState('all');
  const { toast } = useToast();

  useEffect(() => {
    fetchPaymentData();
  }, [filterStatus, filterPlatform, searchUserId]);

  const fetchPaymentData = async () => {
    try {
      setLoading(true);
      
      // Fetch payment transactions
      const params = new URLSearchParams();
      if (searchUserId) params.append('user_id', searchUserId);
      if (filterStatus !== 'all') params.append('status', filterStatus);
      if (filterPlatform !== 'all') params.append('platform', filterPlatform);
      
      const transactionsResponse = await adminApi.get(`/payments/transactions?${params}`);
      setTransactions(transactionsResponse.transactions || []);
      
      // Fetch payment stats
      const statsResponse = await adminApi.get('/payments/stats');
      setStats(statsResponse);
      
    } catch (error) {
      console.error('Error fetching payment data:', error);
      toast({
        title: 'Error',
        description: 'Failed to fetch payment data',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  const getStatusBadge = (status: string, verificationStatus?: string) => {
    if (status === 'completed' && verificationStatus === 'verified') {
      return <Badge variant="default" className="bg-green-600">Verified</Badge>;
    } else if (status === 'completed' && !verificationStatus) {
      return <Badge variant="secondary">Completed</Badge>;
    } else if (verificationStatus === 'failed') {
      return <Badge variant="destructive">Failed Verification</Badge>;
    } else {
      return <Badge variant="outline">{status}</Badge>;
    }
  };

  const getPlatformBadge = (transaction: PaymentTransaction) => {
    if (transaction.apple_transaction_id) {
      return <Badge variant="outline" className="bg-gray-100">🍎 iOS</Badge>;
    } else if (transaction.payment_id?.includes('android')) {
      return <Badge variant="outline" className="bg-green-100">🤖 Android</Badge>;
    } else if (transaction.payment_id?.includes('stripe')) {
      return <Badge variant="outline" className="bg-purple-100">💳 Stripe</Badge>;
    }
    return <Badge variant="outline">Other</Badge>;
  };

  const formatCurrency = (cents?: number) => {
    if (!cents) return 'N/A';
    return `$${(cents / 100).toFixed(2)}`;
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleString();
  };

  const formatAppleDate = (timestampMs?: number) => {
    if (!timestampMs) return 'N/A';
    return new Date(timestampMs).toLocaleString();
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-3xl font-bold">Payment Management</h1>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          {[1, 2, 3, 4].map((i) => (
            <Card key={i}>
              <CardHeader className="animate-pulse">
                <div className="h-4 bg-gray-200 rounded w-3/4"></div>
                <div className="h-8 bg-gray-200 rounded w-1/2"></div>
              </CardHeader>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Payment Management</h1>
        <Button onClick={fetchPaymentData} variant="outline">
          Refresh Data
        </Button>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Total Transactions</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.total_transactions}</div>
            </CardContent>
          </Card>
          
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Total Revenue</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{formatCurrency(stats.total_revenue_cents)}</div>
            </CardContent>
          </Card>
          
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Successful Purchases</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-green-600">{stats.successful_purchases}</div>
            </CardContent>
          </Card>
          
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Failed Verifications</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-red-600">{stats.failed_verifications}</div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Filters */}
      <Card>
        <CardHeader>
          <CardTitle>Filters</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="text-sm font-medium mb-2 block">User ID</label>
              <Input
                placeholder="Search by user ID..."
                value={searchUserId}
                onChange={(e) => setSearchUserId(e.target.value)}
              />
            </div>
            
            <div>
              <label className="text-sm font-medium mb-2 block">Status</label>
              <Select value={filterStatus} onValueChange={setFilterStatus}>
                <SelectTrigger>
                  <SelectValue placeholder="All statuses" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Statuses</SelectItem>
                  <SelectItem value="completed">Completed</SelectItem>
                  <SelectItem value="pending">Pending</SelectItem>
                  <SelectItem value="failed">Failed</SelectItem>
                </SelectContent>
              </Select>
            </div>
            
            <div>
              <label className="text-sm font-medium mb-2 block">Platform</label>
              <Select value={filterPlatform} onValueChange={setFilterPlatform}>
                <SelectTrigger>
                  <SelectValue placeholder="All platforms" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Platforms</SelectItem>
                  <SelectItem value="ios">iOS</SelectItem>
                  <SelectItem value="android">Android</SelectItem>
                  <SelectItem value="stripe">Stripe</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Transactions Table */}
      <Card>
        <CardHeader>
          <CardTitle>Recent Transactions</CardTitle>
          <CardDescription>
            Payment transactions with receipt verification status
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>User ID</TableHead>
                <TableHead>Platform</TableHead>
                <TableHead>Product</TableHead>
                <TableHead>Amount</TableHead>
                <TableHead>Revenue</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Apple Transaction</TableHead>
                <TableHead>Purchase Date</TableHead>
                <TableHead>Created</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {transactions.map((transaction) => (
                <TableRow key={transaction.id}>
                  <TableCell className="font-mono text-xs">
                    {transaction.user_id.substring(0, 8)}...
                  </TableCell>
                  <TableCell>{getPlatformBadge(transaction)}</TableCell>
                  <TableCell>
                    <div>
                      <div className="font-medium">{transaction.apple_product_id || 'N/A'}</div>
                      <div className="text-xs text-gray-500">{transaction.amount} DUST</div>
                    </div>
                  </TableCell>
                  <TableCell>{transaction.amount} DUST</TableCell>
                  <TableCell>{formatCurrency(transaction.payment_amount_cents)}</TableCell>
                  <TableCell>
                    {getStatusBadge(transaction.status, transaction.receipt_verification_status)}
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {transaction.apple_transaction_id ? 
                      `${transaction.apple_transaction_id.substring(0, 12)}...` : 
                      'N/A'
                    }
                  </TableCell>
                  <TableCell className="text-xs">
                    {formatAppleDate(transaction.apple_purchase_date_ms)}
                  </TableCell>
                  <TableCell className="text-xs">
                    {formatDate(transaction.created_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          
          {transactions.length === 0 && (
            <div className="text-center py-8 text-gray-500">
              No payment transactions found
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}