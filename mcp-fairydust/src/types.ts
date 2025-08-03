import { z } from 'zod';

// Image Generation Types
export const ImageStyleSchema = z.enum(['realistic', 'artistic', 'cartoon', 'anime', 'watercolor', 'oil_painting', '3d_render', 'sketch']);
export const ImageSizeSchema = z.enum(['square', 'portrait', 'landscape']);

export const ReferencePersonSchema = z.object({
  person_id: z.string(),
  description: z.string()
});

export const ImageGenerateRequestSchema = z.object({
  prompt: z.string().min(1).max(1000),
  style: ImageStyleSchema.optional(),
  image_size: ImageSizeSchema.optional(),
  reference_people: z.array(ReferencePersonSchema).optional()
});

// Fortune Teller Types
export const ReadingTypeSchema = z.enum(['daily', 'love', 'career', 'general', 'personal_growth']);

export const FortuneGenerateRequestSchema = z.object({
  reading_type: ReadingTypeSchema,
  question: z.string().optional(),
  target_person_id: z.string().optional()
});

// Response Types
export const DustInfoSchema = z.object({
  cost: z.number(),
  remaining_balance: z.number()
});

export type ImageStyle = z.infer<typeof ImageStyleSchema>;
export type ImageSize = z.infer<typeof ImageSizeSchema>;
export type ReferencePerson = z.infer<typeof ReferencePersonSchema>;
export type ImageGenerateRequest = z.infer<typeof ImageGenerateRequestSchema>;
export type ReadingType = z.infer<typeof ReadingTypeSchema>;
export type FortuneGenerateRequest = z.infer<typeof FortuneGenerateRequestSchema>;
export type DustInfo = z.infer<typeof DustInfoSchema>;