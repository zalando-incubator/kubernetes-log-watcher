======================
Kubernetes Log Watcher
======================

.. image:: https://api.travis-ci.org/zalando-incubator/kubernetes-log-watcher.svg?branch=master
  :target: https://travis-ci.org/zalando-incubator/kubernetes-log-watcher

.. image:: https://codecov.io/gh/zalando-incubator/kubernetes-log-watcher/branch/master/graph/badge.svg
  :target: https://codecov.io/gh/zalando-incubator/kubernetes-log-watcher

Kubernetes Log Watcher is used to facilitate log shipping on a Kubernetes cluster. The watcher will detect containers running on a cluster node, and adjust configurations for number of log configuration agents. ``kubernetes-log-watcher`` is intended to run in a Kubernetes ``DaemonSet`` along with one or more log shippers.

``kubernetes-log-watcher`` comes with builtin configuration agents, however it could be extended to support external agents. Current builtin configuration agents are:

- AppDynamics
- Scalyr

``kubernetes-log-watcher`` is used in `kubernetes-on-aws <https://github.com/zalando-incubator/kubernetes-on-aws>`_ project.

Components
==========

Watcher
-------

Log watcher is responsible for detecting running containers on a cluster node, extract information from container labels, and supply sufficient information to configuration agents in order to facilitate log shipping. The log watcher could run with one or more configuration agents.

Configuration Agent
-------------------

The agent acts as a plugin, its sole purpose is to adjust log configuration for its log shipper. It is important to note that the configuration agent is not intended to process the logs, it only adjusts configuration files for log shipper (e.g. set log source paths and custom attributes with log events) based on information received from log watcher.

Features & Constraints
======================

* Log watcher accepts one or more log configuration agent.
* Log watcher will skip ``pause`` containers.
* Configuration agents provide the ability to dynamically attach tags/attributes/metadata to logs based on Kubernetes labels.
* Only containers running in Pods with at least ``application`` and ``version`` metadata labels will be considered for log watching.
* Sync new and stale containers.

Usage
=====

Kubernetes log watcher is intended to run in a ``DaemonSet`` along with one or more log processors (e.g. Scalyr, AppDynamics ...). The DaemonSet will ensure that the watcher is running on every cluster node.


Diagram
-------

The following diagram describes how Log watcher DaemonSet interacts with cluster node containers, Kubernetes API and Log Storage.

.. code-block::

                             +------------------------------------------------------+
    +--------------------+   |                         NODE                         |   +--------------------+
    |       K8s API      |   |  +----------------+              +----------------+  |   |    Log Storage     |
    |                    |   |  |     POD 1      |              |     POD 2      |  |   |                    |
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
              |              |  | Log watcher POD (DaemonSet)           |     | |   |             |
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

    - This manifest assumes running a Kubernetes cluster version > 1.5 (as it depends on `initContainer <https://kubernetes.io/docs/concepts/workloads/pods/init-containers/>`_ for initial Scalyr configuration)
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
          version: v0.11
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
              version: v0.11
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
                  "args": [
                    "if [ ! -f /mnt/scalyr/agent.json ]; then
                      echo {
                        \\\"import_vars\\\": [\\\"WATCHER_SCALYR_API_KEY\\\", \\\"WATCHER_CLUSTER_ID\\\"],
                        \\\"server_attributes\\\": {\\\"serverHost\\\": \\\"\\$WATCHER_CLUSTER_ID\\\"},
                        \\\"implicit_agent_process_metrics_monitor\\\": false,
                        \\\"implicit_metric_monitor\\\": false,
                        \\\"api_key\\\": \\\"\\$WATCHER_SCALYR_API_KEY\\\",
                        \\\"monitors\\\": [],
                        \\\"logs\\\": []
                        } > /mnt/scalyr/agent.json;
                        echo Updated agent.json to inital configuration;
                    fi
                    && cat /mnt/scalyr/agent.json;
                    test -f /mnt/scalyr-checkpoint/checkpoints.json && ls -lah /mnt/scalyr-checkpoint/checkpoints.json && cat /mnt/scalyr-checkpoint/checkpoints.json"
                  ],
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
              image: registry.opensource.zalan.do/eagleeye/kubernetes-log-watcher:0.12
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
              - name: WATCHER_SCALYR_API_KEY
                value: "<SCALYR-KEY-HERE>"
              - name: WATCHER_SCALYR_DEST_PATH
                value: /mnt/scalyr-logs
              - name: WATCHER_SCALYR_CONFIG_PATH
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

              env:
              # Note: added for scalyr-config, but not needed by the scalyr-agent itself.
              - name: WATCHER_SCALYR_API_KEY
                value: "<SCALYR-KEY-HERE>"
              - name: WATCHER_CLUSTER_ID
                value: "kubernetes-cluster-1"

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

