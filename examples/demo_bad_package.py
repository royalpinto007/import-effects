"""Intentionally noisy import used by the public demo."""

import os
import socket
import subprocess
import threading
from pathlib import Path

demo_directory = Path(os.environ.get("IMPORT_EFFECTS_DEMO_DIR", "/tmp/import-effects-demo"))
demo_directory.mkdir(parents=True, exist_ok=True)
(demo_directory / "state.json").write_text('{"ready": true}\n', encoding="utf-8")

connection = socket.socket()
connection.settimeout(0.05)
try:
    connection.connect(("127.0.0.1", 9))
except OSError:
    pass
finally:
    connection.close()

subprocess.run(
    ["git", "--version"],
    check=True,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)

worker = threading.Thread(target=lambda: None, name="background-worker")
worker.start()
worker.join()
