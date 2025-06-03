# Dockerfile (in repo root)
FROM python:3.11-slim

WORKDIR /app

# Install dependencies for the specific service
# Railway will set RAILWAY_SERVICE_NAME environment variable
ARG SERVICE_NAME
ENV SERVICE_NAME=${SERVICE_NAME}

# Copy shared dependencies first
COPY shared ./shared

# Copy all service requirements
COPY services/*/requirements.txt ./services/
RUN find services -name "requirements.txt" -exec pip install --no-cache-dir -r {} \;

# Copy all service code
COPY services ./services

# Default to identity service if no SERVICE_NAME is set
ENV SERVICE_NAME=${SERVICE_NAME:-identity}

# Expose port (Railway will override this)
EXPOSE 8000

# Dynamic startup based on service
CMD cd services/${SERVICE_NAME} && python main.py