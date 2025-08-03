import { 
  DashboardStats, 
  SystemHealth, 
  User, 
  App, 
  LLMUsageMetrics, 
  ActionPricing,
  ReferralConfig,
  ReferralSystemStats,
  ReferralCodesResponse,
  ReferralRedemptionsResponse,
  PromotionalReferralCode,
  PromotionalReferralCodeCreate,
  PromotionalReferralCodesResponse,
  PromotionalReferralRedemptionsResponse,
  TermsDocument,
  TermsDocumentCreate,
  UserTermsAcceptance,
  TermsComplianceStats
} from '@/types/admin';

const API_BASE = window.location.origin;

export class AdminAPI {
  // Generic HTTP methods
  static async get(endpoint: string): Promise<any> {
    try {
      const response = await fetch(`${API_BASE}/admin${endpoint}`, {
        credentials: 'include',
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    } catch (error) {
      console.error(`Failed to GET ${endpoint}:`, error);
      throw error;
    }
  }

  // Dashboard APIs
  static async getDashboardStats(): Promise<DashboardStats> {
    try {
      const response = await fetch(`${API_BASE}/admin/dashboard/stats`, {
        credentials: 'include',
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error('Failed to fetch dashboard stats');
    } catch (error) {
      console.error('Failed to get dashboard stats:', error);
      throw error;
    }
  }

  static async getSystemHealth(): Promise<SystemHealth> {
    try {
      const response = await fetch(`${API_BASE}/admin/dashboard/health`, {
        credentials: 'include',
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error('Failed to fetch system health');
    } catch (error) {
      console.error('Failed to get system health:', error);
      throw error;
    }
  }

  static async getRecentUsers(): Promise<User[]> {
    try {
      const response = await fetch(`${API_BASE}/admin/dashboard/recent-users`, {
        credentials: 'include',
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error('Failed to fetch recent users');
    } catch (error) {
      console.error('Failed to get recent users:', error);
      throw error;
    }
  }

  static async getRecentApps(): Promise<App[]> {
    try {
      const response = await fetch(`${API_BASE}/admin/dashboard/recent-apps`, {
        credentials: 'include',
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error('Failed to fetch recent apps');
    } catch (error) {
      console.error('Failed to get recent apps:', error);
      throw error;
    }
  }

  // Users APIs
  static async getUsers(page: number = 1, limit: number = 50, search?: string): Promise<{ users: User[]; total: number; pages: number }> {
    try {
      const params = new URLSearchParams({
        page: page.toString(),
        limit: limit.toString(),
      });
      
      if (search) {
        params.append('search', search);
      }
      
      const url = `${API_BASE}/admin/users/api?${params}`;
      
      const response = await fetch(url, {
        credentials: 'include',
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error('Failed to fetch users');
    } catch (error) {
      console.error('Failed to get users:', error);
      throw error;
    }
  }

  static async updateUser(userId: string, updates: Partial<User>): Promise<User> {
    try {
      const response = await fetch(`${API_BASE}/admin/users/${userId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify(updates),
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error('Failed to update user');
    } catch (error) {
      console.error('Failed to update user:', error);
      throw error;
    }
  }

  static async deleteUser(userId: string): Promise<void> {
    try {
      const response = await fetch(`${API_BASE}/admin/users/${userId}`, {
        method: 'DELETE',
        credentials: 'include',
      });
      
      if (!response.ok) {
        throw new Error('Failed to delete user');
      }
    } catch (error) {
      console.error('Failed to delete user:', error);
      throw error;
    }
  }

  static async grantDust(userId: string, amount: number, reason: string): Promise<void> {
    try {
      const response = await fetch(`${API_BASE}/admin/users/${userId}/grant-dust`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({ amount, reason }),
      });
      
      if (!response.ok) {
        throw new Error('Failed to grant DUST');
      }
    } catch (error) {
      console.error('Failed to grant DUST:', error);
      throw error;
    }
  }

  // Apps APIs
  static async getApps(page: number = 1, limit: number = 50, status?: string): Promise<{ apps: App[]; total: number; pages: number }> {
    try {
      const params = new URLSearchParams({
        page: page.toString(),
        limit: limit.toString(),
      });
      
      if (status) {
        params.append('status', status);
      }
      
      const response = await fetch(`${API_BASE}/admin/apps/api?${params}`, {
        credentials: 'include',
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error('Failed to fetch apps');
    } catch (error) {
      console.error('Failed to get apps:', error);
      throw error;
    }
  }

  static async updateAppStatus(appId: string, status: 'approved' | 'pending' | 'rejected'): Promise<App> {
    try {
      const response = await fetch(`${API_BASE}/admin/apps/${appId}/status`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({ status }),
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error('Failed to update app status');
    } catch (error) {
      console.error('Failed to update app status:', error);
      throw error;
    }
  }

  static async deleteApp(appId: string): Promise<void> {
    try {
      const response = await fetch(`${API_BASE}/admin/apps/${appId}`, {
        method: 'DELETE',
        credentials: 'include',
      });
      
      if (!response.ok) {
        throw new Error('Failed to delete app');
      }
    } catch (error) {
      console.error('Failed to delete app:', error);
      throw error;
    }
  }

  static async createApp(appData: any): Promise<App> {
    try {
      const response = await fetch(`${API_BASE}/admin/apps/api`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify(appData),
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error('Failed to create app');
    } catch (error) {
      console.error('Failed to create app:', error);
      throw error;
    }
  }

  static async updateApp(appId: string, appData: any): Promise<App> {
    try {
      const response = await fetch(`${API_BASE}/admin/apps/${appId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify(appData),
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error('Failed to update app');
    } catch (error) {
      console.error('Failed to update app:', error);
      throw error;
    }
  }

  static async getBuilders(): Promise<Array<{ id: string; fairyname: string; email: string }>> {
    try {
      const response = await fetch(`${API_BASE}/admin/apps/builders`, {
        credentials: 'include',
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error('Failed to fetch builders');
    } catch (error) {
      console.error('Failed to get builders:', error);
      throw error;
    }
  }

  // LLM Analytics APIs
  static async getLLMUsageMetrics(timeframe: string = '7d'): Promise<LLMUsageMetrics> {
    try {
      const response = await fetch(`${API_BASE}/admin/llm/usage?timeframe=${timeframe}`, {
        credentials: 'include',
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error('Failed to fetch LLM usage metrics');
    } catch (error) {
      console.error('Failed to get LLM usage metrics:', error);
      throw error;
    }
  }

  static async getLLMCostTrends(timeframe: string = '30d'): Promise<Array<{ date: string; cost: number; requests: number }>> {
    try {
      const response = await fetch(`${API_BASE}/admin/llm/cost-trends?timeframe=${timeframe}`, {
        credentials: 'include',
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error('Failed to fetch LLM cost trends');
    } catch (error) {
      console.error('Failed to get LLM cost trends:', error);
      throw error;
    }
  }

  static async getLLMModelUsage(): Promise<Array<{ model: string; requests: number; cost: number; avg_latency: number }>> {
    try {
      const response = await fetch(`${API_BASE}/admin/llm/model-usage`, {
        credentials: 'include',
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error('Failed to fetch LLM model usage');
    } catch (error) {
      console.error('Failed to get LLM model usage:', error);
      throw error;
    }
  }

  static async getLLMAppConfigs(): Promise<Array<any>> {
    try {
      const response = await fetch(`${API_BASE}/admin/llm/app-configs`, {
        credentials: 'include',
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error('Failed to fetch LLM app configs');
    } catch (error) {
      console.error('Failed to get LLM app configs:', error);
      throw error;
    }
  }

  static async updateLLMAppConfig(appId: string, config: any): Promise<any> {
    try {
      const response = await fetch(`${API_BASE}/admin/llm/app-configs/${appId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify(config),
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error('Failed to update LLM app config');
    } catch (error) {
      console.error('Failed to update LLM app config:', error);
      throw error;
    }
  }

  static async getAvailableModels(): Promise<Record<string, string[]>> {
    try {
      const response = await fetch(`${API_BASE}/admin/llm/models`, {
        credentials: 'include',
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error('Failed to fetch available models');
    } catch (error) {
      console.error('Failed to get available models:', error);
      throw error;
    }
  }

  static async getActionAnalytics(timeframe: string = '7d'): Promise<any> {
    try {
      const response = await fetch(`${API_BASE}/admin/llm/action-analytics?timeframe=${timeframe}`, {
        credentials: 'include',
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error('Failed to fetch action analytics');
    } catch (error) {
      console.error('Failed to get action analytics:', error);
      throw error;
    }
  }

  static async getFallbackAnalytics(timeframe: string = '7d'): Promise<any> {
    try {
      const response = await fetch(`${API_BASE}/admin/llm/fallback-analytics?timeframe=${timeframe}`, {
        credentials: 'include',
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error('Failed to fetch fallback analytics');
    } catch (error) {
      console.error('Failed to get fallback analytics:', error);
      throw error;
    }
  }

  static async getSupportedModels(): Promise<any> {
    try {
      console.log('🌐 Fetching supported models from admin service...');
      
      const response = await fetch(`${API_BASE}/admin/apps/supported-models`, {
        method: 'GET',
        credentials: 'include',
      });
      
      console.log('📡 Response status:', response.status, response.statusText);
      
      if (response.ok) {
        const data = await response.json();
        console.log('📦 Response data:', data);
        return data;
      }
      
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    } catch (error) {
      console.error('❌ Failed to get supported models:', error);
      throw error;
    }
  }

  static async updateAppModelConfig(appId: string, modelConfig: any): Promise<any> {
    try {
      console.log('🔧 Updating model config for app:', appId, modelConfig);
      
      const response = await fetch(`${API_BASE}/admin/apps/${appId}/model-config`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify(modelConfig),
      });
      
      console.log('📡 Model config response status:', response.status, response.statusText);
      
      if (response.ok) {
        const data = await response.json();
        console.log('✅ Model config updated successfully:', data);
        return data;
      }
      
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    } catch (error) {
      console.error('❌ Failed to update model config:', error);
      throw error;
    }
  }

  // Action Pricing APIs
  static async getActionPricing(): Promise<ActionPricing[]> {
    try {
      const response = await fetch(`${API_BASE}/admin/apps/pricing/actions`, {
        credentials: 'include',
      });
      
      if (response.ok) {
        const data = await response.json();
        console.log('📡 Raw action pricing response:', data);
        return data;
      }
      
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    } catch (error) {
      console.error('❌ Failed to fetch action pricing:', error);
      throw error;
    }
  }

  static async createActionPricing(actionSlug: string, pricingData: Partial<ActionPricing>): Promise<ActionPricing> {
    try {
      console.log('🆕 Creating action pricing for:', actionSlug, pricingData);
      
      const response = await fetch(`${API_BASE}/admin/apps/pricing/actions/${actionSlug}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify(pricingData),
      });
      
      console.log('📡 Create action pricing response status:', response.status, response.statusText);
      
      if (response.ok) {
        const data = await response.json();
        console.log('✅ Action pricing created successfully:', data);
        return data;
      }
      
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    } catch (error) {
      console.error('❌ Failed to create action pricing:', error);
      throw error;
    }
  }

  static async updateActionPricing(actionSlug: string, pricingData: Partial<ActionPricing>): Promise<ActionPricing> {
    try {
      console.log('📝 Updating action pricing for:', actionSlug, pricingData);
      
      const response = await fetch(`${API_BASE}/admin/apps/pricing/actions/${actionSlug}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify(pricingData),
      });
      
      console.log('📡 Update action pricing response status:', response.status, response.statusText);
      
      if (response.ok) {
        const data = await response.json();
        console.log('✅ Action pricing updated successfully:', data);
        return data;
      }
      
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    } catch (error) {
      console.error('❌ Failed to update action pricing:', error);
      throw error;
    }
  }

  static async deleteActionPricing(actionSlug: string): Promise<void> {
    try {
      const response = await fetch(`${API_BASE}/admin/apps/pricing/actions/${actionSlug}`, {
        method: 'DELETE',
        credentials: 'include',
      });
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
    } catch (error) {
      console.error('❌ Failed to delete action pricing:', error);
      throw error;
    }
  }

  // Referral Management APIs
  static async getReferralConfig(): Promise<ReferralConfig> {
    try {
      const response = await fetch(`${API_BASE}/admin/referrals/config`, {
        credentials: 'include',
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error('Failed to fetch referral config');
    } catch (error) {
      console.error('Failed to get referral config:', error);
      throw error;
    }
  }

  static async updateReferralConfig(config: Partial<ReferralConfig>): Promise<ReferralConfig> {
    try {
      const response = await fetch(`${API_BASE}/admin/referrals/config`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify(config),
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error('Failed to update referral config');
    } catch (error) {
      console.error('Failed to update referral config:', error);
      throw error;
    }
  }

  static async getReferralStats(): Promise<ReferralSystemStats> {
    try {
      const response = await fetch(`${API_BASE}/admin/referrals/stats`, {
        credentials: 'include',
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error('Failed to fetch referral stats');
    } catch (error) {
      console.error('Failed to get referral stats:', error);
      throw error;
    }
  }

  static async getReferralCodes(params: {
    page?: number;
    limit?: number;
    status?: string;
    user_search?: string;
  } = {}): Promise<ReferralCodesResponse> {
    try {
      const searchParams = new URLSearchParams();
      if (params.page) searchParams.append('page', params.page.toString());
      if (params.limit) searchParams.append('limit', params.limit.toString());
      if (params.status) searchParams.append('status', params.status);
      if (params.user_search) searchParams.append('user_search', params.user_search);

      const response = await fetch(`${API_BASE}/admin/referrals/codes?${searchParams}`, {
        credentials: 'include',
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error('Failed to fetch referral codes');
    } catch (error) {
      console.error('Failed to get referral codes:', error);
      throw error;
    }
  }

  static async getReferralRedemptions(params: {
    page?: number;
    limit?: number;
    date_from?: string;
  } = {}): Promise<ReferralRedemptionsResponse> {
    try {
      const searchParams = new URLSearchParams();
      if (params.page) searchParams.append('page', params.page.toString());
      if (params.limit) searchParams.append('limit', params.limit.toString());
      if (params.date_from) searchParams.append('date_from', params.date_from);

      const response = await fetch(`${API_BASE}/admin/referrals/redemptions?${searchParams}`, {
        credentials: 'include',
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error('Failed to fetch referral redemptions');
    } catch (error) {
      console.error('Failed to get referral redemptions:', error);
      throw error;
    }
  }

  // Promotional Referral Code APIs
  static async getPromotionalCodes(params?: {
    page?: number;
    limit?: number;
    status?: 'active' | 'expired' | 'inactive';
  }): Promise<PromotionalReferralCodesResponse> {
    try {
      const queryParams = new URLSearchParams();
      if (params?.page) queryParams.append('page', params.page.toString());
      if (params?.limit) queryParams.append('limit', params.limit.toString());
      if (params?.status) queryParams.append('status', params.status);

      const response = await fetch(`${API_BASE}/admin/referrals/promotional-codes?${queryParams}`, {
        credentials: 'include',
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error('Failed to fetch promotional codes');
    } catch (error) {
      console.error('Failed to get promotional codes:', error);
      throw error;
    }
  }

  static async createPromotionalCode(data: PromotionalReferralCodeCreate): Promise<PromotionalReferralCode> {
    try {
      const response = await fetch(`${API_BASE}/admin/referrals/promotional-codes`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify(data),
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error('Failed to create promotional code');
    } catch (error) {
      console.error('Failed to create promotional code:', error);
      throw error;
    }
  }

  static async updatePromotionalCode(
    codeId: string, 
    data: Partial<PromotionalReferralCodeCreate>
  ): Promise<PromotionalReferralCode> {
    try {
      const response = await fetch(`${API_BASE}/admin/referrals/promotional-codes/${codeId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify(data),
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error('Failed to update promotional code');
    } catch (error) {
      console.error('Failed to update promotional code:', error);
      throw error;
    }
  }

  static async deletePromotionalCode(codeId: string): Promise<void> {
    try {
      const response = await fetch(`${API_BASE}/admin/referrals/promotional-codes/${codeId}`, {
        method: 'DELETE',
        credentials: 'include',
      });
      
      if (!response.ok) {
        throw new Error('Failed to delete promotional code');
      }
    } catch (error) {
      console.error('Failed to delete promotional code:', error);
      throw error;
    }
  }

  static async getPromotionalCodeRedemptions(
    codeId: string,
    params?: { page?: number; limit?: number }
  ): Promise<PromotionalReferralRedemptionsResponse> {
    try {
      const queryParams = new URLSearchParams();
      if (params?.page) queryParams.append('page', params.page.toString());
      if (params?.limit) queryParams.append('limit', params.limit.toString());

      const response = await fetch(
        `${API_BASE}/admin/referrals/promotional-codes/${codeId}/redemptions?${queryParams}`, 
        {
          credentials: 'include',
        }
      );
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error('Failed to fetch promotional code redemptions');
    } catch (error) {
      console.error('Failed to get promotional code redemptions:', error);
      throw error;
    }
  }

  // Service Token APIs
  static async generateServiceToken(): Promise<{ token: string, expires: string | null }> {
    try {
      const response = await fetch(`${API_BASE}/admin/service-token/generate`, {
        method: 'POST',
        credentials: 'include',
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error('Failed to generate service token');
    } catch (error) {
      console.error('Failed to generate service token:', error);
      throw error;
    }
  }

  // System Configuration APIs
  static async getSystemConfig(): Promise<Array<{ key: string; value: string; description: string; updated_at: string }>> {
    try {
      const response = await fetch(`${API_BASE}/admin/system/config`, {
        credentials: 'include',
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error('Failed to fetch system config');
    } catch (error) {
      console.error('Failed to get system config:', error);
      throw error;
    }
  }

  static async getSystemConfigValue(key: string): Promise<{ key: string; value: string; description: string; updated_at: string }> {
    try {
      const response = await fetch(`${API_BASE}/admin/system/config/${key}`, {
        credentials: 'include',
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error(`Failed to fetch system config value: ${key}`);
    } catch (error) {
      console.error(`Failed to get system config value ${key}:`, error);
      throw error;
    }
  }

  static async updateSystemConfigValue(
    key: string, 
    value: string | number, 
    description?: string
  ): Promise<{ key: string; value: string; description: string; updated_by: string }> {
    try {
      const response = await fetch(`${API_BASE}/admin/system/config/${key}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({ value, description }),
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error(`Failed to update system config value: ${key}`);
    } catch (error) {
      console.error(`Failed to update system config value ${key}:`, error);
      throw error;
    }
  }

  // Account Deletion APIs
  static async getDeletionLogs(params: {
    limit?: number;
    offset?: number;
    deleted_by?: 'self' | 'admin';
    reason?: string;
  } = {}): Promise<{
    deletion_logs: Array<{
      id: string;
      user_id: string;
      fairyname: string;
      email: string;
      deletion_reason: string;
      deletion_feedback: string;
      deleted_by: string;
      deleted_by_user_id?: string;
      user_created_at: string;
      deletion_requested_at: string;
      deletion_completed_at?: string;
      data_summary: any;
    }>;
    pagination: {
      total: number;
      limit: number;
      offset: number;
      has_more: boolean;
    };
    filters: {
      deleted_by?: string;
      reason?: string;
    };
  }> {
    try {
      const queryParams = new URLSearchParams();
      if (params.limit) queryParams.append('limit', params.limit.toString());
      if (params.offset) queryParams.append('offset', params.offset.toString());
      if (params.deleted_by) queryParams.append('deleted_by', params.deleted_by);
      if (params.reason) queryParams.append('reason', params.reason);

      const response = await fetch(`${API_BASE}/admin/users/deletion-logs?${queryParams}`, {
        credentials: 'include',
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error('Failed to fetch deletion logs');
    } catch (error) {
      console.error('Failed to get deletion logs:', error);
      throw error;
    }
  }

  static async getDeletionStats(): Promise<{
    total_deletions: number;
    deletion_reasons: Array<{ deletion_reason: string; count: number }>;
    deletion_types: Array<{ deleted_by: string; count: number }>;
    recent_trend: Array<{ deletion_date: string; count: number }>;
  }> {
    try {
      const response = await fetch(`${API_BASE}/admin/users/deletion-logs/stats`, {
        credentials: 'include',
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error('Failed to fetch deletion stats');
    } catch (error) {
      console.error('Failed to get deletion stats:', error);
      throw error;
    }
  }

  // Terms & Conditions APIs
  static async getTermsDocuments(): Promise<TermsDocument[]> {
    try {
      const response = await fetch(`${API_BASE}/admin/terms/documents`, {
        credentials: 'include',
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error('Failed to fetch terms documents');
    } catch (error) {
      console.error('Failed to get terms documents:', error);
      throw error;
    }
  }

  static async createTermsDocument(document: TermsDocumentCreate): Promise<TermsDocument> {
    try {
      const response = await fetch(`${API_BASE}/admin/terms/documents`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify(document),
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error('Failed to create terms document');
    } catch (error) {
      console.error('Failed to create terms document:', error);
      throw error;
    }
  }

  static async activateTermsDocument(documentId: string): Promise<void> {
    try {
      const response = await fetch(`${API_BASE}/admin/terms/documents/${documentId}/activate`, {
        method: 'POST',
        credentials: 'include',
      });
      
      if (!response.ok) {
        throw new Error('Failed to activate terms document');
      }
    } catch (error) {
      console.error('Failed to activate terms document:', error);
      throw error;
    }
  }

  static async deactivateTermsDocument(documentId: string): Promise<void> {
    try {
      const response = await fetch(`${API_BASE}/admin/terms/documents/${documentId}/deactivate`, {
        method: 'POST',
        credentials: 'include',
      });
      
      if (!response.ok) {
        throw new Error('Failed to deactivate terms document');
      }
    } catch (error) {
      console.error('Failed to deactivate terms document:', error);
      throw error;
    }
  }

  static async getTermsAcceptances(documentId: string): Promise<UserTermsAcceptance[]> {
    try {
      const response = await fetch(`${API_BASE}/admin/terms/documents/${documentId}/acceptances`, {
        credentials: 'include',
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error('Failed to fetch terms acceptances');
    } catch (error) {
      console.error('Failed to get terms acceptances:', error);
      throw error;
    }
  }

  static async getTermsStats(): Promise<TermsComplianceStats> {
    try {
      const response = await fetch(`${API_BASE}/admin/terms/stats`, {
        credentials: 'include',
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error('Failed to fetch terms stats');
    } catch (error) {
      console.error('Failed to get terms stats:', error);
      throw error;
    }
  }

  // User Profile Data APIs
  static async getUserPeople(userId: string): Promise<any[]> {
    try {
      const response = await fetch(`${API_BASE}/admin/users/${userId}/people`, {
        credentials: 'include',
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error('Failed to fetch user people');
    } catch (error) {
      console.error('Failed to get user people:', error);
      throw error;
    }
  }

  static async getUserAppUsage(userId: string): Promise<any[]> {
    try {
      const response = await fetch(`${API_BASE}/admin/users/${userId}/app-usage`, {
        credentials: 'include',
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error('Failed to fetch user app usage');
    } catch (error) {
      console.error('Failed to get user app usage:', error);
      throw error;
    }
  }

  static async getUserGeneratedContent(userId: string, limit: number = 10): Promise<any[]> {
    try {
      const response = await fetch(`${API_BASE}/admin/users/${userId}/generated-content?limit=${limit}`, {
        credentials: 'include',
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error('Failed to fetch user generated content');
    } catch (error) {
      console.error('Failed to get user generated content:', error);
      throw error;
    }
  }

  static async getUserDustTransactions(userId: string, limit: number = 20): Promise<any[]> {
    try {
      const response = await fetch(`${API_BASE}/admin/users/${userId}/dust-transactions?limit=${limit}`, {
        credentials: 'include',
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error('Failed to fetch user dust transactions');
    } catch (error) {
      console.error('Failed to get user dust transactions:', error);
      throw error;
    }
  }

  static async getUserPayments(userId: string, limit: number = 20): Promise<any[]> {
    try {
      const response = await fetch(`${API_BASE}/admin/users/${userId}/payments?limit=${limit}`, {
        credentials: 'include',
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      throw new Error('Failed to fetch user payments');
    } catch (error) {
      console.error('Failed to get user payments:', error);
      throw error;
    }
  }
}