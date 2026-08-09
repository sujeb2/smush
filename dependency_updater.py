import os
import re
import shutil
import subprocess
import sys


class DependencyUpdateError(RuntimeError):
    pass


def load_requirements(path):
    requirements = []
    with open(path, "r", encoding="utf-8") as file:
        for line in file:
            requirement = line.strip()
            if not requirement or requirement.startswith("#") or requirement.startswith("-"):
                continue
            requirements.append(requirement)
    return requirements


def requirement_name(requirement):
    name = re.split(r"[<>=!~;\[]", requirement, maxsplit=1)[0]
    return name.strip() or requirement


def python_executable():
    if "__compiled__" in globals():
        executable = shutil.which("python3") or shutil.which("python")
        if executable is None:
            raise DependencyUpdateError("Python executable was not found for dependency updates.")
        return executable
    return sys.executable


def update_dependencies(requirements_path, progress_callback, timeout=900):
    requirements = load_requirements(requirements_path)
    total = len(requirements)
    if total == 0:
        progress_callback(100, "NO DEPENDENCIES FOUND")
        return
    executable = python_executable()
    working_directory = os.path.dirname(os.path.abspath(requirements_path))
    progress_callback(0, "CHECKING DEPENDENCIES")
    for index, requirement in enumerate(requirements):
        name = requirement_name(requirement).upper()
        progress_callback(round(index / total * 100), f"UPDATING {name}")
        try:
            result = subprocess.run(
                [
                    executable,
                    "-m",
                    "pip",
                    "install",
                    "--upgrade",
                    "--disable-pip-version-check",
                    requirement,
                ],
                cwd=working_directory,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise DependencyUpdateError(f"{name}: {error}") from error
        if result.returncode != 0:
            output = result.stderr.strip() or result.stdout.strip() or "pip returned an unknown error"
            raise DependencyUpdateError(f"{name}: {output[-600:]}")
        progress_callback(round((index + 1) / total * 100), f"Checking: {name}")
    progress_callback(100, "DONE")
