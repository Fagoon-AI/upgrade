import {  NextResponse } from "next/server";
import { Storage } from '@google-cloud/storage';
const storage = new Storage({
  keyFilename: 'src/lib/storage/bucket-key.json',
});
const bucket = storage.bucket('upgrade-fagoon');

export async function POST(request: Request) {
  try {
  const data = await request.formData();
  const file = data.get("data") as File;
  const conversation_id = data.get("conversation_id");
  const user_id = data.get("user_id");
  if (!file || typeof file === "string") {
    throw new Error("Audio file not found");
  }
  if(!conversation_id){
    throw new Error('Conversation Id is required')
  }
  if(!user_id){
    throw new Error('User Id is required')
  }
  const filePath = `upgrade-chat/${user_id}/${conversation_id}/${file?.name}`;
  const bytes = await file.arrayBuffer();
  const buffer = Buffer.from(bytes);
  
  await new Promise((resolve, reject) => {
    const blob = bucket.file(filePath);
    const blobStream = blob.createWriteStream({
      resumable: false,
    });
    
    blobStream
    .on("error", (err) => reject(err))
    .on("finish", () => resolve(true));
    
    blobStream.end(buffer);
  });
  return new NextResponse(JSON.stringify({ success: true,file_url: filePath }));
} catch (error) {
   console.log('File Upload Error:',error)
  return new NextResponse(JSON.stringify(error), { status: 500 });
 }
}