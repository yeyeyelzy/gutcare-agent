package com.gutcare.app.core.network

import com.squareup.moshi.Moshi
import okhttp3.OkHttpClient
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory

object BusinessApiFactory {
    fun create(baseUrl: String, client: OkHttpClient = OkHttpClient()): BusinessApi {
        require(baseUrl.startsWith("https://")) { "Business API must use HTTPS" }
        return Retrofit.Builder()
            .baseUrl(baseUrl)
            .client(client)
            .addConverterFactory(MoshiConverterFactory.create(Moshi.Builder().build()))
            .build()
            .create(BusinessApi::class.java)
    }
}
