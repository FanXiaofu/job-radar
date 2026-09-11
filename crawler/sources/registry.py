"""数据源注册表：新增数据源时在这里 import 并加入列表。"""
import logging

logger = logging.getLogger(__name__)


def get_sources() -> list:
    from crawler.base import BaseSource

    sources = []
    for module_name, class_name in [
        ("crawler.sources.iguopin", "IguopinSource"),
        ("crawler.sources.nowcoder", "NowcoderSource"),
    ]:
        try:
            module = __import__(module_name, fromlist=[class_name])
            cls = getattr(module, class_name)
            instance = cls()
            if isinstance(instance, BaseSource):
                sources.append(instance)
        except ImportError as e:
            logger.warning("数据源 %s 不可用: %s", module_name, e)
    return sources
