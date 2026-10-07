package app

// G1 is an opt-in native identity-security keeper. It deliberately has no
// appointment, ban, citizenship issuance, voting or treasury authority shortcut.
import (
	"bytes"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"math"
	"sort"
)

const DaySeconds int64 = 86400
const MaxGovernanceBytes = 8 * 1024 * 1024

type Identity struct {
	Operator     string `json:"operator"`
	CitizenSince int64  `json:"citizen_since"`
	AdminSince   int64  `json:"admin_since,omitempty"`
	FrozenUntil  int64  `json:"frozen_until,omitempty"`
	HeldUntil    int64  `json:"held_until,omitempty"`
}
type SecurityEvent struct {
	Actor string `json:"actor"`
	At    int64  `json:"at"`
}
type Containment struct {
	Target    string   `json:"target"`
	Evidence  string   `json:"evidence"`
	Expires   int64    `json:"expires"`
	Roster    string   `json:"roster"`
	Approvals []string `json:"approvals"`
	Applied   bool     `json:"applied"`
}
type KeyRotation struct {
	Key   []byte `json:"key"`
	Ready int64  `json:"ready"`
}
type Governance struct {
	Version    int                    `json:"version"`
	Time       int64                  `json:"time"`
	Identities map[string]Identity    `json:"identities"`
	Freezes    []SecurityEvent        `json:"freezes"`
	Complaints []SecurityEvent        `json:"complaints"`
	Cases      map[string]Containment `json:"cases"`
	Rosters    map[string][]string    `json:"rosters"`
	Rotations  map[string]KeyRotation `json:"rotations"`
}
type securityMessage struct {
	Target   string `json:"target"`
	Evidence string `json:"evidence"`
	Case     string `json:"case"`
	Key      []byte `json:"key"`
	Proof    []byte `json:"proof"`
}

func (g *Governance) admin(id string, now int64) bool {
	i, ok := g.Identities[id]
	return ok && i.CitizenSince <= now-30*DaySeconds && i.AdminSince > 0 && i.AdminSince <= now-2*DaySeconds && i.HeldUntil <= now
}
func recent(events []SecurityEvent, now int64) []SecurityEvent {
	out := make([]SecurityEvent, 0, len(events))
	for _, e := range events {
		if e.At > now-DaySeconds {
			out = append(out, e)
		}
	}
	return out
}
func operatorCount(g *Governance, events []SecurityEvent, who string) int {
	n := 0
	for _, e := range events {
		if g.Identities[e.Actor].Operator == g.Identities[who].Operator {
			n++
		}
	}
	return n
}
func hashEvidence(e string) bool {
	b, err := hex.DecodeString(e)
	return err == nil && len(b) == 32 && hex.EncodeToString(b) == e
}

// Security messages never mutate document bytes. Copy only their write set.
func cloneSecurity(s State) State {
	n := s
	n.Accounts = make(map[string]Account, len(s.Accounts))
	for id, a := range s.Accounts {
		n.Accounts[id] = a
	}
	b, _ := json.Marshal(s.Governance)
	n.Governance = nil
	_ = json.Unmarshal(b, &n.Governance)
	return n
}
func validateGovernance(s State) error {
	g := s.Governance
	if g == nil {
		return nil
	}
	b, _ := json.Marshal(g)
	if len(b) > MaxGovernanceBytes {
		return errors.New("governance state capacity")
	}
	if g.Version != 1 || g.Time <= 0 || g.Time > math.MaxInt64-60*DaySeconds || len(g.Identities) != len(s.Accounts) || g.Cases == nil || g.Rosters == nil || g.Rotations == nil || len(g.Cases) > MaxAccounts || len(g.Freezes) > 20 || len(g.Complaints) > MaxAccounts {
		return errors.New("invalid G1 metadata")
	}
	for id, i := range g.Identities {
		if _, ok := s.Accounts[id]; !ok || !identifier.MatchString(i.Operator) || i.CitizenSince <= 0 || i.CitizenSince > g.Time || i.AdminSince < 0 || i.AdminSince > g.Time || i.AdminSince > 0 && i.AdminSince < i.CitizenSince+30*DaySeconds || i.FrozenUntil < 0 || i.HeldUntil < 0 || i.FrozenUntil > g.Time+DaySeconds || i.HeldUntil > g.Time+DaySeconds {
			return errors.New("invalid G1 identity")
		}
	}
	keys := map[string]bool{}
	for _, a := range s.Accounts {
		keys[string(a.Key)] = true
	}
	for id, r := range g.Rotations {
		if _, ok := s.Accounts[id]; !ok || len(r.Key) != ed25519.PublicKeySize || keys[string(r.Key)] || r.Ready <= 0 || r.Ready > g.Time+2*DaySeconds {
			return errors.New("invalid pending rotation")
		}
		keys[string(r.Key)] = true
	}
	for _, events := range [][]SecurityEvent{g.Freezes, g.Complaints} {
		for _, e := range events {
			if _, ok := g.Identities[e.Actor]; !ok || e.At <= 0 || e.At > g.Time {
				return errors.New("invalid G1 quota event")
			}
		}
	}
	for hash, roster := range g.Rosters {
		b, _ := json.Marshal(roster)
		h := sha256.Sum256(b)
		if hex.EncodeToString(h[:]) != hash {
			return errors.New("invalid council snapshot hash")
		}
	}
	for id, c := range g.Cases {
		roster, exists := g.Rosters[c.Roster]
		if !exists {
			return errors.New("missing council snapshot")
		}
		if !hashEvidence(id) || !hashEvidence(c.Evidence) || c.Expires <= 0 || c.Expires > g.Time+3600 || len(roster) < 5 || len(roster) > MaxAccounts || !sort.StringsAreSorted(roster) {
			return errors.New("invalid containment case")
		}
		if _, ok := g.Identities[c.Target]; !ok {
			return errors.New("unknown containment target")
		}
		seen := map[string]bool{}
		ops := map[string]bool{}
		for _, v := range roster {
			i, ok := g.Identities[v]
			if !ok || seen[v] || ops[i.Operator] {
				return errors.New("invalid council roster")
			}
			seen[v] = true
			ops[i.Operator] = true
		}
		voted := map[string]bool{}
		for _, v := range c.Approvals {
			if !seen[v] || voted[v] || v == c.Target {
				return errors.New("invalid council approval")
			}
			voted[v] = true
		}
		if c.Applied != (len(c.Approvals)*2 >= len(roster)) {
			return errors.New("containment threshold mismatch")
		}
	}
	return nil
}

