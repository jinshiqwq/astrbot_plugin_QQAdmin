
from functools import wraps
import inspect
from typing import Awaitable, Callable, Any, AsyncGenerator, Dict, List, Optional, Union, cast
from enum import IntEnum
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from astrbot import logger
from .utils import get_ats


class PermLevel(IntEnum):
    """
    定义用户的权限等级。数字越小，权限越高。
    超管: 0
    群主: 1
    管理员: 2
    成员: 3
    未知/无权限: 4
    """

    SUPERUSER = 0
    OWNER = 1
    ADMIN = 2
    MEMBER = 3
    UNKNOWN = 4

    def __str__(self):
        if self == PermLevel.SUPERUSER:
            return "超管"
        elif self == PermLevel.OWNER:
            return "群主"
        elif self == PermLevel.ADMIN:
            return "管理员"
        elif self == PermLevel.MEMBER:
            return "成员"
        else:
            return "未知/无权限"

    @classmethod
    def from_str(cls, perm_str: str):
        mapping = {
            "超管": cls.SUPERUSER,
            "群主": cls.OWNER,
            "管理员": cls.ADMIN,
            "成员": cls.MEMBER,
            "未知": cls.UNKNOWN,
            "无权限": cls.UNKNOWN,
        }
        return mapping.get(perm_str, cls.UNKNOWN)



class PermissionManager:
    _instance: Optional["PermissionManager"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        superusers: Optional[List[str]] = None,
        perms: Optional[Dict[str, str]] = None,
    ):
        if self._initialized:
            return
        self.superusers = superusers or []
        if perms is None:
            raise ValueError("初始化必须传入 perms")
        self.perms: Dict[str, PermLevel] = {
            k: PermLevel.from_str(v) for k, v in perms.items()
        }
        self._initialized = True

    @classmethod
    def get_instance(
        cls,
        superusers: Optional[List[str]] = None,
        perms: Optional[Dict[str, str]] = None,
    ) -> "PermissionManager":
        if cls._instance is None:
            cls._instance = cls(superusers=superusers, perms=perms)
        return cls._instance

    async def get_perm_level(
        self, event: AiocqhttpMessageEvent, user_id: str | int
    ) -> PermLevel:
        group_id = event.get_group_id()
        if not group_id:
            return PermLevel.UNKNOWN
        if str(user_id) in self.superusers:
            return PermLevel.SUPERUSER

        info = await event.bot.get_group_member_info(
            group_id=int(group_id), user_id=int(user_id), no_cache=True
        )
        role = info.get("role", "unknown")
        return {
            "owner": PermLevel.OWNER,
            "admin": PermLevel.ADMIN,
            "member": PermLevel.MEMBER,
        }.get(role, PermLevel.UNKNOWN)

    async def perm_block(
        self,
        event: AiocqhttpMessageEvent,
        bot_perm: PermLevel,
        perm_key: str,
        check_at: bool = True,
    ) -> str | None:
        logger.debug(f"权限输入：{perm_key} {bot_perm}")

        user_level = await self.get_perm_level(event, user_id=event.get_sender_id())

        required_level = self.perms.get(perm_key)
        if required_level is None:
            logger.error(f"未配置权限项: {perm_key}")
            return "无法执行未知权限的操作"

        if user_level > required_level:
            return f"你没{required_level}权限"

        bot_level = await self.get_perm_level(event, user_id=event.get_self_id())
        if bot_level > bot_perm:
            return f"我没{bot_perm}权限"

        if check_at:
            for at_id in get_ats(event):
                at_level = await self.get_perm_level(event, user_id=at_id)
                if bot_level >= at_level:
                    return f"我动不了{at_level}"

        return None


def perm_required(
    bot_perm: PermLevel = PermLevel.ADMIN,
    perm_key: str | None = None,
    check_at: bool = True,
):
    """
    权限检查装饰器。
    :param perm_key: 可选。用户执行命令所需的最低权限键名，默认使用被装饰函数的函数名。
    :param bot_perm: Bot 执行此命令所需的最低权限等级。
    """

    def decorator(
        func: Callable[..., Union[AsyncGenerator[Any, Any], Awaitable[Any]]],
    ) -> Callable[..., AsyncGenerator[Any, Any]]:
        actual_perm_key = perm_key or func.__name__
        @wraps(func)
        async def wrapper(
            plugin_instance: Any,
            event: AiocqhttpMessageEvent,
            *args: Any,
            **kwargs: Any,
        ) -> AsyncGenerator[Any, Any]:
            perm_manager = PermissionManager.get_instance()

            # 仅限群聊
            if event.is_private_chat():
                yield event.plain_result("该功能仅限群聊使用")
                event.stop_event()
                return

            # 权限管理未初始化
            if not perm_manager._initialized:
                logger.error(f"PermissionManager 未初始化（尝试访问权限项：{perm_key}）")
                yield event.plain_result("内部错误：权限系统未正确加载")
                event.stop_event()
                return

            # 判断权限
            result = await perm_manager.perm_block(
                event, bot_perm=bot_perm, perm_key=actual_perm_key, check_at=check_at
            )
            if result:
                yield event.plain_result(result)
                event.stop_event()
                return

            # 执行原始方法
            if inspect.isasyncgenfunction(func):
                async for item in func(plugin_instance, event, *args, **kwargs):
                    yield item
            else:
                await cast(
                    Awaitable[Any], func(plugin_instance, event, *args, **kwargs)
                )

        return wrapper

    return decorator


