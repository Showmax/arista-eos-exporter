#!/usr/bin/env python3

import logging
import re
import socket
import falcon
from collector import AristaMetricsCollector
from prometheus_client.exposition import CONTENT_TYPE_LATEST, generate_latest

class MetricHandler:
    def __init__(self, config):
        self._config = config

    def validate_modules(self, modules):
        if not modules or re.match(r"^([a-zA-Z]+)(,[a-zA-Z]+)*$", modules):
            return True
        logging.error("Invalid modules specified")
        return False

    def on_get(self, req, resp):
        target = req.get_param("target")
        modules = req.get_param("modules")
 
        if modules and not self.validate_modules(modules):
            resp.status = falcon.HTTP_400
            resp.body = "Invalid modules specified"
            return

        resp.set_header("Content-Type", CONTENT_TYPE_LATEST)

        if not target:
            resp.status = falcon.HTTP_400
            resp.body = "No target parameter provided!"
            return

        try:
            socket.getaddrinfo(target, None)
        except socket.gaierror as e:
            resp.status = falcon.HTTP_400
            resp.body = f"Target does not exist in DNS: {e}"
            return

        registry = AristaMetricsCollector(self._config, target=target)
        resp.body = generate_latest(registry)
