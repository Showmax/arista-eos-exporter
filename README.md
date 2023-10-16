# arista-eapi-exporter

This is a Prometheus Exporter for extracting metrics from a Arista Switch using the Arista's eAPI and the Python Client for eAPI [pyeapi](https://pypi.org/project/pyeapi/).

This code is based on a forked version of [arista-eapi-exporter](https://github.com/Showmax/arista-eos-exporter) from Showmax and before from SAP CCloud. 

The hostname of the switch has to be passed as **target parameter** in the http or https call.

## Example Call

if you are logged in to the POD running the exporter you can call (example from my enviroment)

```bash
curl https://prometheus.as47536.net:9120/arista?target=rtr-a-frvzu01.as47536.net&modules=all
[..]
# TYPE arista_up gauge
arista_up 1.0
# HELP arista_hw_info Information about this arista device, such as serial number and model
# TYPE arista_hw_info gauge
arista_hw_info{model="DCS-7280TR-48C6-R",serial="XXXXXXXXXXXX",version="4.30.XX"} 1.0
# HELP arista_mem_total Total memory available
# TYPE arista_mem_total gauge
arista_mem_total 8.05984e+06
# HELP arista_mem_free Total memory free
# TYPE arista_mem_free gauge
arista_mem_free 5.057016e+06
[..]
```

The optional parameter `modules` can have these values at the moment:
 * `memory` memory statistics
 * `tcam` information about tcam usage
 * `port` information about ports - input/output packets, bytes, errors, multicasts, etc
 * `transceiver` information about transceiver modules - transmit/receive power, alerts over thresholds, etc
 * `bgp` information about BGP peers, how many routes they advertise, their status
 * `power` information about PSU (power supply units) - status, model, capacity, fans, power, temperature
 * `all` all of the above. This is the default.

## Prerequisites and Installation

The exporter was written for Python 3.10 or newer. It now supports to be runned from within a python3-venv. 
To install all dependencies, checkout the repo and setup the service you simply have to run the following commands:

```bash
root@prometheus:~# apt install git python3-venv
```

```bash
root@prometheus:~# cd /etc
root@prometheus:/etc# https://github.com/netfreak98/arista-eos-exporter.git
root@prometheus:/etc# cd arista-eos-exporter
```

```bash
root@prometheus:/etc/arista-eos-exporter# bash initialization.sh
```

Now you can use the systemd unit file provided from the extras/ folder. You need to have a look at the config file first. Otherwise the deamon will not come up right away.

```bash
root@prometheus:/etc/arista-eos-exporter# cp extras/prometheus-arista-exporter.service /etc/systemd/system/prometheus-arista-exporter.service
root@prometheus:/etc/arista-eos-exporter# systemctl daemon-reload
root@prometheus:/etc/arista-eos-exporter# sudo systemctl enable prometheus prometheus-arista-exporter
```

Short verification
```bash
root@prometheus:/etc/arista-eos-exporter# systemctl status prometheus-arista-exporter
● prometheus-arista-exporter.service - Arista EOS Exporter
     Loaded: loaded (/etc/systemd/system/prometheus-arista-exporter.service; enabled; vendor preset: enabled)
     Active: active (running) since Mon 2023-10-16 14:02:14 UTC; 2min 35s ago
   Main PID: 35448 (python3)
      Tasks: 5 (limit: 9553)
     Memory: 63.0M
        CPU: 3.375s
     CGroup: /system.slice/prometheus-arista-exporter.service
             ├─35448 /etc/arista-eos-exporter/.venv/bin/python3 /etc/arista-eos-exporter/main.py
             ├─35450 /etc/arista-eos-exporter/.venv/bin/python3 /etc/arista-eos-exporter/main.py
             ├─35451 /etc/arista-eos-exporter/.venv/bin/python3 /etc/arista-eos-exporter/main.py
             ├─35452 /etc/arista-eos-exporter/.venv/bin/python3 /etc/arista-eos-exporter/main.py
             └─35457 /etc/arista-eos-exporter/.venv/bin/python3 /etc/arista-eos-exporter/main.py

Oct 16 14:04:24 prometheus python3[35452]: 2023-10-16 14:04:24,763 35452 INFO collector.py:44 Connecting to switch rtr-b-frvzu01.as47536.net
Oct 16 14:04:26 prometheus python3[35457]: 2023-10-16 14:04:26,929 35457 INFO collector.py:44 Connecting to switch rtr-a-frvzu01.as47536.net
Oct 16 14:04:29 prometheus python3[35451]: 2023-10-16 14:04:29,764 35451 INFO collector.py:44 Connecting to switch rtr-b-frvzu01.as47536.net
Oct 16 14:04:31 prometheus python3[35452]: 2023-10-16 14:04:31,929 35452 INFO collector.py:44 Connecting to switch rtr-a-frvzu01.as47536.net
Oct 16 14:04:34 prometheus python3[35450]: 2023-10-16 14:04:34,762 35450 INFO collector.py:44 Connecting to switch rtr-b-frvzu01.as47536.net
Oct 16 14:04:36 prometheus python3[35451]: 2023-10-16 14:04:36,935 35451 INFO collector.py:44 Connecting to switch rtr-a-frvzu01.as47536.net
Oct 16 14:04:39 prometheus python3[35452]: 2023-10-16 14:04:39,765 35452 INFO collector.py:44 Connecting to switch rtr-b-frvzu01.as47536.net
Oct 16 14:04:41 prometheus python3[35457]: 2023-10-16 14:04:41,928 35457 INFO collector.py:44 Connecting to switch rtr-a-frvzu01.as47536.net
Oct 16 14:04:44 prometheus python3[35451]: 2023-10-16 14:04:44,763 35451 INFO collector.py:44 Connecting to switch rtr-b-frvzu01.as47536.net
Oct 16 14:04:46 prometheus python3[35452]: 2023-10-16 14:04:46,929 35452 INFO collector.py:44 Connecting to switch rtr-a-frvzu01.as47536.net
```

## The config.yml file

* The **listen_port** is providing the port on which the exporter is waiting to receive calls.

* The **listen_addr** - address on which to listen. Defaults to 0.0.0.0

* The credentials for login to the switches can either be added to the config.yaml file or passed via environment variables `ARISTA_USERNAME` and `ARISTA_PASSWORD`. The environment overwrites the settings in the config file

* The **loglevel** can be specified in the config file. If omitted the default level is `INFO`

* The **timeout** parameter specifies the amount of time to wait for an answer from the switch.

* The **disable_certificate_validation: true** needs to be currently set. See the Caveats section for more details.

### Example of a config file

```text
username: <your username>
password: <your password>
loglevel: <INFO|DEBUG>
timeout: 20
disable_certificate_validation: true
web_listen_port: 9120
web_listen_address: "[::]" # [YOUR IPv6] or X.X.X.X notation
web_cert_file: <your cert file path>/fullchain.pem 
web_key_file: <your key file path>/privkey.pem
web_ca_file: <your ca file path>/prometheus.as47536.net/chain.pem
```

### Example of Prometheus configuration
```yaml
  - job_name: 'arista'
    scheme: https
    scrape_interval: 5s
    static_configs:
      - targets:
        - rtr-a-frvzu01.as47536.net
        - rtr-b-frvzu01.as47536.net
    metrics_path: /arista
    params:
      modules: [all]
    relabel_configs:
      - source_labels: [__address__]
        target_label: __param_target
      - source_labels: [__param_target]
        target_label: instance
      - target_label: __address__
        replacement: prometheus.as47536.net:9120
```
This configuration uses relabeling to get `targets` as parameters for exporter running at prometheus.as47536.net:9120. Thanks to this, you can use any service discovery mechanism you want - just exchange static_configs with your desired SD system and adjust relabeling accordingly.

### Caveats
#### Certificate verification
Currently, certificate verification for HTTPS connections doesn't work. We filed an issue with the upstream client library here: https://github.com/arista-eosplus/pyeapi/issues/174

Should it be resolved, we will fix the exporter so it works with certificate validation enabled. For now, you have to explicitly disable certificate validation, because we want the default behavior to be the safe option - validate. After all, you are transferring login credentials to your network infrastructure, and you want to do that over an encrypted and verified channel.

#### Non-standard metrics
The `arista_transceiver_alarms` metric is not conforming to prometheus standards. The reason for that is that there are multiple alarms (high/low) that you need to compare to the current values in different ways (below/over). The exporter does this all for you, so you only get these metrics if there is an alarm firing.

You can therefore alert directly on `arista_transceiver_alarms` and you get the current sensor value in the alert as well as all the labels.
