import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { 
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { 
  ReferralConfig, 
  ReferralSystemStats, 
  ReferralCodesResponse, 
  ReferralRedemptionsResponse,
  MilestoneReward,
  PromotionalReferralCode,
  PromotionalReferralCodeCreate,
  PromotionalReferralCodesResponse
} from '@/types/admin';
import { 
  RefreshCw, 
  AlertTriangle, 
  Settings, 
  BarChart3, 
  Users, 
  Gift,
  Search,
  Filter,
  Plus,
  Minus,
  TrendingUp,
  Calendar,
  UserCheck
} from 'lucide-react';
import { formatDistanceToNow, format } from 'date-fns';
import { AdminAPI } from '@/lib/admin-api';
import { toast } from 'sonner';

export function Referrals() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Configuration state
  const [config, setConfig] = useState<ReferralConfig | null>(null);
  const [configLoading, setConfigLoading] = useState(false);
  const [configDialogOpen, setConfigDialogOpen] = useState(false);
  
  // Statistics state
  const [stats, setStats] = useState<ReferralSystemStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);
  
  // Codes state
  const [codes, setCodes] = useState<ReferralCodesResponse | null>(null);
  const [codesLoading, setCodesLoading] = useState(false);
  const [codesPage, setCodesPage] = useState(1);
  const [codesFilter, setCodesFilter] = useState<string>('');
  const [codesStatusFilter, setCodesStatusFilter] = useState<string>('');
  const [codesSearch, setCodesSearch] = useState<string>('');
  
  // Redemptions state
  const [redemptions, setRedemptions] = useState<ReferralRedemptionsResponse | null>(null);
  const [redemptionsLoading, setRedemptionsLoading] = useState(false);
  const [redemptionsPage, setRedemptionsPage] = useState(1);
  const [redemptionsDateFrom, setRedemptionsDateFrom] = useState<string>('');

  // Promotional codes state
  const [promoCodeDialog, setPromoCodeDialog] = useState(false);
  const [promoCodes, setPromoCodes] = useState<PromotionalReferralCodesResponse | null>(null);
  const [promoCodesLoading, setPromoCodesLoading] = useState(false);
  const [promoCodesPage, setPromoCodesPage] = useState(1);
  const [promoCodesStatusFilter, setPromoCodesStatusFilter] = useState<string>('');
  const [newPromoCode, setNewPromoCode] = useState<PromotionalReferralCodeCreate>({
    code: '',
    description: '',
    dust_bonus: 10,
    max_uses: undefined,
    expires_at: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString().slice(0, 16),
  });

  const loadConfig = async () => {
    try {
      setConfigLoading(true);
      const data = await AdminAPI.getReferralConfig();
      setConfig(data);
    } catch (err) {
      console.error('Failed to load referral config:', err);
      toast.error('Failed to load referral configuration');
    } finally {
      setConfigLoading(false);
    }
  };

  const loadStats = async () => {
    try {
      setStatsLoading(true);
      const data = await AdminAPI.getReferralStats();
      setStats(data);
    } catch (err) {
      console.error('Failed to load referral stats:', err);
      toast.error('Failed to load referral statistics');
    } finally {
      setStatsLoading(false);
    }
  };

  const loadCodes = async () => {
    try {
      setCodesLoading(true);
      const data = await AdminAPI.getReferralCodes({
        page: codesPage,
        limit: 50,
        status: codesStatusFilter || undefined,
        user_search: codesSearch || undefined,
      });
      setCodes(data);
    } catch (err) {
      console.error('Failed to load referral codes:', err);
      toast.error('Failed to load referral codes');
    } finally {
      setCodesLoading(false);
    }
  };

  const loadRedemptions = async () => {
    try {
      setRedemptionsLoading(true);
      const data = await AdminAPI.getReferralRedemptions({
        page: redemptionsPage,
        limit: 50,
        date_from: redemptionsDateFrom || undefined,
      });
      setRedemptions(data);
    } catch (err) {
      console.error('Failed to load referral redemptions:', err);
      toast.error('Failed to load referral redemptions');
    } finally {
      setRedemptionsLoading(false);
    }
  };

  const loadPromoCodes = async () => {
    try {
      setPromoCodesLoading(true);
      const data = await AdminAPI.getPromotionalCodes({
        page: promoCodesPage,
        limit: 50,
        status: (promoCodesStatusFilter as 'active' | 'expired' | 'inactive') || undefined,
      });
      setPromoCodes(data);
    } catch (err) {
      console.error('Failed to load promotional codes:', err);
      toast.error('Failed to load promotional codes');
    } finally {
      setPromoCodesLoading(false);
    }
  };

  const handleUpdateConfig = async () => {
    if (!config) return;
    
    try {
      setConfigLoading(true);
      await AdminAPI.updateReferralConfig(config);
      setConfigDialogOpen(false);
      toast.success('Referral configuration updated successfully');
      await loadConfig();
      await loadStats(); // Refresh stats as they may be affected
    } catch (err) {
      console.error('Failed to update referral config:', err);
      toast.error('Failed to update referral configuration');
    } finally {
      setConfigLoading(false);
    }
  };

  const addMilestone = () => {
    if (!config) return;
    setConfig({
      ...config,
      milestone_rewards: [
        ...config.milestone_rewards,
        { referral_count: 5, bonus_amount: 25 }
      ]
    });
  };

  const removeMilestone = (index: number) => {
    if (!config) return;
    setConfig({
      ...config,
      milestone_rewards: config.milestone_rewards.filter((_, i) => i !== index)
    });
  };

  const updateMilestone = (index: number, field: keyof MilestoneReward, value: number) => {
    if (!config) return;
    const newMilestones = [...config.milestone_rewards];
    newMilestones[index] = { ...newMilestones[index], [field]: value };
    setConfig({ ...config, milestone_rewards: newMilestones });
  };

  const handleCreatePromoCode = async () => {
    try {
      await AdminAPI.createPromotionalCode(newPromoCode);
      setPromoCodeDialog(false);
      toast.success('Promotional code created successfully');
      setNewPromoCode({
        code: '',
        description: '',
        dust_bonus: 10,
        max_uses: undefined,
        expires_at: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString().slice(0, 16),
      });
      await loadPromoCodes();
    } catch (err) {
      console.error('Failed to create promotional code:', err);
      toast.error('Failed to create promotional code');
    }
  };

  useEffect(() => {
    const loadAll = async () => {
      setLoading(true);
      setError(null);
      try {
        await Promise.all([loadConfig(), loadStats(), loadCodes(), loadRedemptions(), loadPromoCodes()]);
      } catch (err) {
        setError('Failed to load referral data');
      } finally {
        setLoading(false);
      }
    };
    
    loadAll();
  }, []);

  // Reload codes when filters change
  useEffect(() => {
    if (!loading) {
      loadCodes();
    }
  }, [codesPage, codesStatusFilter, codesSearch]);

  // Reload redemptions when filters change
  useEffect(() => {
    if (!loading) {
      loadRedemptions();
    }
  }, [redemptionsPage, redemptionsDateFrom]);

  // Reload promotional codes when filters change
  useEffect(() => {
    if (!loading) {
      loadPromoCodes();
    }
  }, [promoCodesPage, promoCodesStatusFilter]);

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'active':
        return <UserCheck className="h-4 w-4 text-green-600" />;
      case 'expired':
        return <Calendar className="h-4 w-4 text-orange-600" />;
      case 'inactive':
        return <AlertTriangle className="h-4 w-4 text-red-600" />;
      default:
        return <AlertTriangle className="h-4 w-4 text-gray-600" />;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active': return 'default';
      case 'expired': return 'secondary';
      case 'inactive': return 'destructive';
      default: return 'secondary';
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <RefreshCw className="h-6 w-6 animate-spin mr-2" />
        Loading referral system...
      </div>
    );
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertTriangle className="h-4 w-4" />
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">Referral System</h1>
          <p className="text-slate-500">Manage referral codes, rewards, and analytics</p>
        </div>
        <div className="flex space-x-3">
          <Button variant="outline" onClick={() => Promise.all([loadStats(), loadCodes(), loadRedemptions()])}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
          <Dialog open={configDialogOpen} onOpenChange={setConfigDialogOpen}>
            <DialogTrigger asChild>
              <Button>
                <Settings className="h-4 w-4 mr-2" />
                Configure System
              </Button>
            </DialogTrigger>
          </Dialog>
        </div>
      </div>

      {/* System Status */}
      {config && (
        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-3">
                <div className={`w-3 h-3 rounded-full ${config.system_enabled ? 'bg-green-500' : 'bg-red-500'}`} />
                <span className="font-medium">
                  Referral System {config.system_enabled ? 'Enabled' : 'Disabled'}
                </span>
              </div>
              <Badge variant="outline">
                {config.referee_bonus} + {config.referrer_bonus} DUST per referral
              </Badge>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Statistics Overview */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Total Codes</CardTitle>
              <Users className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.total_codes_created.toLocaleString()}</div>
              <p className="text-xs text-muted-foreground">
                Codes generated by users
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Successful Referrals</CardTitle>
              <UserCheck className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.total_successful_referrals.toLocaleString()}</div>
              <p className="text-xs text-muted-foreground">
                {(stats.conversion_rate * 100).toFixed(1)}% conversion rate
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">DUST Granted</CardTitle>
              <Gift className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.total_dust_granted.toLocaleString()}</div>
              <p className="text-xs text-muted-foreground">
                Total reward payouts
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Conversion Rate</CardTitle>
              <TrendingUp className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{(stats.conversion_rate * 100).toFixed(1)}%</div>
              <p className="text-xs text-muted-foreground">
                Codes to successful referrals
              </p>
            </CardContent>
          </Card>
        </div>
      )}

      <Tabs defaultValue="overview" className="space-y-6">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="codes">Referral Codes</TabsTrigger>
          <TabsTrigger value="promotional">Promotional Codes</TabsTrigger>
          <TabsTrigger value="redemptions">Redemptions</TabsTrigger>
          <TabsTrigger value="analytics">Analytics</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-6">
          {/* Top Referrers */}
          {stats && stats.top_referrers.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Top Referrers</CardTitle>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>User</TableHead>
                      <TableHead>Successful Referrals</TableHead>
                      <TableHead>DUST Earned</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {stats.top_referrers.map((referrer, index) => (
                      <TableRow key={referrer.user_id}>
                        <TableCell>
                          <div className="flex items-center space-x-2">
                            <Badge variant="outline">#{index + 1}</Badge>
                            <span className="font-medium">{referrer.fairyname}</span>
                          </div>
                        </TableCell>
                        <TableCell>{referrer.successful_referrals}</TableCell>
                        <TableCell>
                          <Badge variant="outline">{referrer.total_dust_earned} DUST</Badge>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="codes" className="space-y-6">
          {/* Filters */}
          <Card>
            <CardContent className="p-6">
              <div className="flex space-x-4">
                <div className="flex-1">
                  <Label htmlFor="search">Search User</Label>
                  <div className="relative">
                    <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                    <Input
                      id="search"
                      placeholder="Search by fairyname..."
                      value={codesSearch}
                      onChange={(e) => setCodesSearch(e.target.value)}
                      className="pl-9"
                    />
                  </div>
                </div>
                <div>
                  <Label htmlFor="status">Status Filter</Label>
                  <Select value={codesStatusFilter} onValueChange={setCodesStatusFilter}>
                    <SelectTrigger className="w-32">
                      <SelectValue placeholder="All" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="">All</SelectItem>
                      <SelectItem value="active">Active</SelectItem>
                      <SelectItem value="expired">Expired</SelectItem>
                      <SelectItem value="inactive">Inactive</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Codes Table */}
          <Card>
            <CardHeader>
              <CardTitle>
                Referral Codes ({codes?.total || 0})
              </CardTitle>
            </CardHeader>
            <CardContent>
              {codesLoading ? (
                <div className="flex items-center justify-center py-8">
                  <RefreshCw className="h-6 w-6 animate-spin mr-2" />
                  Loading codes...
                </div>
              ) : codes && codes.codes.length > 0 ? (
                <>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Code</TableHead>
                        <TableHead>User</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Created</TableHead>
                        <TableHead>Successful Referrals</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {codes.codes.map((code) => (
                        <TableRow key={code.referral_code}>
                          <TableCell>
                            <div className="font-mono font-bold">{code.referral_code}</div>
                          </TableCell>
                          <TableCell>{code.user_name}</TableCell>
                          <TableCell>
                            <div className="flex items-center space-x-2">
                              {getStatusIcon(code.status)}
                              <Badge variant={getStatusColor(code.status) as any}>
                                {code.status}
                              </Badge>
                            </div>
                          </TableCell>
                          <TableCell>
                            {formatDistanceToNow(new Date(code.created_at), { addSuffix: true })}
                          </TableCell>
                          <TableCell>
                            <Badge variant="outline">{code.successful_referrals}</Badge>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                  
                  {/* Pagination */}
                  <div className="flex items-center justify-between mt-4">
                    <div className="text-sm text-muted-foreground">
                      Showing {((codesPage - 1) * 50) + 1} to {Math.min(codesPage * 50, codes.total)} of {codes.total} codes
                    </div>
                    <div className="flex space-x-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setCodesPage(p => Math.max(1, p - 1))}
                        disabled={codesPage <= 1}
                      >
                        Previous
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setCodesPage(p => p + 1)}
                        disabled={!codes.has_more}
                      >
                        Next
                      </Button>
                    </div>
                  </div>
                </>
              ) : (
                <div className="text-center py-8 text-slate-500">
                  No referral codes found
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="redemptions" className="space-y-6">
          {/* Date Filter */}
          <Card>
            <CardContent className="p-6">
              <div className="flex space-x-4">
                <div>
                  <Label htmlFor="date-from">Filter from Date</Label>
                  <Input
                    id="date-from"
                    type="date"
                    value={redemptionsDateFrom}
                    onChange={(e) => setRedemptionsDateFrom(e.target.value)}
                  />
                </div>
                <div className="flex items-end">
                  <Button
                    variant="outline"
                    onClick={() => setRedemptionsDateFrom('')}
                  >
                    Clear Filter
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Redemptions Table */}
          <Card>
            <CardHeader>
              <CardTitle>
                Referral Redemptions ({redemptions?.total || 0})
              </CardTitle>
            </CardHeader>
            <CardContent>
              {redemptionsLoading ? (
                <div className="flex items-center justify-center py-8">
                  <RefreshCw className="h-6 w-6 animate-spin mr-2" />
                  Loading redemptions...
                </div>
              ) : redemptions && redemptions.redemptions.length > 0 ? (
                <>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Code</TableHead>
                        <TableHead>Referrer</TableHead>
                        <TableHead>New User</TableHead>
                        <TableHead>Redeemed</TableHead>
                        <TableHead>Rewards</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {redemptions.redemptions.map((redemption, index) => (
                        <TableRow key={index}>
                          <TableCell>
                            <div className="font-mono font-bold">{redemption.referral_code}</div>
                          </TableCell>
                          <TableCell>{redemption.referrer_name}</TableCell>
                          <TableCell>{redemption.referee_name}</TableCell>
                          <TableCell>
                            {formatDistanceToNow(new Date(redemption.redeemed_at), { addSuffix: true })}
                          </TableCell>
                          <TableCell>
                            <div className="flex space-x-2">
                              <Badge variant="outline">{redemption.referrer_bonus} DUST</Badge>
                              <Badge variant="outline">{redemption.referee_bonus} DUST</Badge>
                            </div>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                  
                  {/* Pagination */}
                  <div className="flex items-center justify-between mt-4">
                    <div className="text-sm text-muted-foreground">
                      Showing {((redemptionsPage - 1) * 50) + 1} to {Math.min(redemptionsPage * 50, redemptions.total)} of {redemptions.total} redemptions
                    </div>
                    <div className="flex space-x-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setRedemptionsPage(p => Math.max(1, p - 1))}
                        disabled={redemptionsPage <= 1}
                      >
                        Previous
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setRedemptionsPage(p => p + 1)}
                        disabled={!redemptions.has_more}
                      >
                        Next
                      </Button>
                    </div>
                  </div>
                </>
              ) : (
                <div className="text-center py-8 text-slate-500">
                  No redemptions found
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="analytics" className="space-y-6">
          {/* Daily Stats Chart would go here */}
          <Card>
            <CardHeader>
              <CardTitle>Daily Statistics</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-center py-8 text-slate-500">
                <BarChart3 className="h-12 w-12 mx-auto mb-4 text-slate-300" />
                Analytics charts coming soon...
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="promotional" className="space-y-6">
          <Card>
            <CardHeader>
              <div className="flex justify-between items-center">
                <div>
                  <CardTitle>Promotional Codes</CardTitle>
                  <p className="text-sm text-muted-foreground mt-1">
                    Create and manage one-off promotional referral codes
                  </p>
                </div>
                <Dialog open={promoCodeDialog} onOpenChange={setPromoCodeDialog}>
                  <DialogTrigger asChild>
                    <Button>
                      <Plus className="h-4 w-4 mr-2" />
                      Create Code
                    </Button>
                  </DialogTrigger>
                  <DialogContent>
                    <DialogHeader>
                      <DialogTitle>Create Promotional Code</DialogTitle>
                      <DialogDescription>
                        Create a new promotional referral code for special campaigns
                      </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4">
                      <div>
                        <Label htmlFor="promo-code">Code</Label>
                        <Input
                          id="promo-code"
                          value={newPromoCode.code}
                          onChange={(e) => setNewPromoCode({ ...newPromoCode, code: e.target.value.toUpperCase() })}
                          placeholder="PROMO2024"
                          maxLength={20}
                        />
                      </div>
                      <div>
                        <Label htmlFor="promo-description">Description</Label>
                        <Textarea
                          id="promo-description"
                          value={newPromoCode.description}
                          onChange={(e) => setNewPromoCode({ ...newPromoCode, description: e.target.value })}
                          placeholder="Special promotion for new users"
                        />
                      </div>
                      <div>
                        <Label htmlFor="promo-dust">DUST Bonus</Label>
                        <Input
                          id="promo-dust"
                          type="number"
                          min="1"
                          max="1000"
                          value={newPromoCode.dust_bonus}
                          onChange={(e) => setNewPromoCode({ ...newPromoCode, dust_bonus: parseInt(e.target.value) || 0 })}
                        />
                      </div>
                      <div>
                        <Label htmlFor="promo-max-uses">Max Uses (Optional)</Label>
                        <Input
                          id="promo-max-uses"
                          type="number"
                          min="1"
                          value={newPromoCode.max_uses || ''}
                          onChange={(e) => setNewPromoCode({ 
                            ...newPromoCode, 
                            max_uses: e.target.value ? parseInt(e.target.value) : undefined 
                          })}
                          placeholder="Leave empty for unlimited"
                        />
                      </div>
                      <div>
                        <Label htmlFor="promo-expires">Expires At</Label>
                        <Input
                          id="promo-expires"
                          type="datetime-local"
                          value={newPromoCode.expires_at}
                          onChange={(e) => setNewPromoCode({ ...newPromoCode, expires_at: e.target.value })}
                        />
                      </div>
                    </div>
                    <DialogFooter>
                      <Button variant="outline" onClick={() => setPromoCodeDialog(false)}>
                        Cancel
                      </Button>
                      <Button onClick={handleCreatePromoCode}>
                        Create Code
                      </Button>
                    </DialogFooter>
                  </DialogContent>
                </Dialog>
              </div>
            </CardHeader>
            <CardContent>
              {/* Filters */}
              <div className="flex space-x-4 mb-6">
                <Select value={promoCodesStatusFilter} onValueChange={setPromoCodesStatusFilter}>
                  <SelectTrigger className="w-48">
                    <SelectValue placeholder="Filter by status" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="">All Statuses</SelectItem>
                    <SelectItem value="active">Active</SelectItem>
                    <SelectItem value="expired">Expired</SelectItem>
                    <SelectItem value="inactive">Inactive</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {promoCodesLoading ? (
                <div className="flex items-center justify-center py-8">
                  <RefreshCw className="h-6 w-6 animate-spin mr-2" />
                  Loading promotional codes...
                </div>
              ) : promoCodes && promoCodes.codes.length > 0 ? (
                <>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Code</TableHead>
                        <TableHead>Description</TableHead>
                        <TableHead>DUST Bonus</TableHead>
                        <TableHead>Usage</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Expires</TableHead>
                        <TableHead>Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {promoCodes.codes.map((code) => (
                        <TableRow key={code.id}>
                          <TableCell className="font-mono font-medium">{code.code}</TableCell>
                          <TableCell>{code.description}</TableCell>
                          <TableCell>
                            <Badge variant="secondary">{code.dust_bonus} DUST</Badge>
                          </TableCell>
                          <TableCell>
                            {code.current_uses}{code.max_uses ? ` / ${code.max_uses}` : ' / ∞'}
                          </TableCell>
                          <TableCell>
                            <Badge 
                              variant={
                                !code.is_active ? 'destructive' :
                                new Date(code.expires_at) < new Date() ? 'secondary' :
                                'default'
                              }
                            >
                              {!code.is_active ? 'Inactive' :
                               new Date(code.expires_at) < new Date() ? 'Expired' :
                               'Active'}
                            </Badge>
                          </TableCell>
                          <TableCell>
                            {format(new Date(code.expires_at), 'MMM d, yyyy')}
                          </TableCell>
                          <TableCell>
                            <Button 
                              variant="destructive" 
                              size="sm"
                              onClick={async () => {
                                try {
                                  await AdminAPI.deletePromotionalCode(code.id);
                                  toast.success('Promotional code deleted');
                                  await loadPromoCodes();
                                } catch (err) {
                                  console.error('Failed to delete code:', err);
                                  toast.error('Failed to delete promotional code');
                                }
                              }}
                            >
                              Delete
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                  
                  {/* Pagination */}
                  <div className="flex items-center justify-between mt-4">
                    <div className="text-sm text-muted-foreground">
                      Showing {((promoCodesPage - 1) * 50) + 1} to {Math.min(promoCodesPage * 50, promoCodes.total)} of {promoCodes.total} codes
                    </div>
                    <div className="flex space-x-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setPromoCodesPage(p => Math.max(1, p - 1))}
                        disabled={promoCodesPage <= 1}
                      >
                        Previous
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setPromoCodesPage(p => p + 1)}
                        disabled={!promoCodes.has_more}
                      >
                        Next
                      </Button>
                    </div>
                  </div>
                </>
              ) : (
                <div className="text-center py-8 text-slate-500">
                  <Gift className="h-12 w-12 mx-auto mb-4 text-slate-300" />
                  No promotional codes found
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Configuration Dialog */}
      <Dialog open={configDialogOpen} onOpenChange={setConfigDialogOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Referral System Configuration</DialogTitle>
            <DialogDescription>
              Configure referral rewards, limits, and system settings
            </DialogDescription>
          </DialogHeader>
          
          {config && (
            <div className="space-y-6 py-4">
              {/* System Enable/Disable */}
              <div className="flex items-center justify-between">
                <div>
                  <Label>System Enabled</Label>
                  <p className="text-sm text-muted-foreground">
                    Enable or disable the entire referral system
                  </p>
                </div>
                <Switch
                  checked={config.system_enabled}
                  onCheckedChange={(checked) => setConfig({ ...config, system_enabled: checked })}
                />
              </div>

              {/* Basic Rewards */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="referee-bonus">Referee Bonus (DUST)</Label>
                  <Input
                    id="referee-bonus"
                    type="number"
                    min="1"
                    max="100"
                    value={config.referee_bonus}
                    onChange={(e) => setConfig({ ...config, referee_bonus: parseInt(e.target.value) || 0 })}
                  />
                </div>
                <div>
                  <Label htmlFor="referrer-bonus">Referrer Bonus (DUST)</Label>
                  <Input
                    id="referrer-bonus"
                    type="number"
                    min="1"
                    max="100"
                    value={config.referrer_bonus}
                    onChange={(e) => setConfig({ ...config, referrer_bonus: parseInt(e.target.value) || 0 })}
                  />
                </div>
              </div>

              {/* System Limits */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="code-expiry">Code Expiry (Days)</Label>
                  <Input
                    id="code-expiry"
                    type="number"
                    min="1"
                    max="365"
                    value={config.code_expiry_days}
                    onChange={(e) => setConfig({ ...config, code_expiry_days: parseInt(e.target.value) || 0 })}
                  />
                </div>
                <div>
                  <Label htmlFor="max-referrals">Max Referrals per User</Label>
                  <Input
                    id="max-referrals"
                    type="number"
                    min="1"
                    max="10000"
                    value={config.max_referrals_per_user}
                    onChange={(e) => setConfig({ ...config, max_referrals_per_user: parseInt(e.target.value) || 0 })}
                  />
                </div>
              </div>

              {/* Milestone Rewards */}
              <div>
                <div className="flex items-center justify-between mb-3">
                  <Label>Milestone Rewards</Label>
                  <Button size="sm" onClick={addMilestone}>
                    <Plus className="h-4 w-4 mr-1" />
                    Add Milestone
                  </Button>
                </div>
                <div className="space-y-3">
                  {config.milestone_rewards.map((milestone, index) => (
                    <div key={index} className="flex items-center space-x-3">
                      <Input
                        type="number"
                        placeholder="Referrals"
                        value={milestone.referral_count}
                        onChange={(e) => updateMilestone(index, 'referral_count', parseInt(e.target.value) || 0)}
                        className="w-24"
                      />
                      <span className="text-sm">referrals =</span>
                      <Input
                        type="number"
                        placeholder="DUST"
                        value={milestone.bonus_amount}
                        onChange={(e) => updateMilestone(index, 'bonus_amount', parseInt(e.target.value) || 0)}
                        className="w-24"
                      />
                      <span className="text-sm">DUST bonus</span>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => removeMilestone(index)}
                      >
                        <Minus className="h-4 w-4" />
                      </Button>
                    </div>
                  ))}
                  {config.milestone_rewards.length === 0 && (
                    <p className="text-sm text-muted-foreground">No milestone rewards configured</p>
                  )}
                </div>
              </div>
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setConfigDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleUpdateConfig} disabled={configLoading}>
              {configLoading ? 'Saving...' : 'Save Configuration'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}