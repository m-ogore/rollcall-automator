# course_manager.py — uses Vercel KV (Redis) instead of courses.json
#
# Vercel KV gives you these env vars automatically when you link a KV store:
#   KV_REST_API_URL
#   KV_REST_API_TOKEN
#
# pip install upstash-redis

import os
from upstash_redis import Redis

KV_KEY = "courses"   # single Redis key that holds the whole courses dict as a hash

class CourseManager:
    def __init__(self):
        url   = os.environ.get("KV_REST_API_URL")
        token = os.environ.get("KV_REST_API_TOKEN")
        if not url or not token:
            raise RuntimeError(
                "KV_REST_API_URL and KV_REST_API_TOKEN must be set.\n"
                "In Vercel: Storage → Create KV store → link to project.\n"
                "Locally: add them to a .env file and load with python-dotenv."
            )
        self.redis = Redis(url=url, token=token)

    async def add_course(self, name: str, url: str):
        self.redis.hset(KV_KEY, name, url)

    async def remove_course(self, name: str):
        self.redis.hdel(KV_KEY, name)

    async def get_courses(self) -> dict:
        result = self.redis.hgetall(KV_KEY)
        return result or {}