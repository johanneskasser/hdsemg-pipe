#src/shared_logic/setup.py
import os

from setuptools import setup, find_packages

version = os.getenv("PACKAGE_VERSION", "0.0.5")

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name='hdsemg_shared',
    version=version,
    packages=find_packages(),
    install_requires=[
        "numpy",
        "scipy",
    ],
    long_description=long_description,
    long_description_content_type="text/markdown",
)