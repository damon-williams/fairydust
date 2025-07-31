import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from '@modelcontextprotocol/sdk/types.js';
import { z } from 'zod';
import { AuthManager } from './auth.js';
import { FairydustClient } from './fairydust-client.js';
import {
  ImageGenerateRequestSchema,
  FortuneGenerateRequestSchema,
  ImageStyleSchema,
  ImageSizeSchema,
  ReadingTypeSchema
} from './types.js';

// Initialize managers
const authManager = new AuthManager();
const fairydustClient = new FairydustClient();

// Create MCP server
const server = new Server(
  {
    name: 'fairydust-mcp',
    vendor: 'fairydust',
    version: '1.0.0',
    description: 'MCP server for Fairydust AI apps: Image Generation & Fortune Teller'
  },
  {
    capabilities: {
      tools: {}
    }
  }
);

// Helper to check authentication
async function requireAuth(): Promise<{ token: string; email: string; userId: string }> {
  const session = authManager.getActiveSession();
  if (!session) {
    throw new Error('Not authenticated. Please use the authenticate tool first.');
  }

  const token = await authManager.getValidToken(session.email);
  if (!token) {
    throw new Error('Session expired. Please authenticate again.');
  }

  return {
    token,
    email: session.email,
    userId: session.userInfo?.user_id || ''
  };
}

