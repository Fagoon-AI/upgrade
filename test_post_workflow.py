import asyncio
import httpx
import json

async def main():
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        # 1. Login
        login_res = await client.post("/api/v1/auth/login", json={
            "email": "chris@fagoondigital.com",
            "password": "Chris@123"
        })
        token = login_res.json().get("token")
        
        # 2. Post workflow
        payload = {
            "name": "Test Workflow",
            "description": "Test",
            "graph_definition": {
                "nodes": [
                    {
                        "id": "node-1",
                        "type": "custom",
                        "position": {"x": 0, "y": 0},
                        "data": {"type": "geminiNode", "label": "test"}
                    }
                ],
                "edges": [],
                "viewport": {"x": 0, "y": 0, "zoom": 1}
            }
        }
        
        url = "/api/v1/workflows/"
        res = await client.post(url, headers={"Authorization": f"Bearer {token}"}, json=payload)
        print("Status Code:", res.status_code)
        if res.status_code != 201:
            print("Response:", res.text)

if __name__ == "__main__":
    asyncio.run(main())
