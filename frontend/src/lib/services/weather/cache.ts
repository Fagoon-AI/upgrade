import { CacheEntry } from "./types";
import { WEATHER_CONFIG } from "./config";

export class WeatherCache {
  private static instance: WeatherCache;
  private cache: Map<string, CacheEntry<any>>;

  private constructor() {
    this.cache = new Map();
  }

  public static getInstance(): WeatherCache {
    if (!WeatherCache.instance) {
      WeatherCache.instance = new WeatherCache();
    }
    return WeatherCache.instance;
  }

  get(key: string): CacheEntry<any> | undefined {
    return this.cache.get(key);
  }

  set(key: string, data: any): void {
    this.cache.set(key, { data, timestamp: Date.now() });
  }

  isValid(entry: CacheEntry<any>): boolean {
    return Date.now() - entry.timestamp < WEATHER_CONFIG.CACHE_TTL * 1000;
  }
}
