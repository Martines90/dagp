package app

import (
	"context"
	"crypto/ed25519"
	"encoding/json"
	abci "github.com/cometbft/cometbft/abci/types"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestAmbiguousJSONIsRefused(t *testing.T) {
	s, key := fixture(t)
	raw := signed(s, key, 0, "document")
	root := string(Root(s))
	variants := [][]byte{
		[]byte(strings.Replace(string(raw), `"sequence":0`, `"sequence":99,"sequence":0`, 1)),
		[]byte(strings.Replace(string(raw), `"sequence":0`, `"Sequence":0`, 1)),
		[]byte(strings.Replace(string(raw), `"body":`, `"unexpected":true,"body":`, 1)),
		append(append([]byte(nil), raw...), []byte(`{}`)...),
	}
	for _, b := range variants {
		if Execute(&s, b, 1) == nil {
			t.Fatal("ambiguous JSON accepted")
		}
		if string(Root(s)) != root {
			t.Fatal("rejection mutated state")
		}
	}
}
func TestAccountQuotasResetOnlyAtEpochBoundary(t *testing.T) {
	s, key := fixture(t)
	for i := 0; i < MaxAccountEpochDocuments; i++ {
		if err := Execute(&s, signed(s, key, uint64(i), string(rune('a'+i))), 1); err != nil {
			t.Fatal(err)
		}
	}
	root := string(Root(s))
	raw := signed(s, key, MaxAccountEpochDocuments, "new")
	if Execute(&s, raw, 2) == nil {
		t.Fatal("publication flood accepted")
	}
	if string(Root(s)) != root {
		t.Fatal("quota refusal mutated state")
	}
	var tx Transaction
	json.Unmarshal(raw, &tx)
	tx.ValidUntil = PublishEpochBlocks + 1
	tx.Signature = ed25519.Sign(key, tx.SignBytes())
	raw, _ = json.Marshal(tx)
	if err := Execute(&s, raw, PublishEpochBlocks+1); err != nil {
		t.Fatal(err)
	}
}
func TestStoreAndBlockCaps(t *testing.T) {
	s, key := fixture(t)
	for i := 0; i < MaxStoreDocuments; i++ {
		s.Documents[string(rune(i))] = []byte("x")
	}
	root := string(Root(s))
	if Execute(&s, signed(s, key, 0, "new"), 1) == nil {
		t.Fatal("store quota bypass")
	}
	if string(Root(s)) != root {
		t.Fatal("mutation")
	}
	a := &Application{committed: s}
	r, err := a.ProcessProposal(context.Background(), &abci.RequestProcessProposal{Height: 1, Txs: make([][]byte, MaxBlockTransactions+1)})
	if err != nil || r.Status != abci.ResponseProcessProposal_REJECT {
		t.Fatal("block count bypass")
	}
	if validBlock([][]byte{make([]byte, MaxTransactionBytes+1)}) {
		t.Fatal("transaction size bypass")
	}
}
func TestCorruptStateCannotPanicSignatureVerification(t *testing.T) {
	s, key := fixture(t)
	account := s.Accounts["agent"]
	account.Key = []byte("broken")
	s.Accounts["agent"] = account
	if Execute(&s, signed(s, key, 0, "new"), 1) == nil {
		t.Fatal("corrupt key accepted")
	}
	path := filepath.Join(t.TempDir(), "state.json")
	raw, _ := json.Marshal(s)
	os.WriteFile(path, raw, 0600)
	if _, err := Open(path); err == nil {
		t.Fatal("corrupt snapshot accepted")
	}
}
func TestDuplicatePublicKeysCannotBecomeMultipleAccounts(t *testing.T) {
	s, _ := fixture(t)
	s.Accounts["alias"] = s.Accounts["agent"]
	a, _ := Open(filepath.Join(t.TempDir(), "state.json"))
	raw, _ := json.Marshal(s)
	if _, err := a.InitChain(context.Background(), &abci.RequestInitChain{ChainId: s.ChainID, AppStateBytes: raw}); err == nil {
		t.Fatal("duplicate key accepted")
	}
}
func TestGenesisPersistenceFailureDoesNotInitializeMemory(t *testing.T) {
	s, _ := fixture(t)
	parent := filepath.Join(t.TempDir(), "file")
	os.WriteFile(parent, []byte("file"), 0600)
	a := &Application{path: filepath.Join(parent, "state.json")}
	raw, _ := json.Marshal(s)
	if _, err := a.InitChain(context.Background(), &abci.RequestInitChain{ChainId: s.ChainID, AppStateBytes: raw}); err == nil {
		t.Fatal("expected failure")
	}
	if a.committed.ChainID != "" {
		t.Fatal("failed initialization changed memory")
	}
}
func TestDocumentQueryDoesNotAliasStateAndSummaryExcludesBodies(t *testing.T) {
	s, key := fixture(t)
	Execute(&s, signed(s, key, 0, "secret public document"), 1)
	a := &Application{committed: s}
	var cid string
	for id := range s.Documents {
		cid = id
	}
	r, _ := a.Query(context.Background(), &abci.RequestQuery{Path: "/document", Data: []byte(cid)})
	r.Value[0] = 'X'
	if string(a.committed.Documents[cid]) != "secret public document" {
		t.Fatal("query mutated state")
	}
	r, _ = a.Query(context.Background(), &abci.RequestQuery{Path: "/state"})
	if strings.Contains(string(r.Value), `"documents"`) {
		t.Fatal("unbounded document bodies exposed in state query")
	}
}
func FuzzExecuteAtomic(f *testing.F) {
	s, key := fixture(f)
	f.Add(signed(s, key, 0, "seed"))
	f.Add([]byte(`{}`))
	f.Fuzz(func(t *testing.T, raw []byte) {
		state := clone(s)
		before := string(Root(state))
		err := Execute(&state, raw, 1)
		if err != nil && before != string(Root(state)) {
			t.Fatal("refused input mutated state")
		}
	})
}
