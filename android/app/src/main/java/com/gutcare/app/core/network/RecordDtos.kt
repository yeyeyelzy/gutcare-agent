package com.gutcare.app.core.network

import com.squareup.moshi.Json
import com.squareup.moshi.JsonWriter
import okhttp3.RequestBody
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import okio.Buffer

/** Generic F03-F05 payload. Callers populate only fields allowed by the selected record type. */
data class RecordPayloadDto(
    @Json(name = "meal_type") val mealType: String? = null,
    @Json(name = "text_description") val textDescription: String? = null,
    val items: List<RecordItemDto>? = null,
    @Json(name = "portion_note") val portionNote: String? = null,
    @Json(name = "cooking_method") val cookingMethod: String? = null,
    @Json(name = "subjective_note") val subjectiveNote: String? = null,
    @Json(name = "bristol_type") val bristolType: Int? = null,
    @Json(name = "color_code") val colorCode: String? = null,
    @Json(name = "blood_reported") val bloodReported: Boolean? = null,
    @Json(name = "urgency_level") val urgencyLevel: Int? = null,
    @Json(name = "bowel_amount") val bowelAmount: String? = null,
    @Json(name = "process_sensation") val processSensation: List<String>? = null,
    @Json(name = "symptom_status") val symptomStatus: String? = null,
    @Json(name = "duration_minutes") val durationMinutes: Int? = null,
    val notes: String? = null,
    @Json(name = "companion_signs") val companionSigns: List<String>? = null,
)

data class RecordItemDto(
    val name: String? = null,
    @Json(name = "category_code") val categoryCode: String? = null,
    @Json(name = "amount_text") val amountText: String? = null,
    @Json(name = "symptom_code") val symptomCode: String? = null,
    @Json(name = "other_description") val otherDescription: String? = null,
    val severity: Int? = null,
    @Json(name = "body_location") val bodyLocation: String? = null,
)

data class RecordWriteDto(@Json(name = "occurred_at") val occurredAt: String, val payload: RecordPayloadDto)
data class RecordPatchDto(
    @Json(name = "record_version") val recordVersion: Int,
    @Json(name = "occurred_at") val occurredAt: String,
    val payload: RecordPayloadDto,
)
data class RecordVersionRequestDto(@Json(name = "record_version") val recordVersion: Int)
data class RecordDto(
    val id: String,
    @Json(name = "record_version") val recordVersion: Int,
    @Json(name = "occurred_at") val occurredAt: String,
    val payload: RecordPayloadDto,
    @Json(name = "created_at") val createdAt: String,
    @Json(name = "updated_at") val updatedAt: String,
    @Json(name = "image_set_version") val imageSetVersion: Int = 0,
)
data class RecordPageDto(val items: List<RecordDto>, @Json(name = "next_cursor") val nextCursor: String? = null)
data class SymptomStatusEventDto(val status: String, @Json(name = "record_version") val recordVersion: Int, @Json(name = "changed_at") val changedAt: String)
data class SymptomStatusHistoryDto(
    @Json(name = "symptom_record_id") val symptomRecordId: String,
    @Json(name = "current_status") val currentStatus: String,
    val events: List<SymptomStatusEventDto>,
)

data class MoodWriteDto(
    @Json(name = "occurred_at") val occurredAt: String,
    @Json(name = "mood_level") val moodLevel: Int,
    @Json(name = "emotion_tags") val emotionTags: List<String> = emptyList(),
    val note: String? = null,
)
data class MoodPatchDto(
    @Json(name = "record_version") val recordVersion: Int,
    @Json(name = "occurred_at") val occurredAt: String? = null,
    @Json(name = "mood_level") val moodLevel: Int? = null,
    @Json(name = "emotion_tags") val emotionTags: List<String>? = null,
    // A wrapper with value=null clears the note; a null wrapper omits an untouched field.
    val note: ExplicitNullableString? = null,
)

/** Distinguishes an explicit JSON null from an omitted nullable PATCH field. */
data class ExplicitNullableString(val value: String?)

/** PATCH omits untouched fields while preserving JSON null when the patient clears note. */
fun MoodPatchDto.toRequestBody(): RequestBody {
    val buffer = Buffer()
    val writer = JsonWriter.of(buffer)
    writer.serializeNulls = true
    writer.beginObject()
    writer.name("record_version").value(recordVersion)
    occurredAt?.let { writer.name("occurred_at").value(it) }
    moodLevel?.let { writer.name("mood_level").value(it) }
    emotionTags?.let { tags ->
        writer.name("emotion_tags").beginArray()
        tags.forEach(writer::value)
        writer.endArray()
    }
    note?.let { explicit ->
        writer.name("note")
        explicit.value?.let(writer::value) ?: writer.nullValue()
    }
    writer.endObject()
    writer.close()
    return buffer.readByteString().toRequestBody("application/json; charset=utf-8".toMediaType())
}
data class MoodSummaryDto(
    val id: String,
    @Json(name = "occurred_at") val occurredAt: String,
    @Json(name = "mood_level") val moodLevel: Int,
    @Json(name = "emotion_tags") val emotionTags: List<String>,
    @Json(name = "record_version") val recordVersion: Int,
    @Json(name = "created_at") val createdAt: String,
    @Json(name = "updated_at") val updatedAt: String,
)
data class MoodDetailDto(
    val id: String,
    @Json(name = "occurred_at") val occurredAt: String,
    @Json(name = "mood_level") val moodLevel: Int,
    @Json(name = "emotion_tags") val emotionTags: List<String>,
    @Json(name = "record_version") val recordVersion: Int,
    @Json(name = "created_at") val createdAt: String,
    @Json(name = "updated_at") val updatedAt: String,
    val note: String?,
)
data class MoodPageDto(val items: List<MoodSummaryDto>, @Json(name = "next_cursor") val nextCursor: String?)

data class HistoryTargetDto(val type: String, val id: String)
data class HistoryItemDto(val id: String, val type: String, @Json(name = "occurred_at") val occurredAt: String, val target: HistoryTargetDto)
data class HistoryPageDto(val items: List<HistoryItemDto>, @Json(name = "next_cursor") val nextCursor: String?)

enum class PatientRecordType(val route: String) { DIET("diet-records"), STOOL("stool-records"), SYMPTOM("symptom-records") }
