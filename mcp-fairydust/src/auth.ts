import fetch from 'node-fetch';
import { z } from 'zod';
import { SessionStore } from './session-store.js';

// Token schemas
const AuthResponseSchema = z.object({
  access_token: z.string(),
  refresh_token: z.string(),
  token_type: z.string(),
  expires_in: z.number()
});

const UserInfoSchema = z.object({
  user_id: z.string(),
  email: z.string().optional(),
  fairyname: z.string().optional(),
  dust_balance: z.number().optional()
});

type AuthResponse = z.infer<typeof AuthResponseSchema>;
type UserInfo = z.infer<typeof UserInfoSchema>;

interface SessionData {
  email: string;
  accessToken: string;
  refreshToken: string;
  expiresAt: number;
  userInfo?: UserInfo;
}

export class AuthManager {
  private sessions: Map<string, SessionData> = new Map();
  private identityUrl: string;
  private sessionStore: SessionStore;

  constructor() {
    const environment = process.env.ENVIRONMENT || 'staging';
    const suffix = environment === 'production' ? 'production' : 'staging';
    this.identityUrl = `https://fairydust-identity-${suffix}.up.railway.app`;
    this.sessionStore = new SessionStore();
    this.loadStoredSession();
  }

  private async loadStoredSession(): Promise<void> {
    const stored = await this.sessionStore.load();
    if (stored) {
      this.sessions.set(stored.email, stored);
    }
  }

  async requestOTP(email: string): Promise<{ success: boolean; message: string }> {
    try {
      const response = await fetch(`${this.identityUrl}/auth/otp/request`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          identifier: email,
          identifier_type: 'email'
        })
      });

      if (response.ok) {
        return {
          success: true,
          message: `Verification code sent to ${email}. Please check your email.`
        };
      }

      const error = await response.text();
      return {
        success: false,
        message: `Failed to send verification code: ${error}`
      };
    } catch (error) {
      return {
        success: false,
        message: `Connection error: ${error instanceof Error ? error.message : 'Unknown error'}`
      };
    }
  }

  async verifyOTP(email: string, code: string): Promise<{ success: boolean; message: string; userInfo?: UserInfo }> {
    try {
      const response = await fetch(`${this.identityUrl}/auth/otp/verify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          identifier: email,
          code: code
        })
      });

      if (!response.ok) {
        const error = await response.text();
        return {
          success: false,
          message: `Invalid code: ${error}`
        };
      }

      const authData = AuthResponseSchema.parse(await response.json());
      
      // Get user info
      const userInfo = await this.getUserInfo(authData.access_token);
      
      // Store session
      const sessionData: SessionData = {
        email,
        accessToken: authData.access_token,
        refreshToken: authData.refresh_token,
        expiresAt: Date.now() + (authData.expires_in * 1000),
        userInfo
      };
      
      this.sessions.set(email, sessionData);
      
      // Store session persistently
      await this.sessionStore.save(sessionData);

      return {
        success: true,
        message: `Successfully authenticated as ${userInfo?.fairyname || email}`,
        userInfo
      };
    } catch (error) {
      return {
        success: false,
        message: `Verification failed: ${error instanceof Error ? error.message : 'Unknown error'}`
      };
    }
  }

  async getUserInfo(token: string): Promise<UserInfo | undefined> {
    try {
      const response = await fetch(`${this.identityUrl}/users/me`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        const data = await response.json();
        return UserInfoSchema.parse(data);
      }
    } catch (error) {
      console.error('Failed to get user info:', error);
    }
    return undefined;
  }

  async refreshToken(email: string): Promise<boolean> {
    const session = this.sessions.get(email);
    if (!session) return false;

    try {
      const response = await fetch(`${this.identityUrl}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          refresh_token: session.refreshToken
        })
      });

      if (!response.ok) {
        this.sessions.delete(email);
        return false;
      }

      const authData = AuthResponseSchema.parse(await response.json());
      
      // Update session
      session.accessToken = authData.access_token;
      session.refreshToken = authData.refresh_token;
      session.expiresAt = Date.now() + (authData.expires_in * 1000);
      
      // Update stored session
      await this.sessionStore.save(session);
      
      return true;
    } catch (error) {
      console.error('Token refresh failed:', error);
      this.sessions.delete(email);
      return false;
    }
  }

  async getValidToken(email: string): Promise<string | null> {
    const session = this.sessions.get(email);
    if (!session) return null;

    // Check if token is expired
    if (Date.now() >= session.expiresAt - 60000) { // Refresh 1 minute before expiry
      const refreshed = await this.refreshToken(email);
      if (!refreshed) return null;
    }

    return session.accessToken;
  }

  getSession(email: string): SessionData | undefined {
    return this.sessions.get(email);
  }

  async clearSession(email: string): Promise<void> {
    this.sessions.delete(email);
    await this.sessionStore.clear();
  }

  getActiveSession(): SessionData | undefined {
    // Return the most recently used session
    const sessions = Array.from(this.sessions.values());
    return sessions[sessions.length - 1];
  }
}