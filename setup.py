#!/usr/bin/env python
import os
import re
from pathlib import Path

from setuptools import setup, find_packages

version = os.getenv("PACKAGE_VERSION", "0.0.1")

pattern = r"^\d+\.\d+\.\d+(?:-(?:dev|rc|alpha|beta|test)\d*)?$"
if not re.match(pattern, version):
    print("ERROR: PACKAGE_VERSION must be a valid format. Setting to 0.0.1.")
    version = "0.0.1"

this_dir = Path(__file__).parent
long_description = (this_dir / "README.md").read_text(encoding="utf-8")

setup(
    name="hdsemg-pipe",
    version=version,
    description="hdsemg-pipe package",
    author="Johannes Kasser",
    author_email="johanneskasser@outlook.de",
    url="https://github.com/johanneskasser/hdsemg-pipe",
    package_dir={"hdsemg_pipe": "hdsemg_pipe"},
    include_package_data=True,
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(include=["hdsemg_pipe", "hdsemg_pipe.*"]),
    install_requires=[
        "PyQt5>=5.15.0",
        "pyqt5-tools>=5.15.0; sys_platform == 'win32'",
        "matplotlib>=3.4.0",
        "numpy>=1.21.0",
        "scipy>=1.7.0",
        "pyinstaller>=6.11.0",
        "pandas>=1.3.5",
        "torch>=1.10.0",
        "requests>=2.26.0",
        "hdsemg-shared>=0.11.1",
        "hdsemg-select>=0.1.0",
        "pefile>=2023.2.7; sys_platform != 'win32'",
    ],
    python_requires=">=3.7",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    entry_points={
        "console_scripts": [
             "hdsemg-pipe=hdsemg_pipe.main:main",
        ],
    },
)
