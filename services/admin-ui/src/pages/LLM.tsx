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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { 
  Brain, 
  DollarSign, 
  Clock, 
  TrendingUp, 
  AlertTriangle,
  RefreshCw
} from 'lucide-react';
import { AdminAPI } from '@/lib/admin-api';

interface LLMUsageMetrics {
  timeframe: string;
  total_stats: {
    total_requests: number;
    total_tokens: number;
    total_cost_usd: number;
    avg_latency_ms: number;
  };
  model_breakdown: Array<{
    provider: string;
    model_id: string;
    requests: number;
    cost: number;
    avg_latency: number;
  }>;
  app_usage: Array<{
    app_name: string;
    app_slug: string;
    total_requests: number;
    avg_prompt_tokens: number;
    avg_completion_tokens: number;
    avg_total_tokens: number;
    avg_cost_per_request: number;
    total_cost: number;
    avg_latency_ms: number;
  }>;
}


interface ModelUsage {
  model: string;
  requests: number;
  cost: number;
  avg_latency: number;
}

interface ActionAnalytics {
  action_slug: string;
  app_name: string;
  total_requests: number;
  avg_cost_per_request: number;
  total_cost: number;
  avg_total_tokens: number;
  avg_latency_ms: number;
  current_dust_cost: number;
  cost_efficiency: number;
  cost_per_dust: number | null;
}

interface FallbackAnalytics {
  timeframe: string;
  overall_stats: {
    total_requests: number;
    fallback_requests: number;
    primary_requests: number;
    fallback_percentage: number;
  };
  provider_reliability: Array<{
    provider: string;
    total_requests: number;
    primary_success: number;
    fallback_usage: number;
    reliability_percentage: number;
    avg_latency_ms: number;
    total_cost: number;
  }>;
  fallback_reasons: Array<{
    fallback_reason: string;
    occurrences: number;
    percentage_of_fallbacks: number;
  }>;
  daily_trends: Array<{
    date: string;
    total_requests: number;
    fallback_requests: number;
    fallback_rate: number;
  }>;
  app_fallback_usage: Array<{
    app_name: string;
    app_slug: string;
    total_requests: number;
    fallback_requests: number;
    fallback_percentage: number;
    avg_cost_per_request: number;
  }>;
}


