# Copyright 2022-, Semiotic AI, Inc.
# SPDX-License-Identifier: Apache-2.0

import json
import logging
import signal
from datetime import datetime
from hashlib import blake2b
from typing import Any, List, Mapping, Tuple, Union

import configargparse
import pika
from graphql import GraphQLSchema, parse
from graphql.utilities import strip_ignored_characters as gql_strip_ignored_characters
from prometheus_client import Counter, start_http_server
from thegraph_gql_utils.misc import ast2str
from thegraph_gql_utils.tools import (
    build_variable_definitions,
    extract_root_queries,
    factorize,
    prune_query_arguments,
    remove_default_values,
    remove_query_name,
    remove_unknown_arguments,
    remove_values,
    sort,
    substitute_fragments,
)

from autoagora_processor.config import args, init_config
from autoagora_processor.logs_db import LogsDB
from autoagora_processor.query_log_entry import QueryLogEntry
from autoagora_processor.subgraph_schemas import SubgraphSchemas

subgraph_fees_counter = Counter("Fees", "Fees counter for subgraph", ["subgraph"])

argsparser = configargparse.get_argument_parser()
argsparser.add_argument(
    "--rabbitmq-host",
    env_var="RABBITMQ_HOST",
    required=True,
    help="Hostname of the RabbitMQ server used for queuing the GQL logs.",
)
argsparser.add_argument(
    "--rabbitmq-queue-name",
    env_var="RABBITMQ_QUEUE_NAME",
    default="gql_logs_processor",
    required=False,
    help="Name of the RabbitMQ queue to pull query-node logs from.",
)
argsparser.add_argument(
    "--rabbitmq-queue-limit",
    env_var="RABBITMQ_QUEUE_LIMIT",
    type=int,
    default=1000,
    required=False,
    help="Size limit of the created RabbitMQ queue. It is discouraged to change that "
    "value while the system is running, because it requires manual destruction of the "
    "queue and a restart of the whole Auto Agora stack.",
)
argsparser.add_argument(
    "--rabbitmq-exchange-name",
    env_var="RABBITMQ_EXCHANGE_NAME",
    default="gql_logs",
    required=False,
    help="Name of the RabbitMQ exchange query-node logs are pushed to.",
)
argsparser.add_argument(
    "--rabbitmq-username",
    env_var="RABBITMQ_USERNAME",
    type=str,
    default="guest",
    required=False,
    help="Username to use for the GQL logs RabbitMQ queue.",
)
argsparser.add_argument(
    "--rabbitmq-password",
    env_var="RABBITMQ_PASSWORD",
    type=str,
    default="guest",
    required=False,
    help="Password to use for the GQL logs RabbitMQ queue.",
)
argsparser.add_argument(
    "--postgres-host",
    env_var="POSTGRES_HOST",
    required=True,
    help="URL of the postgres instance use by the graph-nodes.",
)
argsparser.add_argument(
    "--postgres-database",
    env_var="POSTGRES_DATABASE",
    required=True,
    help="Name of the graph-node database.",
)
argsparser.add_argument(
    "--postgres-username",
    env_var="POSTGRES_USERNAME",
    required=True,
    help="Username for the graph-node databse.",
)
argsparser.add_argument(
    "--postgres-password",
    env_var="POSTGRES_PASSWORD",
    required=True,
    help="Password for the graph-node database.",
)
argsparser.add_argument(
    "--log-level",
    env_var="LOG_LEVEL",
    type=str,
    choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
    default="WARNING",
    required=False,
)

init_config()

logs_db = LogsDB(
    dbname=args.postgres_database,
    user=args.postgres_username,
    password=args.postgres_password,
    host=args.postgres_host,
)

subgraph_schemas = SubgraphSchemas()


# Handle SIGTERM for graceful termination
sigterm_received = False


def sigterm_flip(*args):
    global sigterm_received
    logging.info("SIGTERM received! Shutting down...")
    sigterm_received = True


