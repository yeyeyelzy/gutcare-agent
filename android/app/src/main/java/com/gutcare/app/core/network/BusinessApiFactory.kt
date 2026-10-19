package com.gutcare.app.core.network

import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import okhttp3.OkHttpClient
import okhttp3.HttpUrl.Companion.toHttpUrl
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory

object BusinessApiFactory {
    private fun moshi() = Moshi.Builder().add(KotlinJsonAdapterFactory()).build()

    fun createConfigured(
        accessTokens: AccessTokenProvider,
        authenticator: SessionAuthenticator,
        client: OkHttpClient = OkHttpClient.Builder().build(),
    ): BusinessApi = create(
        ApiConfiguration(
            baseUrl = com.gutcare.app.BuildConfig.API_BASE_URL,
            isDebug = com.gutcare.app.BuildConfig.DEBUG,
            allowEmulatorHttp = com.gutcare.app.BuildConfig.ALLOW_EMULATOR_HTTP,
        ),
        accessTokens,
        authenticator,
        client,
    )

    /** Public authentication client: deliberately has neither bearer interception nor Authenticator. */
    fun createPlainConfigured(client: OkHttpClient = OkHttpClient.Builder().build()): BusinessApi {
        val endpoint = ApiEndpoint.validate(
            ApiConfiguration(
                baseUrl = com.gutcare.app.BuildConfig.API_BASE_URL,
                isDebug = com.gutcare.app.BuildConfig.DEBUG,
                allowEmulatorHttp = com.gutcare.app.BuildConfig.ALLOW_EMULATOR_HTTP,
            ),
        )
        return Retrofit.Builder()
            .baseUrl(endpoint)
            .client(client)
            .addConverterFactory(MoshiConverterFactory.create(moshi()))
            .build()
            .create(BusinessApi::class.java)
    }

    fun create(baseUrl: String, client: OkHttpClient = OkHttpClient()): BusinessApi {
        require(baseUrl.startsWith("https://")) { "Business API must use HTTPS" }
        return Retrofit.Builder()
            .baseUrl(baseUrl)
            .client(client)
            .addConverterFactory(MoshiConverterFactory.create(moshi()))
            .build()
            .create(BusinessApi::class.java)
    }

    fun create(
        config: ApiConfiguration,
        accessTokens: AccessTokenProvider,
        authenticator: SessionAuthenticator,
        client: OkHttpClient = OkHttpClient.Builder().build(),
    ): BusinessApi {
        val endpoint = ApiEndpoint.validate(config)
        val configured = client.newBuilder()
            .addInterceptor(BearerTokenInterceptor(accessTokens))
            .authenticator(authenticator)
            .build()
        return Retrofit.Builder()
            .baseUrl(endpoint)
            .client(configured)
            .addConverterFactory(MoshiConverterFactory.create(moshi()))
            .build()
            .create(BusinessApi::class.java)
    }
}

data class ApiConfiguration(val baseUrl: String, val isDebug: Boolean, val allowEmulatorHttp: Boolean)

object ApiEndpoint {
    fun validate(config: ApiConfiguration): String {
        val url = config.baseUrl.toHttpUrl()
        require(url.encodedPath.endsWith("/")) { "API base URL must end with /" }
        if (url.isHttps) return url.toString()
        require(config.isDebug && config.allowEmulatorHttp && url.scheme == "http" && url.host == "10.0.2.2") {
            "Cleartext API is allowed only for explicit debug emulator configuration"
        }
        return url.toString()
    }
}
