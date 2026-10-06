package app

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"encoding/json"
	abci "github.com/cometbft/cometbft/abci/types"
	"path/filepath"
	"testing"
)

func fixture(t *testing.T) (State, ed25519.PrivateKey) {
	t.Helper()
	pub, key, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	return State{ChainID: "test", Accounts: map[string]Account{"agent": {Key: pub}}, Documents: map[string][]byte{}}, key
}
func signed(s State, key ed25519.PrivateKey, seq uint64, body string) []byte {
	tx := Transaction{ChainID: s.ChainID, Account: "agent", Sequence: seq, ValidUntil: 20, Type: "publish_document", Body: []byte(body)}
	tx.Signature = ed25519.Sign(key, tx.SignBytes())
	b, _ := json.Marshal(tx)
	return b
}
func TestAuthenticationAndAtomicRefusal(t *testing.T) {
	s, key := fixture(t)
	tx := signed(s, key, 0, "hello")
	if err := Execute(&s, tx, 1); err != nil {
		t.Fatal(err)
	}
	root := string(Root(s))
	for _, bad := range [][]byte{tx, []byte(`{}`), signed(s, key, 1, "hello"), signed(s, key, 4, "other")} {
		if Execute(&s, bad, 1) == nil {
			t.Fatal("accepted invalid tx")
		}
		if string(Root(s)) != root {
			t.Fatal("refusal mutated state")
		}
	}
	other := clone(s)
	other.ChainID = "other"
	if Execute(&other, signed(s, key, 1, "cross-chain"), 1) == nil {
		t.Fatal("cross-chain replay")
	}
	tamper := signed(s, key, 1, "tamper")
	var parsed Transaction
	json.Unmarshal(tamper, &parsed)
	parsed.Body = []byte("modified")
	tamper, _ = json.Marshal(parsed)
	if Execute(&s, tamper, 1) == nil {
		t.Fatal("signature accepted tampering")
	}
	if Execute(&s, signed(s, key, 1, "expired"), 21) == nil {
		t.Fatal("accepted expiry")
	}
}
func TestCommitRestartAndReplay(t *testing.T) {
	s, key := fixture(t)
	path := filepath.Join(t.TempDir(), "state.json")
	a, err := Open(path)
	if err != nil {
		t.Fatal(err)
	}
	gen, _ := json.Marshal(s)
	ctx := context.Background()
	if _, err = a.InitChain(ctx, &abci.RequestInitChain{ChainId: s.ChainID, AppStateBytes: gen}); err != nil {
		t.Fatal(err)
	}
	tx := signed(s, key, 0, "hello")
	r, err := a.FinalizeBlock(ctx, &abci.RequestFinalizeBlock{Height: 1, Txs: [][]byte{tx, tx}})
	if err != nil {
		t.Fatal(err)
	}
	if r.TxResults[0].Code != 0 || r.TxResults[1].Code == 0 {
		t.Fatal("execution results")
	}
	q, _ := a.Query(ctx, &abci.RequestQuery{Path: "/state"})
	var queried State
	json.Unmarshal(q.Value, &queried)
	if queried.Height != 0 {
		t.Fatal("uncommitted state leaked")
	}
	if _, err = a.Commit(ctx, &abci.RequestCommit{}); err != nil {
		t.Fatal(err)
	}
	b, err := Open(path)
	if err != nil {
		t.Fatal(err)
	}
	info, _ := b.Info(ctx, &abci.RequestInfo{})
	if info.LastBlockHeight != 1 || string(info.LastBlockAppHash) != string(r.AppHash) {
		t.Fatal("restart mismatch")
	}
	if err = Execute(&s, tx, 1); err != nil {
		t.Fatal(err)
	}
	s.Height = 1
	if string(Root(s)) != string(r.AppHash) {
		t.Fatal("replay mismatch")
	}
}
func TestProposalValidation(t *testing.T) {
	s, key := fixture(t)
	a := &Application{committed: s}
	tx := signed(s, key, 0, "hello")
	ctx := context.Background()
	p, _ := a.PrepareProposal(ctx, &abci.RequestPrepareProposal{Height: 1, MaxTxBytes: 100000, Txs: [][]byte{tx, tx}})
	if len(p.Txs) != 1 {
		t.Fatal("duplicate not filtered")
	}
	r, _ := a.ProcessProposal(ctx, &abci.RequestProcessProposal{Height: 1, Txs: [][]byte{tx, tx}})
	if r.Status != abci.ResponseProcessProposal_REJECT {
		t.Fatal("invalid proposal accepted")
	}
}
