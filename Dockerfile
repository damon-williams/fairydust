FROM python:3.11-slim

WORKDIR /app

# Copy shared dependencies first
COPY shared ./shared

# Copy all service requirements and install them
COPY services/*/requirements.txt ./services/
RUN find services -name "requirements.txt" -exec pip install --no-cache-dir -r {} \;

# Copy all service code
COPY services ./services

# Debug: List what's actually in the container
RUN echo "=== DEBUGGING CONTAINER CONTENTS ===" && \
    ls -la /app/ && \
    echo "=== SERVICES DIRECTORY ===" && \
    ls -la /app/services/ && \
    echo "=== IDENTITY DIRECTORY ===" && \
    ls -la /app/services/identity/ || echo "identity dir not found"
    
# Create startup script - ESCAPE the variables for runtime
RUN echo '#!/bin/bash\ncd /app/services/$${SERVICE_NAME:-identity}\nPYTHONPATH=/app exec python main.py' > /start.sh && chmod +x /start.sh

# Expose port
EXPOSE 8000

CMD ["/start.sh"]