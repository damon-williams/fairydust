#!/usr/bin/env node

/**
 * Register yoga-playlist-agents app using fairydust APIs
 * 
 * This script demonstrates how third-party developers would register
 * their apps programmatically using the fairydust APIs.
 */

const FAIRYDUST_URLS = {
    sandbox: {
        identity: 'https://fairydust-identity-sandbox.up.railway.app',
        apps: 'https://fairydust-apps-sandbox.up.railway.app',
        ledger: 'https://fairydust-ledger-sandbox.up.railway.app'
    },
    production: {
        identity: 'https://fairydust-identity-production.up.railway.app',
        apps: 'https://fairydust-apps-production.up.railway.app',
        ledger: 'https://fairydust-ledger-production.up.railway.app'
    }
};

// App registration details
const YOGA_APP = {
    id: '7f3e4d2c-1a5b-4c3d-8e7f-9b8a7c6d5e4f',
    name: 'Yoga Playlist Generator',
    slug: 'yoga-playlist-generator',
    description: 'AI-powered yoga playlist generator that creates custom Spotify playlists matching your yoga flow. Choose between basic flows (5 DUST) or extended sessions (8 DUST) with perfectly synchronized music.',
    icon_url: 'https://yoga-playlist.app/icon.png',
    category: 'creative',
    website_url: 'https://yoga-playlist.app',
    demo_url: 'https://yoga-playlist.app/demo',
    callback_url: 'https://yoga-playlist.app/api/fairydust-webhook'
};

// Builder account details
const BUILDER = {
    email: 'builder@yoga-playlist.app',
    fairyname: 'yoga-playlist-builder'
};

async function registerApp(environment = 'sandbox') {
    const urls = FAIRYDUST_URLS[environment];
    console.log(`\n🧘‍♀️ Registering Yoga Playlist Generator in ${environment} environment...\n`);

    try {
        // Step 1: Create builder account (or login if exists)
        console.log('1. Creating builder account...');
        
        // First, request OTP
        const otpResponse = await fetch(`${urls.identity}/auth/otp/request`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                identifier: BUILDER.email,
                identifier_type: 'email'
            })
        });

        if (!otpResponse.ok) {
            const error = await otpResponse.json();
            console.error('Failed to request OTP:', error);
            return;
        }

        console.log(`   ✅ OTP sent to ${BUILDER.email}`);
        console.log('   ⏳ Check your email and enter the OTP below...\n');

        // In a real implementation, you'd get the OTP from user input
        // For demo purposes, we'll show the flow
        const otp = await getUserInput('Enter OTP from email: ');

        // Verify OTP and get auth token
        const authResponse = await fetch(`${urls.identity}/auth/otp/verify`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                identifier: BUILDER.email,
                code: otp
            })
        });

        if (!authResponse.ok) {
            const error = await authResponse.json();
            console.error('Failed to verify OTP:', error);
            return;
        }

        const authData = await authResponse.json();
        const accessToken = authData.token.access_token;
        console.log('   ✅ Authentication successful!');

        // Step 2: Update user to be a builder (if needed)
        if (!authData.user.is_builder) {
            console.log('\n2. Upgrading account to builder status...');
            
            // This would typically require admin approval
            console.log('   ⏳ Builder status requires admin approval');
            console.log('   📧 Admin has been notified of your request');
        }

        // Step 3: Register the app
        console.log('\n3. Registering app...');
        
        const appResponse = await fetch(`${urls.apps}/apps`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${accessToken}`
            },
            body: JSON.stringify({
                name: YOGA_APP.name,
                slug: YOGA_APP.slug,
                description: YOGA_APP.description,
                icon_url: YOGA_APP.icon_url,
                category: YOGA_APP.category,
                website_url: YOGA_APP.website_url,
                demo_url: YOGA_APP.demo_url,
                callback_url: YOGA_APP.callback_url
            })
        });

        if (!appResponse.ok) {
            const error = await appResponse.json();
            console.error('Failed to register app:', error);
            return;
        }

        const app = await appResponse.json();
        console.log('   ✅ App registered successfully!');
        console.log(`   📱 App ID: ${app.id}`);
        console.log(`   📊 Status: ${app.status}`);

        // Step 4: Show integration code
        console.log('\n4. Integration Code:\n');
        console.log('```javascript');
        console.log(`const fairydust = new Fairydust.Fairydust({
    appId: '${app.id}',
    apiUrl: '${environment === 'sandbox' ? 'https://sandbox.fairydust.fun' : undefined}'
});

fairydust.createButtonComponent('#generate-button', {
    dustCost: 5,  // or 8 for extended sessions
    label: 'Generate Yoga Playlist',
    onSuccess: async (transaction) => {
        // User paid! Generate the playlist
        const playlist = await generateYogaPlaylist();
        displayPlaylist(playlist);
    }
});`);
        console.log('```');

        console.log('\n✅ Registration complete!');
        console.log('\nNext steps:');
        console.log('1. Wait for app approval (usually within 24 hours)');
        console.log('2. Test in sandbox environment first');
        console.log('3. Deploy to production when ready');
        console.log(`\nAPI Documentation: ${urls.apps}/docs`);

    } catch (error) {
        console.error('Error during registration:', error);
    }
}

// Helper function to get user input (in real app, use readline or prompt library)
async function getUserInput(prompt) {
    // This is a placeholder - in real implementation use readline
    console.log(prompt);
    return '123456'; // Simulated OTP
}

// Check command line arguments
const args = process.argv.slice(2);
const environment = args[0] || 'sandbox';

if (!['sandbox', 'production'].includes(environment)) {
    console.error('Usage: node register-yoga-app-api.js [sandbox|production]');
    process.exit(1);
}

// Run registration
registerApp(environment);