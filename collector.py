from prometheus_client.core import GaugeMetricFamily, InfoMetricFamily

import logging
import os
import time

import pyeapi
import ssl

PORT_STATS_NAMES = [
    "inBroadcastPkts",
    "inDiscards",
    "inMulticastPkts",
    "inOctets",
    "inUcastPkts",
    "outBroadcastPkts",
    "outDiscards",
    "outMulticastPkts",
    "outOctets",
    "outUcastPkts",
]

class AristaTarget(object):
    def __init__(self, config, target):
        self._username = os.getenv("ARISTA_USERNAME", config["username"])
        self._password = os.getenv("ARISTA_PASSWORD", config["password"])
        self._protocol = config["protocol"] or "https"
        self._timeout = config["timeout"]
        self._target = target
        self._labels = {}
        self._switch_up = 0
        self._memtotal = 0
        self._memfree = 0
        self._connection = False
        self._interfaces = False

    def get_connection(self):
        # set the default timeout
        logging.debug(f"Setting timeout to {self._timeout}")
        if not self._connection:
            logging.info(f"Connecting to switch {self._target}")
            self._connection = pyeapi.connect(
                transport=self._protocol,
                host=self._target,
                username=self._username,
                password=self._password,
                timeout=self._timeout,
            )
            # workaround to allow sslv3 ciphers for python =>3.10
            self._connection.transport._context.set_ciphers('DEFAULT')
        return self._connection

    def switch_command(self, command):
        switch_result = ""

        connection = self.get_connection()

        try:
            logging.debug(f"Running command {command}")
            switch_result = connection.execute([command])
        except pyeapi.eapilib.ConnectionError as pyeapi_connect_except:
            self._connection = False
            logging.error(
                ("PYEAPI Client Connection Exception: " f"{pyeapi_connect_except}")
            )
        except pyeapi.eapilib.CommandError as pyeapi_command_except:
            self._connection = False
            logging.error(
                ("PYEAPI Client Command Exception: " f"{pyeapi_command_except}")
            )
        finally:
            return switch_result

    def get_labels(self):
        # Get the switch info for the labels
        switch_info = self.switch_command("show version")
        try:
            si_res = switch_info["result"][0]
        except Exception as e:
            logging.debug(f"No result from switch {self._target}: {e}")
            labels_switch = {
                "model": "unknown",
                "serial": "unknown",
                "version": "unknown",
                "target": "unknown"
            }
            self._switch_up = 0
        else:
            logging.debug(f"Received a result from switch {self._target}")
            labels_switch = {
                "model": si_res["modelName"],
                "serial": si_res["serialNumber"],
                "version": si_res["version"],
                "target": self._target
            }
            self._memtotal = si_res["memTotal"]
            self._memfree = si_res["memFree"]
            self._switch_up = 1

        self._labels = labels_switch
        return self._labels

    def switch_up(self):
        return self._switch_up

    def memtotal(self):
        return self._memtotal

    def memfree(self):
        return self._memfree

