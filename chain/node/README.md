# DAGP G0 network

An executable, local seven-validator CometBFT v0.38.21 network with a Go ABCI++
application. This is the first network foundation, not the full DAGP governance chain.
All validators run on one machine and therefore provide **no operator independence**.
No public deployment, real treasury, or production identity admission is enabled.

## Run

Requires Go 1.25+, Python 3.10+, and a C compiler for race tests. No Docker required.

```sh
cd chain/node
make test
make init
make smoke
make start
```

`init` refuses to overwrite existing devnet keys. `smoke` starts all seven nodes,
waits for blocks, publishes a signed document, verifies identical app hashes in
committed headers and document availability across all validators, rejects replay,
and stops every process. Run it again to check restart recovery. `start` runs until
Ctrl-C. RPC listeners are `127.0.0.1:26657`, then every ten ports through `26717`;
P2P and ABCI also bind only to loopback. Logs and private keys are in the ignored
`.devnet/` directory. Preserve that directory to resume the same chain.

## Implemented contract

Genesis contains preapproved Ed25519 account keys. The only transaction type is
`publish_document`, accepting 1–65,536 bytes and storing it under its SHA-256 hash.
There is no transaction granting privileges or moving money. Account sequence
starts at zero and advances only on success. Expiry is an inclusive block height,
with a maximum lookahead of 1,000 blocks. Unknown fields and trailing JSON fail.

The G0 wire format uses the fixed Go Transaction struct in `internal/app/app.go`.
Body and signature are JSON base64 strings. Signing bytes are the prefix
`DAGP/G0/JSON-v1` plus a zero byte, followed by that struct serialized with signature
set to null. This **temporary G0 encoding differs from the spec's protobuf/CBOR**;
replace it with a versioned cross-language encoding before public integration.

Example signing (private key is read from a file, never an argument):

```sh
bin/dagp-key --key .devnet/agent-key.json --document README.md \
  --sequence 0 --until 100
```

Broadcast the resulting JSON bytes, base64 encoded, using CometBFT's
`broadcast_tx_commit` JSON-RPC method. Query `/state` for committed state and
`/document` with the document hash as data. Queries reject historical heights and
proof requests: no light-client proof service is implemented.

FinalizeBlock computes pending state and app hash. Commit atomically replaces and
fsyncs the snapshot before acknowledging persistence. Queries only expose committed
state. Info reports the last committed height/hash for CometBFT crash recovery.
The hash covers the entire state, including height. JSON snapshot storage and full
state hashing are suitable only for this small G0 network, not the target scale.

## Next implementation gates

See [implementation status](../IMPLEMENTATION_STATUS.md). Cosmos SDK keepers,
challenge-first registry admission, governance modules, sealed ballots, treasury,
external beacons/anchors, operator diversity, proofs, upgrades, and public deployment
are not implemented here. Existing Python governance reference tests remain the
behavioral baseline for the eventual SDK implementation.

## Anchor simulation results

From this directory, after generating the simulation artifacts:

```sh
python3 scripts/devnet.py anchor \
  --document ../simulation/results/pilot/manifest.json \
  --receipt ../simulation/results/pilot/anchor-receipt.json
```

This publishes a document commitment and saves seven matching validator RPC
observations. Governance remains in the Python reference; the node does not
validate the report contents. Existing content is not republished: keep the
receipt for an already anchored manifest. See `../simulation/README.md`.
