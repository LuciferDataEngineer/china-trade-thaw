FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src src
COPY contracts contracts
COPY data/snapshot data/snapshot
ENV PYTHONPATH=/app/src
ENV MPLBACKEND=Agg
CMD ["python", "-m", "china_trade.build"]