- ``WATCHER_CONTAINERS_PATH``: Containers directory path mounted from the host (Default: ``/var/lib/docker/containers``)
- ``WATCHER_AGENTS``: Comma separated string of required log processor agents. (Required. Example: "scalyr,appdynamics")
- ``WATCHER_CLUSTER_ID``: Kubernetes Cluster ID.
- ``WATCHER_KUBE_URL``: URL to API proxy service. Service is expected to handle authentication to the Kubernetes cluster. If set, then log-watcher will not use serviceaccount config.
- ``WATCHER_KUBERNETES_UPDATE_CERTIFICATES``: Call update-ca-certificates for Kubernetes service account ca.crt
- ``WATCHER_INTERVAL``: Polling interval (secs) for the watcher to detect containers changes. (Default: 60 sec)
- ``WATCHER_DEBUG``: Verbose output. (Default: False)

Scalyr configuration agent
^^^^^^^^^^^^^^^^^^^^^^^^^^

Configuration variables can be set via Env variables:

- ``WATCHER_SCALYR_API_KEY``: Scalyr API key. (Required).
- ``WATCHER_SCALYR_DEST_PATH``: Scalyr configuration agent will symlink containers logs in this location. This is to provide more friendly name for log files. Typical log file name for a container will be in the form ``<application>-<version>.log``. (Required).
- ``WATCHER_SCALYR_CONFIG_PATH``: Scalyr configuration file path. (Default: ``/etc/scalyr-agent-2/agent.json``)
- ``WATCHER_SCALYR_JOURNALD``: Scalyr should follow Journald logs. This is for node system processes log shipping (e.g. docker, kube) (Default: ``False``)
- ``WATCHER_SCALYR_JOURNALD_ATTRIBUTES``: Add attributes to Journald logs. By default ``cluster`` and ``node`` will be added by the configuration agent.
- ``WATCHER_SCALYR_JOURNALD_EXTRA_FIELDS``: Add extra Systemd Journald fields. Should be a JSON string. Example: '{"_COMM": "command"}'
- ``WATCHER_SCALYR_JOURNALD_PATH``: Journald logs path mounted from the host. (Default: ``/var/log/journald``)

AppDynamics configuration agent
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Configuration variables can be set via Env variables:

- ``WATCHER_APPDYNAMICS_DEST_PATH``: AppDynamics job files path. (Required).

AppDynamics configuration agent could also add ``app_name`` and ``tier_name`` if ``appdynamics_app`` and ``appdynamics_tier`` were set in Pod metadata labels.


Development
===========

Preferably create a Python 3.5 ``virtualenv``.

.. code-block:: bash

    $ pip install -r requirements.txt
    $ python -m kube_log_watcher --help

Tests
-----

You can use ``pytest``

.. code-block:: bash

    # test requirements
    $ pip install -U flake8 mock pytest pytest_cov codecov>=1.4.0

    $ py.test -v tests/
    $ flake8 .

or via ``tox``

.. code-block:: bash

    $ tox

Build
-----

Build docker image

.. code-block:: bash

    $ pip install -U scm-source
    $ scm-source
    $ docker build -t registry-write.opensource.zalan.do/eagleeye/kubernetes-log-watcher:<WATCHER_VERSION> .

TODO
====

- Support custom extra/external agents (e.g. ``kube-log-watcher --extra-agent /var/lib/custom-agent.py``)
- Support configuration from config files instead of env variables (e.g. ``kube-log-watcher --config /etc/kube-log-watcher/config.yaml``)
- Support extending (overriding) constraints (e.g. require ``application``, ``version`` and ``build`` labels to monitor the container)
- Support running kube-log-watcher as standalone (release to PyPi)
- Add more configuration agents (logstash, fluentd, etc ...)

All contributions are welcome :)

License
=======

The MIT License (MIT)

Copyright (c) 2016 Zalando SE, https://tech.zalando.com

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

