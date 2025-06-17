import { FairydustAPI } from '../utils/api';
import { User, AccountComponentProps } from '../types';
import { AuthenticationComponent } from './AuthenticationComponent';

export class AccountComponent {
  private api: FairydustAPI;
  private container: HTMLElement;
  private props: AccountComponentProps;
  private user: User | null = null;
  private isConnected = false;

  constructor(api: FairydustAPI, container: HTMLElement, props: AccountComponentProps = {}) {
    this.api = api;
    this.container = container;
    this.props = props;
    
    this.init();
  }

  private async init(): Promise<void> {
    try {
      if (this.api.isAuthenticated()) {
        this.user = await this.api.getCurrentUser();
        this.isConnected = true;
        this.props.onConnect?.(this.user);
      }
    } catch (error) {
      console.error('Failed to load user:', error);
      this.isConnected = false;
    }

    this.render();
  }

  private render(): void {
    const fairy = '🧚‍♀️';
    const balance = this.isConnected ? this.user?.dust_balance || 0 : 0;
    const stateClass = this.isConnected ? 'connected' : 'disconnected';

    this.container.innerHTML = `
      <div class="fairydust-account ${stateClass}" data-testid="fairydust-account">
        <span class="fairydust-fairy">${fairy}</span>
        <span class="fairydust-balance">${balance}</span>
      </div>
    `;

    const element = this.container.querySelector('.fairydust-account') as HTMLElement;
    element.addEventListener('click', () => this.handleClick());
  }

  private handleClick(): void {
    if (this.isConnected && this.user) {
      this.showAccountDetails();
    } else {
      this.showAuthentication();
    }
  }

  private showAccountDetails(): void {
    if (!this.user) return;

    const modal = this.createModal();
    modal.innerHTML = `
      <div class="fairydust-modal-content">
        <button class="fairydust-close">&times;</button>
        <div class="fairydust-account-details">
          <div class="fairydust-fairyname">${this.user.fairyname}</div>
          <div class="fairydust-balance-large">${this.user.dust_balance} <span style="font-size: 16px;">DUST</span></div>
          <div class="fairydust-actions">
            <button class="fairydust-button-primary" data-action="buy-dust">Buy More Dust</button>
            <button class="fairydust-button-secondary" data-action="visit-site">Visit fairydust.fun</button>
            <button class="fairydust-button-secondary" data-action="disconnect">Disconnect Account</button>
          </div>
        </div>
      </div>
    `;

    this.attachModalEvents(modal);
    document.body.appendChild(modal);
  }

  private showAuthentication(): void {
    const modal = this.createModal();
    
    // Create authentication component
    const authComponent = new AuthenticationComponent(
      this.api,
      modal,
      {
        appName: document.title || 'This App',
        onSuccess: (authResponse) => {
          this.user = authResponse.user;
          this.isConnected = true;
          this.render();
          this.props.onConnect?.(this.user);
          this.props.onBalanceUpdate?.(this.user.dust_balance);
          this.closeModal(modal);
        },
        onCancel: () => {
          this.closeModal(modal);
        }
      }
    );

    document.body.appendChild(modal);
  }

  private createModal(): HTMLElement {
    const modal = document.createElement('div');
    modal.className = 'fairydust-modal';
    return modal;
  }

  private attachModalEvents(modal: HTMLElement): void {
    // Close button
    const closeBtn = modal.querySelector('.fairydust-close');
    closeBtn?.addEventListener('click', () => this.closeModal(modal));

    // Modal background click
    modal.addEventListener('click', (e) => {
      if (e.target === modal) {
        this.closeModal(modal);
      }
    });

    // Action buttons
    modal.addEventListener('click', async (e) => {
      const target = e.target as HTMLElement;
      const action = target.getAttribute('data-action');

      switch (action) {
        case 'buy-dust':
          this.showPurchaseFlow(modal);
          break;
        case 'visit-site':
          window.open('https://fairydust.fun', '_blank');
          break;
        case 'disconnect':
          await this.disconnect();
          this.closeModal(modal);
          break;
      }
    });

    // Escape key
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        this.closeModal(modal);
        document.removeEventListener('keydown', handleEscape);
      }
    };
    document.addEventListener('keydown', handleEscape);
  }

  private showPurchaseFlow(modal: HTMLElement): void {
    // TODO: Implement purchase flow
    // For now, redirect to fairydust.fun
    window.open('https://fairydust.fun/purchase', '_blank');
  }

  private async disconnect(): Promise<void> {
    try {
      await this.api.logout();
      this.user = null;
      this.isConnected = false;
      this.render();
      this.props.onDisconnect?.();
    } catch (error) {
      console.error('Failed to disconnect:', error);
    }
  }

  private closeModal(modal: HTMLElement): void {
    modal.remove();
  }

  // Public methods
  async refresh(): Promise<void> {
    if (this.isConnected) {
      try {
        this.user = await this.api.getCurrentUser();
        this.render();
        this.props.onBalanceUpdate?.(this.user.dust_balance);
      } catch (error) {
        console.error('Failed to refresh user:', error);
      }
    }
  }

  getUser(): User | null {
    return this.user;
  }

  isUserConnected(): boolean {
    return this.isConnected;
  }
}