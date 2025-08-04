import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
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
import { App, ActionPricing } from '@/types/admin';
import { MoreHorizontal, CheckCircle, XCircle, Clock, RefreshCw, AlertTriangle, Plus, Settings, Edit, Trash2 } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import { AdminAPI } from '@/lib/admin-api';
import { toast } from 'sonner';

export function Apps() {
  const navigate = useNavigate();
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
      image_models: {
        standard_model: 'black-forest-labs/flux-1.1-pro',
        reference_model: 'runwayml/gen4-image',
      },
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
    icon_url: '',
  });

  // Action Pricing state
  const [actionPricing, setActionPricing] = useState<ActionPricing[]>([]);
  const [pricingLoading, setPricingLoading] = useState(false);
  const [editingPricing, setEditingPricing] = useState<ActionPricing | null>(null);
  const [pricingDialogOpen, setPricingDialogOpen] = useState(false);
  const [isCreatingAction, setIsCreatingAction] = useState(false);

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
        icon_url: '',
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
        image_models: {
          standard_model: 'black-forest-labs/flux-1.1-pro',
          reference_model: 'runwayml/gen4-image',
        },
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

  // Action Pricing functions
  const loadActionPricing = async () => {
    try {
      setPricingLoading(true);
      const data = await AdminAPI.getActionPricing();
      console.log('🎯 Action pricing data received:', data);
      setActionPricing(data);
    } catch (err) {
      console.error('Failed to load action pricing:', err);
      toast.error('Failed to load action pricing');
    } finally {
      setPricingLoading(false);
    }
  };

  const handleUpdatePricing = async () => {
    if (!editingPricing) return;

    // Client-side validation
    if (!editingPricing.action_slug?.trim()) {
      toast.error('Action slug is required');
      return;
    }
    
    if (!editingPricing.description?.trim()) {
      toast.error('Description is required');
      return;
    }

    try {
      console.log('🎯 Action pricing operation:', isCreatingAction ? 'CREATE' : 'UPDATE', editingPricing);
      
      const pricingData = {
        dust_cost: editingPricing.dust_cost,
        description: editingPricing.description.trim(),
        is_active: editingPricing.is_active,
      };
      
      if (isCreatingAction) {
        // Use POST for creating new actions
        await AdminAPI.createActionPricing(editingPricing.action_slug, pricingData);
      } else {
        // Use PUT for updating existing actions
        await AdminAPI.updateActionPricing(editingPricing.action_slug, pricingData);
      }
      
      toast.success(isCreatingAction ? 'Action created successfully' : 'Pricing updated successfully');
      setPricingDialogOpen(false);
      setEditingPricing(null);
      setIsCreatingAction(false);
      await loadActionPricing();
    } catch (err) {
      console.error('Failed to update pricing:', err);
      toast.error(isCreatingAction ? 'Failed to create action' : 'Failed to update pricing');
    }
  };

  const handleDeleteAction = async () => {
    if (!editingPricing?.action_slug || isCreatingAction) return;

    if (!confirm(`Are you sure you want to delete the action "${editingPricing.action_slug}"? This cannot be undone.`)) {
      return;
    }

    try {
      await AdminAPI.deleteActionPricing(editingPricing.action_slug);
      toast.success('Action deleted successfully');
      setPricingDialogOpen(false);
      setEditingPricing(null);
      await loadActionPricing();
    } catch (err) {
      console.error('Failed to delete action:', err);
      toast.error('Failed to delete action');
    }
  };

  useEffect(() => {
    loadApps();
    loadBuilders();
    loadSupportedModels();
    loadActionPricing();
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
          <h1 className="text-3xl font-bold text-slate-900">Apps & Pricing</h1>
          <p className="text-slate-500">Manage applications and DUST pricing</p>
        </div>
      </div>

      <Tabs defaultValue="apps" className="space-y-6">
        <TabsList>
          <TabsTrigger value="apps">Apps Management</TabsTrigger>
          <TabsTrigger value="pricing">Action Pricing</TabsTrigger>
        </TabsList>

        <TabsContent value="apps" className="space-y-6">
          <div className="flex justify-end">
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
                <Label htmlFor="icon_url">Icon URL</Label>
                <Input
                  id="icon_url"
                  value={newApp.icon_url}
                  onChange={(e) => setNewApp(prev => ({ ...prev, icon_url: e.target.value }))}
                  placeholder="https://example.com/icon.png"
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
                        onClick={() => navigate(`/apps/${app.id}/config`)}
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

            {/* Image Model Configuration - Only for Story App */}
            {editingApp?.slug === 'fairydust-story' && (
              <div className="space-y-2 col-span-2">
                <Label>Image Generation Models</Label>
                <div className="grid grid-cols-2 gap-4 p-4 bg-slate-50 rounded-lg">
                  <div className="space-y-2">
                    <Label htmlFor="edit-standard-model">Standard Model (No Reference Images)</Label>
                    <Select 
                      value={modelConfig.primary_parameters.image_models?.standard_model || 'black-forest-labs/flux-1.1-pro'} 
                      onValueChange={(value) => setModelConfig(prev => ({ 
                        ...prev, 
                        primary_parameters: {
                          ...prev.primary_parameters,
                          image_models: {
                            ...prev.primary_parameters.image_models,
                            standard_model: value
                          }
                        }
                      }))}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Select standard model" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="black-forest-labs/flux-1.1-pro">FLUX 1.1 Pro ($0.040)</SelectItem>
                        <SelectItem value="black-forest-labs/flux-schnell">FLUX Schnell ($0.003)</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  
                  <div className="space-y-2">
                    <Label htmlFor="edit-reference-model">Reference Model (With People Photos)</Label>
                    <Select 
                      value={modelConfig.primary_parameters.image_models?.reference_model || 'runwayml/gen4-image'} 
                      onValueChange={(value) => setModelConfig(prev => ({ 
                        ...prev, 
                        primary_parameters: {
                          ...prev.primary_parameters,
                          image_models: {
                            ...prev.primary_parameters.image_models,
                            reference_model: value
                          }
                        }
                      }))}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Select reference model" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="runwayml/gen4-image">Runway Gen-4 ($0.050)</SelectItem>
                        <SelectItem value="black-forest-labs/flux-1.1-pro">FLUX 1.1 Pro ($0.040)</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  
                  <div className="col-span-2 text-sm text-slate-600">
                    <p>• Standard Model: Used when generating images from text prompts only</p>
                    <p>• Reference Model: Used when including "My People" photos for character consistency</p>
                  </div>
                </div>
              </div>
            )}
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
        </TabsContent>

        <TabsContent value="pricing" className="space-y-6">
          <div className="flex justify-end">
            <Dialog open={pricingDialogOpen} onOpenChange={(open) => {
              setPricingDialogOpen(open);
              if (!open) {
                setIsCreatingAction(false);
                setEditingPricing(null);
              }
            }}>
              <DialogTrigger asChild>
                <Button onClick={() => {
                  setIsCreatingAction(true);
                  setEditingPricing({
                    action_slug: '',
                    dust_cost: 1,
                    description: '',
                    is_active: true,
                    created_at: '',
                    updated_at: ''
                  });
                }}>
                  <Plus className="h-4 w-4 mr-2" />
                  Create Action
                </Button>
              </DialogTrigger>
            </Dialog>
          </div>

          {/* Action Pricing Table */}
          <Card>
            <CardHeader>
              <CardTitle>Action Pricing ({actionPricing.length})</CardTitle>
            </CardHeader>
            <CardContent>
              {pricingLoading && (
                <div className="flex items-center justify-center py-8">
                  <RefreshCw className="h-6 w-6 animate-spin mr-2" />
                  Loading pricing...
                </div>
              )}
              
              {!pricingLoading && actionPricing.length === 0 && (
                <div className="text-center py-8 text-slate-500">
                  No action pricing found.
                </div>
              )}
              
              {!pricingLoading && actionPricing.length > 0 && (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Action Slug</TableHead>
                      <TableHead>DUST Cost</TableHead>
                      <TableHead>Description</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Last Updated</TableHead>
                      <TableHead>Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {actionPricing.map((pricing) => (
                      <TableRow key={pricing.action_slug}>
                        <TableCell>
                          <div className="font-mono text-sm">{pricing.action_slug}</div>
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline" className="font-mono">
                            {pricing.dust_cost} DUST
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <div className="max-w-xs truncate" title={pricing.description}>
                            {pricing.description}
                          </div>
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center space-x-2">
                            {pricing.is_active ? (
                              <CheckCircle className="h-4 w-4 text-green-600" />
                            ) : (
                              <XCircle className="h-4 w-4 text-red-600" />
                            )}
                            <Badge 
                              variant={pricing.is_active ? 'default' : 'destructive'}
                              className="capitalize"
                            >
                              {pricing.is_active ? 'Active' : 'Inactive'}
                            </Badge>
                          </div>
                        </TableCell>
                        <TableCell>
                          <div className="text-sm text-slate-500">
                            {formatDistanceToNow(new Date(pricing.updated_at), { addSuffix: true })}
                          </div>
                        </TableCell>
                        <TableCell>
                          <Button 
                            variant="ghost" 
                            size="sm"
                            onClick={() => {
                              setIsCreatingAction(false);
                              setEditingPricing(pricing);
                              setPricingDialogOpen(true);
                            }}
                            className="text-blue-600 hover:text-blue-800"
                          >
                            <Edit className="h-4 w-4 mr-1" />
                            Edit
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>

          {/* Edit Pricing Dialog */}
          <Dialog open={pricingDialogOpen} onOpenChange={setPricingDialogOpen}>
            <DialogContent className="max-w-md">
              <DialogHeader>
                <DialogTitle>
                  {isCreatingAction ? 'Create New Action' : 'Edit Action'}
                </DialogTitle>
                <DialogDescription>
                  {isCreatingAction 
                    ? 'Create a new action with DUST pricing'
                    : `Modify DUST cost and settings for ${editingPricing?.action_slug}`
                  }
                </DialogDescription>
              </DialogHeader>
              {editingPricing && (
                <div className="space-y-4 py-4">
                  {isCreatingAction && (
                    <div className="space-y-2">
                      <Label htmlFor="action-slug">Action Slug *</Label>
                      <Input
                        id="action-slug"
                        placeholder="e.g., story-short, recipe-simple"
                        value={editingPricing.action_slug}
                        onChange={(e) => setEditingPricing(prev => prev ? {
                          ...prev,
                          action_slug: e.target.value
                        } : null)}
                      />
                    </div>
                  )}
                  <div className="space-y-2">
                    <Label htmlFor="dust-cost">DUST Cost</Label>
                    <Input
                      id="dust-cost"
                      type="number"
                      min="0"
                      max="100"
                      value={editingPricing.dust_cost}
                      onChange={(e) => setEditingPricing(prev => prev ? {
                        ...prev,
                        dust_cost: parseInt(e.target.value) || 0
                      } : null)}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="description">Description *</Label>
                    <Textarea
                      id="description"
                      value={editingPricing.description}
                      onChange={(e) => setEditingPricing(prev => prev ? {
                        ...prev,
                        description: e.target.value
                      } : null)}
                      placeholder="Describe what this action does (e.g., 'Generate a Would You Rather question')"
                      rows={3}
                      required
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="is-active">Status</Label>
                    <Select 
                      value={editingPricing.is_active ? 'active' : 'inactive'}
                      onValueChange={(value) => setEditingPricing(prev => prev ? {
                        ...prev,
                        is_active: value === 'active'
                      } : null)}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="active">Active</SelectItem>
                        <SelectItem value="inactive">Inactive</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              )}
              <DialogFooter className="flex justify-between">
                <div>
                  {!isCreatingAction && (
                    <Button 
                      variant="destructive" 
                      onClick={handleDeleteAction}
                      className="mr-auto"
                    >
                      <Trash2 className="h-4 w-4 mr-2" />
                      Delete Action
                    </Button>
                  )}
                </div>
                <div className="flex space-x-2">
                  <Button variant="outline" onClick={() => {
                    setPricingDialogOpen(false);
                    setIsCreatingAction(false);
                    setEditingPricing(null);
                  }}>
                    Cancel
                  </Button>
                  <Button 
                    onClick={handleUpdatePricing}
                    disabled={!editingPricing?.action_slug || !editingPricing?.description?.trim()}
                  >
                    {isCreatingAction ? 'Create Action' : 'Save Changes'}
                  </Button>
                </div>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </TabsContent>
      </Tabs>
    </div>
  );
}