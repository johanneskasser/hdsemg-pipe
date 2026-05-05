# Update Notifications

hdsemg-pipe checks for updates of external tools on every startup and notifies you when newer versions are available.
The check runs in the background and does not block the application from loading.

## Tracked Tools

| Tool | Default source | Check method |
|---|---|---|
| **scd-edition** | [`AgneGris/scd-edition`](https://github.com/AgneGris/scd-edition) — `main` branch | Git commit comparison |
| **openhdemg** | [PyPI](https://pypi.org/project/openhdemg/) | Version comparison |
| **MUedit** | [`simonavrillon/MUedit`](https://github.com/simonavrillon/MUedit) — `main` branch | Git commit comparison |

## How Notifications Work

### scd-edition

scd-edition is installed directly from GitHub and does not yet have versioned releases.
When a new commit is detected on the tracked branch, hdsemg-pipe shows a dialog with two options:

- **Install latest main** — installs the latest commit from the tracked branch via `pip install --upgrade git+...`
- **Skip** — dismisses the dialog without updating

If the repository has released a stable version tag, a third button — **Install stable (vX.Y.Z)** — will appear.

The installed commit is read from the package's `direct_url.json` metadata so the comparison is exact.

!!! note
    After installing an update, restart hdsemg-pipe for the changes to take effect.

### openhdemg

openhdemg is a PyPI package. When a newer version is available a toast notification appears in the top-right corner of the window. The notification displays the installed and available versions.

To install the update manually:

```bash
pip install --upgrade openhdemg
```

### MUedit

MUedit is a MATLAB-based tool that is not installed as a Python package — it must be updated manually by downloading the latest code from GitHub.

When a new commit is detected on the tracked branch, a toast notification appears with the commit summary and a link to the repository.

hdsemg-pipe remembers the last-seen commit in `~/.hdsemg_pipe/update_cache.json`. You will only be notified once per new commit, not on every startup.

## Configuring a Custom Fork

If you work with a fork of any tracked tool you can configure hdsemg-pipe to track that fork instead of the upstream repository.

Go to **Settings → Preferences → Updates** and enter the fork's GitHub URL and the branch to track.

![Updates Settings Tab](../img/settings/updates_settings.png)

**Fields:**

- **Repository URL** — the full GitHub HTTPS URL of the fork, e.g. `https://github.com/myfork/MUedit`
- **Branch** — the branch name to track, e.g. `main` or `dev`

Click **Save** to persist the configuration. The override takes effect on the next startup.

To revert to the upstream default, clear both fields and click **Save**.

!!! warning
    When a fork is configured for scd-edition, the **Install latest main** button will install from the fork URL, not the upstream repository. Make sure you trust the fork before installing.

## Disabling Update Checks

Update checks are network requests and require internet access. If the check fails (e.g. no connection or GitHub API rate-limit reached) it silently does nothing — no error is shown.

There is currently no setting to disable update checks entirely. If you need to work offline regularly, set a fork URL pointing to a non-existent host — the check will time out quietly.

## Adding a New Tool (Developer Reference)

The update checker uses a registry of `ToolSpec` objects in `hdsemg_pipe/updates/update_checker.py`.
To track a new external tool, append one entry to `REGISTERED_TOOLS`:

```python
ToolSpec(
    key="my_tool",           # unique ID, used as config key and cache key prefix
    display_name="My Tool",  # shown in UI and notifications
    default_owner="github-owner",
    default_repo="repo-name",
    default_branch="main",   # set to None to use PyPI instead
    pypi_package=None,       # set package name for PyPI checks
    allows_fork=True,        # show fork config in Settings → Updates
)
```

The correct check function (`_make_github_commit_check`, `_make_pypi_check`, or a custom one) is injected automatically based on `default_branch` and `pypi_package`.

No other code changes are needed — the new tool will appear in **Settings → Updates** automatically.

For tools that require a custom upgrade dialog (like scd-edition), add a branch in `_handle_results()` in the same file.
