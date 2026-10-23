package com.gutcare.app.core.network

import com.gutcare.app.BuildConfig
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import okhttp3.OkHttpClient
import retrofit2.Response
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.POST
import retrofit2.http.PUT
import retrofit2.http.Path
import retrofit2.http.Query
import kotlinx.coroutines.CancellationException
import java.util.UUID

/** Authenticated business endpoints only. This service cannot claim or execute agent work. */
interface AnalysisAdviceApi {
    @GET("analysis-tasks") suspend fun listTasks(@Query("cursor") cursor: String? = null, @Query("limit") limit: Int? = null): Response<AnalysisTaskPageDto>
    @GET("analysis-tasks/preview") suspend fun preview(@Query("analysis_type") type: String, @Query("requested_from") from: String? = null, @Query("requested_to") to: String? = null): Response<AnalysisTaskPreviewDto>
    @POST("analysis-tasks") suspend fun createTask(@Header("Idempotency-Key") key: String, @Body body: AnalysisTaskRequestDto): Response<AnalysisTaskDto>
    @GET("analysis-tasks/{task_id}") suspend fun task(@Path("task_id") id: String): Response<AnalysisTaskDto>
    @POST("analysis-tasks/{task_id}/cancel") suspend fun cancel(@Path("task_id") id: String): Response<AnalysisTaskDto>
    @POST("analysis-tasks/{task_id}/retry") suspend fun retry(@Path("task_id") id: String, @Header("Idempotency-Key") key: String): Response<AnalysisTaskDto>
    @GET("advice") suspend fun listAdvice(@Query("cursor") cursor: String? = null, @Query("limit") limit: Int? = null): Response<AdvicePageDto>
    @GET("advice/{advice_id}") suspend fun advice(@Path("advice_id") id: String): Response<AdviceDto>
    @POST("advice/{advice_id}/read") suspend fun markRead(@Path("advice_id") id: String): Response<AdviceDto>
    @POST("advice/{advice_id}/archive") suspend fun archive(@Path("advice_id") id: String): Response<AdviceDto>
    @PUT("advice/{advice_id}/feedback") suspend fun feedback(@Path("advice_id") id: String, @Header("Idempotency-Key") key: String, @Body body: AdviceFeedbackRequestDto): Response<AdviceFeedbackDto>
}

object AnalysisAdviceApiFactory {
    fun createConfigured(tokens: AccessTokenProvider, authenticator: okhttp3.Authenticator, client: OkHttpClient = OkHttpClient.Builder().build()): AnalysisAdviceApi {
        val url = ApiEndpoint.validate(ApiConfiguration(BuildConfig.API_BASE_URL, BuildConfig.DEBUG, BuildConfig.ALLOW_EMULATOR_HTTP))
        val authenticated = client.newBuilder().addInterceptor(BearerTokenInterceptor(tokens)).authenticator(authenticator).build()
        val moshi = Moshi.Builder().add(KotlinJsonAdapterFactory()).build()
        return Retrofit.Builder().baseUrl(url).client(authenticated).addConverterFactory(MoshiConverterFactory.create(moshi)).build().create(AnalysisAdviceApi::class.java)
    }
}

class AnalysisAdviceRepository(private val api: AnalysisAdviceApi) {
    suspend fun tasks(cursor: String? = null) = call { api.listTasks(cursor, 20) }
    suspend fun preview(type: String, from: String? = null, to: String? = null) = call { api.preview(type, from, to) }
    suspend fun create(type: String, from: String? = null, to: String? = null) = call { api.createTask(UUID.randomUUID().toString(), AnalysisTaskRequestDto(type, from, to)) }
    suspend fun task(id: String) = call { api.task(id) }
    suspend fun cancel(id: String) = call { api.cancel(id) }
    suspend fun retry(id: String) = call { api.retry(id, UUID.randomUUID().toString()) }
    suspend fun adviceList(cursor: String? = null) = call { api.listAdvice(cursor, 20) }
    suspend fun advice(id: String) = call { api.advice(id) }
    suspend fun markRead(id: String) = call { api.markRead(id) }
    suspend fun archive(id: String) = call { api.archive(id) }
    suspend fun feedback(id: String, value: String, expectedVersion: Int) = call { api.feedback(id, UUID.randomUUID().toString(), AdviceFeedbackRequestDto(value, expectedVersion)) }

    private suspend fun <T> call(request: suspend () -> Response<T>): ApiResult<T> = try {
        val response = request()
        if (response.isSuccessful) response.body()?.let(ApiResult<T>::Success) ?: ApiResult.Failure(response.code(), "INVALID_RESPONSE")
        else {
            val problem = response.errorBody()?.use { ProblemDetailsParser.parse(it.string()) }
            ApiResult.Failure(response.code(), problem?.code ?: "HTTP_ERROR", problem?.requestId)
        }
    } catch (cancelled: CancellationException) { throw cancelled }
    catch (_: java.io.IOException) { ApiResult.Failure(null, "NETWORK_ERROR") }
    catch (_: Exception) { ApiResult.Failure(null, "INVALID_RESPONSE") }
}
