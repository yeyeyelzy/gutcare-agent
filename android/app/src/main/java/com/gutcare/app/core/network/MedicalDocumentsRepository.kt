package com.gutcare.app.core.network

import kotlinx.coroutines.CancellationException
import okhttp3.RequestBody
import okhttp3.OkHttpClient
import okhttp3.HttpUrl.Companion.toHttpUrl
import retrofit2.Retrofit
import retrofit2.Response
import retrofit2.converter.moshi.MoshiConverterFactory
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.PUT
import retrofit2.http.Query
import retrofit2.http.Url
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory

/** Authenticated F02 boundary. The caller never receives or persists an upload/download capability. */
interface MedicalDocumentsApi {
    suspend fun listMedicalDocuments(cursor: String?, limit: Int?): Response<MedicalDocumentPageDto>
    suspend fun getMedicalDocument(documentId: String): Response<MedicalDocumentDto>
    suspend fun listCandidates(documentId: String): Response<List<MedicalFieldCandidateDto>>
    suspend fun decideCandidate(candidateId: String, idempotencyKey: String, body: MedicalCandidateDecisionDto): Response<Unit>
    suspend fun createUpload(idempotencyKey: String, body: UploadCreateDto): Response<UploadSessionDto>
    suspend fun uploadThroughGateway(uploadUrl: String, body: RequestBody): Response<Unit>
    suspend fun completeUpload(uploadId: String): Response<FileObjectDto>
    suspend fun createMedicalDocument(body: MedicalDocumentCreateDto): Response<MedicalDocumentDto>
}

/** Retrofit declaration stays F02-specific so shared BusinessApi need not grow for this slice. */
private interface RetrofitMedicalDocumentsApi {
    @GET("medical-documents") suspend fun list(@Query("cursor") cursor: String?, @Query("limit") limit: Int?): Response<MedicalDocumentPageDto>
    @GET("medical-documents/{document_id}") suspend fun detail(@Path("document_id") id: String): Response<MedicalDocumentDto>
    @GET("medical-documents/{document_id}/candidates") suspend fun candidates(@Path("document_id") id: String): Response<List<MedicalFieldCandidateDto>>
    @POST("medical-field-candidates/{candidate_id}/decision") suspend fun decide(@Path("candidate_id") id: String, @Header("Idempotency-Key") key: String, @Body body: MedicalCandidateDecisionDto): Response<Unit>
    @POST("files/uploads") suspend fun createUpload(@Header("Idempotency-Key") key: String, @Body body: UploadCreateDto): Response<UploadSessionDto>
    @PUT suspend fun gatewayUpload(@Url url: String, @Body body: RequestBody): Response<Unit>
    @POST("files/uploads/{upload_id}/complete") suspend fun complete(@Path("upload_id") id: String): Response<FileObjectDto>
    @POST("medical-documents") suspend fun create(@Body body: MedicalDocumentCreateDto): Response<MedicalDocumentDto>
}

private class RetrofitMedicalDocumentsAdapter(
    private val api: RetrofitMedicalDocumentsApi,
    private val expectedGatewayOrigin: okhttp3.HttpUrl,
) : MedicalDocumentsApi {
    override suspend fun listMedicalDocuments(cursor: String?, limit: Int?) = api.list(cursor, limit)
    override suspend fun getMedicalDocument(documentId: String) = api.detail(documentId)
    override suspend fun listCandidates(documentId: String) = api.candidates(documentId)
    override suspend fun decideCandidate(candidateId: String, idempotencyKey: String, body: MedicalCandidateDecisionDto) = api.decide(candidateId, idempotencyKey, body)
    override suspend fun createUpload(idempotencyKey: String, body: UploadCreateDto) = api.createUpload(idempotencyKey, body)
    override suspend fun uploadThroughGateway(uploadUrl: String, body: RequestBody): Response<Unit> {
        val url = runCatching { uploadUrl.toHttpUrl() }.getOrNull()
        require(url != null && url.scheme == expectedGatewayOrigin.scheme && url.host == expectedGatewayOrigin.host && url.port == expectedGatewayOrigin.port && url.encodedPath.startsWith("/uploads/")) {
            "Upload gateway must be the configured same-origin /uploads endpoint"
        }
        return api.gatewayUpload(uploadUrl, body)
    }
    override suspend fun completeUpload(uploadId: String) = api.complete(uploadId)
    override suspend fun createMedicalDocument(body: MedicalDocumentCreateDto) = api.create(body)
}

