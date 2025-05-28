import subprocess
import sys
from pathlib import Path

from loguru import logger
from paramiko.client import SSHClient
from scp import SCPClient
from tqdm import tqdm

logger.remove()
logger.add(
    sys.stderr,
    level="INFO",
    colorize=True,
    format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {message}",
)


class ServerBackuper:
    def __init__(
        self,
        ssh_client: SSHClient,
        local_backup_dir: Path,
        remote_backup_dir: Path,
    ) -> None:
        self.ssh_client: SSHClient = ssh_client
        self.remote_backup_dir = remote_backup_dir
        self.local_backup_dir = local_backup_dir

    def __exec_command_sync(self, command: str) -> list[str]:
        stdin, stdout, stderr = self.ssh_client.exec_command(command)
        exit_status = stdout.channel.recv_exit_status()
        output: list[str] = stdout.read().decode().splitlines()

        if exit_status != 0:
            error_output = stderr.read().decode().strip()

            msg = (
                f"Command '{command}' failed with exit code {exit_status}.\n"
                f"Error output:\n{error_output}\n"
                f"Std output:\n{output}"
            )
            raise RuntimeError(msg)

        return output

    def __list_docker_volumes(self) -> list[str]:
        command = "docker volume ls -q"
        return self.__exec_command_sync(command)

    def __save_remove_volume_to_tar(self, volume_name: str) -> Path:
        """Save each volume to a tar file on the remote machine."""
        filename = f"{volume_name}.tar.gz"
        command = (
            "docker run --rm "
            f"-v {volume_name}:/backup/data "
            f"-v {self.remote_backup_dir}:/archive "
            f'--env BACKUP_FILENAME="{filename}" '
            "--entrypoint backup "
            f"offen/docker-volume-backup:v2"
        )
        self.__exec_command_sync(command)
        return self.remote_backup_dir / filename

    def __fetch_tar_file(self, filepath: Path, dest_dir: Path) -> Path:
        """Fetch the tar file from the remote machine to the local machine with progress bar."""
        filename = filepath.name
        local_tar_path = dest_dir / filename

        progress_bar: tqdm | None = None

        def progress(_: str, size: int, sent: int) -> None:
            nonlocal progress_bar
            if progress_bar is None and size > 0:
                progress_bar = tqdm(
                    total=size,
                    unit="B",
                    unit_scale=True,
                    desc=f"Fetching {filename}",
                    leave=False,
                )
            if progress_bar:
                progress_bar.update(sent - progress_bar.n)

        with SCPClient(self.ssh_client.get_transport(), progress=progress) as scp:
            scp.get(str(filepath), str(dest_dir))

        if progress_bar:
            progress_bar.close()

        return local_tar_path

    def __verify_tar_file(self, tar_path: Path) -> None:
        try:
            subprocess.run(
                ["/usr/bin/tar", "-tzf", str(tar_path.absolute())],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            logger.debug(f"Verified tar file {tar_path} successfully.")
        except subprocess.CalledProcessError as e:
            msg = f"Verification failed for {tar_path}: {e.stderr.decode().strip()}"
            raise RuntimeError(msg) from e

    def __delete_remote_file(self, filepath: Path) -> None:
        command = f"rm {filepath}"
        self.__exec_command_sync(command)

    def __get_local_backup_dir(self, hostname: str) -> Path:
        backup_dir = self.local_backup_dir / hostname
        backup_dir.mkdir(parents=True, exist_ok=True)
        return backup_dir

    def __create_remote_backup_dir(self) -> None:
        command = f'mkdir -p "{self.remote_backup_dir}"'
        self.__exec_command_sync(command)

    def backup_server(self, server_name: str) -> None:
        local_backup_dir = self.__get_local_backup_dir(server_name)
        logger.debug(f"Starting backing up to {local_backup_dir}")
        logger.debug(f"Create remove backup dir {self.remote_backup_dir}")
        self.__create_remote_backup_dir()

        volumes = self.__list_docker_volumes()
        logger.info("Found Docker volumes:")
        for volume in volumes:
            logger.info(f"  • {volume}")

        for volume in volumes:
            logger.opt(colors=True).info(f"Backing volume <blue>{volume}</blue> on remote")
            filepath = self.__save_remove_volume_to_tar(volume)

            logger.debug(f"Fetch {filepath}")
            local_tar_path = self.__fetch_tar_file(filepath, local_backup_dir)
            self.__verify_tar_file(local_tar_path)

            logger.debug(f"Deleting tar file {filepath} on remote")
            self.__delete_remote_file(filepath)

        logger.opt(colors=True).success(
            f"✅ All volumes from <blue>{server_name}</blue> have been backed up to {local_backup_dir}"
        )
