FROM python:3.13-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app app
COPY static static
COPY seed seed
ENV NANOSKOP_DATA=/data \
    NANOSKOP_PREPARED=/srv/seed/prepared.pkl.gz \
    NUMBA_CACHE_DIR=/tmp/numba \
    PYTHONUNBUFFERED=1
RUN mkdir -p /data && chown 1000 /data
VOLUME /data
USER 1000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/login',timeout=4)"
# One worker on purpose: uploaded own files and the loaded dataset live in this process's memory.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