object MedicalDocumentsApiFactory {
    fun createConfigured(accessTokens: AccessTokenProvider, authenticator: SessionAuthenticator, client: OkHttpClient = OkHttpClient.Builder().build()): MedicalDocumentsApi {
        val endpoint = ApiEndpoint.validate(ApiConfiguration(com.gutcare.app.BuildConfig.API_BASE_URL, com.gutcare.app.BuildConfig.DEBUG, com.gutcare.app.BuildConfig.ALLOW_EMULATOR_HTTP))
        val configured = client.newBuilder().addInterceptor(BearerTokenInterceptor(accessTokens)).authenticator(authenticator).build()
        val retrofit = Retrofit.Builder().baseUrl(endpoint).client(configured)
            .addConverterFactory(MoshiConverterFactory.create(Moshi.Builder().add(KotlinJsonAdapterFactory()).build())).build()
        return RetrofitMedicalDocumentsAdapter(retrofit.create(RetrofitMedicalDocumentsApi::class.java), endpoint.toHttpUrl())
    }
}

class MedicalDocumentsRepository(
    private val api: MedicalDocumentsApi,
    private val sessions: com.gutcare.app.core.security.SecureSessionStore? = null,
    private val onSessionInvalidated: () -> Unit = {},
) {
    suspend fun list(cursor: String? = null, limit: Int = 20) = call { api.listMedicalDocuments(cursor, limit) }
    suspend fun detail(id: String) = call { api.getMedicalDocument(id) }
    suspend fun candidates(documentId: String) = call { api.listCandidates(documentId) }
    suspend fun decide(candidateId: String, idempotencyKey: String, body: MedicalCandidateDecisionDto): ApiResult<Unit> {
        if (idempotencyKey.length !in 8..128) return ApiResult.Failure(null, "IDEMPOTENCY_KEY_INVALID")
        return call { api.decideCandidate(candidateId, idempotencyKey, body) }
    }
    suspend fun upload(idempotencyKey: String, metadata: UploadCreateDto, content: RequestBody): ApiResult<FileObjectDto> {
        if (idempotencyKey.length !in 8..128) return ApiResult.Failure(null, "IDEMPOTENCY_KEY_INVALID")
        val session = when (val result = call { api.createUpload(idempotencyKey, metadata) }) {
            is ApiResult.Failure -> return result
            is ApiResult.Success -> result.value
        }
        when (val result = call { api.uploadThroughGateway(session.uploadUrl, content) }) {
            is ApiResult.Failure -> return result
            is ApiResult.Success -> Unit
        }
        return call { api.completeUpload(session.uploadId) }
    }
    suspend fun create(body: MedicalDocumentCreateDto) = call { api.createMedicalDocument(body) }

    private suspend fun <T> call(request: suspend () -> Response<T>): ApiResult<T> = try {
        val response = request()
        if (response.isSuccessful) {
            if (response.code() == 204) @Suppress("UNCHECKED_CAST") ApiResult.Success(Unit as T)
            else response.body()?.let { ApiResult.Success(it) } ?: ApiResult.Failure(response.code(), "INVALID_RESPONSE")
        } else {
            val problem = response.errorBody()?.use { ProblemDetailsParser.parse(it.string()) }
            if (response.code() == 401) { sessions?.clear(); onSessionInvalidated() }
            ApiResult.Failure(response.code(), problem?.code ?: "HTTP_ERROR", problem?.requestId)
        }
    } catch (cancelled: CancellationException) { throw cancelled
    } catch (_: java.io.IOException) { ApiResult.Failure(null, "NETWORK_ERROR")
    } catch (_: Exception) { ApiResult.Failure(null, "INVALID_RESPONSE") }
}
