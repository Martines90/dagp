package app

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	abci "github.com/cometbft/cometbft/abci/types"
	"path/filepath"
	"testing"
	"time"
)

func g1Fixture(t testing.TB, n int) (State, map[string]ed25519.PrivateKey) {
	t.Helper()
	s := State{ChainID: "native-g1-test", Accounts: map[string]Account{}, Documents: map[string][]byte{}}
	g := &Governance{Version: 1, Time: 1800000000, Identities: map[string]Identity{}, Cases: map[string]Containment{}, Rosters: map[string][]string{}, Rotations: map[string]KeyRotation{}, Freezes: []SecurityEvent{}, Complaints: []SecurityEvent{}}
	s.Governance = g
	keys := map[string]ed25519.PrivateKey{}
	for j := 0; j < n; j++ {
		id := fmt.Sprintf("agent%03d", j)
		pub, key, err := ed25519.GenerateKey(rand.Reader)
		if err != nil {
			t.Fatal(err)
		}
		keys[id] = key
		s.Accounts[id] = Account{Key: pub}
		g.Identities[id] = Identity{Operator: fmt.Sprintf("op%03d", j), CitizenSince: g.Time - 40*DaySeconds, AdminSince: g.Time - 3*DaySeconds}
	}
	if err := validateState(s); err != nil {
		t.Fatal(err)
	}
	return s, keys
}
func g1Tx(s State, key ed25519.PrivateKey, actor, kind string, body any) []byte {
	b, _ := json.Marshal(body)
	tx := Transaction{ChainID: s.ChainID, Account: actor, Sequence: s.Accounts[actor].Sequence, ValidUntil: s.Height + 100, Type: kind, Body: b}
	tx.Signature = ed25519.Sign(key, tx.SignBytes())
	raw, _ := json.Marshal(tx)
	return raw
}

var evidence = fmt.Sprintf("%064x", 1)

