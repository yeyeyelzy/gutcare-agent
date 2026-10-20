package com.gutcare.app.core.network

import com.gutcare.app.core.security.SecureSessionStore
import kotlinx.coroutines.CancellationException
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import okio.Buffer
import com.squareup.moshi.JsonWriter
import retrofit2.Response

/** Authenticated F06 calls. Conflicts are returned as failures; no local state is overwritten. */
class MedicationRepository(
    private val gateway: MedicationGateway,
    private val sessions: SecureSessionStore? = null,
    private val onSessionInvalidated: () -> Unit = {},
) {
    suspend fun listPlans() = call { gateway.listPlans() }
    suspend fun createPlan(key: String, body: MedicationPlanCreateDto): ApiResult<MedicationPlanDto> =
        if (!validKey(key)) ApiResult.Failure(null, "IDEMPOTENCY_KEY_INVALID") else call { gateway.createPlan(key, body) }
    suspend fun patchPlan(id: String, body: MedicationPlanPatchDto) = call { gateway.patchPlan(id, body.toRequestBody()) }
    suspend fun deletePlan(id: String, recordVersion: Int): ApiResult<Unit> = call { gateway.deletePlan(id, recordVersion) }
    suspend fun transitionPlan(id: String, key: String, body: MedicationPlanTransitionDto): ApiResult<MedicationPlanDto> =
        if (!validKey(key)) ApiResult.Failure(null, "IDEMPOTENCY_KEY_INVALID") else call { gateway.transitionPlan(id, key, body) }
    suspend fun listSchedules(planId: String) = call { gateway.listSchedules(planId) }
    suspend fun createSchedule(planId: String, key: String, body: MedicationScheduleWriteDto): ApiResult<MedicationScheduleDto> =
        if (!validKey(key)) ApiResult.Failure(null, "IDEMPOTENCY_KEY_INVALID") else call { gateway.createSchedule(planId, key, body) }
    suspend fun patchSchedule(id: String, body: MedicationScheduleWriteDto) = call { gateway.patchSchedule(id, body) }
    suspend fun deleteSchedule(id: String, recordVersion: Int): ApiResult<Unit> = call { gateway.deleteSchedule(id, recordVersion) }
    suspend fun listCheckins(start: String, end: String) = call { gateway.listCheckins(start, end) }
    suspend fun todayCheckins() = call { gateway.todayCheckins() }
    suspend fun updateCheckin(id: String, body: MedicationCheckinUpdateDto) = call { gateway.patchCheckin(id, body) }

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

    private fun validKey(key: String) = key.length in 8..128
}

/** Strict PATCH writer preserves explicit clears while omitting fields the patient did not edit. */
fun MedicationPlanPatchDto.toRequestBody(): RequestBody {
    val buffer = Buffer()
    val writer = JsonWriter.of(buffer)
    writer.serializeNulls = true
    writer.beginObject().name("record_version").value(recordVersion)
    medicationName?.let { writer.name("medication_name").value(it) }
    dosageText?.let { writer.name("dosage_text"); it.value?.let(writer::value) ?: writer.nullValue() }
    routeCode?.let { writer.name("route_code"); it.value?.let(writer::value) ?: writer.nullValue() }
    startDate?.let { writer.name("start_date"); it.value?.let(writer::value) ?: writer.nullValue() }
    endDate?.let { writer.name("end_date"); it.value?.let(writer::value) ?: writer.nullValue() }
    confirmationStatus?.let { writer.name("confirmation_status").value(it) }
    writer.endObject().close()
    return buffer.readByteString().toRequestBody("application/json; charset=utf-8".toMediaType())
}
