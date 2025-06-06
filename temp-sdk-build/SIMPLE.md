# Fairydust Simple Integration

The absolute easiest way to add DUST payments to your app.

## Quick Start

Add one script tag and you're done:

```html
<script src="https://fairydust.fun/sdk/simple.js?app=YOUR_APP_ID"></script>
<button class="fairydust-button" data-cost="5" onclick="yourFunction()">
  Pay 5 DUST
</button>
```

That's it! No initialization code, no complex setup.

## Examples

### Basic Button
```html
<button class="fairydust-button" data-cost="2" onclick="generatePlaylist()">
  Generate Playlist (2 DUST)
</button>
```

### Multiple Costs
```html
<!-- Different features, different costs -->
<button class="fairydust-button" data-cost="1" onclick="quickAction()">
  Quick Feature (1 DUST)
</button>

<button class="fairydust-button" data-cost="10" onclick="premiumFeature()">
  Premium Feature (10 DUST)
</button>
```

### Dynamic Buttons
```html
<button class="fairydust-button" data-cost="3" id="my-button" disabled>
  Process Data (3 DUST)
</button>

<script>
  // Enable/disable as needed
  document.getElementById('my-button').disabled = false;
</script>
```

### Event-Based (Alternative to onclick)
```html
<button class="fairydust-button" data-cost="5" id="event-button">
  Pay 5 DUST
</button>

<script>
  document.getElementById('event-button').addEventListener('fairydust:success', (e) => {
    console.log('Payment succeeded!', e.detail.transaction);
    // Your app logic here
  });
</script>
```

## Optional Features

### Account Widget
Show user balance and login status:

```html
<div id="fairydust-account"></div>
```

The script automatically creates an account widget if this element exists. The account widget will automatically update when:
- User authenticates through any payment button
- User's balance changes after successful payments
- User disconnects their account

### Global Events
Listen to all fairydust events:

```javascript
document.addEventListener('fairydust:success', (e) => {
  console.log('Any button succeeded:', e.detail.transaction);
});

document.addEventListener('fairydust:error', (e) => {
  console.log('Payment failed:', e.detail.error);
});
```

## Migration from Complex Integration

**Before (complex):**
```html
<script src="https://fairydust.fun/sdk/index.umd.js"></script>
<script>
  const fairydust = new Fairydust.Fairydust({
    appId: 'YOUR_APP_ID',
    apiUrl: 'https://fairydust-identity-production.up.railway.app',
    ledgerUrl: 'https://fairydust-ledger-production.up.railway.app'
  });

  fairydust.createAccountComponent('#fairydust-account');
  
  function updateButton() {
    fairydust.createButtonComponent('#button-container', {
      dustCost: 5,
      children: 'Pay 5 DUST',
      onSuccess: (transaction) => {
        yourFunction();
      }
    });
  }
  
  updateButton();
</script>
```

**After (simple):**
```html
<script src="https://fairydust.fun/sdk/simple.js?app=YOUR_APP_ID"></script>
<button class="fairydust-button" data-cost="5" onclick="yourFunction()">
  Pay 5 DUST
</button>
<div id="fairydust-account"></div>
```

**Savings:** ~30 lines → 3 lines!

## How It Works

1. **Script loads** and reads the `app` parameter from its own URL
2. **Auto-initializes** fairydust with your app ID
3. **Finds all buttons** with class `fairydust-button`
4. **Enhances them** with payment functionality
5. **Calls your onclick** function after successful payment

The enhanced buttons are fully managed - they handle disabled states, show loading, process payments, and call your functions seamlessly.

## Production URLs

- **Sandbox**: `https://fairydust.fun/sdk/simple.js?app=YOUR_APP_ID`
- **Production**: `https://fairydust.fun/sdk/simple.js?app=YOUR_APP_ID`

Both point to the same SDK - it automatically detects the environment.