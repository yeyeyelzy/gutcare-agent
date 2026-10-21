package com.gutcare.app.core.network

import com.gutcare.app.core.security.SecureSessionStore
import kotlinx.coroutines.CancellationException
import com.squareup.moshi.JsonWriter
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import okio.Buffer

/** Authenticated F07 CRUD. Error bodies are reduced to the shared safe Problem Details fields. */
class ActivityRecordsRepository(
    private val api: BusinessApi,
    private val sessions: SecureSessionStore? = null,
    private val onSessionInvalidated: () -> Unit = {},
) {
    suspend fun list(cursor: String? = null, limit: Int = 50) = call { api.listActivityRecords(cursor, limit) }
    suspend fun create(body: ActivityWriteDto) = call { api.createActivityRecord(body) }
    suspend fun detail(id: String) = call { api.getActivityRecord(id) }
    suspend fun update(id: String, body: ActivityPatchDto) = call { api.patchActivityRecord(id, body.toRequestBody()) }
    suspend fun delete(id: String, version: Int): ApiResult<Unit> = call { api.deleteActivityRecord(id, RecordVersionRequestDto(version)) }

    private suspend fun <T> call(request: suspend () -> retrofit2.Response<T>): ApiResult<T> = try {
        val response = request()
        if (response.isSuccessful) {
            if (response.code() == 204) @Suppress("UNCHECKED_CAST") ApiResult.Success(Unit as T)
            else response.body()?.let(ApiResult<T>::Success) ?: ApiResult.Failure(response.code(), "INVALID_RESPONSE")
        } else {
            val problem = response.errorBody()?.use { ProblemDetailsParser.parse(it.string()) }
            if (response.code() == 401) { sessions?.clear(); onSessionInvalidated() }
            ApiResult.Failure(response.code(), problem?.code ?: "HTTP_ERROR", problem?.requestId)
        }
    } catch (cancelled: CancellationException) {
        throw cancelled
    } catch (_: java.io.IOException) {
        ApiResult.Failure(null, "NETWORK_ERROR")
    } catch (_: Exception) {
        ApiResult.Failure(null, "INVALID_RESPONSE")
    }
}

/** Explicitly writes description:null so switching away from `other` clears the old description. */
internal fun ActivityPatchDto.toRequestBody(): RequestBody {
    val buffer = Buffer()
    val writer = JsonWriter.of(buffer)
    writer.serializeNulls = true
    writer.beginObject()
    writer.name("record_version").value(recordVersion)
    activityType?.let { writer.name("activity_type").value(it) }
    writer.name("description")
    description?.let(writer::value) ?: writer.nullValue()
    intensity?.let { writer.name("intensity").value(it) }
    subjectiveFeeling?.let { writer.name("subjective_feeling").value(it) }
    durationMinutes?.let { writer.name("duration_minutes").value(it.toLong()) }
    occurredAt?.let { writer.name("occurred_at").value(it) }
    writer.endObject()
    writer.close()
    return buffer.readByteString().toRequestBody("application/json; charset=utf-8".toMediaType())
}
