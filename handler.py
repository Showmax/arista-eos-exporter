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
        self._target = None

    def handle_modules(self, modules):
        if not modules:
            return False
        module_functions = []
        modules = modules.split(',')
        for module in modules:
            if module == 'all':
                return False
            elif module == 'memory':
                module.functions

    def on_get(self, req, resp):
        self._target = req.get_param('target')
        modules = req.get_param('modules')
        if modules:
            if re.match(r"^([a-zA-Z]+)(,[a-zA-Z]+)*$", modules):
                self._config['module_names'] = modules
            else:
                msg = 'Invalid modules specified'
                logging.error(msg)
                resp.status = falcon.HTTP_400
                resp.body = msg
                return

        resp.set_header('Content-Type', CONTENT_TYPE_LATEST)
        if not self._target:
            msg = 'No target parameter provided!'
            logging.error(msg)
            resp.status = falcon.HTTP_400
            resp.body = msg

        try:
            socket.getaddrinfo(self._target, None)
        except socket.gaierror as e:
            msg = f'Target does not exist in DNS: {e}'
            logging.error(msg)
            resp.status = falcon.HTTP_400
            resp.body = msg

        else:
            registry = AristaMetricsCollector(
                self._config,
                target=self._target
                )

            collected_metric = generate_latest(registry)
            resp.body = collected_metric
