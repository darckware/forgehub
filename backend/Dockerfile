FROM python:3.13-slim

ARG FORGEHUB_VERSION=unknown
ARG FORGEHUB_GIT_SHA=unknown
ARG FORGEHUB_BUILD_DATE=unknown

ENV FORGEHUB_VERSION=$FORGEHUB_VERSION \
    FORGEHUB_GIT_SHA=$FORGEHUB_GIT_SHA \
    FORGEHUB_BUILD_DATE=$FORGEHUB_BUILD_DATE

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
