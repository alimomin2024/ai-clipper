"""Local schedule notifier; it never claims to publish to an external platform."""

import asyncio
import logging

from db.social_models import ScheduledPostModel

logger = logging.getLogger(__name__)


class SocialPublisherService:
    """Promote due local reminders to READY_TO_PUBLISH for a human handoff.

    Direct posting requires platform OAuth/API access and network connectivity. This
    offline build intentionally does not simulate successful uploads.
    """

    def __init__(self, poll_interval_sec: int = 30):
        self.poll_interval = poll_interval_sec
        self._is_running = False

    async def run_loop(self):
        self._is_running = True
        logger.info("Local publish scheduler started (manual platform handoff mode).")
        while self._is_running:
            try:
                for post in ScheduledPostModel.get_due_posts():
                    ScheduledPostModel.update_status(post["id"], "READY_TO_PUBLISH")
                    logger.info("Scheduled clip %s is ready for manual publishing.", post["clip_id"])
            except Exception:
                logger.exception("Local publish scheduler failed to update due reminders.")
            await asyncio.sleep(self.poll_interval)

    def stop(self):
        self._is_running = False
