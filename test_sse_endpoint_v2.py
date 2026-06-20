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
            print("Login failed:", login_res.status_code, login_res.text)
            return
            
        data = login_res.json()
        token = data.get("token")
        if not token:
            print("No access token in response:", data)
            return
            
        print("Logged in successfully.")
        
        # 2. Test SSE endpoint
        url = f"/api/v1/streams?channel=exec_trace:test&access_token={token}"
        try:
            async with client.stream("GET", url) as response:
                print("SSE Status:", response.status_code)
                print("SSE Headers:", response.headers)
                
                # Try to read one line
                async for line in response.aiter_lines():
                    print("SSE Line:", line)
                    break
        except Exception as e:
            print("SSE Exception:", e)

if __name__ == "__main__":
    asyncio.run(main())