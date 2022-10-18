# Copyright 2022-, Semiotic AI, Inc.
# SPDX-License-Identifier: Apache-2.0

import logging
from collections.abc import Mapping
from typing import Dict, Iterator, Optional

import configargparse
from gql import Client, gql
from gql.transport.exceptions import TransportQueryError
from gql.transport.requests import RequestsHTTPTransport
from graphql import (
    GraphQLSchema,
    IntrospectionQuery,
    build_client_schema,
    get_introspection_query,
)

from autoagora_processor.db_utils import get_indexed_subgraphs

argsparser = configargparse.get_argument_parser()
argsparser.add_argument(
    "--graph-node-query-endpoint",
    env_var="GRAPH_NODE_QUERY_ENDPOINT",
    required=True,
    help="URL of the indexer's graph-node GraphQL query endpoint.",
)

from autoagora_processor.config import args


class SubgraphSchemas(Mapping):
    def __init__(self) -> None:
        super().__init__()

        self.schemas: Dict[str, Optional[GraphQLSchema]] = {
            subgraph: self.get_schema_from_graph_node(subgraph)
            for subgraph in get_indexed_subgraphs()
        }
        logging.info("Added schemas for %s subgraphs", len(self.schemas))

    @staticmethod
    def get_schema_from_graph_node(subgraph_ipfs_hash: str) -> Optional[GraphQLSchema]:
        """Get schema string from graph node URL.
        Taken from https://gitlab.semiotic.ai/thegraph/query_generation

        Args:
            subgraph_ipfs_hash (str)

        Returns:
            str: GraphQL schema.
        """

        logging.info("Adding schema for subgraph %s ...", subgraph_ipfs_hash)
        introspection_query = get_introspection_query(descriptions=False)
        client = Client(
            transport=RequestsHTTPTransport(
                f"{args.graph_node_query_endpoint}/subgraphs/id/{subgraph_ipfs_hash}"
            ),
            fetch_schema_from_transport=False,
        )
        try:
            result = IntrospectionQuery(client.execute(gql(introspection_query)))
        except TransportQueryError as e:
            # Should happen when there is an indexing error
            logging.warn(
                "Query error while running introspection query against %s: %s",
                subgraph_ipfs_hash,
                e,
            )
            return None
        # Crash if other error

        return build_client_schema(result)

    def __getitem__(self, subgraph_ipfs_hash: str) -> Optional[GraphQLSchema]:
        if subgraph_ipfs_hash not in self.schemas.keys():
            assert subgraph_ipfs_hash in get_indexed_subgraphs()
            new_schema = self.get_schema_from_graph_node(subgraph_ipfs_hash)
            self.schemas[subgraph_ipfs_hash] = new_schema
            if new_schema:
                logging.info("Added schema for new subgraph %s", subgraph_ipfs_hash)
            else:
                logging.info(
                    "Added None schema for new subgraph %s", subgraph_ipfs_hash
                )
            return new_schema

        return self.schemas[subgraph_ipfs_hash]

    def __iter__(self) -> Iterator[str]:
        return self.schemas.__iter__()

    def __len__(self) -> int:
        return self.schemas.__len__()
