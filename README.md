# StageFlow

StageFlow is a workflow/state-machine CLI for AI-assisted project work.
The current version relies on Claude Code hooks for stage-based tool and file
access enforcement.

Install StageFlow from this repository once, then use the global `stageflow`
command inside other project repositories that you want StageFlow to manage.

## Quick Install

Prerequisite: install Python 3.10 or newer first. Python 3.13 is recommended.

Run these commands from this StageFlow repository root, for example
`D:\Tool\stageflow`:

```powershell
py -0p
py -3.13 -m venv .venv
.\.venv\Scripts\activate
python -m pip install -U pip
python -m pip install -e .
python -m stageflow register
```

If Python 3.13 is not installed, replace `3.13` with any installed Python
3.10+ version shown by `py -0p`, for example:

```powershell
py -3.12 -m venv .venv
```

If the Windows Python launcher already defaults to a Python 3.10+ interpreter,
this is also fine:

```powershell
py -m venv .venv
```

Avoid using Python 2. If `python --version` or `py -0p` only shows Python 2,
install Python 3 first.

Restart your terminal, then verify:

```powershell
where.exe stageflow
stageflow --help
```

## Command Registration

`python -m stageflow register` creates lightweight wrapper commands such as:

```text
~/.local/bin/stageflow
~/.local/bin/stageflow.cmd
```

Those wrappers call the exact Python used during registration:

```text
<venv-python> -m stageflow
```

After registering from `.venv`, `stageflow` keeps using that `.venv` even when
you run it from other repositories.

Some agent runtimes, including Claude Code on some Windows setups, may not see
the same user PATH as your normal terminal. In an elevated Administrator
PowerShell, activate the same `.venv` and register the wrapper directory to the
system PATH:

```powershell
cd D:\Tool\stageflow
.\.venv\Scripts\activate
python -m stageflow register --machine
```

## Using StageFlow In A Project

Run these commands in the project repository you want StageFlow to manage, not
inside this StageFlow source repository.

```powershell
cd D:\Path\To\YourProject
stageflow init
stageflow start
stageflow status
stageflow next
stageflow editor
```

`stageflow init` creates StageFlow files for that target project. Do not run it
inside the StageFlow source checkout unless you intentionally want StageFlow to
manage its own repository.

## Registration Options

Run these after activating the `.venv` created in this repository.

```powershell
python -m stageflow register
python -m stageflow register --machine
python -m stageflow register --bin-dir D:\Tool\bin
python -m stageflow register --no-path
python -m stageflow register --build-editor
```

- `register`: create wrappers and add the wrapper directory to the user PATH.
- `--machine`: add the wrapper directory to the system PATH on Windows.
- `--bin-dir`: write wrappers to a specific command directory.
- `--no-path`: create wrappers but do not modify PATH.
- `--build-editor`: also run `npm install` and `npm run build` in `editor/`.
  This is only needed after changing frontend source files or if `editor/dist`
  was deleted.

Do not commit generated `stageflow.exe` files. They are local to one
machine/environment. Install the package and run `python -m stageflow register`
on each machine instead.
