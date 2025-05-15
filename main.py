import yaml

from backuper import Backuper, Server


def load_servers_from_yaml(path: str) -> list[Server]:
    with open(path) as f:
        config = yaml.safe_load(f)

    servers_data = config.get("servers")
    if servers_data is None:
        raise Exception("Servers configuration file (servers.yaml) is missing")

    servers = [
        Server(
            name=entry["name"],
            hostname=entry["hostname"],
            port=entry["port"],
            username=entry["username"],
            ssh_key_path=entry["ssh_key_path"],
        )
        for entry in servers_data
    ]

    return servers


def main():
    servers = load_servers_from_yaml("servers.yaml")
    backuper = Backuper(servers)
    backuper.backup()


if __name__ == "__main__":
    main()
