import subprocess
from typing import Dict, Any


def run_command(command: str, timeout: int = 60, cwd: str | None = None) -> Dict[str, Any]:
    """Run a shell command and return output and exit status."""
    try:
        completed = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        return {
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    except subprocess.TimeoutExpired as e:
        return {"returncode": -1, "stdout": "", "stderr": f"Timeout: {e}"}
