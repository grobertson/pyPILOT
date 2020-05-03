# -*- coding: utf-8 -*-
from setuptools import setup, find_packages

with open('README.rst') as f:
    readme = f.read()

with open('LICENSE') as f:
    license = f.read()

setup(
    name='pyPILOT',
    version='0.1.0',
    description='',
    long_description=readme,
    author='F. G. Robertson',
    author_email='me@grantrobertson.com.com',
    url='https://github.com/grobertson/pyPILOT/',
    license=license,
    packages=find_packages(exclude=('tests', 'docs'))
)

