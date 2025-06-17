# fairydust Integration Guide

## Quick Start (10 lines of code!)

```html
<!-- 1. Include fairydust -->
<script src="https://unpkg.com/fairydust-js@latest/dist/index.umd.js"></script>
<link rel="stylesheet" href="https://unpkg.com/fairydust-js@latest/dist/fairydust.css">

<!-- 2. Add a button container -->
<div id="my-ai-button"></div>

<!-- 3. Initialize fairydust -->
<script>
const fairydust = new Fairydust.Fairydust({
    appId: 'YOUR-APP-ID'  // Get this when you register your app
});

// Create a payment button
fairydust.createButtonComponent('#my-ai-button', {
    dustCost: 5,
    label: 'Generate with AI',  // Clear, intuitive naming
    onSuccess: () => {
        // User paid! Do your AI magic here
        generateContent();
    }
});
</script>
```

## Understanding the API URL

By default, fairydust connects to production (`https://api.fairydust.fun`). You can override this for:

### 1. Local Development
```javascript
const fairydust = new Fairydust.Fairydust({
    apiUrl: 'http://localhost:8001',  // Local fairydust instance
    appId: 'YOUR-APP-ID'
});
```

### 2. Sandbox/Testing (coming soon)
```javascript
const fairydust = new Fairydust.Fairydust({
    apiUrl: 'https://sandbox.fairydust.fun',  // Test with fake DUST
    appId: 'YOUR-APP-ID'
});
```

### 3. Staging Environment
```javascript
const fairydust = new Fairydust.Fairydust({
    apiUrl: 'https://staging.fairydust.fun',
    appId: 'YOUR-APP-ID'
});
```

## Complete Example: Yoga Playlist Generator

```html
<!DOCTYPE html>
<html>
<head>
    <title>AI Yoga Playlist Generator</title>
    <link rel="stylesheet" href="https://unpkg.com/fairydust-js@latest/dist/fairydust.css">
</head>
<body>
    <!-- Optional: Show user account -->
    <div id="account-widget"></div>
    
    <!-- Your app UI -->
    <div class="playlist-generator">
        <h1>AI Yoga Playlist Generator</h1>
        <select id="playlist-type">
            <option value="basic">Basic Flow (5 DUST)</option>
            <option value="extended">Extended Session (8 DUST)</option>
        </select>
        
        <!-- fairydust payment button -->
        <div id="generate-button"></div>
        
        <div id="results"></div>
    </div>

    <script src="https://unpkg.com/fairydust-js@latest/dist/index.umd.js"></script>
    <script>
        // Initialize fairydust
        const fairydust = new Fairydust.Fairydust({
            appId: 'YOUR-YOGA-APP-ID',
            // apiUrl: 'http://localhost:8001'  // Uncomment for local testing
        });

        // Optional: Account widget
        fairydust.createAccountComponent('#account-widget');

        // Dynamic pricing based on selection
        function updateButton() {
            const type = document.getElementById('playlist-type').value;
            const cost = type === 'basic' ? 5 : 8;
            const label = type === 'basic' ? 
                'Generate Basic Playlist' : 
                'Generate Extended Playlist';

            // Update or create button
            fairydust.createButtonComponent('#generate-button', {
                dustCost: cost,
                label: label,
                onSuccess: async (transaction) => {
                    // Payment successful! Generate playlist
                    document.getElementById('results').innerHTML = 'Generating...';
                    
                    try {
                        const playlist = await generateYogaPlaylist(type);
                        displayPlaylist(playlist);
                    } catch (error) {
                        document.getElementById('results').innerHTML = 'Error: ' + error;
                    }
                },
                onError: (error) => {
                    console.error('Payment failed:', error);
                    alert('Payment failed: ' + error);
                }
            });
        }

        // Update button when selection changes
        document.getElementById('playlist-type').addEventListener('change', updateButton);
        
        // Initialize button
        updateButton();

        // Your playlist generation logic
        async function generateYogaPlaylist(type) {
            // Call your backend API
            const response = await fetch('/api/generate-playlist', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ type })
            });
            return response.json();
        }

        function displayPlaylist(playlist) {
            // Show the generated playlist
            document.getElementById('results').innerHTML = 
                `<h2>Your Playlist</h2>` + 
                playlist.tracks.map(t => `<div>${t.name} - ${t.artist}</div>`).join('');
        }
    </script>
</body>
</html>
```

## API Reference

### Button Component

```javascript
fairydust.createButtonComponent(selector, {
    dustCost: number,        // Cost in DUST
    label: string,           // Button text (or use 'children' for compatibility)
    onSuccess: function,     // Called after successful payment
    onError: function,       // Called if payment fails
    disabled: boolean,       // Disable the button
    className: string        // Additional CSS classes
});
```

### Account Component

```javascript
fairydust.createAccountComponent(selector, {
    onConnect: function,     // Called when user connects
    onDisconnect: function,  // Called when user disconnects  
    onBalanceUpdate: function // Called when balance changes
});
```

## Testing Your Integration

1. **Local Testing**: Use `apiUrl: 'http://localhost:8001'` to test against your local fairydust instance
2. **Test Accounts**: Use the sandbox environment (coming soon) to test without consuming real DUST
3. **Debug Mode**: Add `debug: true` to your config for verbose console logging

## Best Practices

1. **Clear Pricing**: Always show users how much DUST an action costs
2. **Error Handling**: Always implement `onError` callbacks
3. **Loading States**: Show loading indicators during AI processing
4. **Balance Awareness**: Consider using the account widget so users can see their balance

## Getting Your App ID

1. Register your app at https://fairydust.fun/developers
2. Provide your app details and DUST pricing
3. Get approved and receive your unique app ID
4. Start accepting DUST payments!
</content>