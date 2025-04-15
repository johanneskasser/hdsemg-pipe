#src/shared_logic/setup.py
import os

from setuptools import setup, find_packages

version = os.getenv("PACKAGE_VERSION", "0.0.1")

setup(
    name='hdsemg-shared',
    version=version,
    packages=find_packages(),
    install_requires=[
        "numpy",
        "scipy",
    ]
)