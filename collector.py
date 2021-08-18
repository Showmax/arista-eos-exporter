from prometheus_client.core import GaugeMetricFamily, InfoMetricFamily

import logging
import os
import time

import pyeapi
import ssl

PORT_STATS_NAMES = [
    'inBroadcastPkts',
    'inDiscards',
    'inMulticastPkts',
    'inOctets',
    'inUcastPkts',
    'outBroadcastPkts',
    'outDiscards',
    'outMulticastPkts',
    'outOctets',
    'outUcastPkts',
]


class AristaMetricsCollector(object):
    def __init__(self, config, target):
        self._username = os.getenv('ARISTA_USERNAME', config['username'])
        self._password = os.getenv('ARISTA_PASSWORD', config['password'])
        self._protocol = config['protocol'] or 'https'
        self._timeout = config['timeout']
        self._target = target
        self._labels = {}
        self._switch_up = 0
        self._responsetime = 0
        self._memtotal = 0
        self._memfree = 0
        self._connection = False
        self._interfaces = False
        self._module_names = False
        if 'module_names' in config:
            self._module_names = config['module_names']
        self._scrape_durations = GaugeMetricFamily(
                'arista_scrape_duration_seconds',
                'Duration of a collector scrape.',
                )

    def add_scrape_duration(self, module_name, duration):
        self._scrape_durations.add_sample(
                'arista_scrape_duration_seconds',
                value=duration,
                labels=({'collector': module_name}),
                )

    def get_connection(self):
        # set the default timeout
        logging.debug(f'Setting timeout to {self._timeout}')
        if not self._connection:
            logging.info(f'Connecting to switch {self._target}')
            self._connection = pyeapi.connect(transport=self._protocol,
                                              host=self._target,
                                              username=self._username,
                                              password=self._password,
                                              timeout=self._timeout)
        return self._connection

    def switch_command(self, command):
        switch_result = ''

        connection = self.get_connection()

        try:
            logging.debug(f'Running command {command}')
            switch_result = connection.execute([command])
        except pyeapi.eapilib.ConnectionError as pyeapi_connect_except:
            self._connection = False
            logging.error(('PYEAPI Client Connection Exception: '
                           f'{pyeapi_connect_except}'))
        except pyeapi.eapilib.CommandError as pyeapi_command_except:
            self._connection = False
            logging.error(('PYEAPI Client Command Exception: '
                           f'{pyeapi_command_except}'))
        finally:
            return switch_result

    def _get_labels(self):
        start = time.time()
        # Get the switch info for the labels
        switch_info = self.switch_command(command='show version')
        try:
            si_res = switch_info['result'][0]
        except Exception as e:
            logging.debug(f'No result from switch {self._target}: {e}')
            labels_switch = {'model': 'unknown', 'serial': 'unknown'}
            self._switch_up = 0
        else:
            logging.debug(f'Received a result from switch {self._target}')
            labels_switch = {
                    'model': si_res['modelName'],
                    'serial': si_res['serialNumber'],
                    'version': si_res['version']
            }
            self._memtotal = si_res['memTotal']
            self._memfree = si_res['memFree']
            self._switch_up = 1

        end = time.time()
        self._responsetime = end - start
        self.add_scrape_duration('base', self._responsetime)
        self._labels.update(labels_switch)

    def collect_memory(self):
        # Export the memory usage data
        yield GaugeMetricFamily('arista_mem_total', 'Total memory available',
                                value=self._memtotal)
        yield GaugeMetricFamily('arista_mem_free', 'Total memory free',
                                value=self._memfree)

    def collect_tcam(self):
        # Get the tcam usage data
        switch_tcam = self.switch_command(command='show hardware capacity')

        if switch_tcam:
            used_metrics = GaugeMetricFamily('arista_tcam_used',
                                             'TCAM Usage Data')
            total_metrics = GaugeMetricFamily('arista_tcam_total',
                                              'TCAM Capacity')
            for entry in switch_tcam['result'][0]['tables']:
                try:
                    labels = ({'table': entry['table'],
                               'chip': entry['chip'],
                               'feature': entry['feature']})
                    logging.debug((f'Adding: table={entry["table"]} '
                                   f'value={entry["used"]} '
                                   f'labels={labels}'))
                    used_metrics.add_sample('arista_tcam_used',
                                            value=entry['used'],
                                            labels=labels)
                    total_metrics.add_sample('arista_tcam_total',
                                             value=entry['maxLimit'],
                                             labels=labels)
                except KeyError:
                    logging.error('KeyError in switch_tcam entries')
                    continue

            yield total_metrics
            yield used_metrics

    def collect_port(self):
        command = 'show interfaces'
        port_interfaces = self.switch_command(command)
        port_stats = {k: GaugeMetricFamily(
                             f'arista_port_{k}',
                             f'Port stats {k}',
                             labels=['device', 'description', 'mac', 'mtu'])
                      for k in PORT_STATS_NAMES}
        port_admin_up = GaugeMetricFamily('arista_admin_up',
                                          'Value 1 if port is not shutdown',
                                          labels=['device', 'description'])
        port_l2_up = GaugeMetricFamily('arista_l2_up',
                                       'Value 1 if port is connected',
                                       labels=['device', 'description'])
        port_bandwidth = GaugeMetricFamily('arista_port_bandwidth',
                                           'Bandwidth in bits/s',
                                           labels=['device', 'description'])

        if port_interfaces:
            self._interfaces = port_interfaces['result'][0]['interfaces']
            for interface in self._interfaces:
                try:
                    iface = self._interfaces[interface]
                    data = iface['interfaceCounters']
                except KeyError:
                    logging.debug((
                                   f'Interface {interface} on {self._target}'
                                   ' does not have interfaceCounters,'
                                   ' skipping'))
                    continue
                if iface['interfaceStatus'] == 'disabled':
                    port_admin_up.add_metric(labels=[iface['name'],
                                                     iface['description']],
                                             value=0)
                else:
                    port_admin_up.add_metric(labels=[iface['name'],
                                                     iface['description']],
                                             value=1)
                if iface['lineProtocolStatus'] == 'up':
                    port_l2_up.add_metric(labels=[iface['name'],
                                                  iface['description']],
                                          value=1)
                else:
                    port_l2_up.add_metric(labels=[iface['name'],
                                                  iface['description']],
                                          value=0)
                port_bandwidth.add_metric(labels=[iface['name'],
                                                  iface['description']],
                                          value=int(iface['bandwidth']))
                for port_stat in PORT_STATS_NAMES:
                    metric = [interface,
                              iface['description'],
                              iface['physicalAddress'],
                              str(iface['mtu']),
                              ]
                    port_stats[port_stat].add_metric(metric,
                                                     float(data[port_stat])
                                                     )
            yield from port_stats.values()
            yield port_admin_up
            yield port_l2_up
            yield port_bandwidth

    def collect_sfp(self):
        command = 'show interfaces transceiver detail'
        sfp = self.switch_command(command)
        sensor_entries = ['rxPower', 'txBias', 'txPower', 'voltage']

        if sfp:
            sfp_labels = ['device',
                          'sensor',
                          'mediaType',
                          'serial',
                          'description',
                          'lane']
            sfp_stats_metrics = GaugeMetricFamily('arista_sfp_stats',
                                                  'SFP Statistics',
                                                  labels=sfp_labels)
            alarm_labels = ['device', 'lane', 'sensor', 'alarmType']
            sfp_alarms = GaugeMetricFamily('arista_sfp_alarms',
                                           'SFP Alarms',
                                           labels=alarm_labels)
            for iface, data in sfp['result'][0]['interfaces'].items():
                interface = iface
                lane = iface
                if not data:
                    logging.debug(f'Port does not have SFP: {interface}')
                    continue
                description = ''
                # Lane detection. Lane is an optical transmitter that is
                # a part of an interface. For example, 100G interface
                # is usually comprised of four 25G lanes or ten 10G lanes.
                if iface not in self._interfaces:
                    logging.debug((f'Port {interface} not found in interfaces'
                                   '. Looking for a lane'))
                    try_iface = '/'.join(interface.split('/')[0:-1]) + '/1'
                    sfps = sfp['result'][0]['interfaces']
                    if sfps[iface]['vendorSn'] == sfps[try_iface]['vendorSn']:
                        lane = iface
                        interface = try_iface
                        logging.debug((f'Setting lane {lane} as '
                                       'part of {interface}'))
                try:
                    description = self._interfaces[interface]['description']
                except KeyError:
                    pass
                for sensor in sensor_entries:
                    labels = [interface,
                              sensor,
                              data['mediaType'],
                              data['vendorSn'],
                              description,
                              lane]
                    logging.debug((f'Adding: interface={interface} '
                                   f'sensor={sensor} value={data[sensor]} '
                                   f'labels={labels}'))
                    sfp_stats_metrics.add_metric(value=float(data[sensor]),
                                                 labels=labels)
                    # check thresholds and generate alerts
                    thresholds = data['details'][sensor]
                    labels = [interface, lane, sensor]
                    if data[sensor] > thresholds['highAlarm']:
                        labels.append('highAlarm')
                        sfp_alarms.add_metric(labels=labels,
                                              value=data[sensor])
                    elif data[sensor] > thresholds['highWarn']:
                        labels.append('highWarn')
                        sfp_alarms.add_metric(labels=labels,
                                              value=data[sensor])
                    elif data[sensor] < thresholds['lowAlarm']:
                        labels.append('lowAlarm')
                        sfp_alarms.add_metric(labels=labels,
                                              value=data[sensor])
                    elif data[sensor] < thresholds['lowWarn']:
                        labels.append('lowWarn')
                        sfp_alarms.add_metric(labels=labels,
                                              value=data[sensor])

            yield sfp_stats_metrics
            yield sfp_alarms

    def collect_bgp(self):
        command = 'show ip bgp summary'
        data = self.switch_command(command)
        ipv4 = data['result'][0]['vrfs']
        command = 'show ipv6 bgp summary'
        data = self.switch_command(command)
        ipv6 = data['result'][0]['vrfs']

        labels = ['vrf', 'peer', 'asn']
        prefixes = GaugeMetricFamily('arista_bgp_accepted_prefixes',
                                     'Number of prefixes accepted',
                                     labels=labels)
        peer_state = InfoMetricFamily('arista_bgp_peer_state',
                                      'State of the BGP peer',
                                      labels=labels + ['state', 'router_id'])

        for vrf, vrf_data in ipv4.items():
            if 'peers' not in vrf_data:
                continue
            router_id = vrf_data['routerId']
            for peer, peer_data in vrf_data['peers'].items():
                labels = {'vrf': vrf,
                          'router_id': router_id,
                          'peer': peer,
                          'asn': str(peer_data['asn']),
                          'state': peer_data['peerState']}
                peer_state.add_metric(value=labels, labels=labels)
                labels = [vrf, peer, str(peer_data['asn'])]
                prefixes.add_metric(value=peer_data['prefixReceived'],
                                    labels=labels)
        for vrf, vrf_data in ipv6.items():
            if 'peers' not in vrf_data:
                continue
            router_id = vrf_data['routerId']
            for peer, peer_data in vrf_data['peers'].items():
                labels = {'vrf': vrf,
                          'router_id': router_id,
                          'peer': peer,
                          'asn': str(peer_data['asn']),
                          'state': peer_data['peerState']}
                peer_state.add_metric(value=labels, labels=labels)
                labels = [vrf, peer, str(peer_data['asn'])]
                prefixes.add_metric(value=peer_data['prefixReceived'],
                                    labels=labels)
        yield peer_state
        yield prefixes

    def get_all_modules(self):
        return {'memory': self.collect_memory,
                'tcam': self.collect_tcam,
                'port': self.collect_port,
                'sfp': self.collect_sfp,
                'bgp': self.collect_bgp,
                }

    def get_modules(self):
        if not self._module_names:
            return self.get_all_modules()
        module_functions = {}
        modules = self._module_names.split(',')
        for module in modules:
            if module == 'all':
                return self.get_all_modules()
            elif module == 'memory':
                module_functions['memory'] = self.collect_memory
            elif module == 'tcam':
                module_functions['tcam'] = self.collect_tcam
            elif module == 'port':
                module_functions['port'] = self.collect_port
            elif module == 'sfp':
                module_functions['sfp'] = self.collect_sfp
            elif module == 'bgp':
                module_functions['bgp'] = self.collect_bgp
            else:
                logging.warning(f'Unknown module requested:{module}. Ignoring')
        return module_functions

    def collect(self):
        self._get_labels()
        self._interfaces = False
        # Export the up and response metrics
        yield GaugeMetricFamily('arista_up',
                                ('Information whether the switch is reachable '
                                 'and responds to API calls'),
                                value=self._switch_up)

        if self._switch_up == 1:

            yield InfoMetricFamily('arista_hw',
                                   ('Information about this arista device, '
                                    'such as serial number and model'),
                                   value=self._labels)

            for name, generator in self.get_modules().items():
                start = time.time()
                for metric in generator():
                    yield metric
                end = time.time()
                self.add_scrape_duration(name, end-start)
        yield self._scrape_durations
