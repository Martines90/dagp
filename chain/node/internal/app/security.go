package app

import (
	"bytes"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"math"
	"regexp"
)

// G0 consensus limits: changes require a coordinated chain upgrade, not local tuning.
const (
	MaxTransactionBytes      = 90000
	MaxBlockBytes            = 2 * 1024 * 1024
	MaxBlockTransactions     = 128
	MaxStoreBytes            = 32 * 1024 * 1024
	MaxStoreDocuments        = 4096
	MaxAccounts              = 1024
	PublishEpochBlocks       = 100
	MaxAccountEpochBytes     = 512 * 1024
	MaxAccountEpochDocuments = 16
	MaxSnapshotBytes         = 48 * 1024 * 1024
	MaxG1SnapshotBytes       = 56 * 1024 * 1024
)

var identifier = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`)

// encoding/json otherwise accepts repeated properties and case-insensitive struct aliases.
func uniqueValue(d *json.Decoder, depth int) error {
	if depth > 16 {
		return errors.New("JSON nesting limit")
	}
	token, err := d.Token()
	if err != nil {
		return err
	}
	delimiter, ok := token.(json.Delim)
	if !ok {
		return nil
	}
	switch delimiter {
	case '{':
		seen := map[string]bool{}
		for d.More() {
			k, err := d.Token()
			if err != nil {
				return err
			}
			key, ok := k.(string)
			if !ok || seen[key] {
				return errors.New("duplicate JSON property")
			}
			seen[key] = true
			if err = uniqueValue(d, depth+1); err != nil {
				return err
			}
		}
	case '[':
		for d.More() {
			if err = uniqueValue(d, depth+1); err != nil {
				return err
			}
		}
	default:
		return errors.New("unexpected JSON delimiter")
	}
	_, err = d.Token()
	return err
}
func strictJSON(b []byte) error {
	d := json.NewDecoder(bytes.NewReader(b))
	if err := uniqueValue(d, 0); err != nil {
		return err
	}
	if _, err := d.Token(); err != io.EOF {
		return errors.New("trailing JSON")
	}
	return nil
}
func validateState(s State) error {
	if !identifier.MatchString(s.ChainID) || len(s.ChainID) > 64 || s.Height < 0 || len(s.Accounts) == 0 || len(s.Accounts) > MaxAccounts || s.Documents == nil {
		return errors.New("invalid state metadata")
	}
	keys := map[string]bool{}
	for id, a := range s.Accounts {
		if !identifier.MatchString(id) || len(a.Key) != ed25519.PublicKeySize || keys[string(a.Key)] || a.PublishEpoch < 0 || a.EpochBytes < 0 || a.EpochDocuments < 0 || a.EpochBytes > MaxAccountEpochBytes || a.EpochDocuments > MaxAccountEpochDocuments {
			return errors.New("invalid or duplicate account key/usage")
		}
		keys[string(a.Key)] = true
	}
	if len(s.Documents) > MaxStoreDocuments {
		return errors.New("document count limit")
	}
	size := 0
	for id, body := range s.Documents {
		hash := sha256.Sum256(body)
		if id != hex.EncodeToString(hash[:]) || len(body) == 0 || len(body) > 65536 {
			return errors.New("document hash/size mismatch")
		}
		size += len(body)
	}
	if size > MaxStoreBytes {
		return errors.New("store capacity")
	}
	if err := validateGovernance(s); err != nil {
		return err
	}
	return validateRuntimeState(s)
}
func validBlock(txs [][]byte) bool {
	if len(txs) > MaxBlockTransactions {
		return false
	}
	size := 0
	for _, tx := range txs {
		if len(tx) > MaxTransactionBytes {
			return false
		}
		size += len(tx)
		if size > MaxBlockBytes {
			return false
		}
	}
	return true
}
func validateTransaction(s *State, raw []byte, height int64) (Transaction, error) {
	var t Transaction
	if len(raw) > MaxTransactionBytes || height < 1 || height > math.MaxInt64-1000 {
		return t, errors.New("transaction/height limit")
	}
	if err := decode(raw, &t); err != nil {
		return t, err
	}
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(raw, &fields); err != nil {
		return t, err
	}
	expected := []string{"chain_id", "account", "sequence", "valid_until_height", "type", "body", "signature"}
	if len(fields) != len(expected) {
		return t, errors.New("invalid transaction fields")
	}
	for _, key := range expected {
		if _, ok := fields[key]; !ok {
			return t, errors.New("missing or noncanonical transaction field")
		}
	}
	a, ok := s.Accounts[t.Account]
	if !ok {
		a, ok = registrationAccount(s, t)
	}
	if !ok || len(a.Key) != ed25519.PublicKeySize || t.ChainID != s.ChainID || t.Sequence != a.Sequence || a.Sequence == math.MaxUint64 || t.ValidUntil < height || t.ValidUntil > height+1000 {
		return t, errors.New("invalid account, domain, sequence or expiry")
	}
	if !ed25519.Verify(a.Key, t.SignBytes(), t.Signature) && !verifySession(s, t) {
		return t, errors.New("invalid signature")
	}
	if t.Type == "protocol" {
		next := cloneMutable(*s)
		return t, executeRuntime(&next, t, raw)
	}
	if t.Type != "publish_document" {
		if len(t.Body) > 4096 {
			return t, errors.New("G1 message size")
		}
		next := cloneSecurity(*s)
		if err := executeSecurity(&next, t); err != nil {
			return t, err
		}
		return t, validateGovernance(next)
	}
	if len(t.Body) == 0 || len(t.Body) > 65536 || s.Documents == nil {
		return t, errors.New("unsupported message or document size")
	}
	h := sha256.Sum256(t.Body)
	if _, exists := s.Documents[hex.EncodeToString(h[:])]; exists {
		return t, errors.New("document already exists")
	}
	if len(s.Documents) >= MaxStoreDocuments {
		return t, errors.New("store document quota")
	}
	size := len(t.Body)
	for _, body := range s.Documents {
		size += len(body)
	}
	if size > MaxStoreBytes {
		return t, errors.New("store byte quota")
	}
	epoch := (height-1)/PublishEpochBlocks + 1
	usedBytes, usedDocuments := int64(0), int64(0)
	if a.PublishEpoch == epoch {
		usedBytes, usedDocuments = a.EpochBytes, a.EpochDocuments
	}
	if usedBytes+int64(len(t.Body)) > MaxAccountEpochBytes || usedDocuments >= MaxAccountEpochDocuments {
		return t, errors.New("account publication quota")
	}
	return t, nil
}
