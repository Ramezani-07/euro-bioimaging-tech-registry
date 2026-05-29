FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (layer cache optimisation)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY app/ ./app/
COPY shapes/ ./shapes/
COPY ontology/ ./ontology/
COPY tests/ ./tests/
COPY pytest.ini .


# Create data directories with open permissions (runs as root in demo context)
RUN mkdir -p /data/rdf && chmod -R 777 /data

EXPOSE 8000

# --reload is intentional for demo/panel context: instant code iteration without rebuild
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
