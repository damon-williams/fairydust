import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
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
import { Plus, Edit, Trash2, AlertTriangle, RefreshCw, Brain, Image, Video } from 'lucide-react';
import { toast } from 'sonner';

const GlobalModelFallbacks: React.FC = () => {
  const [fallbacks, setFallbacks] = useState<GlobalFallbackModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingFallback, setEditingFallback] = useState<GlobalFallbackModel | null>(null);

  const [formData, setFormData] = useState<GlobalFallbackModelCreate>({
    model_type: 'text',
    provider: '',
    model_id: '',
    parameters: {},
    is_enabled: true,
  });

  // Model configuration options with proper TypeScript types
  const modelOptions: Record<string, Record<string, Array<{ value: string; label: string }>>> = {
    text: {
      anthropic: [
        { value: 'claude-3-5-sonnet-20241022', label: 'Claude 3.5 Sonnet' },
        { value: 'claude-3-5-haiku-20241022', label: 'Claude 3.5 Haiku' },
      ],
      openai: [
        { value: 'gpt-4o', label: 'GPT-4o' },
        { value: 'gpt-4o-mini', label: 'GPT-4o Mini' },
      ],
    },
    image: {
      replicate: [
        { value: 'black-forest-labs/flux-schnell', label: 'FLUX Schnell ($0.003)' },
        { value: 'black-forest-labs/flux-1.1-pro', label: 'FLUX 1.1 Pro ($0.040)' },
        { value: 'bytedance/seedream-3', label: 'ByteDance SeeDream-3 ($0.008)' },
      ],
      runwayml: [
        { value: 'runwayml/gen4-image', label: 'Runway Gen-4 ($0.050)' },
      ],
    },
    video: {
      runwayml: [
        { value: 'runwayml/gen4-video', label: 'Runway Gen-4 Video' },
      ],
    },
  };

  const providerOptions: Record<string, string[]> = {
    text: ['anthropic', 'openai'],
    image: ['replicate', 'runwayml'],
    video: ['runwayml'],
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
      console.error('Failed to load global fallbacks:', error);
      toast.error('Failed to load global fallbacks');
    } finally {
      setLoading(false);
    }
  };

  const resetForm = () => {
    setFormData({
      model_type: 'text',
      provider: '',
      model_id: '',
      parameters: {},
      is_enabled: true,
    });
    setEditingFallback(null);
  };

  const handleCreate = () => {
    resetForm();
    setDialogOpen(true);
  };

  const handleEdit = (fallback: GlobalFallbackModel) => {
    setFormData({
      model_type: fallback.model_type,
      provider: fallback.provider,
      model_id: fallback.model_id,
      parameters: fallback.parameters,
      is_enabled: fallback.is_enabled,
    });
    setEditingFallback(fallback);
    setDialogOpen(true);
  };

  const handleSave = async () => {
    try {
      if (editingFallback) {
        // Update existing fallback
        await AdminAPI.updateGlobalFallback(editingFallback.id, formData);
        toast.success('Global fallback updated successfully');
      } else {
        // Create new fallback
        await AdminAPI.createGlobalFallback(formData);
        toast.success('Global fallback created successfully');
      }
      
      setDialogOpen(false);
      resetForm();
      loadFallbacks();
    } catch (error) {
      console.error('Failed to save global fallback:', error);
      toast.error('Failed to save global fallback');
    }
  };

  const handleDelete = async (fallback: GlobalFallbackModel) => {
    if (!confirm(`Are you sure you want to delete the ${fallback.model_type} fallback model?`)) {
      return;
    }

    try {
      await AdminAPI.deleteGlobalFallback(fallback.id);
      toast.success('Global fallback deleted successfully');
      loadFallbacks();
    } catch (error) {
      console.error('Failed to delete global fallback:', error);
      toast.error('Failed to delete global fallback');
    }
  };

  const getModelIcon = (type: string) => {
    switch (type) {
      case 'text': return <Brain className="h-4 w-4 text-blue-600" />;
      case 'image': return <Image className="h-4 w-4 text-purple-600" />;
      case 'video': return <Video className="h-4 w-4 text-green-600" />;
      default: return null;
    }
  };

  const getModelTypeLabel = (type: string) => {
    switch (type) {
      case 'text': return 'Text Models';
      case 'image': return 'Image Models';
      case 'video': return 'Video Models';
      default: return type;
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center space-y-4">
          <RefreshCw className="h-8 w-8 animate-spin mx-auto text-slate-400" />
          <p className="text-slate-500">Loading global fallbacks...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-slate-900">Global Model Fallbacks</h2>
          <p className="text-slate-500">
            Configure fallback models that are used when an app's primary model fails
          </p>
        </div>
        <Button onClick={handleCreate} className="flex items-center gap-2">
          <Plus className="h-4 w-4" />
          Add Fallback
        </Button>
      </div>

      <Alert>
        <AlertTriangle className="h-4 w-4" />
        <AlertDescription>
          Each model type (Text, Image, Video) can have one fallback model. When an app's configured model fails, 
          the system will automatically try the corresponding fallback model.
        </AlertDescription>
      </Alert>

      <Card>
        <CardHeader>
          <CardTitle>Configured Fallbacks</CardTitle>
        </CardHeader>
        <CardContent>
          {fallbacks.length === 0 ? (
            <div className="text-center py-8">
              <p className="text-slate-500">No global fallbacks configured</p>
              <Button onClick={handleCreate} variant="outline" className="mt-4">
                Add your first fallback
              </Button>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Type</TableHead>
                  <TableHead>Provider</TableHead>
                  <TableHead>Model</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {fallbacks.map((fallback) => (
                  <TableRow key={fallback.id}>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        {getModelIcon(fallback.model_type)}
                        {getModelTypeLabel(fallback.model_type)}
                      </div>
                    </TableCell>
                    <TableCell className="font-medium">{fallback.provider}</TableCell>
                    <TableCell className="font-mono text-sm">{fallback.model_id}</TableCell>
                    <TableCell>
                      <Badge variant={fallback.is_enabled ? 'default' : 'secondary'}>
                        {fallback.is_enabled ? 'Enabled' : 'Disabled'}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleEdit(fallback)}
                        >
                          <Edit className="h-3 w-3" />
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleDelete(fallback)}
                        >
                          <Trash2 className="h-3 w-3" />
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

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>
              {editingFallback ? 'Edit' : 'Add'} Global Fallback
            </DialogTitle>
            <DialogDescription>
              Configure a fallback model for when apps' primary models fail
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div className="space-y-2">
              <Label>Model Type</Label>
              <Select
                value={formData.model_type}
                onValueChange={(value: 'text' | 'image' | 'video') =>
                  setFormData(prev => ({ 
                    ...prev, 
                    model_type: value,
                    provider: '',
                    model_id: ''
                  }))
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="text">Text Models</SelectItem>
                  <SelectItem value="image">Image Models</SelectItem>
                  <SelectItem value="video">Video Models</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Provider</Label>
              <Select
                value={formData.provider}
                onValueChange={(value) =>
                  setFormData(prev => ({ ...prev, provider: value, model_id: '' }))
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {providerOptions[formData.model_type]?.map((provider) => (
                    <SelectItem key={provider} value={provider}>
                      {provider.charAt(0).toUpperCase() + provider.slice(1)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Model</Label>
              <Select
                value={formData.model_id}
                onValueChange={(value) =>
                  setFormData(prev => ({ ...prev, model_id: value }))
                }
                disabled={!formData.provider}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {formData.provider && modelOptions[formData.model_type]?.[formData.provider]?.map((model: { value: string; label: string }) => (
                    <SelectItem key={model.value} value={model.value}>
                      {model.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="flex items-center space-x-2">
              <Switch
                checked={formData.is_enabled}
                onCheckedChange={(checked) =>
                  setFormData(prev => ({ ...prev, is_enabled: checked }))
                }
              />
              <Label>Enabled</Label>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>
              Cancel
            </Button>
            <Button 
              onClick={handleSave}
              disabled={!formData.provider || !formData.model_id}
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