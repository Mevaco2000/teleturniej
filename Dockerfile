# Serwer gry dla hostingów, które uruchamiają kontenery (gdyby Render przestał być darmowy).
FROM python:3.12-slim

WORKDIR /srv
ENV PYTHONUNBUFFERED=1 PORT=8000

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server server
COPY web web
COPY data data

EXPOSE 8000
CMD ["python", "-m", "server", "--cloud"]
