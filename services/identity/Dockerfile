FROM python:3.11-slim

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared code - adjust path for Railway's root directory context
COPY ../shared ./shared

# Copy service code
COPY . .

EXPOSE 8001

CMD ["python", "main.py"]