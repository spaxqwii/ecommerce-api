FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 5000

# Production mode by default
ENV FLASK_DEBUG=false

CMD ["python", "main.py"]