// Body fields must be exact lower-case names; reject JSON aliases and unused fields.
func decodeSecurity(t Transaction) (securityMessage, error) {
	var m securityMessage
	if len(t.Body) == 0 || t.Body[0] != '{' {
		return m, errors.New("G1 body must be an object")
	}
	if err := decode(t.Body, &m); err != nil {
		return m, err
	}
	var fields map[string]json.RawMessage
	_ = json.Unmarshal(t.Body, &fields)
	allowed := map[string][]string{
		"freeze_identity": {"target", "evidence"}, "open_containment": {"target", "evidence"}, "approve_containment": {"case"},
		"schedule_key_rotation": {"key", "proof"}, "cancel_key_rotation": {}, "activate_key_rotation": {},
	}
	expected, ok := allowed[t.Type]
	if !ok || len(fields) != len(expected) {
		return m, errors.New("unsupported G1 message or fields")
	}
	for _, k := range expected {
		if _, ok := fields[k]; !ok {
			return m, errors.New("noncanonical G1 message")
		}
	}
	return m, nil
}
func rotationBytes(chain, account string, key []byte) []byte {
	b, _ := json.Marshal(struct {
		Chain   string `json:"chain"`
		Account string `json:"account"`
		Key     []byte `json:"key"`
	}{chain, account, key})
	return append([]byte("DAGP/G1/KEY-POSSESSION-v1\x00"), b...)
}

