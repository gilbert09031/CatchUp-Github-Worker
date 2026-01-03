import logging
import asyncio
from faststream import FastStream
from faststream.rabbit import RabbitBroker

from src.config.settings import get_settings
from src.consumers.repository_consumer import router as repo_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("catchup_server")

settings = get_settings()

broker = RabbitBroker(settings.RABBITMQ_URL)

broker.include_router(repo_router)

app = FastStream(broker)

@app.after_startup
async def test_connection():
    logger.info(f"FastStream Server Started in [{settings.APP_ENV}] mode")
    logger.info(f"RabbitMQ Target: {settings.RABBITMQ_URL}")
    logger.info("waiting for messages...")

if __name__ == "__main__":
    asyncio.run(app.run())