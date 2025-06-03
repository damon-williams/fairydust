FROM python:3.11-slim

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared code from parent directory
COPY ../shared ./shared

# Copy service code
COPY . .

EXPOSE 8002

CMD ["python", "main.py"]