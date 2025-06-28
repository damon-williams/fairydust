export interface LoginRequest {
  identifier: string;
  identifier_type: 'email' | 'phone';
}

export interface LoginVerifyRequest {
  identifier: string;
  code: string;
}

export interface AuthUser {
  id: string;
  fairyname: string;
  email?: string;
  is_admin: boolean;
  session_token?: string;
}

export interface AuthState {
  user: AuthUser | null;
  isLoading: boolean;
  isAuthenticated: boolean;
}

export interface OTPResponse {
  success: boolean;
  message: string;
}

export interface LoginResponse {
  success: boolean;
  user?: AuthUser;
  message?: string;
}