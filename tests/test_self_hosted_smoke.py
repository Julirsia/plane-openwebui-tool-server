from __future__ import annotations

import os

import pytest

from app.config import get_settings
from app.plane_client import PlaneClient


pytestmark = pytest.mark.skipif(
    os.getenv("PLANE_SMOKE_TEST") != "1",
    reason="Set PLANE_SMOKE_TEST=1 to run read-only Plane smoke tests.",
)


@pytest.mark.asyncio
async def test_self_hosted_read_only_smoke() -> None:
    client = PlaneClient(get_settings())
    try:
        project = await client.get_project()
        states = await client.list_states()
        labels = await client.list_labels()
        members = await client.list_project_members()
        work_items = await client.list_work_items(limit=5, offset=0)

        assert isinstance(project, dict)
        assert isinstance(states, list)
        assert isinstance(labels, list)
        assert isinstance(members, list)

        results = work_items.get("results", [])
        assert isinstance(results, list)
        if not results:
            pytest.skip("No work items available for identifier smoke lookup.")

        identifier = str(results[0]["identifier"])
        detail = await client.get_work_item_by_identifier(identifier)
        assert detail["identifier"] == identifier
    finally:
        await client.close()
