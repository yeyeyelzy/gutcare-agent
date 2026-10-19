package com.gutcare.app.core.network

import com.squareup.moshi.Json
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory

/** RFC 9457 fields plus contract-defined extensions. */
data class ProblemDetails(
    val type: String,
    val title: String,
    val status: Int,
    val detail: String? = null,
    val instance: String? = null,
    val code: String,
    @param:Json(name = "request_id") val requestId: String,
    val errors: List<Map<String, Any?>>? = null,
)

object ProblemDetailsParser {
    private val adapter = Moshi.Builder().add(KotlinJsonAdapterFactory()).build().adapter(ProblemDetails::class.java)

    fun parse(json: String): ProblemDetails? = runCatching { adapter.fromJson(json) }.getOrNull()
}
