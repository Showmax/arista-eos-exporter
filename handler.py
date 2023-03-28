import logging
import re
import socket

import falcon

from collector import AristaMetricsCollector

from prometheus_client.exposition import CONTENT_TYPE_LATEST
from prometheus_client.exposition import generate_latest


class metricHandler:
    def __init__(self, config):
        self._config = config
        self._targets = None

    def handle_modules(self, modules):
        if not modules:
            return False
        module_functions = []
        modules = modules.split(",")
        for module in modules:
            if module == "all":
                return False
            elif module == "memory":
                module.functions

    def on_get(self, req, resp):
        target_names = req.get_param("target")
        if target_names:
            self._targets = target_names.split(",")
        modules = req.get_param("modules")
        if modules:
            if re.match(r"^([a-zA-Z]+)(,[a-zA-Z]+)*$", modules):
                self._config["module_names"] = modules
            else:
                msg = "Invalid modules specified"
                logging.error(msg)
                resp.status = falcon.HTTP_400
                resp.text = msg
                return
        else:
            msg = "No modules specified"
            logging.error(msg)
            resp.status = falcon.HTTP_400
            resp.text = msg
            return

        resp.set_header("Content-Type", CONTENT_TYPE_LATEST)

        if self._targets and self._targets[0] == "all":
           if 'targets' in self._config:
               self._targets = self._config['targets']

        if not self._targets:
            msg = "No target parameter provided!"
            logging.error(msg)
            resp.status = falcon.HTTP_400
            resp.text = msg

        else:
            for target in self._targets:
                try:
                    socket.getaddrinfo(target, None)
                except socket.gaierror as e:
                    msg = f"Target '{target}' does not exist in DNS: {e}"
                    logging.error(msg)
                    resp.status = falcon.HTTP_400
                    resp.text = msg

        if not resp.text:
            registry = AristaMetricsCollector(self._config, targets=self._targets)

            collected_metric = generate_latest(registry)
            resp.text = collected_metric
