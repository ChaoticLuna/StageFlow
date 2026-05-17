# StageFlow

StageFlow is a declarative workflow/state-machine CLI for AI-assisted project work.

This README focuses on local source installation and global command registration.

## Quick Install

From the repository root:

```powershell
python -c "import sys; print(sys.executable)"
python -m pip install -e .
python -m stageflow register
```

The first command shows which Python will own this installation. `register`
then creates wrappers that keep using that same Python.

Some agent runtimes, including Claude Code in some Windows setups, may not
inherit the same user PATH as your normal terminal. If Claude Code cannot find
`stageflow`, run the registration from an elevated Administrator PowerShell and
write the wrapper directory to the system PATH:

```powershell
python -m stageflow register --machine
```

Restart your terminal, then verify:

```powershell
stageflow --help
stageflow init
stageflow editor
```

`pip install -e .` installs StageFlow into the Python environment that runs the
command. The `-e` flag means "editable": Python imports the live source checkout
instead of copying the package. Code changes in this repository are picked up
without reinstalling, unless packaging metadata changes.

## Which Python Is Used?

The Python in this command decides everything:

```powershell
python -m pip install -e .
```

If `python` resolves to Anaconda, StageFlow is installed into Anaconda. If it
resolves to a python.org install or a virtual environment, StageFlow is installed
there instead.

Check before installing:

```powershell
python -c "import sys; print(sys.executable)"
```

After installing:

```powershell
python -m pip show stageflow
python -c "import stageflow, sys; print(sys.executable); print(stageflow.__file__)"
```

## Recommended Stable Setup

For the fewest environment surprises, use a dedicated virtual environment based
on a normal python.org Python install:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\activate
python -m pip install -U pip
python -m pip install -e .
python -m stageflow register
```

Then restart the terminal and run:

```powershell
stageflow --help
```

## Anaconda And Special Environments

Anaconda can work, but it may behave differently from a standard Python install.
In particular, some tools that touch `tkinter`/Tcl/Tk may hit environment-specific
issues, especially when multiple Tk instances are created in one process.

If you see intermittent Tcl/Tk errors such as:

```text
Can't find a usable tk.tcl
Can't find a usable init.tcl
invalid command name tcl_findLibrary
```

prefer a clean python.org Python or venv, then reinstall and re-register:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\activate
python -m pip install -e .
python -m stageflow register
```

## Global Command Registration

`stageflow register` creates lightweight wrapper commands, Ralph-style:

```text
~/.local/bin/stageflow
~/.local/bin/stageflow.cmd
```

Those wrappers call the exact Python used during registration:

```text
<that-python> -m stageflow
```

So if you register from a venv, `stageflow` will use that venv. If you register
from Anaconda, `stageflow` will use Anaconda.

Options:

```powershell
python -m stageflow register
python -m stageflow register --build-editor
python -m stageflow register --machine
python -m stageflow register --bin-dir D:\Tool\bin
python -m stageflow register --no-path
```

- `register`: create wrappers and add the bin directory to the user PATH.
- `--build-editor`: also run `npm install` and `npm run build` in `editor/`.
  This is optional for normal source installs because the repository includes
  `editor/dist`, but it is useful after changing frontend source files or if the
  built editor files were deleted.
- `--machine`: add the bin directory to the system PATH on Windows. This usually
  requires an elevated administrator terminal.
- `--bin-dir`: write wrappers to a specific command directory.
- `--no-path`: create wrappers but do not modify PATH.

Do not commit a generated `stageflow.exe` to the repository. It is created by
the local Python installer for one machine/environment. The portable approach is
to install the package, then run `python -m stageflow register` on each machine.

## Basic Usage

Create a StageFlow project in the current directory:

```powershell
stageflow init
```

Start a run:

```powershell
stageflow start
```

Inspect and advance:

```powershell
stageflow status
stageflow next
```

Open the visual editor:

```powershell
stageflow editor
```

If the editor reports that the frontend is not built, run:

```powershell
python -m stageflow register --build-editor
```
