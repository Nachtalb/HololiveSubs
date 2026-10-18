FROM python:3.13-slim
RUN pip install --no-cache-dir pillow==11.3.0 && useradd -u 1000 -m app && mkdir /data && chown app /data
WORKDIR /app
COPY talents.json holozone.py ./
COPY www ./www
USER app
ENV DATA_DIR=/data PORT=8080 PYTHONUNBUFFERED=1
EXPOSE 8080
VOLUME /data
CMD ["python", "holozone.py"]
