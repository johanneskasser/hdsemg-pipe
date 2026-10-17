# Installation

Python 3.10+ is required. Use a virtual environment for organization.

## With pip

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install hdsemg-pipe
hdsemg-pipe
```

## With conda

Download `environment.yml` from the repository, then:

```bash
conda env create -f environment.yml
conda activate hdsemg-pipe
hdsemg-pipe
```

If conda cannot find `hdsemg-shared`, drop it from the file and run `pip install hdsemg-shared` afterwards.

## From source

```bash
git clone https://github.com/johanneskasser/hdsemg-pipe.git
cd hdsemg-pipe
pip install -r requirements.txt
cd hdsemg_pipe && pyrcc5 resources.qrc -o resources_rc.py && cd ..
python -m hdsemg_pipe.main
```

If your shell fails to locate `pyrcc5`, it is bundled with `pyqt5-tools`.

## First start

Open **Settings → Preferences** and pick a work folder. The same dialog installs hdsemg-select for you. openhdemg lives in its own environment, so enter its path there. MUedit needs MATLAB and its own entry under the MUEdit tab; scd-edition is optional.
