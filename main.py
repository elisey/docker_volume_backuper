from pathlib import Path

import yaml

from backuper import Backuper, Server


def load_servers_from_yaml(path: str) -> list[Server]:
    with Path(path).open() as f:
        config = yaml.safe_load(f)

    servers_data = config.get("servers")
    if servers_data is None:
        msg = "Servers configuration file (servers.yaml) is missing"
        raise RuntimeError(msg)

    return [
        Server(
            name=entry["name"],
            hostname=entry["hostname"],
            port=entry["port"],
            username=entry["username"],
            ssh_key_path=entry["ssh_key_path"],
        )
        for entry in servers_data
    ]


def main() -> None:
    servers = load_servers_from_yaml("servers.yaml")
    backuper = Backuper(servers)
    backuper.backup()


if __name__ == "__main__":
    main()
