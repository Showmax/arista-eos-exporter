#!/usr/bin/env python3

import argparse
import logging
import sys
import yaml
import falcon
from handler import MetricHandler
from gunicorn.app.base import BaseApplication
from pathlib import Path

class GunicornWebserver(BaseApplication):
    def __init__(self, app, host, port, workers, certfile=None, keyfile=None, cafile=None):
        self.application = app
        self.host = host
        self.port = port
        self.workers = workers
        self.certfile = certfile
        self.keyfile = keyfile
        self.cafile = cafile
        super().__init__()

    def load_config(self):
        self.cfg.set("bind", f"{self.host}:{self.port}")
        self.cfg.set("workers", self.workers)
        if self.certfile and self.keyfile:
            self.cfg.set("certfile", self.certfile)
            self.cfg.set("keyfile", self.keyfile)
        if self.cafile:
            self.cfg.set("ca_certs", self.cafile)

    def load(self):
        return self.application

def setup_logging(config):
    logger = logging.getLogger()
    log_level = config.get("loglevel", "INFO").upper()
    logger.setLevel(log_level)
    format = "%(asctime)-15s %(process)d %(levelname)s %(filename)s:%(lineno)d %(message)s"
    logging.basicConfig(stream=sys.stdout, format=format)
    return logger

def load_config(filename):
    try:
        with open(filename, 'r') as stream:
            config = yaml.safe_load(stream)

        if "web_listen_address" not in config:
            config["web_listen_address"] = "::"

        if config.get("disable_certificate_validation", False) != True:
            raise ValueError(
                "Certificate validation is not supported by pyeapi library. Please specify disable_certificate_validation: true in your configuration file. Upstream issue: https://github.com/arista-eosplus/pyeapi/issues/174"
            )

        return config
    except Exception as e:
        logging.error(f"Failed to load configuration: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", help="Specify config yaml file", metavar="FILE", default="config.yml")
    args = parser.parse_args()

    config = load_config(args.config)
    logger = setup_logging(config)

    api = falcon.App()
    api.add_route("/arista", MetricHandler(config=config))

    host = config.get("web_listen_address", "::")
    port = config.get("web_listen_port", 9120)
    workers = config.get("web_workers", 4)
    certfile = config.get("web_cert_file")
    keyfile = config.get("web_key_file")
    cafile = config.get("web_ca_file")

    if not certfile or not keyfile:
        logger.warning("Warning: either web_cert_file or web_key_file is missing. Falling back to HTTP.")

    logger.info(f"Starting Arista eAPI Prometheus Server on {host}:{port} with {workers} workers...")

    application = GunicornWebserver(api, host, port, workers, certfile, keyfile, cafile)
    application.run()

if __name__ == "__main__":
    main()
