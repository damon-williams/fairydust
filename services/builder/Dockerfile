FROM python:3.11-slim

WORKDIR /app

# Copy requirements first for better caching
COPY services/builder/requirements.txt .

# Force cache bust for pip install
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Verify uuid7 package installation
RUN python -c "from uuid_extensions import uuid7; print('✅ uuid7 package installed successfully')" || echo "❌ uuid7 package failed to install"

# Copy shared code
COPY shared ./shared

# Copy service code
COPY services/builder .

EXPOSE 8005

CMD ["python", "main.py"]