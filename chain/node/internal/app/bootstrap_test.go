package app

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	abci "github.com/cometbft/cometbft/abci/types"
	cmtcrypto "github.com/cometbft/cometbft/proto/tendermint/crypto"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func seedFixture(t *testing.T) (State, ed25519.PrivateKey, []byte) {
	s, keys := g2Fixture(t)
	s.Accounts = map[string]Account{"a000": s.Accounts["a000"]}
	pub, _, _ := ed25519.GenerateKey(rand.Reader)
	now := s.Runtime.Time
	b := BeaconConfig{Scheme: "bootstrap-disabled", GenesisTime: now, Period: 1}
	s.Runtime.Beacon = b
	charter := map[string]any{"identities": map[string]any{"a000": map[string]any{"operator": "founder-op", "family": "founder-family", "citizen_since": now, "roles": []string{"CITIZEN", "ADMIN", "REGISTRAR"}}},
		"common_budget": 100000, "balances": map[string]int64{"a000": 200}, "beacon": b, "root": "root", "constraints": []any{},
		"bootstrap": map[string]any{"founder": "a000", "validator_key": hex.EncodeToString(pub), "budget": 6000, "expires": now + 365*DaySeconds}}
	s.Runtime.Charter, _ = json.Marshal(charter)
	return s, keys["a000"], pub
}
func receiptResult(t *testing.T, s State, actor string) map[string]json.RawMessage {
	t.Helper()
	var receipt struct {
		Result map[string]json.RawMessage `json:"result"`
	}
	if err := json.Unmarshal(s.Runtime.Exports["receipt/"+actor], &receipt); err != nil {
		t.Fatal(err)
	}
	return receipt.Result
}
func receiptString(t *testing.T, s State, actor, field string) string {
	t.Helper()
	var value string
	_ = json.Unmarshal(receiptResult(t, s, actor)[field], &value)
	if value == "" {
		t.Fatal("missing receipt", field)
	}
	return value
}

