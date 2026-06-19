import { z } from 'zod';

const urlPattern = /https?:\/\//i;
const htmlPattern = /<[^>]*>/;

export const userPreferencesSchema = z.object({
  nickname: z.string()
    .max(30, 'Nickname must be max 30 characters')
    .refine(val => !val || !urlPattern.test(val), 'Nickname cannot contain URLs')
    .refine(val => !val || !htmlPattern.test(val), 'Nickname cannot contain HTML')
    .optional(),
  location: z.string()
    .max(100, 'Location must be max 100 characters')
    .refine(val => !val || !urlPattern.test(val), 'Location cannot contain URLs')
    .refine(val => !val || !htmlPattern.test(val), 'Location cannot contain HTML')
    .optional(),
  role: z.string()
    .max(50, 'Role must be max 50 characters')
    .refine(val => !val || !urlPattern.test(val), 'Role cannot contain URLs')
    .refine(val => !val || !htmlPattern.test(val), 'Role cannot contain HTML')
    .optional(),
  bio: z.string()
    .max(500, 'Bio must be max 500 characters')
    .refine(val => !val || !htmlPattern.test(val), 'Bio cannot contain HTML')
    .optional(),
  systemPrompt: z.string()
    .max(1000, 'System prompt must be max 1000 characters')
    .optional(),
  theme: z.enum(['light', 'dark']).default('light'),
  responseTone: z.enum(['professional', 'friendly', 'casual', 'formal']).default('professional'),
});

export type UserPreferencesFormData = z.infer<typeof userPreferencesSchema>;
