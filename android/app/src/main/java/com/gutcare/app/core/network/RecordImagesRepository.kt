package com.gutcare.app.core.network

import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import kotlinx.coroutines.CancellationException
import okhttp3.OkHttpClient
import okhttp3.RequestBody
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.ResponseBody
import retrofit2.Response
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.POST
import retrofit2.http.PUT
import retrofit2.http.Path
import retrofit2.http.Query
import retrofit2.http.Url
import java.util.UUID

interface RecordImagesApi {
    @POST("files/uploads") suspend fun createUpload(@Header("Idempotency-Key") key: String, @Body body: UploadCreateDto): Response<UploadSessionDto>
    @PUT suspend fun upload(@Url url: String, @Body body: RequestBody): Response<Unit>
    @POST("files/uploads/{upload_id}/complete") suspend fun complete(@Path("upload_id") uploadId: String): Response<FileObjectDto>
    @GET("dietary-records/{record_id}/images") suspend fun dietImages(@Path("record_id") recordId: String): Response<List<RecordImageAttachmentDto>>
    @POST("dietary-records/{record_id}/images") suspend fun attachDiet(@Path("record_id") recordId: String, @Header("Idempotency-Key") key: String, @Body body: RecordImageAttachDto): Response<RecordImageAttachmentDto>
    @GET("stool-records/{record_id}/images") suspend fun stoolImages(@Path("record_id") recordId: String): Response<List<RecordImageAttachmentDto>>
    @GET("stool-records/{record_id}/image-recognition-requests/latest") suspend fun latestStoolRecognition(@Path("record_id") recordId: String): Response<RecordImageRecognitionRequestDto>
    @POST("stool-records/{record_id}/images") suspend fun attachStool(@Path("record_id") recordId: String, @Header("Idempotency-Key") key: String, @Body body: RecordImageAttachDto): Response<RecordImageAttachmentDto>
    @DELETE("record-images/{image_id}") suspend fun delete(
        @Path("image_id") imageId: String,
        @Query("record_version") recordVersion: Int,
        @Query("image_set_version") imageSetVersion: Int,
    ): Response<Unit>
    @POST("record-images/{attachment_id}/download-grants") suspend fun createDownloadGrant(@Path("attachment_id") attachmentId: String): Response<FileDownloadGrantDto>
    @GET("record-image-recognition-disclosures") suspend fun recognitionDisclosure(@Query("purpose") purpose: String): Response<RecordImageDisclosureDto>
    @POST("record-image-recognition-disclosures") suspend fun acknowledgeRecognitionDisclosure(@Body body: RecordImageDisclosureAcknowledgeDto): Response<RecordImageDisclosureTokenDto>
    @POST("dietary-records/{record_id}/image-recognition-requests") suspend fun createDietRecognition(@Path("record_id") recordId: String, @Header("Idempotency-Key") key: String, @Body body: RecordImageRecognitionCreateDto): Response<RecordImageRecognitionRequestDto>
    @POST("stool-records/{record_id}/image-recognition-requests") suspend fun createStoolRecognition(@Path("record_id") recordId: String, @Header("Idempotency-Key") key: String, @Body body: RecordImageRecognitionCreateDto): Response<RecordImageRecognitionRequestDto>
    @GET("record-image-recognition-requests/{request_id}") suspend fun recognitionRequest(@Path("request_id") requestId: String): Response<RecordImageRecognitionRequestDto>
    @POST("record-image-recognition-requests/{request_id}/retry") suspend fun retryRecognition(@Path("request_id") requestId: String, @Header("Idempotency-Key") key: String, @Body body: RecordImageRecognitionCreateDto): Response<RecordImageRecognitionRequestDto>
    @POST("record-image-candidates/{candidate_id}/decision") suspend fun decideRecognitionCandidate(@Path("candidate_id") candidateId: String, @Header("Idempotency-Key") key: String, @Body body: RecordImageCandidateDecisionDto): Response<Unit>
    /** Capability GET is deliberately routed through a separate client without app credentials. */
    @GET suspend fun downloadCapability(@Url url: String): Response<ResponseBody>
}

