"""Quickstart example for eve-api."""

import asyncio

from eve_api import EVEClient


async def main():
    async with EVEClient() as eve:
        # Login
        await eve.login("user@example.com", "password")

        # Fetch current user
        me = await eve.get("/users/me")
        print(f"Logged in as: {me['email']}")

        # List public collections
        collections = await eve.get("/collections/public")
        for col in collections["data"]:
            print(f"  - {col['name']}")

        # Create and delete a conversation
        conv = await eve.post("/conversations", json={"name": "Quick Test"})
        print(f"Created conversation: {conv['id']}")

        await eve.delete(f"/conversations/{conv['id']}")
        print("Deleted conversation")

        # Stream a response (requires an existing conversation)
        conv = await eve.post("/conversations", json={"name": "Stream Test"})
        async for event in eve.stream(
            f"/conversations/{conv['id']}/stream_messages",
            json={
                "query": "What is Earth Observation?",
                "public_collections": ["eve-public"],
                "k": 3,
            },
        ):
            if event["type"] == "token":
                print(event["content"], end="", flush=True)
            elif event["type"] == "final":
                print()  # newline after streaming
        await eve.delete(f"/conversations/{conv['id']}")

        # Unauthenticated request
        health = await eve.request("GET", "/health", auth_required=False)
        print(f"API health: {health.json()}")


if __name__ == "__main__":
    asyncio.run(main())