// RotationProofBytes is the domain bound message signed by the new key.
func RotationProofBytes(chain, account string, key []byte) []byte {
	return rotationBytes(chain, account, key)
}
func executeSecurity(s *State, t Transaction) error {
	g := s.Governance
	if g == nil {
		return errors.New("governance disabled on G0")
	}
	m, err := decodeSecurity(t)
	if err != nil {
		return err
	}
	now := g.Time
	switch t.Type {
	case "freeze_identity":
		target, ok := g.Identities[m.Target]
		actor := g.Identities[t.Account]
		if !g.admin(t.Account, now) || actor.FrozenUntil > now || !ok || actor.Operator == target.Operator || !hashEvidence(m.Evidence) || target.FrozenUntil > now {
			return errors.New("ineligible freeze")
		}
		events := recent(g.Freezes, now)
		cap := len(g.Identities) * 2 / 100
		if cap < 3 {
			cap = 3
		}
		if cap > 20 {
			cap = 20
		}
		if len(events) >= cap || operatorCount(g, events, t.Account) >= 2 {
			return errors.New("rolling freeze quota")
		}
		// Freeze is a registration-review hold only. It never revokes civic/key rights.
		target.FrozenUntil = now + DaySeconds
		g.Identities[m.Target] = target
		g.Freezes = append(events, SecurityEvent{t.Account, now})
	case "open_containment":
		target, ok := g.Identities[m.Target]
		actor := g.Identities[t.Account]
		if !g.admin(t.Account, now) || !ok || target.AdminSince == 0 || target.HeldUntil > now || actor.Operator == target.Operator || !hashEvidence(m.Evidence) {
			return errors.New("ineligible containment complaint")
		}
		events := recent(g.Complaints, now)
		if operatorCount(g, events, t.Account) >= 1 {
			return errors.New("rolling complaint quota")
		}
		for id, c := range g.Cases {
			if c.Expires <= now {
				delete(g.Cases, id)
			} else if c.Target == m.Target {
				return errors.New("target already under review")
			}
		}
		used := map[string]bool{}
		for _, c := range g.Cases {
			used[c.Roster] = true
		}
		for hash := range g.Rosters {
			if !used[hash] {
				delete(g.Rosters, hash)
			}
		}
		if len(g.Cases) >= MaxAccounts {
			return errors.New("case capacity")
		}
		roster := []string{}
		ops := map[string]bool{}
		for id := range g.Identities {
			i := g.Identities[id]
			if i.CitizenSince <= now-30*DaySeconds && i.AdminSince > 0 && i.AdminSince <= now-2*DaySeconds {
				op := g.Identities[id].Operator
				if ops[op] {
					return errors.New("council must have independent operators")
				}
				ops[op] = true
				roster = append(roster, id)
			}
		}
		sort.Strings(roster)
		if len(events) >= len(roster) {
			return errors.New("rolling council complaint quota")
		}
		if len(roster) < 5 {
			return errors.New("insufficient mature council")
		}
		digest := sha256.Sum256(t.SignBytes())
		id := hex.EncodeToString(digest[:])
		rb, _ := json.Marshal(roster)
		rh := sha256.Sum256(rb)
		rosterID := hex.EncodeToString(rh[:])
		g.Rosters[rosterID] = roster
		g.Cases[id] = Containment{Target: m.Target, Evidence: m.Evidence, Expires: now + 3600, Roster: rosterID, Approvals: []string{}}
		g.Complaints = append(events, SecurityEvent{t.Account, now})
	case "approve_containment":
		c, ok := g.Cases[m.Case]
		if !ok || c.Applied || c.Expires <= now || !g.admin(t.Account, now) || g.Identities[t.Account].Operator == g.Identities[c.Target].Operator {
			return errors.New("ineligible containment approval")
		}
		roster := g.Rosters[c.Roster]
		n := sort.SearchStrings(roster, t.Account)
		if n == len(roster) || roster[n] != t.Account {
			return errors.New("outside frozen council")
		}
		for _, v := range c.Approvals {
			if v == t.Account {
				return errors.New("duplicate council approval")
			}
		}
		c.Approvals = append(c.Approvals, t.Account)
		sort.Strings(c.Approvals)
		if len(c.Approvals)*2 >= len(roster) {
			i := g.Identities[c.Target]
			i.HeldUntil = now + 6*3600
			g.Identities[c.Target] = i
			c.Applied = true
		}
		g.Cases[m.Case] = c
	case "schedule_key_rotation":
		if len(m.Key) != ed25519.PublicKeySize || !ed25519.Verify(m.Key, rotationBytes(s.ChainID, t.Account, m.Key), m.Proof) {
			return errors.New("invalid new key possession")
		}
		if _, ok := g.Rotations[t.Account]; ok {
			return errors.New("rotation pending")
		}
		for _, a := range s.Accounts {
			if bytes.Equal(a.Key, m.Key) {
				return errors.New("duplicate key")
			}
		}
		for _, r := range g.Rotations {
			if bytes.Equal(r.Key, m.Key) {
				return errors.New("key already reserved")
			}
		}
		g.Rotations[t.Account] = KeyRotation{Key: append([]byte(nil), m.Key...), Ready: now + 2*DaySeconds}
	case "cancel_key_rotation":
		if _, ok := g.Rotations[t.Account]; !ok {
			return errors.New("no pending rotation")
		}
		delete(g.Rotations, t.Account)
	case "activate_key_rotation":
		r, ok := g.Rotations[t.Account]
		if !ok || now < r.Ready {
			return errors.New("rotation not ready")
		}
		a := s.Accounts[t.Account]
		a.Key = append([]byte(nil), r.Key...)
		s.Accounts[t.Account] = a
		delete(g.Rotations, t.Account)
	default:
		return errors.New("unsupported G1 message")
	}
	return nil
}
func advanceTime(s *State, now int64) error {
	if s.Governance == nil {
		return nil
	}
	if now < s.Governance.Time || now > math.MaxInt64-60*DaySeconds {
		return errors.New("nonmonotonic consensus time")
	}
	s.Governance.Time = now
	return nil
}
