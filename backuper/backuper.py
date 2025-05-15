import sys
from contextlib import contextmanager
from pathlib import Path

import paramiko

from loguru import logger

from .server import Server
from .server_backuper import ServerBackuper

logger.remove()
logger.add(sys.stderr, level="INFO", colorize=True,
           format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {message}")


class Backuper:
    def __init__(self, servers: list[Server]) -> None:

        self.servers = servers
        self.local_backup_dir = Path("backup")

    @contextmanager
    def ssh_client(self, server: Server):
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
        try:
            yield ssh_client
        finally:
            ssh_client.close()

    def backup(self) -> None:
        logger.info(f"🗜️ Backing up servers:")
        for server in self.servers:
            logger.info(f"  • {server.name}")

        for server in self.servers:
            logger.info(f"▶️ Backing up {server.name} server")

            with self.ssh_client(server) as ssh_client:
                server_backuper = ServerBackuper(ssh_client, self.local_backup_dir)
                server_backuper.backup_server(server.name)

        logger.success(f"✅ All servers have been backed up to {self.local_backup_dir}")
