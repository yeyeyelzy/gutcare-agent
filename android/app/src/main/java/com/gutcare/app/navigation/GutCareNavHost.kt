package com.gutcare.app.navigation

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.lifecycle.viewmodel.compose.viewModel
import com.gutcare.app.core.network.PatientProfileDto
import com.gutcare.app.core.network.RecordsRepository
import com.gutcare.app.core.network.MedicalDocumentsRepository
import com.gutcare.app.core.network.MedicationRepository
import com.gutcare.app.core.network.AnalysisAdviceRepository
import com.gutcare.app.core.network.PrivacyRepository
import com.gutcare.app.core.network.RecordImagesRepository
import com.gutcare.app.core.network.NotificationRepository
import com.gutcare.app.core.network.ActivityRecordsRepository
import com.gutcare.app.core.network.PatientRecordType
import com.gutcare.app.ui.records.*
import com.gutcare.app.ui.auth.AuthOperationState
import com.gutcare.app.ui.auth.AuthValidators
import com.gutcare.app.ui.auth.AuthWorkflow
import com.gutcare.app.ui.auth.EmailVerificationScreen
import com.gutcare.app.ui.auth.LoginScreen
import com.gutcare.app.ui.auth.MyProfileScreen
import com.gutcare.app.ui.auth.PasswordResetConfirmScreen
import com.gutcare.app.ui.auth.PasswordResetRequestScreen
import com.gutcare.app.ui.auth.ProfileBootstrapScreen
import com.gutcare.app.ui.auth.RegisterCredentialsScreen
import com.gutcare.app.ui.auth.RegistrationDraft
import com.gutcare.app.ui.auth.UnconnectedAuthWorkflow
import com.gutcare.app.ui.auth.WelcomeScreen
import com.gutcare.app.ui.tabs.ProtectedTabShell
import com.gutcare.app.core.network.RegistrationNoticeSummaries
import com.gutcare.app.ui.analysis.AnalysisAdviceViewModel
import com.gutcare.app.ui.analysis.AnalysisAdviceViewModelFactory
import com.gutcare.app.ui.analysis.AnalysisAdviceWorkspace
import com.gutcare.app.ui.analysis.RepositoryAnalysisAdviceGateway
import com.gutcare.app.ui.medication.MedicationViewModel
import com.gutcare.app.ui.medication.MedicationViewModelFactory
import com.gutcare.app.ui.medication.RepositoryMedicationFeatureGateway
import com.gutcare.app.ui.medication.MedicationSection
import com.gutcare.app.ui.medication.MedicationScreen
import com.gutcare.app.ui.privacy.PrivacyViewModel
import com.gutcare.app.ui.privacy.PrivacyViewModelFactory
import com.gutcare.app.ui.privacy.RepositoryPrivacyGateway
import com.gutcare.app.ui.privacy.PrivacySettingsEntry
import com.gutcare.app.ui.risktrend.RiskTrendViewModel
import com.gutcare.app.ui.risktrend.RiskTrendViewModelFactory
import com.gutcare.app.ui.risktrend.RepositoryRiskTrendGateway
import com.gutcare.app.ui.risktrend.RiskTrendDestination
import com.gutcare.app.ui.risktrend.RiskTrendDestinationKind
import com.gutcare.app.ui.records.RecordImagesViewModel
import com.gutcare.app.ui.records.RecordImagesViewModelFactory
import com.gutcare.app.ui.records.RepositoryRecordImagesGateway
import com.gutcare.app.ui.records.RecordImageAttachmentsPanel
import com.gutcare.app.ui.features.FeatureDirectoryScreen
import com.gutcare.app.ui.tabs.TodayDashboardViewModel
import com.gutcare.app.ui.tabs.TodayDashboardViewModelFactory
import com.gutcare.app.ui.notifications.NotificationCenterViewModel
import com.gutcare.app.ui.notifications.NotificationCenterViewModelFactory
import com.gutcare.app.ui.notifications.NotificationCenterScreen
import com.gutcare.app.ui.notifications.NotificationDetailScreen
import com.gutcare.app.ui.notifications.NotificationPreferencesScreen
import com.gutcare.app.ui.notifications.SafeNotificationTarget
import com.gutcare.app.ui.activity.ActivityFeatureEntry
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp

/**
 * Navigation owns public-flow drafts only in Compose memory. The activity supplies session state
 * only after cold-start restoration or login has completed profile bootstrap.
 */
