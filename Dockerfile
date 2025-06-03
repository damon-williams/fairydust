FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY services/identity/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared code
COPY shared ./shared

# Copy identity service code
COPY services/identity ./

# Expose port (Railway will set PORT environment variable)
EXPOSE $PORT

# Run the application
CMD uvicorn main:app --host 0.0.0.0 --port $PORT