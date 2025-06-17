export interface FairydustConfig {
  apiUrl: string;
  appId: string;
  ledgerUrl?: string;
  debug?: boolean;
}

export interface User {
  id: string;
  fairyname: string;
  email?: string;
  phone?: string;
  avatar_url?: string;
  dust_balance: number;
  is_active: boolean;
  is_builder: boolean;
  created_at: string;
  updated_at: string;
}

export interface AuthState {
  isConnected: boolean;
  user?: User;
  accessToken?: string;
  refreshToken?: string;
}

export interface OTPRequest {
  identifier: string;
  identifier_type: 'email' | 'phone';
}

export interface OTPVerify {
  identifier: string;
  code: string;
}

export interface AuthResponse {
  user: User;
  token: {
    access_token: string;
    refresh_token: string;
    token_type: string;
    expires_in: number;
  };
  is_new_user: boolean;
  dust_granted: number;
}

export interface DustTransaction {
  id: string;
  amount: number;
  type: 'grant' | 'consume' | 'purchase' | 'refund';
  description: string;
  app_id?: string;
  created_at: string;
}

export interface ComponentState {
  isVisible: boolean;
  isLoading: boolean;
  error?: string;
}

export interface AccountComponentProps {
  onConnect?: (user: User) => void;
  onDisconnect?: () => void;
  onBalanceUpdate?: (balance: number) => void;
}

export interface ButtonComponentProps {
  dustCost: number;
  children: string;
  label?: string;  // Alias for children - more intuitive
  onSuccess?: (transaction: DustTransaction) => void;
  onError?: (error: string) => void;
  disabled?: boolean;
  className?: string;
}

export interface AuthenticationProps {
  appName: string;
  onSuccess?: (authResponse: AuthResponse) => void;
  onCancel?: () => void;
}

export interface PaymentMethod {
  id: string;
  last4: string;
  brand: string;
  exp_month: number;
  exp_year: number;
}

export interface PurchaseRequest {
  amount: number;
  payment_method_id?: string;
  save_payment_method?: boolean;
}