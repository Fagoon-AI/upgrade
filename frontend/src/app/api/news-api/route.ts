import { NextResponse } from "next/server";
import axios from '@/lib/api/axios';

export async function GET(req: Request) {
  const API_KEY = process.env.NEWSAPI_KEY; // Your external API key
  const BASE_URL = "https://newsapi.org/v2/everything";

  if (!API_KEY) {
    return NextResponse.json([{ title: "News API Key missing", description: "Please configure NEWSAPI_KEY to see real news.", url: "#" }]);
  }

  const { searchParams } = new URL(req.url);
  const country = searchParams.get("country") || "us"; // Use query parameters if needed

  try {
    const response = await axios.get(BASE_URL, {
      params: {
        domains: "techcrunch.com,thenextweb.com",
        apiKey: API_KEY,
      },
    });
    return NextResponse.json(response.data.articles);
  } catch (error) {
    console.error("Error fetching external news", error);
    return NextResponse.json(
      { error: "Failed to fetch news articles." },
      { status: 500 }
    );
  }
}
