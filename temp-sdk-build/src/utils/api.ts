import { FairydustConfig, OTPRequest, OTPVerify, AuthResponse, User, DustTransaction, PurchaseRequest } from '../types';

export class FairydustAPI {
  private config: FairydustConfig;
  private baseUrl: string;

  constructor(config: FairydustConfig) {
    this.config = config;
    this.baseUrl = config.apiUrl.replace(/\/$/, '');
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    const token = this.getAccessToken();

    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      ...options.headers,
    };

    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(url, {
      ...options,
      headers,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ 
        message: 'Network error' 
      }));
      throw new Error(error.message || `HTTP ${response.status}`);
    }

    return response.json();
  }

  private getAccessToken(): string | null {
    return localStorage.getItem(`fairydust_${this.config.appId}_access_token`);
  }

  private setTokens(accessToken: string, refreshToken: string): void {
    localStorage.setItem(`fairydust_${this.config.appId}_access_token`, accessToken);
    localStorage.setItem(`fairydust_${this.config.appId}_refresh_token`, refreshToken);
  }

  private clearTokens(): void {
    localStorage.removeItem(`fairydust_${this.config.appId}_access_token`);
    localStorage.removeItem(`fairydust_${this.config.appId}_refresh_token`);
  }

  // Authentication methods
  async requestOTP(request: OTPRequest): Promise<{ message: string; identifier: string }> {
    return this.request('/auth/otp/request', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  async verifyOTP(request: OTPVerify): Promise<AuthResponse> {
    const response = await this.request<AuthResponse>('/auth/otp/verify', {
      method: 'POST',
      body: JSON.stringify(request),
    });

    // Store tokens
    this.setTokens(response.token.access_token, response.token.refresh_token);

    return response;
  }

  async refreshToken(): Promise<{ access_token: string; refresh_token: string }> {
    const refreshToken = localStorage.getItem(`fairydust_${this.config.appId}_refresh_token`);
    
    if (!refreshToken) {
      throw new Error('No refresh token available');
    }

    const response = await this.request<{ access_token: string; refresh_token: string }>('/auth/refresh', {
      method: 'POST',
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    this.setTokens(response.access_token, response.refresh_token);
    
    return response;
  }

  async logout(): Promise<void> {
    try {
      await this.request('/auth/logout', {
        method: 'POST',
      });
    } finally {
      this.clearTokens();
    }
  }

  // User methods
  async getCurrentUser(): Promise<User> {
    return this.request('/users/me');
  }

  async getUserBalance(): Promise<{ balance: number }> {
    return this.request('/users/me/balance');
  }

  // Transaction methods
  async consumeDust(amount: number, description: string): Promise<DustTransaction> {
    // Call ledger service for transactions
    let ledgerUrl;
    if (this.config.ledgerUrl) {
      ledgerUrl = this.config.ledgerUrl.replace(/\/$/, '');
    } else {
      ledgerUrl = this.baseUrl.replace(':8001', ':8002');
    }
    
    // Get current user to extract user_id
    const user = await this.getCurrentUser();
    
    // Generate idempotency key
    const idempotencyKey = `${user.id}-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    
    const response = await fetch(`${ledgerUrl}/transactions/consume`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.getAccessToken()}`
      },
      body: JSON.stringify({ 
        user_id: user.id,
        amount, 
        action: description,
        app_id: this.config.appId,
        idempotency_key: idempotencyKey
      }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ 
        message: 'Network error' 
      }));
      throw new Error(error.message || `HTTP ${response.status}`);
    }

    return response.json();
  }

  async getTransactions(): Promise<DustTransaction[]> {
    return this.request('/transactions');
  }

  // Payment methods
  async purchaseDust(request: PurchaseRequest): Promise<DustTransaction> {
    return this.request('/payments/purchase', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  async getPaymentMethods(): Promise<any[]> {
    return this.request('/payments/methods');
  }

  // Utility methods
  isAuthenticated(): boolean {
    return !!this.getAccessToken();
  }

  async checkConnection(): Promise<boolean> {
    try {
      await this.getCurrentUser();
      return true;
    } catch {
      return false;
    }
  }
}