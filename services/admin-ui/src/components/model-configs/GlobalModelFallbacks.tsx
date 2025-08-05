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

  const modelProviders = [
    'anthropic',
    'openai',
    'gemini',
    'claude',
    'gpt',
    'dall-e',
    'midjourney',
    'stable-diffusion'
  ];

  const modelTypes = [
    { value: 'text', label: 'Text' },
    { value: 'image', label: 'Image' },
    { value: 'video', label: 'Video' }
  ];

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
      primary_provider: '',
      primary_model_id: '',
      fallback_provider: '',
      fallback_model_id: '',
      parameters: {},
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
                onValueChange={(value: 'text' | 'image' | 'video') => setFormData({ ...formData, model_type: value })}
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
              <Input
                value={formData.primary_provider}
                onChange={(e) => setFormData({ ...formData, primary_provider: e.target.value })}
                placeholder="e.g., anthropic, openai"
                required
              />
            </div>

            <div className="space-y-2">
              <Label>Primary Model ID</Label>
              <Input
                value={formData.primary_model_id}
                onChange={(e) => setFormData({ ...formData, primary_model_id: e.target.value })}
                placeholder="e.g., claude-3-5-sonnet-20241022"
                required
              />
            </div>

            <div className="space-y-2">
              <Label>Fallback Provider (Optional)</Label>
              <Input
                value={formData.fallback_provider}
                onChange={(e) => setFormData({ ...formData, fallback_provider: e.target.value })}
                placeholder="e.g., openai"
              />
            </div>

            <div className="space-y-2">
              <Label>Fallback Model ID (Optional)</Label>
              <Input
                value={formData.fallback_model_id}
                onChange={(e) => setFormData({ ...formData, fallback_model_id: e.target.value })}
                placeholder="e.g., gpt-4o"
              />
            </div>

            <div className="space-y-2">
              <Label>Parameters (JSON)</Label>
              <Textarea
                value={JSON.stringify(formData.parameters, null, 2)}
                onChange={(e) => {
                  try {
                    const params = JSON.parse(e.target.value);
                    setFormData({ ...formData, parameters: params });
                  } catch {
                    // Invalid JSON, keep current value
                  }
                }}
                rows={4}
                placeholder='{"temperature": 0.7, "max_tokens": 1000}'
              />
              <p className="text-sm text-slate-500">Enter model parameters as JSON</p>
            </div>

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