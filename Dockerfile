# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DB_URL=sqlite:////app/data/performometer.db

RUN pip install --no-cache-dir --upgrade pip

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# Store DB and runtime data in /app/data (mount a volume in production)
RUN mkdir -p /app/data

CMD ["python", "-m", "src.bot.bot"]
