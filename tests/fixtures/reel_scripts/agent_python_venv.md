## Python Virtual Environments (venv)
Category: Dev & tools · Platform: instagram · Format: screen · Audience: beginner

### Voice-over
1. Two Python projects need different Django versions. Which one wins?
2. Share one Python, and the last install wins: 6.1 replaces 5.2.
3. The fix: a venv, a private package folder. Create one per project.
4. Activate it: python and pip, the installer, now use that folder.
5. Install Django 5.2 here. It lands only in this project.
6. Repeat in the other project with 6.1. Both versions now coexist.
7. Separate folders, separate versions. Follow @yourhandle for more Python basics.

### Shot list
| # | Heading | Caption | On screen | Code |
|---|---|---|---|---|
| 1 | TWO PROJECTS | blog wants *5.2*, shop wants *6.1* | Editor explorer with folders blog/ and shop/; both requirements.txt files open side by side (Django==5.2.18, Django==6.1.2); zoom on the two version lines, mid-frame | |
| 2 | NO VENV | The last install *wins* | Terminal with no venv active; run the install, zoom on pip's "Successfully uninstalled Django-5.2.18" line. If your pip refuses global installs, record this beat inside a throwaway venv | `pip install django==6.1.2` |
| 3 | MAKE A VENV | A private *folder* per project | Terminal in blog/; run the command; the explorer shows the new .venv folder (bin, lib, pyvenv.cfg) | `python3 -m venv .venv` |
| 4 | ACTIVATE IT | The prompt now starts with *(.venv)* | Zoom on the prompt changing to (.venv); small mid-frame note "Windows: .venv\Scripts\activate" | `source .venv/bin/activate` |
| 5 | INSTALL HERE | Lands in *this* project only | Prompt shows (.venv); highlight django-5.2.18 in pip's output | `pip install django==5.2.18` |
| 6 | BOTH COEXIST | *5.2* here, *6.1* there | Split terminal: blog/ prints 5.2.18, shop/ (its own .venv, active) prints 6.1.2 | `python -m django --version` |
| 7 | ONE PER PROJECT | Separate folders, separate *versions* | Payoff card "One venv per project" in the middle of the frame, above the bottom 20% | |

### Hook options
1. Two Python projects need different Django versions. Which one wins? (recommended)
2. A Python virtual environment is just a folder you can delete.
3. Installing Python packages globally? Your projects end up sharing versions.

### Cheat sheet
- Use when: Starting a new project · Following a tutorial that pins versions · Trying a package without touching your main Python
- Trade-offs: Activate it in each new terminal · Can't be moved or copied: recreate it instead · Uses the Python version that created it
- Snippet:
```bash
python3 -m venv .venv
source .venv/bin/activate
# Windows: .venv\Scripts\activate
pip install django==6.1.2
pip freeze > requirements.txt
deactivate
```
- Comparison:

| Where pip installs | Folder | Shared by | Django versions |
|---|---|---|---|
| No venv | That Python's site-packages | All code run by that Python | One |
| `pip install --user` | Your user site-packages | Your code on that Python | One |
| venv | The project's .venv | One project | One per venv |

### Caption
Your old project and your new one shouldn't have to agree on one Django version.

A virtual environment (venv) is a folder inside your project with its own python and pip. Create it with python3 -m venv .venv, then activate it: source .venv/bin/activate on macOS and Linux, .venv\Scripts\activate on Windows. While it's active, pip install puts packages in that folder, so another project can use a different version. Type deactivate to leave it.

Don't copy or commit the .venv folder: its scripts point to absolute paths. Save pip freeze > requirements.txt instead and rebuild it with pip install -r requirements.txt.

Which package version clash caught you first?

#python #venv #pip #pythonforbeginners #learnpython

### Claims checked
- Installing Django 6.1.2 into an environment that has 5.2.18 uninstalls 5.2.18 ("the last install wins", "6.1 replaces 5.2"): ran it in one shared environment; pip printed "Successfully uninstalled Django-5.2.18" and `python -m django --version` then printed 6.1.2.
- `pip install --user` also keeps one version: ran it with PYTHONUSERBASE pointed at a sandbox; 6.1.2 uninstalled 5.2.18 the same way.
- Django 5.2.18 and 6.1.2 are real releases and both support Python 3.13: PyPI JSON API (5.2.18 and 6.1.2 uploaded 2026-10-06; requires_python >=3.10 and >=3.12); installed both on Python 3.13.17.
- `python3 -m venv .venv` creates a folder with bin, lib, pyvenv.cfg (and, on Python 3.13+, a .gitignore): ran it and listed the folder; Python docs (library/venv, 3.13 changes).
- Activating changes the prompt to (.venv) and makes `python` and `pip` resolve inside .venv: ran it; `which python pip` printed blog/.venv/bin/python and blog/.venv/bin/pip; docs say activation prepends the venv's bin to PATH.
- Packages installed in an active venv land only in that project: ran it; django exists in blog/.venv/lib/python3.13/site-packages and shop/.venv/..., and the system python3 raised ModuleNotFoundError for django.
- Both versions coexist: ran blog/.venv/bin/python and shop/.venv/bin/python -m django --version: 5.2.18 and 6.1.2.
- `deactivate` leaves the venv: ran it; `which python` returned /usr/bin/python.
- Windows activation is `.venv\Scripts\activate`: Python tutorial (Doc/tutorial/venv.rst, 3.13 branch: "On Windows, run: tutorial-env\Scripts\activate"); not run on Windows.
- A venv can't be moved or copied: copied a venv and removed the original; the copy's pip failed ("cannot execute: required file not found") because its shebang is an absolute path; Python docs say venvs are not movable or copyable and shouldn't be checked into source control.
- "A virtual environment is just a folder you can delete": Python docs call a venv a directory that is "disposable -- it should be simple to delete and recreate".
- A venv uses the Python version that created it: Python tutorial ("venv will install the Python version from which the command was run"); pyvenv.cfg recorded version = 3.13.17.
- The snippet works: ran all six lines in bash; requirements.txt contained asgiref==3.13.0, Django==6.1.2, sqlparse==0.6.0.

### Unverified
- none

### Validation
PASS: Python Virtual Environments (venv) (7 beats, 75 words, ~28 s)
(`python3 scripts/check.py reel-scripts/2026-10-30-python-venv.md`, no FAIL or WARN lines)
