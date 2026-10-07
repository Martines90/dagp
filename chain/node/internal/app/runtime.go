package app

// G2 runs the pinned deterministic protocol reducer under ABCI consensus. The
// external process receives authenticated callers, never a user-supplied Actor.
import (
	"bytes"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os/exec"
	"sort"

	bls12381 "github.com/drand/kyber-bls12381"
	"github.com/drand/kyber/sign/bls"
)

const MaxRuntimeBytes = 8 * 1024 * 1024

type BeaconConfig struct {
	PublicKey   string `json:"public_key"`
	GenesisTime int64  `json:"genesis_time"`
	Period      int64  `json:"period"`
	Scheme      string `json:"scheme"`
}
type RuntimeState struct {
	Validators map[string]int64           `json:"validators,omitempty"`
	Peers      map[string]PeerTrust       `json:"peers,omitempty"`
	Exports    map[string]json.RawMessage `json:"exports,omitempty"`
	Sessions   map[string]SessionGrant    `json:"sessions,omitempty"`
	Version    int                        `json:"version"`
	CodeHash   string                     `json:"code_hash"`
	Time       int64                      `json:"time"`
	Beacon     BeaconConfig               `json:"beacon"`
	Charter    json.RawMessage            `json:"charter,omitempty"`
	Graph      json.RawMessage            `json:"graph,omitempty"`
}
type ProtocolMessage struct {
	Operation string          `json:"operation"`
	Args      json.RawMessage `json:"args"`
}
type RuntimeRequest struct {
	Mode      string            `json:"mode"`
	CodeHash  string            `json:"code_hash"`
	Chain     string            `json:"chain"`
	Time      int64             `json:"time"`
	Charter   json.RawMessage   `json:"charter,omitempty"`
	Graph     json.RawMessage   `json:"graph,omitempty"`
	Keys      map[string]string `json:"keys,omitempty"`
	Actor     string            `json:"actor,omitempty"`
	Operation string            `json:"operation,omitempty"`
	Args      json.RawMessage   `json:"args,omitempty"`
	TxID      string            `json:"txid,omitempty"`
	Verified  map[string]string `json:"verified,omitempty"`
}
type RuntimeReply struct {
	Beacon     BeaconConfig               `json:"beacon"`
	Validators map[string]int64           `json:"validators,omitempty"`
	Exports    map[string]json.RawMessage `json:"exports,omitempty"`
	OK         bool                       `json:"ok"`
	Error      string                     `json:"error,omitempty"`
	Graph      json.RawMessage            `json:"graph,omitempty"`
	Keys       map[string]string          `json:"keys,omitempty"`
	Sessions   map[string]SessionGrant    `json:"sessions,omitempty"`
	Result     json.RawMessage            `json:"result,omitempty"`
}

// Host failures halt proposal/finalization rather than becoming nondeterministic
// invalid-transaction decisions. Returned protocol violations are deterministic.
type RuntimeUnavailable struct{ Cause error }

func (e *RuntimeUnavailable) Error() string {
	return "governance runtime unavailable: " + e.Cause.Error()
}

type RuntimeRunner struct{ Python, Script string }

var runtimeRunner *RuntimeRunner

// ConfigureRuntime must run before opening an application. Paths are operator
// configuration, not transaction fields. The fingerprint is checked each call.
func ConfigureRuntime(python, script string) { runtimeRunner = &RuntimeRunner{python, script} }

type boundedBuffer struct {
	bytes.Buffer
	exceeded bool
}

