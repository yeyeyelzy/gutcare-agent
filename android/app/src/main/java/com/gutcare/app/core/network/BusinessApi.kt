package com.gutcare.app.core.network

import com.squareup.moshi.Json
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST

interface BusinessApi {
    @POST("auth/register") suspend fun register(@Body body: RegisterRequest): Response<AcceptedOperation>
    @POST("auth/email/verify") suspend fun verifyEmail(@Body body: VerifyEmailRequest): Response<Unit>
    @POST("auth/login") suspend fun login(@Body body: LoginRequest): Response<TokenPairDto>
    @POST("auth/refresh") suspend fun refresh(@Body body: RefreshRequest): Response<TokenPairDto>
    @POST("auth/logout") suspend fun logout(): Response<Unit>
    @GET("patients/me") suspend fun myProfile(): Response<PatientProfileDto>
}

data class RegisterRequest(
    val email: String,
    val password: String,
    @Json(name = "birth_year") val birthYear: Int,
    @Json(name = "privacy_policy_version") val privacyPolicyVersion: String,
    @Json(name = "health_data_processing_consent") val healthDataProcessingConsent: Boolean,
    @Json(name = "health_data_processing_policy_version") val healthDataProcessingPolicyVersion: String,
)
data class VerifyEmailRequest(val token: String)
data class LoginRequest(val email: String, val password: String)
data class RefreshRequest(@Json(name = "refresh_token") val refreshToken: String)
data class AcceptedOperation(@Json(name = "operation_id") val operationId: String, val status: String)
data class TokenPairDto(
    @Json(name = "access_token") val accessToken: String,
    @Json(name = "refresh_token") val refreshToken: String,
    @Json(name = "token_type") val tokenType: String,
    @Json(name = "expires_in") val expiresIn: Int,
)
data class PatientProfileDto(
    val id: String,
    val nickname: String?,
    @Json(name = "birth_year") val birthYear: Int,
    val timezone: String,
    @Json(name = "profile_version") val profileVersion: Int,
)
data class ProblemDetailsDto(
    val type: String? = null,
    val title: String? = null,
    val status: Int? = null,
    val code: String? = null,
    @Json(name = "request_id") val requestId: String? = null,
    val detail: String? = null,
    val instance: String? = null,
)
