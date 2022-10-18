// Copyright 2022-, Semiotic AI, Inc.
// SPDX-License-Identifier: Apache-2.0

package main

import (
	"bufio"
	"fmt"
	"io"
	"os"
	"os/exec"
	"os/signal"
	"sync"
	"syscall"
	"time"

	"github.com/rs/zerolog"
	"github.com/rs/zerolog/log"

	"github.com/buger/jsonparser"
	"github.com/cristalhq/aconfig"

	rabbitmq "github.com/wagslane/go-rabbitmq"
)

type Config struct {
	Rabbitmq struct {
		Host         string `required:"true" usage:"Hostname of the RabbitMQ server used for queuing the GQL logs.\n(env: RABBITMQ_HOST)"`
		ExchangeName string `default:"gql_logs" usage:"Name of the RabbitMQ exchange query-node logs are pushed to.\n(env: RABBITMQ_EXCHANGE_NAME)"`
		Username     string `default:"guest" usage:"Username to use for the GQL logs RabbitMQ queue.\n(env: RABBITMQ_USERNAME)"`
		Password     string `default:"guest" usage:"Password to use for the GQL logs RabbitMQ queue.\n(env: RABBITMQ_PASSWORD)"`
	}
	MaxCacheLines int    `default:"100" usage:"Maximum number of log lines to cache locally.\n(env: MAX_CACHE_LINES)"`
	LogLevel      string `default:"warn" usage:"Log level. Must be \"trace\", \"debug\", \"info\", \"warn\", \"error\", \"fatal\" or \"panic\".\n(env: LOG_LEVEL)"`
}

// To accomodate long log lines. Lines longer that this will be discarded.
const SCANNER_BUFFER_SIZE = 1048576 // 2^20, or 1MiB

func main() {
	/*
		Initialize config and logger
	*/

	zerolog.TimeFieldFormat = time.RFC3339Nano

	var cfg Config
	loader := aconfig.LoaderFor(&cfg, aconfig.Config{
		SkipDefaults: false,
		SkipFiles:    true,
		SkipEnv:      false,
		SkipFlags:    false,
		EnvPrefix:    "",
		FlagPrefix:   "",
	})
	if err := loader.Load(); err != nil {
		log.Fatal().Err(err).Msg("Error while loading config.")
	}

	log_level, err := zerolog.ParseLevel(cfg.LogLevel)
	if err != nil {
		log.Fatal().Err(err).Msg("Error while parsing log level.")
	}
	zerolog.SetGlobalLevel(log_level)

	/*
		Start the indexer-service and the readers / sender coroutines
	*/

	var reader_waitgroup sync.WaitGroup
	var sender_waitgroup sync.WaitGroup

	cmd := exec.Command("node", "dist/index.js", "start")
	cmd.Dir = "/opt/indexer/packages/indexer-service"

	stderr, err := cmd.StderrPipe()
	if err != nil {
		log.Fatal().Err(err).Msg("Error while creating the indexer-service output stderr pipe.")
	}

	stdout, err := cmd.StdoutPipe()
	if err != nil {
		log.Fatal().Err(err).Msg("Error while creating the indexer-service output stdout pipe.")
	}

	logs_chan := make(chan string, cfg.MaxCacheLines)

	reader_waitgroup.Add(2)
	go reader(&stdout, logs_chan, &reader_waitgroup)
	go reader(&stderr, logs_chan, &reader_waitgroup)

	sender_waitgroup.Add(1)
	go sender(logs_chan, &sender_waitgroup, cfg)

	// Start command
	err = cmd.Start()
	if err != nil {
		log.Fatal().Err(err).Msg("Error while starting indexer-service.")
	} else {
		log.Debug().Int("pid", cmd.Process.Pid).Msg("Started the indexer-service process.")
	}
	// Log the indexer-service exit status
	indexer_service_done := make(chan struct{})
	go func() {
		err := cmd.Wait()
		if err != nil {
			log.Error().Err(err).Int("ExitCode", cmd.ProcessState.ExitCode()).
				Msg("indexer-service exited with an error.")
		} else {
			log.Info().Int("ExitCode", cmd.ProcessState.ExitCode()).Msg("indexer-service exited.")
		}
		close(indexer_service_done)
	}()
	defer func() {
		// If the indexer-service process is still running
		if cmd.ProcessState == nil {
			err := cmd.Process.Kill()
			log.Debug().Msg("Killing the indexer-service process...")
			if err != nil {
				log.Error().Err(err).Msg("Error while killing the indexer-service process.")
			}
		}
	}()

	/*
		Handle graceful termination signals by relaying SIGTERM to the indexer-service
	*/

	sigs := make(chan os.Signal, 1)
	signal.Notify(sigs, syscall.SIGINT, syscall.SIGTERM)
	go func() {
		sig := <-sigs
		log.Warn().Str("signal", sig.String()).Msg("Received termination signal.")

		err := cmd.Process.Signal(syscall.SIGTERM)
		if err != nil {
			log.Error().Err(err).Msg("Error while sending SIGTERM to the indexer-service.")
		}

		select {
		case <-indexer_service_done:
		// timeout after 10 seconds and send SIGKILL to indexer-service
		case <-time.After(10 * time.Second):
			err := cmd.Process.Kill()
			log.Debug().Msg("Killing the indexer-service process...")
			if err != nil {
				log.Error().Err(err).Msg("Error while killing the indexer-service process.")
			}
		}
	}()

	/*
		Shutdown on indexer-service stdout/stderr closing
	*/

	reader_waitgroup.Wait()
	close(logs_chan)

	sender_waitgroup.Wait()
}

