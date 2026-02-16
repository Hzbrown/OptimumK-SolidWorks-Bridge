r"""
export_to_solidworks_wrapper.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Python wrapper that calls the ExportToSolidWorks C# console app.

The C# exe lives at:
  code/ExportToSolidWorks/bin/x64/Debug/net48/ExportToSolidWorks.exe

Usage from notebook:
  from export_to_solidworks_wrapper import run as export_to_solidworks
  export_to_solidworks(step_path=r"D:\...\file.step")
"""

import os
import subprocess
import sys

# Resolve the path to the C# exe relative to this file
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_EXE_PATH = os.path.join(
    _THIS_DIR,
    "ExportToSolidWorks", "bin", "x64", "Debug", "net48",
    "ExportToSolidWorks.exe",
)


def run(step_path: str, center_at_origin: bool = True, visible: bool = True):
    """Open a STEP in SolidWorks and save as Kinematic_Skeleton.SLDASM.

    Parameters
    ----------
    step_path : str
        Absolute path to .step / .stp file.
    center_at_origin : bool
        (Reserved for future use — the C# exe always mates to origin.)
    visible : bool
        (Reserved for future use — the C# exe always runs visible.)

    Raises
    ------
    FileNotFoundError
        If the STEP file or the C# exe cannot be found.
    RuntimeError
        If the C# exe returns a non-zero exit code.
    """
    step_path = os.path.abspath(step_path)

    if not os.path.isfile(step_path):
        raise FileNotFoundError(f"STEP file not found: {step_path}")

    if not os.path.isfile(_EXE_PATH):
        raise FileNotFoundError(
            f"ExportToSolidWorks.exe not found at:\n  {_EXE_PATH}\n"
            f"Build it first:  cd code/ExportToSolidWorks && dotnet build"
        )

    cmd = [_EXE_PATH, step_path]

    print(f"Running: {os.path.basename(_EXE_PATH)} \"{step_path}\"")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=120,  # 2 min max for STEP import
    )

    # Stream stdout/stderr to the caller
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)

    if result.returncode != 0:
        raise RuntimeError(
            f"ExportToSolidWorks.exe exited with code {result.returncode}.\n"
            f"{result.stderr or result.stdout}"
        )

    out_path = os.path.join(
        os.path.dirname(step_path), "Kinematic_Skeleton.SLDASM"
    )
    return out_path


if __name__ == "__main__":
    run(r"D:\EV27 CAD\OptimumK Geometry\Static\3D\Kinematic_Skeleton.step")