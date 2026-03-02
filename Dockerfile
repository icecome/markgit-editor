ARG BASE_IMAGE=python:3.11-slim
FROM ${BASE_IMAGE}

WORKDIR /markgit-editor

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/* \
    && git config --global user.email "markgit-editor@example.com" \
    && git config --global user.name "MarkGit Editor" \
    && git config --global init.defaultBranch main

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY static/ ./static/
COPY main.py .
COPY index.html .

RUN mkdir -p /markgit-editor/blog_cache

ENV PRODUCTION=true
ENV PORT=13131
ENV PYTHONUNBUFFERED=1

EXPOSE ${PORT}

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
