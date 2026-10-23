package com.gutcare.app.core.network

import com.gutcare.app.core.security.SecureSessionStore
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import okhttp3.OkHttpClient
import okhttp3.ResponseBody
import java.io.ByteArrayOutputStream
import kotlinx.coroutines.CancellationException
import retrofit2.Retrofit
import retrofit2.Response
import retrofit2.converter.moshi.MoshiConverterFactory
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

interface PrivacyApi {
    @GET("patients/me/consents") suspend fun consents(): Response<List<ConsentStatusDto>>
    @GET("consent-notices") suspend fun notice(@Query("consent_type") type: String): Response<ConsentNoticeDto>
    @POST("patients/me/consents") suspend fun decide(@Body body: ConsentDecisionDto): Response<ConsentDecisionDto>
    @POST("patients/me/account-deletion") suspend fun deleteAccount(): Response<PrivacyDeletionAcceptedDto>
    @POST("privacy/deletion-operations/{operation_id}/status") suspend fun deletionStatus(@Path("operation_id") id: String, @Body body: DeletionStatusRequestDto): Response<PrivacyDeletionStatusDto>
    @POST("privacy/exports") suspend fun createExport(@Body body: PrivacyExportRequestDto): Response<PrivacyExportPreviewDto>
    @GET("privacy/exports") suspend fun exports(): Response<List<PrivacyExportSummaryDto>>
    @GET("privacy/exports/{export_id}") suspend fun export(@Path("export_id") id: String): Response<PrivacyExportDetailDto>
    @POST("privacy/exports/{export_id}") suspend fun confirmExport(@Path("export_id") id: String): Response<Unit>
    @POST("privacy/exports/{export_id}/cancel") suspend fun cancelExport(@Path("export_id") id: String): Response<Unit>
    @GET("privacy/exports/download") suspend fun download(@Header("X-Export-Capability") capability: String): Response<ResponseBody>
}

object PrivacyApiFactory {
    fun createConfigured(accessTokens: AccessTokenProvider, authenticator: SessionAuthenticator, client: OkHttpClient = OkHttpClient.Builder().build()): PrivacyApi {
        val endpoint = ApiEndpoint.validate(ApiConfiguration(com.gutcare.app.BuildConfig.API_BASE_URL, com.gutcare.app.BuildConfig.DEBUG, com.gutcare.app.BuildConfig.ALLOW_EMULATOR_HTTP))
        val configured = client.newBuilder().addInterceptor(BearerTokenInterceptor(accessTokens)).authenticator(authenticator).build()
        val moshi = Moshi.Builder().add(KotlinJsonAdapterFactory()).build()
        return Retrofit.Builder().baseUrl(endpoint).client(configured).addConverterFactory(MoshiConverterFactory.create(moshi)).build().create(PrivacyApi::class.java)
    }
}

/** Privacy capabilities are returned only to the caller's current memory and never persisted. */
class PrivacyRepository(
    private val api: PrivacyApi,
    private val sessions: SecureSessionStore? = null,
    private val onSessionInvalidated: () -> Unit = {},
) {
    suspend fun consents() = call { api.consents() }
    suspend fun notice(type: String) = call { api.notice(type) }
    suspend fun decide(type: String, version: String, granted: Boolean): ApiResult<ConsentStatusDto> {
        when (val recorded = call { api.decide(ConsentDecisionDto(type, version, granted)) }) {
            is ApiResult.Failure -> return recorded
            is ApiResult.Success -> Unit
        }
        return when (val latest = consents()) {
            is ApiResult.Success -> latest.value.firstOrNull { it.consentType == type }
                ?.let(ApiResult<ConsentStatusDto>::Success) ?: ApiResult.Failure(null, "INVALID_RESPONSE")
            is ApiResult.Failure -> latest
        }
    }
    suspend fun deleteAccount() = call { api.deleteAccount() }
    suspend fun deletionStatus(id: String, receipt: String) = call { api.deletionStatus(id, DeletionStatusRequestDto(receipt)) }
    suspend fun createExport(categories: List<String>) = call { api.createExport(PrivacyExportRequestDto(categories)) }
    suspend fun exports() = call { api.exports() }
    suspend fun export(id: String) = call { api.export(id) }
    suspend fun confirmExport(id: String) = callEmpty { api.confirmExport(id) }
    suspend fun cancelExport(id: String) = callEmpty { api.cancelExport(id) }

    /** Reads the single-use capability response directly into ephemeral memory. Caller must not log/store it. */
    suspend fun download(capability: String): ApiResult<ByteArray> {
        if (capability.length !in 40..128) return ApiResult.Failure(null, "EXPORT_CAPABILITY_INVALID")
        return try {
            val response = api.download(capability)
            if (!response.isSuccessful) failure(response)
            else {
                val body = response.body() ?: return ApiResult.Failure(response.code(), "INVALID_RESPONSE")
                body.use {
                    if (it.contentLength() > MAX_EXPORT_BYTES) ApiResult.Failure(null, "EXPORT_TOO_LARGE")
                    else {
                        val output = ByteArrayOutputStream()
                        val buffer = ByteArray(8192)
                        it.byteStream().use { input ->
                            var total = 0L
                            while (true) {
                                val count = input.read(buffer)
                                if (count < 0) break
                                total += count
                                if (total > MAX_EXPORT_BYTES) return ApiResult.Failure(null, "EXPORT_TOO_LARGE")
                                output.write(buffer, 0, count)
                            }
                        }
                        ApiResult.Success(output.toByteArray())
                    }
                }
            }
        } catch (cancelled: CancellationException) { throw cancelled
        } catch (_: java.io.IOException) { ApiResult.Failure(null, "NETWORK_ERROR")
        } catch (_: Exception) { ApiResult.Failure(null, "INVALID_RESPONSE") }
    }

    private suspend fun <T> call(request: suspend () -> Response<T>): ApiResult<T> = try {
        val response = request()
        if (response.isSuccessful) {
            if (response.code() == 204) @Suppress("UNCHECKED_CAST") ApiResult.Success(Unit as T)
            else response.body()?.let(ApiResult<T>::Success) ?: ApiResult.Failure(response.code(), "INVALID_RESPONSE")
        } else failure(response)
    } catch (cancelled: CancellationException) { throw cancelled
    } catch (_: java.io.IOException) { ApiResult.Failure(null, "NETWORK_ERROR")
    } catch (_: Exception) { ApiResult.Failure(null, "INVALID_RESPONSE") }

    private suspend fun callEmpty(request: suspend () -> Response<Unit>): ApiResult<Unit> = try {
        val response = request()
        if (response.isSuccessful) ApiResult.Success(Unit) else failure(response)
    } catch (cancelled: CancellationException) { throw cancelled
    } catch (_: java.io.IOException) { ApiResult.Failure(null, "NETWORK_ERROR")
    } catch (_: Exception) { ApiResult.Failure(null, "INVALID_RESPONSE") }

    private suspend fun <T> failure(response: Response<T>): ApiResult.Failure {
        val problem = response.errorBody()?.use { ProblemDetailsParser.parse(it.string()) }
        if (response.code() == 401) { sessions?.clear(); onSessionInvalidated() }
        return ApiResult.Failure(response.code(), problem?.code ?: "HTTP_ERROR", problem?.requestId)
    }

    private companion object { const val MAX_EXPORT_BYTES = 50L * 1024 * 1024 }
}
