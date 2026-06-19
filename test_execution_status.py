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
        
        # 2. Get status of the execution mentioned by user: 5b280053-1520-48dd-a5ae-8edb3b3d91bf
        eid = "5b280053-1520-48dd-a5ae-8edb3b3d91bf"
        
        url = f"/api/v1/executions/{eid}/status"
        res = await client.get(url, headers={"Authorization": f"Bearer {token}"})
        print("Status Code:", res.status_code)
        if res.status_code != 200:
            print("Response:", res.text)
            
        url2 = f"/api/v1/executions/{eid}/timeline"
        res2 = await client.get(url2, headers={"Authorization": f"Bearer {token}"})
        print("Timeline Status Code:", res2.status_code)
        if res2.status_code != 200:
            print("Response:", res2.text)

if __name__ == "__main__":
    asyncio.run(main())