func (b *boundedBuffer) Write(p []byte) (int, error) {
	if b.Len()+len(p) > 2*MaxRuntimeBytes {
		b.exceeded = true
		return 0, errors.New("runtime output bound")
	}
	return b.Buffer.Write(p)
}
func runRuntime(req RuntimeRequest) (RuntimeReply, error) {
	var reply RuntimeReply
	if runtimeRunner == nil {
		return reply, &RuntimeUnavailable{errors.New("configure Python and governance runtime paths")}
	}
	input, err := json.Marshal(req)
	if err != nil {
		return reply, err
	}
	cmd := exec.Command(runtimeRunner.Python, "-I", "-B", runtimeRunner.Script)
	cmd.Stdin = bytes.NewReader(input)
	var stdout, stderr boundedBuffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	// Python hash randomization cannot affect persisted state: all graph map/set
	// traversal and protocol pools are canonicalized. Tests replay distinct seeds.
	cmd.Env = []string{"PATH=/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE=1", "TZ=UTC", "LC_ALL=C"}
	if err = cmd.Run(); err != nil {
		return reply, &RuntimeUnavailable{fmt.Errorf("process failed: %w", err)}
	}
	if stdout.exceeded || stderr.exceeded {
		return reply, &RuntimeUnavailable{errors.New("process output limit")}
	}
	if err = decode(stdout.Bytes(), &reply); err != nil {
		return reply, &RuntimeUnavailable{err}
	}
	if !reply.OK {
		return reply, errors.New(reply.Error)
	}
	if len(reply.Graph) == 0 || len(reply.Graph) > MaxRuntimeBytes || len(reply.Keys) > MaxAccounts {
		return reply, &RuntimeUnavailable{errors.New("invalid runtime response")}
	}
	return reply, nil
}
func validateRuntimeState(s State) error {
	r := s.Runtime
	if r == nil {
		return nil
	}
	if s.Governance != nil || r.Version != 2 || !hashEvidence(r.CodeHash) || r.Time <= 0 || r.Time > 253402300799 || len(r.Graph) > MaxRuntimeBytes || r.Beacon.Period < 1 || r.Beacon.Period > 86400 || r.Beacon.GenesisTime < 1 {
		return errors.New("invalid G2 metadata")
	}
	for chain, peer := range r.Peers {
		if !identifier.MatchString(chain) || chain == s.ChainID {
			return errors.New("peer chain domain")
		}
		if _, err := validatorTrust(peer); err != nil {
			return err
		}
	}
	if r.Beacon.Scheme == "bootstrap-disabled" {
		var charter struct {
			Bootstrap json.RawMessage `json:"bootstrap"`
		}
		_ = json.Unmarshal(r.Charter, &charter)
		var society struct {
			Bootstrap struct {
				Phase string `json:"phase"`
			} `json:"bootstrap"`
		}
		_ = json.Unmarshal(r.Exports["society"], &society)
		if r.Beacon.PublicKey != "" || (len(charter.Bootstrap) == 0 && society.Bootstrap.Phase != "SEED" && society.Bootstrap.Phase != "EXPIRED") {
			return errors.New("disabled beacon requires explicit founding stage")
		}
	} else if err := validateBeaconConfig(r.Beacon); err != nil {
		return err
	}
	if len(r.Validators) > 100 {
		return errors.New("validator set bound")
	}
	for key, power := range r.Validators {
		raw, err := hex.DecodeString(key)
		if err != nil || len(raw) != 32 || hex.EncodeToString(raw) != key || power != 1 {
			return errors.New("invalid founding validator set")
		}
	}
	if len(r.Graph) > 0 {
		if len(r.Charter) > 0 {
			return errors.New("charter must be consumed at init")
		}
		if err := strictJSON(r.Graph); err != nil {
			return err
		}
	}
	return nil
}
func validateBeaconConfig(b BeaconConfig) error {
	if b.Scheme != "pedersen-bls-unchained" || b.Period < 1 || b.Period > 86400 || b.GenesisTime < 1 || b.GenesisTime > 253402300799 {
		return errors.New("invalid independent beacon configuration")
	}
	suite := bls12381.NewBLS12381Suite()
	pub := suite.G1().Point()
	key, err := hex.DecodeString(b.PublicKey)
	if err != nil || pub.UnmarshalBinary(key) != nil || pub.Equal(suite.G1().Point().Null()) {
		return errors.New("invalid beacon public key")
	}
	return nil
}
func decodeProtocol(t Transaction) (ProtocolMessage, error) {
	var p ProtocolMessage
	if t.Type != "protocol" || len(t.Body) > 65536 {
		return p, errors.New("G2 protocol message required")
	}
	if err := decode(t.Body, &p); err != nil {
		return p, err
	}
	var fields map[string]json.RawMessage
	_ = json.Unmarshal(t.Body, &fields)
	if len(fields) != 2 || fields["operation"] == nil || fields["args"] == nil || len(p.Args) == 0 || p.Args[0] != '{' {
		return p, errors.New("exact G2 message fields required")
	}
	return p, nil
}
func verifyBeacon(r *RuntimeState, args json.RawMessage, now int64) (string, error) {
	if err := validateBeaconConfig(r.Beacon); err != nil {
		return "", err
	}
	var a struct {
		Scope         string `json:"scope,omitempty"`
		Round         uint64 `json:"round"`
		AbsoluteRound uint64 `json:"absolute_round"`
		Signature     string `json:"signature"`
	}
	if err := decode(args, &a); err != nil {
		return "", err
	}
	if a.AbsoluteRound == 0 || a.AbsoluteRound > uint64((253402300799-r.Beacon.GenesisTime)/r.Beacon.Period)+1 {
		return "", errors.New("beacon round bound")
	}
	at := r.Beacon.GenesisTime + int64(a.AbsoluteRound-1)*r.Beacon.Period
	if at > now {
		return "", errors.New("beacon precedes scheduled publication")
	}
	sig, err := hex.DecodeString(a.Signature)
	if err != nil || len(sig) != 96 {
		return "", errors.New("beacon signature encoding")
	}
	suite := bls12381.NewBLS12381Suite()
	pub := suite.G1().Point()
	key, _ := hex.DecodeString(r.Beacon.PublicKey)
	if err = pub.UnmarshalBinary(key); err != nil {
		return "", err
	}
	var round [8]byte
	binary.BigEndian.PutUint64(round[:], a.AbsoluteRound)
	digest := sha256.Sum256(round[:])
	// This is one pinned collective DKG key, not attacker-chosen aggregate keys.
	if err = bls.NewSchemeOnG2(suite).Verify(pub, digest[:], sig); err != nil {
		return "", errors.New("invalid BLS future beacon proof")
	}
	seed := sha256.Sum256(sig)
	return hex.EncodeToString(seed[:]), nil
}
func applyRuntimeKeys(s *State, keys map[string]string) error {
	if len(keys) < len(s.Accounts) {
		return errors.New("runtime removed signing accounts")
	}
	for id := range s.Accounts {
		if _, ok := keys[id]; !ok {
			return errors.New("runtime removed signing account")
		}
	}
	seen := map[string]bool{}
	ids := make([]string, 0, len(keys))
	for id := range keys {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	for _, id := range ids {
		key, err := hex.DecodeString(keys[id])
		if err != nil || len(key) != ed25519.PublicKeySize || !identifier.MatchString(id) || seen[string(key)] {
			return errors.New("invalid runtime signing account")
		}
		seen[string(key)] = true
		a := s.Accounts[id]
		a.Key = key
		s.Accounts[id] = a
	}
	return nil
}
func initRuntime(s *State) error {
	if s.Runtime == nil {
		return nil
	}
	r := s.Runtime
	if len(r.Graph) > 0 || len(r.Charter) == 0 {
		return errors.New("fresh charter required")
	}
	keys := map[string]string{}
	for id, a := range s.Accounts {
		keys[id] = hex.EncodeToString(a.Key)
	}
	reply, err := runRuntime(RuntimeRequest{Mode: "init", CodeHash: r.CodeHash, Chain: s.ChainID, Time: r.Time, Charter: r.Charter, Keys: keys})
	if err != nil {
		return err
	}
	r.Exports = reply.Exports
	r.Sessions = reply.Sessions
	r.Graph = reply.Graph
	r.Beacon = reply.Beacon
	r.Validators = reply.Validators
	r.Charter = nil
	return applyRuntimeKeys(s, reply.Keys)
}
func advanceRuntime(s *State, now int64) error {
	if s.Runtime == nil {
		return nil
	}
	r := s.Runtime
	if now < r.Time {
		return errors.New("G2 consensus clock reversal")
	}
	reply, err := runRuntime(RuntimeRequest{Mode: "advance", CodeHash: r.CodeHash, Chain: s.ChainID, Time: now, Graph: r.Graph})
	if err != nil {
		return err
	}
	r.Time = now
	r.Exports = reply.Exports
	r.Sessions = reply.Sessions
	r.Graph = reply.Graph
	r.Beacon = reply.Beacon
	r.Validators = reply.Validators
	return applyRuntimeKeys(s, reply.Keys)
}
func executeRuntime(s *State, t Transaction, raw []byte) error {
	if s.Runtime == nil {
		return errors.New("G2 runtime disabled")
	}
	p, err := decodeProtocol(t)
	if err != nil {
		return err
	}
	r := s.Runtime
	verified := map[string]string{}
	if p.Operation == "bootstrap.propose" {
		var proposal struct {
			Action  string `json:"action"`
			Payload struct {
				Join   json.RawMessage `json:"join"`
				Key    string          `json:"key"`
				Proof  string          `json:"proof"`
				Target string          `json:"target"`
				Beacon BeaconConfig    `json:"beacon"`
			} `json:"payload"`
		}
		if err := json.Unmarshal(p.Args, &proposal); err != nil {
			return err
		}
		if proposal.Action == "INVITE" {
			join, err := VerifyJoinRequest(proposal.Payload.Join, s.ChainID)
			if err != nil {
				return err
			}
			verified["join_key"] = hex.EncodeToString(join.Key)
			if r.Validators[verified["join_key"]] != 0 {
				return errors.New("citizen key cannot reuse an active consensus key")
			}
		}
		if proposal.Action == "GRADUATE" {
			if err := validateBeaconConfig(proposal.Payload.Beacon); err != nil {
				return err
			}
			verified["beacon_configuration"] = "verified"
		}
		if proposal.Action == "VALIDATOR_ADD" {
			key, e := hex.DecodeString(proposal.Payload.Key)
			proof, e2 := hex.DecodeString(proposal.Payload.Proof)
			if e != nil || e2 != nil || len(key) != 32 || hex.EncodeToString(key) != proposal.Payload.Key || !ed25519.Verify(key, G2PossessionBytes(s.ChainID, proposal.Payload.Target, key), proof) {
				return errors.New("validator-key possession required")
			}
			verified["new_key"] = proposal.Payload.Key
		}
	}
	var envelope map[string]json.RawMessage
	if json.Unmarshal(p.Args, &envelope) != nil {
		return errors.New("protocol arguments")
	}
	if peer := envelope["peer"]; peer != nil {
		verified, err = verifyPeer(s, peer)
		if err != nil {
			return err
		}
	}
	if p.Operation == "beacon.publish" {
		seed, err := verifyBeacon(r, p.Args, r.Time)
		if err != nil {
			return err
		}
		verified["beacon_seed"] = seed
	}
	if p.Operation == "key.rotate" || p.Operation == "key.session" || p.Operation == "key.recover" || p.Operation == "merger.lock" {
		var a struct {
			Key            string `json:"key"`
			Proof          string `json:"proof"`
			Target         string `json:"target"`
			DestinationKey string `json:"destination_key"`
		}
		if json.Unmarshal(p.Args, &a) != nil {
			return errors.New("key proof fields")
		}
		if p.Operation == "merger.lock" {
			a.Key = a.DestinationKey
		}
		key, err := hex.DecodeString(a.Key)
		proof, e := hex.DecodeString(a.Proof)
		owner := t.Account
		if p.Operation == "key.recover" {
			owner = a.Target
		}
		if err != nil || e != nil || len(key) != 32 || hex.EncodeToString(key) != a.Key || !ed25519.Verify(key, G2PossessionBytes(s.ChainID, owner, key), proof) {
			return errors.New("invalid G2 key possession")
		}
		verified["new_key"] = a.Key
		if r.Validators[a.Key] != 0 {
			return errors.New("citizen/session key cannot reuse an active consensus key")
		}
	}
	if p.Operation == "identity.challenge" {
		var a struct {
			Key string `json:"key"`
		}
		if err := decode(p.Args, &a); err != nil {
			return err
		}
		key, err := hex.DecodeString(a.Key)
		if err != nil || len(key) != 32 || hex.EncodeToString(key) != a.Key || r.Validators[a.Key] != 0 {
			return errors.New("registration key encoding")
		}
		verified["registration_key"] = a.Key
	}
	digest := sha256.Sum256(raw)
	reply, err := runRuntime(RuntimeRequest{Mode: "execute", CodeHash: r.CodeHash, Chain: s.ChainID, Time: r.Time, Graph: r.Graph,
		Actor: t.Account, Operation: p.Operation, Args: p.Args, TxID: hex.EncodeToString(digest[:]), Verified: verified})
	if err != nil {
		return err
	}
	if err := applyRuntimeKeys(s, reply.Keys); err != nil {
		return &RuntimeUnavailable{err}
	}
	r.Graph = reply.Graph
	r.Exports = reply.Exports
	r.Sessions = reply.Sessions
	r.Beacon = reply.Beacon
	r.Validators = reply.Validators
	return nil
}
func registrationAccount(s *State, t Transaction) (Account, bool) {
	if s.Runtime == nil {
		return Account{}, false
	}
	p, err := decodeProtocol(t)
	if err != nil || (p.Operation != "identity.challenge" && p.Operation != "merger.claim") || !identifier.MatchString(t.Account) {
		return Account{}, false
	}
	var a struct {
		Key string `json:"key"`
	}
	if json.Unmarshal(p.Args, &a) != nil {
		return Account{}, false
	}
	key, err := hex.DecodeString(a.Key)
	if err != nil || len(key) != 32 {
		return Account{}, false
	}
	for _, old := range s.Accounts {
		if bytes.Equal(key, old.Key) {
			return Account{}, false
		}
	}
	if len(s.Accounts) >= MaxAccounts {
		return Account{}, false
	}
	return Account{Key: key}, true
}
func isRuntimeUnavailable(err error) bool {
	var failure *RuntimeUnavailable
	return errors.As(err, &failure)
}
func checkRuntimeFingerprint(s State) error {
	if s.Runtime == nil {
		return nil
	}
	// State reconstruction performs a live code pin check before this node reports
	// a committed height. Missing/wrong runtime cannot start serving this chain.
	clone := clone(s)
	return advanceRuntime(&clone, s.Runtime.Time)
}

// Keep imports explicit; command text never goes through a shell.
var _ io.Writer = (*boundedBuffer)(nil)

func cloneMutable(s State) State {
	n := cloneSecurity(s)
	if s.Runtime != nil {
		r := *s.Runtime
		n.Runtime = &r
	}
	return n
}
func advanceClock(s *State, now int64) error {
	if err := advanceTime(s, now); err != nil {
		return err
	}
	return advanceRuntime(s, now)
}

type SessionGrant struct {
	Account    string   `json:"account"`
	Operations []string `json:"operations"`
	Expires    int64    `json:"expires"`
}

func G2PossessionBytes(chain, account string, key []byte) []byte {
	old := RotationProofBytes(chain, account, key)
	return append([]byte("DAGP/G2/KEY-POSSESSION-v1\x00"), old[len("DAGP/G1/KEY-POSSESSION-v1\x00"):]...)
}
func verifySession(s *State, t Transaction) bool {
	if s.Runtime == nil {
		return false
	}
	p, err := decodeProtocol(t)
	if err != nil {
		return false
	}
	for encoded, g := range s.Runtime.Sessions {
		if g.Account != t.Account || g.Expires <= s.Runtime.Time {
			continue
		}
		allowed := false
		for _, op := range g.Operations {
			if op == p.Operation {
				allowed = true
			}
		}
		if !allowed {
			continue
		}
		key, e := hex.DecodeString(encoded)
		if e == nil && len(key) == 32 && ed25519.Verify(key, t.SignBytes(), t.Signature) {
			return true
		}
	}
	return false
}
