import { FairydustAPI } from '../utils/api';
import { ButtonComponentProps, User, DustTransaction } from '../types';
import { AuthenticationComponent } from './AuthenticationComponent';

export class ButtonComponent {
  private api: FairydustAPI;
  private container: HTMLElement;
  private props: ButtonComponentProps;
  private user: User | null = null;
  private isConnected = false;

  constructor(api: FairydustAPI, container: HTMLElement, props: ButtonComponentProps) {
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
      }
    } catch (error) {
      console.error('Failed to load user:', error);
      this.isConnected = false;
    }

    this.render();
  }

  private render(): void {
    const fairy = '🧚‍♀️';
    const disabled = this.props.disabled ? 'disabled' : '';
    const className = `fairydust-button ${this.props.className || ''} ${disabled}`.trim();
    // Use label if provided, otherwise fall back to children
    const buttonText = this.props.label || this.props.children;

    this.container.innerHTML = `
      <button type="button" class="${className}" data-testid="fairydust-button" ${disabled}>
        <span>${buttonText}</span>
        <div class="fairydust-button-dust">
          <span class="fairydust-fairy">${fairy}</span>
          <span>${this.props.dustCost}</span>
        </div>
      </button>
    `;

    const button = this.container.querySelector('button') as HTMLButtonElement;
    button.addEventListener('click', () => this.handleClick());
  }

  private async handleClick(): Promise<void> {
    if (this.props.disabled) return;

    try {
      // Check authentication status fresh each time
      if (!this.api.isAuthenticated()) {
        this.showAuthentication();
        return;
      }

      // Refresh user data to get latest balance
      this.user = await this.api.getCurrentUser();
      this.isConnected = true;

      // Check if user has sufficient balance
      if (this.user.dust_balance < this.props.dustCost) {
        this.showInsufficientBalance();
        return;
      }

      // Check if user has disabled confirmations
      const skipConfirmations = localStorage.getItem(`fairydust_${this.api.config.appId}_skip_confirmations`) === 'true';
      
      if (skipConfirmations) {
        // Direct payment without confirmation
        this.animateButton();
        const transaction = await this.api.consumeDust(
          this.props.dustCost,
          `${this.props.children} - ${document.title || 'App'}`
        );
        
        // Update user balance
        if (this.user) {
          this.user.dust_balance -= this.props.dustCost;
        }
        
        this.props.onSuccess?.(transaction);
      } else {
        // Show confirmation modal
        this.showConfirmation();
      }

    } catch (error) {
      console.error('Button click error:', error);
      this.props.onError?.(error instanceof Error ? error.message : 'An error occurred');
    }
  }

  private showAuthentication(): void {
    const modal = this.createModal();
    
    const authComponent = new AuthenticationComponent(
      this.api,
      modal,
      {
        appName: document.title || 'This App',
        onSuccess: async (authResponse) => {
          this.user = authResponse.user;
          this.isConnected = true;
          this.closeModal(modal);
          
          // After authentication, check balance and proceed
          if (this.user.dust_balance >= this.props.dustCost) {
            this.showConfirmation();
          } else {
            this.showInsufficientBalance();
          }
        },
        onCancel: () => {
          this.closeModal(modal);
        }
      }
    );

    document.body.appendChild(modal);
  }

  private showConfirmation(): void {
    if (!this.user) return;

    const modal = this.createModal();
    modal.innerHTML = `
      <div class="fairydust-modal-content">
        <button class="fairydust-close">&times;</button>
        <div class="fairydust-confirmation">
          <h3>Confirm Action</h3>
          <p>This action will consume:</p>
          <div class="fairydust-dust-amount">${this.props.dustCost} <span style="font-size: 24px;">DUST</span></div>
          <div class="fairydust-current-balance">
            Your current balance: <strong>${this.user.dust_balance} DUST</strong>
          </div>
          <div style="margin: 16px 0; padding: 12px; background: #f8f9fa; border-radius: 6px; text-align: left;">
            <label style="display: flex; align-items: center; gap: 8px; cursor: pointer; font-size: 14px;">
              <input type="checkbox" id="skip-confirmations" style="margin: 0;">
              <span>Skip confirmations</span>
            </label>
          </div>
          <div class="fairydust-actions">
            <button class="fairydust-button-primary" data-action="confirm">
              Confirm & Use Dust
            </button>
            <button class="fairydust-button-secondary" data-action="cancel">
              Cancel
            </button>
          </div>
        </div>
      </div>
    `;

    this.attachConfirmationEvents(modal);
    document.body.appendChild(modal);
  }

  private showInsufficientBalance(): void {
    if (!this.user) return;

    const needed = this.props.dustCost - this.user.dust_balance;
    const modal = this.createModal();
    
    modal.innerHTML = `
      <div class="fairydust-modal-content">
        <button class="fairydust-close">&times;</button>
        <div class="fairydust-confirmation">
          <h3>Insufficient Dust</h3>
          <p>You need <strong>${this.props.dustCost} DUST</strong> but only have <strong>${this.user.dust_balance} DUST</strong></p>
          <div class="fairydust-dust-amount">+${needed} <span style="font-size: 24px;">DUST needed</span></div>
          <div class="fairydust-actions">
            <button class="fairydust-button-primary" data-action="buy-dust">
              Buy More Dust
            </button>
            <button class="fairydust-button-secondary" data-action="cancel">
              Cancel
            </button>
          </div>
        </div>
      </div>
    `;

    this.attachInsufficientBalanceEvents(modal);
    document.body.appendChild(modal);
  }

  private attachConfirmationEvents(modal: HTMLElement): void {
    this.attachModalEvents(modal);

    modal.addEventListener('click', async (e) => {
      const target = e.target as HTMLElement;
      const action = target.getAttribute('data-action');

      switch (action) {
        case 'confirm':
          // Check if user wants to skip future confirmations
          const checkbox = modal.querySelector('#skip-confirmations') as HTMLInputElement;
          if (checkbox?.checked) {
            localStorage.setItem(`fairydust_${this.api.config.appId}_skip_confirmations`, 'true');
          }
          await this.consumeDust(modal);
          break;
        case 'cancel':
          this.closeModal(modal);
          break;
      }
    });
  }

  private attachInsufficientBalanceEvents(modal: HTMLElement): void {
    this.attachModalEvents(modal);

    modal.addEventListener('click', (e) => {
      const target = e.target as HTMLElement;
      const action = target.getAttribute('data-action');

      switch (action) {
        case 'buy-dust':
          // TODO: Implement purchase flow
          window.open('https://fairydust.fun/purchase', '_blank');
          this.closeModal(modal);
          break;
        case 'cancel':
          this.closeModal(modal);
          break;
      }
    });
  }

  private async consumeDust(modal: HTMLElement): Promise<void> {
    try {
      const confirmBtn = modal.querySelector('[data-action="confirm"]') as HTMLButtonElement;
      confirmBtn.disabled = true;
      confirmBtn.textContent = 'Processing...';

      // Animate button
      this.animateButton();

      const transaction = await this.api.consumeDust(
        this.props.dustCost,
        `${this.props.children} - ${document.title || 'App'}`
      );

      // Update user balance
      if (this.user) {
        this.user.dust_balance -= this.props.dustCost;
      }

      this.closeModal(modal);
      this.props.onSuccess?.(transaction);

    } catch (error) {
      console.error('Failed to consume dust:', error);
      this.props.onError?.(error instanceof Error ? error.message : 'Failed to process payment');
    }
  }

  private animateButton(): void {
    const button = this.container.querySelector('button') as HTMLButtonElement;
    button.classList.add('loading');
    
    // Keep spinning fairy for the entire process - no jarring scale animation
    setTimeout(() => {
      button.classList.remove('loading');
    }, 1500);
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

    // Escape key
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        this.closeModal(modal);
        document.removeEventListener('keydown', handleEscape);
      }
    };
    document.addEventListener('keydown', handleEscape);
  }

  private closeModal(modal: HTMLElement): void {
    modal.remove();
  }

  // Public methods
  async refresh(): Promise<void> {
    if (this.isConnected) {
      try {
        this.user = await this.api.getCurrentUser();
      } catch (error) {
        console.error('Failed to refresh user:', error);
      }
    }
  }

  updateProps(props: Partial<ButtonComponentProps>): void {
    this.props = { ...this.props, ...props };
    this.render();
  }

  getUser(): User | null {
    return this.user;
  }
}