import logging
from dwellir_harvester.collectors.dummychain import DummychainCollector

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)
logger.info("Starting direct collector test")

try:
    collector = DummychainCollector()
    result = collector.collect()
    logger.info("Collection result: %s", result)
except Exception as e:
    logger.exception("Error during collection")
    raise