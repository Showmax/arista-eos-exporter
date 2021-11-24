#!/usr/bin/env python3

import argparse
import logging
import socket
import sys
import yaml

import falcon
from handler import metricHandler
from wsgiref import simple_server


def falcon_app(config, logger, port=9200, addr='0.0.0.0'):
    logger.info(f'Starting Arista eAPI exporter on Port {addr}:{port}')
    api = falcon.App()
    api.add_route(
        '/arista',
        metricHandler(config=config)
    )

    try:
        httpd = simple_server.make_server(addr, port, api)
    except Exception as e:
        logger.error(f"Couldn't start Server: {e}")
        return 1

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.server_close()
        logger.info('Stopping Arista eAPI Prometheus Server')


def main():
    # command line options
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-c', '--config',
        help='Specify config yaml file',
        metavar='FILE',
        required=False,
        default='config.yml')
    args = parser.parse_args()

    # get the config
    try:
        with open(args.config, 'r') as stream:
            config = yaml.safe_load(stream)
    except FileNotFoundError:
        logging.error(f'File not found: {args.config}')
        return 1
    if 'listen_addr' not in config:
        config['listen_addr'] = '0.0.0.0'

    if 'disable_certificate_validation' not in config:
        config['disable_certificate_validation'] = False
    if config['disable_certificate_validation'] is not True:
        logging.error(('Certificate validation is not supported by pyeapi'
                       'library. Please specify '
                       'disable_certificate_validation: true in your '
                       'configuration file. Upstream issue: '
                       'https://github.com/arista-eosplus/pyeapi/issues/174'))
        return 1

    # enable logging
    logger = logging.getLogger()
    if config['loglevel']:
        logger.setLevel(logging.getLevelName(config['loglevel'].upper()))
    else:
        logger.setLevel('INFO')

    format = ('%(asctime)-15s %(process)d %(levelname)s '
              '%(filename)s:%(lineno)d %(message)s')
    logging.basicConfig(stream=sys.stdout, format=format)

    falcon_app(config, logger,
               port=config['listen_port'],
               addr=config['listen_addr'])


if __name__ == '__main__':
    main()