@Composable
fun GutCareNavHost(
    navController: NavHostController,
    sessionState: AppSessionState = AppSessionState.Public,
    authWorkflow: AuthWorkflow = UnconnectedAuthWorkflow,
    onLogout: (((AuthOperationState) -> Unit) -> Unit) = {},
    registrationNoticeSummaries: RegistrationNoticeSummaries? = null,
    recordsRepository: RecordsRepository? = null,
    medicalDocumentsRepository: MedicalDocumentsRepository? = null,
    medicationRepository: MedicationRepository? = null,
    analysisAdviceRepository: AnalysisAdviceRepository? = null,
    privacyRepository: PrivacyRepository? = null,
    recordImagesRepository: RecordImagesRepository? = null,
    notificationRepository: NotificationRepository? = null,
    activityRecordsRepository: ActivityRecordsRepository? = null,
    patientProfile: PatientProfileDto? = null,
) {
    var registrationDraft by remember { mutableStateOf(RegistrationDraft()) }
    var loginOperation by remember { mutableStateOf<AuthOperationState>(AuthOperationState.Idle) }
    var registrationOperation by remember { mutableStateOf<AuthOperationState>(AuthOperationState.Idle) }
    var passwordResetOperation by remember { mutableStateOf<AuthOperationState>(AuthOperationState.Idle) }
    var profileOperation by remember { mutableStateOf<AuthOperationState>(AuthOperationState.Idle) }
    val recordsViewModel: RecordsViewModel = viewModel(
        factory = remember(recordsRepository) {
            RecordsViewModelFactory(recordsRepository?.let(::RepositoryRecordsGateway) ?: UnavailableRecordsGateway())
        },
    )
    val recordsState by recordsViewModel.uiState.collectAsState()
    val medicalDocumentsViewModel: MedicalDocumentsViewModel = viewModel(
        factory = remember(medicalDocumentsRepository) {
            MedicalDocumentsViewModelFactory(medicalDocumentsRepository?.let(::RepositoryMedicalDocumentsGateway) ?: UnavailableMedicalDocumentsGateway())
        },
    )
    val medicalDocumentsState by medicalDocumentsViewModel.uiState.collectAsState()
    val medicationViewModel: MedicationViewModel? = medicationRepository?.let { repository ->
        viewModel(factory = remember(repository) { MedicationViewModelFactory(RepositoryMedicationFeatureGateway(repository)) })
    }
    val analysisViewModel: AnalysisAdviceViewModel? = analysisAdviceRepository?.let { repository ->
        viewModel(factory = remember(repository) { AnalysisAdviceViewModelFactory(RepositoryAnalysisAdviceGateway(repository)) })
    }
    val privacyViewModel: PrivacyViewModel? = privacyRepository?.let { repository ->
        viewModel(factory = remember(repository) { PrivacyViewModelFactory(RepositoryPrivacyGateway(repository)) })
    }
    val riskTrendViewModel: RiskTrendViewModel? = recordsRepository?.let { repository ->
        viewModel(factory = remember(repository) { RiskTrendViewModelFactory(RepositoryRiskTrendGateway(repository)) })
    }
    val recordImagesViewModel: RecordImagesViewModel? = recordImagesRepository?.let { repository ->
        viewModel(factory = remember(repository) { RecordImagesViewModelFactory(RepositoryRecordImagesGateway(repository)) })
    }
    val notificationViewModel: NotificationCenterViewModel? = notificationRepository?.let { repository ->
        viewModel(factory = remember(repository) { NotificationCenterViewModelFactory(repository) })
    }
    val todayDashboardViewModel: TodayDashboardViewModel? = if (recordsRepository != null && medicationRepository != null && analysisAdviceRepository != null && notificationRepository != null) {
        viewModel(factory = remember(recordsRepository, medicationRepository, analysisAdviceRepository, notificationRepository) {
            TodayDashboardViewModelFactory(recordsRepository, medicationRepository, analysisAdviceRepository, notificationRepository)
        })
    } else null
    val todayDashboardState by todayDashboardViewModel?.state?.collectAsState() ?: remember { mutableStateOf(com.gutcare.app.ui.tabs.TodayDashboardState()) }
    val notificationState by notificationViewModel?.state?.collectAsState() ?: remember { mutableStateOf(com.gutcare.app.ui.notifications.NotificationCenterState()) }
    LaunchedEffect(patientProfile?.timezone) { recordsViewModel.setTimeZone(patientProfile?.timezone) }
    LaunchedEffect(sessionState) {
        if (sessionState is AppSessionState.Public) recordsViewModel.clearForLogout()
        if (sessionState is AppSessionState.Public) medicalDocumentsViewModel.clearForLogout()
        if (sessionState is AppSessionState.Public) medicationViewModel?.clearForLogout()
        if (sessionState is AppSessionState.Public) analysisViewModel?.clear()
        if (sessionState is AppSessionState.Public) privacyViewModel?.clearSensitiveTransient()
        if (sessionState is AppSessionState.Public) recordImagesViewModel?.clear()
        if (sessionState is AppSessionState.Public) riskTrendViewModel?.clear()
        if (sessionState is AppSessionState.Public) todayDashboardViewModel?.clearForLogout()
        if (sessionState is AppSessionState.Public) notificationViewModel?.clearForLogout()
    }
    LaunchedEffect(sessionState, patientProfile?.timezone) {
        if (sessionState is AppSessionState.Authenticated) todayDashboardViewModel?.refresh(patientProfile?.timezone)
    }
    LaunchedEffect(sessionState) {
        if (sessionState is AppSessionState.Authenticated) notificationViewModel?.refreshCount()
    }

    fun navigate(route: AppRoute, clearDraft: Boolean = false) {
        if (clearDraft || RoutePolicy.shouldClearRegistrationDraftOnExit(route)) {
            registrationDraft = registrationDraft.clearForExit()
        }
        navController.navigate(RoutePolicy.allowedDestination(sessionState, route).value) {
            launchSingleTop = true
        }
    }

    fun returnToWelcome() {
        registrationDraft = registrationDraft.clearForExit()
        navController.navigate(AppRoute.Welcome.value) {
            popUpTo(navController.graph.findStartDestination().id) { inclusive = true }
            launchSingleTop = true
        }
    }

    fun beginRegistration() {
        registrationOperation = AuthOperationState.Idle
        navigate(AppRoute.RegisterCredentials, clearDraft = true)
    }

    NavHost(
        navController = navController,
        startDestination = RoutePolicy.startDestination(sessionState).value,
    ) {
        composable(AppRoute.Welcome.value) {
            WelcomeScreen(
                onLogin = { navigate(AppRoute.Login, clearDraft = true) },
                onRegister = { beginRegistration() },
            )
        }
        composable(AppRoute.Login.value) {
            LoginScreen(
                operation = loginOperation,
                onLogin = { email, password ->
                    loginOperation = AuthOperationState.Loading
                    authWorkflow.login(email, password) { result ->
                        loginOperation = result
                        if (result is AuthOperationState.Accepted) {
                            navController.navigate(AppRoute.Today.value) {
                                popUpTo(navController.graph.findStartDestination().id) { inclusive = true }
                                launchSingleTop = true
                            }
                        }
                    }
                },
                onBack = { returnToWelcome() },
                onRegister = { beginRegistration() },
                onForgotPassword = { navigate(AppRoute.PasswordResetRequest, clearDraft = true) },
            )
        }
        composable(AppRoute.RegisterCredentials.value) {
            RegisterCredentialsScreen(
                draft = registrationDraft,
                operation = registrationOperation,
                privacyNoticeSummary = registrationNoticeSummaries?.privacy,
                onDraftChange = { registrationDraft = it },
                onContinue = {
                    if (RoutePolicy.canEnterProfile(registrationDraft)) {
                        navigate(AppRoute.RegisterProfile)
                    }
                },
                onBack = { returnToWelcome() },
                onLogin = { navigate(AppRoute.Login, clearDraft = true) },
            )
        }
        composable(AppRoute.RegisterProfile.value) {
            if (RoutePolicy.shouldRedirectFromInvalidRegistrationProfile(registrationDraft, registrationOperation)) {
                LaunchedEffect(Unit) {
                    navController.navigate(AppRoute.RegisterCredentials.value) { launchSingleTop = true }
                }
            } else {
                LaunchedEffect(registrationOperation) {
                    if (registrationOperation is AuthOperationState.Accepted) {
                        navController.navigate(AppRoute.EmailVerification.value) {
                            popUpTo(AppRoute.RegisterCredentials.value) { inclusive = true }
                            launchSingleTop = true
                        }
                        registrationDraft = registrationDraft.clearForExit()
                    }
                }
                ProfileBootstrapScreen(
                    draft = registrationDraft,
                    operation = registrationOperation,
                    healthDataNoticeSummary = registrationNoticeSummaries?.healthData,
                    onDraftChange = { registrationDraft = it },
                    onSubmit = {
                        if (AuthValidators.canSubmitRegistration(registrationDraft)) {
                            registrationOperation = AuthOperationState.Loading
                            authWorkflow.register(registrationDraft) { result ->
                                registrationOperation = result
                            }
                        }
                    },
                    onBack = { navController.popBackStack() },
                )
            }
        }
        composable(AppRoute.EmailVerification.value) {
            EmailVerificationScreen(
                operation = registrationOperation,
                onVerify = { token ->
                    registrationOperation = AuthOperationState.Loading
                    authWorkflow.verifyEmail(token) { result -> registrationOperation = result }
                },
                onGoToLogin = { navigate(AppRoute.Login, clearDraft = true) },
                onBack = { returnToWelcome() },
            )
        }
        composable(AppRoute.PasswordResetRequest.value) {
            PasswordResetRequestScreen(
                operation = passwordResetOperation,
                onRequest = { email ->
                    passwordResetOperation = AuthOperationState.Loading
                    authWorkflow.requestPasswordReset(email) { result -> passwordResetOperation = result }
                },
                onOpenConfirmation = { navigate(AppRoute.PasswordResetConfirm) },
                onBack = { navController.popBackStack() },
            )
        }
        composable(AppRoute.PasswordResetConfirm.value) {
            PasswordResetConfirmScreen(
                operation = passwordResetOperation,
                onConfirm = { token, newPassword ->
                    passwordResetOperation = AuthOperationState.Loading
                    authWorkflow.confirmPasswordReset(token, newPassword) { result -> passwordResetOperation = result }
                },
                onBack = { navController.popBackStack() },
                onGoToLogin = { navigate(AppRoute.Login, clearDraft = true) },
            )
        }
        composable(AppRoute.Today.value) {
            ProtectedRoot(sessionState, navController, RootTab.Today, onLogout) {
                TodayScreen(
                    TodayUiState(
                        dateLabel = todayDashboardState.dateLabel,
                        displayName = patientProfile?.nickname,
                        medication = todayDashboardState.medication.value,
                        medicationUnavailable = todayDashboardState.medication.failed,
                        riskSummary = todayDashboardState.risks.value?.firstOrNull()?.let { alert ->
                            (if (alert.environment == "test_only") "演示测试规则（非临床）· " else "风险提示 · ") + alert.message
                        } ?: if (todayDashboardState.risks.failed) "风险提示暂不可用" else null,
                        recentRecordSummary = todayDashboardState.recentRecord.value,
                        recentRecordMessage = if (todayDashboardState.recentRecord.failed) "近期记录暂不可用" else if (todayDashboardState.recentRecord.value == null) "暂无近期记录" else null,
                        adviceSummary = todayDashboardState.latestAdvice.value,
                        adviceMessage = if (todayDashboardState.latestAdvice.failed) "最新建议暂不可用" else if (todayDashboardState.latestAdvice.value == null) "暂无最新建议" else null,
                        unreadCount = todayDashboardState.unreadCount,
                    ),
                    TodayCallbacks(
                        onQuickRecord = { navigate(recordFormRoute(it)) },
                        onOpenMedication = { navigate(AppRoute.Medication) },
                        onOpenMeals = { navigate(AppRoute.DietRecords) },
                        onOpenTrend = { navigate(AppRoute.Trends) },
                        onOpenProfile = { navigate(AppRoute.HealthArchive) },
                        onOpenNotifications = { navigate(AppRoute.Notifications) },
                    ),
                )
            }
        }
        composable(AppRoute.Records.value) {
            ProtectedRoot(sessionState, navController, RootTab.Records, onLogout) {
                RecordsHubScreen(
                    onOpenCategory = { navController.navigate(categoryRoute(it).value) },
                    onOpenArchive = { navController.navigate(AppRoute.HealthArchive.value) },
                )
            }
        }
        composable(AppRoute.Analysis.value) {
            ProtectedRoot(sessionState, navController, RootTab.Analysis, onLogout) {
                val model = analysisViewModel
                if (model == null) FeatureUnavailable("分析服务尚未配置。")
                else {
                    val state by model.state.collectAsState()
                    AnalysisAdviceWorkspace(state, model)
                }
            }
        }
        composable(AppRoute.Me.value) {
            ProtectedRoot(sessionState, navController, RootTab.Me, onLogout) {
                MyProfileScreen(
                    profile = patientProfile,
                    operation = profileOperation,
                    onSave = { nickname, birthYear, version ->
                        profileOperation = AuthOperationState.Loading
                        authWorkflow.updateProfile(nickname, birthYear, version) { result -> profileOperation = result }
                    },
                    onLogout = { onLogout { profileOperation = it } },
                    onOpenFeatures = { navigate(AppRoute.FeatureDirectory) },
                )
            }
        }
        composable(AppRoute.FeatureDirectory.value) {
            RequireAuthenticated(sessionState, navController) {
                FeatureDirectoryScreen(
                    onBack = { navController.popBackStack() },
                    onMedication = { navigate(AppRoute.Medication) },
                    onRisks = { navigate(AppRoute.RiskAlerts) },
                    onTrends = { navigate(AppRoute.Trends) },
                    onHistory = { navigate(AppRoute.History) },
                    onPrivacy = { navigate(AppRoute.PrivacySettings) },
                    onNotifications = { navigate(AppRoute.Notifications) },
                    onActivity = { navigate(AppRoute.Activity) },
                )
            }
        }
        composable(AppRoute.Medication.value) {
            RequireAuthenticated(sessionState, navController) {
                val model = medicationViewModel
                if (model == null) FeatureUnavailable("用药服务尚未配置。")
                else {
                    val state by model.uiState.collectAsState()
                    LaunchedEffect(Unit) { model.load() }
                    MedicationScreen(
                        state = state, onBack = { navController.popBackStack() }, onRefresh = { model.load() },
                        onSection = model::selectSection, onSelectPlan = model::selectPlan,
                        onHistoryRange = model::setHistoryRange, onCreatePlan = model::createPlan,
                        onTransition = model::transition, onCreateSchedule = model::createSchedule,
                        onToggleSchedule = model::toggleSchedule, onRemoveSchedule = model::removeSchedule,
                        onUpdateCheckin = model::updateCheckin,
                    )
                }
            }
        }
        composable(AppRoute.Activity.value) {
            RequireAuthenticated(sessionState, navController) {
                val repository = activityRecordsRepository
                if (repository == null) FeatureUnavailable("活动记录服务尚未配置。")
                else ActivityFeatureEntry(repository, onBack = { navController.popBackStack() }, onSessionExpired = {
                    navController.navigate(AppRoute.Welcome.value) { popUpTo(navController.graph.findStartDestination().id) { inclusive = true }; launchSingleTop = true }
                })
            }
        }
        composable(AppRoute.RiskAlerts.value) {
            RequireAuthenticated(sessionState, navController) {
                val model = riskTrendViewModel
                if (model == null) FeatureUnavailable("风险提示服务尚未配置。")
                else RiskTrendDestination(model, RiskTrendDestinationKind.RISKS, patientTimeZone = patientProfile?.timezone ?: java.time.ZoneId.systemDefault().id,
                    onNavigate = { destination, id ->
                        if (destination == RiskTrendDestinationKind.RISK_DETAIL && id != null) navController.navigate(riskAlertDetailRoute(id))
                        else navController.popBackStack()
                    })
            }
        }
        composable(AppRoute.RiskAlertDetail.value) { entry ->
            RequireAuthenticated(sessionState, navController) {
                val model = riskTrendViewModel
                val id = entry.arguments?.getString("alertId")
                if (model == null) FeatureUnavailable("风险提示服务尚未配置。")
                else if (id.isNullOrBlank()) LaunchedEffect(Unit) { navController.popBackStack() }
                else RiskTrendDestination(model, RiskTrendDestinationKind.RISK_DETAIL, alertId = id,
                    patientTimeZone = patientProfile?.timezone ?: java.time.ZoneId.systemDefault().id,
                    onNavigate = { _, _ -> navController.popBackStack() })
            }
        }
        composable(AppRoute.Trends.value) {
            RequireAuthenticated(sessionState, navController) {
                val model = riskTrendViewModel
                if (model == null) FeatureUnavailable("趋势服务尚未配置。")
                else RiskTrendDestination(model, RiskTrendDestinationKind.TRENDS,
                    patientTimeZone = patientProfile?.timezone ?: java.time.ZoneId.systemDefault().id,
                    onNavigate = { _, _ -> navController.popBackStack() })
            }
        }
        composable(AppRoute.History.value) {
            RequireAuthenticated(sessionState, navController) {
                val model = riskTrendViewModel
                if (model == null) FeatureUnavailable("历史服务尚未配置。")
                else RiskTrendDestination(model, RiskTrendDestinationKind.HISTORY,
                    patientTimeZone = patientProfile?.timezone ?: java.time.ZoneId.systemDefault().id,
                    onNavigate = { _, _ -> navController.popBackStack() },
                    onOpenHistoryTarget = { type, id ->
                        val recordType = when (type) { "diet" -> "diet"; "stool" -> "stool"; "symptom" -> "symptoms"; "mood" -> "mood"; else -> null }
                        if (recordType != null) navController.navigate(recordDetailRoute(recordType, id))
                    })
            }
        }
        composable(AppRoute.Notifications.value) {
            RequireAuthenticated(sessionState, navController) {
                val model = notificationViewModel
                if (model == null) FeatureUnavailable("通知服务尚未配置。") else {
                    LaunchedEffect(model) { model.load() }
                    NotificationCenterScreen(notificationState, model,
                        onBack = { navController.popBackStack() },
                        onPreferences = { navigate(AppRoute.NotificationPreferences) },
                        onOpenDetail = { navController.navigate(notificationDetailRoute(it)) },
                        onOpenTarget = { target -> openSafeNotificationTarget(target, navController) },
                    )
                }
            }
        }
        composable(AppRoute.NotificationDetail.value) { entry ->
            RequireAuthenticated(sessionState, navController) {
                val model = notificationViewModel
                val id = entry.arguments?.getString("notificationId")
                if (model == null) FeatureUnavailable("通知服务尚未配置。")
                else if (id == null || runCatching { java.util.UUID.fromString(id) }.isFailure) LaunchedEffect(Unit) { navController.popBackStack() }
                else {
                    LaunchedEffect(id) { model.openDetail(id) }
                    NotificationDetailScreen(notificationState, model,
                        onBack = { navController.popBackStack() },
                        onOpenTarget = { target -> openSafeNotificationTarget(target, navController) },
                    )
                }
            }
        }
        composable(AppRoute.NotificationPreferences.value) {
            RequireAuthenticated(sessionState, navController) {
                val model = notificationViewModel
                if (model == null) FeatureUnavailable("通知服务尚未配置。") else {
                    LaunchedEffect(model) { model.loadPreferences() }
                    NotificationPreferencesScreen(notificationState, model, onBack = { navController.popBackStack() })
                }
            }
        }
        composable(AppRoute.PrivacySettings.value) {
            RequireAuthenticated(sessionState, navController) {
                val repository = privacyRepository
                val model = privacyViewModel
                if (repository == null || model == null) FeatureUnavailable("隐私服务尚未配置。")
                else PrivacySettingsEntry(repository = repository, onBack = { navController.popBackStack() }, model = model)
            }
        }
        WorkspaceRecordType.entries.forEach { type ->
            val category = categoryRoute(type)
            val create = recordFormRoute(type.toCategory())
            composable(category.value) {
                RequireAuthenticated(sessionState, navController) {
                    LaunchedEffect(type) { recordsViewModel.load(type) }
                    RecordListScreen(type, recordsState, onBack = { navController.popBackStack() },
                        onRetry = { recordsViewModel.load(type) }, onNew = { navController.navigate(create.value) },
                        onOpen = { navController.navigate(recordDetailRoute(type.routeKey, it.id)) },
                        onLoadMore = { recordsViewModel.loadMore() },
                        onDelete = { recordsViewModel.delete(type, it) })
                }
            }
            val formRoute = create
            composable(formRoute.value) {
                RequireAuthenticated(sessionState, navController) {
                    RecordFormDestination(type, recordsState, recordsViewModel,
                        onBack = { recordsViewModel.clearDraft(); navController.popBackStack() },
                        onCategory = { navController.navigate(recordFormRoute(it).value) },
                        onManageImages = { id -> navController.navigate(recordImagesRoute(type.routeKey, id)) },
                        onSaved = { id ->
                            if (id != null) navController.navigate(recordDetailRoute(type.routeKey, id)) {
                                popUpTo(formRoute.value) { inclusive = true }; launchSingleTop = true
                            } else navController.navigate(categoryRoute(type).value) { popUpTo(formRoute.value) { inclusive = true }; launchSingleTop = true }
                        })
                }
            }
        composable(AppRoute.RecordDetail.value) { entry ->
            RequireAuthenticated(sessionState, navController) {
                val type = recordTypeFromRouteKey(entry.arguments?.getString("recordType"))
                val id = entry.arguments?.getString("recordId")
                if (type == null || id.isNullOrBlank()) {
                    LaunchedEffect(Unit) { navController.popBackStack() }
                } else {
                    LaunchedEffect(type, id) { recordsViewModel.loadDetail(type, id) }
                    DisposableEffect(type, id) { onDispose { recordsViewModel.clearDetail() } }
                    RecordDetailScreen(type, recordsState, onBack = { navController.popBackStack() },
                        onRetry = { recordsViewModel.refreshDetail(type, id) },
                        onEdit = { recordsViewModel.beginEdit(type); navController.navigate(recordEditRoute(type.routeKey, id)) },
                        onDelete = { recordsViewModel.deleteDetail(type) },
                        onManageImages = if (type == WorkspaceRecordType.DIET || type == WorkspaceRecordType.STOOL) {
                            { navController.navigate(recordImagesRoute(type.routeKey, id)) }
                        } else null)
                    LaunchedEffect(recordsState.operation.feedback, recordsState.operation.savedRecordId) {
                        if (recordsState.operation.feedback == "记录已删除。") navController.popBackStack()
                    }
                }
            }
        }
        composable(AppRoute.RecordEdit.value) { entry ->
            RequireAuthenticated(sessionState, navController) {
                val type = recordTypeFromRouteKey(entry.arguments?.getString("recordType"))
                val id = entry.arguments?.getString("recordId")
                if (type == null || id.isNullOrBlank()) {
                    LaunchedEffect(Unit) { navController.popBackStack() }
                } else {
                    LaunchedEffect(type, id) {
                        if (recordsState.editingRecordId != id) {
                            // A direct/deep route must load the record before it can be edited.
                            recordsViewModel.loadDetail(type, id)
                        }
                    }
                    LaunchedEffect(recordsState.detailState, id) {
                        if (recordsState.editingRecordId != id && recordsState.detailState is RecordDetailLoadState.Loaded) recordsViewModel.beginEdit(type)
                    }
                    if (recordsState.editingRecordId == id) {
                        RecordFormDestination(type, recordsState, recordsViewModel,
                            onBack = { recordsViewModel.clearDraft(); navController.popBackStack() },
                            onCategory = { navController.navigate(recordFormRoute(it).value) },
                            onManageImages = { navController.navigate(recordImagesRoute(type.routeKey, it)) },
                            onSaved = { navController.popBackStack() }, editingId = id)
                    } else {
                        RecordEditBootstrapScreen(
                            type = type,
                            state = recordsState,
                            onBack = { recordsViewModel.clearDraft(); navController.popBackStack() },
                            onRetry = { recordsViewModel.refreshDetail(type, id) },
                        )
                    }
                }
            }
        }
        }
        composable(AppRoute.HealthArchive.value) {
            RequireAuthenticated(sessionState, navController) {
                LaunchedEffect(Unit) { medicalDocumentsViewModel.load() }
                MedicalArchiveRoute(
                    model = medicalDocumentsViewModel,
                    onBack = { navController.popBackStack() },
                    onOpenDocument = { id -> navController.navigate(medicalDocumentDetailRoute(id)) },
                )
            }
        }
        composable(AppRoute.MedicalDocumentDetail.value) { entry ->
            RequireAuthenticated(sessionState, navController) {
                val id = entry.arguments?.getString("documentId")
                if (id.isNullOrBlank()) LaunchedEffect(Unit) { navController.popBackStack() }
                else {
                    LaunchedEffect(id) { medicalDocumentsViewModel.open(id) }
                    MedicalDocumentDetailScreen(
                        state = medicalDocumentsState,
                        onBack = { navController.popBackStack() },
                        onRetry = { medicalDocumentsViewModel.open(id) },
                        onDecision = medicalDocumentsViewModel::decide,
                    )
                }
            }
        }
        composable(AppRoute.RecordImages.value) { entry ->
            RequireAuthenticated(sessionState, navController) {
                val type = recordTypeFromRouteKey(entry.arguments?.getString("recordType"))
                val id = entry.arguments?.getString("recordId")
                val model = recordImagesViewModel
                if ((type != WorkspaceRecordType.DIET && type != WorkspaceRecordType.STOOL) || id.isNullOrBlank() || model == null) {
                    LaunchedEffect(Unit) { navController.popBackStack() }
                } else {
                    val imageState by model.uiState.collectAsState()
                    val detail = (recordsState.detailState as? RecordDetailLoadState.Loaded)?.detail
                        ?.takeIf { it.id == id }
                    LaunchedEffect(type, id) {
                        if (detail == null) recordsViewModel.loadDetail(type, id)
                    }
                    DisposableEffect(type, id) { onDispose { model.clear() } }
                    TextButton(onClick = { navController.popBackStack() }) { Text("‹ 返回记录详情") }
                    if (detail == null) FeatureUnavailable("正在读取记录版本…")
                    else RecordImageAttachmentsPanel(
                        type = if (type == WorkspaceRecordType.DIET) PatientRecordType.DIET else PatientRecordType.STOOL,
                        recordId = id,
                        recordVersion = detail.recordVersion,
                        imageSetVersion = detail.imageSetVersion,
                        state = imageState,
                        onLoad = model::load,
                        onUpload = model::upload,
                        onDelete = model::delete,
                        onPreview = model::preview,
                        onClearPreview = model::clearPreview,
                    )
                }
            }
        }
    }
}

