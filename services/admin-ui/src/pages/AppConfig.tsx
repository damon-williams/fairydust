import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { 
  ArrowLeft, 
  Save, 
  RefreshCw, 
  AlertTriangle,
  Brain,
  Image,
  Video,
  Settings
} from 'lucide-react';
import { AdminAPI } from '@/lib/admin-api';
import { toast } from 'sonner';

interface AppModelConfig {
  // Model type enablement
  text_models_enabled: boolean;
  image_models_enabled: boolean;
  video_models_enabled: boolean;
  
  // Text/LLM Configuration
  text_config?: {
    primary_provider: string;
    primary_model_id: string;
    fallback_provider?: string;
    fallback_model_id?: string;
    parameters: {
      temperature: number;
      max_tokens: number;
      top_p: number;
    };
  };
  
  // Image Configuration
  image_config?: {
    standard_model: string;
    reference_model: string;
    parameters: {
      default_style: string;
      default_size: string;
      quality: string;
    };
  };
  
  // Video Configuration
  video_config?: {
    standard_model: string;
    parameters: {
      text_to_video_model?: string;
      image_to_video_model?: string;
      duration: number;
      fps: number;
      resolution: string;
    };
  };
}

interface App {
  id: string;
  name: string;
  slug: string;
  description: string;
  status: string;
  category: string;
}

