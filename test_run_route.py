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
        if login_res.status_code != 200:
            print("Login failed:", login_res.status_code)
            return
            
        token = login_res.json().get("token")
        
        # 2. Get workflows to find an ID
        wf_res = await client.get("/api/v1/workflows/", headers={"Authorization": f"Bearer {token}"})
        workflows = wf_res.json().get("data", {}).get("items", [])
        if not workflows:
            print("No workflows found.")
            return
            
        workflow_id = workflows[0]["id"]
        print("Running workflow:", workflow_id)
        
        # 3. Hit run route
        url = f"/api/v1/executions/{workflow_id}/run"
        res = await client.post(url, headers={"Authorization": f"Bearer {token}"}, json={"async_execution": True})
        print("Run Status Code:", res.status_code)
        if res.status_code != 202:
            print("Response:", res.text)
        else:
            print("Response JSON:", res.json())

if __name__ == "__main__":
    asyncio.run(main())