// Tool handlers
server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      // Authentication tools
      {
        name: 'authenticate',
        description: 'Start authentication with Fairydust using email',
        inputSchema: {
          type: 'object',
          properties: {
            email: {
              type: 'string',
              description: 'Your email address for Fairydust account'
            }
          },
          required: ['email']
        }
      },
      {
        name: 'verify_code',
        description: 'Verify the 6-digit code sent to your email',
        inputSchema: {
          type: 'object',
          properties: {
            email: {
              type: 'string',
              description: 'Email address used for authentication'
            },
            code: {
              type: 'string',
              description: '6-digit verification code from email'
            }
          },
          required: ['email', 'code']
        }
      },
      {
        name: 'check_auth',
        description: 'Check current authentication status and DUST balance',
        inputSchema: {
          type: 'object',
          properties: {}
        }
      },
      {
        name: 'logout',
        description: 'Logout from current Fairydust session',
        inputSchema: {
          type: 'object',
          properties: {}
        }
      },
      
      // Image generation tools
      {
        name: 'generate_image',
        description: 'Generate an AI image with FLUX. Costs 3 DUST.',
        inputSchema: {
          type: 'object',
          properties: {
            prompt: {
              type: 'string',
              description: 'Detailed description of the image you want to generate'
            },
            style: {
              type: 'string',
              enum: ['realistic', 'artistic', 'cartoon', 'anime', 'watercolor', 'oil_painting', '3d_render', 'sketch'],
              description: 'Visual style for the image'
            },
            size: {
              type: 'string',
              enum: ['square', 'portrait', 'landscape'],
              description: 'Image aspect ratio'
            }
          },
          required: ['prompt']
        }
      },
      {
        name: 'list_images',
        description: 'List your generated images',
        inputSchema: {
          type: 'object',
          properties: {
            limit: {
              type: 'number',
              description: 'Number of images to return (default: 10)'
            },
            favorites_only: {
              type: 'boolean',
              description: 'Only show favorited images'
            },
            style: {
              type: 'string',
              description: 'Filter by specific style'
            }
          }
        }
      },
      
      // Fortune teller tools
      {
        name: 'generate_fortune',
        description: 'Get a mystical fortune reading. Costs 2 DUST.',
        inputSchema: {
          type: 'object',
          properties: {
            reading_type: {
              type: 'string',
              enum: ['daily', 'love', 'career', 'general', 'personal_growth'],
              description: 'Type of fortune reading'
            },
            question: {
              type: 'string',
              description: 'Optional specific question for the reading'
            }
          },
          required: ['reading_type']
        }
      },
      {
        name: 'fortune_history',
        description: 'View your past fortune readings',
        inputSchema: {
          type: 'object',
          properties: {
            limit: {
              type: 'number',
              description: 'Number of readings to return (default: 10)'
            },
            reading_type: {
              type: 'string',
              description: 'Filter by reading type'
            }
          }
        }
      }
    ]
  };
});

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    switch (name) {
      // Authentication tools
      case 'authenticate': {
        const { email } = z.object({ email: z.string().email() }).parse(args);
        const result = await authManager.requestOTP(email);
        return {
          content: [
            {
              type: 'text',
              text: result.message
            }
          ]
        };
      }

      case 'verify_code': {
        const { email, code } = z.object({
          email: z.string().email(),
          code: z.string()
        }).parse(args);
        
        const result = await authManager.verifyOTP(email, code);
        
        if (result.success && result.userInfo) {
          return {
            content: [
              {
                type: 'text',
                text: `✓ ${result.message}\n✓ Your session will remain active for 30 days.\n✓ DUST balance: ${result.userInfo.dust_balance || 'Unknown'}`
              }
            ]
          };
        }
        
        return {
          content: [
            {
              type: 'text',
              text: result.message
            }
          ]
        };
      }

      case 'check_auth': {
        const session = authManager.getActiveSession();
        if (!session) {
          return {
            content: [
              {
                type: 'text',
                text: '✗ Not authenticated. Please use the authenticate tool first.'
              }
            ]
          };
        }

        const expiresIn = Math.round((session.expiresAt - Date.now()) / (1000 * 60 * 60 * 24));
        return {
          content: [
            {
              type: 'text',
              text: `✓ Authenticated as ${session.email}\n✓ Session expires in ${expiresIn} days\n✓ DUST balance: ${session.userInfo?.dust_balance || 'Unknown'}`
            }
          ]
        };
      }

      case 'logout': {
        const session = authManager.getActiveSession();
        if (session) {
          await authManager.clearSession(session.email);
          return {
            content: [
              {
                type: 'text',
                text: '✓ Successfully logged out from Fairydust'
              }
            ]
          };
        }
        return {
          content: [
            {
              type: 'text',
              text: 'No active session to logout from'
            }
          ]
        };
      }

      // Image generation tools
      case 'generate_image': {
        const auth = await requireAuth();
        const imageRequest = ImageGenerateRequestSchema.parse({
          prompt: args.prompt,
          style: args.style || 'realistic',
          image_size: args.size || 'square'
        });

        const result = await fairydustClient.generateImage(
          auth.token,
          auth.userId,
          imageRequest
        );

        if (result.error) {
          return {
            content: [
              {
                type: 'text',
                text: `Failed to generate image: ${result.error}`
              }
            ]
          };
        }

        return {
          content: [
            {
              type: 'text',
              text: `🎨 Created with ${result.dust_info.cost} DUST\n📊 Your balance: ${result.dust_info.remaining_balance} DUST remaining\n\nImage URL: ${result.image.url}`
            }
          ]
        };
      }

      case 'list_images': {
        const auth = await requireAuth();
        const result = await fairydustClient.listImages(
          auth.token,
          auth.userId,
          {
            limit: args.limit,
            favorites_only: args.favorites_only,
            style: args.style
          }
        );

        if (result.error) {
          return {
            content: [
              {
                type: 'text',
                text: `Failed to list images: ${result.error}`
              }
            ]
          };
        }

        const imageList = result.images.map((img: any, idx: number) => 
          `${idx + 1}. ${img.style === 'realistic' ? '🌅' : img.style === 'anime' ? '🎌' : '🎨'} "${img.prompt.substring(0, 50)}${img.prompt.length > 50 ? '...' : ''}" - Created ${new Date(img.created_at).toLocaleDateString()}`
        ).join('\n');

        return {
          content: [
            {
              type: 'text',
              text: `Here are your recent Fairydust images:\n\n${imageList}\n\nTotal images: ${result.total}`
            }
          ]
        };
      }

      // Fortune teller tools
      case 'generate_fortune': {
        const auth = await requireAuth();
        const fortuneRequest = FortuneGenerateRequestSchema.parse({
          reading_type: args.reading_type,
          question: args.question
        });

        const result = await fairydustClient.generateFortune(
          auth.token,
          auth.userId,
          fortuneRequest
        );

        if (result.error) {
          return {
            content: [
              {
                type: 'text',
                text: `Failed to generate fortune: ${result.error}`
              }
            ]
          };
        }

        return {
          content: [
            {
              type: 'text',
              text: `🔮 **${fortuneRequest.reading_type.toUpperCase()} READING**\n\n${result.fortune.reading}\n\n✨ **Cosmic Influences:**\n${result.fortune.cosmic_influences}\n\n🌟 **Guidance:**\n${result.fortune.guidance}\n\n💫 **Affirmation:**\n*${result.fortune.affirmation}*\n\n🎨 Created with ${result.dust_info.cost} DUST\n📊 Your balance: ${result.dust_info.remaining_balance} DUST remaining`
            }
          ]
        };
      }

      case 'fortune_history': {
        const auth = await requireAuth();
        const result = await fairydustClient.getFortuneHistory(
          auth.token,
          auth.userId,
          {
            limit: args.limit,
            reading_type: args.reading_type
          }
        );

        if (result.error) {
          return {
            content: [
              {
                type: 'text',
                text: `Failed to get fortune history: ${result.error}`
              }
            ]
          };
        }

        const fortuneList = result.fortunes.map((fortune: any, idx: number) => {
          const typeEmoji = {
            daily: '☀️',
            love: '❤️',
            career: '💼',
            general: '🔮',
            personal_growth: '🌱'
          }[fortune.reading_type] || '🔮';
          
          return `${idx + 1}. ${typeEmoji} ${fortune.reading_type} - ${new Date(fortune.created_at).toLocaleDateString()}`;
        }).join('\n');

        return {
          content: [
            {
              type: 'text',
              text: `Your recent fortune readings:\n\n${fortuneList}\n\nTotal readings: ${result.total}`
            }
          ]
        };
      }

      default:
        throw new Error(`Unknown tool: ${name}`);
    }
  } catch (error) {
    return {
      content: [
        {
          type: 'text',
          text: `Error: ${error instanceof Error ? error.message : 'Unknown error occurred'}`
        }
      ]
    };
  }
});

// Start server
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error('Fairydust MCP server started');
}

main().catch((error) => {
  console.error('Server error:', error);
  process.exit(1);
});