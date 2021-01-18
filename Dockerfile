FROM registry.opensource.zalan.do/library/python-3.8-slim:3.8-slim-20201005

RUN apt-get update && apt-get install -y python3-dev libffi-dev libssl-dev

COPY . /watcher

WORKDIR /watcher

RUN pip install .

CMD ["kube-log-watcher"]
