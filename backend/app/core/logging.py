import logging


def setup_logger():

    logger = logging.getLogger(
        "ai_pr_reviewer"
    )

    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(

        "%(asctime)s | "
        "%(levelname)s | "
        "%(message)s"
    )

    console_handler = logging.StreamHandler()

    console_handler.setFormatter(
        formatter
    )

    if not logger.handlers:

        logger.addHandler(
            console_handler
        )

    return logger


logger = setup_logger()