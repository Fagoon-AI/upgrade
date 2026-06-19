import { NextResponse } from 'next/server';

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const backendUrl = process.env.NEXT_PUBLIC_BASE_URL || process.env.API_BASE_URL || "https://fagoon.tech";
    
    // Direct forward to the backend's dedicated code generation endpoint
    const res = await fetch(`${backendUrl}/api/code`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...req.headers.get('authorization') && { 'Authorization': req.headers.get('authorization')! }
      },
      body: JSON.stringify(body)
    });

    const data = await res.json();
    
    if (!res.ok) {
      return NextResponse.json(data, { status: res.status });
    }

    return NextResponse.json(data);
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
