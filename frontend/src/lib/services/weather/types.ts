export interface Location {
  latitude: number;
  longitude: number;
  city?: string;
  country?: string;
}

export interface WeatherData {
  temperature: number;
  feelsLike: number;
  maxTemp: number;
  minTemp: number;
  description: string;
  weatherIcon: string;
  humidity: number;
  windSpeed: number;
  city: string;
  country: string;
}

export interface CacheEntry<T> {
  data: T;
  timestamp: number;
}
