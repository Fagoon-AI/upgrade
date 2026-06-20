// @/utils/stream.ts

export class StreamProcessor {
  private decoder: TextDecoder;

  constructor() {
    this.decoder = new TextDecoder("utf-8");
  }

  public decodeChunk(chunk: Uint8Array): string {
    return this.decoder.decode(chunk, { stream: true });
  }

  public parseStreamData(data: string): string | null {
    const contentMatch = data.match(/content=(['"])((?:\\\1|.)*?)\1/);
    if (!contentMatch) return null;

    const [_, quote, rawContent] = contentMatch;
    return this.unescapeContent(rawContent, quote);
  }

  private unescapeContent(content: string, quote: string): string {
    return content
      .replace(/\\n/g, "\n")
      .replace(/\\\\/g, "\\")
      .replace(new RegExp(`\\\\${quote}`, "g"), quote);
  }
}
