
import asyncio
from datetime import datetime, time
from typing import Optional

from aiocqhttp import CQHttp
from astrbot import logger



class CurfewManager:
    """
    管理群组宵禁功能的类。
    每个 CurfewManager 实例负责一个群组的宵禁状态和调度。
    """

    def __init__(
        self,
        bot: CQHttp,
        group_id: str,
        start_time_str: str,
        end_time_str: str,
    ):
        self.bot = bot
        self.group_id = group_id
        self._start_time_str = start_time_str
        self._end_time_str = end_time_str
        self.curfew_task: Optional[asyncio.Task] = None
        self.whole_ban_status: bool = False

        try:
            self.start_time: time = datetime.strptime(start_time_str, "%H:%M").time()
            self.end_time: time = datetime.strptime(end_time_str, "%H:%M").time()
        except ValueError as e:
            logger.error(f"宵禁时间格式错误 for group {group_id}: {e}", exc_info=True)
            raise ValueError("宵禁时间格式必须是 HH:MM") from e

        logger.info(
            f"群 {self.group_id} 的宵禁管理器初始化成功，时间段：{start_time_str}~{end_time_str}"
        )

    def is_running(self) -> bool:
        """检查宵禁任务是否正在运行。"""
        return self.curfew_task is not None and not self.curfew_task.done()

    async def start_curfew_task(self):
        """启动宵禁后台调度任务。"""
        if self.is_running():
            logger.warning(f"群 {self.group_id} 的宵禁任务已在运行，无需重复启动。")
            return

        self.curfew_task = asyncio.create_task(self._scheduler_loop())
        logger.info(f"群 {self.group_id} 的宵禁任务已启动。")

    async def stop_curfew_task(self):
        """停止宵禁后台调度任务。"""
        if self.curfew_task and not self.curfew_task.done():
            self.curfew_task.cancel()
            try:
                await self.curfew_task  # 等待任务完成取消
            except asyncio.CancelledError:
                logger.info(f"群 {self.group_id} 的宵禁任务已成功取消。")
            except Exception as e:
                logger.error(
                    f"停止群 {self.group_id} 宵禁任务时发生异常: {e}", exc_info=True
                )
        self.curfew_task = None
        logger.info(f"群 {self.group_id} 的宵禁任务已停止。")

    async def _scheduler_loop(self):
        """宵禁后台调度器，每 10 秒检查一次条件并执行操作。"""
        logger.info(
            f"群 {self.group_id} 宵禁调度循环开始，时间段：{self.start_time.strftime('%H:%M')}~{self.end_time.strftime('%H:%M')}"
        )
        while True:
            await asyncio.sleep(10)  # 每10秒检查一次
            current_time = datetime.now().time()

            # 处理跨天宵禁逻辑 (例如 23:00 到 06:00)
            is_during_curfew = False
            if self.start_time < self.end_time:  # 宵禁在同一天
                is_during_curfew = self.start_time <= current_time <= self.end_time
            else:  # 宵禁跨越午夜
                is_during_curfew = (current_time >= self.start_time) or (
                    current_time <= self.end_time
                )

            if is_during_curfew:
                if not self.whole_ban_status:
                    try:
                        await self.bot.send_group_msg(
                            group_id=int(self.group_id),
                            message=f"【{self.start_time.strftime('%H:%M')}】本群宵禁开始！",
                        )
                        await self.bot.set_group_whole_ban(
                            group_id=int(self.group_id), enable=True
                        )
                        self.whole_ban_status = True
                        logger.info(f"群 {self.group_id} 已开启全体禁言。")
                    except Exception as e:
                        logger.error(
                            f"群 {self.group_id} 宵禁开启失败: {e}", exc_info=True
                        )
            else:
                if self.whole_ban_status:
                    try:
                        await self.bot.send_group_msg(
                            group_id=int(self.group_id),
                            message=f"【{self.end_time.strftime('%H:%M')}】本群宵禁结束！",
                        )
                        await self.bot.set_group_whole_ban(
                            group_id=int(self.group_id), enable=False
                        )
                        self.whole_ban_status = False
                        logger.info(f"群 {self.group_id} 已解除全体禁言。")
                    except Exception as e:
                        logger.error(
                            f"群 {self.group_id} 宵禁解除失败: {e}", exc_info=True
                        )
