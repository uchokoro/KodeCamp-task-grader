import base64
import time
import docker

from typing import Any
from docker.models.containers import Container
from docker import errors as docker_errors


class CodeSandbox:
    """
    Provides an isolated Docker container environment for executing
    arbitrary trainee code safely.
    """

    def __init__(self, image: str = "python:3.12-slim"):
        # Stable timeout for Windows Docker Desktop
        self._client = docker.from_env(timeout=300)
        self._image = image
        self._ensure_image_exists()

    def _ensure_image_exists(self):
        """Checks if the docker image is local; if not, pulls it from Docker Hub."""
        try:
            self._client.images.get(self._image)
        except docker_errors.ImageNotFound:
            print(f"Image {self._image} not found locally. Pulling...")
            self._client.images.pull(self._image)

    @staticmethod
    def _poll_container_status(container: Container, timeout: int) -> int | None:
        # Polling Loop: Monitor container status
        start_time = time.time()
        exit_code = None  # noqa

        while time.time() - start_time < timeout:
            container.reload()

            if container.status == "exited":
                state = container.attrs.get("State", {})
                exit_code = state.get("ExitCode", -1)
                break

            time.sleep(0.5)  # Polling interval
        else:
            # Loop completed without the container exiting
            raise Exception(f"timeout: Code execution exceeded {timeout}s limit.")

        return exit_code

    def execute_python_snippet(
        self, code: str, timeout: int = 10, mem_limit: str = "128m"
    ) -> dict[str, Any]:
        """
        Executes a multiline Python string inside an isolated container and returns stdout/stderr.
        Uses Base64 encoding in the command string to bypass Windows stdin pipe issues.
        """
        container = None
        encoded_code = base64.b64encode(code.encode("utf-8")).decode("utf-8")
        command = [
            "python",
            "-c",
            f"import base64; exec(base64.b64decode('{encoded_code}').decode('utf-8'))",
        ]

        try:
            # Create a detached container with constraints
            container = self._client.containers.create(
                self._image,
                command=command,
                detach=True,
                mem_limit=mem_limit,
                memswap_limit=mem_limit,  # Security: Disable disk swapping to prevent slow-downs
                network_disabled=True,  # Security: No internet access
                cpu_quota=50000,  # Security: 50% of 1 CPU
            )

            container.start()
            exit_code = self._poll_container_status(container, timeout)

            # Fetch output logs
            stdout = container.logs(stdout=True, stderr=False).decode("utf-8")
            stderr = container.logs(stdout=False, stderr=True).decode("utf-8")

            return {
                "exit_code": exit_code,
                "stdout": stdout,
                "stderr": stderr,
                "status": "success",
            }

        except Exception as e:
            # Categorize the error for the Agent's reflexive logic
            error_msg = str(e)
            error_type = (
                "timeout" if "timeout" in error_msg.lower() else "execution_error"
            )
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": error_msg,
                "status": error_type,
            }
        finally:
            if container:
                try:
                    container.remove(force=True)
                except Exception as e:  # noqa
                    print(f"Failed to remove container.\n{e}")

    def execute_python_file(
        self, file_path: str, timeout: int = 10, mem_limit: str = "128m"
    ) -> dict[str, Any]:
        """
        Reads a local .py file and executes its content within the sandbox.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                code = f.read()

            return self.execute_python_snippet(
                code=code, timeout=timeout, mem_limit=mem_limit
            )

        except FileNotFoundError:
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Error: The file at {file_path} was not found.",
                "status": "execution_error",
            }
        except Exception as e:
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Failed to read or execute file: {str(e)}",
                "status": "execution_error",
            }

    def execute_python_module(
        self,
        module_path: str,  # Path to the directory or the main .py file
        timeout: int = 15,
        mem_limit: str = "128m",
    ) -> dict[str, Any]:
        """
        Executes a local Python file as a module within the sandbox.
        Handles directory mounting to allow for local imports.
        """
        import os

        # Resolve absolute paths for Windows Docker compatibility
        abs_path = os.path.abspath(module_path)
        if os.path.isfile(abs_path):
            workdir = os.path.dirname(abs_path)
            target_file = os.path.basename(abs_path)
        else:
            workdir = abs_path
            target_file = "main.py"  # Default entry point

        container = None

        execution_logic = f"""
import sys
import os
sys.path.append('/app')
os.chdir('/app')
# Execute the target file
with open('{target_file}', 'r') as f:
    exec(f.read())
"""
        encoded_logic = base64.b64encode(execution_logic.encode("utf-8")).decode(
            "utf-8"
        )
        command = [
            "python",
            "-c",
            f"import base64; exec(base64.b64decode('{encoded_logic}').decode('utf-8'))",
        ]

        try:
            container = self._client.containers.create(
                self._image,
                command=command,
                detach=True,
                # Mount the host directory to /app in the container as Read-Only (ro)
                volumes={workdir: {"bind": "/app", "mode": "ro"}},
                mem_limit=mem_limit,
                memswap_limit=mem_limit,
                network_disabled=True,
                cpu_quota=50000,
            )

            container.start()
            exit_code = self._poll_container_status(container, timeout)

            stdout = container.logs(stdout=True, stderr=False).decode("utf-8")
            stderr = container.logs(stdout=False, stderr=True).decode("utf-8")

            return {
                "exit_code": exit_code,
                "stdout": stdout,
                "stderr": stderr,
                "status": "success",
            }

        except Exception as e:
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e),
                "status": "execution_error",
            }
        finally:
            if container:
                container.remove(force=True)
