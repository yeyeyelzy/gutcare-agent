package com.gutcare.app.core.network

import okhttp3.RequestBody
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

/** Retrofit gateway kept separate so F06 can be wired into the authenticated API composition. */
interface MedicationGateway {
    @GET("medication-plans") suspend fun listPlans(): Response<List<MedicationPlanDto>>
    @POST("medication-plans") suspend fun createPlan(@Header("Idempotency-Key") key: String, @Body body: MedicationPlanCreateDto): Response<MedicationPlanDto>
    @PATCH("medication-plans/{plan_id}") suspend fun patchPlan(@Path("plan_id") id: String, @Body body: RequestBody): Response<MedicationPlanDto>
    @DELETE("medication-plans/{plan_id}") suspend fun deletePlan(@Path("plan_id") id: String, @Query("record_version") version: Int): Response<Unit>
    @POST("medication-plans/{plan_id}/transitions") suspend fun transitionPlan(@Path("plan_id") id: String, @Header("Idempotency-Key") key: String, @Body body: MedicationPlanTransitionDto): Response<MedicationPlanDto>
    @GET("medication-plans/{plan_id}/schedules") suspend fun listSchedules(@Path("plan_id") planId: String): Response<List<MedicationScheduleDto>>
    @POST("medication-plans/{plan_id}/schedules") suspend fun createSchedule(@Path("plan_id") planId: String, @Header("Idempotency-Key") key: String, @Body body: MedicationScheduleWriteDto): Response<MedicationScheduleDto>
    @PATCH("medication-schedules/{schedule_id}") suspend fun patchSchedule(@Path("schedule_id") id: String, @Body body: MedicationScheduleWriteDto): Response<MedicationScheduleDto>
    @DELETE("medication-schedules/{schedule_id}") suspend fun deleteSchedule(@Path("schedule_id") id: String, @Query("record_version") version: Int): Response<Unit>
    @GET("medication-checkins") suspend fun listCheckins(@Query("start") start: String, @Query("end") end: String): Response<List<MedicationCheckinDto>>
    @GET("medication-checkins/today") suspend fun todayCheckins(): Response<List<MedicationCheckinDto>>
    @PATCH("medication-checkins/{checkin_id}") suspend fun patchCheckin(@Path("checkin_id") id: String, @Body body: MedicationCheckinUpdateDto): Response<MedicationCheckinDto>
}
