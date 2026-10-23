package com.gutcare.app.core.network

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Opt-in local demo helper. Credentials are accepted only as instrumentation arguments and
 * remain outside source control. A successful login leaves the encrypted refresh session in
 * the target app so the normal startup restore path can open the demo account.
 */
@RunWith(AndroidJUnit4::class)
class DemoSessionBootstrapTest {
    @Test
    fun bootstrapLocalDemoSession() = runBlocking {
        val arguments = InstrumentationRegistry.getArguments()
        val email = arguments.getString("demoEmail")
        val password = arguments.getString("demoPassword")
        assumeTrue("Local demo bootstrap is opt-in", !email.isNullOrBlank() && !password.isNullOrBlank())
        val app = InstrumentationRegistry.getInstrumentation().targetContext
        val result = AndroidAuthComposition(app).repository.login(checkNotNull(email), checkNotNull(password))
        assertTrue("Local demo session bootstrap failed", result is AuthWorkflowResult.Success)
    }
}
