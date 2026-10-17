import type { components, operations } from './generated/openapi'

export type AcceptedOperation = components['schemas']['AcceptedOperation']
export type ProblemDetails = components['schemas']['Problem']
export type LoginRequest = operations['login']['requestBody']['content']['application/json']
export type RegisterRequest = components['schemas']['RegisterRequest']
export type TokenPair = components['schemas']['TokenPair']
export type PatientProfile = components['schemas']['PatientProfile']
export type PatientProfilePatch = components['schemas']['PatientProfilePatch']
export type VerifyEmailRequest = operations['verifyEmail']['requestBody']['content']['application/json']
export type PasswordResetRequest = operations['requestPasswordReset']['requestBody']['content']['application/json']
export type PasswordResetConfirmRequest = operations['confirmPasswordReset']['requestBody']['content']['application/json']
