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

    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      return NextResponse.json(errorData, { status: res.status });
    }

    // Stream the backend response back to the client directly
    return new Response(res.body, {
      status: res.status,
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
      }
    });
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
