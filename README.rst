======================
Kubernetes Log Watcher
======================

.. image:: https://api.travis-ci.org/zalando-incubator/kubernetes-log-watcher.svg?branch=master
  :target: https://travis-ci.org/zalando-incubator/kubernetes-log-watcher

Kubernetes Log Watcher is used to facilitate log shipping on a Kubernetes cluster. The watcher will detect containers running on a cluster node, and adjust configurations for number of log configuration agents. ``kubernetes-log-watcher`` is intended to run in a Kubernetes ``DaemonSet`` along with one or more log shippers.

``kubernetes-log-watcher`` comes with builtin configuration agents, however it could be extended to support external agents. Current builtin configuration agents are:

- AppDynamics
- Scalyr
- Symlinker (embeds metadata in symlink filenames, to be extracted by a log shipping agent such as Fluentd)

``kubernetes-log-watcher`` is used in `kubernetes-on-aws <https://github.com/zalando-incubator/kubernetes-on-aws>`_ project.

Components
==========

Watcher
-------

Log Watcher is responsible for detecting running containers on a cluster node, extract information from container labels, and supply sufficient information to configuration agents in order to facilitate log shipping. The log watcher could run with one or more configuration agents.

Configuration Agent
-------------------

The agent acts as a plugin, its sole purpose is to adjust log configuration for its log shipper. It is important to note that the configuration agent is not intended to process the logs, it only adjusts configuration files for log shipper (e.g. set log source paths and custom attributes with log events) based on information received from log watcher.

Features & Constraints
======================

* Log watcher accepts one or more log configuration agent.
* Log watcher will skip ``pause`` containers.
* Configuration agents provide the ability to dynamically attach tags/attributes/metadata to logs based on Kubernetes labels.
* **Optionally** follow logs from containers running in pods with a defined list of metadata labels. (optional since 0.14)
* Sync new and stale containers.

Usage
=====

Kubernetes Log Watcher is intended to run in a ``DaemonSet`` along with one or more log configuration agent (e.g. Scalyr, AppDynamics ...). The DaemonSet will ensure that the watcher is running on every cluster node.


Diagram
-------

The following diagram describes how Log watcher DaemonSet interacts with cluster node containers, Kubernetes API and Log Storage.

.. code-block::

                             +------------------------------------------------------+
    +--------------------+   |                         NODE                         |   +--------------------+
    |       K8s API      |   |  +----------------+              +----------------+  |   |    Log Storage     |
    |                    |   |  |     pod 1      |              |     pod 2      |  |   |                    |
    |                    |   |  |                |              |                |  |   |                    |
    |                    |   |  | +------------+ |              | +------------+ |  |   |                    |
    |                    |   |  | |   Cont 1   | |              | |   Cont 2   | |  |   |                    |
    |                    |   |  | +------+-----+ |              | +--------+---+ |  |   |                    |
    +---------+----------+   |  |        |       |              |          |     |  |   +---------+----------+
              ^              |  |        |       |              |          |     |  |             ^
              |              |  +----------------+              +----------------+  |             |
              |              |           |                                 v        |             |
              |              |           |                                          |             |
              |              |           +-----------[0]--------------> +-----+     |             |
              |              |                                          |LOGS |     |             |
              |              |  +-----------------------------------------------+   |             |
              |              |  | Log watcher pod (DaemonSet)           |     | |   |             |
              |              |  |       +-------[1]----------> +------> +-----+ |   |             |
              |              |  |       |                      |                |   |             |
              |              |  | +-----+-----+          +-----+--------------+ |   |             |
              +-----[2,3]---------+Log|watcher+--[4]---> |     Log shipper    +------------[5]----+
                             |  | +-----------+          +--------------------+ |   |
                             |  +-----------------------------------------------+   |
                             +------------------------------------------------------+

Operation
---------

#. ``Log watcher`` container detects changes in node containers mounted directory (typically ``/var/lib/docker/containers``)
#. ``Log watcher`` container loads containers information with help of Kubernetes API.
#. ``Log watcher`` container will supply containers info to configuration agents.
#. Configuration agents will adjust log configuration for the ``Log shipper`` container (one or more). Log configuration may include containers log file paths and extra attributes/tags attached to the logs.
#. ``Log shippers`` should start following logs from mounted log volume (based on log configuration) and ship logs to the log storage.

