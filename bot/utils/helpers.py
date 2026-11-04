"""Утилиты и вспомогательные функции"""
import re
from urllib.parse import parse_qs, urlsplit, urlunsplit


# Любая ссылка на reddit.com / redd.it внутри текста (схема необязательна).
# lookbehind не даёт зацепить "notreddit.com".
_REDDIT_URL_RE = re.compile(
    r"(?<![\w.-])(?:https?://)?(?:[\w-]+\.)?(?:reddit\.com|redd\.it)/[^\s<>\"']*",
    re.IGNORECASE,
)

# Поддерживаемые виды ссылок (проверяются без схемы).
# Поддомены reddit.com: www, old, new, m, np, sh, amp ...
_REDDIT_PATTERNS = [
    # пост в сабреддите или в профиле юзера
    r"^(?:[\w-]+\.)?reddit\.com/(?:r|u|user)/[\w-]+/comments/\w+",
    # пост без сабреддита
    r"^(?:[\w-]+\.)?reddit\.com/comments/\w+",
    r"^(?:[\w-]+\.)?reddit\.com/gallery/\w+",
    # share-ссылка из приложения Reddit (нужен редирект на пост)
    r"^(?:[\w-]+\.)?reddit\.com/(?:r|u|user)/[\w-]+/s/\w+",
    # просмотрщик медиа: reddit.com/media?url=https%3A%2F%2Fi.redd.it%2F...
    r"^(?:[\w-]+\.)?reddit\.com/media\?(?:.*&)?url=",
    # короткая ссылка на пост
    r"^redd\.it/\w+",
    # прямые ссылки на медиа
    r"^(?:i|v|preview)\.redd\.it/\w+",
]

# знаки препинания, которые прилипают к ссылке в конце фразы
_TRAILING_JUNK = ".,;:!?)]}»\"'"


def extract_reddit_url(text: str) -> str | None:
    """Находит первую поддерживаемую ссылку Reddit в тексте.

    Ссылка может быть в любом месте текста ("Глянь: https://..."),
    без схемы ("reddit.com/r/..."), с любым поддоменом.
    Возвращает ссылку с https:// или None.
    """
    if not text:
        return None
    for match in _REDDIT_URL_RE.finditer(text):
        candidate = match.group(0).rstrip(_TRAILING_JUNK)
        bare = re.sub(r"^https?://", "", candidate, flags=re.IGNORECASE)
        if any(re.match(p, bare, re.IGNORECASE) for p in _REDDIT_PATTERNS):
            return "https://" + bare
    return None


def is_reddit_url(text: str) -> bool:
    """Проверяет, есть ли в тексте ссылка на Reddit"""
    return extract_reddit_url(text) is not None


def clean_reddit_url(url: str) -> str:
    """Приводит ссылку к каноничному виду.

    - убирает query-параметры и мусор (?utm_source=..., ?share_id=...)
    - хост в нижний регистр (путь не трогаем: коды share-ссылок регистрозависимы)
    - reddit.com/media?url=... → ссылка из параметра url
    - preview.redd.it/<file> → i.redd.it/<file> (оригинал без подписи preview)
    """
    url = (url or "").strip()
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url

    parts = urlsplit(url)
    host = parts.netloc.lower()

    # просмотрщик медиа — настоящая ссылка лежит в параметре url
    if host.endswith("reddit.com") and parts.path.rstrip("/") == "/media":
        # parse_qs уже декодирует %3A%2F%2F
        inner = parse_qs(parts.query).get("url", [""])[0]
        if inner and inner != url:
            return clean_reddit_url(inner)

    if host == "preview.redd.it":
        host = "i.redd.it"

    path = parts.path.rstrip("/")
    return urlunsplit(("https", host, path, "", ""))


def is_share_url(url: str) -> bool:
    """share-ссылка (reddit.com/r/<sub>/s/<code>) — нужен редирект на пост"""
    return bool(re.search(r"reddit\.com/(?:r|u|user)/[\w-]+/s/\w+", url, re.IGNORECASE))


def is_direct_media_url(url: str) -> bool:
    """Прямая ссылка на картинку (i.redd.it) — пост и JSON API не нужны"""
    return bool(re.match(r"^https?://i\.redd\.it/\w+", url, re.IGNORECASE))


def extract_post_id(url: str) -> str | None:
    """Извлекает post ID из Reddit URL.

    v.redd.it / i.redd.it — это ID медиа, а не поста, поэтому их не трогаем.
    """
    patterns = [
        r"reddit\.com/(?:.*/)?comments/(\w+)",
        r"reddit\.com/gallery/(\w+)",
        r"(?<![\w.-])redd\.it/(\w+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            return match.group(1)
    return None
