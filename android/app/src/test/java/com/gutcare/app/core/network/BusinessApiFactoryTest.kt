package com.gutcare.app.core.network

import org.junit.Assert.assertThrows
import org.junit.Test

class BusinessApiFactoryTest {
    @Test
    fun rejectsCleartextBaseUrls() {
        assertThrows(IllegalArgumentException::class.java) {
            BusinessApiFactory.create("http://localhost/")
        }
    }
}
