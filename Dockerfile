FROM python:3.11-slim

WORKDIR /app

# Copy shared dependencies first
COPY shared ./shared

# Copy all service requirements and install them with more explicit commands
COPY services/identity/requirements.txt ./identity-requirements.txt
COPY services/ledger/requirements.txt ./ledger-requirements.txt  
COPY services/apps/requirements.txt ./apps-requirements.txt

# Install all requirements explicitly
RUN pip install --no-cache-dir -r identity-requirements.txt && \
    pip install --no-cache-dir -r ledger-requirements.txt && \
    pip install --no-cache-dir -r apps-requirements.txt

# Copy all service code
COPY services ./services

# Create startup script with proper escaping
RUN printf '#!/bin/bash\necho "Starting service: $SERVICE_NAME"\ncd /app/services/${SERVICE_NAME:-identity}\necho "Working directory: $(pwd)"\nPYTHONPATH=/app exec python main.py\n' > /start.sh && chmod +x /start.sh

# Expose port
EXPOSE 8000

CMD ["/start.sh"]