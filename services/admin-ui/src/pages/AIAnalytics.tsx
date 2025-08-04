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
  RefreshCw,
  Image,
  Video,
  Zap
} from 'lucide-react';
import { AdminAPI } from '@/lib/admin-api';

interface AIUsageMetrics {
  timeframe: string;
  total_stats: {
    total_requests: number;
    total_tokens: number;
    total_images: number;
    total_videos: number;
    total_cost_usd: number;
    avg_latency_ms: number;
  };
  model_breakdown: Array<{
    provider: string;
    model_id: string;
    model_type: 'text' | 'image' | 'video';
    requests: number;
    cost: number;
    avg_latency: number;
    // Additional metrics per type
    tokens?: number;
    images?: number;
    videos?: number;
  }>;
  app_usage: Array<{
    app_name: string;
    app_slug: string;
    models_used: Array<{
      model_id: string;
      model_type: 'text' | 'image' | 'video';
      requests: number;
      cost: number;
      avg_latency_ms: number;
    }>;
    total_requests: number;
    avg_prompt_tokens?: number;
    avg_completion_tokens?: number;
    avg_total_tokens?: number;
    total_images?: number;
    total_videos?: number;
    avg_cost_per_request: number;
    total_cost: number;
  }>;
}

interface ModelUsage {
  model: string;
  model_type: 'text' | 'image' | 'video';
  requests: number;
  cost: number;
  avg_latency: number;
  provider?: string;
}

