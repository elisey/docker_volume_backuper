import sys
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import paramiko
import tzlocal
from loguru import logger

from .server import Server
from .server_backuper import ServerBackuper

logger.remove()
logger.add(
    sys.stderr,
    level="INFO",
    colorize=True,
    format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {message}",
)


class Backuper:
    MAIN_BACKUP_DIR = Path("backup")

    def __init__(self, servers: list[Server]) -> None:
        self.servers = servers

    @contextmanager
    def ssh_client(self, server: Server) -> Generator[paramiko.SSHClient]:
        ssh_client: paramiko.SSHClient = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.RejectPolicy())
        ssh_client.connect(
            hostname=server.hostname,
            port=server.port,
            username=server.username,
            key_filename=server.ssh_key_path,
            look_for_keys=True,
            allow_agent=True,
        )
        try:
            yield ssh_client
        finally:
            ssh_client.close()

    def backup(self) -> None:
        logger.info("🗜️ Backing up servers:")
        for server in self.servers:
            logger.info(f"  • {server.name}")

        timestamp = datetime.now(tzlocal.get_localzone()).strftime("%Y-%m-%d_%H-%M-%S")
        backup_dir = self.MAIN_BACKUP_DIR / f"backup_{timestamp}"
        logger.info(f"Backup dir: {backup_dir}")

        for server in self.servers:
            logger.info(f"▶️ Backing up {server.name} server")

            with self.ssh_client(server) as ssh_client:
                server_backuper = ServerBackuper(ssh_client, backup_dir)
                server_backuper.backup_server(server.name)

        logger.success(f"✅ All servers have been backed up to {backup_dir}")
