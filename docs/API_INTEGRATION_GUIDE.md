# fairydust API Integration Guide

## API Documentation Links

### Production Environment
- **Identity API**: https://fairydust-identity-production.up.railway.app/docs
- **Apps API**: https://fairydust-apps-production.up.railway.app/docs
- **Ledger API**: https://fairydust-ledger-production.up.railway.app/docs

### Sandbox Environment (coming soon)
- **Identity API**: https://fairydust-identity-sandbox.up.railway.app/docs
- **Apps API**: https://fairydust-apps-sandbox.up.railway.app/docs
- **Ledger API**: https://fairydust-ledger-sandbox.up.railway.app/docs

## Quick Start: Register Your App

### Step 1: Get Authentication Token

1. Go to https://fairydust-identity-production.up.railway.app/docs
2. Use the **POST /auth/otp/request** endpoint:
   ```json
   {
     "identifier": "your-email@example.com",
     "identifier_type": "email"
   }
   ```
3. Check your email for the OTP
4. Use the **POST /auth/otp/verify** endpoint:
   ```json
   {
     "identifier": "your-email@example.com",
     "code": "123456"
   }
   ```
5. Save the `access_token` from the response

### Step 2: Register Your App

1. Go to https://fairydust-apps-production.up.railway.app/docs
2. Click "Authorize" and enter your access token
3. Use the **POST /apps** endpoint:
   ```json
   {
     "name": "Your App Name",
     "slug": "your-app-slug",
     "description": "What your app does with AI",
     "icon_url": "https://yourapp.com/icon.png",
     "category": "creative",
     "website_url": "https://yourapp.com",
     "demo_url": "https://yourapp.com/demo",
     "callback_url": "https://yourapp.com/api/fairydust-webhook"
   }
   ```
4. Save the `id` from the response - this is your App ID

### Step 3: Integrate the SDK

```html
<!-- Include fairydust SDK -->
<script src="https://unpkg.com/fairydust-js@latest/dist/index.umd.js"></script>
<link rel="stylesheet" href="https://unpkg.com/fairydust-js@latest/dist/fairydust.css">

<script>
// Initialize with your App ID
const fairydust = new Fairydust.Fairydust({
    appId: 'YOUR-APP-ID-FROM-STEP-2'
});

// Create a payment button
fairydust.createButtonComponent('#pay-button', {
    dustCost: 5,
    label: 'Generate with AI',
    onSuccess: async (transaction) => {
        // Payment successful! Do your AI work
        console.log('Transaction:', transaction);
        await doYourAIWork();
    }
});
</script>

<!-- Place button in your HTML -->
<div id="pay-button"></div>
```

## Testing Your Integration

### Using the Sandbox (Recommended)

When sandbox is available, you can test without real DUST:

```javascript
const fairydust = new Fairydust.Fairydust({
    appId: 'YOUR-APP-ID',
    apiUrl: 'https://sandbox.fairydust.fun'  // Use sandbox API
});
```

### API Testing Tips

1. **Test Authentication Flow**
   - Use the Identity API `/docs` to test OTP flow
   - Try both email and phone authentication

2. **Check Your App Status**
   - Use Apps API `GET /apps/{app_id}` to check approval status
   - Apps must be approved before accepting payments

3. **Monitor Transactions**
   - Use Ledger API `GET /transactions` to see your app's transactions
   - Filter by `app_id` to see only your transactions

## API Authentication

All API requests (except auth endpoints) require a Bearer token:

```javascript
const response = await fetch('https://fairydust-apps-production.up.railway.app/apps', {
    headers: {
        'Authorization': `Bearer ${accessToken}`,
        'Content-Type': 'application/json'
    }
});
```

## Common Integration Patterns

### Dynamic Pricing

```javascript
// Change price based on user selection
function updateButton(feature) {
    const pricing = {
        'basic': 3,
        'standard': 5,
        'premium': 10
    };
    
    fairydust.createButtonComponent('#pay-button', {
        dustCost: pricing[feature],
        label: `Generate ${feature} content`,
        onSuccess: handlePayment
    });
}
```

### Check User Balance

```javascript
// Show content based on user's DUST balance
fairydust.createAccountComponent('#account-widget', {
    onConnect: (user) => {
        if (user.dust_balance >= 10) {
            showPremiumFeatures();
        }
    }
});
```

### Batch Operations

```javascript
// Let users pay once for multiple operations
fairydust.createButtonComponent('#batch-button', {
    dustCost: itemCount * 2,  // 2 DUST per item
    label: `Process ${itemCount} items`,
    onSuccess: async (transaction) => {
        for (let i = 0; i < itemCount; i++) {
            await processItem(items[i]);
        }
    }
});
```

## Webhook Integration (Coming Soon)

Register a callback URL to receive transaction notifications:

```json
POST /apps
{
    "callback_url": "https://yourapp.com/api/fairydust-webhook",
    // ... other app details
}
```

Your webhook will receive:
```json
{
    "event": "transaction.completed",
    "transaction": {
        "id": "...",
        "user_id": "...",
        "amount": 5,
        "app_id": "your-app-id"
    }
}
```

## Best Practices

1. **Clear Pricing**: Always show DUST cost before actions
2. **Error Handling**: Implement `onError` callbacks
3. **Loading States**: Show progress during AI operations
4. **Sandbox First**: Test thoroughly in sandbox before production
5. **API Rate Limits**: Respect rate limits (1000 req/hour)

## Support

- **API Issues**: Check the `/docs` endpoint for each service
- **Integration Help**: support@fairydust.fun
- **Feature Requests**: https://github.com/fairydust/feedback