/**
 * Fairydust Simple Integration
 * 
 * Usage:
 * <script src="https://fairydust.fun/sdk/simple.js?app=YOUR_APP_ID"></script>
 * <button class="fairydust-button" data-cost="5" onclick="yourFunction()">Pay with Dust</button>
 */

import { Fairydust } from './index';

// Get app ID from script tag
function getAppIdFromScript(): string | null {
  const scripts = document.getElementsByTagName('script');
  for (let i = 0; i < scripts.length; i++) {
    const src = scripts[i].src;
    if (src && src.includes('fairydust') && src.includes('app=')) {
      const urlParams = new URLSearchParams(src.split('?')[1]);
      return urlParams.get('app');
    }
  }
  return null;
}

// Initialize on load
if (typeof window !== 'undefined') {
  window.addEventListener('DOMContentLoaded', () => {
    const appId = getAppIdFromScript();
    if (!appId) {
      console.error('[Fairydust] No app ID found. Add ?app=YOUR_APP_ID to the script URL');
      return;
    }

    // Initialize Fairydust
    const fairydust = new Fairydust({ appId });
    
    // Store instance globally for optional advanced usage
    (window as any).fairydust = fairydust;

    // Auto-enhance all buttons with class "fairydust-button"
    const enhanceButtons = () => {
      const buttons = document.querySelectorAll('button.fairydust-button');
      
      buttons.forEach((button) => {
        const btn = button as HTMLButtonElement;
        
        // Skip if already enhanced
        if (btn.dataset.fairydustEnhanced === 'true') return;
        
        // Get cost from data attribute
        const cost = parseInt(btn.dataset.cost || '1');
        
        // Store original onclick
        const originalOnclick = btn.onclick;
        
        // Create wrapper div
        const wrapper = document.createElement('div');
        wrapper.className = 'fairydust-button-wrapper';
        wrapper.style.display = 'inline-block';
        
        // Insert wrapper and move button into it
        btn.parentNode?.insertBefore(wrapper, btn);
        wrapper.appendChild(btn);
        
        // Hide original button
        btn.style.display = 'none';
        
        // Create Fairydust button in wrapper
        fairydust.createButtonComponent(wrapper, {
          dustCost: cost,
          children: btn.innerHTML,
          disabled: btn.disabled,
          onSuccess: async (transaction) => {
            // Call original onclick if it exists
            if (originalOnclick) {
              originalOnclick.call(btn, new Event('click'));
            }
            
            // The main SDK automatically refreshes account components after successful payments
            
            // Also dispatch a custom event for flexibility
            btn.dispatchEvent(new CustomEvent('fairydust:success', { 
              detail: { transaction },
              bubbles: true 
            }));
          },
          onError: (error) => {
            console.error('[Fairydust] Payment failed:', error);
            btn.dispatchEvent(new CustomEvent('fairydust:error', { 
              detail: { error },
              bubbles: true 
            }));
          }
        });
        
        // Mark as enhanced
        btn.dataset.fairydustEnhanced = 'true';
        
        // Watch for disabled state changes
        const observer = new MutationObserver((mutations) => {
          mutations.forEach((mutation) => {
            if (mutation.attributeName === 'disabled') {
              // Re-render the button with new disabled state
              fairydust.createButtonComponent(wrapper, {
                dustCost: cost,
                children: btn.innerHTML,
                disabled: btn.disabled,
                onSuccess: async (transaction) => {
                  if (originalOnclick) {
                    originalOnclick.call(btn, new Event('click'));
                  }
                  btn.dispatchEvent(new CustomEvent('fairydust:success', { 
                    detail: { transaction },
                    bubbles: true 
                  }));
                }
              });
            }
          });
        });
        
        observer.observe(btn, { attributes: true, attributeFilter: ['disabled'] });
      });
    };
    
    // Enhance buttons on load
    enhanceButtons();
    
    // Also support dynamically added buttons
    const observer = new MutationObserver(() => {
      enhanceButtons();
    });
    
    observer.observe(document.body, { 
      childList: true, 
      subtree: true 
    });
    
    // Optional: Add account widget if element exists
    const accountElement = document.getElementById('fairydust-account');
    if (accountElement) {
      fairydust.createAccountComponent(accountElement, {
        onConnect: (user) => {
          console.log('[Fairydust] User connected:', user);
        },
        onDisconnect: () => {
          console.log('[Fairydust] User disconnected');
        }
      });
    }
    
    console.log('[Fairydust] Ready! App ID:', appId);
  });
}