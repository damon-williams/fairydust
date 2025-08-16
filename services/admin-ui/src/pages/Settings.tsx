import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import { AdminAPI } from '@/lib/admin-api';
import { Settings as SettingsIcon, Save, Plus, RefreshCw } from 'lucide-react';

interface SystemConfigItem {
  key: string;
  value: string;
  description: string;
  updated_at: string;
}

export default function Settings() {
  const [configs, setConfigs] = useState<SystemConfigItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingAll, setSavingAll] = useState(false);
  const [editingValues, setEditingValues] = useState<Record<string, string>>({});
  const [editingDescriptions, setEditingDescriptions] = useState<Record<string, string>>({});

  // Load system configurations
  const loadConfigs = async () => {
    try {
      setLoading(true);
      const data = await AdminAPI.getSystemConfig();
      setConfigs(data);
      
      // Initialize editing values with current values
      const values: Record<string, string> = {};
      const descriptions: Record<string, string> = {};
      data.forEach(item => {
        values[item.key] = item.value;
        descriptions[item.key] = item.description || '';
      });
      setEditingValues(values);
      setEditingDescriptions(descriptions);
    } catch (error) {
      console.error('Failed to load system config:', error);
      toast.error('Failed to load system configuration');
    } finally {
      setLoading(false);
    }
  };


  // Save all configurations with unsaved changes
  const saveAllConfigs = async () => {
    try {
      setSavingAll(true);
      const changedConfigs = configs.filter(item => hasUnsavedChanges(item));
      
      if (changedConfigs.length === 0) {
        toast.info('No changes to save');
        return;
      }

      // Save all changed configurations
      for (const item of changedConfigs) {
        await AdminAPI.updateSystemConfigValue(
          item.key, 
          editingValues[item.key], 
          editingDescriptions[item.key]
        );
      }
      
      // Update local state for all changed items
      setConfigs(prev => prev.map(item => {
        if (hasUnsavedChanges(item)) {
          return {
            ...item,
            value: editingValues[item.key],
            description: editingDescriptions[item.key],
            updated_at: new Date().toISOString()
          };
        }
        return item;
      }));
      
      toast.success(`Updated ${changedConfigs.length} configuration${changedConfigs.length > 1 ? 's' : ''} successfully`);
    } catch (error) {
      console.error('Failed to save configurations:', error);
      toast.error('Failed to update configurations');
    } finally {
      setSavingAll(false);
    }
  };

  // Handle value changes
  const handleValueChange = (key: string, value: string) => {
    setEditingValues(prev => ({ ...prev, [key]: value }));
  };

  // Handle description changes
  const handleDescriptionChange = (key: string, description: string) => {
    setEditingDescriptions(prev => ({ ...prev, [key]: description }));
  };

  // Check if a config has unsaved changes
  const hasUnsavedChanges = (item: SystemConfigItem) => {
    return editingValues[item.key] !== item.value || 
           editingDescriptions[item.key] !== (item.description || '');
  };

  // Check if there are any unsaved changes across all configs
  const hasAnyUnsavedChanges = () => {
    return configs.some(item => hasUnsavedChanges(item));
  };

  // Format timestamp
  const formatTimestamp = (timestamp: string) => {
    return new Date(timestamp).toLocaleString();
  };

  // Get input type based on key
  const getInputType = (key: string) => {
    if (key.includes('amount') || key.includes('count') || key.includes('limit')) {
      return 'number';
    }
    if (key.includes('url') || key.includes('email')) {
      return 'text';
    }
    return 'text';
  };

  // Get human-readable display name for configuration keys
  const getDisplayName = (key: string) => {
    const displayNames: Record<string, string> = {
      'daily_login_bonus_amount': 'Daily Login Bonus',
      'initial_dust_amount': 'Initial DUST Grant',
      'app_store_url_ios': 'iOS App Store URL',
      'app_store_url_android': 'Android App Store URL',
      'support_email': 'Support Email',
      'terms_of_service_url': 'Terms of Service URL',
      'privacy_policy_url': 'Privacy Policy URL',
      'terms_of_service_current_version': 'Terms of Service Version',
      'privacy_policy_current_version': 'Privacy Policy Version',
      'terms_enforcement_enabled': 'Terms Enforcement Enabled',
      'terms_grace_period_days': 'Terms Grace Period (Days)'
    };
    
    return displayNames[key] || key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
  };

  useEffect(() => {
    loadConfigs();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <RefreshCw className="h-8 w-8 animate-spin text-gray-400" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
            <SettingsIcon className="h-8 w-8" />
            System Settings
          </h1>
          <p className="text-muted-foreground">
            Manage system-wide configuration values
          </p>
        </div>
        <div className="flex gap-2">
          {hasAnyUnsavedChanges() && (
            <Button 
              onClick={saveAllConfigs} 
              disabled={savingAll}
              className="bg-green-600 hover:bg-green-700"
            >
              {savingAll ? (
                <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Save className="h-4 w-4 mr-2" />
              )}
              Save All Changes
            </Button>
          )}
          <Button onClick={loadConfigs} variant="outline">
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
        </div>
      </div>



      {/* All System Configurations */}
      <Card>
        <CardHeader>
          <CardTitle>All System Configuration</CardTitle>
          <CardDescription>
            Complete list of system configuration values
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-6">
            {configs.map((item, index) => (
              <div key={item.key}>
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="font-medium">{getDisplayName(item.key)}</h3>
                      <p className="text-sm text-muted-foreground">
                        {item.description || 'No description provided'}
                      </p>
                    </div>
                    {hasUnsavedChanges(item) && (
                      <Badge variant="destructive">Unsaved</Badge>
                    )}
                  </div>
                  
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label htmlFor={`value-${item.key}`}>Value</Label>
                      <Input
                        id={`value-${item.key}`}
                        type={getInputType(item.key)}
                        value={editingValues[item.key] || ''}
                        onChange={(e) => handleValueChange(item.key, e.target.value)}
                      />
                    </div>
                    
                    <div className="space-y-2">
                      <Label htmlFor={`desc-${item.key}`}>Description</Label>
                      <Input
                        id={`desc-${item.key}`}
                        value={editingDescriptions[item.key] || ''}
                        onChange={(e) => handleDescriptionChange(item.key, e.target.value)}
                        placeholder="Description of this setting"
                      />
                    </div>
                  </div>
                  
                  <div className="text-xs text-muted-foreground">
                    Last updated: {formatTimestamp(item.updated_at)}
                  </div>
                </div>
                
                {index < configs.length - 1 && <div className="mt-6 border-t border-gray-200" />}
              </div>
            ))}
            
            {configs.length === 0 && (
              <div className="text-center py-8 text-muted-foreground">
                No system configuration found
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}