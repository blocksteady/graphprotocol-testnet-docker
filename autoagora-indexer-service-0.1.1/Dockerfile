FROM golang:1.18-bullseye as build

WORKDIR /root/app
COPY . .
RUN go build -ldflags="-s -w" -o autoagora-indexer-service ./src

########################################################################################

FROM indexer-service:v0.19.3-querylogspatch

WORKDIR /opt/autoagora/bin

COPY --from=build /root/app/autoagora-indexer-service /opt/autoagora/bin/
ENV PATH=/opt/autoagora/bin:$PATH
ENV INDEXER_SERVICE_QUERY_TIMING_LOGS=true

# Run the indexer-service through the AutoAgora wrapper
ENTRYPOINT ["autoagora-indexer-service"]
