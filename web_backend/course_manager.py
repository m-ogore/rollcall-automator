import os

try:
    from upstash_redis import Redis
    _redis_available = True
except ImportError:
    _redis_available = False

KV_KEY = "courses"

class CourseManager:
    def __init__(self):
        url   = os.environ.get("KV_REST_API_URL")
        token = os.environ.get("KV_REST_API_TOKEN")
        if _redis_available and url and token:
            self.redis = Redis(url=url, token=token)
            self._memory = None
        else:
            # Fallback: in-memory storage for local development
            self.redis = None
            self._memory = {}

    def add_course(self, name: str, url: str):
        if self.redis:
            self.redis.hset(KV_KEY, name, url)
        else:
            self._memory[name] = url

    def remove_course(self, name: str):
        if self.redis:
            self.redis.hdel(KV_KEY, name)
        else:
            self._memory.pop(name, None)

    def get_courses(self) -> dict:
        if self.redis:
            return self.redis.hgetall(KV_KEY) or {}
        return dict(self._memory)