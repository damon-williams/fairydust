FROM python:3.11-slim

WORKDIR /app

# Copy requirements first for better caching
COPY services/admin/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared code
COPY shared ./shared

# Copy service code
COPY services/admin .

# Copy migration scripts
COPY scripts ./scripts
COPY migrations ./migrations

EXPOSE 8003

# Run migrations on startup, then start the service
CMD ["sh", "-c", "python scripts/migrate_ai_usage_logs.py && python main.py"]