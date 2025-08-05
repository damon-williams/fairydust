import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
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
import { AdminAPI } from '@/lib/admin-api';
import { GlobalFallbackModel, GlobalFallbackModelCreate } from '@/types/admin';
import { Plus, Edit, Trash2, AlertTriangle, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';

const GlobalModelFallbacks: React.FC = () => {
  const [fallbacks, setFallbacks] = useState<GlobalFallbackModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingFallback, setEditingFallback] = useState<GlobalFallbackModel | null>(null);

  const [formData, setFormData] = useState<GlobalFallbackModelCreate>({
    model_type: 'text',
    primary_provider: '',
    primary_model_id: '',
    fallback_provider: '',
    fallback_model_id: '',
    parameters: {},
    is_enabled: true
  });

  const textProviders = ['anthropic', 'openai'];
  const imageProviders = ['replicate', 'runwayml'];
  const videoProviders = ['runwayml'];

  const textModels = {
    anthropic: [
      { value: 'claude-3-5-sonnet-20241022', label: 'Claude 3.5 Sonnet' },
      { value: 'claude-3-5-haiku-20241022', label: 'Claude 3.5 Haiku' },
    ],
    openai: [
      { value: 'gpt-4o', label: 'GPT-4o' },
      { value: 'gpt-4o-mini', label: 'GPT-4o Mini' },
    ],
  };

  const imageModels = {
    replicate: [
      { value: 'black-forest-labs/flux-1.1-pro', label: 'FLUX 1.1 Pro ($0.040)' },
      { value: 'black-forest-labs/flux-schnell', label: 'FLUX Schnell ($0.003)' },
    ],
    runwayml: [
      { value: 'runwayml/gen4-image', label: 'Runway Gen-4 ($0.050)' },
    ],
  };

  const videoModels = {
    runwayml: [
      { value: 'runwayml/gen4-video', label: 'Runway Gen-4 Video' },
    ],
  };

  const modelTypes = [
    { value: 'text', label: 'Text' },
    { value: 'image', label: 'Image' },
    { value: 'video', label: 'Video' }
  ];

  const getAvailableProviders = (modelType: 'text' | 'image' | 'video') => {
    switch (modelType) {
      case 'text': return textProviders;
      case 'image': return imageProviders;
      case 'video': return videoProviders;
      default: return [];
    }
  };

  const getAvailableModels = (modelType: 'text' | 'image' | 'video', provider: string) => {
    switch (modelType) {
      case 'text': return textModels[provider as keyof typeof textModels] || [];
      case 'image': return imageModels[provider as keyof typeof imageModels] || [];
      case 'video': return videoModels[provider as keyof typeof videoModels] || [];
      default: return [];
    }
  };

  useEffect(() => {
    loadFallbacks();
  }, []);

  const loadFallbacks = async () => {
    try {
      setLoading(true);
      const data = await AdminAPI.getGlobalFallbacks();
      setFallbacks(data);
    } catch (error) {
      console.error('Error loading fallbacks:', error);
      toast.error('Failed to load global fallback models');
    } finally {
      setLoading(false);
    }
  };

  const handleCreateFallback = () => {
    setEditingFallback(null);
    setFormData({
      model_type: 'text',
      primary_provider: textProviders[0] || '',
      primary_model_id: '',
      fallback_provider: '',
      fallback_model_id: '',
      parameters: {
        temperature: 0.7,
        max_tokens: 1000,
      },
      is_enabled: true
    });
    setDialogOpen(true);
  };

  const handleEditFallback = (fallback: GlobalFallbackModel) => {
    setEditingFallback(fallback);
    setFormData({
      model_type: fallback.model_type,
      primary_provider: fallback.primary_provider,
      primary_model_id: fallback.primary_model_id,
      fallback_provider: fallback.fallback_provider || '',
      fallback_model_id: fallback.fallback_model_id || '',
      parameters: fallback.parameters,
      is_enabled: fallback.is_enabled
    });
    setDialogOpen(true);
  };

  const handleSaveFallback = async () => {
    try {
      if (editingFallback) {
        await AdminAPI.updateGlobalFallback(editingFallback.id, formData);
        toast.success('Global fallback model updated successfully');
      } else {
        await AdminAPI.createGlobalFallback(formData);
        toast.success('Global fallback model created successfully');
      }
      setDialogOpen(false);
      await loadFallbacks();
    } catch (error) {
      console.error('Error saving fallback:', error);
      toast.error('Failed to save global fallback model');
    }
  };

  const handleDeleteFallback = async (fallback: GlobalFallbackModel) => {
    if (window.confirm(`Are you sure you want to delete the ${fallback.model_type} fallback model?`)) {
      try {
        await AdminAPI.deleteGlobalFallback(fallback.id);
        toast.success('Global fallback model deleted successfully');
        await loadFallbacks();
      } catch (error) {
        console.error('Error deleting fallback:', error);
        toast.error('Failed to delete global fallback model');
      }
    }
  };

  const handleToggleEnabled = async (fallback: GlobalFallbackModel) => {
    try {
      const updatedFallback = { ...fallback, is_enabled: !fallback.is_enabled };
      await AdminAPI.updateGlobalFallback(fallback.id, updatedFallback);
      toast.success(`Global fallback model ${updatedFallback.is_enabled ? 'enabled' : 'disabled'}`);
      await loadFallbacks();
    } catch (error) {
      console.error('Error toggling fallback:', error);
      toast.error('Failed to update global fallback model');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center space-y-4">
          <RefreshCw className="h-8 w-8 animate-spin mx-auto text-slate-400" />
          <p className="text-slate-500">Loading global fallback models...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">
            Global Model Fallbacks
          </h1>
          <p className="text-slate-500">
            Configure global fallback models that apps will use when their specific configurations are unavailable.
          </p>
        </div>
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button onClick={handleCreateFallback} className="flex items-center gap-2">
              <Plus className="h-4 w-4" />
              Add Fallback Model
            </Button>
          </DialogTrigger>
        </Dialog>
      </div>

      <Card>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Model Type</TableHead>
              <TableHead>Primary Provider</TableHead>
              <TableHead>Primary Model</TableHead>
              <TableHead>Fallback Provider</TableHead>
              <TableHead>Fallback Model</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {fallbacks.map((fallback) => (
              <TableRow key={fallback.id}>
                <TableCell>
                  <Badge 
                    variant={fallback.model_type === 'text' ? 'default' : 'secondary'}
                  >
                    {fallback.model_type.toUpperCase()}
                  </Badge>
                </TableCell>
                <TableCell>{fallback.primary_provider}</TableCell>
                <TableCell>{fallback.primary_model_id}</TableCell>
                <TableCell>{fallback.fallback_provider || 'None'}</TableCell>
                <TableCell>{fallback.fallback_model_id || 'None'}</TableCell>
                <TableCell>
                  <Switch
                    checked={fallback.is_enabled}
                    onCheckedChange={() => handleToggleEnabled(fallback)}
                  />
                </TableCell>
                <TableCell className="space-x-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleEditFallback(fallback)}
                    className="flex items-center gap-1"
                  >
                    <Edit className="h-3 w-3" />
                    Edit
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleDeleteFallback(fallback)}
                    className="flex items-center gap-1 text-red-600 hover:text-red-700"
                  >
                    <Trash2 className="h-3 w-3" />
                    Delete
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {fallbacks.length === 0 && (
              <TableRow>
                <TableCell colSpan={7} className="text-center">
                  <p className="text-slate-500 py-8">
                    No global fallback models configured
                  </p>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Card>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>
              {editingFallback ? 'Edit Global Fallback Model' : 'Create Global Fallback Model'}
            </DialogTitle>
            <DialogDescription>
              Configure a global fallback model that apps can use when specific configurations are unavailable.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>Model Type</Label>
              <Select
                value={formData.model_type}
                onValueChange={(value: 'text' | 'image' | 'video') => {
                  const availableProviders = getAvailableProviders(value);
                  const defaultParams = value === 'text' 
                    ? { temperature: 0.7, max_tokens: 1000 }
                    : value === 'image'
                    ? { default_style: 'realistic' }
                    : { duration: 5, resolution: '1080p' };
                  
                  setFormData({ 
                    ...formData, 
                    model_type: value,
                    primary_provider: availableProviders[0] || '',
                    primary_model_id: '',
                    fallback_provider: '',
                    fallback_model_id: '',
                    parameters: defaultParams,
                  });
                }}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {modelTypes.map((type) => (
                    <SelectItem key={type.value} value={type.value}>
                      {type.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Primary Provider</Label>
              <Select
                value={formData.primary_provider}
                onValueChange={(value) => setFormData({ 
                  ...formData, 
                  primary_provider: value,
                  primary_model_id: '', // Reset model when provider changes
                })}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select a provider" />
                </SelectTrigger>
                <SelectContent>
                  {getAvailableProviders(formData.model_type).map((provider) => (
                    <SelectItem key={provider} value={provider}>
                      {provider.charAt(0).toUpperCase() + provider.slice(1)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Primary Model</Label>
              <Select
                value={formData.primary_model_id}
                onValueChange={(value) => setFormData({ ...formData, primary_model_id: value })}
                disabled={!formData.primary_provider}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select a model" />
                </SelectTrigger>
                <SelectContent>
                  {getAvailableModels(formData.model_type, formData.primary_provider).map((model) => (
                    <SelectItem key={model.value} value={model.value}>
                      {model.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Fallback Provider (Optional)</Label>
              <Select
                value={formData.fallback_provider || ''}
                onValueChange={(value) => setFormData({ 
                  ...formData, 
                  fallback_provider: value || undefined,
                  fallback_model_id: value ? '' : undefined, // Reset fallback model when provider changes
                })}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select a fallback provider" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="">None</SelectItem>
                  {getAvailableProviders(formData.model_type).map((provider) => (
                    <SelectItem key={provider} value={provider}>
                      {provider.charAt(0).toUpperCase() + provider.slice(1)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Fallback Model (Optional)</Label>
              <Select
                value={formData.fallback_model_id || ''}
                onValueChange={(value) => setFormData({ ...formData, fallback_model_id: value || undefined })}
                disabled={!formData.fallback_provider}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select a fallback model" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="">None</SelectItem>
                  {formData.fallback_provider && getAvailableModels(formData.model_type, formData.fallback_provider).map((model) => (
                    <SelectItem key={model.value} value={model.value}>
                      {model.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {formData.model_type === 'text' && (
              <div className="space-y-4">
                <Label>Text Model Parameters</Label>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Temperature</Label>
                    <Input
                      type="number"
                      step="0.1"
                      min="0"
                      max="2"
                      value={formData.parameters.temperature || 0.7}
                      onChange={(e) => setFormData({ 
                        ...formData, 
                        parameters: { 
                          ...formData.parameters, 
                          temperature: parseFloat(e.target.value) || 0.7 
                        } 
                      })}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Max Tokens</Label>
                    <Input
                      type="number"
                      min="1"
                      max="4000"
                      value={formData.parameters.max_tokens || 1000}
                      onChange={(e) => setFormData({ 
                        ...formData, 
                        parameters: { 
                          ...formData.parameters, 
                          max_tokens: parseInt(e.target.value) || 1000 
                        } 
                      })}
                    />
                  </div>
                </div>
              </div>
            )}

            {formData.model_type === 'image' && (
              <div className="space-y-4">
                <Label>Image Model Parameters</Label>
                <div className="space-y-2">
                  <Label>Default Style</Label>
                  <Select
                    value={formData.parameters.default_style || 'realistic'}
                    onValueChange={(value) => setFormData({ 
                      ...formData, 
                      parameters: { 
                        ...formData.parameters, 
                        default_style: value 
                      } 
                    })}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="realistic">Realistic</SelectItem>
                      <SelectItem value="artistic">Artistic</SelectItem>
                      <SelectItem value="cartoon">Cartoon</SelectItem>
                      <SelectItem value="abstract">Abstract</SelectItem>
                      <SelectItem value="vintage">Vintage</SelectItem>
                      <SelectItem value="modern">Modern</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            )}

            {formData.model_type === 'video' && (
              <div className="space-y-4">
                <Label>Video Model Parameters</Label>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Duration (seconds)</Label>
                    <Input
                      type="number"
                      min="1"
                      max="30"
                      value={formData.parameters.duration || 5}
                      onChange={(e) => setFormData({ 
                        ...formData, 
                        parameters: { 
                          ...formData.parameters, 
                          duration: parseInt(e.target.value) || 5 
                        } 
                      })}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Resolution</Label>
                    <Select
                      value={formData.parameters.resolution || '1080p'}
                      onValueChange={(value) => setFormData({ 
                        ...formData, 
                        parameters: { 
                          ...formData.parameters, 
                          resolution: value 
                        } 
                      })}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="720p">720p</SelectItem>
                        <SelectItem value="1080p">1080p</SelectItem>
                        <SelectItem value="4k">4K</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </div>
            )}

            <div className="flex items-center space-x-2">
              <Switch
                checked={formData.is_enabled}
                onCheckedChange={(checked) => setFormData({ ...formData, is_enabled: checked })}
              />
              <Label>Enabled</Label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>
              Cancel
            </Button>
            <Button 
              onClick={handleSaveFallback}
              disabled={!formData.primary_provider || !formData.primary_model_id}
            >
              {editingFallback ? 'Update' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default GlobalModelFallbacks;