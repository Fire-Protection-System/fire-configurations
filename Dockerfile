FROM python:3.11-slim
WORKDIR /code

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY ./requirements.txt .
RUN pip install --no-cache-dir --upgrade -r requirements.txt

COPY ./app /code/app
COPY ./cracow /code/cracow
COPY ./forest /code/forest

RUN mkdir -p /var/log/fire-configuration && \
    adduser --disabled-password --gecos "" appuser && \
    chown -R appuser:appuser /code /var/log/fire-configuration

USER appuser

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "31415"]