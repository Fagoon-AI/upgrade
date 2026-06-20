import { Storage } from '@google-cloud/storage';
import { NextResponse } from 'next/server';

const storage = new Storage({
  keyFilename: 'src/lib/storage/bucket-key.json',
});
const bucket = storage.bucket('upgrade-fagoon');


export async function POST(request: Request) {
    const body = await request.json()
    const {file_path} = body;
    if(!file_path){
        return NextResponse.json({success: false, message:'File Path is required'})
    }

    const file = bucket.file(`${file_path}`);
    const [exists] = await file.exists();

    if (!exists) {
        return NextResponse.json({ success: false, message: 'File not found in bucket' }, { status: 404 });
    }

    const [url] = await file.getSignedUrl({
        action: 'read',
        expires: Date.now() + 60 * 60 * 1000,
    });

    return NextResponse.json({success: true, data: url})
}