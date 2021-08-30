import logging


logger = logging.getLogger(f"func.{__name__}")


def log_message_from_another_file(message):
    logger.info(message)
