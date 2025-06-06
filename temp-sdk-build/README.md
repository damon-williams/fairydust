# fairydust JavaScript SDK

The official JavaScript SDK for integrating fairydust into web applications.

## Installation

```bash
npm install @fairydust/sdk
```

## Quick Start

```html
<!DOCTYPE html>
<html>
<head>
    <title>My App</title>
    <link rel="stylesheet" href="node_modules/@fairydust/sdk/dist/fairydust.css">
</head>
<body>
    <!-- Account Component -->
    <div id="fairydust-account"></div>
    
    <!-- Button Component -->
    <div id="ai-button"></div>
    
    <script src="node_modules/@fairydust/sdk/dist/index.umd.js"></script>
    <script>
        // Initialize fairydust
        const fairydust = new Fairydust({
            apiUrl: 'https://api.fairydust.fun',
            appId: 'your-app-id',
            debug: true
        });

        // Create account component
        const accountComponent = fairydust.createAccountComponent('#fairydust-account', {
            onConnect: (user) => console.log('User connected:', user),
            onDisconnect: () => console.log('User disconnected'),
            onBalanceUpdate: (balance) => console.log('Balance updated:', balance)
        });

        // Create AI button
        const aiButton = fairydust.createButtonComponent('#ai-button', {
            dustCost: 5,
            children: 'Generate AI Content',
            onSuccess: (transaction) => {
                console.log('Dust consumed:', transaction);
                // Proceed with AI generation
                generateAIContent();
            },
            onError: (error) => console.error('Payment failed:', error)
        });

        function generateAIContent() {
            // Your AI generation logic here
            console.log('Generating AI content...');
        }
    </script>
</body>
</html>
```

## Components

### Account Component

The fairydust Account Component (fAC) displays the user's connection status and dust balance.

```javascript
const accountComponent = fairydust.createAccountComponent('#account-container', {
    onConnect: (user) => {
        console.log('User connected:', user.fairyname, user.dust_balance);
    },
    onDisconnect: () => {
        console.log('User disconnected');
    },
    onBalanceUpdate: (balance) => {
        console.log('New balance:', balance);
    }
});
```

**States:**
- **Connected**: Shows fairy emoji and current dust balance
- **Disconnected**: Shows fairy emoji and "0" balance

**Click behavior:**
- **Connected**: Shows account details with options to buy dust, visit fairydust.fun, or disconnect
- **Disconnected**: Shows authentication flow

### Button Component

The fairydust Button Component handles dust consumption for AI actions.

```javascript
const aiButton = fairydust.createButtonComponent('#button-container', {
    dustCost: 10,
    children: 'Ask AI Question',
    onSuccess: (transaction) => {
        // Dust consumed successfully
        callYourAIAPI();
    },
    onError: (error) => {
        console.error('Payment failed:', error);
    },
    disabled: false,
    className: 'my-custom-class'
});
```

**Click behavior:**
- **Connected + Sufficient Balance**: Shows confirmation screen
- **Connected + Insufficient Balance**: Shows top-up screen
- **Disconnected**: Shows authentication flow

### Authentication Component

The authentication component handles the sign-up/sign-in flow.

```javascript
const authComponent = fairydust.createAuthenticationComponent('#auth-container', {
    appName: 'My Amazing App',
    onSuccess: (authResponse) => {
        console.log('User authenticated:', authResponse.user);
        console.log('New user?', authResponse.is_new_user);
        console.log('Dust granted:', authResponse.dust_granted);
    },
    onCancel: () => {
        console.log('Authentication cancelled');
    }
});
```

## API Reference

### Fairydust Class

```javascript
const fairydust = new Fairydust({
    apiUrl: 'https://api.fairydust.fun',
    appId: 'your-app-id',
    debug: false
});
```

#### Methods

- `getAPI()` - Get the underlying API client
- `getAuthState()` - Get current authentication state
- `isConnected()` - Check if user is connected
- `getCurrentUser()` - Get current user data
- `logout()` - Disconnect user

### Configuration

```typescript
interface FairydustConfig {
    apiUrl: string;        // fairydust API endpoint
    appId: string;         // Your app identifier
    debug?: boolean;       // Enable debug logging
}
```

## Advanced Usage

### Using with Module Bundlers

```javascript
import Fairydust from '@fairydust/sdk';

const fairydust = new Fairydust({
    apiUrl: process.env.FAIRYDUST_API_URL,
    appId: process.env.FAIRYDUST_APP_ID,
    debug: process.env.NODE_ENV === 'development'
});
```

### Custom Styling

The SDK includes default styles, but you can customize them:

```css
/* Override default styles */
.fairydust-account.connected {
    border-color: #your-brand-color;
    color: #your-brand-color;
}

.fairydust-button {
    background: linear-gradient(135deg, #your-color1, #your-color2);
}
```

### Event Handling

```javascript
// Listen for authentication state changes
fairydust.getAPI().addEventListener('authStateChanged', (state) => {
    console.log('Auth state changed:', state);
});

// Check connection status
const isConnected = await fairydust.isConnected();
if (isConnected) {
    const user = await fairydust.getCurrentUser();
    console.log('Current user:', user);
}
```

### Error Handling

```javascript
const button = fairydust.createButtonComponent('#ai-button', {
    dustCost: 5,
    children: 'Generate Content',
    onError: (error) => {
        // Handle payment errors
        if (error.includes('insufficient')) {
            showTopUpDialog();
        } else {
            showGenericError(error);
        }
    }
});
```

## TypeScript Support

The SDK is written in TypeScript and includes full type definitions:

```typescript
import Fairydust, { User, AuthResponse, DustTransaction } from '@fairydust/sdk';

const fairydust = new Fairydust({
    apiUrl: 'https://api.fairydust.fun',
    appId: 'my-app'
});

fairydust.createAccountComponent('#account', {
    onConnect: (user: User) => {
        console.log(user.fairyname, user.dust_balance);
    }
});
```

## Examples

### React Integration

```jsx
import { useEffect, useRef } from 'react';
import Fairydust from '@fairydust/sdk';

function AIButton({ onGenerate }) {
    const buttonRef = useRef();
    const fairydustRef = useRef();

    useEffect(() => {
        fairydustRef.current = new Fairydust({
            apiUrl: process.env.REACT_APP_FAIRYDUST_API_URL,
            appId: process.env.REACT_APP_FAIRYDUST_APP_ID
        });

        fairydustRef.current.createButtonComponent(buttonRef.current, {
            dustCost: 10,
            children: 'Generate AI Content',
            onSuccess: () => onGenerate()
        });
    }, []);

    return <div ref={buttonRef} />;
}
```

### Vue Integration

```vue
<template>
    <div ref="accountRef"></div>
    <div ref="buttonRef"></div>
</template>

<script>
import Fairydust from '@fairydust/sdk';

export default {
    mounted() {
        this.fairydust = new Fairydust({
            apiUrl: process.env.VUE_APP_FAIRYDUST_API_URL,
            appId: process.env.VUE_APP_FAIRYDUST_APP_ID
        });

        this.fairydust.createAccountComponent(this.$refs.accountRef);
        this.fairydust.createButtonComponent(this.$refs.buttonRef, {
            dustCost: 5,
            children: 'Ask AI',
            onSuccess: this.handleAIRequest
        });
    },
    methods: {
        handleAIRequest() {
            // Handle successful dust consumption
        }
    }
};
</script>
```

## Support

- [Documentation](https://docs.fairydust.fun)
- [GitHub Issues](https://github.com/fairydust/fairydust-js/issues)
- [Community Discord](https://discord.gg/fairydust)

## License

MIT License - see LICENSE file for details.