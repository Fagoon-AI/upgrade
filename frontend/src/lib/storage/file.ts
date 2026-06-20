export const UploadToGcs = async (file: File, conversation_id: string, user_id: string) => {
  if (!file) throw new Error('No file provided');
  if (file.size < 1) throw new Error('File is empty');

  if(!conversation_id){
    throw new Error('Conversation Id is required')
  }
  if(!user_id){
    throw new Error('User Id is required')
  }
  const buffer = await file.arrayBuffer();
  const storage = new Storage();
  const cloudFile = await storage.bucket('scriptbytes-storagedemo').file(`upgrade-chat/${user_id}/${conversation_id}/${file.name}`).save(Buffer.from(buffer));

  return cloudFile;
}

export const UploadWorkflowFileToGCS = async (file: File, user_id: string) => {
  if (!file) throw new Error('No file provided');
  if (file.size < 1) throw new Error('File is empty');

  if(!user_id){
    throw new Error('User Id is required')
  }
  const buffer = await file.arrayBuffer();
  const storage = new Storage();
  const cloudFile = await storage.bucket('scriptbytes-storagedemo').file(`upgrade-chat/${user_id}/${file.name}`).save(Buffer.from(buffer));

  return cloudFile;
}