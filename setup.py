#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Setup file for K8S log watcher.
"""
import os

from setuptools import setup, find_packages


def read_version(package):
    data = {}
    with open(os.path.join(package, '__init__.py'), 'r') as fd:
        exec(fd.read(), data)
    return data['__version__']


def get_requirements(path):
    content = open(path).read()
    return [req for req in content.split('\\n') if req != '']


MAIN_PACKAGE = 'k8s_log_watcher'
VERSION = read_version(MAIN_PACKAGE)
DESCRIPTION = 'K8S log watcher'

CONSOLE_SCRIPTS = ['k8s-log-watcher=k8s_log_watcher.main:main']


setup(
    name='k8s-log-watcher',
    version=VERSION,
    description=DESCRIPTION,
    long_description=open('README.rst').read(),
    license=open('LICENSE').read(),
    packages=find_packages(exclude=['tests']),
    install_requires=get_requirements('requirements.txt'),
    setup_requires=['pytest-runner'],
    test_suite='tests',
    tests_require=['pytest', 'pytest_cov', 'mock==2.0.0'],
    entry_points={
        'console_scripts': CONSOLE_SCRIPTS
    },
    include_package_data=True,
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python',
        'Programming Language :: Python :: Implementation :: CPython',
        'Environment :: Console',
        'Operating System :: POSIX :: Linux',
        'Operating System :: MacOS :: MacOS X',
        'Topic :: System :: Monitoring',
        'Topic :: System :: Networking :: Monitoring',
    ]
)
