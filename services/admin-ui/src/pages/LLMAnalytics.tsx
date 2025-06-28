import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
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
  Activity
} from 'lucide-react';

// Mock LLM usage data
const mockLLMStats = {
  total_requests: 12450,
  total_tokens: 8967234,
  total_cost: 124.56,
  requests_today: 567,
  avg_tokens_per_request: 720,
};

const mockTopModels = [
  {
    model: 'claude-3-5-sonnet-20241022',
    provider: 'anthropic',
    requests: 8234,
    tokens: 5923847,
    cost: 89.23,
    avg_latency: 1240,
  },
  {
    model: 'claude-3-haiku-20240307',
    provider: 'anthropic',
    requests: 3456,
    tokens: 2234567,
    cost: 28.45,
    avg_latency: 850,
  },
  {
    model: 'gpt-4o-mini',
    provider: 'openai',
    requests: 760,
    tokens: 808820,
    cost: 6.88,
    avg_latency: 980,
  },
];

const mockUsageByApp = [
  {
    app_name: 'Story Creator',
    slug: 'fairydust-story',
    requests: 4567,
    tokens: 3234567,
    cost: 45.67,
    avg_cost_per_request: 0.01,
  },
  {
    app_name: 'Recipe Generator',
    slug: 'fairydust-recipe',
    requests: 3234,
    tokens: 2567890,
    cost: 38.90,
    avg_cost_per_request: 0.012,
  },
  {
    app_name: 'Inspiration Generator',
    slug: 'fairydust-inspire',
    requests: 2890,
    tokens: 1234567,
    cost: 23.45,
    avg_cost_per_request: 0.008,
  },
  {
    app_name: 'Activity Finder',
    slug: 'fairydust-activity',
    requests: 1759,
    tokens: 1930210,
    cost: 16.54,
    avg_cost_per_request: 0.009,
  },
];

export function LLMAnalytics() {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">LLM Analytics</h1>
          <p className="text-slate-500">Monitor AI model usage and performance</p>
        </div>
        <Badge className="bg-blue-100 text-blue-800 hover:bg-blue-100">
          NEW
        </Badge>
      </div>

      {/* Overall Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-6">
        <StatsCard
          title="Total Requests"
          value={mockLLMStats.total_requests}
          change={{ value: 23, trend: 'up', period: 'last week' }}
          icon={<Brain className="h-5 w-5" />}
          gradient="from-purple-500 to-purple-600"
        />
        <StatsCard
          title="Total Tokens"
          value={`${(mockLLMStats.total_tokens / 1000000).toFixed(1)}M`}
          change={{ value: 18, trend: 'up', period: 'last week' }}
          icon={<Zap className="h-5 w-5" />}
          gradient="from-blue-500 to-blue-600"
        />
        <StatsCard
          title="Total Cost"
          value={`$${mockLLMStats.total_cost}`}
          change={{ value: 12, trend: 'up', period: 'last week' }}
          icon={<DollarSign className="h-5 w-5" />}
          gradient="from-green-500 to-green-600"
        />
        <StatsCard
          title="Requests Today"
          value={mockLLMStats.requests_today}
          icon={<Activity className="h-5 w-5" />}
          gradient="from-orange-500 to-orange-600"
        />
        <StatsCard
          title="Avg Tokens/Request"
          value={mockLLMStats.avg_tokens_per_request}
          icon={<TrendingUp className="h-5 w-5" />}
          gradient="from-cyan-500 to-cyan-600"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Top Models */}
        <Card>
          <CardHeader>
            <CardTitle>Top Models by Usage</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Model</TableHead>
                  <TableHead>Requests</TableHead>
                  <TableHead>Tokens</TableHead>
                  <TableHead>Cost</TableHead>
                  <TableHead>Latency</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {mockTopModels.map((model, index) => (
                  <TableRow key={model.model}>
                    <TableCell>
                      <div>
                        <div className="font-medium text-sm">{model.model}</div>
                        <Badge variant="outline" className="text-xs capitalize mt-1">
                          {model.provider}
                        </Badge>
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="font-medium">{model.requests.toLocaleString()}</div>
                    </TableCell>
                    <TableCell>
                      <div className="text-sm">{(model.tokens / 1000000).toFixed(1)}M</div>
                    </TableCell>
                    <TableCell>
                      <div className="font-medium">${model.cost}</div>
                    </TableCell>
                    <TableCell>
                      <div className="text-sm">{model.avg_latency}ms</div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        {/* Usage by App */}
        <Card>
          <CardHeader>
            <CardTitle>Usage by Application</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Application</TableHead>
                  <TableHead>Requests</TableHead>
                  <TableHead>Cost</TableHead>
                  <TableHead>Avg/Request</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {mockUsageByApp.map((app) => (
                  <TableRow key={app.slug}>
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
                      <div className="font-medium">${app.cost}</div>
                    </TableCell>
                    <TableCell>
                      <div className="text-sm">${app.avg_cost_per_request.toFixed(3)}</div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>

      {/* Cost Breakdown */}
      <Card>
        <CardHeader>
          <CardTitle>Cost Analysis</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="text-center">
              <div className="text-2xl font-bold text-green-600">$89.23</div>
              <div className="text-sm text-slate-500">Anthropic (Claude)</div>
              <div className="text-xs text-slate-400">71.7% of total</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-blue-600">$6.88</div>
              <div className="text-sm text-slate-500">OpenAI (GPT)</div>
              <div className="text-xs text-slate-400">5.5% of total</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-purple-600">$28.45</div>
              <div className="text-sm text-slate-500">Other costs</div>
              <div className="text-xs text-slate-400">22.8% of total</div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}