func mustExecute(t testing.TB, s *State, raw []byte) {
	t.Helper()
	if err := Execute(s, raw, s.Height+1); err != nil {
		t.Fatal(err)
	}
}
func refuse(t testing.TB, s *State, raw []byte) {
	t.Helper()
	before := string(Root(*s))
	if Execute(s, raw, s.Height+1) == nil {
		t.Fatal("accepted hostile transaction")
	}
	if string(Root(*s)) != before {
		t.Fatal("failed transaction changed state")
	}
}
func TestG1CoordinatedInsiders(t *testing.T) {
	s, keys := g1Fixture(t, 1000)
	// Exactly 50 pre-provisioned admins; the other 950 are citizens.
	for id, i := range s.Governance.Identities {
		if id >= "agent050" {
			i.AdminSince = 0
			s.Governance.Identities[id] = i
		}
	}
	for j := 0; j < 10; j++ {
		actor := fmt.Sprintf("agent%03d", j)
		for k := 0; k < 2; k++ {
			target := fmt.Sprintf("agent%03d", 100+j*2+k)
			mustExecute(t, &s, g1Tx(s, keys[actor], actor, "freeze_identity", map[string]string{"target": target, "evidence": evidence}))
		}
	}
	refuse(t, &s, g1Tx(s, keys["agent010"], "agent010", "freeze_identity", map[string]string{"target": "agent999", "evidence": evidence}))
	// Frozen identities retain their key and citizenship date, and can rotate keys.
	if len(s.Governance.Freezes) != 20 || s.Governance.Identities["agent100"].CitizenSince == 0 {
		t.Fatal("quota or civic state")
	}
	raw := g1Tx(s, keys["agent010"], "agent010", "open_containment", map[string]string{"target": "agent000", "evidence": evidence})
	var tx Transaction
	_ = json.Unmarshal(raw, &tx)
	h := sha256.Sum256(tx.SignBytes())
	cid := hex.EncodeToString(h[:])
	mustExecute(t, &s, raw)
	if len(s.Governance.Rosters[s.Governance.Cases[cid].Roster]) != 50 {
		t.Fatal("council denominator changed")
	}
	for j := 1; j <= 10; j++ {
		actor := fmt.Sprintf("agent%03d", j)
		mustExecute(t, &s, g1Tx(s, keys[actor], actor, "approve_containment", map[string]string{"case": cid}))
	}
	if s.Governance.Identities["agent000"].HeldUntil != 0 {
		t.Fatal("minority seized council")
	}
	for j := 11; j <= 25; j++ {
		actor := fmt.Sprintf("agent%03d", j)
		mustExecute(t, &s, g1Tx(s, keys[actor], actor, "approve_containment", map[string]string{"case": cid}))
	}
	if s.Governance.Identities["agent000"].HeldUntil <= s.Governance.Time {
		t.Fatal("majority containment failed")
	}
	s.Governance.Time += 60
	refuse(t, &s, g1Tx(s, keys["agent000"], "agent000", "open_containment", map[string]string{"target": "agent030", "evidence": evidence}))
	if err := validateState(s); err != nil {
		t.Fatal(err)
	}
}
func TestG1FreezeCannotShrinkCouncil(t *testing.T) {
	s, keys := g1Fixture(t, 50)
	mustExecute(t, &s, g1Tx(s, keys["agent000"], "agent000", "freeze_identity", map[string]string{"target": "agent049", "evidence": evidence}))
	mustExecute(t, &s, g1Tx(s, keys["agent001"], "agent001", "open_containment", map[string]string{"target": "agent000", "evidence": evidence}))
	for _, c := range s.Governance.Cases {
		if len(s.Governance.Rosters[c.Roster]) != 50 {
			t.Fatal("freeze shrank roster")
		}
	}
}
func TestG1TenureQuotaAndAtomicity(t *testing.T) {
	s, keys := g1Fixture(t, 1000)
	actor := "agent000"
	i := s.Governance.Identities[actor]
	original := i
	for _, change := range []Identity{{Operator: i.Operator, CitizenSince: s.Governance.Time - 29*DaySeconds, AdminSince: s.Governance.Time - 3*DaySeconds}, {Operator: i.Operator, CitizenSince: i.CitizenSince, AdminSince: s.Governance.Time - DaySeconds}} {
		s.Governance.Identities[actor] = change
		refuse(t, &s, g1Tx(s, keys[actor], actor, "freeze_identity", map[string]string{"target": "agent100", "evidence": evidence}))
	}
	s.Governance.Identities[actor] = original
	for _, target := range []string{"agent100", "agent101"} {
		mustExecute(t, &s, g1Tx(s, keys[actor], actor, "freeze_identity", map[string]string{"target": target, "evidence": evidence}))
	}
	refuse(t, &s, g1Tx(s, keys[actor], actor, "freeze_identity", map[string]string{"target": "agent102", "evidence": evidence}))
	s.Governance.Time += DaySeconds - 1
	refuse(t, &s, g1Tx(s, keys[actor], actor, "freeze_identity", map[string]string{"target": "agent102", "evidence": evidence}))
	s.Governance.Time++
	mustExecute(t, &s, g1Tx(s, keys[actor], actor, "freeze_identity", map[string]string{"target": "agent102", "evidence": evidence}))
	for _, kind := range []string{"grant_admin", "ban_citizen", "allocate_budget", "cast_vote"} {
		refuse(t, &s, g1Tx(s, keys[actor], actor, kind, map[string]string{}))
	}
	refuse(t, &s, g1Tx(s, keys[actor], actor, "freeze_identity", map[string]string{"Target": "agent103", "evidence": evidence}))
	refuse(t, &s, g1Tx(s, keys[actor], actor, "freeze_identity", map[string]string{"target": "agent103", "evidence": "bad"}))
}
func TestG1DelayedRotationAndReplay(t *testing.T) {
	s, keys := g1Fixture(t, 5)
	actor := "agent000"
	pub, newkey, _ := ed25519.GenerateKey(rand.Reader)
	proof := ed25519.Sign(newkey, RotationProofBytes(s.ChainID, actor, pub))
	raw := g1Tx(s, keys[actor], actor, "schedule_key_rotation", map[string][]byte{"key": pub, "proof": proof})
	mustExecute(t, &s, raw)
	refuse(t, &s, raw)
	refuse(t, &s, g1Tx(s, keys[actor], actor, "activate_key_rotation", map[string]string{}))
	s.Governance.Time += 2 * DaySeconds
	mustExecute(t, &s, g1Tx(s, keys[actor], actor, "activate_key_rotation", map[string]string{}))
	refuse(t, &s, g1Tx(s, keys[actor], actor, "cancel_key_rotation", map[string]string{}))
	pub2, key2, _ := ed25519.GenerateKey(rand.Reader)
	mustExecute(t, &s, g1Tx(s, newkey, actor, "schedule_key_rotation", map[string][]byte{"key": pub2, "proof": ed25519.Sign(key2, RotationProofBytes(s.ChainID, actor, pub2))}))
	mustExecute(t, &s, g1Tx(s, newkey, actor, "cancel_key_rotation", map[string]string{}))
	if err := validateState(s); err != nil {
		t.Fatal(err)
	}
}
func TestG1ConsensusTimeCommitRestart(t *testing.T) {
	s, keys := g1Fixture(t, 7)
	ctx := context.Background()
	path := filepath.Join(t.TempDir(), "state.json")
	a, _ := Open(path)
	gen, _ := json.Marshal(s)
	_, err := a.InitChain(ctx, &abci.RequestInitChain{ChainId: s.ChainID, Time: time.Unix(s.Governance.Time, 0), AppStateBytes: gen})
	if err != nil {
		t.Fatal(err)
	}
	tx := g1Tx(s, keys["agent000"], "agent000", "freeze_identity", map[string]string{"target": "agent006", "evidence": evidence})
	stamp := time.Unix(s.Governance.Time+1, 0)
	p, err := a.PrepareProposal(ctx, &abci.RequestPrepareProposal{Height: 1, Time: stamp, MaxTxBytes: MaxBlockBytes, Txs: [][]byte{tx, tx}})
	if err != nil || len(p.Txs) != 1 {
		t.Fatal("prepare", err)
	}
	check, _ := a.ProcessProposal(ctx, &abci.RequestProcessProposal{Height: 1, Time: stamp, Txs: p.Txs})
	if check.Status != abci.ResponseProcessProposal_ACCEPT {
		t.Fatal("valid proposal rejected")
	}
	result, err := a.FinalizeBlock(ctx, &abci.RequestFinalizeBlock{Height: 1, Time: stamp, Txs: p.Txs})
	if err != nil || result.TxResults[0].Code != 0 {
		t.Fatal("finalize", err)
	}
	q, _ := a.Query(ctx, &abci.RequestQuery{Path: "/governance"})
	var before Governance
	_ = json.Unmarshal(q.Value, &before)
	if before.Time != s.Governance.Time {
		t.Fatal("pending leaked")
	}
	if _, err := a.Commit(ctx, &abci.RequestCommit{}); err != nil {
		t.Fatal(err)
	}
	b, err := Open(path)
	if err != nil {
		t.Fatal(err)
	}
	info, _ := b.Info(ctx, &abci.RequestInfo{})
	if string(info.LastBlockAppHash) != string(result.AppHash) {
		t.Fatal("restart hash")
	}
	s.Governance.Time = stamp.Unix()
	mustExecute(t, &s, tx)
	s.Height = 1
	if string(Root(s)) != string(result.AppHash) {
		t.Fatal("independent deterministic replay")
	}
	check, _ = b.ProcessProposal(ctx, &abci.RequestProcessProposal{Height: 2, Time: time.Unix(stamp.Unix()-1, 0)})
	if check.Status != abci.ResponseProcessProposal_REJECT {
		t.Fatal("clock reversal")
	}
}
func TestG1IdentityAndKeyConflicts(t *testing.T) {
	s, keys := g1Fixture(t, 50)
	actor := "agent000"
	other := "agent001"
	i := s.Governance.Identities[other]
	i.Operator = s.Governance.Identities[actor].Operator
	s.Governance.Identities[other] = i
	refuse(t, &s, g1Tx(s, keys[actor], actor, "freeze_identity", map[string]string{"target": other, "evidence": evidence}))
	refuse(t, &s, g1Tx(s, keys[actor], actor, "open_containment", map[string]string{"target": "agent049", "evidence": evidence}))
	pub, newkey, _ := ed25519.GenerateKey(rand.Reader)
	refuse(t, &s, g1Tx(s, keys[actor], actor, "schedule_key_rotation", map[string][]byte{"key": pub, "proof": ed25519.Sign(newkey, RotationProofBytes("other-chain", actor, pub))}))
	mustExecute(t, &s, g1Tx(s, keys[actor], actor, "schedule_key_rotation", map[string][]byte{"key": pub, "proof": ed25519.Sign(newkey, RotationProofBytes(s.ChainID, actor, pub))}))
	refuse(t, &s, g1Tx(s, keys[other], other, "schedule_key_rotation", map[string][]byte{"key": pub, "proof": ed25519.Sign(newkey, RotationProofBytes(s.ChainID, other, pub))}))
	zero := clone(s)
	zero.Governance = nil
	refuse(t, &zero, g1Tx(zero, keys[actor], actor, "freeze_identity", map[string]string{"target": "agent049", "evidence": evidence}))
}
func TestG1PopulationCapAndDuplicateCouncilVote(t *testing.T) {
	s, keys := g1Fixture(t, 50)
	for j := 0; j < 3; j++ {
		actor := fmt.Sprintf("agent%03d", j)
		target := fmt.Sprintf("agent%03d", j+40)
		mustExecute(t, &s, g1Tx(s, keys[actor], actor, "freeze_identity", map[string]string{"target": target, "evidence": evidence}))
	}
	refuse(t, &s, g1Tx(s, keys["agent003"], "agent003", "freeze_identity", map[string]string{"target": "agent043", "evidence": evidence}))
	mustExecute(t, &s, g1Tx(s, keys["agent003"], "agent003", "open_containment", map[string]string{"target": "agent000", "evidence": evidence}))
	var cid string
	for id := range s.Governance.Cases {
		cid = id
	}
	mustExecute(t, &s, g1Tx(s, keys["agent004"], "agent004", "approve_containment", map[string]string{"case": cid}))
	refuse(t, &s, g1Tx(s, keys["agent004"], "agent004", "approve_containment", map[string]string{"case": cid}))
	refuse(t, &s, g1Tx(s, keys["agent000"], "agent000", "approve_containment", map[string]string{"case": cid}))
	s.Governance.Time += 3600
	refuse(t, &s, g1Tx(s, keys["agent005"], "agent005", "approve_containment", map[string]string{"case": cid}))
}
func TestG1MinorityCannotExhaustComplaintCapacity(t *testing.T) {
	s, keys := g1Fixture(t, 50)
	for j := 0; j < 10; j++ {
		actor := fmt.Sprintf("agent%03d", j)
		target := fmt.Sprintf("agent%03d", j+30)
		mustExecute(t, &s, g1Tx(s, keys[actor], actor, "open_containment", map[string]string{"target": target, "evidence": evidence}))
	}
	mustExecute(t, &s, g1Tx(s, keys["agent010"], "agent010", "open_containment", map[string]string{"target": "agent000", "evidence": evidence}))
	if len(s.Governance.Cases) != 11 {
		t.Fatal("minority exhausted complaints")
	}
	refuse(t, &s, g1Tx(s, keys["agent000"], "agent000", "open_containment", map[string]string{"target": "agent029", "evidence": evidence}))
	if err := validateState(s); err != nil {
		t.Fatal(err)
	}
}
func TestG1OperatorAliasesShareFreezeQuota(t *testing.T) {
	s, keys := g1Fixture(t, 1000)
	alias := s.Governance.Identities["agent001"]
	alias.Operator = s.Governance.Identities["agent000"].Operator
	s.Governance.Identities["agent001"] = alias
	for j, actor := range []string{"agent000", "agent001"} {
		target := fmt.Sprintf("agent%03d", 100+j)
		mustExecute(t, &s, g1Tx(s, keys[actor], actor, "freeze_identity", map[string]string{"target": target, "evidence": evidence}))
	}
	refuse(t, &s, g1Tx(s, keys["agent001"], "agent001", "freeze_identity", map[string]string{"target": "agent102", "evidence": evidence}))
}
func TestG1RejectsNullAndOversizedBodies(t *testing.T) {
	s, keys := g1Fixture(t, 5)
	refuse(t, &s, g1Tx(s, keys["agent000"], "agent000", "cancel_key_rotation", nil))
	refuse(t, &s, g1Tx(s, keys["agent000"], "agent000", "freeze_identity", map[string]string{"target": "agent001", "evidence": string(make([]byte, 4096))}))
}
func TestG1GenesisMustMatchConsensusTime(t *testing.T) {
	s, _ := g1Fixture(t, 5)
	a, _ := Open(filepath.Join(t.TempDir(), "state.json"))
	gen, _ := json.Marshal(s)
	if _, err := a.InitChain(context.Background(), &abci.RequestInitChain{ChainId: s.ChainID, Time: time.Unix(s.Governance.Time+1, 0), AppStateBytes: gen}); err == nil {
		t.Fatal("client clock accepted")
	}
	if a.committed.ChainID != "" {
		t.Fatal("invalid genesis persisted")
	}
}
