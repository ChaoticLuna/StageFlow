FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY stageflow/ stageflow/

RUN pip install --no-cache-dir -e .

ENTRYPOINT ["python", "-m", "stageflow"]
CMD ["status"]
