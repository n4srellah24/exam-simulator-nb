# Tests

These run the add-on against a real Anki collection (the `anki` and `aqt` packages) and open the real exam window in Qt WebEngine, with no visible window. The one stand-in is Anki's main window `mw`: a plain `QMainWindow` that holds the collection, the profile folder and the Tools menu.

```sh
python -m venv .venv && .venv/bin/pip install -r tests/requirements.txt
.venv/bin/python -m pytest -c tests/pytest.ini tests
```

On a Linux machine without a desktop, Qt WebEngine needs the EGL/GL system libraries (`libegl1`, `libgl1`, `libnss3`, …).

Leave `tests/` out of the `.ankiaddon` zip you upload to AnkiWeb.
