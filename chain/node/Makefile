.PHONY: build test init start smoke
build:
	mkdir -p bin
	go build -o bin/dagpd ./cmd/dagpd
	go build -o bin/dagp-key ./cmd/dagp-key
	go build -o bin/cometbft ./cmd/cometbft
test:
	go test -race ./...
init: build
	python3 scripts/devnet.py init
start:
	python3 scripts/devnet.py start
smoke:
	python3 scripts/devnet.py smoke
