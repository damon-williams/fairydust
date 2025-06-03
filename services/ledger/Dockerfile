FROM python:3.11-slim

WORKDIR /app

# Copy requirements first for better caching
COPY services/ledger/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared code
COPY shared ./shared

# Copy service code
COPY services/ledger .

EXPOSE 8002

CMD ["python", "main.py"]