object RecordImagesApiFactory {
    fun createConfigured(
        accessTokens: AccessTokenProvider,
        authenticator: SessionAuthenticator,
        client: OkHttpClient = OkHttpClient.Builder().build(),
    ): RecordImagesApi {
        val endpoint = ApiEndpoint.validate(ApiConfiguration(com.gutcare.app.BuildConfig.API_BASE_URL, com.gutcare.app.BuildConfig.DEBUG, com.gutcare.app.BuildConfig.ALLOW_EMULATOR_HTTP))
        val configured = client.newBuilder().addInterceptor(BearerTokenInterceptor(accessTokens)).authenticator(authenticator).build()
        val retrofit = Retrofit.Builder().baseUrl(endpoint).client(configured)
            .addConverterFactory(MoshiConverterFactory.create(Moshi.Builder().add(KotlinJsonAdapterFactory()).build())).build()
        val unauthenticatedGateway = Retrofit.Builder().baseUrl(endpoint).client(
            OkHttpClient.Builder().followRedirects(false).followSslRedirects(false).build(),
        )
            .addConverterFactory(MoshiConverterFactory.create(Moshi.Builder().add(KotlinJsonAdapterFactory()).build()))
            .build().create(RecordImagesApi::class.java)
        return SameOriginRecordImagesApi(
            retrofit.create(RecordImagesApi::class.java),
            endpoint.toHttpUrl(),
            unauthenticatedGateway,
            allowEmulatorLoopback = com.gutcare.app.BuildConfig.DEBUG && com.gutcare.app.BuildConfig.ALLOW_EMULATOR_HTTP,
        )
    }
}

internal class SameOriginRecordImagesApi(
    private val delegate: RecordImagesApi,
    private val origin: okhttp3.HttpUrl,
    private val gateway: RecordImagesApi = delegate,
    private val allowEmulatorLoopback: Boolean = false,
) : RecordImagesApi by delegate {
    override suspend fun upload(url: String, body: RequestBody): Response<Unit> {
        val target = resolveCapabilityUrl(url)
        require(target != null) {
            "Upload URL must be the configured same-origin gateway"
        }
        return delegate.upload(target.toString(), body)
    }

    override suspend fun downloadCapability(url: String): Response<ResponseBody> {
        val target = resolveCapabilityUrl(url)
        require(target != null) {
            "Download grant must be an HTTPS (or configured development HTTP) same-origin gateway capability"
        }
        return gateway.downloadCapability(target.toString())
    }

    private fun resolveCapabilityUrl(value: String): okhttp3.HttpUrl? {
        val target = runCatching { value.toHttpUrl() }.getOrNull() ?: return null
        if (target.scheme != origin.scheme || target.port != origin.port || !target.encodedPath.startsWith("/uploads/")) return null
        if (target.host == origin.host) return target
        if (allowEmulatorLoopback && origin.host == "10.0.2.2" && target.host in setOf("localhost", "127.0.0.1")) {
            return target.newBuilder().host(origin.host).build()
        }
        return null
    }
}