func TestSeedRealSignaturesAdmissionAndNoBackdatedTenure(t *testing.T) {
	s, founder, validator := seedFixture(t)
	a, _ := Open(filepath.Join(t.TempDir(), "state.json"))
	gen, _ := json.Marshal(s)
	validators := []abci.ValidatorUpdate{{PubKey: cmtcrypto.PublicKey{Sum: &cmtcrypto.PublicKey_Ed25519{Ed25519: validator}}, Power: 1}}
	if _, err := a.InitChain(context.Background(), &abci.RequestInitChain{ChainId: s.ChainID, Time: time.Unix(s.Runtime.Time, 0), AppStateBytes: gen, Validators: validators}); err != nil {
		t.Fatal(err)
	}
	s = clone(a.committed)
	send := func(actor string, key ed25519.PrivateKey, op string, args any) {
		t.Helper()
		raw := g2Signed(s, key, actor, op, args)
		if err := Execute(&s, raw, 1); err != nil {
			t.Fatal(op, err)
		}
	}
	pub, candidate, _ := ed25519.GenerateKey(rand.Reader)
	join := JoinRequest{ChainID: s.ChainID, Account: "alice", Operator: "alice-op", Family: "alice-family", Key: pub}
	join.Signature = ed25519.Sign(candidate, join.SignBytes())
	send("a000", founder, "bootstrap.propose", map[string]any{"action": "INVITE", "payload": map[string]any{"join": join}})
	cid := receiptString(t, s, "a000", "case")
	send("a000", founder, "bootstrap.vote", map[string]any{"case": cid})
	send("a000", founder, "bootstrap.apply", map[string]any{"case": cid})
	roguePub, rogueKey, _ := ed25519.GenerateKey(rand.Reader)
	if err := Execute(&s, g2Signed(s, rogueKey, "alice", "identity.challenge", map[string]any{"key": hex.EncodeToString(roguePub)}), 1); err == nil {
		t.Fatal("attacker bound the invited name to a different key")
	}
	if _, exists := s.Accounts["alice"]; exists {
		t.Fatal("failed challenge consumed the invited account")
	}
	send("alice", candidate, "identity.challenge", map[string]any{"key": hex.EncodeToString(pub)})
	challenge := receiptString(t, s, "alice", "challenge")
	if err := advanceClock(&s, s.Runtime.Time+1); err != nil {
		t.Fatal(err)
	}
	send("alice", candidate, "identity.register", map[string]any{"operator": "alice-op", "family": "alice-family", "key": hex.EncodeToString(pub), "challenge": challenge})
	cid = receiptString(t, s, "alice", "case")
	send("a000", founder, "bootstrap.vote", map[string]any{"case": cid})
	send("a000", founder, "bootstrap.apply", map[string]any{"case": cid})
	var citizen struct {
		Status    string   `json:"status"`
		Since     int64    `json:"citizen_since"`
		Effective []string `json:"effective_roles"`
	}
	_ = json.Unmarshal(s.Runtime.Exports["citizen/alice"], &citizen)
	if citizen.Status != "ACTIVE" || citizen.Since != s.Runtime.Time || len(citizen.Effective) != 0 {
		t.Fatal("warmup/backdating", citizen)
	}
	if err := Execute(&s, g2Signed(s, founder, "a000", "admin.open", map[string]any{"target": "alice", "evidence": "bad"}), 1); err == nil {
		t.Fatal("seed bypassed normal governance gate")
	}
	if err := advanceClock(&s, s.Runtime.Time+3*DaySeconds); err != nil {
		t.Fatal(err)
	}
	_ = json.Unmarshal(s.Runtime.Exports["citizen/alice"], &citizen)
	if len(citizen.Effective) != 1 || citizen.Effective[0] != "CITIZEN" {
		t.Fatal("mature citizenship", citizen)
	}
	if len(s.Runtime.Validators) != 1 {
		t.Fatal("admission changed validator power")
	}
	// Mature citizen enrollment must reach the real ABCI validator update path.
	nodePub, nodeKey, _ := ed25519.GenerateKey(rand.Reader)
	proof := ed25519.Sign(nodeKey, G2PossessionBytes(s.ChainID, "alice", nodePub))
	payload := map[string]any{"target": "alice", "key": hex.EncodeToString(nodePub), "proof": hex.EncodeToString(make([]byte, 64))}
	if err := Execute(&s, g2Signed(s, candidate, "alice", "bootstrap.propose", map[string]any{"action": "VALIDATOR_ADD", "payload": payload}), 1); err == nil {
		t.Fatal("forged validator possession")
	}
	payload["proof"] = hex.EncodeToString(proof)
	payload["key"] = strings.ToUpper(hex.EncodeToString(nodePub))
	if err := Execute(&s, g2Signed(s, candidate, "alice", "bootstrap.propose", map[string]any{"action": "VALIDATOR_ADD", "payload": payload}), 1); err == nil {
		t.Fatal("noncanonical consensus key alias")
	}
	payload["key"] = hex.EncodeToString(nodePub)
	send("alice", candidate, "bootstrap.propose", map[string]any{"action": "VALIDATOR_ADD", "payload": payload})
	cid = receiptString(t, s, "alice", "case")
	send("a000", founder, "bootstrap.vote", map[string]any{"case": cid})
	if err := Execute(&s, g2Signed(s, founder, "a000", "bootstrap.apply", map[string]any{"case": cid}), 1); err == nil {
		t.Fatal("one of two citizens authorized enrollment")
	}
	send("alice", candidate, "bootstrap.vote", map[string]any{"case": cid})
	a.committed = clone(s)
	response, err := a.FinalizeBlock(context.Background(), &abci.RequestFinalizeBlock{Height: s.Height + 1, Time: time.Unix(s.Runtime.Time+1, 0), Txs: [][]byte{g2Signed(s, founder, "a000", "bootstrap.apply", map[string]any{"case": cid})}})
	if err != nil || response.TxResults[0].Code != 0 || len(response.ValidatorUpdates) != 1 || response.ValidatorUpdates[0].Power != 1 {
		t.Fatal("consensus enrollment", response, err)
	}
	if hex.EncodeToString(response.ValidatorUpdates[0].PubKey.GetEd25519()) != hex.EncodeToString(nodePub) {
		t.Fatal("wrong consensus key")
	}
}

func TestJoinSignatureDomainAndLabels(t *testing.T) {
	pub, key, _ := ed25519.GenerateKey(rand.Reader)
	join := JoinRequest{ChainID: "seed", Account: "alice", Operator: "operator", Family: "family", Key: pub}
	join.Signature = ed25519.Sign(key, join.SignBytes())
	raw, _ := json.Marshal(join)
	if _, err := VerifyJoinRequest(raw, "seed"); err != nil {
		t.Fatal(err)
	}
	if _, err := VerifyJoinRequest(raw, "other"); err == nil {
		t.Fatal("cross-chain join")
	}
	join.Operator = "impostor"
	raw, _ = json.Marshal(join)
	if _, err := VerifyJoinRequest(raw, "seed"); err == nil {
		t.Fatal("relabeled operator")
	}
}

func TestValidatorChangesAreActualABCIUpdates(t *testing.T) {
	oldKey := make([]byte, 32)
	newKey := make([]byte, 32)
	newKey[0] = 1
	old := &RuntimeState{Validators: map[string]int64{hex.EncodeToString(oldKey): 1}}
	next := &RuntimeState{Validators: map[string]int64{hex.EncodeToString(oldKey): 1, hex.EncodeToString(newKey): 1}}
	updates := validatorChanges(old, next)
	if len(updates) != 1 || updates[0].Power != 1 || updates[0].PubKey.GetEd25519()[0] != 1 {
		t.Fatal(updates)
	}
	updates = validatorChanges(next, old)
	if len(updates) != 1 || updates[0].Power != 0 {
		t.Fatal("removal", updates)
	}
}
