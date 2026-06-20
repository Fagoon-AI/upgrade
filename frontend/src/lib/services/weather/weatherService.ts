import { Location, WeatherData } from "./types";
import { WeatherCache } from "./cache";
import { WEATHER_CONFIG } from "./config";
import { LocationSchema, WeatherApiResponseSchema } from "./schemas";

export class WeatherService {
  private cache: WeatherCache;

  constructor() {
    this.cache = WeatherCache.getInstance();
  }

  private async fetchWithTimeout(url: string): Promise<Response> {
    const controller = new AbortController();
    const timeoutId = setTimeout(
      () => controller.abort(),
      WEATHER_CONFIG.API_TIMEOUT
    );

    try {
      const response = await fetch(url, { signal: controller.signal });
      clearTimeout(timeoutId);
      return response;
    } catch (error) {
      clearTimeout(timeoutId);
      throw error;
    }
  }

  async getClientLocation(url: string): Promise<Location> {
    try {
      const { searchParams } = new URL(url);
      const lat = searchParams.get("latitude");
      const lon = searchParams.get("longitude");

      if (lat && lon) {
        const coords = LocationSchema.parse({ latitude: lat, longitude: lon });
        return coords;
      }

      const ipResponse = await this.fetchWithTimeout(
        `https://api.weatherapi.com/v1/ip.json?key=${WEATHER_CONFIG.API_KEY}&q=auto:ip`
      );

      const ipData = await ipResponse.json();
      return {
        city: ipData.city,
        country: ipData.country_name,
        latitude: ipData.lat,
        longitude: ipData.lon,
      };
    } catch (error) {
      console.error("Location detection error:", error);
      return WEATHER_CONFIG.DEFAULT_LOCATION;
    }
  }

  async getWeatherData(location: Location): Promise<WeatherData> {
    const weatherUrl = `https://api.weatherapi.com/v1/forecast.json?key=${
      WEATHER_CONFIG.API_KEY
    }&q=${
      location.city || `${location.latitude},${location.longitude}`
    }&days=1&aqi=no`;

    const response = await this.fetchWithTimeout(weatherUrl);

    if (!response.ok) {
      throw new Error(`Weather API failed: ${response.statusText}`);
    }

    const rawData = await response.json();
    const data = WeatherApiResponseSchema.parse(rawData);

    return {
      temperature: data.current.temp_c,
      feelsLike: data.current.feelslike_c,
      maxTemp: data.forecast.forecastday[0].day.maxtemp_c,
      minTemp: data.forecast.forecastday[0].day.mintemp_c,
      description: data.current.condition.text,
      weatherIcon: data.current.condition.icon,
      humidity: data.current.humidity,
      windSpeed: data.current.wind_kph,
      city: data.location.name,
      country: data.location.country,
    };
  }
}
