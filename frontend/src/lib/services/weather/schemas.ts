import { z } from "zod";

export const LocationSchema = z.object({
  latitude: z.preprocess((val) => Number(val), z.number().min(-90).max(90)),
  longitude: z.preprocess((val) => Number(val), z.number().min(-180).max(180)),
});

export const WeatherApiResponseSchema = z.object({
  current: z.object({
    temp_c: z.number(),
    feelslike_c: z.number(),
    condition: z.object({
      text: z.string(),
      icon: z.string(),
    }),
    humidity: z.number(),
    wind_kph: z.number(),
  }),
  location: z.object({
    name: z.string(),
    country: z.string(),
  }),
  forecast: z.object({
    forecastday: z.array(
      z.object({
        day: z.object({
          maxtemp_c: z.number(),
          mintemp_c: z.number(),
        }),
      })
    ),
  }),
});
