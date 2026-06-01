#!/usr/bin/env python3
"""CLI для быстрой публикации без HTTP."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.services.publishers.registry import publish_to_platform


async def main() -> int:
    parser = argparse.ArgumentParser(description="MDSA Content Factory — быстрая публикация")
    parser.add_argument("--platform", default="vk", choices=["vk", "telegram"])
    parser.add_argument("--text", required=True, help="Текст поста")
    parser.add_argument("--link", default=None, help="Ссылка (для VK attachments)")
    parser.add_argument("--image-url", default=None, help="URL картинки из источника")
    args = parser.parse_args()

    result = await publish_to_platform(
        args.platform,
        args.text,
        link=args.link,
        image_url=args.image_url,
    )
    if result.success:
        print(f"OK: {result.post_url or result.external_id}")
        return 0

    print(f"ERROR: {result.error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
