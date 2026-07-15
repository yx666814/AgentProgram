import subprocess
import sys
import time
from pathlib import Path


def main() -> None:
    if len(sys.argv) >= 2 and sys.argv[1] == "child":
        time.sleep(60)
        return
    marker = Path(sys.argv[1])
    child = subprocess.Popen([sys.executable, __file__, "child"])
    marker.write_text(str(child.pid), encoding="ascii")
    time.sleep(60)


if __name__ == "__main__":
    main()
