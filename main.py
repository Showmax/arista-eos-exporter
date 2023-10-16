#!/usr/bin/env python3

import argparse
import logging
import socket
import sys
import yaml
import falcon
from handler import MetricHandler
from wsgiref import simple_server

class IPv6WSGIServer(simple_server.WSGIServer):
    address_family = socket.AF_INET6

def determine_server_class(addr, logger):
    try:
        socket.inet_pton(socket.AF_INET, addr)
        return simple_server.WSGIServer
    except OSError:
        try:
            socket.inet_pton(socket.AF_INET6, addr)
            return IPv6WSGIServer
        except OSError:
            logger.error(f"Invalid address: {addr}")
            sys.exit(1)

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
        if "listen_addr" not in config:
            config["listen_addr"] = "0.0.0.0"
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
    server_class = determine_server_class(config["listen_addr"], logger)

    api = falcon.App()
    api.add_route("/arista", MetricHandler(config=config))
    try:
        httpd = simple_server.make_server(config["listen_addr"], config["listen_port"], api, server_class=server_class)
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.server_close()
        logger.info("Stopping Arista eAPI Prometheus Server")
    except Exception as e:
        logger.error(f"Error: {e}")

if __name__ == "__main__":
    main()
