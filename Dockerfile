FROM python:3.11-slim
WORKDIR /app
COPY services/ledger/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY shared ./shared
COPY services/ledger .
ENV PYTHONPATH=/app
CMD python -c "import os; import uvicorn; port = int(os.getenv('PORT', 8002)); uvicorn.run('main:app', host='0.0.0.0', port=port)"