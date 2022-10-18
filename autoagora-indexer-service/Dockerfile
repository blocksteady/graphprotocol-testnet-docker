ARG INDEXER_SERVICE_TAG=latest

FROM golang:1.18-bullseye as build

WORKDIR /root/app
COPY . .
RUN go build -ldflags="-s -w" -o autoagora-indexer-service ./src

########################################################################################

FROM ghcr.io/graphprotocol/indexer-service:${INDEXER_SERVICE_TAG}

# Upgrade everything:
RUN apt-get -y update && apt-get -y upgrade

# Create a privilege drop user:
RUN groupadd -r indexer && useradd -r -m -s /bin/bash -d /var/lib/indexer -c 'Indexer Service' -g indexer indexer
RUN chown -R indexer:indexer /var/lib/indexer

WORKDIR /opt/autoagora/bin

COPY --from=build /root/app/autoagora-indexer-service /opt/autoagora/bin/

USER indexer:indexer
ENV PATH=/opt/autoagora/bin:$PATH
ENV INDEXER_SERVICE_QUERY_TIMING_LOGS=true

# Run the indexer-service through the AutoAgora wrapper
ENTRYPOINT ["autoagora-indexer-service"]
