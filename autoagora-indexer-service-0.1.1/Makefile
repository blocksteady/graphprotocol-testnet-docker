INDEXER_SERVICE_VERSION=0.19.3
AUTOAGORA_INDEXER_SERVICE_VERSION:=$(shell git tag)

build: build-indexer-service
	docker build \
		-t autoagora-indexer-service:${AUTOAGORA_INDEXER_SERVICE_VERSION}-${INDEXER_SERVICE_VERSION} \
		.

prepare-submodules:
	git submodule init
	git submodule update

build-indexer-service: prepare-submodules
	docker build \
		-f indexer/Dockerfile.indexer-service \
		-t indexer-service:v${INDEXER_SERVICE_VERSION}-querylogspatch \
		indexer
