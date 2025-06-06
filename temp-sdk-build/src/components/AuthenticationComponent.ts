import { FairydustAPI } from '../utils/api';
import { AuthenticationProps, AuthResponse } from '../types';

export class AuthenticationComponent {
  private api: FairydustAPI;
  private container: HTMLElement;
  private props: AuthenticationProps;
  private currentStep: 'input' | 'otp' = 'input';
  private identifier = '';
  private identifierType: 'email' | 'phone' = 'email';

  constructor(api: FairydustAPI, container: HTMLElement, props: AuthenticationProps) {
    this.api = api;
    this.container = container;
    this.props = props;
    
    this.render();
  }

  private render(): void {
    if (this.currentStep === 'input') {
      this.renderIdentifierInput();
    } else {
      this.renderOTPInput();
    }
  }

  private renderIdentifierInput(): void {
    this.container.innerHTML = `
      <div class="fairydust-modal-content">
        <button class="fairydust-close">&times;</button>
        <div class="fairydust-auth">
          <h2>Connect with fairydust</h2>
          <p><strong>${this.props.appName}</strong> uses fairydust to help cover AI costs. New users get 25 dust for free by providing phone or email.</p>
          
          <form class="fairydust-form" data-testid="auth-form">
            <div>
              <label style="display: block; margin-bottom: 8px; font-weight: 600; color: #374151;">
                Sign up or log in
              </label>
              <input 
                type="text" 
                class="fairydust-input" 
                placeholder="Enter email or phone number"
                data-testid="identifier-input"
                required
              />
            </div>
            
            <button type="submit" class="fairydust-button-primary" data-testid="submit-button">
              Continue
            </button>
            
            <div class="fairydust-error" style="display: none;" data-testid="error-message"></div>
          </form>
        </div>
      </div>
    `;

    this.attachIdentifierEvents();
    
    // Auto-focus the input
    setTimeout(() => {
      const input = this.container.querySelector('.fairydust-input') as HTMLInputElement;
      if (input) input.focus();
    }, 100);
  }

  private renderOTPInput(): void {
    this.container.innerHTML = `
      <div class="fairydust-modal-content">
        <button class="fairydust-close">&times;</button>
        <div class="fairydust-auth">
          <h2>Enter Verification Code</h2>
          <p>We've sent a 6-digit code to <strong>${this.identifier}</strong></p>
          
          <form class="fairydust-form" data-testid="otp-form">
            <div>
              <input 
                type="text" 
                class="fairydust-input fairydust-otp-input" 
                placeholder="000000"
                maxlength="6"
                pattern="[0-9]{6}"
                data-testid="otp-input"
                required
              />
            </div>
            
            <button type="submit" class="fairydust-button-primary" data-testid="verify-button">
              Verify
            </button>
            
            <button type="button" class="fairydust-button-secondary" data-testid="back-button">
              Use Different ${this.identifierType === 'email' ? 'Email' : 'Phone'}
            </button>
            
            <div class="fairydust-error" style="display: none;" data-testid="error-message"></div>
          </form>
        </div>
      </div>
    `;

    this.attachOTPEvents();
    
    // Auto-focus the OTP input
    setTimeout(() => {
      const input = this.container.querySelector('.fairydust-otp-input') as HTMLInputElement;
      if (input) input.focus();
    }, 100);
  }

  private attachIdentifierEvents(): void {
    const form = this.container.querySelector('[data-testid="auth-form"]') as HTMLFormElement;
    const input = this.container.querySelector('[data-testid="identifier-input"]') as HTMLInputElement;
    const submitBtn = this.container.querySelector('[data-testid="submit-button"]') as HTMLButtonElement;
    const errorDiv = this.container.querySelector('[data-testid="error-message"]') as HTMLElement;
    const closeBtn = this.container.querySelector('.fairydust-close') as HTMLElement;

    // Auto-focus
    input.focus();

    // Close events
    closeBtn.addEventListener('click', () => this.props.onCancel?.());
    this.container.addEventListener('click', (e) => {
      if (e.target === this.container) {
        this.props.onCancel?.();
      }
    });

    // Form submission
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      
      const value = input.value.trim();
      if (!value) return;

      this.identifier = value;
      this.identifierType = this.detectIdentifierType(value);

      try {
        submitBtn.disabled = true;
        submitBtn.textContent = 'Sending...';
        
        await this.api.requestOTP({
          identifier: this.identifier,
          identifier_type: this.identifierType
        });

        this.currentStep = 'otp';
        this.render();
      } catch (error) {
        this.showError(errorDiv, error instanceof Error ? error.message : 'Failed to send verification code');
      } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Continue';
      }
    });
  }

  private attachOTPEvents(): void {
    const form = this.container.querySelector('[data-testid="otp-form"]') as HTMLFormElement;
    const input = this.container.querySelector('[data-testid="otp-input"]') as HTMLInputElement;
    const verifyBtn = this.container.querySelector('[data-testid="verify-button"]') as HTMLButtonElement;
    const backBtn = this.container.querySelector('[data-testid="back-button"]') as HTMLButtonElement;
    const errorDiv = this.container.querySelector('[data-testid="error-message"]') as HTMLElement;
    const closeBtn = this.container.querySelector('.fairydust-close') as HTMLElement;

    // Auto-focus
    input.focus();

    // Close events
    closeBtn.addEventListener('click', () => this.props.onCancel?.());
    this.container.addEventListener('click', (e) => {
      if (e.target === this.container) {
        this.props.onCancel?.();
      }
    });

    // Back button
    backBtn.addEventListener('click', () => {
      this.currentStep = 'input';
      this.render();
    });

    // OTP input formatting
    input.addEventListener('input', (e) => {
      const target = e.target as HTMLInputElement;
      const value = target.value.replace(/\D/g, ''); // Only digits
      target.value = value;
      
      // Auto-submit when 6 digits entered
      if (value.length === 6) {
        form.dispatchEvent(new Event('submit', { cancelable: true }));
      }
    });

    // Form submission
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      
      const code = input.value.trim();
      if (code.length !== 6) {
        this.showError(errorDiv, 'Please enter a 6-digit code');
        return;
      }

      try {
        verifyBtn.disabled = true;
        verifyBtn.textContent = 'Verifying...';
        
        const authResponse = await this.api.verifyOTP({
          identifier: this.identifier,
          code
        });

        this.props.onSuccess?.(authResponse);
      } catch (error) {
        this.showError(errorDiv, error instanceof Error ? error.message : 'Invalid verification code');
        input.value = '';
        input.focus();
      } finally {
        verifyBtn.disabled = false;
        verifyBtn.textContent = 'Verify';
      }
    });
  }

  private detectIdentifierType(value: string): 'email' | 'phone' {
    // Simple email pattern
    if (value.includes('@') && value.includes('.')) {
      return 'email';
    }
    // Assume phone if it starts with + or contains only digits/spaces/dashes
    return 'phone';
  }

  private showError(errorDiv: HTMLElement, message: string): void {
    errorDiv.textContent = message;
    errorDiv.style.display = 'block';
    
    // Hide error after 5 seconds
    setTimeout(() => {
      errorDiv.style.display = 'none';
    }, 5000);
  }
}