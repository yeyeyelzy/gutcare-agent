package com.gutcare.app.core.network

import com.squareup.moshi.JsonReader
import okio.Buffer

/** A deliberately small, non-sensitive diagnostic classification for registration failures. */
enum class AuthFailureReason {
    HEALTH_CONSENT_REQUIRED,
    UNSUPPORTED_POLICY_VERSION,
    POLICY_VERSION_MISMATCH,
    OTHER,
    ;

    companion object {
        fun fromBackendDetail(detail: String?): AuthFailureReason = when (detail) {
            "Health data processing consent is required" -> HEALTH_CONSENT_REQUIRED
            "Unsupported consent policy version" -> UNSUPPORTED_POLICY_VERSION
            "Consent policy version does not match" -> POLICY_VERSION_MISMATCH
            else -> OTHER
        }
    }
}

/** RFC 9457 metadata used by auth; free-form detail/extensions are intentionally discarded. */
data class ProblemDetails(
    val status: Int?,
    val code: String?,
    val requestId: String?,
    val reason: AuthFailureReason,
)

object ProblemDetailsParser {
    fun parse(json: String): ProblemDetails? = runCatching {
        var status: Int? = null
        var code: String? = null
        var requestId: String? = null
        var reason = AuthFailureReason.OTHER
        JsonReader.of(Buffer().writeUtf8(json)).use { reader ->
            reader.beginObject()
            while (reader.hasNext()) {
                when (reader.nextName()) {
                    "status" -> status = reader.nextInt()
                    "code" -> code = reader.nextString()
                    "request_id" -> requestId = reader.nextString()
                    "detail" -> reason = AuthFailureReason.fromBackendDetail(
                        if (reader.peek() == JsonReader.Token.NULL) { reader.nextNull<Unit>(); null } else reader.nextString(),
                    )
                    else -> reader.skipValue()
                }
            }
            reader.endObject()
        }
        ProblemDetails(status, code, requestId, reason)
    }.getOrNull()
}
