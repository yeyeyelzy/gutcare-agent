package com.gutcare.app.core.network

import okhttp3.RequestBody
import com.squareup.moshi.Json
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.PATCH
import retrofit2.http.DELETE
import retrofit2.http.Path
import retrofit2.http.Query
import retrofit2.http.Header
import retrofit2.http.HTTP

interface BusinessApi {
    @POST("auth/register") suspend fun register(@Body body: RegisterRequest): Response<AcceptedOperation>
    @POST("auth/email/verify") suspend fun verifyEmail(@Body body: VerifyEmailRequest): Response<Unit>
    @POST("auth/login") suspend fun login(@Body body: LoginRequest): Response<TokenPairDto>
    @POST("auth/refresh") suspend fun refresh(@Body body: RefreshRequest): Response<TokenPairDto>
    @POST("auth/logout") suspend fun logout(): Response<Unit>
    @POST("auth/password/reset/request") suspend fun requestPasswordReset(@Body body: PasswordResetRequest): Response<AcceptedOperation>
    @POST("auth/password/reset/confirm") suspend fun confirmPasswordReset(@Body body: PasswordResetConfirmRequest): Response<Unit>
    @GET("patients/me") suspend fun myProfile(): Response<PatientProfileDto>

    @GET("{record_type}") suspend fun listRecords(
        @Path(value = "record_type", encoded = true) recordType: String,
        @Query("cursor") cursor: String? = null,
        @Query("limit") limit: Int? = null,
        @Query("since") since: String? = null,
        @Query("until") until: String? = null,
    ): Response<RecordPageDto>
    @POST("{record_type}") suspend fun createRecord(
        @Path(value = "record_type", encoded = true) recordType: String,
        @Header("Idempotency-Key") idempotencyKey: String,
        @Body body: RecordWriteDto,
    ): Response<RecordDto>
    @GET("{record_type}/{record_id}") suspend fun getRecord(
        @Path(value = "record_type", encoded = true) recordType: String,
        @Path("record_id") recordId: String,
    ): Response<RecordDto>
    @PATCH("{record_type}/{record_id}") suspend fun updateRecord(
        @Path(value = "record_type", encoded = true) recordType: String,
        @Path("record_id") recordId: String,
        @Body body: RecordPatchDto,
    ): Response<RecordDto>
    @DELETE("{record_type}/{record_id}") suspend fun deleteRecord(
        @Path(value = "record_type", encoded = true) recordType: String,
        @Path("record_id") recordId: String,
        @Query("record_version") recordVersion: Int,
    ): Response<Unit>
    @GET("symptom-records/{record_id}/status-history") suspend fun symptomStatusHistory(
        @Path("record_id") recordId: String,
    ): Response<SymptomStatusHistoryDto>

    @GET("mood-records") suspend fun listMoodRecords(
        @Query("cursor") cursor: String? = null,
        @Query("limit") limit: Int? = null,
        @Query("since") since: String? = null,
        @Query("until") until: String? = null,
    ): Response<MoodPageDto>
    @POST("mood-records") suspend fun createMoodRecord(
        @Header("Idempotency-Key") idempotencyKey: String,
        @Body body: MoodWriteDto,
    ): Response<MoodDetailDto>
    @GET("mood-records/{record_id}") suspend fun getMoodRecord(@Path("record_id") recordId: String): Response<MoodDetailDto>
    @PATCH("mood-records/{record_id}") suspend fun updateMoodRecord(
        @Path("record_id") recordId: String,
        @Body body: RequestBody,
    ): Response<MoodDetailDto>
    @HTTP(method = "DELETE", path = "mood-records/{record_id}", hasBody = true) suspend fun deleteMoodRecord(
        @Path("record_id") recordId: String,
        @Body body: RecordVersionRequestDto,
    ): Response<Unit>
    @GET("history/timeline") suspend fun historyTimeline(
        @Query("cursor") cursor: String? = null,
        @Query("limit") limit: Int? = null,
        @Query("category") categories: List<String>? = null,
        @Query("since") since: String? = null,
        @Query("until") until: String? = null,
    ): Response<HistoryPageDto>
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
data class PasswordResetRequest(val email: String)
data class PasswordResetConfirmRequest(val token: String, @Json(name = "new_password") val newPassword: String)
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
