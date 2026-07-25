from __future__ import annotations

import time
from collections.abc import Iterator


WORD_DELAY_SECONDS = 0.05


def response_generator(response: str, *, delay_seconds: float = WORD_DELAY_SECONDS) -> Iterator[str]:
    """Yield an assistant response at a constant delay between words."""

    for word in response.split():
        yield f"{word} "
        time.sleep(delay_seconds)