/** Authenticated, purpose-specific image upload and attachment calls. Capabilities are never exposed to UI. */
class RecordImagesRepository(
    private val api: RecordImagesApi,
    private val sessions: com.gutcare.app.core.security.SecureSessionStore? = null,
    private val onSessionInvalidated: () -> Unit = {},
) {
    suspend fun list(type: PatientRecordType, recordId: String): ApiResult<List<RecordImageAttachmentDto>> = when (type) {
        PatientRecordType.DIET -> call { api.dietImages(recordId) }
        PatientRecordType.STOOL -> call { api.stoolImages(recordId) }
        else -> ApiResult.Failure(null, "UNSUPPORTED_RECORD_TYPE")
    }

    suspend fun latestStoolRecognition(recordId: String): ApiResult<RecordImageRecognitionRequestDto> =
        call { api.latestStoolRecognition(recordId) }

    suspend fun uploadAndAttach(
        type: PatientRecordType,
        recordId: String,
        recordVersion: Int,
        imageSetVersion: Int,
        idempotencyKey: String,
        fileName: String,
        contentType: String,
        content: RequestBody,
        sizeBytes: Long,
    ): ApiResult<RecordImageAttachmentDto> {
        if (type != PatientRecordType.DIET && type != PatientRecordType.STOOL) return ApiResult.Failure(null, "UNSUPPORTED_RECORD_TYPE")
        if (idempotencyKey.length !in 8..128 || contentType !in setOf("image/jpeg", "image/png") || sizeBytes !in 1..RecordImageRules.MAX_IMAGE_BYTES) {
            return ApiResult.Failure(null, "INVALID_IMAGE")
        }
        val purpose = if (type == PatientRecordType.DIET) "diet_image" else "stool_image"
        val upload = when (val result = call { api.createUpload(idempotencyKey, UploadCreateDto(purpose, fileName, contentType, sizeBytes)) }) {
            is ApiResult.Failure -> return result
            is ApiResult.Success -> result.value
        }
        when (val result = call { api.upload(upload.uploadUrl, content) }) {
            is ApiResult.Failure -> return result
            is ApiResult.Success -> Unit
        }
        val file = when (val result = call { api.complete(upload.uploadId) }) {
            is ApiResult.Failure -> return result
            is ApiResult.Success -> result.value
        }
        if (file.storageStatus != "available") return ApiResult.Failure(null, "FILE_NOT_AVAILABLE")
        val body = RecordImageAttachDto(file.id, recordVersion, imageSetVersion)
        return when (type) {
            PatientRecordType.DIET -> call { api.attachDiet(recordId, UUID.randomUUID().toString(), body) }
            PatientRecordType.STOOL -> call { api.attachStool(recordId, UUID.randomUUID().toString(), body) }
            else -> ApiResult.Failure(null, "UNSUPPORTED_RECORD_TYPE")
        }
    }

    suspend fun delete(imageId: String, recordVersion: Int, imageSetVersion: Int): ApiResult<Unit> =
        call { api.delete(imageId, recordVersion, imageSetVersion) }

    suspend fun recognitionDisclosure(purpose: String): ApiResult<RecordImageDisclosureDto> =
        call { api.recognitionDisclosure(purpose) }

    suspend fun acknowledgeRecognitionDisclosure(body: RecordImageDisclosureAcknowledgeDto): ApiResult<RecordImageDisclosureTokenDto> =
        call { api.acknowledgeRecognitionDisclosure(body) }

    suspend fun createRecognition(type: PatientRecordType, recordId: String, key: String, body: RecordImageRecognitionCreateDto): ApiResult<RecordImageRecognitionRequestDto> =
        when (type) {
            PatientRecordType.DIET -> call { api.createDietRecognition(recordId, key, body) }
            PatientRecordType.STOOL -> call { api.createStoolRecognition(recordId, key, body) }
            else -> ApiResult.Failure(null, "UNSUPPORTED_RECORD_TYPE")
        }

    suspend fun recognitionRequest(requestId: String): ApiResult<RecordImageRecognitionRequestDto> =
        call { api.recognitionRequest(requestId) }

    suspend fun retryRecognition(requestId: String, key: String, body: RecordImageRecognitionCreateDto): ApiResult<RecordImageRecognitionRequestDto> =
        call { api.retryRecognition(requestId, key, body) }

    suspend fun decideRecognitionCandidate(candidateId: String, key: String, body: RecordImageCandidateDecisionDto): ApiResult<Unit> =
        call { api.decideRecognitionCandidate(candidateId, key, body) }

    /** Requests a fresh short-lived grant on every preview; neither grant nor bytes are persisted. */
    suspend fun downloadPreview(attachmentId: String): ApiResult<ByteArray> {
        val grant = when (val result = call { api.createDownloadGrant(attachmentId) }) {
            is ApiResult.Failure -> return result
            is ApiResult.Success -> result.value
        }
        return try {
            val response = api.downloadCapability(grant.downloadUrl)
            if (!response.isSuccessful) return ApiResult.Failure(response.code(), "DOWNLOAD_FAILED")
            val body = response.body() ?: return ApiResult.Failure(response.code(), "INVALID_RESPONSE")
            body.use {
                val contentType = it.contentType()?.let { type -> "${type.type}/${type.subtype}" }
                if (contentType !in setOf("image/jpeg", "image/png")) return ApiResult.Failure(415, "UNSUPPORTED_IMAGE_TYPE")
                val source = it.source()
                val output = java.io.ByteArrayOutputStream()
                val buffer = ByteArray(8192)
                var total = 0
                while (true) {
                    val count = source.read(buffer)
                    if (count < 0) break
                    total += count
                    if (total > RecordImageRules.MAX_IMAGE_BYTES) return ApiResult.Failure(413, "IMAGE_TOO_LARGE")
                    output.write(buffer, 0, count)
                }
                if (total == 0) ApiResult.Failure(null, "INVALID_RESPONSE") else ApiResult.Success(output.toByteArray())
            }
        } catch (cancelled: CancellationException) { throw cancelled
        } catch (_: java.io.IOException) { ApiResult.Failure(null, "NETWORK_ERROR")
        } catch (_: IllegalArgumentException) { ApiResult.Failure(null, "UNSAFE_DOWNLOAD_URL")
        } catch (_: Exception) { ApiResult.Failure(null, "INVALID_RESPONSE") }
    }

    private suspend fun <T> call(request: suspend () -> Response<T>): ApiResult<T> = try {
        val response = request()
        if (response.isSuccessful) {
            if (response.code() == 204) @Suppress("UNCHECKED_CAST") ApiResult.Success(Unit as T)
            else response.body()?.let(ApiResult<T>::Success) ?: ApiResult.Failure(response.code(), "INVALID_RESPONSE")
        } else {
            val problem = response.errorBody()?.use { ProblemDetailsParser.parse(it.string()) }
            if (response.code() == 401) { sessions?.clear(); onSessionInvalidated() }
            ApiResult.Failure(response.code(), problem?.code ?: "HTTP_ERROR", problem?.requestId)
        }
    } catch (cancelled: CancellationException) { throw cancelled
    } catch (_: java.io.IOException) { ApiResult.Failure(null, "NETWORK_ERROR")
    } catch (_: Exception) { ApiResult.Failure(null, "INVALID_RESPONSE") }
}
