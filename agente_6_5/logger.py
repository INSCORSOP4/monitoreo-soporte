"""Logging estructurado del agente (§35 observabilidad)."""
import logging
import sys

from config import LOG_LEVEL


def _configurar() -> None:
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )


_configurar()


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
