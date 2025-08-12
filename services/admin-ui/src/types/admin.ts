export interface User {
  id: string;
  fairyname: string;
  email?: string;
  phone?: string;
  is_admin: boolean;
  first_name?: string;
  birth_date?: string;
  dust_balance: number;
  auth_provider: string;
  streak_days: number;
  last_login_date?: string;
  last_activity_at?: string;
  is_onboarding_completed?: boolean;
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
  primary_model_id?: string;
  primary_provider?: string;
  created_at: string;
  updated_at: string;
}

export interface DashboardStats {
  total_users: number;
  total_apps: number;
  // Removed pending_apps - auto-approval workflow
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

export interface ActionPricing {
  action_slug: string;
  dust_cost: number;
  description: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

// Referral system types
export interface MilestoneReward {
  referral_count: number;
  bonus_amount: number;
}

export interface ReferralConfig {
  referee_bonus: number;
  referrer_bonus: number;
  milestone_rewards: MilestoneReward[];
  code_expiry_days: number;
  max_referrals_per_user: number;
  system_enabled: boolean;
}

export interface TopReferrer {
  user_id: string;
  fairyname: string;
  successful_referrals: number;
  total_dust_earned: number;
}

export interface DailyStat {
  date: string;
  codes_created: number;
  successful_referrals: number;
  dust_granted: number;
}

export interface ReferralSystemStats {
  total_codes_created: number;
  total_successful_referrals: number;
  conversion_rate: number;
  total_dust_granted: number;
  top_referrers: TopReferrer[];
  daily_stats: DailyStat[];
}

export interface ReferralCodeDisplay {
  referral_code: string;
  user_id: string;
  user_name: string;
  created_at: string;
  status: 'active' | 'expired' | 'inactive';
  successful_referrals: number;
}

export interface ReferralCodesResponse {
  codes: ReferralCodeDisplay[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

export interface ReferralRedemptionDisplay {
  referral_code: string;
  referrer_name: string;
  referee_name: string;
  redeemed_at: string;
  referee_bonus: number;
  referrer_bonus: number;
}

export interface ReferralRedemptionsResponse {
  redemptions: ReferralRedemptionDisplay[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

// Promotional referral code types
export interface PromotionalReferralCode {
  id: string;
  code: string;
  description: string;
  dust_bonus: number;
  max_uses?: number;
  current_uses: number;
  created_by: string;
  created_at: string;
  expires_at: string;
  is_active: boolean;
}

export interface PromotionalReferralCodeCreate {
  code: string;
  description: string;
  dust_bonus: number;
  max_uses?: number;
  expires_at: string;
}

export interface PromotionalReferralCodesResponse {
  codes: PromotionalReferralCode[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

export interface PromotionalReferralRedemption {
  id: string;
  promotional_code: string;
  user_id: string;
  user_name: string;
  dust_bonus: number;
  redeemed_at: string;
}

export interface PromotionalReferralRedemptionsResponse {
  redemptions: PromotionalReferralRedemption[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

// Terms & Conditions types
export interface TermsDocument {
  id: string;
  document_type: 'terms_of_service' | 'privacy_policy';
  version: string;
  title: string;
  content_url: string;
  content_hash: string;
  is_active: boolean;
  requires_acceptance: boolean;
  effective_date: string;
  created_by: string;
  created_at: string;
}

export interface TermsDocumentCreate {
  document_type: 'terms_of_service' | 'privacy_policy';
  version: string;
  content_url: string;
  requires_acceptance: boolean;
  effective_date: string;
}

export interface UserTermsAcceptance {
  id: string;
  user_id: string;
  document_id: string;
  document_type: string;
  document_version: string;
  accepted_at: string;
  ip_address?: string;
  user_agent?: string;
  acceptance_method: string;
}

export interface TermsComplianceStats {
  total_documents: number;
  active_documents: number;
  total_acceptances: number;
  compliance_rate: number;
  recent_acceptances: UserTermsAcceptance[];
}

// Global fallback model types
export interface GlobalFallbackModel {
  id: string;
  model_type: 'text' | 'image' | 'video';
  provider: string;
  model_id: string;
  parameters: Record<string, any>;
  is_enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface GlobalFallbackModelCreate {
  model_type: 'text' | 'image' | 'video';
  provider: string;
  model_id: string;
  parameters: Record<string, any>;
  is_enabled: boolean;
}