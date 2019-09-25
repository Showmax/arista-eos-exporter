#!/usr/bin/env python
from setuptools import setup

setup(
    name='arista_eos_exporter',
    version='0.1.0',
    description='Arista EOS Exporter',
    author='Stefan Safar',
    author_email='stefan.safar@showmax.com',
    scripts=['main.py', 'handler.py', 'collector.py'],
)