func reader(readcloser *io.ReadCloser, log_lines chan string, wg *sync.WaitGroup) {
	defer wg.Done()

	scanner := bufio.NewScanner(*readcloser)
	scanner.Buffer(make([]byte, SCANNER_BUFFER_SIZE), SCANNER_BUFFER_SIZE-1)

	// Automatically resume the scanner on error. Break only on EOF.
	for {
		for scanner.Scan() {
			select {
			case log_lines <- scanner.Text():
				log.Debug().Msg("Added log line to cache.")
			default:
				log.Error().Msg("Local cache full. Log line dropped.")
			}
		}
		if scanner.Err() != nil {
			log.Error().Err(scanner.Err()).Msg("stdout/stderr reader error.")
		} else {
			// EOF
			break
		}
	}
}

func sender(log_lines chan string, wg *sync.WaitGroup, cfg Config) {
	defer wg.Done()

	/*
		Set up RabbitMQ
	*/

	publisher, err := rabbitmq.NewPublisher(
		fmt.Sprintf(
			"amqp://%s:%s@%s",
			cfg.Rabbitmq.Username,
			cfg.Rabbitmq.Password,
			cfg.Rabbitmq.Host),
		rabbitmq.Config{},
		rabbitmq.WithPublisherOptionsLogging,
	)
	if err != nil {
		log.Fatal().Err(err).Msg("Error while initializing RabbitMQ publisher.")
	}
	defer func() {
		err := publisher.Close()
		if err != nil {
			log.Error().Err(err).Msg("Error while closing RabbitMQ publisher.")
		}
	}()

	returns := publisher.NotifyReturn()
	go func() {
		for r := range returns {
			log.Debug().Str("body", string(r.Body)).Msg("Message returned from RabbitMQ server")
		}
	}()

	confirmations := publisher.NotifyPublish()
	go func() {
		for c := range confirmations {
			log.Debug().Uint64("DeliveryTag", c.DeliveryTag).Bool("Ack", c.Ack).
				Msg("Message confirmed from RabbitMQ server.")
		}
	}()

	/*
		Consume log lines
	*/

	for value := range log_lines {

		msg, _ := jsonparser.GetString([]byte(value), "msg")

		if msg == "Done executing paid query" {
			err = publisher.Publish(
				[]byte(value),
				[]string{""},
				rabbitmq.WithPublishOptionsContentType("application/json"),
				rabbitmq.WithPublishOptionsExchange(cfg.Rabbitmq.ExchangeName),
				rabbitmq.WithPublishOptionsMandatory,
			)
			if err != nil {
				log.Error().Err(err).Msg("Log entry dropped.")
			} else {
				log.Debug().Str("val", value).Msg("Sent log entry to RabbitMQ.")
			}
		} else {
			// Log entries that do not contain query timings are spit back out to STDOUT
			fmt.Println(value)
		}
	}
}
