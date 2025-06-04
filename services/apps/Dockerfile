FROM python:3.11-slim

WORKDIR /app

# Copy and install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy this service's code
COPY . .

# Use Railway's PORT environment variable
CMD python -c "import os; import uvicorn; port = int(os.getenv('PORT', 8003)); uvicorn.run('main:app', host='0.0.0.0', port=port)"