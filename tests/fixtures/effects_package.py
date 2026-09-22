import logging
import os
import socket
import subprocess
import sys
import threading
import warnings
from pathlib import Path

root = Path(os.environ["IMPORT_EFFECTS_FIXTURE_DIR"])
(root / "created").mkdir(exist_ok=True)
(root / "created" / "effect.txt").write_text("observed", encoding="utf-8")
(root / "renamed.txt").unlink(missing_ok=True)
(root / "rename-source.txt").write_text("rename", encoding="utf-8")
(root / "rename-source.txt").rename(root / "renamed.txt")
(root / "delete.txt").write_text("delete", encoding="utf-8")
(root / "delete.txt").unlink()

sock = socket.socket()
sock.settimeout(0.05)
try:
    sock.connect(("127.0.0.1", 9))
except OSError:
    pass
finally:
    sock.close()

subprocess.run(
    [sys.executable, "-c", "pass"],
    check=True,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)

thread = threading.Thread(target=lambda: None, name="fixture-worker")
thread.start()
thread.join()

os.environ["IMPORT_EFFECTS_CHANGED"] = "secret-value-never-reported"
os.chdir(root)
logging.getLogger("fixture").addHandler(logging.NullHandler())
warnings.filterwarnings("ignore", category=UserWarning)
sys.path.append("fixture-added-path")
