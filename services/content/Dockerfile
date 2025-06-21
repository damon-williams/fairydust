FROM python:3.11-slim

WORKDIR /app

# Copy requirements first for better caching
COPY services/content/requirements.txt services/content/requirements.txt
RUN pip install --no-cache-dir -r services/content/requirements.txt

# Copy shared modules
COPY shared/ shared/

# Copy content service files
COPY services/content/ services/content/

# Set environment variables
ENV PYTHONPATH=/app
ENV PORT=8006

# Expose port
EXPOSE 8006

# Run the application
CMD ["python", "services/content/main.py"]