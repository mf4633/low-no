# Building the double-clickable Marchlands

The game is pure Python and has no dependencies, so this is packaging only:
nothing here changes how it plays.

## The short version

Most people do not need to build anything. Either:

* **Download `Marchlands.exe`** from the Releases page and double-click it. It
  opens the drawn game in your browser. Nothing is installed; your save lands
  in the same folder as the exe.
* **Or, if you have Python 3.9 or newer**, double-click `Marchlands.bat`
  (Windows) or `Marchlands.command` (macOS, Linux) in the `game/` folder.
  Same game, no download.

## Building one yourself

    pip install pyinstaller
    cd game
    pyinstaller packaging/marchlands.spec

The result is `dist/Marchlands.exe` (or `dist/Marchlands` elsewhere). Build it
on the platform you want it to run on -- PyInstaller does not cross-compile.

CI does this on every push that touches `game/`, on a Windows runner, and
attaches the exe to the release for any `marchlands-v*` tag.

## Cutting a release

Either push a `marchlands-v*` tag, or change one line:

    # game/marchlands/__init__.py
    __version__ = "0.4.0"

Push that and the same Windows build publishes `marchlands-v0.4.0` with the
exe attached. The second way exists because pushing a tag needs write access
to `refs/tags`, which a session that can push a branch does not necessarily
have -- the build already runs with `contents: write`, so it can do what the
person asking for the release cannot.

It fires on the commit that changes the version and only if that version has
no release yet, so neither ordinary work on the branch nor a re-run replaces
a build somebody has already downloaded. `pyproject.toml` reads the same
line, so there is one version number in the project and not two.

## The two things that make a frozen build different

**The page is somewhere else.** A one-file build unpacks itself into a
temporary directory and points `sys._MEIPASS` at it, so the static files are
not beside `web.py` any more. `web._static_dir()` looks there first and the
spec's `datas` puts them there. Get either wrong and the exe starts, serves a
path that does not exist, and shows a blank window.

**There is nowhere to print.** `console=False` means a traceback goes into the
void, and a crash is an icon that does nothing at all. `packaging/launch.py`
catches everything on the way out and shows it in a message box, falling back
to a `marchlands-error.txt` written beside the executable.

## Running the console game from a packaged build

    Marchlands.exe --terminal

It is the same game; it just spells the town out instead of drawing it.