private fun openSafeNotificationTarget(target: SafeNotificationTarget, navController: NavHostController) {
    when (target) {
        is SafeNotificationTarget.Risk -> navController.navigate(riskAlertDetailRoute(target.id))
        is SafeNotificationTarget.Medication -> navController.navigate(AppRoute.Medication.value)
        is SafeNotificationTarget.Analysis, is SafeNotificationTarget.Advice -> navController.navigate(AppRoute.Analysis.value)
    }
}

@Composable
private fun ProtectedRoot(
    sessionState: AppSessionState,
    navController: NavHostController,
    selectedTab: RootTab,
    onLogout: (((AuthOperationState) -> Unit) -> Unit),
    content: @Composable () -> Unit,
) {
    RequireAuthenticated(sessionState, navController) {
        ProtectedTabShell(
            selectedTab = selectedTab,
            onLogout = { onLogout { } },
            screenContent = content,
            onSelectTab = { tab ->
                navController.navigate(tab.route.value) {
                    popUpTo(navController.graph.findStartDestination().id) { saveState = true }
                    launchSingleTop = true
                    restoreState = true
                }
            },
        )
    }
}

@Composable
private fun RequireAuthenticated(sessionState: AppSessionState, navController: NavHostController, content: @Composable () -> Unit) {
    if (sessionState !is AppSessionState.Authenticated) {
        LaunchedEffect(Unit) {
            navController.navigate(AppRoute.Welcome.value) {
                popUpTo(navController.graph.findStartDestination().id) { inclusive = true }
                launchSingleTop = true
            }
        }
    } else content()
}

