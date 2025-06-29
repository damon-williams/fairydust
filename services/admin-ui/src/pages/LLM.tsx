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
import { Switch } from '@/components/ui/switch';
import { 
  Brain, 
  DollarSign, 
  Clock, 
  TrendingUp, 
  Settings,
  AlertTriangle,
  RefreshCw,
  Plus,
  Trash2,
  Save
} from 'lucide-react';
import { AdminAPI } from '@/lib/admin-api';
import { toast } from 'sonner';
import { formatDistanceToNow } from 'date-fns';

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

interface AppConfig {
  app_id: string;
  app_name: string;
  app_slug: string;
  primary_provider: string;
  primary_model_id: string;
  primary_parameters: any;
  fallback_models: any[];
  cost_limits: any;
  feature_flags: any;
  updated_at: string;
}

interface ModelUsage {
  model: string;
  requests: number;
  cost: number;
  avg_latency: number;
}

interface ConfigFormData {
  primary_provider: string;
  primary_model_id: string;
  primary_parameters: {
    temperature: number;
    max_tokens: number;
    top_p: number;
  };
  fallback_models: Array<{
    provider: string;
    model_id: string;
    trigger: string;
    parameters: {
      temperature: number;
      max_tokens: number;
    };
  }>;
  cost_limits: {
    per_request_max: number;
    daily_max: number;
    monthly_max: number;
  };
  feature_flags: {
    streaming_enabled: boolean;
    cache_responses: boolean;
    log_prompts: boolean;
  };
}

