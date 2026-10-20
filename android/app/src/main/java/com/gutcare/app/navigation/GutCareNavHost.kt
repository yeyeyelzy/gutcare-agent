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
import com.gutcare.app.ui.records.*
import com.gutcare.app.ui.auth.AuthOperationState
import com.gutcare.app.ui.auth.AuthValidators
import com.gutcare.app.ui.auth.AuthWorkflow
import com.gutcare.app.ui.auth.EmailVerificationScreen
import com.gutcare.app.ui.auth.LoginScreen
import com.gutcare.app.ui.auth.PasswordResetConfirmScreen
import com.gutcare.app.ui.auth.PasswordResetRequestScreen
import com.gutcare.app.ui.auth.ProfileBootstrapScreen
import com.gutcare.app.ui.auth.RegisterCredentialsScreen
import com.gutcare.app.ui.auth.RegistrationDraft
import com.gutcare.app.ui.auth.UnconnectedAuthWorkflow
import com.gutcare.app.ui.auth.WelcomeScreen
import com.gutcare.app.ui.tabs.ProtectedTabShell
import com.gutcare.app.core.network.RegistrationNoticeSummaries

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
    patientProfile: PatientProfileDto? = null,
) {
    var registrationDraft by remember { mutableStateOf(RegistrationDraft()) }
    var loginOperation by remember { mutableStateOf<AuthOperationState>(AuthOperationState.Idle) }
    var registrationOperation by remember { mutableStateOf<AuthOperationState>(AuthOperationState.Idle) }
    var passwordResetOperation by remember { mutableStateOf<AuthOperationState>(AuthOperationState.Idle) }
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
    LaunchedEffect(patientProfile?.timezone) { recordsViewModel.setTimeZone(patientProfile?.timezone) }
    LaunchedEffect(sessionState) {
        if (sessionState is AppSessionState.Public) recordsViewModel.clearForLogout()
        if (sessionState is AppSessionState.Public) medicalDocumentsViewModel.clearForLogout()
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

    NavHost(
        navController = navController,
        startDestination = RoutePolicy.startDestination(sessionState).value,
    ) {
        composable(AppRoute.Welcome.value) {
            WelcomeScreen(
                onLogin = { navigate(AppRoute.Login, clearDraft = true) },
                onRegister = { navigate(AppRoute.RegisterCredentials) },
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
                onRegister = { navigate(AppRoute.RegisterCredentials, clearDraft = true) },
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
            if (!RoutePolicy.canEnterProfile(registrationDraft)) {
                LaunchedEffect(Unit) {
                    navController.navigate(AppRoute.RegisterCredentials.value) { launchSingleTop = true }
                }
            } else {
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
                                if (result is AuthOperationState.Accepted) {
                                    registrationDraft = registrationDraft.clearForExit()
                                    navController.navigate(AppRoute.EmailVerification.value) {
                                        popUpTo(AppRoute.RegisterCredentials.value) { inclusive = true }
                                        launchSingleTop = true
                                    }
                                }
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
                        displayName = patientProfile?.nickname,
                        summaryMessage = "今日摘要服务尚未接入；可使用下方入口记录本人健康数据。",
                    ),
                    TodayCallbacks(
                        onQuickRecord = { navigate(recordFormRoute(it)) },
                        onOpenMeals = { navigate(AppRoute.DietRecords) },
                        onOpenProfile = { navigate(AppRoute.HealthArchive) },
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
            ProtectedRoot(sessionState, navController, RootTab.Analysis, onLogout) { ProtectedPlaceholderScreen(RootTab.Analysis) }
        }
        composable(AppRoute.Me.value) {
            ProtectedRoot(sessionState, navController, RootTab.Me, onLogout) { ProtectedPlaceholderScreen(RootTab.Me) { onLogout { } } }
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
                        onDelete = { recordsViewModel.deleteDetail(type) })
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
