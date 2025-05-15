from dataclasses import dataclass


@dataclass
class Server:
    name: str
    hostname: str
    port: int
    username: str
    ssh_key_path: str
