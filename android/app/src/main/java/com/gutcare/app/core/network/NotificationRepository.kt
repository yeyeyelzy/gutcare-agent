package com.gutcare.app.core.network

import com.gutcare.app.BuildConfig
import com.squareup.moshi.Json
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import kotlinx.coroutines.CancellationException
import okhttp3.OkHttpClient
import retrofit2.Response
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.PUT
import retrofit2.http.Path
import retrofit2.http.Query

data class NotificationTargetDto(val type: String, val id: String)
data class PatientNotificationDto(
    val id: String,
    @Json(name = "event_type") val eventType: String,
    val category: String,
    val priority: String,
    @Json(name = "occurred_at") val occurredAt: String,
    @Json(name = "created_at") val createdAt: String,
    @Json(name = "read_at") val readAt: String?,
    val target: NotificationTargetDto?,
    @Json(name = "target_unavailable") val targetUnavailable: Boolean,
)
data class NotificationPageDto(val items: List<PatientNotificationDto>, @Json(name = "next_cursor") val nextCursor: String?)
data class NotificationUnreadCountDto(val count: Int)
data class NotificationPreferenceDto(
    @Json(name = "ordinary_in_app_enabled") val ordinaryInAppEnabled: Boolean,
    @Json(name = "quiet_start") val quietStart: String?,
    @Json(name = "quiet_end") val quietEnd: String?,
    val timezone: String,
)
data class NotificationReadBatchRequestDto(@Json(name = "notification_ids") val notificationIds: List<String>)
data class NotificationReadBatchResponseDto(val items: List<PatientNotificationDto>)

interface NotificationApi {
    @GET("notifications") suspend fun list(
        @Query("cursor") cursor: String? = null,
        @Query("limit") limit: Int = 20,
        @Query("category") category: String? = null,
        @Query("unread_only") unreadOnly: Boolean = false,
    ): Response<NotificationPageDto>
    @GET("notifications/unread-count") suspend fun unreadCount(): Response<NotificationUnreadCountDto>
    @GET("notifications/{notification_id}") suspend fun detail(@Path("notification_id") id: String): Response<PatientNotificationDto>
    @POST("notifications/{notification_id}/read") suspend fun markRead(@Path("notification_id") id: String): Response<PatientNotificationDto>
    @POST("notifications/read-batch") suspend fun markReadBatch(@Body body: NotificationReadBatchRequestDto): Response<NotificationReadBatchResponseDto>
    @GET("notifications/preferences") suspend fun preferences(): Response<NotificationPreferenceDto>
    @PUT("notifications/preferences") suspend fun updatePreferences(@Body body: NotificationPreferenceDto): Response<NotificationPreferenceDto>
}

object NotificationApiFactory {
    fun createConfigured(tokens: AccessTokenProvider, authenticator: okhttp3.Authenticator, client: OkHttpClient = OkHttpClient.Builder().build()): NotificationApi {
        val url = ApiEndpoint.validate(ApiConfiguration(BuildConfig.API_BASE_URL, BuildConfig.DEBUG, BuildConfig.ALLOW_EMULATOR_HTTP))
        val authenticated = client.newBuilder().addInterceptor(BearerTokenInterceptor(tokens)).authenticator(authenticator).build()
        val moshi = Moshi.Builder().add(KotlinJsonAdapterFactory()).build()
        return Retrofit.Builder().baseUrl(url).client(authenticated).addConverterFactory(MoshiConverterFactory.create(moshi)).build().create(NotificationApi::class.java)
    }
}

class NotificationRepository(
    private val api: NotificationApi,
    private val sessions: com.gutcare.app.core.security.SecureSessionStore? = null,
    private val onSessionInvalidated: () -> Unit = {},
) {
    suspend fun list(cursor: String? = null, category: String? = null, unreadOnly: Boolean = false) = call { api.list(cursor, category = category, unreadOnly = unreadOnly) }
    suspend fun unreadCount() = call { api.unreadCount() }
    suspend fun detail(id: String) = call { api.detail(id) }
    suspend fun markRead(id: String) = call { api.markRead(id) }
    suspend fun markReadBatch(ids: List<String>): ApiResult<NotificationReadBatchResponseDto> {
        if (ids.isEmpty() || ids.size > 100 || ids.distinct().size != ids.size) return ApiResult.Failure(null, "NOTIFICATION_SELECTION_INVALID")
        return call { api.markReadBatch(NotificationReadBatchRequestDto(ids)) }
    }
    suspend fun preferences() = call { api.preferences() }
    suspend fun updatePreferences(value: NotificationPreferenceDto) = call { api.updatePreferences(value) }

    private suspend fun <T> call(request: suspend () -> Response<T>): ApiResult<T> = try {
        val response = request()
        if (response.isSuccessful) response.body()?.let(ApiResult<T>::Success) ?: ApiResult.Failure(response.code(), "INVALID_RESPONSE")
        else {
            val problem = response.errorBody()?.use { ProblemDetailsParser.parse(it.string()) }
            if (response.code() == 401) { sessions?.clear(); onSessionInvalidated() }
            ApiResult.Failure(response.code(), problem?.code ?: "HTTP_ERROR", problem?.requestId)
        }
    } catch (cancelled: CancellationException) { throw cancelled }
    catch (_: java.io.IOException) { ApiResult.Failure(null, "NETWORK_ERROR") }
    catch (_: Exception) { ApiResult.Failure(null, "INVALID_RESPONSE") }
}
