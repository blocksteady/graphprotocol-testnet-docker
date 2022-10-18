# Copyright 2022-, Semiotic AI, Inc.
# SPDX-License-Identifier: Apache-2.0

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass
class QueryLogEntry:
    timestamp: datetime
    query_time_ms: Optional[int]
    query_variables: Optional[List[str]]
    query: str
    query_hash: bytes
    subgraph: str
    fees: Optional[int]