signal.signal(signal.SIGTERM, sigterm_flip)


def normalize_query(
    query: str, variables: Union[str, Mapping[str, Any]], schema: GraphQLSchema
) -> List[Tuple[str, List[str]]]:
    logging.debug("Query before normalization: %s", query)

    if isinstance(variables, (str, bytes)):
        variables = json.loads(variables)

    outputs = []
    query_ast = parse(query)

    query_ast = substitute_fragments(query_ast)
    query_ast = factorize(query_ast)
    query_ast = prune_query_arguments(query_ast)
    query_ast = sort(query_ast)
    query_ast = remove_unknown_arguments(query_ast, schema)
    query_ast, default_values = remove_default_values(query_ast)

    for root_query in extract_root_queries(query_ast):
        # Merge variable values
        variables_merged = {**default_values, **variables}

        root_query, removed_variables = remove_values(
            root_query, existing_variables=variables_merged
        )
        root_query = build_variable_definitions(root_query, schema)
        root_query = remove_query_name(root_query)

        outputs += [
            (gql_strip_ignored_characters(ast2str(root_query)), removed_variables)
        ]

    return outputs


def parse_gql_logline(logline: str):
    res = json.loads(logline)

    assert res["msg"] == "Done executing paid query"

    timestamp = datetime.fromtimestamp(res["time"] / 1000)
    query_time_ms: int = res["responseTime"]
    subgraph: str = res["deployment"]
    query_blob = json.loads(res["query"])
    query: str = query_blob["query"]
    query_variables: Mapping[str, Any] = query_blob["variables"]
    fees = int(res["fees"])

    # Increment the prometheus fees counter for the subgraph
    subgraph_fees_counter.labels(subgraph).inc(fees)

    # Normalize query
    schema = subgraph_schemas[subgraph]

    normalized_queries = normalize_query(query, query_variables, schema)
    return [
        QueryLogEntry(
            timestamp=timestamp,
            query_time_ms=query_time_ms if len(normalized_queries) == 1 else None,
            query_variables=removed_variables if removed_variables else None,
            query=query,
            query_hash=blake2b(query.encode(), digest_size=16).digest(),
            subgraph=subgraph,
            fees=fees if len(normalized_queries) == 1 else None,
        )
        for query, removed_variables in normalized_queries
    ]


def callback(channel, _method, _properties, body):
    # Graceful termination
    global sigterm_received
    if sigterm_received:
        channel.stop_consuming()

    try:
        logline = body.decode()
    except:
        logging.exception("Failed to decode log data: %s", body)
        return

    try:
        logging.debug("GQL log line: %s", logline)
        for db_log_entry in parse_gql_logline(logline):
            logs_db.log_query(db_log_entry)
            logging.info("Parsed GQL log entry: %s", db_log_entry)
    except:
        logging.exception("Failed to parse GQL log line: %s", logline)
        return


def main():
    credentials = pika.PlainCredentials(args.rabbitmq_username, args.rabbitmq_password)
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(host=args.rabbitmq_host, credentials=credentials)
    )
    channel = connection.channel()

    # (re)-declare the rabbitmq exchange and queue
    channel.exchange_declare(
        exchange=args.rabbitmq_exchange_name,
        exchange_type="fanout",
    )
    channel.queue_declare(
        queue=args.rabbitmq_queue_name,
        arguments={
            "x-max-length": args.rabbitmq_queue_limit,
            "x-overflow": "drop-head",
        },
    )
    channel.queue_bind(
        queue=args.rabbitmq_queue_name, exchange=args.rabbitmq_exchange_name
    )

    channel.basic_consume(
        queue=args.rabbitmq_queue_name,
        on_message_callback=callback,
        auto_ack=True,
    )

    # Start prometheus HTTP server
    start_http_server(8000)

    logging.info("Start consuming from queue...")
    channel.start_consuming()
    logging.info("Terminating...")


if __name__ == "__main__":
    main()
