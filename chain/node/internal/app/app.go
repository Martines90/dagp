// Package app implements the G0 authenticated content registry. Governance is not enabled.
package app

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sync"

	abci "github.com/cometbft/cometbft/abci/types"
)

type Account struct {
	Key      []byte `json:"key"`
	Sequence uint64 `json:"sequence"`
}
type State struct {
	ChainID   string             `json:"chain_id"`
	Height    int64              `json:"height"`
	Accounts  map[string]Account `json:"accounts"`
	Documents map[string][]byte  `json:"documents"`
}

// Transaction uses a fixed struct encoding; arbitrary JSON objects never enter signed state.
type Transaction struct {
	ChainID    string `json:"chain_id"`
	Account    string `json:"account"`
	Sequence   uint64 `json:"sequence"`
	ValidUntil int64  `json:"valid_until_height"`
	Type       string `json:"type"`
	Body       []byte `json:"body"`
	Signature  []byte `json:"signature"`
}

func (t Transaction) SignBytes() []byte {
	t.Signature = nil
	b, _ := json.Marshal(t)
	return append([]byte("DAGP/G0/JSON-v1\x00"), b...)
}
func Root(s State) []byte { b, _ := json.Marshal(s); h := sha256.Sum256(b); return h[:] }
func clone(s State) State { b, _ := json.Marshal(s); var n State; _ = json.Unmarshal(b, &n); return n }
func decode(b []byte, v any) error {
	d := json.NewDecoder(bytes.NewReader(b))
	d.DisallowUnknownFields()
	if err := d.Decode(v); err != nil {
		return err
	}
	if d.Decode(new(any)) != io.EOF {
		return errors.New("trailing JSON")
	}
	return nil
}
func Execute(s *State, raw []byte, height int64) error {
	if len(raw) > 90000 {
		return errors.New("transaction too large")
	}
	var t Transaction
	if err := decode(raw, &t); err != nil {
		return err
	}
	a, ok := s.Accounts[t.Account]
	if !ok || t.ChainID != s.ChainID || t.Sequence != a.Sequence || t.ValidUntil < height || t.ValidUntil > height+1000 || a.Sequence == ^uint64(0) {
		return errors.New("invalid account, domain, sequence or expiry")
	}
	if !ed25519.Verify(ed25519.PublicKey(a.Key), t.SignBytes(), t.Signature) {
		return errors.New("invalid signature")
	}
	if t.Type != "publish_document" || len(t.Body) == 0 || len(t.Body) > 65536 {
		return errors.New("unsupported message or document size")
	}
	h := sha256.Sum256(t.Body)
	id := hex.EncodeToString(h[:])
	if _, exists := s.Documents[id]; exists {
		return errors.New("document already exists")
	}
	s.Documents[id] = append([]byte(nil), t.Body...)
	a.Sequence++
	s.Accounts[t.Account] = a
	return nil
}

type Application struct {
	abci.BaseApplication
	mu        sync.Mutex
	path      string
	committed State
	pending   *State
}