export function AppConfig() {
  const { appId } = useParams<{ appId: string }>();
  const navigate = useNavigate();
  
  const [app, setApp] = useState<App | null>(null);
  const [config, setConfig] = useState<AppModelConfig>({
    text_models_enabled: false,
    image_models_enabled: false,
    video_models_enabled: false,
  });
  const [existingConfigs, setExistingConfigs] = useState<{
    text: boolean;
    image: boolean;
    video: boolean;
  }>({
    text: false,
    image: false,
    video: false,
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);


  useEffect(() => {
    if (appId) {
      loadAppConfig();
    }
  }, [appId]);

  const loadAppConfig = async () => {
    try {
      setLoading(true);
      setError(null);
      
      // Load app details
      const appData = await AdminAPI.getApp(appId!);
      setApp(appData);
      
      // Load normalized model configurations
      let configData = null;
      try {
        configData = await AdminAPI.getAppModelConfigs(appId!);
      } catch (configError: any) {
        if (configError.message?.includes('404') || configError.message?.includes('not found')) {
          console.info('No model configuration found for app, using defaults');
          configData = null;
        } else {
          throw configError; // Re-throw non-404 errors
        }
      }
      
      // Parse normalized configuration structure
      if (configData) {
        console.log('🔍 FRONTEND: Raw config data from API:', configData);
        const textConfig = configData.text_config;
        const imageConfig = configData.image_config;
        const videoConfig = configData.video_config;
        console.log('🔍 FRONTEND: Text config:', textConfig);
        
        setExistingConfigs({
          text: !!(textConfig),
          image: !!(imageConfig),
          video: !!(videoConfig),
        });
        
        setConfig({
          text_models_enabled: !!(textConfig),
          image_models_enabled: !!(imageConfig),
          video_models_enabled: !!(videoConfig),
          
          text_config: textConfig ? {
            primary_provider: textConfig.provider || '',
            primary_model_id: textConfig.model_id || '',
            parameters: {
              temperature: textConfig.parameters?.temperature || 0.7,
              max_tokens: textConfig.parameters?.max_tokens || 1000,
              top_p: textConfig.parameters?.top_p || 0.9,
            }
          } : undefined,
          
          image_config: imageConfig ? {
            standard_model: imageConfig.parameters?.standard_model || 'black-forest-labs/flux-1.1-pro',
            reference_model: imageConfig.parameters?.reference_model || 'runwayml/gen4-image',
            parameters: {
              default_style: 'realistic',
              default_size: 'standard',
              quality: 'high'
            }
          } : undefined,
          
          video_config: videoConfig ? {
            standard_model: videoConfig.parameters?.text_to_video_model || videoConfig.parameters?.standard_model || 'minimax/video-01',
            parameters: {
              text_to_video_model: videoConfig.parameters?.text_to_video_model || videoConfig.parameters?.standard_model || 'minimax/video-01',
              image_to_video_model: videoConfig.parameters?.image_to_video_model || 'bytedance/seedance-1-pro',
              duration: videoConfig.parameters?.duration || 5,
              fps: videoConfig.parameters?.fps || 24,
              resolution: videoConfig.parameters?.resolution || '1080p'
            }
          } : undefined,
        });
      } else {
        // No configuration exists, use empty defaults
        setConfig({
          text_models_enabled: false,
          image_models_enabled: false,
          video_models_enabled: false,
        });
      }
    } catch (err) {
      console.error('Failed to load app configuration:', err);
      setError('Failed to load app configuration. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const saveModelConfig = async (
    modelType: 'text' | 'image' | 'video',
    payload: any,
    exists: boolean
  ) => {
    try {
      if (exists) {
        // Use PUT to update existing config
        await AdminAPI.updateAppModelConfigByType(appId!, modelType, payload);
      } else {
        // Use POST to create new config
        const createPayload = {
          ...payload,
          app_id: appId!,
          model_type: modelType,
        };
        await AdminAPI.createAppModelConfig(appId!, createPayload);
      }
    } catch (error: any) {
      // If PUT fails with 404, try creating instead
      if (exists && error.message?.includes('404')) {
        const createPayload = {
          ...payload,
          app_id: appId!,
          model_type: modelType,
        };
        await AdminAPI.createAppModelConfig(appId!, createPayload);
      } else {
        throw error;
      }
    }
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      setError(null);

      console.log('🔍 FRONTEND: Saving app configuration with new normalized structure');

      // Save text model configuration
      if (config.text_models_enabled && config.text_config) {
        const textPayload = {
          provider: config.text_config.primary_provider,
          model_id: config.text_config.primary_model_id,
          parameters: {
            temperature: config.text_config.parameters.temperature,
            max_tokens: config.text_config.parameters.max_tokens,
            top_p: config.text_config.parameters.top_p,
          },
          is_enabled: true,
        };

        console.log('🔍 FRONTEND: Saving text config:', textPayload);
        await saveModelConfig('text', textPayload, existingConfigs.text);
      } else if (existingConfigs.text) {
        // Disable text models if not enabled but config exists
        await AdminAPI.updateAppModelConfigByType(appId!, 'text', { is_enabled: false });
      }

      // Save image model configuration
      if (config.image_models_enabled && config.image_config) {
        const imagePayload = {
          provider: 'replicate',
          model_id: 'image-config',  // Generic identifier since we store actual models in parameters
          parameters: {
            standard_model: config.image_config.standard_model,
            reference_model: config.image_config.reference_model,
            default_style: config.image_config.parameters.default_style,
            default_size: config.image_config.parameters.default_size,
            quality: config.image_config.parameters.quality,
          },
          is_enabled: true,
        };

        console.log('🔍 FRONTEND: Saving image config:', imagePayload);
        await saveModelConfig('image', imagePayload, existingConfigs.image);
      } else if (existingConfigs.image) {
        // Disable image models if not enabled but config exists
        await AdminAPI.updateAppModelConfigByType(appId!, 'image', { is_enabled: false });
      }

      // Save video model configuration (when enabled)
      if (config.video_models_enabled && config.video_config) {
        const videoPayload = {
          provider: 'replicate',
          model_id: config.video_config.standard_model,
          parameters: {
            text_to_video_model: config.video_config.parameters?.text_to_video_model || config.video_config.standard_model,
            image_to_video_model: config.video_config.parameters?.image_to_video_model || 'bytedance/seedance-1-pro',
            duration: config.video_config.parameters.duration,
            fps: config.video_config.parameters.fps,
            resolution: config.video_config.parameters.resolution,
          },
          is_enabled: true,
        };

        console.log('🔍 FRONTEND: Saving video config:', videoPayload);
        await saveModelConfig('video', videoPayload, existingConfigs.video);
      } else if (existingConfigs.video) {
        // Disable video models if not enabled but config exists
        await AdminAPI.updateAppModelConfigByType(appId!, 'video', { is_enabled: false });
      }

      console.log('✅ FRONTEND: All model configurations saved successfully');
      toast.success('App configuration saved successfully!');
      
      // Update existingConfigs state to reflect what now exists
      setExistingConfigs({
        text: config.text_models_enabled,
        image: config.image_models_enabled,
        video: config.video_models_enabled,
      });
      
    } catch (err) {
      console.error('Failed to save app configuration:', err);
      setError('Failed to save configuration. Please try again.');
      toast.error('Failed to save configuration');
    } finally {
      setSaving(false);
    }
  };

  const handleToggleModelType = (type: 'text' | 'image' | 'video', enabled: boolean) => {
    setConfig(prev => {
      const newConfig = { ...prev };
      
      switch (type) {
        case 'text':
          newConfig.text_models_enabled = enabled;
          if (enabled && !newConfig.text_config) {
            // Use OpenAI as default since it's the current global fallback
            newConfig.text_config = {
              primary_provider: 'openai',
              primary_model_id: 'gpt-5-mini',
              parameters: {
                temperature: 0.7,
                max_tokens: 1000,
                top_p: 0.9,
              }
            };
          }
          break;
          
        case 'image':
          newConfig.image_models_enabled = enabled;
          if (enabled && !newConfig.image_config) {
            newConfig.image_config = {
              standard_model: 'black-forest-labs/flux-1.1-pro',
              reference_model: 'runwayml/gen4-image',
              parameters: {
                default_style: 'realistic',
                default_size: 'standard',
                quality: 'high'
              }
            };
          }
          break;
          
        case 'video':
          newConfig.video_models_enabled = enabled;
          if (enabled && !newConfig.video_config) {
            newConfig.video_config = {
              standard_model: 'minimax/video-01',
              parameters: {
                text_to_video_model: 'minimax/video-01',
                image_to_video_model: 'bytedance/seedance-1-pro',
                duration: 5,
                fps: 24,
                resolution: '1080p'
              }
            };
          }
          break;
      }
      
      return newConfig;
    });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center space-y-4">
          <RefreshCw className="h-8 w-8 animate-spin mx-auto text-slate-400" />
          <p className="text-slate-500">Loading app configuration...</p>
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
              onClick={loadAppConfig}
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
      <div className="flex items-center gap-4">
        <Button 
          variant="outline" 
          onClick={() => navigate('/admin/apps')}
          className="flex items-center gap-2"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Apps
        </Button>
        
        <div className="flex-1">
          <h1 className="text-3xl font-bold text-slate-900">
            Configure {app?.name}
          </h1>
          <p className="text-slate-500">
            Configure AI models and parameters for this app
          </p>
        </div>

        <Button 
          onClick={handleSave} 
          disabled={saving}
          className="flex items-center gap-2"
        >
          {saving ? (
            <RefreshCw className="h-4 w-4 animate-spin" />
          ) : (
            <Save className="h-4 w-4" />
          )}
          {saving ? 'Saving...' : 'Save Configuration'}
        </Button>
      </div>

      {/* App Info */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Settings className="h-5 w-5" />
            App Information
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <Label className="text-sm font-medium text-slate-600">Name</Label>
              <p className="text-sm">{app?.name}</p>
            </div>
            <div>
              <Label className="text-sm font-medium text-slate-600">Slug</Label>
              <p className="text-sm font-mono">{app?.slug}</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Model Type Configuration */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Text/LLM Models */}
        <Card className={config.text_models_enabled ? 'ring-2 ring-blue-200' : ''}>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <Brain className="h-5 w-5 text-blue-600" />
                Text Models (LLM)
              </CardTitle>
              <Switch
                checked={config.text_models_enabled}
                onCheckedChange={(checked) => handleToggleModelType('text', checked)}
              />
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {config.text_models_enabled && config.text_config ? (
              <>
                <div className="space-y-2">
                  <Label>Primary Provider</Label>
                  <Select 
                    value={config.text_config.primary_provider || ""}
                    onValueChange={(value) => setConfig(prev => ({
                      ...prev,
                      text_config: prev.text_config ? {
                        ...prev.text_config,
                        primary_provider: value
                      } : undefined
                    }))}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select provider..." />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="anthropic">Anthropic</SelectItem>
                      <SelectItem value="openai">OpenAI</SelectItem>
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-gray-500">Current value: "{config.text_config.primary_provider}"</p>
                </div>

                <div className="space-y-2">
                  <Label>Primary Model</Label>
                  <Select 
                    value={config.text_config.primary_model_id || ""}
                    onValueChange={(value) => setConfig(prev => ({
                      ...prev,
                      text_config: prev.text_config ? {
                        ...prev.text_config,
                        primary_model_id: value
                      } : undefined
                    }))}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select model..." />
                    </SelectTrigger>
                    <SelectContent>
                      {config.text_config.primary_provider === 'anthropic' ? (
                        <>
                          <SelectItem value="claude-3-5-sonnet-20241022">Claude 3.5 Sonnet</SelectItem>
                          <SelectItem value="claude-3-5-haiku-20241022">Claude 3.5 Haiku</SelectItem>
                        </>
                      ) : (
                        <>
                          <SelectItem value="gpt-5">GPT-5</SelectItem>
                          <SelectItem value="gpt-5-mini">GPT-5 Mini</SelectItem>
                          <SelectItem value="gpt-5-nano">GPT-5 Nano</SelectItem>
                          <SelectItem value="gpt-4o">GPT-4o</SelectItem>
                          <SelectItem value="gpt-4o-mini">GPT-4o Mini</SelectItem>
                        </>
                      )}
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-gray-500">Current value: "{config.text_config.primary_model_id}"</p>
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <div className="space-y-2">
                    <Label>Temperature</Label>
                    <Input
                      type="number"
                      step="0.1"
                      min="0"
                      max="2"
                      value={config.text_config.parameters.temperature}
                      onChange={(e) => setConfig(prev => ({
                        ...prev,
                        text_config: prev.text_config ? {
                          ...prev.text_config,
                          parameters: {
                            ...prev.text_config.parameters,
                            temperature: parseFloat(e.target.value)
                          }
                        } : undefined
                      }))}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Max Tokens</Label>
                    <Input
                      type="number"
                      min="1"
                      max="4000"
                      value={config.text_config.parameters.max_tokens}
                      onChange={(e) => setConfig(prev => ({
                        ...prev,
                        text_config: prev.text_config ? {
                          ...prev.text_config,
                          parameters: {
                            ...prev.text_config.parameters,
                            max_tokens: parseInt(e.target.value)
                          }
                        } : undefined
                      }))}
                    />
                  </div>
                </div>
              </>
            ) : (
              <p className="text-sm text-slate-500">
                Enable text models to configure LLM settings for this app.
              </p>
            )}
          </CardContent>
        </Card>

        {/* Image Models */}
        <Card className={config.image_models_enabled ? 'ring-2 ring-purple-200' : ''}>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <Image className="h-5 w-5 text-purple-600" />
                Image Models
              </CardTitle>
              <Switch
                checked={config.image_models_enabled}
                onCheckedChange={(checked) => handleToggleModelType('image', checked)}
              />
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {config.image_models_enabled && config.image_config ? (
              <>
                <div className="space-y-2">
                  <Label>Standard Model (Text-to-Image)</Label>
                  <Select 
                    value={config.image_config.standard_model}
                    onValueChange={(value) => setConfig(prev => ({
                      ...prev,
                      image_config: prev.image_config ? {
                        ...prev.image_config,
                        standard_model: value
                      } : undefined
                    }))}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="black-forest-labs/flux-1.1-pro">FLUX 1.1 Pro</SelectItem>
                      <SelectItem value="black-forest-labs/flux-schnell">FLUX Schnell</SelectItem>
                      <SelectItem value="bytedance/seedream-3">ByteDance SeeDream-3</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label>Reference Model (With People)</Label>
                  <Select 
                    value={config.image_config.reference_model}
                    onValueChange={(value) => setConfig(prev => ({
                      ...prev,
                      image_config: prev.image_config ? {
                        ...prev.image_config,
                        reference_model: value
                      } : undefined
                    }))}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="runwayml/gen4-image">Runway Gen-4</SelectItem>
                      <SelectItem value="runwayml/gen4-image-turbo">Runway Gen-4 Turbo</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label>Default Style</Label>
                  <Select 
                    value={config.image_config.parameters.default_style}
                    onValueChange={(value) => setConfig(prev => ({
                      ...prev,
                      image_config: prev.image_config ? {
                        ...prev.image_config,
                        parameters: {
                          ...prev.image_config.parameters,
                          default_style: value
                        }
                      } : undefined
                    }))}
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
              </>
            ) : (
              <p className="text-sm text-slate-500">
                Enable image models to configure AI image generation for this app.
              </p>
            )}
          </CardContent>
        </Card>

        {/* Video Models */}
        <Card className={config.video_models_enabled ? 'ring-2 ring-green-200' : ''}>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <Video className="h-5 w-5 text-green-600" />
                Video Models
              </CardTitle>
              <Switch
                checked={config.video_models_enabled}
                onCheckedChange={(checked) => handleToggleModelType('video', checked)}
              />
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {config.video_models_enabled && config.video_config ? (
              <>
                <div className="space-y-2">
                  <Label>Text-to-Video Model</Label>
                  <Select 
                    value={config.video_config.standard_model}
                    onValueChange={(value) => setConfig(prev => ({
                      ...prev,
                      video_config: prev.video_config ? {
                        ...prev.video_config,
                        standard_model: value
                      } : undefined
                    }))}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="minimax/video-01">MiniMax Video-01</SelectItem>
                      <SelectItem value="bytedance/seedance-1-pro">ByteDance SeeDance-1-Pro</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label>Image-to-Video Model</Label>
                  <Select 
                    value={config.video_config.parameters?.image_to_video_model || 'bytedance/seedance-1-pro'}
                    onValueChange={(value) => setConfig(prev => ({
                      ...prev,
                      video_config: prev.video_config ? {
                        ...prev.video_config,
                        parameters: {
                          ...prev.video_config.parameters,
                          image_to_video_model: value
                        }
                      } : undefined
                    }))}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="bytedance/seedance-1-pro">ByteDance SeeDance-1-Pro</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <div className="space-y-2">
                    <Label>Default Duration</Label>
                    <Select 
                      value={config.video_config.parameters.duration.toString()}
                      onValueChange={(value) => setConfig(prev => ({
                        ...prev,
                        video_config: prev.video_config ? {
                          ...prev.video_config,
                          parameters: {
                            ...prev.video_config.parameters,
                            duration: parseInt(value)
                          }
                        } : undefined
                      }))}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="5">5 seconds</SelectItem>
                        <SelectItem value="10">10 seconds</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label>Resolution</Label>
                    <Select 
                      value={config.video_config.parameters.resolution}
                      onValueChange={(value) => setConfig(prev => ({
                        ...prev,
                        video_config: prev.video_config ? {
                          ...prev.video_config,
                          parameters: {
                            ...prev.video_config.parameters,
                            resolution: value
                          }
                        } : undefined
                      }))}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="720p">720p HD</SelectItem>
                        <SelectItem value="1080p">1080p Full HD</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </>
            ) : (
              <p className="text-sm text-slate-500">
                Enable video models to configure AI video generation for this app.
              </p>
            )}
          </CardContent>
        </Card>

      </div>

      {/* Save Actions */}
      <div className="flex justify-end gap-4 pt-6 border-t">
        <Button 
          variant="outline" 
          onClick={() => navigate('/admin/apps')}
        >
          Cancel
        </Button>
        <Button 
          onClick={handleSave} 
          disabled={saving}
          className="flex items-center gap-2"
        >
          {saving ? (
            <RefreshCw className="h-4 w-4 animate-spin" />
          ) : (
            <Save className="h-4 w-4" />
          )}
          {saving ? 'Saving...' : 'Save Configuration'}
        </Button>
      </div>

    </div>
  );
}