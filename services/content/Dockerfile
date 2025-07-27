FROM python:3.11-slim

WORKDIR /app

# Force Python to run in unbuffered mode so logs appear immediately
ENV PYTHONUNBUFFERED=1

# Copy requirements first for better caching  
COPY services/content/requirements.txt services/content/requirements.txt

# Force fresh package installation
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r services/content/requirements.txt

# Verify critical package installations
RUN python -c "import googlemaps; print('✅ googlemaps package installed successfully')" || echo "❌ googlemaps package failed to install"
RUN python -c "import langsmith; print('✅ langsmith package installed successfully')" || echo "❌ langsmith package failed to install"
RUN python -c "import langchain; print('✅ langchain package installed successfully')" || echo "❌ langchain package failed to install"
RUN python -c "import langchain_openai; print('✅ langchain-openai package installed successfully')" || echo "❌ langchain-openai package failed to install"

# Copy shared modules
COPY shared/ shared/

# Copy content service files
COPY services/content/ services/content/

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PORT=8006

# Expose port
EXPOSE 8006

# Run the application
CMD ["python", "services/content/main.py"]