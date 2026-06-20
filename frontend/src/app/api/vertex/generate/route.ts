import { NextRequest, NextResponse } from 'next/server';
import { VertexAI } from '@google-cloud/vertexai';

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { prompt } = body;

    if (!prompt) {
      return NextResponse.json({ error: 'Prompt is required' }, { status: 400 });
    }

    // Initialize Vertex AI with application default credentials
    const vertexAI = new VertexAI({
      project: process.env.GOOGLE_CLOUD_PROJECT || 'fagoon', 
      location: process.env.GOOGLE_CLOUD_LOCATION || 'us-central1'
    });

    const generativeModel = vertexAI.preview.getGenerativeModel({
      model: 'gemini-2.5-flash',
    });

    const request = {
      contents: [{ role: 'user', parts: [{ text: prompt }] }],
    };

    const streamingResp = await generativeModel.generateContentStream(request);
    let fullText = '';
    for await (const item of streamingResp.stream) {
      if (item.candidates && item.candidates[0].content.parts[0].text) {
        fullText += item.candidates[0].content.parts[0].text;
      }
    }

    return NextResponse.json({ 
      text: fullText 
    });
  } catch (error: any) {
    console.error('Vertex AI Error:', error);
    return NextResponse.json(
      { error: 'Failed to generate content', details: error.message },
      { status: 500 }
    );
  }
}
