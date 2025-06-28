export interface User {
  id: string;
  fairyname: string;
  email?: string;
  phone?: string;
  avatar_url?: string;
  is_builder: boolean;
  is_admin: boolean;
  is_active: boolean;
  first_name?: string;
  age_range?: string;
  city?: string;
  country?: string;
  dust_balance: number;
  auth_provider: string;
  last_profiling_session?: string;
  total_profiling_sessions: number;
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
  builder: 'online' | 'offline' | 'degraded';
}

export interface LLMUsageMetrics {
  total_requests: number;
  total_tokens: number;
  total_cost: number;
  top_models: Array<{
    model: string;
    requests: number;
    tokens: number;
    cost: number;
  }>;
  usage_by_app: Array<{
    app_name: string;
    requests: number;
    tokens: number;
    cost: number;
  }>;
}

export interface AdminUser {
  id: string;
  fairyname: string;
  email?: string;
  is_admin: boolean;
}