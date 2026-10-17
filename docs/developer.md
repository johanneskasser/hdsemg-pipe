# Development

```bash
git clone https://github.com/johanneskasser/hdsemg-pipe.git
cd hdsemg-pipe
pip install -r requirements.txt
pytest
mkdocs serve
```

## Layout

| Folder | Contents |
|---|---|
| `hdsemg_pipe/widgets/wizard` | One widget per step |
| `hdsemg_pipe/actions` | Processing code the steps call |
| `hdsemg_pipe/controller` | Restoring a working directory from disk |
| `hdsemg_pipe/state` | Global state shared between steps |
| `hdsemg_pipe/settings`, `config` | Preferences dialog and stored values |
| `hdsemg_pipe/updates` | Update checks |
| `hdsemg_pipe/scd_utils` | scd-edition conversion helpers |

## Writing a step

Subclass `WizardStepWidget`. Do heavy loading in `on_shown`, which runs when the user opens the step, and do it in a worker thread. If the step draws its own widgets, call `use_scoped_content_card()` so the card's frame styling does not leak into them. Qt resources are compiled with `pyrcc5 resources.qrc -o resources_rc.py`.

## Contributing

Open an issue first if the change is not small. Work on a branch, add a test for what you change, and open a pull request against `main`. Please include the Python version and operating system in bug reports.
