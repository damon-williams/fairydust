FROM python:3.11-slim
WORKDIR /app

# Copy shared code
COPY shared ./shared

# Install all service dependencies
COPY services/apps/requirements.txt ./apps-requirements.txt
COPY services/identity/requirements.txt ./identity-requirements.txt  
COPY services/ledger/requirements.txt ./ledger-requirements.txt
COPY services/content/requirements.txt ./content-requirements.txt

# Force cache bust for pip install by upgrading pip first
RUN pip install --upgrade pip

# Install all dependencies with no cache
RUN pip install --no-cache-dir -r apps-requirements.txt -r identity-requirements.txt -r ledger-requirements.txt -r content-requirements.txt

# Debug: Check what Python sees
RUN echo "🐍 Python version:" && python --version
RUN echo "📦 Installed packages containing 'uuid':" && pip list | grep uuid || echo "No uuid packages found"
RUN echo "📂 Python path:" && python -c "import sys; print('\\n'.join(sys.path))"
RUN echo "🔍 Searching for uuid7 files:" && find /usr/local/lib/python*/site-packages -name "*uuid7*" 2>/dev/null || echo "No uuid7 files found"

# Try alternative: Install uuid7 directly and verify
RUN pip install --no-cache-dir uuid7==0.1.0 --force-reinstall
RUN echo "📦 After reinstall:" && pip list | grep uuid7

# Verify uuid7 package installation
RUN python -c "from uuid_extensions import uuid7; print('✅ uuid7 package installed successfully')" || echo "❌ uuid7 package failed to install"

# Copy all service code
COPY services ./services

# Set Python path
ENV PYTHONPATH=/app

# Change to service directory before running
CMD bash -c "service=\${SERVICE_NAME:-identity}; cd /app/services/\$service; python -c \"import os; import uvicorn; port = int(os.getenv('PORT', 8001)); uvicorn.run('main:app', host='0.0.0.0', port=port)\""