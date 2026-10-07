// dagp-key generates G0 keys or signs a document transaction; private keys stay in local files.
package main

import (
	"crypto/ed25519"
	"crypto/rand"
	app "dagp.net/chain/internal/app"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"os"
)

func main() {
	keypath := flag.String("key", "agent-key.json", "private key file")
	gen := flag.Bool("generate", false, "generate key (refuses overwrite)")
	chain := flag.String("chain", "dagp-local-g0", "chain ID")
	account := flag.String("account", "agent", "account ID")
	seq := flag.Uint64("sequence", 0, "account sequence")
	expiry := flag.Int64("until", 1000, "last valid height")
	body := flag.String("document", "", "document or JSON message file")
	kind := flag.String("type", "publish_document", "transaction type")
	flag.Parse()
	if *gen {
		pub, key, err := ed25519.GenerateKey(rand.Reader)
		if err != nil {
			log.Fatal(err)
		}
		b, _ := json.Marshal(key)
		f, err := os.OpenFile(*keypath, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
		if err != nil {
			log.Fatal(err)
		}
		if _, err = f.Write(b); err != nil {
			log.Fatal(err)
		}
		if err = f.Close(); err != nil {
			log.Fatal(err)
		}
		out, _ := json.Marshal(app.Account{Key: pub})
		fmt.Println(string(out))
		return
	}
	b, err := os.ReadFile(*keypath)
	if err != nil {
		log.Fatal(err)
	}
	var key ed25519.PrivateKey
	if err = json.Unmarshal(b, &key); err != nil || len(key) != ed25519.PrivateKeySize {
		log.Fatal("invalid private key")
	}
	data, err := os.ReadFile(*body)
	if err != nil {
		log.Fatal(err)
	}
	tx := app.Transaction{ChainID: *chain, Account: *account, Sequence: *seq, ValidUntil: *expiry, Type: *kind, Body: data}
	tx.Signature = ed25519.Sign(key, tx.SignBytes())
	out, _ := json.Marshal(tx)
	fmt.Println(string(out))
}
