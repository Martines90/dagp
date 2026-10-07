package app

import (
	"encoding/json"
	"strings"
	"testing"
	"time"

	cmted "github.com/cometbft/cometbft/crypto/ed25519"
	"github.com/cometbft/cometbft/crypto/merkle"
	cmtjson "github.com/cometbft/cometbft/libs/json"
	cmtproto "github.com/cometbft/cometbft/proto/tendermint/types"
	cmtversion "github.com/cometbft/cometbft/proto/tendermint/version"
	cmttypes "github.com/cometbft/cometbft/types"
	"github.com/cometbft/cometbft/version"
)

// Synthetic checkpoints use real validator signatures and CometBFT verification.
// They test the proof boundary; they are not evidence of a deployed peer network.
func TestG2PeerProofQuorumAndCommitment(t *testing.T) {
	trust := PeerTrust{CodeHash: strings.Repeat("a", 64)}
	keys := map[string]cmted.PrivKey{}
	for i := 0; i < 7; i++ {
		key := cmted.GenPrivKey()
		pub := key.PubKey()
		trust.Validators = append(trust.Validators, PeerValidator{Key: pub.Bytes(), Power: 1})
		keys[string(pub.Address())] = key
	}
	vals, err := validatorTrust(trust)
	if err != nil {
		t.Fatal(err)
	}
	value, _ := json.Marshal(map[string]any{"chain": "source", "root": "cohort", "size": 100, "code_hash": trust.CodeHash})
	root, proofs := merkle.ProofsFromByteSlices([][]byte{exportLeaf("export/population/cohort", value), exportLeaf("other", json.RawMessage(`1`))})
	stamp := time.Unix(1800000000, 0)
	header := cmttypes.Header{Version: cmtversion.Consensus{Block: version.BlockProtocol}, ChainID: "source", Height: 2, Time: stamp, ValidatorsHash: vals.Hash(), NextValidatorsHash: vals.Hash(), AppHash: root, ProposerAddress: vals.Validators[0].Address}
	block := cmttypes.BlockID{Hash: header.Hash(), PartSetHeader: cmttypes.PartSetHeader{Total: 1, Hash: make([]byte, 32)}}
	commit := cmttypes.Commit{Height: 2, BlockID: block, Signatures: make([]cmttypes.CommitSig, 7)}
	for i, v := range vals.Validators {
		vote := cmttypes.Vote{Type: cmtproto.PrecommitType, Height: 2, BlockID: block, Timestamp: stamp, ValidatorAddress: v.Address, ValidatorIndex: int32(i)}
		vote.Signature, err = keys[string(v.Address)].Sign(cmttypes.VoteSignBytes("source", vote.ToProto()))
		if err != nil {
			t.Fatal(err)
		}
		commit.Signatures[i] = vote.CommitSig()
	}
	headerJSON, _ := cmtjson.Marshal(header)
	commitJSON, _ := cmtjson.Marshal(commit)
	proof := PeerProof{Chain: "source", Header: headerJSON, Commit: commitJSON, Key: "population/cohort", Value: value, Proof: *proofs[0]}
	state := State{ChainID: "destination", Runtime: &RuntimeState{Time: stamp.Unix(), Peers: map[string]PeerTrust{"source": trust}}}
	verify := func(p PeerProof) error { raw, _ := json.Marshal(p); _, err := verifyPeer(&state, raw); return err }
	if err := verify(proof); err != nil {
		t.Fatal("valid proof", err)
	}
	t.Run("no supermajority", func(t *testing.T) {
		bad := proof
		weak := commit
		weak.Signatures = append([]cmttypes.CommitSig(nil), commit.Signatures...)
		for i := 4; i < 7; i++ {
			weak.Signatures[i] = cmttypes.NewCommitSigAbsent()
		}
		bad.Commit, _ = cmtjson.Marshal(weak)
		if verify(bad) == nil {
			t.Fatal("accepted 4/7")
		}
	})
	t.Run("export substitution", func(t *testing.T) {
		bad := proof
		bad.Value = json.RawMessage(`{"chain":"source","root":"attacker","size":100}`)
		if verify(bad) == nil {
			t.Fatal("accepted tampered export")
		}
	})
	t.Run("export domain", func(t *testing.T) {
		bad := proof
		bad.Key = "identity/victim"
		if verify(bad) == nil {
			t.Fatal("accepted another export key")
		}
	})
	t.Run("chain domain", func(t *testing.T) {
		bad := proof
		bad.Chain = "untrusted"
		if verify(bad) == nil {
			t.Fatal("accepted untrusted chain")
		}
	})
	t.Run("future checkpoint", func(t *testing.T) {
		state.Runtime.Time = stamp.Unix() - 121
		if verify(proof) == nil {
			t.Fatal("accepted future checkpoint")
		}
		state.Runtime.Time = stamp.Unix()
	})
}
