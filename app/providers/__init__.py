from .base import EPISODE, LIVE, MOVIE, SERIES, Category, Item, Provider, ProviderError, make_session
from .m3u import M3UProvider
from .stalker import StalkerProvider, random_mac
from .xtream import XtreamProvider, parse_xtream_m3u_link

SECTIONS = (LIVE, MOVIE, SERIES)


def create_provider(profile, user_agent):
    t = profile.get("type")
    if t == "xtream":
        return XtreamProvider(profile, make_session(user_agent))
    if t == "stalker":
        return StalkerProvider(profile, make_session(user_agent))
    return M3UProvider(profile, make_session(user_agent))


__all__ = ["EPISODE", "LIVE", "MOVIE", "SERIES", "SECTIONS", "Category", "Item", "Provider",
           "ProviderError", "create_provider", "random_mac", "parse_xtream_m3u_link"]
