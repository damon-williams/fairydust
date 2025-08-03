import fetch from 'node-fetch';
import { z } from 'zod';
import type { 
  ImageGenerateRequest, 
  FortuneGenerateRequest,
  DustInfo 
} from './types.js';

export class FairydustClient {
  private contentUrl: string;
  private appsUrl: string;

  constructor() {
    const environment = process.env.ENVIRONMENT || 'staging';
    const suffix = environment === 'production' ? 'production' : 'staging';
    this.contentUrl = `https://fairydust-content-${suffix}.up.railway.app`;
    this.appsUrl = `https://fairydust-apps-${suffix}.up.railway.app`;
  }

  async generateImage(
    token: string, 
    userId: string, 
    request: ImageGenerateRequest
  ): Promise<{ 
    image: { url: string; id: string; prompt: string }; 
    dust_info: DustInfo;
    error?: string;
  }> {
    try {
      // First, call the apps service to deduct DUST
      const appsResponse = await fetch(`${this.appsUrl}/apps/fairydust-ai-image/use`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          user_id: userId,
          feature: 'image_generation',
          metadata: {
            style: request.style || 'realistic',
            size: request.image_size || 'square'
          }
        })
      });

      if (!appsResponse.ok) {
        const error = await appsResponse.text();
        return { 
          image: { url: '', id: '', prompt: '' }, 
          dust_info: { cost: 0, remaining_balance: 0 },
          error: `Failed to use app: ${error}`
        };
      }

      const appUsage = await appsResponse.json();
      
      // Then generate the image
      const imageResponse = await fetch(`${this.contentUrl}/images/generate`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          user_id: userId,
          ...request
        })
      });

      if (!imageResponse.ok) {
        const error = await imageResponse.text();
        return { 
          image: { url: '', id: '', prompt: '' }, 
          dust_info: { cost: 3, remaining_balance: appUsage.dust_balance - 3 },
          error: `Failed to generate image: ${error}`
        };
      }

      const imageData = await imageResponse.json();
      
      return {
        image: {
          url: imageData.image.url,
          id: imageData.image.id,
          prompt: imageData.image.prompt
        },
        dust_info: {
          cost: 3,
          remaining_balance: appUsage.dust_balance - 3
        }
      };
    } catch (error) {
      return {
        image: { url: '', id: '', prompt: '' },
        dust_info: { cost: 0, remaining_balance: 0 },
        error: `Error: ${error instanceof Error ? error.message : 'Unknown error'}`
      };
    }
  }

  async listImages(
    token: string,
    userId: string,
    options?: {
      limit?: number;
      favorites_only?: boolean;
      style?: string;
    }
  ): Promise<{ images: any[]; total: number; error?: string }> {
    try {
      const params = new URLSearchParams({
        limit: String(options?.limit || 10),
        ...(options?.favorites_only && { favorites_only: 'true' }),
        ...(options?.style && { style: options.style })
      });

      const response = await fetch(
        `${this.contentUrl}/images/users/${userId}?${params}`,
        {
          headers: { 'Authorization': `Bearer ${token}` }
        }
      );

      if (!response.ok) {
        const error = await response.text();
        return { images: [], total: 0, error };
      }

      const data = await response.json();
      return {
        images: data.images,
        total: data.pagination.total
      };
    } catch (error) {
      return {
        images: [],
        total: 0,
        error: `Error: ${error instanceof Error ? error.message : 'Unknown error'}`
      };
    }
  }

  async generateFortune(
    token: string,
    userId: string,
    request: FortuneGenerateRequest
  ): Promise<{
    fortune: {
      reading: string;
      cosmic_influences: string;
      guidance: string;
      affirmation: string;
    };
    dust_info: DustInfo;
    error?: string;
  }> {
    try {
      // Fortune teller app request
      const response = await fetch(`${this.contentUrl}/apps/fortune-teller/generate`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          user_id: userId,
          reading_type: request.reading_type,
          question: request.question,
          target_person_id: request.target_person_id || userId
        })
      });

      if (!response.ok) {
        const error = await response.text();
        return {
          fortune: {
            reading: '',
            cosmic_influences: '',
            guidance: '',
            affirmation: ''
          },
          dust_info: { cost: 0, remaining_balance: 0 },
          error: `Failed to generate fortune: ${error}`
        };
      }

      const data = await response.json();
      
      // Handle error response
      if (data.error) {
        return {
          fortune: {
            reading: '',
            cosmic_influences: '',
            guidance: '',
            affirmation: ''
          },
          dust_info: { cost: 0, remaining_balance: 0 },
          error: data.error
        };
      }

      return {
        fortune: {
          reading: data.reading.fortune_text,
          cosmic_influences: data.reading.cosmic_influences,
          guidance: data.reading.guidance,
          affirmation: data.reading.affirmation
        },
        dust_info: {
          cost: data.dust_cost,
          remaining_balance: data.dust_balance
        }
      };
    } catch (error) {
      return {
        fortune: {
          reading: '',
          cosmic_influences: '',
          guidance: '',
          affirmation: ''
        },
        dust_info: { cost: 0, remaining_balance: 0 },
        error: `Error: ${error instanceof Error ? error.message : 'Unknown error'}`
      };
    }
  }

  async getFortuneHistory(
    token: string,
    userId: string,
    options?: {
      limit?: number;
      reading_type?: string;
    }
  ): Promise<{ fortunes: any[]; total: number; error?: string }> {
    try {
      const params = new URLSearchParams({
        limit: String(options?.limit || 10),
        ...(options?.reading_type && { reading_type: options.reading_type })
      });

      const response = await fetch(
        `${this.contentUrl}/apps/fortune-teller/history?${params}`,
        {
          headers: { 'Authorization': `Bearer ${token}` }
        }
      );

      if (!response.ok) {
        const error = await response.text();
        return { fortunes: [], total: 0, error };
      }

      const data = await response.json();
      return {
        fortunes: data.readings,
        total: data.total
      };
    } catch (error) {
      return {
        fortunes: [],
        total: 0,
        error: `Error: ${error instanceof Error ? error.message : 'Unknown error'}`
      };
    }
  }
}