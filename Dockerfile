FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

ENV PIP_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cpu
ENV HF_HOME=/app/.cache/huggingface

COPY requirements.txt requirements-app.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
