# AutoAgora Processor

Processes raw `indexer-service` logs from a RabbitMQ queue, saves the results to a PostgreSQL database.

The processing:

- Extracts details about query execution form the log lines: The subgraph deployment, timestamp, query, variables,
execution time and fees paid.
- Normalizes the queries, separates the "query skeleton" from all values and variables.
- Saves the query skeleton (if never seen before), as well as a logs all the information
  about the query execution (including the variable values used).

Refer to [AutoAgora](https://gitlab.com/semiotic-ai/the-graph/autoagora) for more
details.

## Indexer's guide

### Build

Just build the container!

```sh
docker build -t autoagora-processor .
```

### Usage

Because it is a stateless service, and only consumes from a RabbitMQ queue and adds rows to a PostgreSQL database, the
Autoagora Processor can safely be dynamically scaled horizontally. Note however that it has been observed processing
upwards of 50 queries per second on a single CPU core.

Note that it also needs to connect to the `graph-node`'s database to determine the currently indexed subgraphs, and then
pull their schemas using the `graph-node` query endpoint.

Configuration:

```txt
usage: autoagora-processor [-h] --graph-postgres-host GRAPH_POSTGRES_HOST --graph-postgres-database
                           GRAPH_POSTGRES_DATABASE --graph-postgres-username GRAPH_POSTGRES_USERNAME
                           --graph-postgres-password GRAPH_POSTGRES_PASSWORD --graph-node-query-endpoint
                           GRAPH_NODE_QUERY_ENDPOINT --rabbitmq-host RABBITMQ_HOST
                           [--rabbitmq-queue-name RABBITMQ_QUEUE_NAME] [--rabbitmq-queue-limit RABBITMQ_QUEUE_LIMIT]
                           [--rabbitmq-exchange-name RABBITMQ_EXCHANGE_NAME] [--rabbitmq-username RABBITMQ_USERNAME]
                           [--rabbitmq-password RABBITMQ_PASSWORD] --postgres-host POSTGRES_HOST --postgres-database
                           POSTGRES_DATABASE --postgres-username POSTGRES_USERNAME --postgres-password
                           POSTGRES_PASSWORD [--log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}]

options:
  -h, --help            show this help message and exit
  --graph-postgres-host GRAPH_POSTGRES_HOST
                        URL of the postgres instance use by the graph-nodes. [env var: GRAPH_POSTGRES_HOST] (default:
                        None)
  --graph-postgres-database GRAPH_POSTGRES_DATABASE
                        Name of the graph-node database. [env var: GRAPH_POSTGRES_DATABASE] (default: None)
  --graph-postgres-username GRAPH_POSTGRES_USERNAME
                        Username for the graph-node databse. [env var: GRAPH_POSTGRES_USERNAME] (default: None)
  --graph-postgres-password GRAPH_POSTGRES_PASSWORD
                        Password for the graph-node database. [env var: GRAPH_POSTGRES_PASSWORD] (default: None)
  --graph-node-query-endpoint GRAPH_NODE_QUERY_ENDPOINT
                        URL of the indexer's graph-node GraphQL query endpoint. [env var: GRAPH_NODE_QUERY_ENDPOINT]
                        (default: None)
  --rabbitmq-host RABBITMQ_HOST
                        Hostname of the RabbitMQ server used for queuing the GQL logs. [env var: RABBITMQ_HOST]
                        (default: None)
  --rabbitmq-queue-name RABBITMQ_QUEUE_NAME
                        Name of the RabbitMQ queue to pull query-node logs from. [env var: RABBITMQ_QUEUE_NAME]
                        (default: gql_logs_processor)
  --rabbitmq-queue-limit RABBITMQ_QUEUE_LIMIT
                        Size limit of the created RabbitMQ queue. It is discouraged to change that value while the
                        system is running, because it requires manual destruction of the queue and a restart of the
                        whole Auto Agora stack. [env var: RABBITMQ_QUEUE_LIMIT] (default: 1000)
  --rabbitmq-exchange-name RABBITMQ_EXCHANGE_NAME
                        Name of the RabbitMQ exchange query-node logs are pushed to. [env var: RABBITMQ_EXCHANGE_NAME]
                        (default: gql_logs)
  --rabbitmq-username RABBITMQ_USERNAME
                        Username to use for the GQL logs RabbitMQ queue. [env var: RABBITMQ_USERNAME] (default: guest)
  --rabbitmq-password RABBITMQ_PASSWORD
                        Password to use for the GQL logs RabbitMQ queue. [env var: RABBITMQ_PASSWORD] (default: guest)
  --postgres-host POSTGRES_HOST
                        URL of the postgres instance use by the graph-nodes. [env var: POSTGRES_HOST] (default: None)
  --postgres-database POSTGRES_DATABASE
                        Name of the graph-node database. [env var: POSTGRES_DATABASE] (default: None)
  --postgres-username POSTGRES_USERNAME
                        Username for the graph-node databse. [env var: POSTGRES_USERNAME] (default: None)
  --postgres-password POSTGRES_PASSWORD
                        Password for the graph-node database. [env var: POSTGRES_PASSWORD] (default: None)
  --log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}
                        [env var: LOG_LEVEL] (default: WARNING)
```