Example manifest
----------------

This is an example manifest for shipping logs to Scalyr, with additional Journald monitoring for master processes running on the node.

.. note::

    - This manifest assumes running a Kubernetes cluster version >= 1.5 (as it depends on `initContainer <https://kubernetes.io/docs/concepts/workloads/pods/init-containers/>`_ for initial Scalyr configuration)
    - All shared volumes are of type ``hostPath`` in order to survive pod restarts.
    - Initial Scalyr configuration using ``configMap`` is no longer used as it appears to be reseted to initial values by Kubernetes.

.. code-block:: yaml

    apiVersion: extensions/v1beta1
    kind: DaemonSet
    metadata:
        name: logging-agent
        namespace: kube-system
        labels:
          application: logging-agent
          version: v0.27
          component: logging
    spec:
        selector:
          matchLabels:
            application: logging-agent
        template:
          metadata:
            name: logging-agent
            labels:
              application: logging-agent
              version: v0.27
              component: logging
            annotations:
              scheduler.alpha.kubernetes.io/critical-pod: ''
              scheduler.alpha.kubernetes.io/tolerations: '[{"key":"CriticalAddonsOnly", "operator":"Exists"}]'
              pod.beta.kubernetes.io/init-containers: '[
                {
                  "name": "init-scalyr-config",
                  "image": "busybox",
                  "imagePullPolicy": "IfNotPresent",
                  "command": ["sh", "-c"],
                  "args":
                    - |
                      SCALYR_CONFIG_PATH="/mnt/scalyr/agent.json"
                      if [ -f "$SCALYR_CONFIG_PATH" ]; then
                        echo "Has agent.json with configuration:"
                        cat $SCALYR_CONFIG_PATH;
                      else
                        # Write a minimal configuration which let scalyr agent to start and wait for real configuration
                        echo "Create agent.json with inital configuration:"
                        tee "$SCALYR_CONFIG_PATH" <<EOF
                      {
                          "api_key": "$WATCHER_SCALYR_API_KEY",
                          "scalyr_server": "${WATCHER_SCALYR_SERVER:-https://upload.eu.scalyr.com}",
                          "implicit_agent_process_metrics_monitor": false,
                          "implicit_metric_monitor": false,
                          "monitors": [],
                          "logs": []
                      }
                      EOF
                      # ^^^ "EOF" must be at 0 position after YAML decode
                      fi;

                      SCALYR_CHECKPOINTS_PATH="/mnt/scalyr-agent-checkpoints/checkpoints.json"
                      if [ -f "$SCALYR_CHECKPOINTS_PATH" ]; then
                        echo
                        ls -lah "$SCALYR_CHECKPOINTS_PATH"
                        cat "$SCALYR_CHECKPOINTS_PATH"
                      fi
                  "env":
                    - name: WATCHER_SCALYR_API_KEY
                      value: "<SCALYR-KEY-HERE>"
                  "volumeMounts": [
                    {
                      "name": "scalyr-config",
                      "mountPath": "/mnt/scalyr"
                    },
                    {
                      "name": "scalyr-checkpoint",
                      "mountPath": "/mnt/scalyr-checkpoint"
                    }
                  ]
                }
              ]'
          spec:
            containers:
            - name: log-watcher
              image: registry.opensource.zalan.do/eagleeye/kubernetes-log-watcher:0.27
              env:
              - name: CLUSTER_NODE_NAME
                valueFrom:
                  fieldRef:
                    fieldPath: spec.nodeName

              - name: WATCHER_DEBUG
                value: "true"
              - name: WATCHER_CLUSTER_ID
                value: "kubernetes-cluster-1"

              - name: WATCHER_AGENTS
                value: scalyr
              - name: WATCHER_SCALYR_API_KEY_FILE
                value: "<PATH-TO-SCALYR-KEY-HERE>"
              - name: WATCHER_SCALYR_DEST_PATH
                value: /mnt/scalyr-logs
              - name: WATCHER_SCALYR_CONFIG_PATH
                value: /mnt/scalyr-config/agent.json
              - name: WATCHER_CONFIG
                value: /mnt/scalyr-config/agent.json
              - name: WATCHER_SCALYR_JOURNALD
                value: "true"

              volumeMounts:
              - name: containerlogs
                mountPath: /mnt/containers
                readOnly: true
              - name: scalyr-logs
                mountPath: /mnt/scalyr-logs
                readOnly: false
              - name: scalyr-config
                mountPath: /mnt/scalyr-config

            - name: scalyr-agent

              image: registry.opensource.zalan.do/eagleeye/scalyr-agent:0.2

              volumeMounts:
              - name: containerlogs
                mountPath: /mnt/containers
                readOnly: true
              - name: scalyr-logs
                mountPath: /mnt/scalyr-logs
                readOnly: true
              - name: scalyr-checkpoint
                mountPath: /var/lib/scalyr-agent-2
              - name: scalyr-config
                mountPath: /etc/scalyr-agent-2
                readOnly: true
              - name: journal
                mountPath: /var/log/journal
                readOnly: true

            volumes:
            - name: containerlogs
              hostPath:
                path: /var/lib/docker/containers

            - name: journal
              hostPath:
                path: /var/log/journal

            - name: scalyr-checkpoint
              hostPath:
                path: /var/lib/scalyr-agent

            - name: scalyr-config
              hostPath:
                path: /etc/scalyr-agent

            - name: scalyr-logs
              hostPath:
                path: /var/log/scalyr-agent


