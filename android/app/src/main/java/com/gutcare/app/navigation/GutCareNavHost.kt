package com.gutcare.app.navigation

import androidx.compose.runtime.Composable
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import com.gutcare.app.ui.home.HomeScreen
import com.gutcare.app.ui.home.HomeViewModel

private object Routes {
    const val Home = "home"
}

@Composable
fun GutCareNavHost(navController: NavHostController) {
    NavHost(navController = navController, startDestination = Routes.Home) {
        composable(Routes.Home) {
            val homeViewModel: HomeViewModel = viewModel()
            val uiState = homeViewModel.uiState.collectAsStateWithLifecycle()
            HomeScreen(uiState = uiState.value)
        }
    }
}
