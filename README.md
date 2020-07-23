# arista-eapi-exporter

This is a Prometheus Exporter for extracting metrics from a Arista Switch using the Arista's eAPI and the Python Client for eAPI [pyeapi](https://pypi.org/project/pyeapi/).

This code is based on a forked version of [arista-eapi-exporter](https://github.com/sapcc/arista-eapi-exporter) from SAP CCloud.

The hostname of the switch has to be passed as **target parameter** in the http call.

## Example Call

if you are logged in to the POD running the exporter you can call

```
curl http://localhost:9200/arista?target=myswitch.local&modules=tcam,port
```

The optional parameter `modules` can have these values at the moment:
 * `memory` memory statistics
 * `tcam` information about tcam usage
 * `port` information about ports - input/output packets, bytes, errors, multicasts, etc
 * `sfp` information about SFP modules - transmit/receive power, alerts over thresholds, etc
 * `bgp` information about BGP peers, how many routes they advertise, their status
 * `all` all of the above. This is the default.

## Prerequisites and Installation

The exporter was written for Python 3.6 or newer. To install all modules needed you have to run the following command:

```bash
pip3 install -r requirements.txt
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
listen_port: 9200
username: <your username>
password: <your password>
loglevel: <INFO|DEBUG>
timeout: 20
disable_certificate_validation: true
```

### Example of Prometheus configuration
```yaml
- job_name: 'arista'
  static_configs:
    - targets:
      - switch1.example.com
      - switch2.example.com
  metrics_path: /arista
  params:
    modules: [tcam,port]
  relabel_configs:
    - source_labels: [__address__]
      target_label: __param_target
    - source_labels: [__param_target]
      target_label: instance
    - target_label: __address__
      replacement: arista-exporter.example.com:9200
```
This configuration uses relabeling to get `targets` as parameters for exporter running at arista-exporter.example.com:9200. Thanks to this, you can use any service discovery mechanism you want - just exchange static_configs with your desired SD system and adjust relabeling accordingly.

### Example exporter output
Look in the examples/ folder.

### Caveats
#### Certificate verification
Currently, certificate verification for HTTPS connections doesn't work. We filed an issue with the upstream client library here: https://github.com/arista-eosplus/pyeapi/issues/174

Should it be resolved, we will fix the exporter so it works with certificate validation enabled. For now, you have to explicitly disable certificate validation, because we want the default behavior to be the safe option - validate. After all, you are transferring login credentials to your network infrastructure, and you want to do that over an encrypted and verified channel.

#### Non-standard metrics
The `arista_sfp_alarms` metric is not conforming to prometheus standards. The reason for that is that there are multiple alarms (high/low) that you need to compare to the current values in different ways (below/over). The exporter does this all for you, so you only get these metrics if there is an alarm firing.

You can therefore alert directly on `arista_sfp_alarms` and you get the current sensor value in the alert as well as all the labels.