Configuration
-------------

Log watcher accepts a set of configuration variables to adjust its behavior. The same applies to builtin configuration agents.

Log watcher
^^^^^^^^^^^

Configuration variables can be set via Env variables:

WATCHER_CONTAINERS_PATH
  Containers directory path mounted from the host (Default: ``/var/lib/docker/containers``)

WATCHER_STRICT_LABELS
  If set then only containers running in pods with the list of metadata labels will be considered for log watching. Value is a comma separated string of label names. (Default is ``''``)

  If no ``application`` label is set then kubernetes-log-watcher will set ``application`` from *pod name*; in order to provide consistent attributes to log configuration agents.

WATCHER_AGENTS
   Comma separated string of required log configuration agents. (Required. Example: "scalyr,appdynamics")

WATCHER_CLUSTER_ID
   Kubernetes Cluster ID.

WATCHER_KUBE_URL
   URL to API proxy service. Service is expected to handle authentication to the Kubernetes cluster. If set, then log-watcher will not use serviceaccount config.

WATCHER_KUBERNETES_UPDATE_CERTIFICATES
   [Deprecated] Call update-ca-certificates for Kubernetes service account ca.crt.

WATCHER_INTERVAL
   Polling interval (secs) for the watcher to detect containers changes. (Default: 60 sec)

WATCHER_DEBUG
   Verbose output. (Default: False)

Scalyr configuration agent
^^^^^^^^^^^^^^^^^^^^^^^^^^

Configuration variables can be set via Env variables:

WATCHER_CONFIG
  Log watcher configuration file (YAML).

WATCHER_SCALYR_API_KEY
  Scalyr API key. (Required).

WATCHER_SCALYR_API_KEY_FILE
  Path to a file with Scalyr API key. (Required).

WATCHER_SCALYR_DEST_PATH
  Scalyr configuration agent will symlink containers logs in this location. This is to provide more friendly name for log files. Typical log file name for a container will be in the form ``<application>-<version>.log``. (Required).

WATCHER_SCALYR_CONFIG_PATH
  Scalyr configuration file path. (Default: ``/etc/scalyr-agent-2/agent.json``)

WATCHER_SCALYR_ENABLE_PROFILING
  If true, the agent will log performance profiling data about itself into a log file.

WATCHER_SCALYR_PARSE_LINES_JSON
  Useful for raw docker logs. Comma-separated list of parsers expecting decoded JSON. Each item could also be defined as ``foo=bar`` to override defined parser ``foo`` with ``bar``. Use `*` to decode JSON for all parsers. Default is ``""`` — decoding is disabled.

WATCHER_SCALYR_JOURNALD
  Scalyr should follow Journald logs. This is for node system processes log shipping (e.g. docker, kube) (Default: ``False``)

WATCHER_SCALYR_JOURNALD_ATTRIBUTES
  Add attributes to Journald logs. By default ``cluster`` and ``node`` will be added by the configuration agent.

WATCHER_SCALYR_JOURNALD_EXTRA_FIELDS
  Add extra Systemd Journald fields. Should be a JSON string. Example: '{"_COMM": "command"}'

