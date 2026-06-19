// app/api/text-to-speech/route.ts
import { NextResponse } from "next/server";
import axios from '@/lib/api/axios';

export async function POST(request: Request) {
  try {
    const body = await request.json();

    if (!body.chat) {
      return NextResponse.json(
        { error: "Chat text is required" },
        { status: 400 }
      );
    }

    const response = await axios.post(
      "https://upgrade-serverless.1rr1py3l6q1g.jp-osa.codeengine.appdomain.cloud/api/fagoonchat_audio",
      { chat: body.chat },
      {
        responseType: "arraybuffer", // Changed from 'blob' to 'arraybuffer'
        headers: {
          Accept: "audio/mp3,audio/*", // Specify accepted audio formats
        },
      }
    );

    // Get the content type, defaulting to audio/mp3 if not specified
    const contentType = response.headers["content-type"] || "audio/mp3";

    // Return the audio data with explicit headers
    return new NextResponse(response.data, {
      headers: {
        "Content-Type": contentType,
        "Content-Length": response.headers["content-length"] || "",
        "Accept-Ranges": "bytes",
        "Cache-Control": "no-cache",
      },
    });
  } catch (error) {
    console.error("Text-to-speech conversion failed:", error);
    return NextResponse.json(
      { error: "Failed to convert text to speech" },
      { status: 500 }
    );
  }
}
