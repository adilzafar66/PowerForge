from redis import Redis

from powerforge_shared.config import get_settings


def redis_ready() -> bool:
    client: Redis | None = None
    try:
        client = Redis.from_url(
            get_settings().redis_url,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        return bool(client.ping())
    except Exception:
        return False
    finally:
        if client is not None:
            client.close()