WATCHER_SCALYR_JOURNALD_PATH
  Journald logs path mounted from the host. (Default: ``/var/log/journald``)

WATCHER_SCALYR_JOURNALD_WRITE_RATE
  Journald monitor write rate. (Default: 10000)

WATCHER_SCALYR_JOURNALD_WRITE_BURST
  Journald monitor write burst. (Default: 200000)

Scalyr custom parser
....................

The default parser for container logs is ``json`` parser. In some cases however you might need to assign a `custom Scalyr parser <https://www.scalyr.com/help/config>`_ for specific container. This can be achieved via pod annotations. The following example shows an annotation value that instructs kubernetes-log-watcher to set custom parser ``json-java-parser`` for container ``app-1``.

.. code-block:: yaml

  annotations:
    kubernetes-log-watcher/scalyr-parser: '[{"container": "app-1", "parser": "json-java-parser"}]'

The value of ``kubernetes-log-watcher/scalyr-parser`` annotation should be a json serialized list. If ``container`` value did not match, then default parser is used (i.e. ``json``).

Scalyr sampling rules
....................

Sampling rules enable to only ship a certain pattern that matches a regular expression and specified amount of log percentage to Scalyr. The example shows an expression that matches ``app-1`` and a match expression ``my-expression``. If it's met, only 10% of it will be shipped to Scalyr using a ``sampling_rate`` of ``0.1``.

.. code-block:: yaml

  annotations:
    kubernetes-log-watcher/scalyr-sampling-rules: '[{"container": "app-1", "sampling-rules":[{ "match_expression": "my-expression", "sampling_rate": "0.1" }]}]'


Scalyr log redaction
....................

Redaction rules enable to avoid shipping sensitive data that shouldn't get transferred to Scalyr either getting fully removed from log files or to replace them with specific strings. The first example below shows how matches will be fully removed and the second shows how matches will be replaced with a different string.

.. code-block:: yaml

  annotations:
    kubernetes-log-watcher/scalyr-redaction-rules: '[{"container": "app-1", "redaction-rules":[{ "match_expression": "my-expression" }]}]'
    kubernetes-log-watcher/scalyr-redaction-rules: '[{"container": "app-1", "redaction-rules":[{ "match_expression": "my-expression", "replacement": "replacement-expression" }]}]'

The following redaction rule is added automatically for all containers. It redacts `JSON Web Tokens  <https://tools.ietf.org/html/rfc7519>`_ from all logs.

.. code-block:: json

   {
     "match_expression": "eyJ[a-zA-Z0-9/+_=-]{5,}\\.eyJ[a-zA-Z0-9/+_=-]{5,}\\.[a-zA-Z0-9/+_=-]{5,}",
     "replacement": "+++JWT_TOKEN_REDACTED+++"
   }

AppDynamics configuration agent
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Configuration variables can be set via Env variables:

WATCHER_APPDYNAMICS_DEST_PATH
  AppDynamics job files path. (Required).

AppDynamics configuration agent could also add ``app_name`` and ``tier_name`` if ``appdynamics_app`` and ``appdynamics_tier`` were set in pod metadata labels.

Symlinker configuration agent
^^^^^^^^^^^^^^^^^^^^^^^^^

The Symlinker agent requires only one environment variable:

WATCHER_SYMLINK_DIR
  Base directory where symlink directory structure will be created.


Development
===========

Preferably create a Python 3.8 ``virtualenv``.

.. code-block:: bash

    $ pip install -r requirements.txt
    $ python -m kube_log_watcher --help

Tests
-----

You can use ``pytest``

.. code-block:: bash

    # test requirements
    $ pip install -U flake8 mock pytest pytest_cov

    $ py.test -v tests/
    $ flake8 .

or via ``tox``

.. code-block:: bash

    $ tox

TODO
====

- Support custom extra/external agents (e.g. ``kube-log-watcher --extra-agent /var/lib/custom-agent.py``)
- Support configuration from config files instead of env variables (e.g. ``kube-log-watcher --config /etc/kube-log-watcher/config.yaml``)
- Support running kube-log-watcher as standalone (release to PyPi)
- Add more configuration agents (logstash, fluentd, etc ...)

All contributions are welcome :)

License
=======

The MIT License (MIT)

Copyright (c) 2021 Zalando SE, https://tech.zalando.com

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
