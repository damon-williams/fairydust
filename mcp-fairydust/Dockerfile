FROM node:20-alpine

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci --only=production

# Copy source files
COPY dist ./dist

# Create health check endpoint
RUN echo '{"status":"ok"}' > /app/health.json

# Expose port
EXPOSE 8080

# Start MCP server
CMD ["node", "dist/index.js"]