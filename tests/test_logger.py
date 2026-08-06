import logging
from logger import logger, setup_logger

def test_setup_logger_creates_handlers():
    handlers = logger.handlers
    
    has_file_handler = any(isinstance(h, logging.FileHandler) for h in handlers)
    has_stream_handler = any(isinstance(h, logging.StreamHandler) for h in handlers)
    
    assert has_file_handler, "FileHandler was not added to the logger"
    assert has_stream_handler, "StreamHandler was not added to the logger"

def test_setup_logger_singleton():
    logger1 = setup_logger()
    logger2 = setup_logger()
    
    assert logger1 is logger2
    assert len(logger1.handlers) == len(logger2.handlers)