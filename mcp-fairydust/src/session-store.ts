import { promises as fs } from 'fs';
import path from 'path';
import os from 'os';

interface StoredSession {
  email: string;
  accessToken: string;
  refreshToken: string;
  expiresAt: number;
  userInfo?: {
    user_id: string;
    email?: string;
    fairyname?: string;
    dust_balance?: number;
  };
}

export class SessionStore {
  private storePath: string;

  constructor() {
    // Store in user's home directory
    const configDir = path.join(os.homedir(), '.fairydust-mcp');
    this.storePath = path.join(configDir, 'session.json');
    this.ensureDirectory();
  }

  private async ensureDirectory(): Promise<void> {
    const dir = path.dirname(this.storePath);
    try {
      await fs.mkdir(dir, { recursive: true });
    } catch (error) {
      // Directory might already exist
    }
  }

  async save(session: StoredSession): Promise<void> {
    try {
      await fs.writeFile(
        this.storePath,
        JSON.stringify(session, null, 2),
        'utf-8'
      );
    } catch (error) {
      console.error('Failed to save session:', error);
    }
  }

  async load(): Promise<StoredSession | null> {
    try {
      const data = await fs.readFile(this.storePath, 'utf-8');
      const session = JSON.parse(data) as StoredSession;
      
      // Check if session is still valid
      if (session.expiresAt > Date.now()) {
        return session;
      }
      
      // Session expired, remove it
      await this.clear();
      return null;
    } catch (error) {
      // No session file or invalid JSON
      return null;
    }
  }

  async clear(): Promise<void> {
    try {
      await fs.unlink(this.storePath);
    } catch (error) {
      // File might not exist
    }
  }
}