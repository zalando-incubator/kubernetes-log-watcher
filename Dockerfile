FROM registry.opensource.zalan.do/stups/python:3.5.2-38

RUN apt-get update && apt-get install -y python3-dev libffi-dev libssl-dev

COPY . /watcher

WORKDIR /watcher

RUN python setup.py install

CMD ["kube-log-watcher"]
