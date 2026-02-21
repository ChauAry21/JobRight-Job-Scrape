FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m playwright install --with-deps chromium

COPY . .

CMD ["python", "jobright_scrape.py", "--max", "50", "--out", "/app/out/jobright_recs.json"]