import { NextResponse } from 'next/server'

export async function POST(req: Request) {
  const body = await req.json()
  const cookie = req.headers.get('cookie') || ''
  // Call Python API
  const pythonRes = await fetch('http://localhost:2321/api/v1/users/login', {
    method: 'POST',
    headers: {
      Cookie: cookie,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  })

  // Extract cookies from Python API response
  const setCookie = pythonRes.headers.get('set-cookie')

  // Read response body
  const data = await pythonRes.json()

  // Forward cookie to browser
  const response = NextResponse.json(data, {
    status: pythonRes.status,
  })

  if (setCookie) {
    response.headers.set('set-cookie', setCookie)
  }

  return response
}