export function LLM() {
  const [metrics, setMetrics] = useState<LLMUsageMetrics | null>(null);
  const [appConfigs, setAppConfigs] = useState<AppConfig[]>([]);
  const [modelUsage, setModelUsage] = useState<ModelUsage[]>([]);
  const [availableModels, setAvailableModels] = useState<Record<string, string[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [timeframe, setTimeframe] = useState('7d');
  const [configDialogOpen, setConfigDialogOpen] = useState(false);
  const [selectedConfig, setSelectedConfig] = useState<AppConfig | null>(null);
  const [configForm, setConfigForm] = useState<ConfigFormData>({
    primary_provider: 'anthropic',
    primary_model_id: 'claude-3-5-haiku-20241022',
    primary_parameters: {
      temperature: 0.8,
      max_tokens: 150,
      top_p: 0.9
    },
    fallback_models: [],
    cost_limits: {
      per_request_max: 0.05,
      daily_max: 10.0,
      monthly_max: 100.0
    },
    feature_flags: {
      streaming_enabled: true,
      cache_responses: true,
      log_prompts: false
    }
  });

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const [metricsData, configsData, modelUsageData, modelsData] = await Promise.all([
        AdminAPI.getLLMUsageMetrics(timeframe),
        AdminAPI.getLLMAppConfigs(),
        AdminAPI.getLLMModelUsage(),
        AdminAPI.getAvailableModels(),
      ]);
      
      setMetrics(metricsData);
      setAppConfigs(configsData);
      setModelUsage(modelUsageData);
      setAvailableModels(modelsData);
    } catch (err) {
      console.error('Failed to load LLM data:', err);
      setError('Failed to load LLM data. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const openConfigDialog = (config: AppConfig) => {
    setSelectedConfig(config);
    setConfigForm({
      primary_provider: config.primary_provider || 'anthropic',
      primary_model_id: config.primary_model_id || 'claude-3-5-haiku-20241022',
      primary_parameters: config.primary_parameters || {
        temperature: 0.8,
        max_tokens: 150,
        top_p: 0.9
      },
      fallback_models: config.fallback_models || [],
      cost_limits: config.cost_limits || {
        per_request_max: 0.05,
        daily_max: 10.0,
        monthly_max: 100.0
      },
      feature_flags: config.feature_flags || {
        streaming_enabled: true,
        cache_responses: true,
        log_prompts: false
      }
    });
    setConfigDialogOpen(true);
  };

  const saveConfig = async () => {
    if (!selectedConfig) return;
    
    try {
      await AdminAPI.updateLLMAppConfig(selectedConfig.app_id, configForm);
      toast.success('Configuration updated successfully');
      setConfigDialogOpen(false);
      loadData(); // Reload to show updated config
    } catch (err) {
      console.error('Failed to update config:', err);
      toast.error('Failed to update configuration');
    }
  };

  const addFallbackModel = () => {
    setConfigForm((prev: ConfigFormData) => ({
      ...prev,
      fallback_models: [
        ...prev.fallback_models,
        {
          provider: 'openai',
          model_id: 'gpt-4o-mini',
          trigger: 'provider_error',
          parameters: { temperature: 0.8, max_tokens: 150 }
        }
      ]
    }));
  };

  const removeFallbackModel = (index: number) => {
    setConfigForm((prev: ConfigFormData) => ({
      ...prev,
      fallback_models: prev.fallback_models.filter((_: any, i: number) => i !== index)
    }));
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

      <Tabs defaultValue="overview" className="space-y-6">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="models">Model Usage</TabsTrigger>
          <TabsTrigger value="apps">App Usage</TabsTrigger>
          <TabsTrigger value="config">Configuration</TabsTrigger>
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

        <TabsContent value="config" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>App Model Configurations</CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>App</TableHead>
                    <TableHead>Provider</TableHead>
                    <TableHead>Model</TableHead>
                    <TableHead>Last Updated</TableHead>
                    <TableHead>Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {appConfigs.map((config) => (
                    <TableRow key={config.app_id}>
                      <TableCell>
                        <div>
                          <div className="font-medium">{config.app_name}</div>
                          <div className="text-sm text-muted-foreground">{config.app_slug}</div>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className="capitalize">
                          {config.primary_provider || 'Not configured'}
                        </Badge>
                      </TableCell>
                      <TableCell>{config.primary_model_id || 'Not configured'}</TableCell>
                      <TableCell>
                        {config.updated_at ? 
                          formatDistanceToNow(new Date(config.updated_at), { addSuffix: true }) : 
                          'Never'
                        }
                      </TableCell>
                      <TableCell>
                        <Button 
                          size="sm" 
                          onClick={() => openConfigDialog(config)}
                        >
                          <Settings className="h-4 w-4 mr-2" />
                          Configure
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Configuration Dialog */}
      <Dialog open={configDialogOpen} onOpenChange={setConfigDialogOpen}>
        <DialogContent className="max-w-4xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Configure {selectedConfig?.app_name}</DialogTitle>
            <DialogDescription>
              Manage LLM settings, fallback models, and cost limits for this app
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-6">
            {/* Primary Model */}
            <div className="space-y-4">
              <h4 className="font-medium">Primary Model</h4>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Provider</Label>
                  <Select 
                    value={configForm.primary_provider} 
                    onValueChange={(value) => setConfigForm((prev: ConfigFormData) => ({ ...prev, primary_provider: value }))}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="anthropic">Anthropic</SelectItem>
                      <SelectItem value="openai">OpenAI</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Model</Label>
                  <Select 
                    value={configForm.primary_model_id} 
                    onValueChange={(value) => setConfigForm((prev: ConfigFormData) => ({ ...prev, primary_model_id: value }))}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {availableModels[configForm.primary_provider]?.map(model => (
                        <SelectItem key={model} value={model}>{model}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              
              <div className="grid grid-cols-3 gap-4">
                <div className="space-y-2">
                  <Label>Temperature</Label>
                  <Input 
                    type="number" 
                    step="0.1" 
                    min="0" 
                    max="2"
                    value={configForm.primary_parameters?.temperature || 0.8}
                    onChange={(e) => setConfigForm((prev: ConfigFormData) => ({
                      ...prev,
                      primary_parameters: {
                        ...prev.primary_parameters,
                        temperature: parseFloat(e.target.value)
                      }
                    }))}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Max Tokens</Label>
                  <Input 
                    type="number" 
                    min="1" 
                    max="4000"
                    value={configForm.primary_parameters?.max_tokens || 150}
                    onChange={(e) => setConfigForm((prev: ConfigFormData) => ({
                      ...prev,
                      primary_parameters: {
                        ...prev.primary_parameters,
                        max_tokens: parseInt(e.target.value)
                      }
                    }))}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Top P</Label>
                  <Input 
                    type="number" 
                    step="0.1" 
                    min="0" 
                    max="1"
                    value={configForm.primary_parameters?.top_p || 0.9}
                    onChange={(e) => setConfigForm((prev: ConfigFormData) => ({
                      ...prev,
                      primary_parameters: {
                        ...prev.primary_parameters,
                        top_p: parseFloat(e.target.value)
                      }
                    }))}
                  />
                </div>
              </div>
            </div>

            {/* Cost Limits */}
            <div className="space-y-4">
              <h4 className="font-medium">Cost Limits</h4>
              <div className="grid grid-cols-3 gap-4">
                <div className="space-y-2">
                  <Label>Per Request Max ($)</Label>
                  <Input 
                    type="number" 
                    step="0.01"
                    value={configForm.cost_limits?.per_request_max || 0.05}
                    onChange={(e) => setConfigForm((prev: ConfigFormData) => ({
                      ...prev,
                      cost_limits: {
                        ...prev.cost_limits,
                        per_request_max: parseFloat(e.target.value)
                      }
                    }))}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Daily Max ($)</Label>
                  <Input 
                    type="number" 
                    step="0.01"
                    value={configForm.cost_limits?.daily_max || 10.0}
                    onChange={(e) => setConfigForm((prev: ConfigFormData) => ({
                      ...prev,
                      cost_limits: {
                        ...prev.cost_limits,
                        daily_max: parseFloat(e.target.value)
                      }
                    }))}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Monthly Max ($)</Label>
                  <Input 
                    type="number" 
                    step="0.01"
                    value={configForm.cost_limits?.monthly_max || 100.0}
                    onChange={(e) => setConfigForm((prev: ConfigFormData) => ({
                      ...prev,
                      cost_limits: {
                        ...prev.cost_limits,
                        monthly_max: parseFloat(e.target.value)
                      }
                    }))}
                  />
                </div>
              </div>
            </div>

            {/* Feature Flags */}
            <div className="space-y-4">
              <h4 className="font-medium">Feature Flags</h4>
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <Label htmlFor="streaming">Streaming Enabled</Label>
                  <Switch 
                    id="streaming"
                    checked={configForm.feature_flags?.streaming_enabled || false}
                    onCheckedChange={(checked) => setConfigForm((prev: ConfigFormData) => ({
                      ...prev,
                      feature_flags: {
                        ...prev.feature_flags,
                        streaming_enabled: checked
                      }
                    }))}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <Label htmlFor="cache">Cache Responses</Label>
                  <Switch 
                    id="cache"
                    checked={configForm.feature_flags?.cache_responses || false}
                    onCheckedChange={(checked) => setConfigForm((prev: ConfigFormData) => ({
                      ...prev,
                      feature_flags: {
                        ...prev.feature_flags,
                        cache_responses: checked
                      }
                    }))}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <Label htmlFor="log">Log Prompts</Label>
                  <Switch 
                    id="log"
                    checked={configForm.feature_flags?.log_prompts || false}
                    onCheckedChange={(checked) => setConfigForm((prev: ConfigFormData) => ({
                      ...prev,
                      feature_flags: {
                        ...prev.feature_flags,
                        log_prompts: checked
                      }
                    }))}
                  />
                </div>
              </div>
            </div>

            {/* Fallback Models */}
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h4 className="font-medium">Fallback Models</h4>
                <Button size="sm" onClick={addFallbackModel}>
                  <Plus className="h-4 w-4 mr-2" />
                  Add Fallback
                </Button>
              </div>
              {configForm.fallback_models?.map((fallback: ConfigFormData['fallback_models'][0], index: number) => (
                <div key={index} className="border rounded-lg p-4 space-y-4">
                  <div className="flex items-center justify-between">
                    <h5 className="font-medium">Fallback {index + 1}</h5>
                    <Button 
                      size="sm" 
                      variant="outline" 
                      onClick={() => removeFallbackModel(index)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                  <div className="grid grid-cols-3 gap-4">
                    <div className="space-y-2">
                      <Label>Provider</Label>
                      <Select 
                        value={fallback.provider} 
                        onValueChange={(value) => {
                          const newFallbacks = [...configForm.fallback_models];
                          newFallbacks[index].provider = value;
                          setConfigForm((prev: ConfigFormData) => ({ ...prev, fallback_models: newFallbacks }));
                        }}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="anthropic">Anthropic</SelectItem>
                          <SelectItem value="openai">OpenAI</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label>Model</Label>
                      <Select 
                        value={fallback.model_id} 
                        onValueChange={(value) => {
                          const newFallbacks = [...configForm.fallback_models];
                          newFallbacks[index].model_id = value;
                          setConfigForm((prev: ConfigFormData) => ({ ...prev, fallback_models: newFallbacks }));
                        }}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {availableModels[fallback.provider]?.map(model => (
                            <SelectItem key={model} value={model}>{model}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label>Trigger</Label>
                      <Select 
                        value={fallback.trigger} 
                        onValueChange={(value) => {
                          const newFallbacks = [...configForm.fallback_models];
                          newFallbacks[index].trigger = value;
                          setConfigForm((prev: ConfigFormData) => ({ ...prev, fallback_models: newFallbacks }));
                        }}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="provider_error">Provider Error</SelectItem>
                          <SelectItem value="cost_threshold_exceeded">Cost Threshold Exceeded</SelectItem>
                          <SelectItem value="rate_limit">Rate Limit</SelectItem>
                          <SelectItem value="model_unavailable">Model Unavailable</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setConfigDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={saveConfig}>
              <Save className="h-4 w-4 mr-2" />
              Save Configuration
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}