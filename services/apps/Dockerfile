FROM python:3.11-slim

WORKDIR /app

# Copy and install requirements
COPY services/apps/requirements.txt .

# Force cache bust for pip install
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Verify uuid7 package installation
RUN python -c "from uuid_extensions import uuid7; print('✅ uuid7 package installed successfully')" || echo "❌ uuid7 package failed to install"

# Copy shared code
COPY shared ./shared

# Copy this service's code
COPY services/apps .

# Use Railway's PORT environment variable
CMD python -c "import os; import uvicorn; port = int(os.getenv('PORT', 8003)); uvicorn.run('main:app', host='0.0.0.0', port=port)"