FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake git \
 && rm -rf /var/lib/apt/lists/*

COPY server.py /app/server.py

RUN pip install --no-cache-dir fastapi uvicorn pydantic 'llama-cpp-python[server]' sse-starlette starlette
RUN python -c "import sse_starlette; import llama_cpp.server; print('deps-ok')"

EXPOSE 8080
CMD ["python", "/app/server.py"]
