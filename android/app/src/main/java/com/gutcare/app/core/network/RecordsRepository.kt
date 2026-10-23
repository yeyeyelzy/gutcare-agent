package com.gutcare.app.core.network

import retrofit2.Response
import kotlinx.coroutines.CancellationException
import com.gutcare.app.core.security.SecureSessionStore

sealed interface ApiResult<out T> {
    data class Success<T>(val value: T) : ApiResult<T>
    data class Failure(val status: Int?, val code: String?, val requestId: String? = null) : ApiResult<Nothing>
}

/** Network-only record access. Error bodies are reduced to stable RFC 9457 fields and never retained. */
class RecordsRepository(
    private val api: BusinessApi,
    private val sessions: SecureSessionStore? = null,
    private val onSessionInvalidated: () -> Unit = {},
) {
    suspend fun list(type: PatientRecordType, cursor: String? = null, limit: Int? = null, since: String? = null, until: String? = null) =
        call { api.listRecords(type.route, cursor, limit, since, until) }
    suspend fun create(type: PatientRecordType, idempotencyKey: String, body: RecordWriteDto): ApiResult<RecordDto> {
        if (idempotencyKey.length !in 8..128) return ApiResult.Failure(null, "IDEMPOTENCY_KEY_INVALID")
        return call { api.createRecord(type.route, idempotencyKey, body) }
    }
    suspend fun detail(type: PatientRecordType, id: String) = call { api.getRecord(type.route, id) }
    suspend fun update(type: PatientRecordType, id: String, body: RecordPatchDto) = call { api.updateRecord(type.route, id, body) }
    suspend fun delete(type: PatientRecordType, id: String, recordVersion: Int): ApiResult<Unit> =
        call { api.deleteRecord(type.route, id, recordVersion) }
    suspend fun symptomStatusHistory(id: String) = call { api.symptomStatusHistory(id) }

    suspend fun listMood(cursor: String? = null, limit: Int? = null, since: String? = null, until: String? = null) =
        call { api.listMoodRecords(cursor, limit, since, until) }
    suspend fun createMood(idempotencyKey: String, body: MoodWriteDto): ApiResult<MoodDetailDto> {
        if (idempotencyKey.length !in 1..128) return ApiResult.Failure(null, "IDEMPOTENCY_KEY_INVALID")
        return call { api.createMoodRecord(idempotencyKey, body) }
    }
    suspend fun moodDetail(id: String) = call { api.getMoodRecord(id) }
    suspend fun updateMood(id: String, body: MoodPatchDto) = call { api.updateMoodRecord(id, body.toRequestBody()) }
    suspend fun deleteMood(id: String, recordVersion: Int): ApiResult<Unit> =
        call { api.deleteMoodRecord(id, RecordVersionRequestDto(recordVersion)) }
    suspend fun history(cursor: String? = null, limit: Int? = null, categories: List<String>? = null, since: String? = null, until: String? = null) =
        call { api.historyTimeline(cursor, limit, categories, since, until) }
    suspend fun listRiskAlerts(cursor: String? = null, limit: Int? = null, unreadOnly: Boolean? = null) =
        call { api.listRiskAlerts(cursor, limit, unreadOnly) }
    suspend fun riskAlert(id: String) = call { api.getRiskAlert(id) }
    suspend fun markRiskAlertRead(id: String) = call { api.readRiskAlert(id) }
    suspend fun reevaluateRiskAlert(id: String) = call { api.reevaluateRiskAlert(id) }
    suspend fun trends(from: String, to: String, bucket: String = "day") = call { api.getTrends(from, to, bucket) }

    private suspend fun <T> call(request: suspend () -> Response<T>): ApiResult<T> = try {
        val response = request()
        if (response.isSuccessful) {
            if (response.code() == 204) @Suppress("UNCHECKED_CAST") ApiResult.Success(Unit as T)
            else response.body()?.let(ApiResult<T>::Success) ?: ApiResult.Failure(response.code(), "INVALID_RESPONSE")
        } else {
            val problem = response.errorBody()?.use { ProblemDetailsParser.parse(it.string()) }
            if (response.code() == 401) {
                sessions?.clear()
                onSessionInvalidated()
            }
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
