// Simple test server for yoga-playlist integration
const express = require('express');
const path = require('path');
const app = express();

// Serve static files
app.use(express.static(__dirname));

// Serve the integration example
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'yoga-playlist-integration.html'));
});

// Start server
const PORT = 3001;
app.listen(PORT, () => {
    console.log(`
🧘‍♀️ Yoga Playlist fairydust Integration Test
==========================================

Server running at: http://localhost:${PORT}

To test the integration:

1. Make sure fairydust services are running locally:
   - docker-compose up
   
2. Register the yoga app in your local database:
   - cd scripts
   - ./register_yoga_app.sh local

3. Open http://localhost:${PORT} in your browser

4. Click on the account widget to sign in

5. Try generating playlists with different durations:
   - ≤45 minutes: 5 DUST
   - >45 minutes: 8 DUST

The integration demonstrates:
- Dynamic pricing based on user selection
- Disabled state when form is incomplete
- Account widget for balance display
- Seamless payment flow
`);
});

// Error handling
app.use((err, req, res, next) => {
    console.error(err.stack);
    res.status(500).send('Something broke!');
});