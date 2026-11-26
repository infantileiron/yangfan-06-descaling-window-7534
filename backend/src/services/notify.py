import logging

from redis.exceptions import RedisError

from src.config.settings import redis

WAKE_KEY = "workbench:wake"
logger = logging.getLogger(__name__)


def wake(job_id):
    try:
        with redis.pipeline() as commands:
            commands.lpush(WAKE_KEY, job_id)
            commands.ltrim(WAKE_KEY, 0, 99)
            commands.execute()
    except RedisError:
        logger.warning("Redis wake signal failed for %s. Worker will poll the database.", job_id)
