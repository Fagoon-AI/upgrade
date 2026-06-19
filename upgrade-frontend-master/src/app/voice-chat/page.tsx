// app/page.tsx
import { getHumeAccessToken } from "@/utils/audio/getHumeAccessToken";
import ClientVoiceChat from "@/components/VoiceChat";

export default async function Page() {
  const accessToken = await getHumeAccessToken();

  return (
    <div className="grow flex flex-col">
      <ClientVoiceChat accessToken={accessToken!} />
    </div>
  );
}
