FROM python:3.11-slim
WORKDIR /app

# Copy shared code
COPY shared ./shared

# Install all service dependencies
COPY services/apps/requirements.txt ./apps-requirements.txt
COPY services/identity/requirements.txt ./identity-requirements.txt  
COPY services/ledger/requirements.txt ./ledger-requirements.txt
COPY services/content/requirements.txt ./content-requirements.txt
RUN pip install --no-cache-dir -r apps-requirements.txt -r identity-requirements.txt -r ledger-requirements.txt -r content-requirements.txt

# Copy all service code
COPY services ./services

# Set Python path
ENV PYTHONPATH=/app

# Change to service directory before running
CMD bash -c "service=\${SERVICE_NAME:-identity}; cd /app/services/\$service; python -c \"import os; import uvicorn; port = int(os.getenv('PORT', 8001)); uvicorn.run('main:app', host='0.0.0.0', port=port)\""