@Composable
private fun RecordFormDestination(
    type: WorkspaceRecordType,
    state: RecordsUiState,
    viewModel: RecordsViewModel,
    onBack: () -> Unit,
    onCategory: (RecordCategory) -> Unit,
    onSaved: (String?) -> Unit,
    onManageImages: (String) -> Unit,
    editingId: String? = null,
) {
    val draft = state.draft
    val operation = state.operation
    LaunchedEffect(operation.feedback, type) {
        if (operation.feedback == "记录已保存。" || operation.feedback == "修改已保存。") {
            val savedId = operation.savedRecordId
            viewModel.clearDraft()
            onSaved(savedId)
        }
    }
    DisposableEffect(type) { onDispose { viewModel.clearDraft() } }
    when (type) {
        WorkspaceRecordType.DIET -> DietRecordScreen(
            DietRecordUiState(
                mealType = MealType.entries.firstOrNull { mealCode(it) == draft.mealType } ?: MealType.Lunch,
                occurredDate = draft.date, occurredTime = draft.time, textDescription = draft.description,
                draftItems = draft.dietItems.map { DietDraftItemUiState(it.name.orEmpty(), it.amountText) },
                portionSize = PortionSize.entries.firstOrNull { it.label == draft.portionNote },
                cookingStyle = CookingStyle.entries.firstOrNull { it.label == draft.cookingMethod },
                canSave = draft.description.isNotBlank() || draft.dietItems.isNotEmpty(), isSaving = operation.saving,
                feedbackMessage = operation.feedback, isEditing = editingId != null,
            ),
            DietRecordCallbacks(
                onBack = onBack, onSelectCategory = onCategory,
                onManageImages = { editingId?.let(onManageImages) },
                onSelectMealType = { meal -> viewModel.updateDraft { draft -> draft.copy(mealType = mealCode(meal)) } },
                onDateChange = { value -> viewModel.updateDraft { it.copy(date = value) } },
                onTimeChange = { value -> viewModel.updateDraft { it.copy(time = value) } },
                onDescriptionChange = { value -> viewModel.updateDraft { it.copy(description = value) } },
                onAddFood = { name, amount -> viewModel.addDietItem(name, amount) },
                onRemoveFood = { index -> viewModel.removeDietItem(index) },
                onSelectPortionSize = { value -> viewModel.updateDraft { it.copy(portionNote = value.label) } },
                onSelectCookingStyle = { value -> viewModel.updateDraft { it.copy(cookingMethod = value.label) } },
                onSave = { viewModel.save(type) },
            ),
        )
        WorkspaceRecordType.STOOL -> BowelRecordScreen(
            BowelRecordUiState(
                occurredDate = draft.date, occurredTime = draft.time, bristolType = draft.bristolType,
                discomfort = BowelDiscomfort.entries.firstOrNull { discomfortCode(it) == draft.discomfort } ?: BowelDiscomfort.None,
                note = draft.bowelNote, canSave = draft.bristolType != null || draft.bowelNote.isNotBlank(),
                isSaving = operation.saving, feedbackMessage = operation.feedback, isEditing = editingId != null,
            ),
            BowelRecordCallbacks(
                onBack = onBack, onSelectCategory = onCategory,
                onManageImages = { editingId?.let(onManageImages) },
                onDateChange = { value -> viewModel.updateDraft { it.copy(date = value) } },
                onTimeChange = { value -> viewModel.updateDraft { it.copy(time = value) } },
                onSelectBristolType = { value -> viewModel.updateDraft { it.copy(bristolType = value) } },
                onSelectDiscomfort = { value -> viewModel.updateDraft { it.copy(discomfort = discomfortCode(value)) } },
                onNoteChange = { value -> viewModel.updateDraft { it.copy(bowelNote = value) } },
                onSave = { viewModel.save(type) },
            ),
        )
        WorkspaceRecordType.SYMPTOM -> SymptomRecordScreen(
            SymptomRecordUiState(
                selectedCode = draft.symptomCode, severity = draft.severity, startedTime = draft.time,
                durationMinutes = draft.duration, change = if (draft.symptomStatus == "relieved") SymptomChange.Better else SymptomChange.Same,
                note = draft.symptomNote,
                canSave = draft.symptomCode != null && (draft.symptomCode != "other" || draft.otherDescription.isNotBlank()),
                isSaving = operation.saving, feedbackMessage = operation.feedback,
                otherDescription = draft.otherDescription, isEditing = editingId != null,
            ),
            SymptomRecordCallbacks(
                onBack = onBack, onSelectCategory = onCategory,
                onSelectSymptom = { choice -> viewModel.updateDraft { it.copy(symptomCode = choice.code) } },
                onOtherDescriptionChange = { value -> viewModel.updateDraft { it.copy(otherDescription = value) } },
                onSeverityChange = { value -> viewModel.updateDraft { it.copy(severity = value) } },
                onStartedTimeChange = { value -> viewModel.updateDraft { it.copy(time = value) } },
                onDurationChange = { value -> viewModel.updateDraft { it.copy(duration = value) } },
                onSelectChange = { value -> viewModel.updateDraft { it.copy(symptomStatus = if (value == SymptomChange.Better) "relieved" else "ongoing") } },
                onNoteChange = { value -> viewModel.updateDraft { it.copy(symptomNote = value) } },
                onSave = { viewModel.save(type) },
            ),
        )
        WorkspaceRecordType.MOOD -> MoodRecordScreen(
            MoodRecordUiState(
                selectedLevel = draft.moodLevel, occurredDate = draft.date, occurredTime = draft.time,
                note = draft.moodNote, canSave = draft.moodLevel != null, isSaving = operation.saving,
                feedbackMessage = operation.feedback, isEditing = editingId != null,
            ),
            MoodRecordCallbacks(
                onBack = onBack, onSelectCategory = onCategory,
                onSelectMood = { option -> viewModel.updateDraft { it.copy(moodLevel = option.level) } },
                onDateChange = { value -> viewModel.updateDraft { it.copy(date = value) } },
                onTimeChange = { value -> viewModel.updateDraft { it.copy(time = value) } },
                onNoteChange = { value -> viewModel.updateDraft { it.copy(moodNote = value) } },
                onSave = { viewModel.save(type) },
            ),
        )
    }
}

