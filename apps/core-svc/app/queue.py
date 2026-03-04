import json

from redis import Redis

from app.config import get_settings


settings = get_settings()
redis_client = Redis.from_url(settings.redis_url, decode_responses=True)


def publish_job(queue_name: str, payload: dict) -> None:
    redis_client.rpush(queue_name, json.dumps(payload))


def consume_job(queue_name: str, timeout_seconds: int = 5):
    item = redis_client.blpop(queue_name, timeout=timeout_seconds)
    if not item:
        return None
    _, raw = item
    return json.loads(raw)
