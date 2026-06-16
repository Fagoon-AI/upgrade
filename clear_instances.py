import httpx
import asyncio

async def main():
    async with httpx.AsyncClient(timeout=30.0) as client:
        headers = {"apikey": "fagoon-super-secret-password-12345!"}
        print("Fetching instances...")
        resp = await client.get("http://localhost:8080/instance/fetchInstances", headers=headers)
        instances = resp.json()
        print(f"Found {len(instances)} instances")
        for inst in instances:
            name = inst.get("name")
            print(f"Deleting {name}...")
            # Logout
            await client.delete(f"http://localhost:8080/instance/logout/{name}", headers=headers)
            # Delete
            await client.delete(f"http://localhost:8080/instance/delete/{name}", headers=headers)
        print("All cleared.")

asyncio.run(main())