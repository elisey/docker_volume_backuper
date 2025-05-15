import sys
from datetime import datetime
from pathlib import Path

import paramiko
from paramiko.client import SSHClient
from scp import SCPClient
from loguru import logger

from .server import Server

logger.remove()
logger.add(sys.stderr, level="INFO", colorize=True, format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {message}")

class Backuper:
    def __init__(self, servers: list[Server]) -> None:
        self.ssh_client: SSHClient = None
        self.servers = servers
        self.REMOVE_BACKUP_DIR = "/home/www/backups"
        self.LOCAL_BACKUP_DIR = "backup"

    def __create_ssh_client(self, server: Server) -> SSHClient:

        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh_client.connect(
            hostname=server.hostname,
            port=server.port,
            username=server.username,
            key_filename=server.ssh_key_path,
            look_for_keys=True,
            allow_agent=True
        )
        return ssh_client

    def __exec_command_sync(self, command: str) -> list[str]:
        stdin, stdout, stderr = self.ssh_client.exec_command(command)
        exit_status = stdout.channel.recv_exit_status()  # Waits for command to finish

        if exit_status != 0:
            error_output = stderr.read().decode().strip()
            std_output = stdout.read().decode().splitlines()
            raise RuntimeError(f"Command '{command}' failed with exit code {exit_status}.\nError output:\n{error_output}\nStd output:\n{std_output}")

        return stdout.read().decode().splitlines()

    def __list_docker_volumes(self):
        command = "docker volume ls -q"
        return self.__exec_command_sync(command)

    def __save_remove_volume_to_tar(self, volume_name: str) -> Path:
        """Save each volume to a tar file on the remote machine."""

        uid = self.__exec_command_sync("id -u")[0]
        gid = self.__exec_command_sync("id -g")[0]

        filename = f"{volume_name}.tar.gz"
        #command = f'docker run --rm --user {uid}:{gid} -v {volume_name}:/backup/data -v {self.REMOVE_BACKUP_DIR}:/archive --env BACKUP_FILENAME="{filename}" --entrypoint backup offen/docker-volume-backup:v2'
        command = f'docker run --rm -v {volume_name}:/backup/data -v {self.REMOVE_BACKUP_DIR}:/archive --env BACKUP_FILENAME="{filename}" --entrypoint backup offen/docker-volume-backup:v2'

        self.__exec_command_sync(command)
        return Path(self.REMOVE_BACKUP_DIR) / filename

    def __fetch_tar_file(self, filepath: Path, dest_dir: Path):
        """Fetch the tar file from the remote machine to the local machine."""
        with SCPClient(self.ssh_client.get_transport()) as scp:
            scp.get(filepath, str(dest_dir))

    def __delete_remote_file(self, filepath: Path):
        command = f'rm {filepath}'
        self.__exec_command_sync(command)

    def __get_local_backup_dir(self, hostname: str) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = Path(self.LOCAL_BACKUP_DIR) / f"{hostname}_{timestamp}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        return backup_dir

    def __create_remote_backup_dir(self) -> None:
        command = f'mkdir -p "{self.REMOVE_BACKUP_DIR}"'
        self.__exec_command_sync(command)

    def __backup_server(self, server: Server) -> None:
        local_backup_dir = self.__get_local_backup_dir(server.name)
        logger.debug(f"Starting backing up to {local_backup_dir}")
        self.ssh_client = self.__create_ssh_client(server)

        try:
            logger.debug(f"Create remove backup dir {self.REMOVE_BACKUP_DIR}")
            self.__create_remote_backup_dir()

            volumes = self.__list_docker_volumes()
            logger.info(f"Found Docker volumes:")
            for volume in volumes[:1]:
                logger.info(f"  • {volume}")

            for volume in volumes:
                logger.opt(colors=True).info(f"Backing volume <blue>{volume}</blue> on remote")
                filepath = self.__save_remove_volume_to_tar(volume)

                logger.debug(f"Fetch {filepath}")
                self.__fetch_tar_file(filepath, local_backup_dir)

                logger.debug(f"Deleting tar file {filepath} on remote")
                self.__delete_remote_file(filepath)

            logger.opt(colors=True).success(f"✅ All volumes from <blue>{server.name}</blue> have been backed up to {local_backup_dir}")

        finally:
            self.ssh_client.close()
            self.ssh_client = None

    def backup(self) -> None:
        logger.info(f"🗜️ Backing up servers:")
        for server in self.servers:
            logger.info(f"  • {server.name}")
        for server in self.servers[:1]:
            logger.info(f"▶️ Backing up {server.name} server")
            self.__backup_server(server)
        logger.success(f"✅ All servers have been backed up to {self.LOCAL_BACKUP_DIR}")