package main

import (
	app "dagp.net/chain/internal/app"
	"flag"
	"github.com/cometbft/cometbft/abci/server"
	cmtlog "github.com/cometbft/cometbft/libs/log"
	"log"
	"os"
	"os/signal"
	"syscall"
)

func main() {
	path := flag.String("state", "data/application.json", "state file")
	addr := flag.String("listen", "tcp://127.0.0.1:26658", "ABCI socket")
	python := flag.String("python", "python3", "Python 3.11+ interpreter for opt-in G2 governance")
	runtimePath := flag.String("governance-runtime", "", "pinned governance runtime.py path (required for G2)")
	flag.Parse()
	if *runtimePath != "" {
		app.ConfigureRuntime(*python, *runtimePath)
	}
	a, err := app.Open(*path)
	if err != nil {
		log.Fatal(err)
	}
	s, err := server.NewServer(*addr, "socket", a)
	if err != nil {
		log.Fatal(err)
	}
	s.SetLogger(cmtlog.NewTMLogger(os.Stderr))
	if err = s.Start(); err != nil {
		log.Fatal(err)
	}
	ch := make(chan os.Signal, 1)
	signal.Notify(ch, os.Interrupt, syscall.SIGTERM)
	<-ch
	if err = s.Stop(); err != nil {
		log.Print(err)
	}
}