private fun categoryRoute(type: WorkspaceRecordType): AppRoute = when (type) {
    WorkspaceRecordType.DIET -> AppRoute.DietRecords
    WorkspaceRecordType.STOOL -> AppRoute.StoolRecords
    WorkspaceRecordType.SYMPTOM -> AppRoute.SymptomRecords
    WorkspaceRecordType.MOOD -> AppRoute.MoodRecords
}

private fun recordFormRoute(category: RecordCategory): AppRoute = when (category) {
    RecordCategory.Diet -> AppRoute.DietRecordNew
    RecordCategory.Bowel -> AppRoute.StoolRecordNew
    RecordCategory.Symptoms -> AppRoute.SymptomRecordNew
    RecordCategory.Mood -> AppRoute.MoodRecordNew
    RecordCategory.Activity -> AppRoute.Records
}

private fun WorkspaceRecordType.toCategory(): RecordCategory = when (this) {
    WorkspaceRecordType.DIET -> RecordCategory.Diet
    WorkspaceRecordType.STOOL -> RecordCategory.Bowel
    WorkspaceRecordType.SYMPTOM -> RecordCategory.Symptoms
    WorkspaceRecordType.MOOD -> RecordCategory.Mood
}

private fun mealCode(value: MealType): String = when (value) {
    MealType.Breakfast -> "breakfast"
    MealType.Lunch -> "lunch"
    MealType.Dinner -> "dinner"
    MealType.Snack -> "snack"
    MealType.Other -> "other"
}

private fun discomfortCode(value: BowelDiscomfort): String? = when (value) {
    BowelDiscomfort.None -> null
    BowelDiscomfort.Pain -> "abdominal_pain"
    BowelDiscomfort.Bloating -> "bloating"
}

private fun recordTypeFromRouteKey(value: String?): WorkspaceRecordType? = WorkspaceRecordType.entries.firstOrNull { it.routeKey == value }

@Composable
private fun FeatureUnavailable(message: String) {
    androidx.compose.foundation.layout.Column(Modifier.fillMaxSize().padding(24.dp).testTag("feature_unavailable")) {
        Text(message, color = androidx.compose.material3.MaterialTheme.colorScheme.onSurfaceVariant)
    }
}
