#!/usr/bin/env node
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from '@modelcontextprotocol/sdk/types.js';
import fetch from 'node-fetch';

const RAILWAY_URL = process.env.FAIRYDUST_MCP_URL || 'https://fairydust-mcp-production.up.railway.app';

// Create MCP server that proxies to Railway
const server = new Server(
  {
    name: 'fairydust-mcp-proxy',
    vendor: 'fairydust',
    version: '1.0.0',
    description: 'MCP proxy for Railway-hosted Fairydust server'
  },
  {
    capabilities: {
      tools: {}
    }
  }
);

// Proxy tool list request
server.setRequestHandler(ListToolsRequestSchema, async () => {
  const response = await fetch(`${RAILWAY_URL}/mcp/tools`);
  return await response.json();
});

// Proxy tool calls
server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const response = await fetch(`${RAILWAY_URL}/mcp/call`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request.params)
  });
  return await response.json();
});

// Start proxy
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error('Fairydust MCP proxy started');
}

main().catch((error) => {
  console.error('Proxy error:', error);
  process.exit(1);
});