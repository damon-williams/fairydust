import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Activity, RefreshCw, AlertTriangle, CheckCircle, Key, Copy, Check } from 'lucide-react';
import { SystemHealth } from '@/types/admin';
import { AdminAPI } from '@/lib/admin-api';

export function SystemStatus() {
  const [systemHealth, setSystemHealth] = useState<SystemHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date());
  
  // Service token state
  const [serviceToken, setServiceToken] = useState<string>('');
  const [tokenGenerating, setTokenGenerating] = useState(false);
  const [tokenCopied, setTokenCopied] = useState(false);
  const [tokenError, setTokenError] = useState<string | null>(null);

  const loadSystemHealth = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const healthData = await AdminAPI.getSystemHealth();
      setSystemHealth(healthData);
      setLastUpdated(new Date());
    } catch (err) {
      console.error('Failed to load system health:', err);
      setError('Failed to load system health. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const generateServiceToken = async () => {
    try {
      setTokenGenerating(true);
      setTokenError(null);
      
      const response = await AdminAPI.generateServiceToken();
      setServiceToken(response.token);
    } catch (err) {
      console.error('Failed to generate service token:', err);
      setTokenError('Failed to generate service token. Please try again.');
    } finally {
      setTokenGenerating(false);
    }
  };

  const copyTokenToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(serviceToken);
      setTokenCopied(true);
      setTimeout(() => setTokenCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy token:', err);
    }
  };

  useEffect(() => {
    loadSystemHealth();
    
    // Auto-refresh every 30 seconds
    const interval = setInterval(loadSystemHealth, 30000);
    return () => clearInterval(interval);
  }, []);

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'online':
        return <CheckCircle className="h-5 w-5 text-green-500" />;
      case 'degraded':
        return <AlertTriangle className="h-5 w-5 text-yellow-500" />;
      case 'offline':
        return <AlertTriangle className="h-5 w-5 text-red-500" />;
      default:
        return <Activity className="h-5 w-5 text-gray-500" />;
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'online':
        return <Badge className="bg-green-100 text-green-800">Online</Badge>;
      case 'degraded':
        return <Badge className="bg-yellow-100 text-yellow-800">Degraded</Badge>;
      case 'offline':
        return <Badge className="bg-red-100 text-red-800">Offline</Badge>;
      default:
        return <Badge className="bg-gray-100 text-gray-800">Unknown</Badge>;
    }
  };

  const services = systemHealth ? [
    { name: 'Identity Service', key: 'identity', description: 'User authentication and management' },
    { name: 'Ledger Service', key: 'ledger', description: 'DUST transactions and balances' },
    { name: 'Apps Service', key: 'apps', description: 'App marketplace and LLM management' },
    { name: 'Content Service', key: 'content', description: 'User-generated content storage' },
    { name: 'Admin Portal', key: 'admin', description: 'Administrative interface' },
  ] : [];

  const overallStatus = systemHealth ? 
    Object.values(systemHealth).every(status => status === 'online') ? 'online' :
    Object.values(systemHealth).some(status => status === 'offline') ? 'offline' :
    'degraded' : 'unknown';

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center space-y-4">
          <RefreshCw className="h-8 w-8 animate-spin mx-auto text-slate-400" />
          <p className="text-slate-500">Loading system status...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">System Status</h1>
          <p className="text-slate-500">Monitor the health of all fairydust services</p>
        </div>
        <div className="flex items-center space-x-4">
          <span className="text-sm text-slate-500">
            Last updated: {lastUpdated.toLocaleTimeString()}
          </span>
          <Button 
            variant="outline" 
            size="sm" 
            onClick={loadSystemHealth}
            disabled={loading}
          >
            <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>
      </div>

      {error && (
        <Alert className="border-red-200 bg-red-50">
          <AlertTriangle className="h-4 w-4 text-red-600" />
          <AlertDescription className="text-red-700">
            {error}
          </AlertDescription>
        </Alert>
      )}

      {/* Overall Status */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center space-x-2">
            {getStatusIcon(overallStatus)}
            <span>Overall System Status</span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            <span className="text-lg font-medium">Fairydust Platform</span>
            {getStatusBadge(overallStatus)}
          </div>
          <p className="text-slate-500 mt-2">
            {overallStatus === 'online' && 'All systems are operational'}
            {overallStatus === 'degraded' && 'Some services are experiencing issues'}
            {overallStatus === 'offline' && 'Critical services are offline'}
          </p>
        </CardContent>
      </Card>

      {/* Individual Services */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {services.map((service) => {
          const status = systemHealth?.[service.key as keyof SystemHealth] || 'unknown';
          return (
            <Card key={service.key}>
              <CardHeader>
                <CardTitle className="flex items-center justify-between">
                  <div className="flex items-center space-x-2">
                    {getStatusIcon(status)}
                    <span className="text-base">{service.name}</span>
                  </div>
                  {getStatusBadge(status)}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-slate-500">{service.description}</p>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Service Token Management */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center space-x-2">
            <Key className="h-5 w-5" />
            <span>Service Token Management</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-slate-600">
            Generate a long-lived JWT token for service-to-service authentication (apps ↔ ledger).
            This token should be set as the <code className="bg-slate-100 px-1 rounded">SERVICE_JWT_TOKEN</code> environment variable in the apps service.
          </p>
          
          {tokenError && (
            <Alert className="border-red-200 bg-red-50">
              <AlertTriangle className="h-4 w-4 text-red-600" />
              <AlertDescription className="text-red-700">
                {tokenError}
              </AlertDescription>
            </Alert>
          )}

          <div className="flex space-x-2">
            <Button 
              onClick={generateServiceToken} 
              disabled={tokenGenerating}
              variant="outline"
            >
              <Key className={`h-4 w-4 mr-2 ${tokenGenerating ? 'animate-spin' : ''}`} />
              {tokenGenerating ? 'Generating...' : 'Generate Service Token'}
            </Button>
            
            {serviceToken && (
              <Button 
                onClick={copyTokenToClipboard} 
                variant="secondary"
                disabled={tokenCopied}
              >
                {tokenCopied ? (
                  <>
                    <Check className="h-4 w-4 mr-2" />
                    Copied!
                  </>
                ) : (
                  <>
                    <Copy className="h-4 w-4 mr-2" />
                    Copy Token
                  </>
                )}
              </Button>
            )}
          </div>

          {serviceToken && (
            <div className="space-y-2">
              <label className="text-sm font-medium text-slate-700">Generated Token:</label>
              <div className="bg-slate-50 p-3 rounded border font-mono text-xs break-all">
                {serviceToken}
              </div>
              <div className="text-sm text-slate-500">
                <strong>Instructions:</strong>
                <ol className="list-decimal ml-4 mt-1 space-y-1">
                  <li>Copy the token above</li>
                  <li>Go to Railway dashboard → fairydust-apps service → Variables</li>
                  <li>Add: <code>SERVICE_JWT_TOKEN = [paste token]</code></li>
                  <li>Redeploy the apps service</li>
                </ol>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}