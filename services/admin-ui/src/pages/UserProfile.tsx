import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { 
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { ArrowLeft, User as UserIcon, RefreshCw, AlertTriangle, Users, FileText, DollarSign, Heart, PawPrint, CreditCard } from 'lucide-react';
import { User } from '@/types/admin';
import { AdminAPI } from '@/lib/admin-api';
import { formatDistanceToNow } from 'date-fns';
import { toast } from 'sonner';

interface PersonInLife {
  id: string;
  name: string;
  entry_type: 'person' | 'pet';
  relationship?: string;
  species?: string;
  birth_date?: string;
  created_at: string;
}


interface GeneratedContent {
  id: string;
  type: 'recipe' | 'story' | 'activity';
  title: string;
  created_at: string;
  dust_cost: number;
}

interface DustTransaction {
  id: string;
  amount: number;
  transaction_type: 'grant' | 'spend' | 'refund';
  description: string;
  created_at: string;
}

interface Payment {
  id: string;
  payment_method: string;
  amount_usd: number;
  dust_amount: number;
  status: string;
  transaction_id?: string;
  created_at: string;
  completed_at?: string;
}

export function UserProfile() {
  const { userId } = useParams<{ userId: string }>();
  const navigate = useNavigate();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Data states
  const [people, setPeople] = useState<PersonInLife[]>([]);
  const [generatedContent, setGeneratedContent] = useState<GeneratedContent[]>([]);
  const [dustTransactions, setDustTransactions] = useState<DustTransaction[]>([]);
  const [payments, setPayments] = useState<Payment[]>([]);
  
  // Loading states
  const [peopleLoading, setPeopleLoading] = useState(true);
  const [contentLoading, setContentLoading] = useState(true);
  const [transactionsLoading, setTransactionsLoading] = useState(true);
  const [paymentsLoading, setPaymentsLoading] = useState(true);
  
  // Grant DUST dialog state
  const [grantDialogOpen, setGrantDialogOpen] = useState(false);
  const [grantAmount, setGrantAmount] = useState('');
  const [grantReason, setGrantReason] = useState('');
  const [granting, setGranting] = useState(false);

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

  const loadPeopleData = async () => {
    if (!userId) return;
    
    try {
      setPeopleLoading(true);
      const data = await AdminAPI.getUserPeople(userId);
      setPeople(data);
    } catch (err) {
      console.error('Failed to load people:', err);
    } finally {
      setPeopleLoading(false);
    }
  };


  const loadGeneratedContentData = async () => {
    if (!userId) return;
    
    try {
      setContentLoading(true);
      const data = await AdminAPI.getUserGeneratedContent(userId, 10);
      setGeneratedContent(data);
    } catch (err) {
      console.error('Failed to load generated content:', err);
    } finally {
      setContentLoading(false);
    }
  };

  const loadDustTransactionData = async () => {
    if (!userId) return;
    
    try {
      setTransactionsLoading(true);
      const data = await AdminAPI.getUserDustTransactions(userId, 20);
      setDustTransactions(data);
    } catch (err) {
      console.error('Failed to load transactions:', err);
    } finally {
      setTransactionsLoading(false);
    }
  };

  const loadPaymentsData = async () => {
    if (!userId) return;
    
    try {
      setPaymentsLoading(true);
      const data = await AdminAPI.getUserPayments(userId, 20);
      setPayments(data);
    } catch (err) {
      console.error('Failed to load payments:', err);
    } finally {
      setPaymentsLoading(false);
    }
  };

  const handleGrantDust = async () => {
    if (!user || !grantAmount || !grantReason) {
      toast.error('Please fill in all fields');
      return;
    }

    const amount = parseInt(grantAmount);
    if (isNaN(amount) || amount <= 0) {
      toast.error('Please enter a valid amount');
      return;
    }

    try {
      setGranting(true);
      await AdminAPI.grantDust(user.id, amount, grantReason);
      toast.success(`Granted ${amount} DUST to ${user.fairyname}`);
      
      // Reset form and close dialog
      setGrantDialogOpen(false);
      setGrantAmount('');
      setGrantReason('');
      
      // Reload user data, transactions and payments
      loadUserData();
      loadDustTransactionData();
      loadPaymentsData();
    } catch (err) {
      toast.error('Failed to grant DUST');
    } finally {
      setGranting(false);
    }
  };

  useEffect(() => {
    loadUserData();
    loadPeopleData();
    loadGeneratedContentData();
    loadDustTransactionData();
    loadPaymentsData();
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
            <Button 
              variant="outline"
              className="w-full"
              onClick={() => setGrantDialogOpen(true)}
            >
              Grant DUST
            </Button>
          </CardContent>
        </Card>
      </div>

      {/* Data sections */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* People in My Life */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center space-x-2">
              <Users className="h-5 w-5" />
              <span>People in My Life</span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {peopleLoading ? (
              <div className="flex items-center justify-center py-8">
                <RefreshCw className="h-4 w-4 animate-spin mr-2" />
                Loading...
              </div>
            ) : people.length === 0 ? (
              <p className="text-slate-500 text-center py-8">
                No people or pets added yet
              </p>
            ) : (
              <div className="space-y-3">
                {people.map((person) => (
                  <div key={person.id} className="flex items-center justify-between">
                    <div className="flex items-center space-x-3">
                      <div className="w-8 h-8 bg-gradient-to-br from-green-500 to-blue-600 rounded-full flex items-center justify-center">
                        {person.entry_type === 'pet' ? (
                          <PawPrint className="h-4 w-4 text-white" />
                        ) : (
                          <Heart className="h-4 w-4 text-white" />
                        )}
                      </div>
                      <div>
                        <p className="text-sm font-medium">{person.name}</p>
                        <p className="text-xs text-slate-500">
                          {person.entry_type === 'pet' ? person.species : person.relationship}
                        </p>
                      </div>
                    </div>
                    <p className="text-xs text-slate-500">
                      {formatDistanceToNow(new Date(person.created_at), { addSuffix: true })}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Generated Content */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center space-x-2">
              <FileText className="h-5 w-5" />
              <span>Generated Content</span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {contentLoading ? (
              <div className="flex items-center justify-center py-8">
                <RefreshCw className="h-4 w-4 animate-spin mr-2" />
                Loading...
              </div>
            ) : generatedContent.length === 0 ? (
              <p className="text-slate-500 text-center py-8">
                No content generated yet
              </p>
            ) : (
              <div className="space-y-3">
                {generatedContent.map((content) => (
                  <div key={content.id} className="flex items-center justify-between">
                    <div className="flex items-center space-x-3">
                      <Badge variant="outline" className="text-xs">
                        {content.type}
                      </Badge>
                      <div>
                        <p className="text-sm font-medium">{content.title}</p>
                        <p className="text-xs text-slate-500">
                          Created content
                        </p>
                      </div>
                    </div>
                    <p className="text-xs text-slate-500">
                      {formatDistanceToNow(new Date(content.created_at), { addSuffix: true })}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* DUST Transactions */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center space-x-2">
              <DollarSign className="h-5 w-5" />
              <span>DUST Transactions</span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {transactionsLoading ? (
              <div className="flex items-center justify-center py-8">
                <RefreshCw className="h-4 w-4 animate-spin mr-2" />
                Loading...
              </div>
            ) : dustTransactions.length === 0 ? (
              <p className="text-slate-500 text-center py-8">
                No transactions yet
              </p>
            ) : (
              <div className="space-y-3">
                {dustTransactions.map((transaction) => (
                  <div key={transaction.id} className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium">{transaction.description}</p>
                      <p className="text-xs text-slate-500 capitalize">
                        {transaction.transaction_type}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className={`text-sm font-medium ${
                        transaction.amount > 0 ? 'text-green-600' : 'text-red-600'
                      }`}>
                        {transaction.amount > 0 ? '+' : ''}{transaction.amount} DUST
                      </p>
                      <p className="text-xs text-slate-500">
                        {formatDistanceToNow(new Date(transaction.created_at), { addSuffix: true })}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Payments */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center space-x-2">
              <CreditCard className="h-5 w-5" />
              <span>Payments</span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {paymentsLoading ? (
              <div className="flex items-center justify-center py-8">
                <RefreshCw className="h-4 w-4 animate-spin mr-2" />
                Loading...
              </div>
            ) : payments.length === 0 ? (
              <p className="text-slate-500 text-center py-8">
                No payments yet
              </p>
            ) : (
              <div className="space-y-3">
                {payments.map((payment) => (
                  <div key={payment.id} className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium">
                        ${payment.amount_usd.toFixed(2)} → {payment.dust_amount} DUST
                      </p>
                      <p className="text-xs text-slate-500">
                        {payment.payment_method} • {payment.status}
                      </p>
                    </div>
                    <div className="text-right">
                      <Badge 
                        variant={payment.status === 'completed' ? 'secondary' : 
                                payment.status === 'pending' ? 'outline' : 'destructive'}
                        className="text-xs"
                      >
                        {payment.status}
                      </Badge>
                      <p className="text-xs text-slate-500 mt-1">
                        {formatDistanceToNow(new Date(payment.created_at), { addSuffix: true })}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Grant DUST Dialog */}
      <Dialog open={grantDialogOpen} onOpenChange={setGrantDialogOpen}>
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>Grant DUST</DialogTitle>
            <DialogDescription>
              Grant DUST to {user.fairyname}. Current balance: {user.dust_balance} DUST
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="amount" className="text-right">
                Amount
              </Label>
              <Input
                id="amount"
                type="number"
                min="1"
                max="10000"
                value={grantAmount}
                onChange={(e) => setGrantAmount(e.target.value)}
                className="col-span-3"
                placeholder="Enter DUST amount"
              />
            </div>
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="reason" className="text-right">
                Reason
              </Label>
              <Textarea
                id="reason"
                value={grantReason}
                onChange={(e) => setGrantReason(e.target.value)}
                className="col-span-3"
                placeholder="Enter reason for grant..."
                rows={3}
              />
            </div>
          </div>
          <DialogFooter>
            <Button 
              variant="outline" 
              onClick={() => setGrantDialogOpen(false)}
              disabled={granting}
            >
              Cancel
            </Button>
            <Button 
              onClick={handleGrantDust}
              disabled={granting || !grantAmount || !grantReason}
            >
              {granting ? 'Granting...' : 'Grant DUST'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}