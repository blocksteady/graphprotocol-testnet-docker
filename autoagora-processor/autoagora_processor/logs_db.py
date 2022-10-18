# Copyright 2022-, Semiotic AI, Inc.
# SPDX-License-Identifier: Apache-2.0

import json

import psycopg2 as pg

from autoagora_processor.query_log_entry import QueryLogEntry


class LogsDB:
    def __init__(
        self,
        dbname: str,
        user: str,
        password: str,
        host: str,
    ) -> None:
        self.conn = pg.connect(dbname=dbname, user=user, password=password, host=host)
        self.conn.autocommit = True
        self.cur = self.conn.cursor()

        self.cur.execute(
            """
            CREATE TABLE IF NOT EXISTS query_skeletons (
                hash    bytea   PRIMARY KEY,
                query   text    NOT NULL
            )
            """
        )

        self.cur.execute(
            """
            CREATE TABLE IF NOT EXISTS query_logs (
                id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
                subgraph        char(46)    NOT NULL,
                query_hash      bytea       REFERENCES query_skeletons(hash),
                timestamp       timestamptz NOT NULL,
                query_time_ms   integer,
                query_variables text
            )
            """
        )

    def log_query(self, query: QueryLogEntry):
        self.cur.execute(
            """
            INSERT INTO query_skeletons (hash, query)
                VALUES (%s, %s)
                ON CONFLICT (hash) DO NOTHING
            """,
            (query.query_hash, query.query),
        )

        self.cur.execute(
            """
            INSERT INTO query_logs (
                    subgraph,
                    query_hash,
                    timestamp,
                    query_time_ms,
                    query_variables
                )
                VALUES (%s, %s, %s, %s, %s)
            """,
            (
                query.subgraph,
                query.query_hash,
                query.timestamp,
                query.query_time_ms,
                json.dumps(query.query_variables),
            ),
        )
