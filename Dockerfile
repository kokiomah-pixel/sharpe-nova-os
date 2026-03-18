# Simple Docker image for the Nova API
# Build: docker build -t nova-api .
# Run:  docker run --rm -p 8000:8000 -e NOVA_API_KEY=mykey nova-api

FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8000
EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
