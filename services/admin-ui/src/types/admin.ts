export interface User {
  id: string;
  fairyname: string;
  email?: string;
  phone?: string;
  is_admin: boolean;
  first_name?: string;
  age_range?: string;
  dust_balance: number;
  auth_provider: string;
  streak_days: number;
  last_login_date?: string;
  created_at: string;
  updated_at: string;
}

export interface App {
  id: string;
  name: string;
  slug: string;
  description: string;
  status: 'approved' | 'pending' | 'rejected';
  builder_id: string;
  builder_name: string;
  category: string;
  icon_url?: string;
  created_at: string;
  updated_at: string;
}

export interface DashboardStats {
  total_users: number;
  total_apps: number;
  pending_apps: number;
  total_dust_issued: number;
  active_users_today: number;
  active_users_week: number;
  new_users_week: number;
  total_dust_consumed: number;
  dust_consumed_today: number;
  dust_consumed_week: number;
  total_transactions: number;
  total_llm_usage: number;
}

export interface SystemHealth {
  identity: 'online' | 'offline' | 'degraded';
  ledger: 'online' | 'offline' | 'degraded';
  apps: 'online' | 'offline' | 'degraded';
  content: 'online' | 'offline' | 'degraded';
  admin: 'online' | 'offline' | 'degraded';
}

export interface LLMUsageMetrics {
  timeframe: string;
  total_stats: {
    total_requests: number;
    total_tokens: number;
    total_cost_usd: number;
    avg_latency_ms: number;
  };
  model_breakdown: Array<{
    provider: string;
    model_id: string;
    requests: number;
    cost: number;
    avg_latency: number;
  }>;
  app_usage: Array<{
    app_name: string;
    app_slug: string;
    total_requests: number;
    avg_prompt_tokens: number;
    avg_completion_tokens: number;
    avg_total_tokens: number;
    avg_cost_per_request: number;
    total_cost: number;
    avg_latency_ms: number;
  }>;
}

export interface AdminUser {
  id: string;
  fairyname: string;
  email?: string;
  is_admin: boolean;
}