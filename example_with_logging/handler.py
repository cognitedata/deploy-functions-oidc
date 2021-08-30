import logging

from cognite.logger import configure_logger

from another_file import log_message_from_another_file


# Configure application logger (only done ONCE):
configure_logger(logger_name="func", log_json=False, log_level="INFO")

# The following line must be added to all python modules (after imports):
logger = logging.getLogger(f"func.{__name__}")


def handle():
    logger.info("Log message using 'info'")
    logger.warning("Log message using 'warning'")
    logger.error("Log message using 'error'")

    log_message_from_another_file("A polite, but brief message")
