"""Test configuration for Spa Booking component."""

import pytest

pytest_plugins = ["pytest_asyncio"]


@pytest.fixture(scope="session")
def event_loop():
    import asyncio

    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
