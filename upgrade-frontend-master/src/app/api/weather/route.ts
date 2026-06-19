import { NextRequest, NextResponse } from "next/server";
import { WeatherService } from "@/lib/services/weather/weatherService";
import { WeatherCache } from "@/lib/services/weather/cache";
import { WEATHER_CONFIG } from "@/lib/services/weather/config";

export async function GET(request: NextRequest) {
  try {
    if (!WEATHER_CONFIG.API_KEY) {
      return NextResponse.json(
        { temperature: 22, description: "Weather API key missing", icon: "01d", city: "Mock City" }
      );
    }

    const cache = WeatherCache.getInstance();
    const cacheKey = request.nextUrl.searchParams.toString();
    const cached = cache.get(cacheKey);

    if (cached && cache.isValid(cached)) {
      return NextResponse.json(cached.data);
    }

    const weatherService = new WeatherService();
    const location = await weatherService.getClientLocation(request.url);
    const weatherData = await weatherService.getWeatherData(location);

    cache.set(cacheKey, weatherData);

    return NextResponse.json(weatherData);
  } catch (error) {
    console.error("Weather API error:", error);
    return NextResponse.json(
      {
        error: "Failed to fetch weather data",
        message: error instanceof Error ? error.message : "Unknown error",
      },
      { status: 500 }
    );
  }
}
