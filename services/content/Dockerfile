FROM python:3.11-slim

WORKDIR /app

# Force Python to run in unbuffered mode so logs appear immediately
ENV PYTHONUNBUFFERED=1

# Copy requirements first for better caching  
COPY services/content/requirements.txt ./requirements.txt

# Debug: Show requirements content
RUN echo "📋 Requirements file contents:" && cat requirements.txt

# Force fresh package installation
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Debug: List installed packages
RUN echo "📦 Installed packages:" && pip list | grep -E "(uuid7|googlemaps|langsmith)"

# Verify critical package installations
RUN python -c "import googlemaps; print('✅ googlemaps package installed successfully')" || echo "❌ googlemaps package failed to install"
RUN python -c "import langsmith; print('✅ langsmith package installed successfully')" || echo "❌ langsmith package failed to install"  
RUN python -c "from uuid_extensions import uuid7; print('✅ uuid7 package installed successfully')" || echo "❌ uuid7 package failed to install"

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