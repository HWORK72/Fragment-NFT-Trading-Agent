import asyncio
import logging
from src.fragment_agent.config import AgentSettings
from src.fragment_agent.logger import get_logger
from src.fragment_agent.supervisor import LiveTradingSupervisor

logger: logging.Logger = get_logger("FragmentMain")


async def run_agent() -> None:
    settings: AgentSettings = AgentSettings()
    supervisor: LiveTradingSupervisor = LiveTradingSupervisor(settings)
    try:
        await supervisor.start()
    except asyncio.CancelledError:
        pass
    finally:
        await supervisor.stop()


if __name__ == "__main__":
    try:
        asyncio.run(run_agent())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Application execution stopped cleanly by user signal.")