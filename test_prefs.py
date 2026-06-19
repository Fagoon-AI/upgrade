import asyncio
import httpx

async def main():
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        # 1. Login
        login_res = await client.post("/api/v1/auth/login", json={
            "email": "chris@fagoondigital.com",
            "password": "Chris@123"
        })
        token = login_res.json().get("token")
        
        # 2. Get Prefs
        url = "/api/v1/userPreferences"
        res = await client.get(url, headers={"Authorization": f"Bearer {token}"})
        print("GET /userPreferences:", res.status_code, res.text)
        
        # 3. Post Prefs
        res2 = await client.post(url, headers={"Authorization": f"Bearer {token}"}, json={"theme": "dark", "responseTone": "casual"})
        print("POST /userPreferences:", res2.status_code, res2.text)

if __name__ == "__main__":
    asyncio.run(main())
