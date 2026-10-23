package com.gutcare.app.ui.notifications

import com.gutcare.app.core.network.NotificationTargetDto
import com.gutcare.app.core.network.PatientNotificationDto
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class NotificationTargetTest {
    private val id = "c2e5c22e-8f26-4d12-9b68-2b71cdbd065f"

    @Test fun onlyContractTargetsWithUuidAreRoutable() {
        assertEquals(SafeNotificationTarget.Risk(id), safeNotificationTarget(notification("risk_alert")))
        assertEquals(SafeNotificationTarget.Medication(id), safeNotificationTarget(notification("medication_checkin")))
        assertEquals(SafeNotificationTarget.Analysis(id), safeNotificationTarget(notification("analysis_task")))
        assertEquals(SafeNotificationTarget.Advice(id), safeNotificationTarget(notification("advice")))
        assertNull(safeNotificationTarget(notification("arbitrary_url")))
        assertNull(safeNotificationTarget(notification("risk_alert", id = "../../settings")))
        assertNull(safeNotificationTarget(notification("risk_alert", unavailable = true)))
    }

    private fun notification(type: String, id: String = this.id, unavailable: Boolean = false) = PatientNotificationDto(
        id = this.id,
        eventType = "risk_alert_created",
        category = "risk",
        priority = "risk",
        occurredAt = "2026-10-20T10:00:00Z",
        createdAt = "2026-10-20T10:00:00Z",
        readAt = null,
        target = NotificationTargetDto(type, id),
        targetUnavailable = unavailable,
    )
}