func Open(path string) (*Application, error) {
	a := &Application{path: path}
	b, err := os.ReadFile(path)
	if errors.Is(err, os.ErrNotExist) {
		return a, nil
	}
	if err != nil {
		return nil, err
	}
	if err = decode(b, &a.committed); err != nil {
		return nil, err
	}
	return a, nil
}
func (a *Application) Info(context.Context, *abci.RequestInfo) (*abci.ResponseInfo, error) {
	a.mu.Lock()
	defer a.mu.Unlock()
	var h []byte
	if a.committed.ChainID != "" {
		h = Root(a.committed)
	}
	return &abci.ResponseInfo{Data: "DAGP G0 content registry", LastBlockHeight: a.committed.Height, LastBlockAppHash: h}, nil
}
func (a *Application) InitChain(_ context.Context, r *abci.RequestInitChain) (*abci.ResponseInitChain, error) {
	a.mu.Lock()
	defer a.mu.Unlock()
	if a.committed.ChainID != "" {
		return nil, errors.New("already initialized")
	}
	var s State
	if err := decode(r.AppStateBytes, &s); err != nil {
		return nil, err
	}
	if s.ChainID != r.ChainId || s.Height != 0 || len(s.Accounts) == 0 || len(s.Documents) > 0 {
		return nil, errors.New("invalid genesis")
	}
	for id, k := range s.Accounts {
		if id == "" || len(k.Key) != ed25519.PublicKeySize || k.Sequence != 0 {
			return nil, errors.New("invalid genesis account")
		}
	}
	s.Documents = map[string][]byte{}
	a.committed = s
	if err := a.persist(s); err != nil {
		return nil, err
	}
	return &abci.ResponseInitChain{AppHash: Root(s)}, nil
}
func (a *Application) CheckTx(_ context.Context, r *abci.RequestCheckTx) (*abci.ResponseCheckTx, error) {
	a.mu.Lock()
	defer a.mu.Unlock()
	s := clone(a.committed)
	if err := Execute(&s, r.Tx, s.Height+1); err != nil {
		return &abci.ResponseCheckTx{Code: 1, Log: err.Error()}, nil
	}
	return &abci.ResponseCheckTx{}, nil
}
func (a *Application) PrepareProposal(_ context.Context, r *abci.RequestPrepareProposal) (*abci.ResponsePrepareProposal, error) {
	a.mu.Lock()
	defer a.mu.Unlock()
	s := clone(a.committed)
	var txs [][]byte
	var size int64
	for _, t := range r.Txs {
		if size+int64(len(t)) > r.MaxTxBytes {
			continue
		}
		if Execute(&s, t, r.Height) == nil {
			txs = append(txs, t)
			size += int64(len(t))
		}
	}
	return &abci.ResponsePrepareProposal{Txs: txs}, nil
}
func (a *Application) ProcessProposal(_ context.Context, r *abci.RequestProcessProposal) (*abci.ResponseProcessProposal, error) {
	a.mu.Lock()
	defer a.mu.Unlock()
	s := clone(a.committed)
	for _, t := range r.Txs {
		if Execute(&s, t, r.Height) != nil {
			return &abci.ResponseProcessProposal{Status: abci.ResponseProcessProposal_REJECT}, nil
		}
	}
	return &abci.ResponseProcessProposal{Status: abci.ResponseProcessProposal_ACCEPT}, nil
}
func (a *Application) FinalizeBlock(_ context.Context, r *abci.RequestFinalizeBlock) (*abci.ResponseFinalizeBlock, error) {
	a.mu.Lock()
	defer a.mu.Unlock()
	if r.Height != a.committed.Height+1 {
		return nil, errors.New("unexpected height")
	}
	s := clone(a.committed)
	results := make([]*abci.ExecTxResult, len(r.Txs))
	for i, t := range r.Txs {
		results[i] = &abci.ExecTxResult{}
		if err := Execute(&s, t, r.Height); err != nil {
			results[i].Code = 1
			results[i].Log = err.Error()
		}
	}
	s.Height = r.Height
	a.pending = &s
	return &abci.ResponseFinalizeBlock{TxResults: results, AppHash: Root(s)}, nil
}
func (a *Application) persist(s State) error {
	if err := os.MkdirAll(filepath.Dir(a.path), 0700); err != nil {
		return err
	}
	b, err := json.Marshal(s)
	if err != nil {
		return err
	}
	f, err := os.OpenFile(a.path+".tmp", os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0600)
	if err != nil {
		return err
	}
	if _, err = f.Write(b); err != nil {
		f.Close()
		return err
	}
	if err = f.Sync(); err != nil {
		f.Close()
		return err
	}
	if err = f.Close(); err != nil {
		return err
	}
	if err = os.Rename(a.path+".tmp", a.path); err != nil {
		return err
	}
	d, err := os.Open(filepath.Dir(a.path))
	if err != nil {
		return err
	}
	defer d.Close()
	return d.Sync()
}
func (a *Application) Commit(context.Context, *abci.RequestCommit) (*abci.ResponseCommit, error) {
	a.mu.Lock()
	defer a.mu.Unlock()
	if a.pending == nil {
		return nil, errors.New("no pending block")
	}
	if err := a.persist(*a.pending); err != nil {
		return nil, err
	}
	a.committed = *a.pending
	a.pending = nil
	return &abci.ResponseCommit{}, nil
}
func (a *Application) Query(_ context.Context, r *abci.RequestQuery) (*abci.ResponseQuery, error) {
	a.mu.Lock()
	defer a.mu.Unlock()
	if r.Prove || (r.Height != 0 && r.Height != a.committed.Height) {
		return &abci.ResponseQuery{Code: 1, Log: "historical queries and proofs not implemented"}, nil
	}
	var value []byte
	switch r.Path {
	case "/state":
		value, _ = json.Marshal(a.committed)
	case "/document":
		value = a.committed.Documents[string(r.Data)]
	default:
		return &abci.ResponseQuery{Code: 1, Log: fmt.Sprintf("unknown path %s", r.Path)}, nil
	}
	return &abci.ResponseQuery{Value: value, Height: a.committed.Height}, nil
}
