FROM python:3.11-slim

WORKDIR /app

# Copy shared dependencies first
COPY shared ./shared

# Copy all service requirements and install them
COPY services/*/requirements.txt ./services/
RUN find services -name "requirements.txt" -exec pip install --no-cache-dir -r {} \;

# Copy all service code
COPY services ./services

# Create startup script with proper escaping
RUN printf '#!/bin/bash\necho "Starting service: $SERVICE_NAME"\ncd /app/services/${SERVICE_NAME:-identity}\necho "Working directory: $(pwd)"\nPYTHONPATH=/app exec python main.py\n' > /start.sh && chmod +x /start.sh

# Expose port
EXPOSE 8000

CMD ["/start.sh"]