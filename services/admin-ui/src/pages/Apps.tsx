import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
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
import { App } from '@/types/admin';
import { MoreHorizontal, CheckCircle, XCircle, Clock, RefreshCw, AlertTriangle, Plus, Settings, Edit } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import { AdminAPI } from '@/lib/admin-api';
import { toast } from 'sonner';

export function Apps() {
  const [apps, setApps] = useState<App[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Debug logging
  console.log('🔍 APPS_DEBUG: Apps component loaded with LLM Config and max-w-6xl modal v2.1.7');
  console.log('🔍 APPS_DEBUG: Build timestamp:', new Date().toISOString());
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [configureDialogOpen, setConfigureDialogOpen] = useState(false);
  const [editingApp, setEditingApp] = useState<App | null>(null);
  const [editingAppData, setEditingAppData] = useState({
    name: '',
    slug: '',
    description: '',
    category: '',
    status: 'active',
  });
  const [modelConfig, setModelConfig] = useState({
    primary_provider: '',
    primary_model_id: '',
    primary_parameters: {
      temperature: 0.7,
      max_tokens: 1000,
      top_p: 0.9,
    },
  });
  const [supportedModels, setSupportedModels] = useState<any>({});
  const [savingApp, setSavingApp] = useState(false);
  const [builders, setBuilders] = useState<Array<{ id: string; fairyname: string; email: string }>>([]);
  const [creatingApp, setCreatingApp] = useState(false);
  const [newApp, setNewApp] = useState({
    name: '',
    slug: '',
    description: '',
    category: '',
    builder_id: '',
    dust_per_use: 5,
    icon_url: '',
    website_url: '',
    demo_url: '',
    callback_url: '',
  });

  const loadApps = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await AdminAPI.getApps();
      setApps(data.apps);
    } catch (err) {
      console.error('Failed to load apps:', err);
      setError('Failed to load apps. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const loadBuilders = async () => {
    try {
      const buildersData = await AdminAPI.getBuilders();
      setBuilders(buildersData);
    } catch (err) {
      console.error('Failed to load builders:', err);
      toast.error('Failed to load builders');
    }
  };

  const loadSupportedModels = async () => {
    try {
      console.log('🔍 Loading supported models...');
      const modelsData = await AdminAPI.getSupportedModels();
      console.log('📊 Received models data:', modelsData);
      console.log('🔧 Setting supported models:', modelsData.supported_models || {});
      setSupportedModels(modelsData.supported_models || {});
    } catch (err) {
      console.error('Failed to load supported models:', err);
      toast.error('Failed to load supported models');
    }
  };

  const handleCreateApp = async () => {
    try {
      setCreatingApp(true);
      const createdApp = await AdminAPI.createApp(newApp);
      setApps(prevApps => [createdApp, ...prevApps]);
      setCreateDialogOpen(false);
      setNewApp({
        name: '',
        slug: '',
        description: '',
        category: '',
        builder_id: '',
        dust_per_use: 5,
        icon_url: '',
        website_url: '',
        demo_url: '',
        callback_url: '',
      });
      toast.success('App created successfully');
    } catch (err) {
      console.error('Failed to create app:', err);
      toast.error('Failed to create app');
    } finally {
      setCreatingApp(false);
    }
  };

  const handleConfigureApp = (app: App) => {
    setEditingApp(app);
    setEditingAppData({
      name: app.name,
      slug: app.slug,
      description: app.description,
      category: app.category,
      status: app.status === 'approved' ? 'active' : 'inactive',
    });
    
    // Set model configuration from app data
    setModelConfig({
      primary_provider: app.primary_provider || '',
      primary_model_id: app.primary_model_id || '',
      primary_parameters: {
        temperature: 0.7,
        max_tokens: 1000,
        top_p: 0.9,
      },
    });
    
    setConfigureDialogOpen(true);
  };

  const handleSaveApp = async () => {
    if (!editingApp) return;
    
    try {
      setSavingApp(true);
      
      // Save app properties
      const updatedApp = await AdminAPI.updateApp(editingApp.id, editingAppData);
      
      // Save model configuration if provider and model are selected
      if (modelConfig.primary_provider && modelConfig.primary_model_id) {
        await AdminAPI.updateAppModelConfig(editingApp.id, modelConfig);
      }
      
      // Reload apps to get all updated data including model config
      await loadApps();
      
      setConfigureDialogOpen(false);
      toast.success('App and model configuration updated successfully');
    } catch (err) {
      console.error('Failed to update app:', err);
      toast.error('Failed to update app');
    } finally {
      setSavingApp(false);
    }
  };

  const categories = [
    { value: 'productivity', label: 'Productivity' },
    { value: 'entertainment', label: 'Entertainment' },
    { value: 'education', label: 'Education' },
    { value: 'business', label: 'Business' },
    { value: 'creative', label: 'Creative' },
    { value: 'utilities', label: 'Utilities' },
    { value: 'games', label: 'Games' },
    { value: 'other', label: 'Other' },
  ];

  useEffect(() => {
    loadApps();
    loadBuilders();
    loadSupportedModels();
  }, []);

  const getStatusIcon = (status: string) => {
    // Convert old status to new active/inactive model
    const isActive = status === 'approved';
    return isActive ? 
      <CheckCircle className="h-4 w-4 text-green-600" /> : 
      <XCircle className="h-4 w-4 text-red-600" />;
  };

  const getStatusDisplay = (status: string) => {
    return status === 'approved' ? 'active' : 'inactive';
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">Apps</h1>
          <p className="text-slate-500">Manage applications and review submissions</p>
        </div>
        <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="h-4 w-4 mr-2" />
              Create App
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-2xl">
            <DialogHeader>
              <DialogTitle>Create New App</DialogTitle>
              <DialogDescription>
                Create a new application for the fairydust platform
              </DialogDescription>
            </DialogHeader>
            <div className="grid grid-cols-2 gap-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="name">App Name *</Label>
                <Input
                  id="name"
                  value={newApp.name}
                  onChange={(e) => setNewApp(prev => ({ ...prev, name: e.target.value }))}
                  placeholder="e.g., Recipe Generator"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="slug">Slug *</Label>
                <Input
                  id="slug"
                  value={newApp.slug}
                  onChange={(e) => setNewApp(prev => ({ ...prev, slug: e.target.value }))}
                  placeholder="e.g., recipe-generator"
                />
              </div>
              <div className="space-y-2 col-span-2">
                <Label htmlFor="description">Description *</Label>
                <Textarea
                  id="description"
                  value={newApp.description}
                  onChange={(e) => setNewApp(prev => ({ ...prev, description: e.target.value }))}
                  placeholder="Describe what your app does..."
                  rows={3}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="category">Category *</Label>
                <Select value={newApp.category} onValueChange={(value) => setNewApp(prev => ({ ...prev, category: value }))}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select category" />
                  </SelectTrigger>
                  <SelectContent>
                    {categories.map((category) => (
                      <SelectItem key={category.value} value={category.value}>
                        {category.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="builder">Builder *</Label>
                <Select value={newApp.builder_id} onValueChange={(value) => setNewApp(prev => ({ ...prev, builder_id: value }))}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select builder" />
                  </SelectTrigger>
                  <SelectContent>
                    {builders.map((builder) => (
                      <SelectItem key={builder.id} value={builder.id}>
                        {builder.fairyname} ({builder.email})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="dust_per_use">DUST per Use</Label>
                <Input
                  id="dust_per_use"
                  type="number"
                  min="1"
                  max="100"
                  value={newApp.dust_per_use}
                  onChange={(e) => setNewApp(prev => ({ ...prev, dust_per_use: parseInt(e.target.value) || 5 }))}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="icon_url">Icon URL</Label>
                <Input
                  id="icon_url"
                  value={newApp.icon_url}
                  onChange={(e) => setNewApp(prev => ({ ...prev, icon_url: e.target.value }))}
                  placeholder="https://example.com/icon.png"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="website_url">Website URL</Label>
                <Input
                  id="website_url"
                  value={newApp.website_url}
                  onChange={(e) => setNewApp(prev => ({ ...prev, website_url: e.target.value }))}
                  placeholder="https://example.com"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="demo_url">Demo URL</Label>
                <Input
                  id="demo_url"
                  value={newApp.demo_url}
                  onChange={(e) => setNewApp(prev => ({ ...prev, demo_url: e.target.value }))}
                  placeholder="https://demo.example.com"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="callback_url">Callback URL</Label>
                <Input
                  id="callback_url"
                  value={newApp.callback_url}
                  onChange={(e) => setNewApp(prev => ({ ...prev, callback_url: e.target.value }))}
                  placeholder="https://api.example.com/callback"
                />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setCreateDialogOpen(false)}>
                Cancel
              </Button>
              <Button 
                onClick={handleCreateApp} 
                disabled={creatingApp || !newApp.name || !newApp.slug || !newApp.description || !newApp.category || !newApp.builder_id}
              >
                {creatingApp ? 'Creating...' : 'Create App'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      {/* Apps Table */}
      <Card>
        <CardHeader>
          <CardTitle>Applications ({apps.length})</CardTitle>
        </CardHeader>
        <CardContent>
          {loading && (
            <div className="flex items-center justify-center py-8">
              <RefreshCw className="h-6 w-6 animate-spin mr-2" />
              Loading apps...
            </div>
          )}
          
          {error && (
            <Alert variant="destructive" className="mb-4">
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
          
          {!loading && !error && apps.length === 0 && (
            <div className="text-center py-8 text-slate-500">
              No apps found.
            </div>
          )}
          
          {!loading && !error && apps.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>App</TableHead>
                <TableHead>Slug</TableHead>
                <TableHead>Category</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Model</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {apps.map((app) => (
                <TableRow key={app.id}>
                  <TableCell>
                    <div className="flex items-center space-x-3">
                      <div className="w-10 h-10 bg-gradient-to-br from-green-500 to-blue-600 rounded-lg flex items-center justify-center">
                        <span className="text-sm font-bold text-white">
                          {app.name.charAt(0).toUpperCase()}
                        </span>
                      </div>
                      <div>
                        <div className="font-medium">{app.name}</div>
                        <div className="text-sm text-slate-500 max-w-xs truncate">
                          {app.description}
                        </div>
                      </div>
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="text-sm font-mono text-slate-700 max-w-[200px] truncate" title={app.slug}>
                      {app.slug}
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className="capitalize">
                      {app.category}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center space-x-2">
                      {getStatusIcon(app.status)}
                      <Badge 
                        variant={app.status === 'approved' ? 'default' : 'destructive'}
                        className="capitalize"
                      >
                        {getStatusDisplay(app.status)}
                      </Badge>
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="text-sm">
                      {app.primary_model_id ? (
                        <div>
                          <div className="font-mono text-slate-700">{app.primary_model_id}</div>
                          <div className="text-xs text-slate-500 capitalize">{app.primary_provider}</div>
                        </div>
                      ) : (
                        <div className="text-slate-400 italic">Not configured</div>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center space-x-2">
                      <Button 
                        variant="ghost" 
                        size="sm"
                        onClick={() => handleConfigureApp(app)}
                        className="text-blue-600 hover:text-blue-800"
                      >
                        <Settings className="h-4 w-4 mr-1" />
                        Configure
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          )}
        </CardContent>
      </Card>

      {/* Configure App Dialog */}
      <Dialog open={configureDialogOpen} onOpenChange={setConfigureDialogOpen}>
        <DialogContent className="max-w-6xl">
          <DialogHeader>
            <DialogTitle>Edit App: {editingApp?.name}</DialogTitle>
            <DialogDescription>
              Edit app properties, settings, and configuration
            </DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="edit-name">App Name *</Label>
              <Input
                id="edit-name"
                value={editingAppData.name}
                onChange={(e) => setEditingAppData(prev => ({ ...prev, name: e.target.value }))}
                placeholder="e.g., Recipe Generator"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-slug">Slug *</Label>
              <Input
                id="edit-slug"
                value={editingAppData.slug}
                onChange={(e) => setEditingAppData(prev => ({ ...prev, slug: e.target.value }))}
                placeholder="e.g., recipe-generator"
              />
            </div>
            <div className="space-y-2 col-span-2">
              <Label htmlFor="edit-description">Description *</Label>
              <Textarea
                id="edit-description"
                value={editingAppData.description}
                onChange={(e) => setEditingAppData(prev => ({ ...prev, description: e.target.value }))}
                placeholder="Describe what your app does..."
                rows={3}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-category">Category *</Label>
              <Select value={editingAppData.category} onValueChange={(value) => setEditingAppData(prev => ({ ...prev, category: value }))}>
                <SelectTrigger>
                  <SelectValue placeholder="Select category" />
                </SelectTrigger>
                <SelectContent>
                  {categories.map((category) => (
                    <SelectItem key={category.value} value={category.value}>
                      {category.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-status">Status *</Label>
              <Select value={editingAppData.status} onValueChange={(value) => setEditingAppData(prev => ({ ...prev, status: value }))}>
                <SelectTrigger>
                  <SelectValue placeholder="Select status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="active">Active</SelectItem>
                  <SelectItem value="inactive">Inactive</SelectItem>
                </SelectContent>
              </Select>
            </div>
            
            <div className="space-y-2 col-span-2">
              <Label>LLM Model Configuration</Label>
              <div className="grid grid-cols-2 gap-4 p-4 bg-slate-50 rounded-lg">
                <div className="space-y-2">
                  <Label htmlFor="edit-provider">Provider</Label>
                  <Select 
                    value={modelConfig.primary_provider} 
                    onValueChange={(value) => setModelConfig(prev => ({ 
                      ...prev, 
                      primary_provider: value,
                      primary_model_id: '' // Reset model when provider changes
                    }))}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select provider" />
                    </SelectTrigger>
                    <SelectContent>
                      {Object.keys(supportedModels).map((provider) => (
                        <SelectItem key={provider} value={provider}>
                          {provider.charAt(0).toUpperCase() + provider.slice(1)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                
                <div className="space-y-2">
                  <Label htmlFor="edit-model">Model</Label>
                  <Select 
                    value={modelConfig.primary_model_id} 
                    onValueChange={(value) => setModelConfig(prev => ({ ...prev, primary_model_id: value }))}
                    disabled={!modelConfig.primary_provider}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select model" />
                    </SelectTrigger>
                    <SelectContent>
                      {modelConfig.primary_provider && supportedModels[modelConfig.primary_provider] && 
                        Object.keys(supportedModels[modelConfig.primary_provider]).map((modelId) => (
                          <SelectItem key={modelId} value={modelId}>
                            {modelId}
                          </SelectItem>
                        ))
                      }
                    </SelectContent>
                  </Select>
                </div>
                
                <div className="space-y-2">
                  <Label htmlFor="edit-temperature">Temperature</Label>
                  <Input
                    id="edit-temperature"
                    type="number"
                    min="0"
                    max="2"
                    step="0.1"
                    value={modelConfig.primary_parameters.temperature}
                    onChange={(e) => setModelConfig(prev => ({
                      ...prev,
                      primary_parameters: {
                        ...prev.primary_parameters,
                        temperature: parseFloat(e.target.value) || 0.7
                      }
                    }))}
                  />
                </div>
                
                <div className="space-y-2">
                  <Label htmlFor="edit-max-tokens">Max Tokens</Label>
                  <Input
                    id="edit-max-tokens"
                    type="number"
                    min="1"
                    max="4000"
                    value={modelConfig.primary_parameters.max_tokens}
                    onChange={(e) => setModelConfig(prev => ({
                      ...prev,
                      primary_parameters: {
                        ...prev.primary_parameters,
                        max_tokens: parseInt(e.target.value) || 1000
                      }
                    }))}
                  />
                </div>
              </div>
            </div>
            
            <div className="space-y-2 col-span-2">
              <Label>Per-Action DUST Costs</Label>
              <div className="p-4 bg-slate-50 rounded-lg">
                <div className="text-sm text-slate-600">
                  Configure individual DUST costs per action. This will replace the single "dust_per_use" value with granular pricing.
                </div>
                <div className="mt-2">
                  <div className="text-xs text-amber-600">
                    ⚠️ Coming Soon: Per-action cost management interface
                  </div>
                </div>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfigureDialogOpen(false)}>
              Cancel
            </Button>
            <Button 
              onClick={handleSaveApp}
              disabled={savingApp || !editingAppData.name || !editingAppData.slug || !editingAppData.description || !editingAppData.category}
            >
              {savingApp ? 'Saving...' : 'Save Changes'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}