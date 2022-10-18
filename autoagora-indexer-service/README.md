# AutoAgora indexer-service

A wrapper around the [`indexer-service`](https://github.com/graphprotocol/indexer) that
captures and filters its logs.

The point of this is to capture "query timing" logs from the `indexer-service` and send
them to the
[`AutoAgora Processor`](https://gitlab.com/semiotic-ai/the-graph/autoagora-processor)
through RabbitMQ.
All the other logs are sent back to `stdout`.

Works only with `indexer-service` v0.20.1+, which generates the
logs that are needed for AutoAgora (see [indexer-service PR #428](https://github.com/graphprotocol/indexer/pull/428)).

## Building

We suggest an image tag of the form
`autoagora-indexer-service:{autoagora-indexer-service version}-{indexer-service version}`.

The Dockerfile builds on top of `ghcr.io/graphprotocol/indexer-service:latest` by default. You can specify a particular
tag using Docker build's `--build-arg` option such as below:

```sh
docker build --build-arg "INDEXER_SERVICE_TAG=v0.20.3" -t autoagora-indexer-service:v0.1.2-0.20.3 .
```

## Usage

The `autoagora-indexer-service` container is a drop-in replacement for the regular
`indexer-service` container. Pass your `indexer-service` configuration through the usual
environment variables. Don't forget to also add the wrapper configuration through
flags or environment variables:

```txt
Usage:
  -log_level string
        Log level. Must be "trace", "debug", "info", "warn", "error", "fatal" or "panic".
        (env: LOG_LEVEL) (default "warn")
  -max_cache_lines string
        Maximum number of log lines to cache locally.
        (env: MAX_CACHE_LINES) (default "100")
  -rabbitmq.exchange_name string
        Name of the RabbitMQ exchange query-node logs are pushed to.
        (env: RABBITMQ_EXCHANGE_NAME) (default "gql_logs")
  -rabbitmq.host string
        Hostname of the RabbitMQ server used for queuing the GQL logs.
        (env: RABBITMQ_HOST)
  -rabbitmq.password string
        Password to use for the GQL logs RabbitMQ queue.
        (env: RABBITMQ_PASSWORD) (default "guest")
  -rabbitmq.username string
        Username to use for the GQL logs RabbitMQ queue.
        (env: RABBITMQ_USERNAME) (default "guest")
```
