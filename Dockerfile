FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY funds_portfolio/ ./funds_portfolio/
COPY config/ ./config/
COPY templates/ ./templates/
COPY funds_database.json preferences_schema.json ./

# Create portfolios directory (will be mounted as volume in dev/prod)
RUN mkdir -p /app/portfolios /app/logs

# Set Python to run in unbuffered mode
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:5000/health', timeout=5)"

# Run with gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "30", "--access-logfile", "-", "--error-logfile", "-", "funds_portfolio.app:app"]
