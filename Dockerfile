FROM python:3.11-slim
WORKDIR /app

# Copy shared code
COPY shared ./shared

# Install all service dependencies
COPY services/apps/requirements.txt ./apps-requirements.txt
COPY services/identity/requirements.txt ./identity-requirements.txt  
COPY services/ledger/requirements.txt ./ledger-requirements.txt
RUN pip install --no-cache-dir -r apps-requirements.txt -r identity-requirements.txt -r ledger-requirements.txt

# Copy all service code
COPY services ./services

# Set Python path
ENV PYTHONPATH=/app

# Dynamic startup based on SERVICE_NAME environment variable
CMD python -c "import os; import uvicorn; service = os.getenv('SERVICE_NAME', 'identity'); port_map = {'apps': 8003, 'identity': 8001, 'ledger': 8002}; port = int(os.getenv('PORT', port_map[service])); uvicorn.run(f'services.{service}.main:app', host='0.0.0.0', port=port)"