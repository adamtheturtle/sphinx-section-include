"""Install the wheel and build an independent project without checkout
imports.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> None:
    """Install and exercise the wheel in a temporary consumer project."""
    root = Path(__file__).resolve().parents[1]
    (wheel,) = root.joinpath("dist").glob(pattern="*.whl")
    with tempfile.TemporaryDirectory() as directory:
        temp = Path(directory)
        _ = subprocess.run(
            args=[
                "uv",
                "venv",
                "--python",
                sys.executable,
                str(object=temp / "venv"),
            ],
            check=True,
        )
        python = (
            temp
            / "venv"
            / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        )
        _ = subprocess.run(
            args=[
                "uv",
                "pip",
                "install",
                "--python",
                str(object=python),
                str(object=wheel),
            ],
            check=True,
        )
        _ = shutil.copytree(src=root / "sample/source", dst=temp / "manual")
        _ = subprocess.run(
            args=[
                str(object=python),
                "-m",
                "sphinx",
                "-W",
                "-b",
                "html",
                "manual",
                "output",
            ],
            cwd=temp,
            check=True,
            env={
                key: value
                for key, value in os.environ.items()
                if key != "PYTHONPATH"
            },
        )
        output = (temp / "output/quickstart.html").read_text(encoding="utf-8")
        assert "Create a widget with a name." in output
        assert "Use a descriptive widget name." in output
        print("Installed-wheel build passed outside the checkout.")


if __name__ == "__main__":
    main()
