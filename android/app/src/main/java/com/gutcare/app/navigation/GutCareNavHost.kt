package com.gutcare.app.navigation

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
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

/**
 * Navigation owns public-flow drafts only in Compose memory. It deliberately has no access to the
 * secure session store: a later core adapter must supply [AppSessionState] after authenticating.
 */
@Composable
fun GutCareNavHost(
    navController: NavHostController,
    sessionState: AppSessionState = AppSessionState.Public,
    authWorkflow: AuthWorkflow = UnconnectedAuthWorkflow,
) {
    var registrationDraft by remember { mutableStateOf(RegistrationDraft()) }
    var loginOperation by remember { mutableStateOf<AuthOperationState>(AuthOperationState.Idle) }
    var registrationOperation by remember { mutableStateOf<AuthOperationState>(AuthOperationState.Idle) }
    var passwordResetOperation by remember { mutableStateOf<AuthOperationState>(AuthOperationState.Idle) }

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
                    authWorkflow.login(email, password) { result -> loginOperation = result }
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
        composable(AppRoute.Today.value) { ProtectedRoot(sessionState, navController, RootTab.Today) }
        composable(AppRoute.Records.value) { ProtectedRoot(sessionState, navController, RootTab.Records) }
        composable(AppRoute.Analysis.value) { ProtectedRoot(sessionState, navController, RootTab.Analysis) }
        composable(AppRoute.Me.value) { ProtectedRoot(sessionState, navController, RootTab.Me) }
    }
}

@Composable
private fun ProtectedRoot(
    sessionState: AppSessionState,
    navController: NavHostController,
    selectedTab: RootTab,
) {
    if (sessionState !is AppSessionState.Authenticated) {
        LaunchedEffect(Unit) {
            navController.navigate(AppRoute.Welcome.value) {
                popUpTo(navController.graph.findStartDestination().id) { inclusive = true }
                launchSingleTop = true
            }
        }
        return
    }
    ProtectedTabShell(
        selectedTab = selectedTab,
        onSelectTab = { tab ->
            navController.navigate(tab.route.value) {
                popUpTo(navController.graph.findStartDestination().id) { saveState = true }
                launchSingleTop = true
                restoreState = true
            }
        },
    )
}
