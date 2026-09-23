import asyncio
from datetime import datetime, timezone

from bot.config import cfg
from bot.constants import MSG_CONVERTING, MSG_ERROR, MSG_PROCESSING, MSG_SUCCESS, progress_bar
from bot.database.db import db
from bot.utils.helpers import new_id


class JobManager:
    def __init__(self):
        self.semaphore = asyncio.Semaphore(cfg.max_concurrent_jobs)

    @property
    def busy(self):
        return self.semaphore.locked()

    async def start(self, token, user_id, chat_id, media_message_id, convert_fn):
        job_id = new_id()
        await db().create_job(job_id, token, user_id, chat_id, media_message_id)
        asyncio.create_task(self._run(job_id, token, user_id, chat_id, convert_fn))
        return job_id

    async def _run(self, job_id, token, user_id, chat_id, convert_fn):
        await db().update_job(job_id, status="running", progress=0)
        message_id = 0
        bot = None
        try:
            from bot.services.bot_registry import get_bot
            bot = get_bot()
            msg = await bot.send_message(chat_id, MSG_PROCESSING)
            message_id = msg.message_id
            await db().update_job(job_id, message_id=message_id)

            last_sent = [0]

            async def progress_cb(pct):
                nonlocal last_sent, message_id
                pct = max(0, min(100, int(pct)))
                await db().update_job(job_id, progress=pct)
                current = await db().get_job(job_id)
                current_msg = (current or {}).get("message_id") or 0
                if pct >= last_sent[0] + 5 or pct >= 100 or current_msg != message_id:
                    last_sent[0] = pct
                    text = MSG_SUCCESS if pct >= 100 else MSG_CONVERTING.format(
                        bar=progress_bar(pct), pct=pct)
                    use_msg = current_msg or message_id
                    try:
                        await bot.edit_message_text(text, chat_id=chat_id, message_id=use_msg)
                    except Exception:
                        try:
                            new_msg = await bot.send_message(chat_id, text)
                            message_id = new_msg.message_id
                            await db().update_job(job_id, message_id=message_id)
                        except Exception:
                            pass

            await self.semaphore.acquire()
            try:
                result = await convert_fn(progress_cb)
            finally:
                self.semaphore.release()

            await db().update_job(job_id, status="done", progress=100)
            await db().record_conversion(
                user_id, result.get("label", "conversion"),
                result.get("filename", ""), "ok",
                duration_ms=int(result.get("duration_ms", 0) * 1000),
            )
            current = await db().get_job(job_id)
            use_msg = (current or {}).get("message_id") or message_id
            try:
                await bot.edit_message_text(MSG_SUCCESS, chat_id=chat_id, message_id=use_msg)
            except Exception:
                pass
        except Exception as exc:
            import logging
            logging.getLogger(__name__).exception("Job %s failed", job_id)
            await db().update_job(job_id, status="failed", error=str(exc)[:400])
            current = await db().get_job(job_id)
            use_msg = (current or {}).get("message_id") or message_id
            if bot and use_msg:
                try:
                    await bot.edit_message_text(MSG_ERROR, chat_id=chat_id, message_id=use_msg)
                except Exception:
                    pass
            await db().record_conversion(user_id, "conversion", "", "failed", error=str(exc)[:400])


def _now_ts():
    return datetime.now(timezone.utc).timestamp()


job_manager = JobManager()