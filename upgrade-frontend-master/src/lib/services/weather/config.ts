export const WEATHER_CONFIG = {
  API_KEY: process.env.WEATHERAPI_API_KEY,
  CACHE_TTL: 300, // 5 minutes in seconds
  API_TIMEOUT: 3000, // 3 seconds
  DEFAULT_LOCATION: {
    city: "Kathmandu",
    country: "NP",
    latitude: 27.7172,
    longitude: 85.324,
  },
} as const;