export function LLM() {
  const [metrics, setMetrics] = useState<LLMUsageMetrics | null>(null);
  const [modelUsage, setModelUsage] = useState<ModelUsage[]>([]);
  const [actionAnalytics, setActionAnalytics] = useState<ActionAnalytics[]>([]);
  const [fallbackAnalytics, setFallbackAnalytics] = useState<FallbackAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [timeframe, setTimeframe] = useState('7d');
  const [activeTab, setActiveTab] = useState('overview');

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const [metricsData, modelUsageData, actionData, fallbackData] = await Promise.all([
        AdminAPI.getLLMUsageMetrics(timeframe),
        AdminAPI.getLLMModelUsage(),
        AdminAPI.getActionAnalytics(timeframe),
        AdminAPI.getFallbackAnalytics(timeframe),
      ]);
      
      setMetrics(metricsData);
      setModelUsage(modelUsageData);
      setActionAnalytics(actionData.action_analytics || []);
      setFallbackAnalytics(fallbackData);
    } catch (err) {
      console.error('Failed to load LLM data:', err);
      setError('Failed to load LLM data. Please try again.');
    } finally {
      setLoading(false);
    }
  };


  useEffect(() => {
    loadData();
  }, [timeframe]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center space-y-4">
          <RefreshCw className="h-8 w-8 animate-spin mx-auto text-slate-400" />
          <p className="text-slate-500">Loading LLM data...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <Alert className="border-red-200 bg-red-50">
          <AlertTriangle className="h-4 w-4 text-red-600" />
          <AlertDescription className="text-red-700">
            {error}
            <Button 
              variant="link" 
              className="p-0 ml-2 text-red-800 underline"
              onClick={loadData}
            >
              Retry
            </Button>
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">LLM Management</h1>
          <p className="text-slate-500">Monitor usage, costs, and configure AI models</p>
        </div>
        <div className="flex items-center gap-4">
          <Select value={timeframe} onValueChange={setTimeframe}>
            <SelectTrigger className="w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="1d">Last Day</SelectItem>
              <SelectItem value="7d">Last Week</SelectItem>
              <SelectItem value="30d">Last Month</SelectItem>
              <SelectItem value="90d">Last 3 Months</SelectItem>
            </SelectContent>
          </Select>
          <Button onClick={loadData} variant="outline">
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="models">Model Usage</TabsTrigger>
          <TabsTrigger value="apps">App Usage</TabsTrigger>
          <TabsTrigger value="actions">Action Analytics</TabsTrigger>
          <TabsTrigger value="reliability">Provider Reliability</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-6">
          {/* Stats Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Total Requests</CardTitle>
                <Brain className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {metrics?.total_stats.total_requests?.toLocaleString() || 0}
                </div>
                <p className="text-xs text-muted-foreground">
                  in the last {timeframe === '1d' ? 'day' : timeframe === '7d' ? 'week' : timeframe === '30d' ? 'month' : '3 months'}
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Total Tokens</CardTitle>
                <TrendingUp className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {metrics?.total_stats.total_tokens?.toLocaleString() || 0}
                </div>
                <p className="text-xs text-muted-foreground">
                  tokens processed
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Total Cost</CardTitle>
                <DollarSign className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  ${metrics?.total_stats.total_cost_usd?.toFixed(2) || '0.00'}
                </div>
                <p className="text-xs text-muted-foreground">
                  USD spent
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Avg Latency</CardTitle>
                <Clock className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {metrics?.total_stats.avg_latency_ms?.toFixed(0) || 0}ms
                </div>
                <p className="text-xs text-muted-foreground">
                  average response time
                </p>
              </CardContent>
            </Card>
          </div>

          {/* Model Breakdown */}
          <Card>
            <CardHeader>
              <CardTitle>Top Models by Cost</CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Provider</TableHead>
                    <TableHead>Model</TableHead>
                    <TableHead>Requests</TableHead>
                    <TableHead>Cost</TableHead>
                    <TableHead>Avg Latency</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {metrics?.model_breakdown.map((model, index) => (
                    <TableRow key={index}>
                      <TableCell>
                        <Badge variant="outline" className="capitalize">
                          {model.provider}
                        </Badge>
                      </TableCell>
                      <TableCell className="font-medium">{model.model_id}</TableCell>
                      <TableCell>{model.requests.toLocaleString()}</TableCell>
                      <TableCell>${model.cost.toFixed(4)}</TableCell>
                      <TableCell>{model.avg_latency.toFixed(0)}ms</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="models" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Model Usage Statistics</CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Model</TableHead>
                    <TableHead>Requests</TableHead>
                    <TableHead>Total Cost</TableHead>
                    <TableHead>Avg Latency</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {modelUsage.map((model, index) => (
                    <TableRow key={index}>
                      <TableCell className="font-medium">{model.model}</TableCell>
                      <TableCell>{model.requests.toLocaleString()}</TableCell>
                      <TableCell>${model.cost.toFixed(4)}</TableCell>
                      <TableCell>{model.avg_latency.toFixed(0)}ms</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="apps" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>App Usage Analytics</CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>App</TableHead>
                    <TableHead>Requests</TableHead>
                    <TableHead>Avg Tokens</TableHead>
                    <TableHead>Avg Cost/Request</TableHead>
                    <TableHead>Total Cost</TableHead>
                    <TableHead>Avg Latency</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {metrics?.app_usage.map((app, index) => (
                    <TableRow key={index}>
                      <TableCell>
                        <div>
                          <div className="font-medium">{app.app_name}</div>
                          <div className="text-sm text-muted-foreground">{app.app_slug}</div>
                        </div>
                      </TableCell>
                      <TableCell>{app.total_requests.toLocaleString()}</TableCell>
                      <TableCell>{app.avg_total_tokens.toFixed(0)}</TableCell>
                      <TableCell>${app.avg_cost_per_request.toFixed(6)}</TableCell>
                      <TableCell>${app.total_cost.toFixed(4)}</TableCell>
                      <TableCell>{app.avg_latency_ms.toFixed(0)}ms</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="actions" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Action Cost Analytics</CardTitle>
              <p className="text-sm text-muted-foreground">
                Analyze token costs by action-slug to optimize DUST pricing
              </p>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Action</TableHead>
                    <TableHead>App</TableHead>
                    <TableHead>Requests</TableHead>
                    <TableHead>Avg Cost/Request</TableHead>
                    <TableHead>Current DUST Cost</TableHead>
                    <TableHead>Cost per DUST</TableHead>
                    <TableHead>Avg Tokens</TableHead>
                    <TableHead>Total Cost</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {actionAnalytics.map((action, index) => (
                    <TableRow key={index}>
                      <TableCell className="font-medium">{action.action_slug}</TableCell>
                      <TableCell>
                        <Badge variant="outline">{action.app_name}</Badge>
                      </TableCell>
                      <TableCell>{action.total_requests.toLocaleString()}</TableCell>
                      <TableCell>${action.avg_cost_per_request.toFixed(6)}</TableCell>
                      <TableCell>
                        <Badge variant={action.current_dust_cost > 0 ? "default" : "secondary"}>
                          {action.current_dust_cost} DUST
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {action.cost_per_dust !== null ? (
                          <span className={action.cost_per_dust > 0.001 ? "text-red-600" : "text-green-600"}>
                            ${action.cost_per_dust.toFixed(6)}/DUST
                          </span>
                        ) : (
                          <span className="text-gray-400">No pricing</span>
                        )}
                      </TableCell>
                      <TableCell>{action.avg_total_tokens.toFixed(0)}</TableCell>
                      <TableCell>${action.total_cost.toFixed(4)}</TableCell>
                    </TableRow>
                  ))}
                  {actionAnalytics.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={8} className="text-center text-muted-foreground">
                        No action analytics data available for the selected timeframe
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="reliability" className="space-y-6">
          {/* Overall Fallback Stats */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Total Requests</CardTitle>
                <Brain className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {fallbackAnalytics?.overall_stats.total_requests?.toLocaleString() || 0}
                </div>
                <p className="text-xs text-muted-foreground">
                  in the last {timeframe === '1d' ? 'day' : timeframe === '7d' ? 'week' : timeframe === '30d' ? 'month' : '3 months'}
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Primary Success</CardTitle>
                <TrendingUp className="h-4 w-4 text-green-600" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {fallbackAnalytics?.overall_stats.primary_requests?.toLocaleString() || 0}
                </div>
                <p className="text-xs text-muted-foreground">
                  successful primary requests
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Fallback Usage</CardTitle>
                <AlertTriangle className="h-4 w-4 text-orange-600" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {fallbackAnalytics?.overall_stats.fallback_requests?.toLocaleString() || 0}
                </div>
                <p className="text-xs text-muted-foreground">
                  requests used fallback
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Fallback Rate</CardTitle>
                <DollarSign className="h-4 w-4 text-red-600" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {fallbackAnalytics?.overall_stats.fallback_percentage?.toFixed(1) || 0}%
                </div>
                <p className="text-xs text-muted-foreground">
                  of total requests
                </p>
              </CardContent>
            </Card>
          </div>

          {/* Provider Reliability Table */}
          <Card>
            <CardHeader>
              <CardTitle>Provider Reliability</CardTitle>
              <p className="text-sm text-muted-foreground">
                Monitor which providers are most reliable and when fallbacks occur
              </p>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Provider</TableHead>
                    <TableHead>Total Requests</TableHead>
                    <TableHead>Success Rate</TableHead>
                    <TableHead>Fallback Usage</TableHead>
                    <TableHead>Avg Latency</TableHead>
                    <TableHead>Total Cost</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {fallbackAnalytics?.provider_reliability.map((provider, index) => (
                    <TableRow key={index}>
                      <TableCell className="font-medium">
                        <Badge 
                          variant="outline" 
                          className={`capitalize ${
                            provider.provider === 'anthropic' ? 'border-blue-200 text-blue-700' : 'border-green-200 text-green-700'
                          }`}
                        >
                          {provider.provider}
                        </Badge>
                      </TableCell>
                      <TableCell>{provider.total_requests.toLocaleString()}</TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <div 
                            className={`w-2 h-2 rounded-full ${
                              provider.reliability_percentage >= 95 ? 'bg-green-500' : 
                              provider.reliability_percentage >= 90 ? 'bg-yellow-500' : 'bg-red-500'
                            }`} 
                          />
                          <span className={
                            provider.reliability_percentage >= 95 ? 'text-green-700' : 
                            provider.reliability_percentage >= 90 ? 'text-yellow-700' : 'text-red-700'
                          }>
                            {provider.reliability_percentage.toFixed(1)}%
                          </span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <span className={provider.fallback_usage > 0 ? 'text-orange-600' : 'text-green-600'}>
                          {provider.fallback_usage.toLocaleString()}
                        </span>
                      </TableCell>
                      <TableCell>{provider.avg_latency_ms.toFixed(0)}ms</TableCell>
                      <TableCell>${provider.total_cost.toFixed(4)}</TableCell>
                    </TableRow>
                  )) || []}
                  {(!fallbackAnalytics?.provider_reliability || fallbackAnalytics.provider_reliability.length === 0) && (
                    <TableRow>
                      <TableCell colSpan={6} className="text-center text-muted-foreground">
                        No provider reliability data available for the selected timeframe
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          {/* Fallback Reasons */}
          {fallbackAnalytics?.fallback_reasons && fallbackAnalytics.fallback_reasons.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Fallback Reasons</CardTitle>
                <p className="text-sm text-muted-foreground">
                  Why providers failed and triggered fallbacks
                </p>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Reason</TableHead>
                      <TableHead>Occurrences</TableHead>
                      <TableHead>% of Fallbacks</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {fallbackAnalytics.fallback_reasons.map((reason, index) => (
                      <TableRow key={index}>
                        <TableCell className="font-medium">{reason.fallback_reason}</TableCell>
                        <TableCell>{reason.occurrences.toLocaleString()}</TableCell>
                        <TableCell>
                          <Badge variant="secondary">
                            {reason.percentage_of_fallbacks.toFixed(1)}%
                          </Badge>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}

          {/* App Fallback Usage */}
          <Card>
            <CardHeader>
              <CardTitle>App Fallback Usage</CardTitle>
              <p className="text-sm text-muted-foreground">
                Which apps experience the most provider failures
              </p>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>App</TableHead>
                    <TableHead>Total Requests</TableHead>
                    <TableHead>Fallback Usage</TableHead>
                    <TableHead>Fallback Rate</TableHead>
                    <TableHead>Avg Cost/Request</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {fallbackAnalytics?.app_fallback_usage.map((app, index) => (
                    <TableRow key={index}>
                      <TableCell>
                        <div>
                          <div className="font-medium">{app.app_name}</div>
                          <div className="text-sm text-muted-foreground">{app.app_slug}</div>
                        </div>
                      </TableCell>
                      <TableCell>{app.total_requests.toLocaleString()}</TableCell>
                      <TableCell>
                        <span className={app.fallback_requests > 0 ? 'text-orange-600' : 'text-green-600'}>
                          {app.fallback_requests.toLocaleString()}
                        </span>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <div 
                            className={`w-2 h-2 rounded-full ${
                              app.fallback_percentage <= 5 ? 'bg-green-500' : 
                              app.fallback_percentage <= 15 ? 'bg-yellow-500' : 'bg-red-500'
                            }`} 
                          />
                          <span className={
                            app.fallback_percentage <= 5 ? 'text-green-700' : 
                            app.fallback_percentage <= 15 ? 'text-yellow-700' : 'text-red-700'
                          }>
                            {app.fallback_percentage ? app.fallback_percentage.toFixed(1) : 0}%
                          </span>
                        </div>
                      </TableCell>
                      <TableCell>${app.avg_cost_per_request.toFixed(6)}</TableCell>
                    </TableRow>
                  )) || []}
                  {(!fallbackAnalytics?.app_fallback_usage || fallbackAnalytics.app_fallback_usage.length === 0) && (
                    <TableRow>
                      <TableCell colSpan={5} className="text-center text-muted-foreground">
                        No app fallback data available for the selected timeframe
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

    </div>
  );
}