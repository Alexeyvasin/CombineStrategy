FROM python:3.13.0-slim

WORKDIR  /app

RUN  pip  install --no-cache-dir poetry

COPY poetry.lock /app

COPY pyproject.toml /app

RUN  poetry  config virtualenvs.create  false

RUN poetry install

COPY . /app

CMD ["python", "combine_strategy.py"]