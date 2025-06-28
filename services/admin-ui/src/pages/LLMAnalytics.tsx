import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { StatsCard } from '@/components/dashboard/StatsCard';
import { 
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { 
  Brain,
  DollarSign,
  Zap,
  TrendingUp,
  Activity,
  RefreshCw,
  AlertTriangle
} from 'lucide-react';
import { AdminAPI } from '@/lib/admin-api';
import { LLMUsageMetrics } from '@/types/admin';

export function LLMAnalytics() {
  const [llmMetrics, setLlmMetrics] = useState<LLMUsageMetrics | null>(null);
  const [modelUsage, setModelUsage] = useState<Array<{ model: string; requests: number; cost: number; avg_latency: number }>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadLLMData = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const [metrics, models] = await Promise.all([
        AdminAPI.getLLMUsageMetrics(),
        AdminAPI.getLLMModelUsage()
      ]);
      
      setLlmMetrics(metrics);
      setModelUsage(models);
    } catch (err) {
      console.error('Failed to load LLM data:', err);
      setError('Failed to load LLM analytics. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadLLMData();
  }, []);
  if (loading) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">LLM Analytics</h1>
          <p className="text-slate-500">Monitor AI model usage and performance</p>
        </div>
        <div className="flex items-center justify-center py-12">
          <RefreshCw className="h-8 w-8 animate-spin mr-3" />
          Loading LLM analytics...
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">LLM Analytics</h1>
          <p className="text-slate-500">Monitor AI model usage and performance</p>
        </div>
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">LLM Analytics</h1>
          <p className="text-slate-500">Monitor AI model usage and performance</p>
        </div>
      </div>

      {/* Overall Stats */}
      {llmMetrics && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-6">
          <StatsCard
            title="Total Requests"
            value={llmMetrics.total_requests}
            icon={<Brain className="h-5 w-5" />}
            gradient="from-purple-500 to-purple-600"
          />
          <StatsCard
            title="Total Tokens"
            value={`${(llmMetrics.total_tokens / 1000000).toFixed(1)}M`}
            icon={<Zap className="h-5 w-5" />}
            gradient="from-blue-500 to-blue-600"
          />
          <StatsCard
            title="Total Cost"
            value={`$${llmMetrics.total_cost.toFixed(2)}`}
            icon={<DollarSign className="h-5 w-5" />}
            gradient="from-green-500 to-green-600"
          />
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Top Models */}
        <Card>
          <CardHeader>
            <CardTitle>Model Usage</CardTitle>
          </CardHeader>
          <CardContent>
            {modelUsage.length === 0 ? (
              <div className="text-center py-8 text-slate-500">
                No model usage data available.
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Model</TableHead>
                    <TableHead>Requests</TableHead>
                    <TableHead>Cost</TableHead>
                    <TableHead>Latency</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {modelUsage.map((model) => (
                    <TableRow key={model.model}>
                      <TableCell>
                        <div className="font-medium text-sm">{model.model}</div>
                      </TableCell>
                      <TableCell>
                        <div className="font-medium">{model.requests.toLocaleString()}</div>
                      </TableCell>
                      <TableCell>
                        <div className="font-medium">${model.cost.toFixed(2)}</div>
                      </TableCell>
                      <TableCell>
                        <div className="text-sm">{model.avg_latency}ms</div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        {/* Usage by App */}
        <Card>
          <CardHeader>
            <CardTitle>Usage by Application</CardTitle>
          </CardHeader>
          <CardContent>
            {!llmMetrics || llmMetrics.usage_by_app.length === 0 ? (
              <div className="text-center py-8 text-slate-500">
                No application usage data available.
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Application</TableHead>
                    <TableHead>Requests</TableHead>
                    <TableHead>Cost</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {llmMetrics.usage_by_app.map((app) => (
                    <TableRow key={app.app_name}>
                      <TableCell>
                        <div className="flex items-center space-x-2">
                          <div className="w-6 h-6 bg-gradient-to-br from-green-500 to-blue-600 rounded flex items-center justify-center">
                            <span className="text-xs font-bold text-white">
                              {app.app_name.charAt(0)}
                            </span>
                          </div>
                          <span className="font-medium text-sm">{app.app_name}</span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="font-medium">{app.requests.toLocaleString()}</div>
                      </TableCell>
                      <TableCell>
                        <div className="font-medium">${app.cost.toFixed(2)}</div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}