interface ActionAnalytics {
  action_slug: string;
  app_name: string;
  model_type: 'text' | 'image' | 'video';
  model_id: string;
  total_requests: number;
  avg_cost_per_request: number;
  total_cost: number;
  avg_total_tokens?: number;
  total_images?: number;
  total_videos?: number;
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
    model_type: 'text' | 'image' | 'video';
    total_requests: number;
    primary_success: number;
    fallback_usage: number;
    reliability_percentage: number;
    avg_latency_ms: number;
    total_cost: number;
  }>;
  fallback_reasons: Array<{
    fallback_reason: string;
    model_type: 'text' | 'image' | 'video';
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

const getModelTypeIcon = (type: 'text' | 'image' | 'video') => {
  switch (type) {
    case 'text': return <Brain className="h-4 w-4" />;
    case 'image': return <Image className="h-4 w-4" />;
    case 'video': return <Video className="h-4 w-4" />;
  }
};

const getModelTypeColor = (type: 'text' | 'image' | 'video') => {
  switch (type) {
    case 'text': return 'text-blue-600 bg-blue-50 border-blue-200';
    case 'image': return 'text-purple-600 bg-purple-50 border-purple-200';
    case 'video': return 'text-green-600 bg-green-50 border-green-200';
  }
};

export function AIAnalytics() {
  const [metrics, setMetrics] = useState<AIUsageMetrics | null>(null);
  const [modelUsage, setModelUsage] = useState<ModelUsage[]>([]);
  const [actionAnalytics, setActionAnalytics] = useState<ActionAnalytics[]>([]);
  const [fallbackAnalytics, setFallbackAnalytics] = useState<FallbackAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [timeframe, setTimeframe] = useState('7d');
  const [activeTab, setActiveTab] = useState('overview');
  const [modelTypeFilter, setModelTypeFilter] = useState<'all' | 'text' | 'image' | 'video'>('all');

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const [metricsData, modelUsageData, actionData, fallbackData] = await Promise.all([
        AdminAPI.getAIUsageMetrics(timeframe),
        AdminAPI.getAIModelUsage(modelTypeFilter),
        AdminAPI.getActionAnalytics(timeframe),
        AdminAPI.getFallbackAnalytics(timeframe),
      ]);
      
      setMetrics(metricsData);
      setModelUsage(modelUsageData);
      setActionAnalytics(actionData.action_analytics || []);
      setFallbackAnalytics(fallbackData);
    } catch (err) {
      console.error('Failed to load AI analytics data:', err);
      setError('Failed to load AI analytics data. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [timeframe, modelTypeFilter]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center space-y-4">
          <RefreshCw className="h-8 w-8 animate-spin mx-auto text-slate-400" />
          <p className="text-slate-500">Loading AI analytics data...</p>
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

  const filteredModelUsage = modelTypeFilter === 'all' 
    ? modelUsage 
    : modelUsage.filter(model => model.model_type === modelTypeFilter);

  const filteredActionAnalytics = modelTypeFilter === 'all'
    ? actionAnalytics
    : actionAnalytics.filter(action => action.model_type === modelTypeFilter);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">AI Model Analytics</h1>
          <p className="text-slate-500">Monitor usage, costs, and performance across Text, Image, and Video models</p>
        </div>
        <div className="flex items-center gap-4">
          <Select value={modelTypeFilter} onValueChange={(value: any) => setModelTypeFilter(value)}>
            <SelectTrigger className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Models</SelectItem>
              <SelectItem value="text">Text Models</SelectItem>
              <SelectItem value="image">Image Models</SelectItem>
              <SelectItem value="video">Video Models</SelectItem>
            </SelectContent>
          </Select>
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
                <Zap className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {metrics?.total_stats.total_requests?.toLocaleString() || 0}
                </div>
                <p className="text-xs text-muted-foreground">
                  across all AI models
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Content Generated</CardTitle>
                <TrendingUp className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {((metrics?.total_stats.total_tokens || 0) / 1000).toFixed(0)}K
                </div>
                <div className="text-xs text-muted-foreground space-y-1">
                  <div>• {metrics?.total_stats.total_tokens?.toLocaleString() || 0} tokens</div>
                  <div>• {metrics?.total_stats.total_images?.toLocaleString() || 0} images</div>
                  <div>• {metrics?.total_stats.total_videos?.toLocaleString() || 0} videos</div>
                </div>
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
                  USD spent on AI
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
                    <TableHead>Type</TableHead>
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
                        <Badge variant="outline" className={getModelTypeColor(model.model_type)}>
                          {getModelTypeIcon(model.model_type)}
                          <span className="ml-1 capitalize">{model.model_type}</span>
                        </Badge>
                      </TableCell>
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
                    <TableHead>Type</TableHead>
                    <TableHead>Model</TableHead>
                    <TableHead>Provider</TableHead>
                    <TableHead>Requests</TableHead>
                    <TableHead>Total Cost</TableHead>
                    <TableHead>Avg Latency</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredModelUsage.map((model, index) => (
                    <TableRow key={index}>
                      <TableCell>
                        <Badge variant="outline" className={getModelTypeColor(model.model_type)}>
                          {getModelTypeIcon(model.model_type)}
                          <span className="ml-1 capitalize">{model.model_type}</span>
                        </Badge>
                      </TableCell>
                      <TableCell className="font-medium">{model.model}</TableCell>
                      <TableCell>
                        <Badge variant="outline" className="capitalize">
                          {model.provider || 'Unknown'}
                        </Badge>
                      </TableCell>
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
                    <TableHead>Models Used</TableHead>
                    <TableHead>Requests</TableHead>
                    <TableHead>Content Generated</TableHead>
                    <TableHead>Avg Cost/Request</TableHead>
                    <TableHead>Total Cost</TableHead>
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
                      <TableCell>
                        <div className="space-y-1">
                          {app.models_used.map((model, idx) => (
                            <Badge key={idx} variant="outline" className={`${getModelTypeColor(model.model_type)} text-xs`}>
                              {getModelTypeIcon(model.model_type)}
                              <span className="ml-1">{model.model_id}</span>
                            </Badge>
                          ))}
                        </div>
                      </TableCell>
                      <TableCell>{app.total_requests.toLocaleString()}</TableCell>
                      <TableCell>
                        <div className="text-sm">
                          {app.avg_total_tokens && (
                            <div>{app.avg_total_tokens.toFixed(0)} tokens</div>
                          )}
                          {app.total_images && (
                            <div>{app.total_images} images</div>
                          )}
                          {app.total_videos && (
                            <div>{app.total_videos} videos</div>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>${app.avg_cost_per_request.toFixed(6)}</TableCell>
                      <TableCell>${app.total_cost.toFixed(4)}</TableCell>
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
                Analyze AI costs by action-slug to optimize DUST pricing
              </p>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Action</TableHead>
                    <TableHead>App</TableHead>
                    <TableHead>Model</TableHead>
                    <TableHead>Requests</TableHead>
                    <TableHead>Avg Cost/Request</TableHead>
                    <TableHead>Current DUST Cost</TableHead>
                    <TableHead>Cost per DUST</TableHead>
                    <TableHead>Total Cost</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredActionAnalytics.map((action, index) => (
                    <TableRow key={index}>
                      <TableCell className="font-medium">{action.action_slug}</TableCell>
                      <TableCell>
                        <Badge variant="outline">{action.app_name}</Badge>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <Badge variant="outline" className={getModelTypeColor(action.model_type)}>
                            {getModelTypeIcon(action.model_type)}
                          </Badge>
                          <span className="text-sm">{action.model_id}</span>
                        </div>
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
                      <TableCell>${action.total_cost.toFixed(4)}</TableCell>
                    </TableRow>
                  ))}
                  {filteredActionAnalytics.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={8} className="text-center text-muted-foreground">
                        No action analytics data available for the selected filters
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="reliability" className="space-y-6">
          {/* Overall Stats */}
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
                  across all providers
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
                    <TableHead>Model Type</TableHead>
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
                            provider.provider === 'anthropic' ? 'border-blue-200 text-blue-700' : 
                            provider.provider === 'openai' ? 'border-green-200 text-green-700' :
                            'border-purple-200 text-purple-700'
                          }`}
                        >
                          {provider.provider}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className={getModelTypeColor(provider.model_type)}>
                          {getModelTypeIcon(provider.model_type)}
                          <span className="ml-1 capitalize">{provider.model_type}</span>
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
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}