FROM python:3.11-slim

WORKDIR /app

# Copy requirements first for better caching
COPY services/admin/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared code
COPY shared ./shared

# Copy service code
COPY services/admin .

EXPOSE 8003

CMD ["python", "main.py"]