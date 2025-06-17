import { FairydustAPI } from './utils/api';
import { AccountComponent } from './components/AccountComponent';
import { ButtonComponent } from './components/ButtonComponent';
import { AuthenticationComponent } from './components/AuthenticationComponent';
import { 
  FairydustConfig, 
  AccountComponentProps, 
  ButtonComponentProps, 
  AuthenticationProps,
  User,
  AuthState
} from './types';

// Import styles
import './styles/components.css';

export class Fairydust {
  private api: FairydustAPI;
  private config: FairydustConfig;
  private accountComponents: AccountComponent[] = [];

  constructor(config: FairydustConfig) {
    this.config = config;
    this.api = new FairydustAPI(config);

    if (config.debug) {
      console.log('Fairydust SDK initialized:', config);
    }
  }

  // Core API access
  getAPI(): FairydustAPI {
    return this.api;
  }

  // Authentication state
  async getAuthState(): Promise<AuthState> {
    if (!this.api.isAuthenticated()) {
      return { isConnected: false };
    }

    try {
      const user = await this.api.getCurrentUser();
      return {
        isConnected: true,
        user
      };
    } catch (error) {
      return { isConnected: false };
    }
  }

  // Component factory methods
  createAccountComponent(container: HTMLElement | string, props: AccountComponentProps = {}): AccountComponent {
    const element = typeof container === 'string' 
      ? document.querySelector(container) as HTMLElement
      : container;

    if (!element) {
      throw new Error('Container element not found');
    }

    const component = new AccountComponent(this.api, element, props);
    this.accountComponents.push(component);
    return component;
  }

  createButtonComponent(container: HTMLElement | string, props: ButtonComponentProps): ButtonComponent {
    const element = typeof container === 'string' 
      ? document.querySelector(container) as HTMLElement
      : container;

    if (!element) {
      throw new Error('Container element not found');
    }

    // Wrap the onSuccess callback to refresh account components
    const originalOnSuccess = props.onSuccess;
    props.onSuccess = (transaction) => {
      // Refresh all account components
      this.refreshAccountComponents();
      // Call original callback if provided
      originalOnSuccess?.(transaction);
    };

    return new ButtonComponent(this.api, element, props);
  }

  createAuthenticationComponent(container: HTMLElement | string, props: AuthenticationProps): AuthenticationComponent {
    const element = typeof container === 'string' 
      ? document.querySelector(container) as HTMLElement
      : container;

    if (!element) {
      throw new Error('Container element not found');
    }

    return new AuthenticationComponent(this.api, element, props);
  }

  // Convenience methods
  async isConnected(): Promise<boolean> {
    return this.api.checkConnection();
  }

  async getCurrentUser(): Promise<User | null> {
    try {
      return await this.api.getCurrentUser();
    } catch {
      return null;
    }
  }

  async logout(): Promise<void> {
    return this.api.logout();
  }

  // Component management
  private async refreshAccountComponents(): Promise<void> {
    for (const component of this.accountComponents) {
      await component.refresh();
    }
  }

  // Static factory method
  static create(config: FairydustConfig): Fairydust {
    return new Fairydust(config);
  }
}

// Export types and components for advanced usage
export { FairydustAPI };
export { AccountComponent, ButtonComponent, AuthenticationComponent };
export type { 
  FairydustConfig, 
  AccountComponentProps, 
  ButtonComponentProps, 
  AuthenticationProps,
  User,
  AuthState,
  AuthResponse,
  DustTransaction
};

// Default export
export default Fairydust;