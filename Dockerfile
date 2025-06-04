FROM python:3.11-slim
WORKDIR /app
COPY services/identity/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY shared ./shared
COPY services/identity .
ENV PYTHONPATH=/app
CMD python -c "import os; import uvicorn; port = int(os.getenv('PORT', 8001)); uvicorn.run('main:app', host='0.0.0.0', port=port)"