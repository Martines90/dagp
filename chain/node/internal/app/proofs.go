package app

import (
	"bytes"
	"encoding/json"
	"errors"
	"sort"

	cmted "github.com/cometbft/cometbft/crypto/ed25519"
	"github.com/cometbft/cometbft/crypto/merkle"
	cmtjson "github.com/cometbft/cometbft/libs/json"
	cmttypes "github.com/cometbft/cometbft/types"
)

type PeerValidator struct {
	Key   []byte `json:"key"`
	Power int64  `json:"power"`
}
type PeerTrust struct {
	CodeHash   string          `json:"code_hash"`
	Validators []PeerValidator `json:"validators"`
}
type PeerProof struct {
	Chain  string          `json:"chain"`
	Header json.RawMessage `json:"header"`
	Commit json.RawMessage `json:"commit"`
	Key    string          `json:"key"`
	Value  json.RawMessage `json:"value"`
	Proof  merkle.Proof    `json:"proof"`
}

func exportLeaf(key string, value json.RawMessage) []byte {
	b, _ := json.Marshal(struct {
		Key   string          `json:"key"`
		Value json.RawMessage `json:"value"`
	}{key, value})
	return b
}
func merkleState(s State) ([]string, [][]byte) {
	values := map[string]json.RawMessage{}
	metadata := s
	metadata.Accounts = nil
	metadata.Documents = nil
	r := *s.Runtime
	r.Graph = nil
	r.Exports = nil
	metadata.Runtime = &r
	values["metadata"], _ = json.Marshal(metadata)
	values["runtime_graph"] = s.Runtime.Graph
	for id, a := range s.Accounts {
		values["account/"+id], _ = json.Marshal(a)
	}
	for id, d := range s.Documents {
		values["document/"+id], _ = json.Marshal(d)
	}
	for id, v := range s.Runtime.Exports {
		values["export/"+id] = v
	}
	keys := make([]string, 0, len(values))
	for k := range values {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	leaves := make([][]byte, len(keys))
	for i, k := range keys {
		leaves[i] = exportLeaf(k, values[k])
	}
	return keys, leaves
}
func runtimeRoot(s State) []byte {
	_, leaves := merkleState(s)
	return merkle.HashFromByteSlices(leaves)
}
func exportProof(s State, key string) (json.RawMessage, *merkle.Proof, error) {
	value, ok := s.Runtime.Exports[key]
	if !ok {
		return nil, nil, errors.New("unknown committed export")
	}
	keys, leaves := merkleState(s)
	_, proofs := merkle.ProofsFromByteSlices(leaves)
	index := sort.SearchStrings(keys, "export/"+key)
	return value, proofs[index], nil
}
func validatorTrust(p PeerTrust) (*cmttypes.ValidatorSet, error) {
	if !hashEvidence(p.CodeHash) || len(p.Validators) < 7 || len(p.Validators) > 100 {
		return nil, errors.New("bounded peer charter and seven validators required")
	}
	seen := map[string]bool{}
	vals := make([]*cmttypes.Validator, len(p.Validators))
	for i, v := range p.Validators {
		if len(v.Key) != 32 || seen[string(v.Key)] || v.Power < 1 || v.Power > 1000000000 {
			return nil, errors.New("invalid peer validator")
		}
		seen[string(v.Key)] = true
		vals[i] = cmttypes.NewValidator(cmted.PubKey(v.Key), v.Power)
	}
	return cmttypes.NewValidatorSet(vals), nil
}
func verifyPeer(s *State, raw json.RawMessage) (map[string]string, error) {
	var proof PeerProof
	if err := decode(raw, &proof); err != nil {
		return nil, err
	}
	trust, ok := s.Runtime.Peers[proof.Chain]
	if !ok || proof.Chain == s.ChainID {
		return nil, errors.New("untrusted peer chain")
	}
	vals, err := validatorTrust(trust)
	if err != nil {
		return nil, err
	}
	var header cmttypes.Header
	var commit cmttypes.Commit
	if err = cmtjson.Unmarshal(proof.Header, &header); err != nil {
		return nil, err
	}
	if err = cmtjson.Unmarshal(proof.Commit, &commit); err != nil {
		return nil, err
	}
	if header.ValidateBasic() != nil || header.ChainID != proof.Chain || header.Height < 2 || header.Time.Unix() > s.Runtime.Time+120 || !bytes.Equal(header.ValidatorsHash, vals.Hash()) || !bytes.Equal(header.NextValidatorsHash, vals.Hash()) || !bytes.Equal(commit.BlockID.Hash, header.Hash()) {
		return nil, errors.New("invalid peer checkpoint domain or validator set")
	}
	if err = vals.VerifyCommitLightAllSignatures(proof.Chain, commit.BlockID, header.Height, &commit); err != nil {
		return nil, errors.New("peer checkpoint lacks valid supermajority")
	}
	if proof.Proof.Total > 100000 || len(proof.Proof.Aunts) > 32 || len(proof.Value) > 32768 || len(proof.Key) > 256 {
		return nil, errors.New("peer export proof bound")
	}
	if proof.Proof.Verify(header.AppHash, exportLeaf("export/"+proof.Key, proof.Value)) != nil {
		return nil, errors.New("invalid committed peer export proof")
	}
	var domain struct {
		CodeHash string `json:"code_hash"`
		Chain    string `json:"chain"`
	}
	if json.Unmarshal(proof.Value, &domain) != nil || domain.CodeHash != trust.CodeHash || domain.Chain != proof.Chain {
		return nil, errors.New("peer export lacks pinned code and chain commitment")
	}
	return map[string]string{"peer_chain": proof.Chain, "peer_key": proof.Key, "peer_value": string(proof.Value), "peer_code_hash": trust.CodeHash}, nil
}
