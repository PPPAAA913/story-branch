FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 STUDIO_DB_PATH=/app/data/projects.db
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home studio && mkdir /app/data && chown studio:studio /app/data
COPY --chown=studio:studio studio ./studio
COPY --chown=studio:studio third_party ./third_party
USER studio
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "studio.main:app", "--host", "0.0.0.0", "--port", "8000"]