class AristaMetricsCollector(object):
    def __init__(self, config, targets):
        self._targets = {}
        for target in targets:
            arista_target = AristaTarget(config,target)
            self._targets[target] = arista_target
        self._module_names = False
        if "module_names" in config:
            self._module_names = config["module_names"]
        self._scrape_durations = GaugeMetricFamily(
            "arista_scrape_duration_seconds",
            "Duration of a collector scrape.",
            labels=["collector","target"]
        )

    def add_scrape_duration(self, module_name, duration, target):
        self._scrape_durations.add_sample(
            "arista_scrape_duration_seconds",
            value=duration,
            labels=({"collector": module_name, "target": target})
        )

    def collect_memory(self, targets):
        # Export the memory usage data
        mem_total = GaugeMetricFamily(
            "arista_mem_total", "Total memory available",
            labels=["target"]
        )
        mem_free = GaugeMetricFamily(
            "arista_mem_free", "Total memory free",
            labels=["target"]
        )

        for target_name,target in targets.items():
            if target.switch_up() == 0:
                continue
            start = time.time()
            mem_total.add_metric(
                value=target.memtotal(), labels=[target_name]
            )
            mem_free.add_metric(
                value=target.memfree(), labels=[target_name]
            )
            end = time.time()
            self.add_scrape_duration("memory", end - start, target_name)
        yield mem_total
        yield mem_free

    def collect_tcam(self, targets):
        # Get the tcam usage data
        used_metrics = GaugeMetricFamily(
            "arista_tcam_used", "TCAM Usage Data",
            labels=["table", "chip", "feature", "target"]
        )
        total_metrics = GaugeMetricFamily(
            "arista_tcam_total", "TCAM Capacity",
            labels=["table", "chip", "feature", "target"]
        )

        for target_name,target in targets.items():
            if target.switch_up() == 0:
                continue
            start = time.time()
            switch_tcam = target.switch_command("show hardware capacity")

            if switch_tcam:
                for entry in switch_tcam["result"][0]["tables"]:
                    try:
                        labels = {
                            "table": entry["table"],
                            "chip": entry["chip"],
                            "feature": entry["feature"],
                            "target": target_name
                        }
                        logging.debug(
                            (
                                f'Adding: table={entry["table"]} '
                                f'value={entry["used"]} '
                                f"labels={labels}"
                            )
                        )
                        used_metrics.add_sample(
                            "arista_tcam_used", value=entry["used"], labels=labels
                        )
                        total_metrics.add_sample(
                            "arista_tcam_total", value=entry["maxLimit"], labels=labels
                        )
                    except KeyError:
                        logging.error("KeyError in switch_tcam entries")
                        continue
            end = time.time()
            self.add_scrape_duration("tcam", end - start, target_name)

        yield total_metrics
        yield used_metrics

    def collect_port(self, targets):
        port_stats = {
            k: GaugeMetricFamily(
                f"arista_port_{k}",
                f"Port stats {k}",
                labels=["device", "description", "mac", "mtu", "target"],
            )
            for k in PORT_STATS_NAMES
        }
        port_admin_up = GaugeMetricFamily(
            "arista_admin_up",
            "Value 1 if port is not shutdown",
            labels=["device", "description", "target"],
        )
        port_l2_up = GaugeMetricFamily(
            "arista_l2_up",
            "Value 1 if port is connected",
            labels=["device", "description", "target"],
        )
        port_bandwidth = GaugeMetricFamily(
            "arista_port_bandwidth",
            "Bandwidth in bits/s",
            labels=["device", "description", "target"],
        )

        for target_name,target in targets.items():
            if target.switch_up() == 0:
                continue
            start = time.time()
            port_interfaces = target.switch_command("show interfaces")

            if port_interfaces:
                self._interfaces = port_interfaces["result"][0]["interfaces"]
                for interface in self._interfaces:
                    try:
                        iface = self._interfaces[interface]
                        data = iface["interfaceCounters"]
                    except KeyError:
                        logging.debug(
                            (
                                f"Interface {interface} on {target_name}"
                                " does not have interfaceCounters,"
                                " skipping"
                            )
                        )
                        continue
                    if iface["interfaceStatus"] == "disabled":
                        port_admin_up.add_metric(
                            labels=[iface["name"], iface["description"], target_name],
                            value=0
                        )
                    else:
                        port_admin_up.add_metric(
                            labels=[iface["name"], iface["description"], target_name],
                            value=1
                        )
                    if iface["lineProtocolStatus"] == "up":
                        port_l2_up.add_metric(
                            labels=[iface["name"], iface["description"], target_name],
                            value=1
                        )
                    else:
                        port_l2_up.add_metric(
                            labels=[iface["name"], iface["description"], target_name],
                            value=0
                        )
                    port_bandwidth.add_metric(
                        labels=[iface["name"], iface["description"], target_name],
                        value=int(iface["bandwidth"]),
                    )
                    for port_stat in PORT_STATS_NAMES:
                        metric = [
                            interface,
                            iface["description"],
                            iface["physicalAddress"],
                            str(iface["mtu"]),
                            target_name,
                        ]
                        port_stats[port_stat].add_metric(metric, float(data[port_stat]))
            end = time.time()
            self.add_scrape_duration("port", end - start, target_name)
        yield from port_stats.values()
        yield port_admin_up
        yield port_l2_up
        yield port_bandwidth

    def collect_sfp(self, targets):
        sfp_labels = [
            "device",
            "sensor",
            "mediaType",
            "serial",
            "description",
            "lane",
            "target",
        ]
        sfp_stats_metrics = GaugeMetricFamily(
            "arista_sfp_stats", "SFP Statistics", labels=sfp_labels
        )
        alarm_labels = ["device", "lane", "sensor", "alarmType", "target"]
        sfp_alarms = GaugeMetricFamily(
            "arista_sfp_alarms", "SFP Alarms", labels=alarm_labels
        )

        for target_name,target in targets.items():
            if target.switch_up() == 0:
                continue
            port_interfaces = target.switch_command("show interfaces")
            if port_interfaces:
                interfaces = port_interfaces["result"][0]["interfaces"]
            start = time.time()
            sfp = target.switch_command("show interfaces transceiver detail")
            sensor_entries = ["rxPower", "txBias", "txPower", "voltage"]

            if interfaces and sfp:
                for iface, data in sfp["result"][0]["interfaces"].items():
                    interface = iface
                    lane = iface
                    if not data:
                        logging.debug(f"Port does not have SFP: {interface}")
                        continue
                    description = ""
                    # Lane detection. Lane is an optical transmitter that is
                    # a part of an interface. For example, 100G interface
                    # is usually comprised of four 25G lanes or ten 10G lanes.
                    if iface not in interfaces:
                        logging.debug(
                            (
                                f"Port {interface} not found in interfaces"
                                ". Looking for a lane"
                            )
                        )
                        try_iface = "/".join(interface.split("/")[0:-1]) + "/1"
                        sfps = sfp["result"][0]["interfaces"]
                        if sfps[iface]["vendorSn"] == sfps[try_iface]["vendorSn"]:
                            lane = iface
                            interface = try_iface
                            logging.debug(
                                (f"Setting lane {lane} as " "part of {interface}")
                            )
                    try:
                        description = interfaces[interface]["description"]
                    except KeyError:
                        pass
                    for sensor in sensor_entries:
                        labels = [
                            interface,
                            sensor,
                            data["mediaType"],
                            data["vendorSn"],
                            description,
                            lane,
                            target_name
                        ]
                        logging.debug(
                            (
                                f"Adding: interface={interface} "
                                f"sensor={sensor} value={data[sensor]} "
                                f"labels={labels}"
                            )
                        )
                        sfp_stats_metrics.add_metric(
                            value=float(data[sensor]), labels=labels
                        )
                        # check thresholds and generate alerts
                        thresholds = data["details"][sensor]
                        labels = [interface, lane, sensor, target_name]
                        if data[sensor] > thresholds["highAlarm"]:
                            labels.append("highAlarm")
                            sfp_alarms.add_metric(labels=labels, value=data[sensor])
                        elif data[sensor] > thresholds["highWarn"]:
                            labels.append("highWarn")
                            sfp_alarms.add_metric(labels=labels, value=data[sensor])
                        elif data[sensor] < thresholds["lowAlarm"]:
                            labels.append("lowAlarm")
                            sfp_alarms.add_metric(labels=labels, value=data[sensor])
                        elif data[sensor] < thresholds["lowWarn"]:
                            labels.append("lowWarn")
                            sfp_alarms.add_metric(labels=labels, value=data[sensor])
            end = time.time()
            self.add_scrape_duration("sfp", end - start, target_name)

        yield sfp_stats_metrics
        yield sfp_alarms

    def collect_bgp(self, targets):
        labels = ["vrf", "peer", "asn", "target"]
        prefixes = GaugeMetricFamily(
            "arista_bgp_accepted_prefixes", "Number of prefixes accepted", labels=labels
        )
        peer_state = InfoMetricFamily(
            "arista_bgp_peer_state",
            "State of the BGP peer",
            labels=labels + ["state", "router_id", "target"],
        )

        for target_name,target in targets.items():
            if target.switch_up() == 0:
                continue
            start = time.time()
            data = target.switch_command("show ip bgp summary")
            ipv4 = data["result"][0]["vrfs"]
            data = target.switch_command("show ipv6 bgp summary")
            ipv6 = data["result"][0]["vrfs"]

            for vrf, vrf_data in ipv4.items():
                if "peers" not in vrf_data:
                    continue
                router_id = vrf_data["routerId"]
                for peer, peer_data in vrf_data["peers"].items():
                    labels = {
                        "vrf": vrf,
                        "router_id": router_id,
                        "peer": peer,
                        "asn": str(peer_data["asn"]),
                        "state": peer_data["peerState"],
                        "target": target_name
                    }
                    peer_state.add_metric(value=labels, labels=labels)
                    labels = [vrf, peer, str(peer_data["asn"]), target_name]
                    prefixes.add_metric(value=peer_data["prefixReceived"], labels=labels)
            for vrf, vrf_data in ipv6.items():
                if "peers" not in vrf_data:
                    continue
                router_id = vrf_data["routerId"]
                for peer, peer_data in vrf_data["peers"].items():
                    labels = {
                        "vrf": vrf,
                        "router_id": router_id,
                        "peer": peer,
                        "asn": str(peer_data["asn"]),
                        "state": peer_data["peerState"],
                        "target": target_name
                    }
                    peer_state.add_metric(value=labels, labels=labels)
                    labels = [vrf, peer, str(peer_data["asn"]), target_name]
                    prefixes.add_metric(value=peer_data["prefixReceived"], labels=labels)
            end = time.time()
            self.add_scrape_duration("bgp", end - start, target_name)
        yield peer_state
        yield prefixes

    def collect_power(self, targets):
        psu_info = InfoMetricFamily(
            "arista_power_supply",
            "State of the power supply",
            labels=["state", "model", "capacity_watts", "id", "target"]
        )
        psu_power = GaugeMetricFamily(
            "arista_power_supply_power",
            "Power supply power measurements",
            labels=["id", "measurement", "target"]
        )
        psu_temp = GaugeMetricFamily(
            "arista_power_supply_temperature",
            "Power supply temperature sensors",
            labels=["id", "status", "sensor", "target"]
        )
        psu_fan = GaugeMetricFamily(
            "arista_power_supply_fan_speed_percent",
            "Power supply fan speed sensors",
            labels=["id", "status", "sensor", "target"]
        )

        measurements = ["inputCurrent", "inputVoltage", "outputCurrent", "outputPower"]
        for target_name,target in targets.items():
            if target.switch_up() == 0:
                continue
            start = time.time()
            data = target.switch_command("show environment power")
            for psu_id, psu in data["result"][0]["powerSupplies"].items():
                labels = {
                    "state": psu["state"],
                    "model": psu["modelName"],
                    "capacity_watts": str(psu["capacity"]),
                    "id": str(psu_id),
                    "target": target_name
                }
                psu_info.add_metric(value=labels, labels=labels)
                for measurement in measurements:
                    psu_power.add_metric(
                        value=psu[measurement], labels=[psu_id, measurement, target_name]
                    )
                for name, sensor_data in psu["tempSensors"].items():
                    psu_temp.add_metric(
                        value=sensor_data["temperature"],
                        labels=[psu_id, sensor_data["status"], name, target_name],
                    )
                for name, fan_data in psu["fans"].items():
                    psu_fan.add_metric(
                        value=fan_data["speed"], labels=[psu_id, fan_data["status"], name, target_name]
                    )
            end = time.time()
            self.add_scrape_duration("power", end - start, target_name)

        yield psu_info
        yield psu_power
        yield psu_temp
        yield psu_fan

    def get_all_modules(self):
        return {
            "memory": self.collect_memory,
            "tcam": self.collect_tcam,
            "port": self.collect_port,
            "sfp": self.collect_sfp,
            "bgp": self.collect_bgp,
            "power": self.collect_power,
        }

    def get_modules(self):
        all_modules = self.get_all_modules()
        if not self._module_names:
            return all_modules
        module_functions = {}
        modules = self._module_names.split(",")
        for module in modules:
            if module == "all":
                return all_modules
            elif module in all_modules:
                module_functions[module] = all_modules[module]
            else:
                logging.warning(f"Unknown module requested:{module}. Ignoring")
        return module_functions

    def collect(self):

        info_labels = ["model", "serial", "version", "target"]
        arista_up = GaugeMetricFamily(
            "arista_up",
            (
                "Information whether the switch is reachable "
                "and responds to API calls"
            ),
            labels=["target"]
        )
        arista_hw = InfoMetricFamily(
            "arista_hw",
            (
                "Information about this arista device, "
                "such as serial number and model"
            ),
            labels=info_labels
        )
        for target_name,target in self._targets.items():
            start = time.time()
            target_labels = target.get_labels()

            # Export the up and response metrics
            switch_up = target.switch_up()
            arista_up.add_metric(
                value=switch_up, labels=[target_name]
           )

            if switch_up == 1:
                arista_hw.add_metric(
                    value=target_labels, labels=info_labels
                )

            end = time.time()
            self.add_scrape_duration("base", end - start, target_name)

        for name, generator in self.get_modules().items():
            for metric in generator(self._targets):
                yield metric
        yield self._scrape_durations
        yield arista_up
        yield arista_hw
