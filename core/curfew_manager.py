import asyncio
from datetime import datetime, time, timedelta, timezone
from typing import Optional

from aiocqhttp import CQHttp
from astrbot import logger

# 创建北京时区对象 (UTC+8)
BEIJING_TIMEZONE = timezone(timedelta(hours=8))


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
        self._active = False  # 添加活动状态标志

        try:
            # 解析为无时区的time对象
            self.start_time: time = datetime.strptime(start_time_str, "%H:%M").time()
            self.end_time: time = datetime.strptime(end_time_str, "%H:%M").time()
        except ValueError as e:
            logger.error(f"宵禁时间格式错误 for group {group_id}: {e}", exc_info=True)
            raise ValueError("宵禁时间格式必须是 HH:MM") from e

        logger.info(
            f"群 {self.group_id} 的宵禁管理器初始化成功，北京时间段：{start_time_str}~{end_time_str}"
        )

    def is_running(self) -> bool:
        """检查宵禁任务是否正在运行。"""
        return self.curfew_task is not None and not self.curfew_task.done()

    async def start_curfew_task(self):
        """启动宵禁后台调度任务。"""
        if self.is_running():
            logger.warning(f"群 {self.group_id} 的宵禁任务已在运行，无需重复启动。")
            return

        if self._active:
            logger.warning(f"群 {self.group_id} 的宵禁任务已激活，无需重复启动。")
            return

        self._active = True
        self.curfew_task = asyncio.create_task(self._scheduler_loop())
        logger.info(f"群 {self.group_id} 的宵禁任务已启动。")

    async def stop_curfew_task(self):
        """停止宵禁后台调度任务。"""
        if not self._active:
            logger.warning(f"群 {self.group_id} 的宵禁任务未运行，无需停止。")
            return

        self._active = False

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
        """宵禁后台调度器，使用时间差计算代替循环检查"""
        logger.info(
            f"群 {self.group_id} 宵禁调度循环开始，北京时间段：{self.start_time.strftime('%H:%M')}~{self.end_time.strftime('%H:%M')}"
        )

        try:
            while self._active:
                # 获取当前北京时间 (UTC+8)
                current_dt = datetime.now(BEIJING_TIMEZONE)
                today = current_dt.date()           # 每次循环都重新取“今天”
                start_dt = datetime.combine(today, self.start_time).replace(tzinfo=BEIJING_TIMEZONE)
                end_dt   = datetime.combine(today, self.end_time).replace(tzinfo=BEIJING_TIMEZONE)

                # 处理跨天宵禁逻辑
                if self.start_time >= self.end_time:
                    # 如果结束时间在第二天，则加一天
                    end_dt += timedelta(days=1)

                # 判断是否在宵禁时段内
                is_during_curfew = start_dt <= current_dt < end_dt

                # 计算下次检查时间 - 使用更智能的时间差计算
                if is_during_curfew:
                    next_check = min(end_dt - current_dt, timedelta(seconds=60))
                    if not self.whole_ban_status:
                        await self._enable_curfew()
                else:
                    # 计算到宵禁开始的时间
                    if current_dt < start_dt:
                        next_check = start_dt - current_dt
                    else:
                        # 如果当前时间已超过结束时间，计算到明天的开始时间
                        next_check = (start_dt + timedelta(days=1)) - current_dt

                    if self.whole_ban_status:
                        await self._disable_curfew()

                # 确保等待时间至少1秒，不超过1小时
                sleep_time = max(
                    timedelta(seconds=1), min(next_check, timedelta(hours=1))
                )
                await asyncio.sleep(sleep_time.total_seconds())

        except asyncio.CancelledError:
            # 任务被取消，正常退出
            logger.info(f"群 {self.group_id} 的宵禁任务被取消")
            raise
        except Exception as e:
            logger.error(
                f"群 {self.group_id} 宵禁任务发生未处理异常: {e}", exc_info=True
            )
        finally:
            self._active = False
            self.curfew_task = None

    async def _enable_curfew(self):
        """启用宵禁（内部方法）"""
        try:
            await self.bot.send_group_msg(
                group_id=int(self.group_id),
                message=f"【{self.start_time.strftime('%H:%M')}】本群宵禁开始！",
            )
            await self.bot.set_group_whole_ban(group_id=int(self.group_id), enable=True)
            self.whole_ban_status = True
            logger.info(f"群 {self.group_id} 已开启全体禁言。")
        except Exception as e:
            logger.error(f"群 {self.group_id} 宵禁开启失败: {e}", exc_info=True)

    async def _disable_curfew(self):
        """禁用宵禁（内部方法）"""
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
            logger.error(f"群 {self.group_id} 宵禁解除失败: {e}", exc_info=True)
