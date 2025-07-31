# Fairydust MCP Server

An MCP (Model Context Protocol) server that provides Claude with access to Fairydust AI apps: Image Generation and Fortune Teller.

## Features

- 🎨 **Image Generation** - Create AI images using FLUX with various styles
- 🔮 **Fortune Teller** - Get mystical fortune readings for daily guidance
- 🔐 **Secure Authentication** - Email/OTP authentication with persistent sessions
- 💎 **DUST Economy** - Integrated with Fairydust's DUST currency system

## Installation

### For Claude Desktop Users

1. Install the MCP server globally:
```bash
npm install -g @fairydust/mcp-server
```

2. Configure Claude Desktop by adding to your MCP settings:
```json
{
  "mcpServers": {
    "fairydust": {
      "command": "fairydust-mcp"
    }
  }
}
```

3. Restart Claude Desktop

### For Developers

1. Clone the repository:
```bash
git clone https://github.com/fairydust/mcp-fairydust.git
cd mcp-fairydust
```

2. Install dependencies:
```bash
npm install
```

3. Build the project:
```bash
npm run build
```

4. Configure Claude Desktop to use local build:
```json
{
  "mcpServers": {
    "fairydust": {
      "command": "node",
      "args": ["/path/to/mcp-fairydust/dist/index.js"],
      "env": {
        "ENVIRONMENT": "staging"
      }
    }
  }
}
```

## Usage

### First-Time Setup

1. Ask Claude: "Authenticate with Fairydust"
2. Provide your email address
3. Check your email for the 6-digit verification code
4. Give the code to Claude
5. You're authenticated! Session lasts 30 days.

### Available Commands

#### Authentication
- **"Authenticate with Fairydust"** - Start authentication
- **"Check my Fairydust status"** - View auth status and DUST balance
- **"Logout from Fairydust"** - End current session

#### Image Generation (3 DUST per image)
- **"Generate an image of [description]"** - Create an AI image
- **"Create a cartoon style image of [description]"** - Specify style
- **"Show my recent images"** - List generated images
- **"Show my favorite images"** - List favorited images

Available styles:
- realistic, artistic, cartoon, anime, watercolor, oil_painting, 3d_render, sketch

#### Fortune Teller (2 DUST per reading)
- **"Give me a daily fortune reading"** - Daily guidance
- **"I need a love fortune reading"** - Romance insights
- **"Generate a career fortune"** - Professional guidance
- **"Show my fortune history"** - View past readings

Reading types:
- daily, love, career, general, personal_growth

## Session Persistence

Sessions are stored locally in `~/.fairydust-mcp/session.json` and persist across Claude restarts. The session automatically refreshes tokens as needed.

## Environment Variables

For deployment or development:

```bash
ENVIRONMENT=staging|production  # Default: staging
FAIRYDUST_SERVICE_TOKEN=xxx    # For service registration (optional)
```

## Railway Deployment

To deploy the MCP server on Railway:

1. Push to GitHub
2. Create new Railway project
3. Connect GitHub repo
4. Add environment variables:
   - `ENVIRONMENT`: production or staging
   - `FAIRYDUST_SERVICE_TOKEN`: Your service token
5. Deploy!

## Development

```bash
# Run in development mode
npm run dev

# Type checking
npm run typecheck

# Build for production
npm run build
```

## Architecture

```
mcp-fairydust/
├── src/
│   ├── index.ts          # MCP server entry point
│   ├── auth.ts           # Authentication manager
│   ├── fairydust-client.ts # API client for Fairydust services
│   ├── session-store.ts  # Persistent session storage
│   └── types.ts          # TypeScript type definitions
├── dist/                 # Compiled JavaScript
├── package.json
├── tsconfig.json
└── README.md
```

## Error Handling

The MCP server handles common errors gracefully:
- **Not authenticated**: Prompts to use authenticate tool
- **Session expired**: Automatically refreshes tokens
- **Insufficient DUST**: Shows current balance and required amount
- **Rate limits**: Displays limit information

## Security

- JWT tokens are stored securely in user's home directory
- Tokens auto-refresh before expiration
- Service authentication uses separate tokens
- All API calls use HTTPS

## Contributing

1. Fork the repository
2. Create feature branch
3. Make changes and test
4. Submit pull request

## License

MIT License - see LICENSE file for details