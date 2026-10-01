import asyncio
import base64
import io
import os
import tarfile
from pathlib import PurePosixPath


class DockerRunner:
    def __init__(self, image, timeout=15):
        self.image, self.timeout = image, timeout
        # Some rootless/AppArmor Docker hosts reject every exec when this flag is set.
        # Keep it opt-in until the local Docker runtime is known to support it.
        self.no_new_privileges = os.getenv("SANDBOX_NO_NEW_PRIVILEGES", "false").lower() == "true"

    async def execute(self, code, inputs):
        return await asyncio.to_thread(self._execute_sync, code, inputs)

    def _execute_sync(self, code, inputs):
        import docker
        client = docker.from_env()
        container = None
        output_volume = None
        try:
            encoded = base64.b64encode(code.encode("utf-8")).decode("ascii")
            output_volume = client.volumes.create(labels={"ai-harness": "temporary-output"})
            options = dict(
                image=self.image, command=["python", "-c", "import base64,os;exec(compile(base64.b64decode(os.environ['HARNESS_CODE']),'artifact.py','exec'))"],
                environment={"HARNESS_CODE": encoded}, network_disabled=True, read_only=True,
                cap_drop=["ALL"], cap_add=["CHOWN", "SETUID", "SETGID"], pids_limit=64, mem_limit="128m",
                nano_cpus=500_000_000,
                tmpfs={"/tmp": "rw,noexec,nosuid,size=16m,uid=65534,gid=65534,mode=1777"},
                volumes={output_volume.name: {"bind": "/output", "mode": "rw"}},
            )
            if self.no_new_privileges:
                options["security_opt"] = ["no-new-privileges"]
            container = client.containers.create(**options)
            container.start()
            try:
                result = container.wait(timeout=self.timeout)
                logs = container.logs(stdout=True, stderr=True).decode("utf-8", errors="replace")[-4000:]
                exit_code, stdout, stderr = result["StatusCode"], logs if result["StatusCode"] == 0 else "", logs if result["StatusCode"] else ""
            except Exception:
                container.kill()
                return {"exit_code": 124, "stdout": "", "stderr": "Execution timed out", "outputs": []}
            outputs = []
            if exit_code == 0:
                stream, _ = container.get_archive("/output")
                archive_data = b"".join(stream)
                with tarfile.open(fileobj=io.BytesIO(archive_data)) as tar:
                    for member in tar.getmembers():
                        member_path = PurePosixPath(member.name)
                        if member.isfile() and len(member_path.parts) == 2 and member_path.parts[0] == "output" and member.size <= 1_000_000:
                            data = tar.extractfile(member).read()
                            outputs.append({"name": member_path.name, "content_base64": base64.b64encode(data).decode()})
            return {"exit_code": exit_code, "stdout": stdout, "stderr": stderr, "outputs": outputs}
        finally:
            if container is not None:
                container.remove(force=True)
            if output_volume is not None:
                output_volume.remove(force=True)
