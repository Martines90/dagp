package app

import (
	"crypto/ed25519"
	"encoding/json"
	"errors"
)

// Join requests authorize an invitation for exactly this chain/account/labels.
// They confer no citizenship; the later challenge and admission are separate.
type JoinRequest struct {
	ChainID   string `json:"chain_id"`
	Account   string `json:"account"`
	Operator  string `json:"operator"`
	Family    string `json:"family"`
	Key       []byte `json:"key"`
	Signature []byte `json:"signature"`
}

func (r JoinRequest) SignBytes() []byte {
	r.Signature = nil
	b, _ := json.Marshal(r)
	return append([]byte("DAGP/SEED/JOIN-v1\x00"), b...)
}
func VerifyJoinRequest(raw []byte, chain string) (JoinRequest, error) {
	var r JoinRequest
	if len(raw) > 4096 {
		return r, errors.New("join request size")
	}
	if err := decode(raw, &r); err != nil {
		return r, err
	}
	var fields map[string]json.RawMessage
	_ = json.Unmarshal(raw, &fields)
	if len(fields) != 6 {
		return r, errors.New("exact join fields required")
	}
	for _, name := range []string{"chain_id", "account", "operator", "family", "key", "signature"} {
		if _, ok := fields[name]; !ok {
			return r, errors.New("canonical join fields required")
		}
	}
	if r.ChainID != chain || !identifier.MatchString(r.Account) || !identifier.MatchString(r.Operator) || !identifier.MatchString(r.Family) || len(r.Key) != 32 || !ed25519.Verify(r.Key, r.SignBytes(), r.Signature) {
		return r, errors.New("invalid join signature or domain")
	}
	return r, nil
}
