package app

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"

	abci "github.com/cometbft/cometbft/abci/types"
	bls12381 "github.com/drand/kyber-bls12381"
	"github.com/drand/kyber/sign/bls"
)

func g2Fixture(t testing.TB) (State, map[string]ed25519.PrivateKey) {
	t.Helper()
	script, err := filepath.Abs("../../../native/runtime.py")
	if err != nil {
		t.Fatal(err)
	}
	var python string
	var code []byte
	for _, candidate := range []string{os.Getenv("DAGP_PYTHON"), "python3.14", "python3.13", "python3.12", "python3.11", "python3.10", "python3", "/opt/homebrew/bin/python3"} {
		if candidate == "" {
			continue
		}
		path, e := exec.LookPath(candidate)
		if e != nil {
			continue
		}
		code, err = exec.Command(path, "-I", "-B", script, "--fingerprint").Output()
		if err == nil {
			python = path
			break
		}
	}
	if python == "" {
		t.Fatal("Python >=3.10 is required; set DAGP_PYTHON", err)
	}
	ConfigureRuntime(python, script)
	s := State{ChainID: "native-g2-test", Accounts: map[string]Account{}, Documents: map[string][]byte{}}
	keys := map[string]ed25519.PrivateKey{}
	ids := map[string]any{}
	balances := map[string]int64{}
	const now int64 = 1800000000
	for i := 0; i < 60; i++ {
		id := fmt.Sprintf("a%03d", i)
		pub, key, _ := ed25519.GenerateKey(rand.Reader)
		s.Accounts[id] = Account{Key: pub}
		keys[id] = key
		ids[id] = map[string]any{"operator": fmt.Sprintf("op%d", i), "family": fmt.Sprintf("family%d", i%5), "citizen_since": now - 40*DaySeconds,
			"roles": []string{"CITIZEN", "ADMIN", "EXAMINER", "REGISTRAR", "VERIFIER", "JUROR", "VOTE_SUPERVISOR"}}
		balances[id] = 100
	}
	suite := bls12381.NewBLS12381Suite()
	secret := suite.G1().Scalar().SetInt64(7)
	point := suite.G1().Point().Mul(secret, nil)
	pk, _ := point.MarshalBinary()
	beacon := BeaconConfig{PublicKey: hex.EncodeToString(pk), GenesisTime: now, Period: 1, Scheme: "pedersen-bls-unchained"}
	charter, _ := json.Marshal(map[string]any{"identities": ids, "common_budget": 100000, "balances": balances, "beacon": beacon, "root": "root", "constraints": []any{}})
	s.Runtime = &RuntimeState{Version: 2, CodeHash: strings.TrimSpace(string(code)), Time: now, Beacon: beacon, Charter: charter}
	return s, keys
}
func g2Signed(s State, key ed25519.PrivateKey, actor, operation string, args any) []byte {
	body, _ := json.Marshal(map[string]any{"operation": operation, "args": args})
	tx := Transaction{ChainID: s.ChainID, Account: actor, Sequence: s.Accounts[actor].Sequence, ValidUntil: s.Height + 100, Type: "protocol", Body: body}
	tx.Signature = ed25519.Sign(key, tx.SignBytes())
	raw, _ := json.Marshal(tx)
	return raw
}
func TestG2AuthenticatedPartyConsensusAndRestart(t *testing.T) {
	s, keys := g2Fixture(t)
	a, _ := Open(filepath.Join(t.TempDir(), "state.json"))
	ctx := context.Background()
	gen, _ := json.Marshal(s)
	if _, err := a.InitChain(ctx, &abci.RequestInitChain{ChainId: s.ChainID, Time: time.Unix(s.Runtime.Time, 0), AppStateBytes: gen}); err != nil {
		t.Fatal(err)
	}
	current := clone(a.committed)
	members := []string{}
	for i := 0; i < 10; i++ {
		members = append(members, fmt.Sprintf("a%03d", i))
	}
	txs := [][]byte{}
	for _, actor := range members {
		txs = append(txs, g2Signed(current, keys[actor], actor, "party.consent", map[string]any{"party": "alpha", "members": members, "nonce": "form", "scope": "root"}))
	}
	stamp := time.Unix(current.Runtime.Time+1, 0)
	prepare, err := a.PrepareProposal(ctx, &abci.RequestPrepareProposal{Height: 1, Time: stamp, MaxTxBytes: MaxBlockBytes, Txs: txs})
	if err != nil || len(prepare.Txs) != 10 {
		t.Fatal("prepare", err)
	}
	accepted, err := a.ProcessProposal(ctx, &abci.RequestProcessProposal{Height: 1, Time: stamp, Txs: prepare.Txs})
	if err != nil || accepted.Status != abci.ResponseProcessProposal_ACCEPT {
		t.Fatal("process", err)
	}
	result, err := a.FinalizeBlock(ctx, &abci.RequestFinalizeBlock{Height: 1, Time: stamp, Txs: prepare.Txs})
	if err != nil {
		t.Fatal(err)
	}
	for _, r := range result.TxResults {
		if r.Code != 0 {
			t.Fatal(r.Log)
		}
	}
	if _, err = a.Commit(ctx, &abci.RequestCommit{}); err != nil {
		t.Fatal(err)
	}
	restored, err := Open(a.path)
	if err != nil {
		t.Fatal(err)
	}
	info, _ := restored.Info(ctx, &abci.RequestInfo{})
	if string(info.LastBlockAppHash) != string(result.AppHash) {
		t.Fatal("native restart root mismatch")
	}
	if err := advanceRuntime(&current, stamp.Unix()); err != nil {
		t.Fatal(err)
	}
	for _, tx := range txs {
		mustExecute(t, &current, tx)
	}
	current.Height = 1
	if string(Root(current)) != string(result.AppHash) {
		t.Fatal("independent process/hash-seed replay diverged")
	}
	before := string(Root(restored.committed))
	check, _ := restored.CheckTx(ctx, &abci.RequestCheckTx{Tx: txs[0]})
	if check.Code == 0 || string(Root(restored.committed)) != before {
		t.Fatal("replay or mutable checktx")
	}
	hostile := g2Signed(restored.committed, keys["a000"], "a000", "treasury.release_next", map[string]any{})
	check, _ = restored.CheckTx(ctx, &abci.RequestCheckTx{Tx: hostile})
	if check.Code == 0 {
		t.Fatal("raw treasury capability exposed")
	}
}
func TestG2BLSProofAndFutureSchedule(t *testing.T) {
	s, _ := g2Fixture(t)
	suite := bls12381.NewBLS12381Suite()
	secret := suite.G1().Scalar().SetInt64(7)
	var round [8]byte
	binary.BigEndian.PutUint64(round[:], 2)
	digest := sha256.Sum256(round[:])
	sig, err := bls.NewSchemeOnG2(suite).Sign(secret, digest[:])
	if err != nil {
		t.Fatal(err)
	}
	args, _ := json.Marshal(map[string]any{"round": 1, "absolute_round": 2, "signature": hex.EncodeToString(sig)})
	if _, err := verifyBeacon(s.Runtime, args, s.Runtime.Time); err == nil {
		t.Fatal("future beacon admitted early")
	}
	if _, err := verifyBeacon(s.Runtime, args, s.Runtime.Time+1); err != nil {
		t.Fatal(err)
	}
	sig[0] ^= 1
	args, _ = json.Marshal(map[string]any{"round": 1, "absolute_round": 2, "signature": hex.EncodeToString(sig)})
	if _, err := verifyBeacon(s.Runtime, args, s.Runtime.Time+1); err == nil {
		t.Fatal("forged seed accepted")
	}
}
func TestG2KeyPossessionAndSessionScope(t *testing.T) {
	s, keys := g2Fixture(t)
	if err := initRuntime(&s); err != nil {
		t.Fatal(err)
	}
	pub, key, _ := ed25519.GenerateKey(rand.Reader)
	proof := ed25519.Sign(key, G2PossessionBytes(s.ChainID, "a000", pub))
	args := map[string]any{"key": hex.EncodeToString(pub), "proof": hex.EncodeToString(proof), "operations": []string{"pre.vote"}, "expires": s.Runtime.Time + 3600}
	mustExecute(t, &s, g2Signed(s, keys["a000"], "a000", "key.session", args))
	if len(s.Runtime.Sessions) != 1 {
		t.Fatal("session not committed")
	}
	refuse(t, &s, g2Signed(s, key, "a000", "wallet.transfer", map[string]any{"to": "a001", "amount": 1}))
	mustExecute(t, &s, g2Signed(s, keys["a000"], "a000", "key.session_revoke", map[string]any{"key": hex.EncodeToString(pub)}))
	if len(s.Runtime.Sessions) != 0 {
		t.Fatal("session not revoked")
	}
}
